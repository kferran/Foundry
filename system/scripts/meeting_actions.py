#!/usr/bin/env python3
"""Open meeting action items and meeting notices for the brief (meetings spec §2.5).

Usage: meeting_actions.py YYYY-MM-DD   prints actions.md: the user's open actions (owner_names, case-folded,
whole entries) from every meeting, everyone else's from meetings in the last 14 days grouped by owner, and
the Notices of the last 7 days from system/logs/meetings-<YYYY-MM>.jsonl.
"""
import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import frontmatter  # noqa: E402
from vaultlib.index import Index  # noqa: E402

OPEN = re.compile(r"^- \[ \] (?:\[([^\]]+)\] )?(.+)$")
OTHERS_DAYS = 14
NOTICE_DAYS = 7


def owner_names():
    try:
        data = frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return set()
    names = data.get("owner_names")
    return {n.strip().casefold() for n in names if isinstance(n, str)} if isinstance(names, list) else set()


def open_actions(path):
    """(owners, text) for each unticked line under ## Action items."""
    try:
        body = frontmatter.parse((VAULT / path).read_text(encoding="utf-8")).body
    except (OSError, UnicodeDecodeError):
        return []
    out, on = [], False
    for line in body.split("\n"):
        if line.startswith("## "):
            on = line.strip() == "## Action items"
            continue
        match = OPEN.match(line.strip()) if on else None
        if match:
            owners = [o.strip() for o in (match.group(1) or "").split(",") if o.strip()]
            out.append((owners, match.group(1), match.group(2).strip()))
    return out


def notices(day):
    out = []
    for path in sorted((VAULT / "system" / "logs").glob("meetings-*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
                when = date.fromisoformat(str(r.get("time", ""))[:10]) if isinstance(r, dict) else None
            except ValueError:
                continue
            if when is None or not day - timedelta(days=NOTICE_DAYS) <= when <= day:
                continue
            if r.get("kind") == "imported" and r.get("complete") is False:
                out.append(f"- {r.get('note')} was imported from a transcript cut short (complete: false).")
            elif r.get("kind") == "quarantined":
                out.append(f"- Quarantined meeting source {r.get('file')}: {r.get('reason')}. "
                           "It is in system/quarantine/meetings/.")
            elif r.get("kind") == "duplicate":
                out.append(f"- {r.get('source')} was archived: the same meeting is already {r.get('note')}.")
    return out


def main(argv):
    try:
        day = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        day = None
    if day is None:
        print("usage: meeting_actions.py YYYY-MM-DD (invalid date)", file=sys.stderr)
        return 2
    idx = Index(VAULT)
    idx.refresh(timeout=60)
    conn = sqlite3.connect(idx.db_path)
    try:
        rows = conn.execute("SELECT path, date FROM v_meeting ORDER BY date, path").fetchall()
    finally:
        conn.close()
    mine, others, me = [], {}, owner_names()
    for path, held in rows:
        try:
            held_on = date.fromisoformat(held)
        except (TypeError, ValueError):
            continue
        link = f"[[{Path(path).stem}]]"
        for owners, bracket, text in open_actions(path):
            if any(o.casefold() in me for o in owners):
                days = (day - held_on).days
                mine.append(f"- [{bracket}] {text} ({link}, {days} day{'' if days == 1 else 's'} open)")
            elif day - timedelta(days=OTHERS_DAYS) <= held_on <= day:
                for owner in owners or ["Unassigned"]:
                    others.setdefault(owner, []).append(f"- {text} ({link}, {held})")
    waiting = [line for owner in sorted(others, key=str.casefold) for line in (f"### {owner}", *others[owner])]
    print(f"# Meeting actions for {day}\n")
    for heading, lines in (("Yours", mine), ("Waiting on", waiting), ("Notices", notices(day))):
        print(f"## {heading}\n" + "\n".join(lines or ["None."]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
