import json
import time

import pytest

from helpers import concept, write
from vaultlib import frontmatter, publish

RID = "20261001T120000-ingest-ab12"
LATER = time.time() + 3600


def decide(vault, *records, run_id=RID):
    write(vault, f"wiki/.staging/{run_id}/_decisions.jsonl", "\n".join(json.dumps(r) for r in records) + "\n")


def rec(target, decision="create"):
    return {"item": "i", "decision": decision, "target": target, "source": "s", "reason": "r"}


@pytest.fixture
def run(vault):
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    return vault


def test_publish_new_note_with_provenance(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/New.md", concept("work", "New", "[[Index]]"))
    decide(run, rec("wiki/work/concepts/New.md"))
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "published" and report["published"] == ["wiki/work/concepts/New.md"]
    data = frontmatter.parse((run / "wiki/work/concepts/New.md").read_text()).data
    assert data["provenance"] == ["headless"]
    assert not (run / "wiki/.staging" / RID).exists()
    assert (run / "system/logs/runs" / RID / "_decisions.jsonl").is_file()
    journal = (run / "system/logs/runs" / RID / "publish.journal").read_text().splitlines()
    assert json.loads(journal[-1]) == {"committed": True}


def test_provenance_appended_not_replaced(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    text = dst.read_text().replace("partition: work", 'partition: work\nprovenance: ["interactive"]')
    dst.write_text(text + "\nmore\n")
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert publish.commit_run(run, RID, now=LATER)["status"] == "published"
    data = frontmatter.parse((run / "wiki/work/concepts/Kafka.md").read_text()).data
    assert data["provenance"] == ["interactive", "headless"]


def test_rejected_run_publishes_nothing_and_quarantines(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/Good.md", concept("work", "Good"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad\n")
    decide(run, rec("wiki/work/concepts/Good.md"), rec("wiki/work/concepts/Bad.md"))
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "rejected" and report["problems"]
    assert not (run / "wiki/work/concepts/Good.md").exists()
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/Good.md").is_file()


def test_noop_and_empty(run):
    decide(run, rec("wiki/work/concepts/Kafka.md", "noop"))
    assert publish.commit_run(run, RID, now=LATER)["status"] == "noop"
    rid2 = "20261001T120000-brief-ab12"
    publish.snapshot(run, rid2, ["briefings/2026-10-01.md"])
    assert publish.commit_run(run, rid2, now=LATER)["status"] == "empty"


def test_target_changed_between_validation_and_rename_is_held_back(run, monkeypatch):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real = publish._rename

    def racing_rename(src, dst):
        if dst.endswith("A.md"):
            write(run, "wiki/work/concepts/B.md", concept("work", "B", "user wrote this"))
        real(src, dst)

    monkeypatch.setattr(publish, "_rename", racing_rename)
    report = publish.commit_run(run, RID, now=LATER)
    assert report["published"] == ["wiki/work/concepts/A.md"] and report["conflicts"] == ["wiki/work/concepts/B.md"]
    assert "user wrote this" in (run / "wiki/work/concepts/B.md").read_text()


@pytest.mark.parametrize("crash_after", [0, 1])
def test_crash_mid_publish_rolls_forward(run, monkeypatch, crash_after):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real, calls = publish._rename, []

    def crashing(src, dst):
        if len(calls) == crash_after:
            raise KeyboardInterrupt("simulated crash")
        calls.append(dst)
        real(src, dst)

    monkeypatch.setattr(publish, "_rename", crashing)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish, "_rename", real)
    result = publish.recover(run)
    assert result["recovered"] == [RID]
    assert (run / "wiki/work/concepts/A.md").is_file() and (run / "wiki/work/concepts/B.md").is_file()
    assert json.loads((run / "system/logs/runs" / RID / "publish.journal").read_text().splitlines()[-1]) == {"committed": True}


def test_recover_quarantines_aborted_staging(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    result = publish.recover(run)
    assert result["aborted"] == [RID]
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/A.md").is_file()
    assert json.loads((run / "system/logs/runs" / RID / "publish.json").read_text())["status"] == "aborted"


def test_abort_run(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    assert publish.abort_run(run, RID)["status"] == "aborted"
    assert not (run / "wiki/.staging" / RID).exists()
