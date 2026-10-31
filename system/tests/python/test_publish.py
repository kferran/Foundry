import json
import os
import time

import pytest

from helpers import concept, meeting, transcript, write
from vaultlib import publish

RID = "20261001T120000-ingest-ab12"
MID = "20261005T160000-meeting-ab12"
NAME = "2026-10-05-1500-weekly-sync"
LATER = time.time() + 3600


def stage_new(vault, rel, text, run_id=RID):
    return write(vault, f"wiki/.staging/{run_id}/{rel}", text)


def decide(vault, *records, run_id=RID):
    lines = [json.dumps(r) for r in records]
    write(vault, f"wiki/.staging/{run_id}/_decisions.jsonl", "\n".join(lines) + "\n")


def rec(target, decision="create"):
    return {"item": "i", "decision": decision, "target": target, "source": "s", "reason": "r"}


@pytest.fixture
def run(vault):
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    return vault


def reasons(problems):
    return [p.reason for p in problems]


def test_check_run_id():
    assert publish.check_run_id(RID) == "ingest"
    assert publish.check_run_id(MID) == "meeting"
    for bad in ("x", "20261001T120000-rm-ab12", "../20261001T120000-ingest-ab12"):
        with pytest.raises(publish.PublishError):
            publish.check_run_id(bad)


