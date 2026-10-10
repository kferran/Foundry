import fcntl
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from helpers import REPO, write
from vaultlib.intake import Intake

TZ = ZoneInfo("America/Denver")  # the iv fixture's configured timezone


def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def ledger_month():
    return datetime.now(TZ).strftime("%Y-%m")

STUB = """#!/usr/bin/env python3
import json, os, sys, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
TZ = ZoneInfo("America/Denver")
vault = Path(__file__).resolve().parents[2]
args = sys.argv[1:]
calls = vault / "calls.jsonl"
staged = {a: (vault / a).read_text(errors="replace") for a in args[1:] if (vault / a).is_file()}
rc_queue = vault / "rc_queue.json"
rcs = json.loads(rc_queue.read_text()) if rc_queue.exists() else []
rc = rcs.pop(0) if rcs else int(os.environ.get("STUB_RC", "0"))
rc_queue.write_text(json.dumps(rcs))
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
with open(calls, "a") as fh:
    fh.write(json.dumps({"args": args, "staged": staged}) + "\\n")
ledger = vault / "system/logs" / f"runs-{datetime.now(TZ).strftime('%Y-%m')}.jsonl"
ledger.parent.mkdir(parents=True, exist_ok=True)
with open(ledger, "a") as fh:
    fh.write(json.dumps({"run_id": f"stub-{time.time_ns()}", "command": "ingest",
                         "started_at": datetime.now(TZ).isoformat(), "inputs": args[1:],
                         "input_sha256": os.environ.get("FOUNDRY_ORIGINAL_SHA256", "").split(), "exit": rc}) + "\\n")
sys.exit(rc)
"""


