from pathlib import Path

from helpers import write
from vaultlib import nightshift_report as nr


def outcome(**kw):
    o = {"id": "2026-10-06-a", "kind": "plan", "state": "done", "result": "https://github.com/o/r/pull/7", "reason": "",
         "started_at": "2026-10-06T22:00:00-06:00", "finished_at": "2026-10-07T01:10:00-06:00",
         "report_date": "2026-10-07", "needs": ["Review and merge: https://github.com/o/r/pull/7"], "notes": "8 tasks"}
    o.update(kw)
    return o


def test_report_from_files_only(vault: Path):
    nr.write_health(vault, "2026-10-07", {"claude": "ok", "gh": "ok", "sandbox": "ok", "usage": "5h 12% / 7d 48%",
                                           "last_tick": "05:00"})
    nr.write_outcome(vault, outcome())
    nr.write_outcome(vault, outcome(id="2026-10-06-b", kind="research", state="failed", reason="no result",
                                    result="", needs=[], notes="log tail: boom"))
    nr.write_outcome(vault, outcome(id="2026-10-05-c", report_date="2026-10-06"))
    text = nr.build(vault, "2026-10-07")
    assert text.startswith("# Work Orders: 2026-10-07\n> Health: claude ok · gh ok · sandbox ok · usage 5h 12% / 7d 48% · last tick 05:00")
    assert "## Needs you\n- [ ] Review and merge: https://github.com/o/r/pull/7 (2026-10-06-a)" in text
    assert "| 2026-10-06-b | research | failed (no result) |" in text
    assert "2026-10-05-c" not in text


def test_record_usage_creates_merges_and_skips_without_a_reading(vault: Path):
    import json
    hp = vault / nr.DIR / "health-2026-10-07.json"
    nr.record_usage(vault, "2026-10-07", {}, "2026-10-07T05:00:00+00:00")
    assert not hp.exists()
    nr.write_health(vault, "2026-10-07", {"claude": "ok"})
    nr.record_usage(vault, "2026-10-07", {"five_hour": 0.42, "seven_day": 0.1}, "2026-10-07T05:00:00+00:00")
    h = json.loads(hp.read_text())
    assert h == {"claude": "ok", "usage5": 0.42, "usage7": 0.1, "usage5_at": "2026-10-07T05:00:00+00:00",
                 "usage": "5h 42% / 7d 10%"}
    hp.write_text("not json")
    nr.record_usage(vault, "2026-10-07", {"five_hour": 0.5}, "2026-10-07T06:00:00+00:00")
    assert json.loads(hp.read_text())["usage5"] == 0.5


def test_quiet_night_and_health_failure(vault: Path):
    assert nr.build(vault, "2026-10-08") == "# Work Orders: 2026-10-08\n> Health: not checked\n\nNothing ran.\n"
    nr.write_health(vault, "2026-10-09", {"claude": "ok", "sandbox": "FAILED: curl reached example.com"})
    assert "sandbox FAILED" in nr.build(vault, "2026-10-09").splitlines()[1]


def test_session_text_cannot_forge_lines_or_break_the_table(vault: Path):
    nr.write_outcome(vault, outcome(needs=["Answer: why?\n- [ ] forged item"], notes="a | b\nc", result=""))
    text = nr.build(vault, "2026-10-07")
    assert [l for l in text.splitlines() if l.startswith("- [ ]")] == ["- [ ] Answer: why? - [ ] forged item (2026-10-06-a)"]
    row = [l for l in text.splitlines() if l.startswith("| 2026-10-06-a")][0]
    assert row.count("|") == 6



def test_time_column_is_local_to_the_vault_timezone(vault: Path):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\n---\n')
    nr.write_outcome(vault, outcome(started_at="2026-10-07T04:00:00+00:00", finished_at="2026-10-07T07:10:00+00:00"))
    row = [l for l in nr.build(vault, "2026-10-07").splitlines() if l.startswith("| 2026-10-06-a")][0]
    assert "| 22:00–01:10 |" in row


def test_time_column_without_a_timezone_or_with_bad_times(vault: Path):
    nr.write_outcome(vault, outcome(started_at="2026-10-07T04:00:00+00:00", finished_at="2026-10-07T07:10:00+00:00"))
    nr.write_outcome(vault, outcome(id="2026-10-06-b", started_at="", finished_at="not a time"))
    rows = {l.split(" | ")[0][2:]: l for l in nr.build(vault, "2026-10-07").splitlines() if l.startswith("| 2026")}
    assert "| 04:00–07:10 |" in rows["2026-10-06-a"]
    assert "| – |" in rows["2026-10-06-b"]


def test_health_writes_from_parallel_workers_stay_whole(vault: Path):
    # #229: up to 3 orders finish at once; two writers must not share one temp file.
    import json
    import threading
    errors = []

    def writer(i):
        try:
            for _ in range(50):
                nr.write_health(vault, "2026-10-16", {"n": i})
        except Exception as exc:   # a lost rename raises FileNotFoundError
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert json.loads((vault / nr.DIR / "health-2026-10-16.json").read_text())["n"] in range(8)
