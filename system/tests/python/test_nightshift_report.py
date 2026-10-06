from pathlib import Path

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
    assert text.startswith("# Nightshift: 2026-10-07\n> Health: claude ok · gh ok · sandbox ok · usage 5h 12% / 7d 48% · last tick 05:00")
    assert "## Needs you\n- [ ] Review and merge: https://github.com/o/r/pull/7 (2026-10-06-a)" in text
    assert "| 2026-10-06-b | research | failed (no result) |" in text
    assert "2026-10-05-c" not in text


def test_quiet_night_and_health_failure(vault: Path):
    assert nr.build(vault, "2026-10-08") == "# Nightshift: 2026-10-08\n> Health: not checked\n\nNothing ran.\n"
    nr.write_health(vault, "2026-10-09", {"claude": "ok", "sandbox": "FAILED: curl reached example.com"})
    assert "sandbox FAILED" in nr.build(vault, "2026-10-09").splitlines()[1]
