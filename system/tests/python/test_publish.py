import json
import os
import time

import pytest

from helpers import concept, write
from vaultlib import publish

RID = "20261001T120000-ingest-ab12"
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