@pytest.fixture
def iv(vault):
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    stub = vault / "system/scripts/run_headless.sh"
    stub.write_text(STUB)
    stub.chmod(0o755)
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\n'
          'debrief_time: "17:00"\nremote_mode: "none"\ndefault_partition: "personal"\n---\n')
    for d in ("raw/inbox", "raw/archive", "raw/telemetry"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    return vault


def calls(vault):
    path = vault / "calls.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def later():
    return time.time() + 3600


def test_inbox_file_ingested_and_archived(iv):
    write(iv, "raw/inbox/note.md", "plain note\n")
    Intake(iv, now=later()).run()
    assert calls(iv)[0]["args"] == ["ingest", "raw/inbox/.staging/note.md"]
    assert (iv / "raw/archive/note.md").read_text() == "plain note\n"
    assert not (iv / "raw/inbox/note.md").exists() and not (iv / "raw/inbox/.staging/note.md").exists()
    manifest = (iv / "system/logs" / f"intake_manifest-{datetime.now(TZ).year}.jsonl").read_text()
    assert '"name": "note.md"' in manifest


def test_fresh_and_temp_files_skipped(iv):
    write(iv, "raw/inbox/fresh.md", "x")
    for name in (".hidden.md", "a.md~", "b.tmp", "c.swp", "d.sync-conflict-1.md", ".~lock.e#", "f.crdownload", "g.part"):
        write(iv, f"raw/inbox/{name}", "x")
    Intake(iv).run()
    assert calls(iv) == []
    Intake(iv, now=later()).run()
    assert [c["args"][1] for c in calls(iv)] == ["raw/inbox/.staging/fresh.md"]


def test_unicode_name_sanitized(iv):
    write(iv, "raw/inbox/Meeting – café notes.md", "x")
    Intake(iv, now=later()).run()
    staged = calls(iv)[0]["args"][1]
    assert staged.startswith("raw/inbox/.staging/Meeting") and staged.endswith("notes.md")
    assert all(ch.isascii() for ch in staged)


def test_duplicate_is_archived_without_ingest(iv):
    write(iv, "raw/inbox/a.md", "same")
    Intake(iv, now=later()).run()
    write(iv, "raw/inbox/b.md", "same")
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert any(p.name.startswith("b-dup-") for p in (iv / "raw/archive").iterdir())


def test_production_error_routed_to_telemetry(iv):
    write(iv, "raw/inbox/err.md", '---\ntype: production_error\nservice: "x"\nexception: "E"\n'
          'operation_id: "1"\ndetected_at: "2026-10-01T00:00:00Z"\n---\nboom\n')
    Intake(iv, now=later()).run()
    assert calls(iv) == [] and (iv / "raw/telemetry/err.md").is_file()


def test_archive_collision_renamed_before_ingest(iv):
    write(iv, "raw/archive/n.md", "older")
    write(iv, "raw/inbox/n.md", "newer")
    Intake(iv, now=later()).run()
    staged = calls(iv)[0]["args"][1]
    assert staged.startswith("raw/inbox/.staging/n-") and staged.endswith(".md")
    assert (iv / "raw/archive/n.md").read_text() == "older"


def test_redacted_copy_ingested_original_archived(iv):
    write(iv, "raw/inbox/s.md", "password=hunter2\n")
    Intake(iv, now=later()).run()
    assert "hunter2" not in calls(iv)[0]["staged"]["raw/inbox/.staging/s.md"]
    assert (iv / "raw/archive/s.md").read_text() == "password=hunter2\n"


def test_daily_cap_leaves_inputs_and_stops(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "4")
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert (iv / "raw/inbox/a.md").exists() and (iv / "raw/inbox/b.md").exists()


def test_failures_poison_after_three_attempts(iv, monkeypatch):
    write(iv, "raw/inbox/bad.md", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(2):
        Intake(iv, now=later()).run()
        assert (iv / "raw/inbox/bad.md").exists()
    Intake(iv, now=later()).run()
    assert (iv / "system/quarantine/poisoned/bad.md").is_file()
    origin = json.loads((iv / "system/quarantine/poisoned/bad.md.origin.json").read_text())
    assert origin["origin"] == "raw/inbox/bad.md"
    assert "poisoned" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_max_runs(iv, monkeypatch):
    for i in range(4):
        write(iv, f"raw/inbox/{i}.md", str(i))
    Intake(iv, now=later(), max_runs=2).run()
    assert len(calls(iv)) == 2


def test_malformed_ledger_line_ignored(iv, monkeypatch):
    write(iv, f"system/logs/runs-{ledger_month()}.jsonl", '{"run_id": "x", "exit"\n')
    write(iv, "raw/inbox/a.md", "a")
    Intake(iv, now=later()).run()
    assert (iv / "raw/archive/a.md").exists()


def test_concurrent_daemons_do_not_double_ingest(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    monkeypatch.setenv("STUB_SLEEP", "1")
    threads = [threading.Thread(target=lambda: Intake(iv, now=later()).run()) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls(iv)) == 1


def briefing(iv, text):
    path = write(iv, f"briefings/{today()}.md", text)
    old = time.time() - 600
    os.utime(path, (old, old))
    return path


def drops(iv):
    return sorted((iv / "raw/inbox").glob("daily_note_drop_*.md"))


def blocks_log(iv):
    path = iv / "system/logs/extracted_blocks.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def test_each_new_block_becomes_one_drop_and_the_briefing_is_unchanged(iv):
    text = "top\n#wiki-ingest-start\nidea one\n#wiki-ingest-end\nmid\n#wiki-ingest-start\n  idea two  \n#wiki-ingest-end\nbottom\n"
    path = briefing(iv, text)
    before = path.read_bytes()
    Intake(iv, now=later()).extract_briefing()
    assert path.read_bytes() == before
    assert sorted(d.read_text() for d in drops(iv)) == ["  idea two  \n", "idea one\n"]
    records = blocks_log(iv)
    assert [r["kind"] for r in records] == ["block", "block"]
    assert {r["briefing"] for r in records} == {f"briefings/{today()}.md"}
    assert {r["drop"] for r in records} == {d.relative_to(iv).as_posix() for d in drops(iv)}


def test_a_known_block_is_not_extracted_again(iv):
    briefing(iv, "#wiki-ingest-start\nidea\n#wiki-ingest-end\n")
    Intake(iv, now=later()).extract_briefing()
    Intake(iv, now=later()).extract_briefing()
    assert len(drops(iv)) == 1
    assert len(blocks_log(iv)) == 1


def test_an_edited_block_is_extracted_again(iv):
    path = briefing(iv, "#wiki-ingest-start\nidea\n#wiki-ingest-end\n")
    Intake(iv, now=later()).extract_briefing()
    path.write_text("#wiki-ingest-start\nidea, refined\n#wiki-ingest-end\n")
    old = time.time() - 600
    os.utime(path, (old, old))
    Intake(iv, now=later()).extract_briefing()
    assert sorted(d.read_text() for d in drops(iv)) == ["idea\n", "idea, refined\n"]


def test_the_same_text_in_a_later_briefing_is_a_new_block(iv):
    import hashlib
    h = hashlib.sha256(b"idea").hexdigest()
    write(iv, "system/logs/extracted_blocks.jsonl", json.dumps(
        {"kind": "block", "briefing": "briefings/2026-01-01.md", "hash": h, "drop": "raw/inbox/x.md", "time": "t"}) + "\n")
    briefing(iv, "#wiki-ingest-start\nidea\n#wiki-ingest-end\n")
    Intake(iv, now=later()).extract_briefing()
    assert [d.read_text() for d in drops(iv)] == ["idea\n"]


def test_complete_blocks_before_a_bad_marker_are_extracted_and_it_is_alerted_once_a_day(iv):
    text = "#wiki-ingest-start\ndone\n#wiki-ingest-end\n#wiki-ingest-start\nhalf typed\n"
    path = briefing(iv, text)
    Intake(iv, now=later()).extract_briefing()
    Intake(iv, now=later()).extract_briefing()
    assert path.read_text() == text
    assert [d.read_text() for d in drops(iv)] == ["done\n"]
    alerts = next((iv / "system/logs").glob("alerts_*.md")).read_text()
    assert alerts.count("unterminated") == 1
    assert [r["kind"] for r in blocks_log(iv)] == ["block", "alert"]


def test_a_nested_start_marker_is_alerted_once_a_day(iv):
    briefing(iv, "#wiki-ingest-start\na\n#wiki-ingest-start\nb\n#wiki-ingest-end\n")
    Intake(iv, now=later()).extract_briefing()
    Intake(iv, now=later()).extract_briefing()
    assert drops(iv) == []
    assert next((iv / "system/logs").glob("alerts_*.md")).read_text().count("nested") == 1


def test_an_empty_block_makes_no_drop(iv):
    briefing(iv, "#wiki-ingest-start\n   \n#wiki-ingest-end\n")
    Intake(iv, now=later()).extract_briefing()
    assert drops(iv) == []


def test_unterminated_marker_leaves_briefing(iv):
    text = "top\n#wiki-ingest-start\nidea\n## Evening\nimportant\n"
    path = briefing(iv, text)
    Intake(iv, now=later()).extract_briefing()
    assert path.read_text() == text
    assert not list((iv / "raw/inbox").glob("daily_note_drop_*.md"))
    assert "unterminated" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_fresh_briefing_skipped_and_never_created(iv):
    path = write(iv, f"briefings/{today()}.md", "#wiki-ingest-start\nx\n#wiki-ingest-end\n")
    Intake(iv).extract_briefing()
    assert "#wiki-ingest-start" in path.read_text()
    path.unlink()
    Intake(iv, now=later()).run()
    assert not path.exists()


def test_cli_entry(iv):
    write(iv, "raw/inbox/a.md", "a")
    res = subprocess.run([str(iv / "system/scripts/intake_daemon.sh")], capture_output=True, text=True,
                         env={**os.environ, "INTAKE_NOW_OFFSET": "3600"})
    assert res.returncode == 0, res.stderr
    assert (iv / "raw/archive/a.md").exists()


# -- controller rulings X1-X4 -------------------------------------------------
def ledger_line(vault, **rec):
    path = vault / "system/logs" / f"runs-{ledger_month()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def test_settings_and_busy_exits_do_not_poison(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    monkeypatch.setenv("STUB_RC", "3")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert (iv / "raw/inbox/a.md").exists()
    assert not (iv / "system/quarantine/poisoned").exists()


def test_failures_since_retry_ignores_nonfault_exits(iv):
    import hashlib
    sha = hashlib.sha256(b"a").hexdigest()
    for rc in (3, 4, 6, None, "x", 0):
        ledger_line(iv, command="ingest", input_sha256=[sha], exit=rc)
    assert Intake(iv).failures_since_retry(sha) == 0
    ledger_line(iv, command="ingest", input_sha256=[sha], exit=5)
    ledger_line(iv, command="ingest", input_sha256=[sha], exit=124)
    assert Intake(iv).failures_since_retry(sha) == 2
    ledger_line(iv, command="retry", input_sha256=[sha], exit=0)
    assert Intake(iv).failures_since_retry(sha) == 0


def test_invalid_input_exit_poisons_immediately(iv, monkeypatch):
    write(iv, "raw/inbox/bad.md", "bad")
    monkeypatch.setenv("STUB_RC", "2")
    Intake(iv, now=later()).run()
    assert (iv / "system/quarantine/poisoned/bad.md").is_file()
    assert (iv / "system/quarantine/poisoned/bad.md.origin.json").is_file()
    assert "rejected as invalid input" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_invalid_settings_stops_the_run(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "3")
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert (iv / "raw/inbox/a.md").exists() and (iv / "raw/inbox/b.md").exists()


def test_manifest_append_survives_torn_line(iv):
    write(iv, f"system/logs/intake_manifest-{datetime.now(TZ).year}.jsonl", '{"sha256": "abc", "na')
    write(iv, "raw/inbox/a.md", "a")
    Intake(iv, now=later()).run()
    import hashlib
    last = (iv / "system/logs" / f"intake_manifest-{datetime.now(TZ).year}.jsonl").read_text().splitlines()[-1]
    assert json.loads(last)["sha256"] == hashlib.sha256(b"a").hexdigest()


# -- fix round 1 ---------------------------------------------------------------
def test_briefing_edit_during_lock_wait_survives(iv):
    import fcntl
    text = "top\n#wiki-ingest-start\nidea\n#wiki-ingest-end\nbottom\n"
    path = briefing(iv, text)
    holder = open(iv / "system/run.lock", "a")
    fcntl.flock(holder, fcntl.LOCK_EX)
    t = threading.Thread(target=lambda: Intake(iv, now=later()).extract_briefing())
    t.start()
    time.sleep(0.5)
    edited = text + "USER EDIT WHILE WAITING\n"
    path.write_text(edited)
    fcntl.flock(holder, fcntl.LOCK_UN)
    holder.close()
    t.join()
    # the read happens under the lock, so it sees the edit; the briefing is never rewritten
    assert path.read_text() == edited
    drops = list((iv / "raw/inbox").glob("daily_note_drop_*.md"))
    assert len(drops) == 1 and drops[0].read_text() == "idea\n"


def test_non_utf8_inbox_file_is_redacted(iv):
    (iv / "raw/inbox/s.md").write_bytes(b"caf\xe9\npassword=hunter2\n")
    Intake(iv, now=later()).run()
    assert "hunter2" not in calls(iv)[0]["staged"]["raw/inbox/.staging/s.md"]
    assert (iv / "raw/archive/s.md").read_bytes() == b"caf\xe9\npassword=hunter2\n"


def test_non_utf8_briefing_does_not_stop_inbox(iv):
    p = iv / f"briefings/{today()}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"caf\xe9\n#wiki-ingest-start\nx\n#wiki-ingest-end\n")
    old = time.time() - 600
    os.utime(p, (old, old))
    write(iv, "raw/inbox/a.md", "a")
    Intake(iv, now=later()).run()
    assert (iv / "raw/archive/a.md").exists()
    assert "briefing" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_unreadable_inbox_file_does_not_stop_intake(iv):
    a = write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    a.chmod(0)
    try:
        Intake(iv, now=later()).run()
    finally:
        a.chmod(0o644)
    assert (iv / "raw/archive/b.md").exists()
    assert (iv / "raw/inbox/a.md").exists()
    assert "a.md" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_signal_exits_are_not_input_failures(iv, monkeypatch):
    import hashlib
    sha = hashlib.sha256(b"a").hexdigest()
    for rc in (143, 143, 143, 129, 130):
        ledger_line(iv, command="ingest", input_sha256=[sha], exit=rc)
    assert Intake(iv).failures_since_retry(sha) == 0
    write(iv, "raw/inbox/a.md", "a")
    monkeypatch.setenv("STUB_RC", "143")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert (iv / "raw/inbox/a.md").exists()
    assert not (iv / "system/quarantine/poisoned").exists()


def test_archive_rename_failure_does_not_double_ingest(iv, monkeypatch):
    import pathlib
    write(iv, "raw/inbox/a.md", "a")
    real, failed = pathlib.Path.rename, []

    def flaky(self, target):
        if not failed and pathlib.Path(target).parent == iv / "raw/archive":
            failed.append(target)
            raise OSError("simulated EIO on archive")
        return real(self, target)

    monkeypatch.setattr(pathlib.Path, "rename", flaky)
    Intake(iv, now=later()).run()
    assert failed and (iv / "raw/inbox/a.md").exists()
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert not (iv / "raw/inbox/a.md").exists()
    assert any(p.name.startswith("a-dup-") for p in (iv / "raw/archive").iterdir())


def test_each_intake_tick_closes_now_lines_on_finished_work_orders(iv):
    write(iv, "raw/work/nightshift/2026-10-08-x.md",
          '---\ntype: "nightshift_item"\nid: "2026-10-08-x"\npartition: "work"\nkind: "plan"\nstate: "done"\n---\n')
    write(iv, "wiki/work/Now.md", '---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-08"\npartition: work\n---\n'
          "# Now\n\n## Needs you\n\n## Waiting\n- [ ] waiting: X runs (since 2026-10-08, 2026-10-08-x)\n")
    Intake(iv, now=later()).run()
    assert f"_(closed: Work Order done {today()})_" in (iv / "wiki/work/Now.md").read_text()


def test_a_busy_run_lock_skips_the_now_check(iv):
    write(iv, "wiki/work/Now.md", '---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-08"\npartition: work\n---\n'
          "# Now\n\n## Needs you\n- [x] owed: A (since 2026-10-08)\n\n## Waiting\n")
    with open(iv / "system/run.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        Intake(iv, now=later()).check_now()
    assert "_(closed:" not in (iv / "wiki/work/Now.md").read_text()



# -- the Notes block goes out once, early the next morning (#61) --------------
NOTES_BRIEF = ("# Briefing\n### 1. Objectives\n#wiki-ingest-start\nright away\n#wiki-ingest-end\n"
               "## 📝 Notes\n<!-- yours -->\n#wiki-ingest-start\n{notes}\n#wiki-ingest-end\n## 🌌 Evening\n")


def dated(iv, day, text):
    path = write(iv, f"briefings/{day}.md", text)
    old = time.time() - 600
    os.utime(path, (old, old))
    return path


def yesterday():
    from datetime import timedelta
    return (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def at(iv, hour):
    """An Intake whose wall clock reads today at <hour>:30 in the vault's timezone."""
    intake = Intake(iv, now=later())
    fixed = datetime.now(TZ).replace(hour=hour, minute=30)
    intake.dt = lambda: fixed
    return intake


def test_todays_notes_block_waits_while_other_blocks_go_now(iv):
    briefing(iv, NOTES_BRIEF.format(notes="draft one"))
    at(iv, 10).extract_briefing()
    briefing(iv, NOTES_BRIEF.format(notes="draft two"))
    at(iv, 11).extract_briefing()
    assert [d.read_text() for d in drops(iv)] == ["right away\n"]


def test_the_notes_block_goes_once_from_five_and_never_before(iv):
    path = dated(iv, yesterday(), NOTES_BRIEF.format(notes="final notes"))
    at(iv, 0).extract_briefing()  # a client may still sync its last edits overnight
    assert drops(iv) == []
    at(iv, 5).extract_briefing()
    # its block outside Notes goes too: it had not gone on its day
    assert sorted(d.read_text() for d in drops(iv)) == ["final notes\n", "right away\n"]
    path.write_text(NOTES_BRIEF.format(notes="edited later"))
    old = time.time() - 600
    os.utime(path, (old, old))
    at(iv, 5).extract_briefing()
    assert len(drops(iv)) == 2
    assert [r["kind"] for r in blocks_log(iv)].count("notes") == 1


def test_an_empty_notes_block_makes_no_drop(iv):
    dated(iv, yesterday(), NOTES_BRIEF.format(notes="   ").replace("right away", " "))
    at(iv, 5).extract_briefing()
    assert drops(iv) == []


def test_an_archived_briefing_and_a_debrief_are_not_read(iv):
    day = yesterday()
    dated(iv, f"archive/{day[:7]}/{day}", NOTES_BRIEF.format(notes="archived"))
    dated(iv, f"{day}.debrief", NOTES_BRIEF.format(notes="debrief"))
    at(iv, 5).extract_briefing()
    assert drops(iv) == []


def test_a_notes_block_already_sent_is_not_sent_again(iv):
    import hashlib
    day = yesterday()
    write(iv, "system/logs/extracted_blocks.jsonl", json.dumps(
        {"kind": "block", "briefing": f"briefings/{day}.md", "hash": hashlib.sha256(b"sent before").hexdigest(),
         "drop": "raw/inbox/x.md", "time": "t"}) + "\n")
    dated(iv, day, "## 📝 Notes\n#wiki-ingest-start\nsent before\n#wiki-ingest-end\n")
    at(iv, 5).extract_briefing()
    assert drops(iv) == []


def test_a_broken_notes_section_waits_and_alerts(iv):
    dated(iv, yesterday(), "## 📝 Notes\n#wiki-ingest-start\nhalf typed\n")
    at(iv, 5).extract_briefing()
    assert drops(iv) == []
    assert "unterminated" in next((iv / "system/logs").glob("alerts_*.md")).read_text()
    assert "notes" not in [r["kind"] for r in blocks_log(iv)]


def test_a_broken_marker_after_notes_does_not_hold_the_notes_back(iv):
    dated(iv, yesterday(), "## 📝 Notes\n#wiki-ingest-start\nmy notes\n#wiki-ingest-end\n## 🌌 Evening\n"
          "#wiki-ingest-start\nhalf typed\n")
    at(iv, 5).extract_briefing()
    assert [d.read_text() for d in drops(iv)] == ["my notes\n"]
    assert "notes" in [r["kind"] for r in blocks_log(iv)]
    assert "unterminated" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_a_heading_of_your_own_inside_notes_keeps_the_block_waiting(iv):
    text = "## 📝 Notes\n## Ideas\n#wiki-ingest-start\n{}\n#wiki-ingest-end\n## 🌌 Evening\n"
    briefing(iv, text.format("draft one"))
    at(iv, 10).extract_briefing()
    briefing(iv, text.format("draft two"))
    at(iv, 11).extract_briefing()
    assert drops(iv) == []
