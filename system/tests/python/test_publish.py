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


@pytest.mark.parametrize("text", [meeting("work", NAME), concept("work", "Sneaky", "[[Index]]")], ids=["meeting", "concept"])
def test_an_ingest_never_stages_a_note_under_meetings(run, text):
    target = f"wiki/work/meetings/{NAME}.md"
    stage_new(run, target, text)
    decide(run, rec(target))
    assert "meeting notes are written only by the meeting import" in reasons(publish.validate_run(run, RID, now=LATER)[2])
