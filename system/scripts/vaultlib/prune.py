"""Once a day the intake tick deletes what has aged 30 days and is settled (#436 S7). The caller holds run.lock.
Poisoned inputs, quarantined meetings and backfills, and a run folder a recovery or commit still needs all stay."""
import json
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

import commit_runs   # system/scripts is on sys.path wherever vaultlib is
from . import publish, quarantine

DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BRIEFING = re.compile(r"^briefings/(\d{4}-\d{2}-\d{2})\.md$")


def _settled(rd: Path, since: str) -> bool:
    """Recovery has nothing to roll forward, and commit_runs.py has nothing to commit (its `pending`)."""
    journal, report_file = rd / "publish.journal", rd / "publish.json"
    try:
        if journal.exists() and not publish._committed(journal):
            return False
        # a kind commit_runs.py never commits (digest-backfill), or no publish.json: the run ended before publish
        if ((rd / "committed").exists() or rd.name[:15] < since or not commit_runs.committable(rd.name)
                or not report_file.exists()):
            return True
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):   # a torn journal or report stays for recovery or a hand fix
        return False
    return isinstance(report, dict) and not [p for p in report.get("published") or [] if isinstance(p, str)]


def _entries(vault: Path, cutoff: date) -> int:
    """Drop extracted_blocks.jsonl entries of a briefing dated before the cutoff that is archived and gone."""
    path = vault / "system" / "logs" / "extracted_blocks.jsonl"
    if not path.is_file():
        return 0
    keep, dropped = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rel = json.loads(line).get("briefing")
        except (ValueError, AttributeError):
            rel = None
        m = BRIEFING.match(rel) if isinstance(rel, str) else None
        if (m and m.group(1) < cutoff.isoformat() and not (vault / rel).exists()
                and (vault / "briefings" / "archive" / m.group(1)[:7] / f"{m.group(1)}.md").is_file()):
            dropped += 1
        else:
            keep.append(line + "\n")
    if dropped:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("".join(keep), encoding="utf-8")
        os.replace(tmp, path)
    return dropped


def prune(vault, cutoff: date) -> dict:
    vault = Path(vault)
    logs = vault / "system" / "logs"
    done = {"runs": 0, "inputs": 0, "quarantine": 0, "entries": 0, "unsettled": 0, "oldest": ""}
    since_file = logs / "commit_runs.since"   # absent until commit_runs.py first runs
    since = since_file.read_text(encoding="utf-8").strip() if since_file.is_file() else ""
    runs = logs / "runs"
    for rd in sorted(runs.iterdir()) if runs.is_dir() else []:
        old = publish.RUN_ID.match(rd.name) and rd.name[:8] < f"{cutoff:%Y%m%d}"
        if not old or rd.is_symlink() or not rd.is_dir():
            continue
        if _settled(rd, since):
            shutil.rmtree(rd)
            done["runs"] += 1
        else:
            done["unsettled"] += 1
            done["oldest"] = done["oldest"] or rd.name
    inputs = logs / "inputs"
    for d in sorted(inputs.iterdir()) if inputs.is_dir() else []:
        if d.is_dir() and not d.is_symlink() and DAY.match(d.name) and d.name < cutoff.isoformat():
            shutil.rmtree(d)
            done["inputs"] += 1
    for row in quarantine.items(vault, cutoff + timedelta(days=30)):
        name = Path(row.path).name
        kept = (runs / name).exists()   # an unsettled run keeps its held-back staging
        if row.kind == "run" and not publish.RUN_ID.match(name):
            continue   # a folder someone else put here is not a run's staging
        if row.kind in quarantine.SAFE and row.days >= 30 and not kept:
            item = vault / row.path
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
            done["quarantine"] += 1
    done["entries"] = _entries(vault, cutoff)
    return done
