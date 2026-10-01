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
    assert report["status"] == "conflict"
    assert "user wrote this" in (run / "wiki/work/concepts/B.md").read_text()
    held = run / "system/quarantine" / RID / "staged/wiki/work/concepts/B.md"
    assert held.is_file() and "user wrote this" not in held.read_text()


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


def test_list_valued_type_commit_is_rejected_not_a_traceback(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/New.md", "---\ntype: [concept]\npartition: work\n---\n# New\n")
    decide(run, rec("wiki/work/concepts/New.md"))
    assert publish.commit_run(run, RID, now=LATER)["status"] == "rejected"


def test_journal_written_atomically(run, monkeypatch):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    decide(run, rec("wiki/work/concepts/A.md"))
    real = publish.os.replace

    def dying_replace(src, dst):
        if str(dst).endswith("publish.journal"):
            raise KeyboardInterrupt("crash while moving the journal into place")
        real(src, dst)

    monkeypatch.setattr(publish.os, "replace", dying_replace)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish.os, "replace", real)
    rd = run / "system/logs/runs" / RID
    assert not (rd / "publish.journal").exists()
    assert not (run / "wiki/work/concepts/A.md").exists()
    result = publish.recover(run)
    assert result["aborted"] == [RID] and result["recovered"] == []
    assert not (run / "wiki/work/concepts/A.md").exists()
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/A.md").is_file()


def test_recover_does_not_report_held_back_conflict_as_published(run, monkeypatch):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real_read, real_rename = publish._read_journal, publish._rename

    def read_then_user_writes_a(journal):
        entries = real_read(journal)
        write(run, "wiki/work/concepts/A.md", concept("work", "A", "user wrote this"))
        return entries

    def crash(src, dst):
        raise KeyboardInterrupt("simulated crash")

    monkeypatch.setattr(publish, "_read_journal", read_then_user_writes_a)
    monkeypatch.setattr(publish, "_rename", crash)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish, "_read_journal", real_read)
    monkeypatch.setattr(publish, "_rename", real_rename)
    assert publish.recover(run)["recovered"] == [RID]
    report = json.loads((run / "system/logs/runs" / RID / "publish.json").read_text())
    assert report["conflicts"] == ["wiki/work/concepts/A.md"]
    assert "wiki/work/concepts/A.md" not in report["published"]
    assert report["published"] == ["wiki/work/concepts/B.md"]
    assert report["status"] == "conflict"
    assert "user wrote this" in (run / "wiki/work/concepts/A.md").read_text()
    assert (run / "wiki/work/concepts/B.md").is_file()


def test_recover_survives_torn_journal_and_continues(run, monkeypatch):
    bad = "20261001T120000-ingest-0001"
    publish.snapshot(run, bad, ["wiki/work/**"])
    write(run, f"wiki/.staging/{bad}/wiki/work/concepts/T.md", concept("work", "T"))
    write(run, f"system/logs/runs/{bad}/publish.journal", '{"staged": "wiki/.st')
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real = publish._rename

    def crash(src, dst):
        raise KeyboardInterrupt("simulated crash")

    monkeypatch.setattr(publish, "_rename", crash)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish, "_rename", real)
    result = publish.recover(run)
    assert result["failed"] == [bad] and result["recovered"] == [RID]
    assert (run / "wiki/work/concepts/A.md").is_file() and (run / "wiki/work/concepts/B.md").is_file()
    report = json.loads((run / "system/logs/runs" / bad / "publish.json").read_text())
    assert report["status"] == "recovery_failed" and "unreadable journal" in report["problems"][0]["reason"]
    assert (run / "system/quarantine" / bad / "staged/wiki/work/concepts/T.md").is_file()
    assert not (run / "wiki/.staging" / bad).exists()


def test_recover_quarantines_conflicted_entries(run, monkeypatch):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real, calls = publish._rename, []

    def crash_second(src, dst):
        if calls:
            raise KeyboardInterrupt("simulated crash")
        calls.append(dst)
        real(src, dst)

    monkeypatch.setattr(publish, "_rename", crash_second)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish, "_rename", real)
    write(run, "wiki/work/concepts/B.md", concept("work", "B", "user wrote this"))
    publish.recover(run)
    assert "user wrote this" in (run / "wiki/work/concepts/B.md").read_text()
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/B.md").is_file()


# -- F1: model-staged paths that cannot be published -----------------------

