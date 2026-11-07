"""The foundry-market unit (market watch spec §3.6; plan 3, rulings 1, 2): the fetch under its own time limit, then the
rating run when the day has candidates it has not rated, then the after-publish step. Each run's status goes to
system/logs/market_run.json for the brief's Market line."""
import os
import subprocess
from datetime import date
from pathlib import Path

from vaultlib.api import load, save

# FETCH_LIMIT bounds the fetch's whole run (and a server that drips its answer); NOTIFY_LIMIT bounds the
# after-publish step's now.py calls together, each of which may wait for run.lock. RATE_LOCK_WAIT is how long the
# rating waits for run.lock: a run that starts later than 30 - 8 - 15.5 minutes before the brief would hold the
# brief, so it ends busy instead (spec §3.6: the brief is never delayed).
FETCH_LIMIT = 300
NOTIFY_LIMIT = 120
RATE_LOCK_WAIT = 480
STATUS = {0: "ok", 124: "timeout", 6: "busy", 5: "rejected"}
FETCH = "extensions/market/scripts/market_fetch.py"
RATE = ["system/scripts/run_headless.sh", "market"]


def _count(path: Path) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


def _status(vault: Path, day: str, status: str, reason: str = "") -> None:
    save(vault / "system" / "logs" / "market_run.json", {"date": day, "status": status, "reason": reason})


def main(vault: Path, today: date, run=subprocess.run, after=None) -> int:
    day = today.isoformat()
    folder = vault / "raw" / "market" / day
    try:
        run([FETCH], cwd=vault, timeout=FETCH_LIMIT)
    except subprocess.TimeoutExpired:
        pass  # the killed fetch wrote nothing this run; rate any candidates an earlier run left unrated
    lines = _count(folder / "candidates.jsonl")
    rated_file = folder / "rated"
    rated = int(rated_file.read_text().strip() or 0) if rated_file.is_file() else 0
    if lines <= rated:
        prev = load(vault / "system" / "logs" / "market_run.json", {})
        if not (isinstance(prev, dict) and prev.get("date") == day and prev.get("status") == "ok"):
            _status(vault, day, "none")
        return 0
    _status(vault, day, "running")
    rc = run(RATE, cwd=vault, env={**os.environ, "HEADLESS_LOCK_WAIT": str(RATE_LOCK_WAIT)}).returncode
    status = STATUS.get(rc, "failed")
    _status(vault, day, status, "" if rc in STATUS else f"exit {rc}")
    if rc != 0:
        return 1
    if after is None:
        from . import page
        after = page.after_publish
    after(vault, day)  # before `rated` moves on, so a crash here is retried by the next run
    rated_file.write_text(f"{lines}\n", encoding="utf-8")
    return 0