def test_snapshot_records_existing_targets(run):
    snap = json.loads((run / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert "wiki/work/concepts/Kafka.md" in snap["files"] and "wiki/shared/concepts/Git.md" in snap["files"]
    assert "wiki/personal/concepts/Gardening.md" not in snap["files"]
    assert (run / "wiki/.staging" / RID).is_dir()
    with pytest.raises(publish.PublishError):
        publish.snapshot(run, RID, ["wiki/work/**"])


def test_valid_new_note(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New", "[[Kafka]] [[Index]]"))
    decide(run, rec("wiki/work/concepts/New.md"))
    staged, decisions, problems = publish.validate_run(run, RID, now=LATER)
    assert staged == ["wiki/work/concepts/New.md"] and problems == []


def test_target_outside_targets_rejected(run):
    stage_new(run, "wiki/personal/concepts/P.md", concept("personal", "P"))
    decide(run, rec("wiki/personal/concepts/P.md"))
    assert "not a publishable target" in reasons(publish.validate_run(run, RID, now=LATER)[2])


def test_schema_error_rejected(run):
    stage_new(run, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad\n")
    decide(run, rec("wiki/work/concepts/Bad.md"))
    assert any(r.startswith("schema:") for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_partition_wall_rejected(run):
    stage_new(run, "wiki/work/concepts/W.md", concept("work", "W", "[[Gardening]]"))
    decide(run, rec("wiki/work/concepts/W.md"))
    assert any("partition wall" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_a_created_note_with_a_bad_tag_is_rejected(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New", "[[Index]]", tags="[Tooling]"))
    decide(run, rec("wiki/work/concepts/New.md"))
    assert any('tag "Tooling"' in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_a_patch_keeps_an_old_bad_tag(vault):
    write(vault, "wiki/work/concepts/Kafka.md", concept("work", "Kafka", "event streaming", tags="[Streaming]"))
    publish.snapshot(vault, RID, ["wiki/work/**"])
    dst = publish.record_stage(vault, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text(dst.read_text().replace("event streaming", "event streaming at scale"))
    decide(vault, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert publish.validate_run(vault, RID, now=LATER)[2] == []


def test_a_patch_that_adds_a_bad_tag_is_rejected(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text(dst.read_text().replace("tags: [streaming]", "tags: [streaming, Tooling, now]"))
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    found = [r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]) if "tag" in r]
    assert len(found) == 2 and 'tag "Tooling"' in found[0] and 'tag "now"' in found[1]


def test_existing_target_must_be_staged_via_stage(run):
    stage_new(run, "wiki/work/concepts/Kafka.md", concept("work", "Kafka", "rewritten wholesale"))
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert any("not staged with vault_index.py stage" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_stage_then_patch_ok(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text(dst.read_text().replace("event streaming", "event streaming at scale"))
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert publish.validate_run(run, RID, now=LATER)[2] == []


def test_shrink_guard(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text("---\ntype: concept\ntags: []\ncompiled_at: \"2026-09-01\"\npartition: work\n---\nx\n")
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    rs = reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert any("headings removed" in r for r in rs) and any("below 60%" in r for r in rs)
    decide(run, rec("wiki/work/concepts/Kafka.md", "deprecate"))
    assert not any(r.startswith("shrink guard") for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


PIPELINE = ("## Pipeline\nBuilds run on every push to the main branch and on every pull request.\n"
            "The gate runs before each publish and refuses a red build.\n")
TRAIN = "Release tags follow the build date.\nEach tag is signed.\n"
ROLLBACK = ("## Rollback\nRollback restores the last good tag and restarts the service.\n"
            "The logs of the failed build are kept for thirty days.\n")
STATE_HEADING = "## Release train (merged, not yet in the vault)\n"


@pytest.fixture
def sectioned(vault):
    """A note with three sections, the middle heading encoding a pending state, staged for a patch."""
    write(vault, "wiki/work/concepts/Deploys.md",
          concept("work", "Deploys", PIPELINE + "\n" + STATE_HEADING + TRAIN + "\n" + ROLLBACK))
    publish.snapshot(vault, RID, ["wiki/work/**"])
    decide(vault, rec("wiki/work/concepts/Deploys.md", "patch"))
    return publish.record_stage(vault, RID, "wiki/work/concepts/Deploys.md")


def test_shrink_guard_accepts_a_heading_renamed_in_place(vault, sectioned):
    """(#160) spec 2026-10-14 shrink-guard-rename rule 3"""
    sectioned.write_text(sectioned.read_text().replace(STATE_HEADING, "## Release train\n")
                         .replace(TRAIN, TRAIN + "It reached the vault on 2026-10-14.\n"))
    assert publish.validate_run(vault, RID, now=LATER)[2] == []


def test_shrink_guard_refuses_a_rename_that_drops_section_lines(vault, sectioned):
    """(#160) the section must keep every non-blank line"""
    sectioned.write_text(sectioned.read_text().replace(STATE_HEADING + TRAIN,
                                                       "## Release train\nRelease tags follow the build date.\n"))
    rs = reasons(publish.validate_run(vault, RID, now=LATER)[2])
    assert any("headings removed: " + STATE_HEADING.strip() in r for r in rs)
    assert not any("below 60%" in r for r in rs)


def test_shrink_guard_refuses_a_heading_removed_with_its_section(vault, sectioned):
    """(#160) removal stays refused while the body keeps 60%"""
    sectioned.write_text(sectioned.read_text().replace(STATE_HEADING + TRAIN, ""))
    rs = reasons(publish.validate_run(vault, RID, now=LATER)[2])
    assert any("headings removed: " + STATE_HEADING.strip() in r for r in rs)
    assert not any("below 60%" in r for r in rs)


def test_shrink_guard_refuses_a_renamed_heading_moved_elsewhere(vault, sectioned):
    """(#160) the heading at the old position is judged, and it is an existing one"""
    text = sectioned.read_text().replace(STATE_HEADING + TRAIN + "\n", "")
    sectioned.write_text(text + "\n## Release train\n" + TRAIN)
    rs = reasons(publish.validate_run(vault, RID, now=LATER)[2])
    assert any("headings removed: " + STATE_HEADING.strip() in r for r in rs)


def patch_note(vault, old_body, new_body):
    """Write a note with old_body, snapshot, stage it as a patch and rewrite the staged copy with new_body."""
    write(vault, "wiki/work/concepts/Deploys.md", concept("work", "Deploys", old_body))
    publish.snapshot(vault, RID, ["wiki/work/**"])
    decide(vault, rec("wiki/work/concepts/Deploys.md", "patch"))
    publish.record_stage(vault, RID, "wiki/work/concepts/Deploys.md").write_text(concept("work", "Deploys", new_body))
    return reasons(publish.validate_run(vault, RID, now=LATER)[2])


S1 = "The first release shipped on time and the vendor contract was signed for one year.\n"
S2 = "- [ ] owner task: pay the vendor\n"
A_, B_, C_ = ("Alpha section line one.\n", "Beta section line one.\n", "Gamma section line one.\n")


def test_shrink_guard_refuses_a_duplicate_heading_deleted_beside_a_rename(vault):
    """(#160) a rename consumes one occurrence of a repeated heading, never all of them"""
    rs = patch_note(vault, "## Alpha\n### Status\n" + S1 + "## Beta\n### Status\n" + S2,
                    "## Alpha\n### Status (done)\n" + S1 + "## Beta\n")
    assert any("headings removed: ### Status" in r for r in rs)
    assert not any("below 60%" in r for r in rs)


def test_shrink_guard_refuses_deleting_one_of_two_duplicate_headings(vault):
    """(#160) headings are counted, so one surviving copy does not cover a deleted one"""
    rs = patch_note(vault, "## Alpha\n### Status\n" + S1 + "## Beta\n### Status\n" + S2,
                    "## Alpha\n### Status\n" + S1 + "## Beta\n")
    assert any("headings removed: ### Status" in r for r in rs)
    assert not any("below 60%" in r for r in rs)


def test_shrink_guard_accepts_renaming_one_of_two_duplicate_headings(vault):
    """(#160) one copy renamed in place with its section kept, the other untouched"""
    old = "## Alpha\n### Status\n" + S1 + "## Beta\n### Status\n" + S2
    assert patch_note(vault, old, old.replace("### Status\n" + S1, "### Status (done)\n" + S1)) == []


def test_shrink_guard_refuses_a_rename_onto_a_title_the_note_has(vault):
    """(#160) the heading at the old position must carry a title new to the note"""
    rs = patch_note(vault, "## A\n" + A_ + "## B\n" + B_ + "## C\n" + C_, "## A\n" + A_ + "## C\n" + B_)
    assert any("headings removed: ## B" in r for r in rs)


def test_shrink_guard_refuses_a_rename_that_changes_level(vault):
    """(#160) a rename keeps the heading's level"""
    rs = patch_note(vault, "## A\n" + A_ + "## B\n" + B_ + "## C\n" + C_,
                    "## A\n" + A_ + "### X\n" + B_ + "## C\n" + C_)
    assert any("headings removed: ## B" in r for r in rs)


def test_protected_fields(run):
    stage_new(run, "wiki/work/preferences/P.md",
              '---\ntype: preference\nstatement: "x"\npartition: work\naccepted_at: "2026-10-01"\n---\n# P\n')
    decide(run, rec("wiki/work/preferences/P.md"))
    assert any("protected field accepted_at" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


DIGEST = ('---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "s-1"\n'
          'created_at: "2026-10-01T11:00:00Z"\nprovenance: ["session"]\n---\n'
          '## Corrections\n- Always run the gate before a push — after a red pull request\n')
PREFERENCE = ('---\ntype: preference\nstatement: "Always run the gate before a push"\npartition: work\n'
              'codebase: "vault"\nevidence: ["[[2026-10-01-s-1]]"]\ncreated_at: "2026-10-01"\n---\n'
              '# Gate Before Push\n\nAfter a red pull request.\n')


def test_a_preference_written_as_ingest_says_publishes(run):
    """The note shape .claude/commands/ingest.md asks for (step Preferences) passes the gate."""
    write(run, "raw/work/notes/2026-10-01-s-1.md", DIGEST)
    stage_new(run, "wiki/work/preferences/GateBeforePush.md", PREFERENCE)
    decide(run, rec("wiki/work/preferences/GateBeforePush.md"))
    assert publish.validate_run(run, RID, now=LATER)[2] == []


def test_a_shared_preference_is_rejected(run):
    write(run, "raw/work/notes/2026-10-01-s-1.md", DIGEST)
    stage_new(run, "wiki/shared/preferences/GateBeforePush.md", PREFERENCE.replace("partition: work", "partition: shared"))
    decide(run, rec("wiki/shared/preferences/GateBeforePush.md"))
    assert "schema: type 'preference' is not allowed in this folder" in reasons(publish.validate_run(run, RID, now=LATER)[2])


def test_a_second_digest_appended_to_evidence_publishes(vault):
    write(vault, "raw/work/notes/2026-10-01-s-1.md", DIGEST)
    write(vault, "raw/work/notes/2026-10-02-s-2.md", DIGEST.replace('"s-1"', '"s-2"'))
    old = write(vault, "wiki/work/preferences/GateBeforePush.md", PREFERENCE)
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    dst = publish.record_stage(vault, RID, "wiki/work/preferences/GateBeforePush.md")
    dst.write_text(dst.read_text().replace('["[[2026-10-01-s-1]]"]', '["[[2026-10-01-s-1]]", "[[2026-10-02-s-2]]"]'))
    decide(vault, rec("wiki/work/preferences/GateBeforePush.md", "patch"))
    assert publish.validate_run(vault, RID, now=LATER)[2] == []


def test_conflicts(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New"))
    decide(run, rec("wiki/work/concepts/New.md"))
    write(run, "wiki/work/concepts/New.md", concept("work", "New", "user created it meanwhile"))
    assert any("created during the run" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_recent_edit_is_conflict(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text(dst.read_text() + "\nmore\n")
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    # copytree keeps the fixture's old mtime; make the target's recent edit explicit (content/hash unchanged)
    os.utime(run / "wiki/work/concepts/Kafka.md", None)
    assert any("last 60 s" in r for r in reasons(publish.validate_run(run, RID, now=time.time())[2]))


def test_decisions_required_and_validated(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New"))
    assert any("_decisions.jsonl" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))
    write(run, f"wiki/.staging/{RID}/_decisions.jsonl", "not json\n{\"item\": 1}\n")
    rs = reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert any("invalid JSON" in r for r in rs) and any("invalid decision record" in r for r in rs)


def test_noop_must_cite_existing_note(run):
    decide(run, rec("wiki/work/concepts/Ghost.md", "noop"))
    assert any("noop must cite an existing note" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_staged_symlink_rejected(run, tmp_path):
    outside = tmp_path / "evil.md"
    outside.write_text("x")
    link = run / "wiki/.staging" / RID / "wiki/work/concepts/Evil.md"
    link.parent.mkdir(parents=True)
    os.symlink(outside, link)
    decide(run, rec("wiki/work/concepts/Evil.md"))
    assert any("symlink" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_unsafe_staged_path_rejected(run):
    decide(run, rec("../../etc/passwd"))
    assert any("unsafe path" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_record_stage_refuses_non_targets_and_unknown_runs(run):
    with pytest.raises(publish.PublishError):
        publish.record_stage(run, RID, "wiki/personal/concepts/Gardening.md")
    with pytest.raises(publish.PublishError):
        publish.record_stage(run, "20261001T120000-ingest-ffff", "wiki/work/concepts/Kafka.md")
    with pytest.raises(publish.PublishError):
        publish.record_stage(run, RID, "../outside.md")


def test_record_stage_holds_stage_lock_while_writing_the_snapshot(run, monkeypatch):
    """A second writer blocks on stage.lock until the first has written snapshot.json (audit C1 spec §2)."""
    import fcntl
    real, seen = publish._write_json, []

    def locked_write(path, data):
        with open(run / "system/logs/runs" / RID / "stage.lock", "w") as other:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        seen.append(path)
        real(path, data)

    monkeypatch.setattr(publish, "_write_json", locked_write)
    publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    assert len(seen) == 1


def test_list_valued_decision_is_invalid_record_not_crash(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New"))
    decide(run, rec("wiki/work/concepts/New.md", ["create"]))
    assert any("invalid decision record" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_non_string_decision_fields_are_invalid_records(run):
    bad = [{"item": "i", "decision": "create", "target": ["t"], "source": "s", "reason": "r"},
           {"item": "i", "decision": {"a": 1}, "target": "wiki/work/concepts/N.md", "source": "s", "reason": "r"}]
    decide(run, *bad)
    rs = reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert sum("invalid decision record" in r for r in rs) == 2


def test_list_valued_type_is_a_problem_not_a_crash(run):
    stage_new(run, "wiki/work/concepts/New.md", "---\ntype: [concept]\npartition: work\n---\n# New\n")
    decide(run, rec("wiki/work/concepts/New.md"))
    assert publish.validate_run(run, RID, now=LATER)[2]


def test_unexpected_check_exception_becomes_problem(run, monkeypatch):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New"))
    decide(run, rec("wiki/work/concepts/New.md"))

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(publish, "_walls", boom)
    assert any(r.startswith("internal error:") for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_cannot_stage_note_created_during_the_run(run):
    write(run, "wiki/work/concepts/Late.md", concept("work", "Late", "long body " * 50 + "\n## Section\n"))
    with pytest.raises(publish.PublishError, match="created during the run"):
        publish.record_stage(run, RID, "wiki/work/concepts/Late.md")


def test_fresh_staging_over_note_created_during_run_is_conflict(run):
    late = write(run, "wiki/work/concepts/Late.md", concept("work", "Late", "long body " * 50))
    before = late.read_text()
    stage_new(run, "wiki/work/concepts/Late.md", concept("work", "Late", "x"))
    decide(run, rec("wiki/work/concepts/Late.md"))
    assert any("created during the run" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))
    assert late.read_text() == before


@pytest.mark.parametrize("content", ["{bad", '{"targets": "x", "files": {}, "staged": {}}',
                                     '{"targets": [], "files": [], "staged": {}}', "[]"])
def test_corrupt_snapshot_is_publish_error(run, content):
    (run / "system/logs/runs" / RID / "snapshot.json").write_text(content)
    with pytest.raises(publish.PublishError, match="corrupt snapshot"):
        publish.load_snapshot(run, RID)
    with pytest.raises(publish.PublishError):
        publish.validate_run(run, RID, now=LATER)


# -- F3: snapshot environment faults --------------------------------------

def test_snapshot_skips_a_file_that_vanishes_mid_walk(vault, monkeypatch):
    real = publish.sha256_file

    def vanishing(path):
        if str(path).endswith("wiki/work/concepts/Kafka.md"):
            raise FileNotFoundError(path)
        return real(path)

    monkeypatch.setattr(publish, "sha256_file", vanishing)
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    snap = json.loads((vault / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert "wiki/work/concepts/Kafka.md" not in snap["files"]
    assert "wiki/shared/concepts/Git.md" in snap["files"]


def test_snapshot_other_oserror_is_a_publish_error(vault, monkeypatch):
    def unreadable(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(publish, "sha256_file", unreadable)
    with pytest.raises(publish.PublishError, match="snapshot failed"):
        publish.snapshot(vault, RID, ["wiki/work/**"])


# -- F10/F11: target guards ------------------------------------------------

def test_non_markdown_target_rejected(run):
    stage_new(run, "wiki/work/x.sh", concept("work", "X"))
    decide(run, rec("wiki/work/x.sh"))
    assert "not a markdown note" in reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert publish.commit_run(run, RID, now=LATER)["status"] == "rejected"
    assert not (run / "wiki/work/x.sh").exists()


def test_existing_non_utf8_target_rejected(vault):
    (vault / "wiki/work/concepts/Bin.md").write_bytes(
        b'---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n'
        b'accepted_at: "2026-09-01"\n---\n# Bin\n\xff\xfe body\n')
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    dst = publish.record_stage(vault, RID, "wiki/work/concepts/Bin.md")
    dst.write_text(concept("work", "Bin", "patched"))
    decide(vault, rec("wiki/work/concepts/Bin.md", "patch"))
    rs = reasons(publish.validate_run(vault, RID, now=LATER)[2])
    assert "existing note unreadable" in rs


def test_a_meeting_run_publishes_its_two_exact_targets(vault):
    targets = [f"wiki/work/meetings/{NAME}.md", f"wiki/work/meetings/{NAME}.transcript.md"]
    publish.snapshot(vault, MID, targets)
    stage_new(vault, targets[0], meeting("work", NAME, body="[[Index]]"), run_id=MID)
    stage_new(vault, targets[1], transcript("work", NAME), run_id=MID)
    report = publish.commit_run(vault, MID, now=LATER)
    assert (report["status"], report["published"]) == ("published", targets)
    assert 'provenance: ["headless"]' in (vault / targets[0]).read_text()


def test_an_ingest_never_publishes_a_now_page(run):
    # Audit S5: "never stage Now.md" was prompt text only; the brief and now.py own the page.
    target = "wiki/work/Now.md"
    stage_new(run, target, "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n"
              "# Now\n\n## Needs you\n- [ ] owed: Wire the money (since 2026-10-01)\n")
    decide(run, rec(target))
    assert "the Now page is written only by now.py and the brief" in reasons(publish.validate_run(run, RID, now=LATER)[2])


def test_an_index_note_outside_wiki_index_gets_no_wall_exemption(run):
    # Audit S2: type: index skipped the partition wall anywhere under wiki/.
    target = "wiki/work/concepts/Hub.md"
    stage_new(run, target, "---\ntype: index\ntags: []\n---\n# Hub\n[[Gardening]]\n")
    decide(run, rec(target))
    rs = reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert any("partition wall" in r for r in rs)
    assert any(r.startswith("schema:") for r in rs)


@pytest.mark.parametrize("text", [meeting("work", NAME), concept("work", "Sneaky", "[[Index]]")], ids=["meeting", "concept"])
def test_an_ingest_never_stages_a_note_under_meetings(run, text):
    target = f"wiki/work/meetings/{NAME}.md"
    stage_new(run, target, text)
    decide(run, rec(target))
    assert "meeting notes are written only by the meeting import" in reasons(publish.validate_run(run, RID, now=LATER)[2])


def test_private_folder_is_never_staged_or_published(vault):
    """A headless run can neither copy a private note out (stage) nor write one in (publish) (#166)."""
    write(vault, "wiki/work/private/Secret.md", concept("work", "Secret"))
    publish.snapshot(vault, RID, ["wiki/work/**"])
    with pytest.raises(publish.PublishError, match="not a publishable target"):
        publish.record_stage(vault, RID, "wiki/work/private/Secret.md")
    stage_new(vault, "wiki/work/private/New.md", concept("work", "New"))
    decide(vault, rec("wiki/work/private/New.md"))
    assert "not a publishable target" in reasons(publish.validate_run(vault, RID, now=LATER)[2])


def test_snapshot_never_lists_a_private_note(vault):
    """snapshot.json holds file names and hashes; a private note's name stays out of it (#166)."""
    write(vault, "wiki/work/private/Secret.md", concept("work", "Secret"))
    publish.snapshot(vault, RID, ["wiki/work/**"])
    snap = json.loads((vault / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert "wiki/work/concepts/Kafka.md" in snap["files"]
    assert not [f for f in snap["files"] if "/private/" in f]


BID = "20261001T120000-brief-ab12"
NOW_HEAD = "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n# Now\n\n## Needs you\n"
OLD_LONG = f"- [ ] owed: {'old ' * 80}(since 2026-09-01)"


def brief_run(vault, page_lines):
    """A brief run that stages wiki/work/Now.md with these lines over a live page holding OLD_LONG."""
    write(vault, "wiki/work/Now.md", NOW_HEAD + OLD_LONG + "\n")
    os.utime(vault / "wiki/work/Now.md", (time.time() - 600, time.time() - 600))
    publish.snapshot(vault, BID, ["wiki/work/**"])
    publish.record_stage(vault, BID, "wiki/work/Now.md")
    stage_new(vault, "wiki/work/Now.md", NOW_HEAD + "\n".join(page_lines) + "\n", run_id=BID)
    return [r for r in reasons(publish.validate_run(vault, BID, now=LATER)[2]) if "Now line" in r]


def test_the_gate_refuses_a_new_now_line_over_300_characters(vault):
    added = f"- [ ] owed: {'x' * 270} (since 2026-10-01)"
    assert len(added) > 300
    assert brief_run(vault, [OLD_LONG, added]) == [
        "a Now line the check would redact or cut: run now.py fit-staged before publish"]


HAND = "- [ ] owed: two  spaces (since 2026-10-01)"   # not in now.py's form: checked whole, never rebuilt


def test_the_gate_refuses_an_added_now_line_holding_a_credential_and_passes_a_clean_hand_shaped_one(vault):
    key = "ghp_" + "a" * 36
    assert brief_run(vault, [OLD_LONG, f"- [ ] owed: Rotate {key} (since 2026-10-01)", HAND]) == [
        "a Now line the check would redact or cut: run now.py fit-staged before publish"]


def test_the_gate_refuses_a_long_hand_shaped_now_line(vault):
    assert brief_run(vault, [OLD_LONG, f"- [ ] owed: two  spaces {'h' * 280} (since 2026-10-01)"]) == [
        "a Now line: over 300 characters and not in now.py's form: move its history to a note under it"]


def test_the_gate_passes_an_unchanged_long_line_and_one_at_300(vault):
    at_cap = "- [ ] owed: " + "y" * (300 - len("- [ ] owed:  (since 2026-10-01)")) + " (since 2026-10-01)"
    assert len(at_cap) == 300
    assert brief_run(vault, [OLD_LONG, at_cap]) == []


# -- #298: the gate refuses every path with a symlink below the vault root --

def commit_note(vault, target, run_id=RID):
    stage_new(vault, target, concept("work", "X", "[[Index]]"), run_id=run_id)
    decide(vault, rec(target), run_id=run_id)
    return publish.commit_run(vault, run_id, now=LATER)


def report_reasons(report):
    return [p["reason"] for p in report["problems"]]


@pytest.mark.parametrize("dest", ["wiki/work/private", "system/agents/workcells", None],
                         ids=["private", "workcells", "outside"])
def test_a_note_staged_through_a_linked_folder_is_refused(run, tmp_path, dest):
    real = run / dest if dest else tmp_path / "outside"
    real.mkdir(parents=True, exist_ok=True)
    os.symlink(real, run / "wiki/work/concepts/linked")
    report = commit_note(run, "wiki/work/concepts/linked/X.md")
    assert report["status"] == "rejected"
    assert "symlink on the target path" in report_reasons(report)
    assert not (real / "X.md").exists()


def test_an_in_tree_link_into_meetings_is_refused(run):
    (run / "wiki/work/meetings").mkdir()
    os.symlink(run / "wiki/work/meetings", run / "wiki/work/notes")
    report = commit_note(run, "wiki/work/notes/X.md")
    assert report["status"] == "rejected"
    assert "symlink on the target path" in report_reasons(report)
    assert not (run / "wiki/work/meetings/X.md").exists()


@pytest.mark.parametrize("existing", [False, True], ids=["dangling", "existing"])
def test_a_leaf_link_target_is_refused(run, tmp_path, existing):
    kafka = run / "wiki/work/concepts/Kafka.md"
    before = kafka.read_text()
    os.symlink(kafka if existing else tmp_path / "gone.md", run / "wiki/work/concepts/Leaf.md")
    report = commit_note(run, "wiki/work/concepts/Leaf.md")
    assert "symlink on the target path" in report_reasons(report)
    assert not (tmp_path / "gone.md").exists() and kafka.read_text() == before


def test_a_linked_staging_folder_is_refused(run, tmp_path):
    outside = tmp_path / "st"
    write(outside, "wiki/work/concepts/S.md", concept("work", "S", "[[Index]]"))
    write(outside, "_decisions.jsonl", json.dumps(rec("wiki/work/concepts/S.md")) + "\n")
    (run / "wiki/.staging" / RID).rmdir()
    os.symlink(outside, run / "wiki/.staging" / RID)
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "rejected"
    assert "staged path is a symlink" in report_reasons(report)
    assert not (run / "wiki/work/concepts/S.md").exists()
    assert not (run / "system/logs/runs" / RID / "_decisions.jsonl").exists()


def test_record_stage_refuses_an_exact_target_under_a_linked_folder(vault, tmp_path):
    write(tmp_path / "out", "X.md", concept("work", "X"))
    os.symlink(tmp_path / "out", vault / "wiki/work/concepts/linked")
    publish.snapshot(vault, RID, ["wiki/work/concepts/linked/X.md"])
    with pytest.raises(publish.PublishError, match="symlink on the target or staging path"):
        publish.record_stage(vault, RID, "wiki/work/concepts/linked/X.md")
    assert not (vault / "wiki/.staging" / RID / "wiki/work/concepts/linked/X.md").exists()


def test_a_vault_reached_through_a_linked_parent_publishes(vault, tmp_path):
    via = tmp_path / "vlink"
    os.symlink(vault, via)
    publish.snapshot(via, RID, ["wiki/work/**"])
    report = commit_note(via, "wiki/work/concepts/X.md")
    assert (report["status"], report["published"]) == ("published", ["wiki/work/concepts/X.md"])


@pytest.mark.parametrize("linked", ["wiki/.staging", "system/logs/runs"])
def test_snapshot_refuses_a_linked_staging_or_runs_folder(vault, tmp_path, linked):
    out = tmp_path / "out"
    out.mkdir()
    (vault / linked).parent.mkdir(parents=True, exist_ok=True)
    os.symlink(out, vault / linked)
    with pytest.raises(publish.PublishError, match="symlink"):
        publish.snapshot(vault, RID, ["wiki/work/**"])
    assert list(out.iterdir()) == []


def test_record_stage_refuses_a_linked_staging_subfolder(run, tmp_path):
    (tmp_path / "out").mkdir()
    (run / "wiki/.staging" / RID / "wiki").mkdir()
    os.symlink(tmp_path / "out", run / "wiki/.staging" / RID / "wiki/work")
    with pytest.raises(publish.PublishError, match="symlink"):
        publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    assert list((tmp_path / "out").iterdir()) == []


def test_commit_never_copies_decisions_through_a_linked_run_file(run, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("victim")
    os.symlink(victim, run / "system/logs/runs" / RID / "_decisions.jsonl")
    commit_note(run, "wiki/work/concepts/X.md")
    assert victim.read_text() == "victim"


def test_a_staged_hard_link_is_refused(vault):
    private = write(vault, "wiki/work/private/Secret.md", concept("work", "Secret", "[[Index]]"))
    before = private.read_text()
    publish.snapshot(vault, RID, ["wiki/work/**"])
    staged = vault / "wiki/.staging" / RID / "wiki/work/concepts/Secret.md"
    staged.parent.mkdir(parents=True)
    os.link(private, staged)
    decide(vault, rec("wiki/work/concepts/Secret.md"))
    report = publish.commit_run(vault, RID, now=LATER)
    assert "staged file is a hard link" in report_reasons(report)
    assert private.read_text() == before and not (vault / "wiki/work/concepts/Secret.md").exists()


def test_the_gate_passes_an_added_brief_line_that_names_its_writer(vault):
    assert brief_run(vault, [OLD_LONG, "- [ ] owed: New objective [via:: brief] (since 2026-10-01)"]) == []


HELD = ("- [ ] owed: Review 1 stale claims from a research Work Order before they reach the wiki: "
        "raw/work/held/2026-10-01-r.stale-claims.md [due:: 2026-10-31] (since 2026-10-01)")
OTHER = "- [ ] owed: Send the draft (since 2026-10-01)"
HELD_REFUSAL = "a Now line naming raw/<p>/held/ changes only by hand"


def held_run(vault, live, staged):
    """A brief run staging wiki/work/Now.md with `staged` lines over a live page holding `live` (confinement §3.7)."""
    write(vault, "wiki/work/Now.md", NOW_HEAD + "\n".join(live) + "\n")
    os.utime(vault / "wiki/work/Now.md", (time.time() - 600, time.time() - 600))
    publish.snapshot(vault, BID, ["wiki/work/**"])
    publish.record_stage(vault, BID, "wiki/work/Now.md")
    stage_new(vault, "wiki/work/Now.md", NOW_HEAD + "\n".join(staged) + "\n", run_id=BID)
    return [r for r in reasons(publish.validate_run(vault, BID, now=LATER)[2]) if "Now line" in r]


@pytest.mark.parametrize("staged", [
    [OTHER, HELD.replace("- [ ] ", "- [x] ", 1)],                       # ticked
    [OTHER],                                                             # removed
    [OTHER, HELD, HELD.replace("2026-10-01-r", "2026-10-01-q")],        # added
    [OTHER, HELD.replace("Review 1", "Review 2")],                       # reworded
], ids=["ticked", "removed", "added", "reworded"])
def test_the_gate_refuses_a_brief_that_changes_a_held_line(vault, staged):
    assert held_run(vault, [OTHER, HELD], staged) == [HELD_REFUSAL]


def test_the_gate_passes_a_brief_that_keeps_held_lines_and_moves_others(vault):
    assert held_run(vault, [OTHER, HELD], [HELD, OTHER, "- [ ] owed: A new line (since 2026-10-02)"]) == []
