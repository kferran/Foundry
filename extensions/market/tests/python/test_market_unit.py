"""marketlib.unit: fetch, then rate when there is something new, with a run status (spec §3.6; plan 3, rulings 1, 2)."""
import json
import subprocess
from datetime import date

import pytest

from marketlib import unit

DAY = date(2026, 11, 6)


class Runs:
    """A fake subprocess.run: records each argv and returns the scripted exit for the fetch and the rating."""

    def __init__(self, vault, rate=0, fetch_lines=2, fetch_raises=False, on_rate=None):
        self.vault, self.rate, self.lines, self.raises, self.on_rate, self.calls = vault, rate, fetch_lines, fetch_raises, on_rate, []

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        if argv[0].endswith("market_fetch.py"):
            folder = self.vault / "raw/market" / DAY.isoformat()
            folder.mkdir(parents=True, exist_ok=True)
            with open(folder / "candidates.jsonl", "a") as fh:
                fh.write("".join('{"title": "x"}\n' for _ in range(self.lines)))
            if self.raises:
                raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
            return subprocess.CompletedProcess(argv, 0)
        if self.on_rate:
            self.on_rate()
        return subprocess.CompletedProcess(argv, self.rate)

    def rated(self):
        return [c for c in self.calls if c[-1] == "market"]


def status(vault):
    return json.loads((vault / "system/logs/market_run.json").read_text())


def rated_count(vault):
    path = vault / "raw/market" / DAY.isoformat() / "rated"
    return int(path.read_text()) if path.exists() else 0


def test_new_candidates_run_the_rating_then_after_publish(vault):
    runs, after = Runs(vault), []
    assert unit.main(vault, DAY, run=runs, after=lambda v, d: after.append(d)) == 0
    assert runs.rated() == [["system/scripts/run_headless.sh", "market"]]
    assert status(vault) == {"date": "2026-11-06", "status": "ok", "reason": ""}
    assert rated_count(vault) == 2
    assert after == ["2026-11-06"]


def test_no_unrated_candidates_runs_no_session(vault):
    unit.main(vault, DAY, run=Runs(vault), after=lambda v, d: None)
    runs = Runs(vault, fetch_lines=0)
    unit.main(vault, DAY, run=runs, after=lambda v, d: None)
    assert runs.rated() == []
    assert status(vault)["status"] == "ok"
    (vault / "system/logs/market_run.json").unlink()
    unit.main(vault, DAY, run=Runs(vault, fetch_lines=0), after=lambda v, d: None)
    assert status(vault)["status"] == "none"


@pytest.mark.parametrize("code,word,reason", [(124, "timeout", ""), (6, "busy", ""), (5, "rejected", ""),
                                              (1, "failed", "exit 1")])
def test_each_harness_exit_maps_to_a_status(vault, code, word, reason):
    after = []
    assert unit.main(vault, DAY, run=Runs(vault, rate=code), after=lambda v, d: after.append(d)) == 1
    assert status(vault) == {"date": "2026-11-06", "status": word, "reason": reason}
    assert after == [] and rated_count(vault) == 0


def test_the_status_is_running_while_the_rating_runs(vault):
    seen = []
    unit.main(vault, DAY, run=Runs(vault, on_rate=lambda: seen.append(status(vault)["status"])), after=lambda v, d: None)
    assert seen == ["running"]


def test_a_fetch_past_its_limit_still_rates_what_was_written(vault):
    runs = Runs(vault, fetch_raises=True)
    unit.main(vault, DAY, run=runs, after=lambda v, d: None)
    assert runs.rated() and runs.calls[0][-1].endswith("market_fetch.py")
    assert status(vault)["status"] == "ok"


def test_the_rating_waits_at_most_rate_lock_wait_for_run_lock(vault):
    seen = {}
    runs = Runs(vault)
    orig = runs.__call__

    def spy(argv, **kw):
        if argv[-1] == "market":
            seen["wait"] = (kw.get("env") or {}).get("HEADLESS_LOCK_WAIT")
        return orig(argv, **kw)
    unit.main(vault, DAY, run=spy, after=lambda v, d: None)
    assert seen["wait"] == str(unit.RATE_LOCK_WAIT) and unit.RATE_LOCK_WAIT == 480


def test_rated_advances_only_after_after_publish(vault):
    def boom(v, d):
        raise RuntimeError("after failed")
    with pytest.raises(RuntimeError):
        unit.main(vault, DAY, run=Runs(vault), after=boom)
    assert rated_count(vault) == 0