def test_stage_under_an_existing_file_is_rejected_not_a_traceback(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/Kafka.md/bar.md", concept("work", "Bar"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/a/A.md", concept("work", "A"))
    decide(run, rec("wiki/work/concepts/Kafka.md/bar.md"), rec("wiki/work/concepts/a/A.md"))
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "rejected"
    assert any(p["path"] == "wiki/work/concepts/Kafka.md/bar.md" and "not a file path" in p["reason"]
               for p in report["problems"])
    assert not any("internal error" in p["reason"] for p in report["problems"])
    assert not (run / "wiki/work/concepts/a/A.md").exists()
    assert (run / "wiki/work/concepts/Kafka.md").is_file()


def test_stage_onto_an_existing_directory_is_rejected(run):
    (run / "wiki/work/concepts/Dir.md").mkdir(parents=True)
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/Dir.md", concept("work", "Dir"))
    decide(run, rec("wiki/work/concepts/Dir.md"))
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "rejected"
    assert any("not a file path" in p["reason"] for p in report["problems"])


def test_apply_oserror_holds_entry_back_and_journal_commits(run, monkeypatch):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real = publish._rename

    def failing(src, dst):
        if dst.endswith("B.md"):
            raise OSError("simulated EIO")
        real(src, dst)

    monkeypatch.setattr(publish, "_rename", failing)
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "conflict"
    assert report["published"] == ["wiki/work/concepts/A.md"]
    assert report["conflicts"] == ["wiki/work/concepts/B.md"]
    assert (run / "wiki/work/concepts/A.md").is_file()
    assert not (run / "wiki/work/concepts/B.md").exists()
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/B.md").is_file()
    journal = (run / "system/logs/runs" / RID / "publish.journal").read_text().splitlines()
    assert json.loads(journal[-1]) == {"committed": True}


def test_recover_isolates_a_run_whose_apply_raises(run, monkeypatch):
    bad = "20261001T110000-ingest-0002"
    publish.snapshot(run, bad, ["wiki/work/**"])
    write(run, f"wiki/.staging/{bad}/wiki/work/concepts/T.md", concept("work", "T"))
    write(run, f"system/logs/runs/{bad}/publish.journal",
          json.dumps({"staged": f"wiki/.staging/{bad}/wiki/work/concepts/T.md",
                      "target": "wiki/work/concepts/T.md", "expected": None}) + "\n")
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    decide(run, rec("wiki/work/concepts/A.md"))
    real_rename, real_apply = publish._rename, publish._apply

    def crash(src, dst):
        raise KeyboardInterrupt("simulated crash")

    monkeypatch.setattr(publish, "_rename", crash)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish, "_rename", real_rename)

    def apply(vault, journal):
        if journal.parent.name == bad:
            raise RuntimeError("boom")
        return real_apply(vault, journal)

    monkeypatch.setattr(publish, "_apply", apply)
    result = publish.recover(run)
    assert result["failed"] == [bad] and result["recovered"] == [RID]
    assert (run / "wiki/work/concepts/A.md").is_file()
    report = json.loads((run / "system/logs/runs" / bad / "publish.json").read_text())
    assert report["status"] == "recovery_failed" and "boom" in report["problems"][0]["reason"]
    assert (run / "system/quarantine" / bad / "staged/wiki/work/concepts/T.md").is_file()


def test_recover_lets_keyboard_interrupt_propagate(run, monkeypatch):
    write(run, f"system/logs/runs/{RID}/publish.journal",
          json.dumps({"staged": "wiki/.staging/x", "target": "wiki/work/concepts/T.md", "expected": None}) + "\n")

    def apply(vault, journal):
        raise KeyboardInterrupt("stop")

    monkeypatch.setattr(publish, "_apply", apply)
    with pytest.raises(KeyboardInterrupt):
        publish.recover(run)


def test_recover_staging_loop_is_guarded_per_dir(run, monkeypatch):
    other = "20261001T110000-ingest-0003"
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{other}/wiki/work/concepts/B.md", concept("work", "B"))
    real = publish._quarantine

    def quarantine(vault, run_id):
        if run_id == RID:
            raise OSError("simulated EIO")
        return real(vault, run_id)

    monkeypatch.setattr(publish, "_quarantine", quarantine)
    result = publish.recover(run)
    assert RID in result["failed"] and result["aborted"] == [other]
    assert (run / "system/quarantine" / other / "staged/wiki/work/concepts/B.md").is_file()
