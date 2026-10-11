#!/usr/bin/env python3
"""Open meeting action items and meeting notices for the brief (meetings spec §2.5; one-screen brief spec §3.2).

Usage: meeting_actions.py YYYY-MM-DD   prints actions.md: the user's open actions (owner_names, case-folded,
whole entries) from every meeting; everyone else's from the meeting notes imported since the previous weekday
brief, grouped by owner, printed once (none on a Saturday or Sunday); and the Notices of the last 7 days from
system/logs/meetings-<YYYY-MM>.jsonl.
"""
import json
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import briefings, frontmatter  # noqa: E402
from vaultlib.index import Index  # noqa: E402
from vaultlib.meetings import open_actions, owner_names  # noqa: E402

NO_BRIEF_DAYS = 7
NOTICE_DAYS = 7
UNASSIGNED = "Unassigned"


def _config():
    try:
        return frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return {}


def _zone(config):
    try:
        return ZoneInfo(str(config.get("timezone") or "UTC"))
    except Exception:  # an unknown zone name: read times as UTC
        return ZoneInfo("UTC")


def window_start(vault, day: str) -> datetime:
    """When the previous weekday brief ran (its date at brief_time, config timezone); 7 days back at 00:00 without one."""
    config, tz = _config(), _zone(_config())
    previous = briefings.previous_weekday_briefing(vault, day)
    if previous is None:
        return datetime.combine(date.fromisoformat(day) - timedelta(days=NO_BRIEF_DAYS), time(0, 0), tz)
    try:
        hour, minute = (int(x) for x in str(config.get("brief_time") or "06:00").split(":")[:2])
    except ValueError:
        hour, minute = 6, 0
    return datetime.combine(date.fromisoformat(previous), time(hour, minute), tz)


def _records():
    for path in sorted((VAULT / "system" / "logs").glob("meetings-*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                yield r


def _when(record, tz):
    try:
        when = datetime.fromisoformat(str(record.get("time", "")))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=tz)


def imported_notes(vault, day: str) -> list:
    """(note path, meeting date) for each meeting note imported since the window start, each once, in log order;
    a note that is gone or deprecated is skipped."""
    start, tz, seen, out = window_start(vault, day), _zone(_config()), set(), []
    for r in _records():
        if r.get("kind") != "imported" or not isinstance(r.get("note"), str) or r["note"] in seen:
            continue
        when = _when(r, tz)
        if when is None or when <= start:
            continue
        seen.add(r["note"])
        try:
            note = frontmatter.parse((Path(vault) / r["note"]).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        data = note.data or {}
        if data.get("status") == "deprecated":
            continue
        out.append((r["note"], str(data.get("date") or r["note"].rsplit("/", 1)[-1][:10]), note.body))
    return out


def merge_first_names(groups: dict) -> dict:
    """A bare first name joins the one owner whose full name starts with it; two candidates leave it as written."""
    for key in list(groups):
        if " " in key or key == UNASSIGNED:
            continue
        matches = [k for k in groups if k != key and k.casefold().startswith(key.casefold() + " ")]
        if len(matches) == 1:
            groups[matches[0]].extend(groups.pop(key))
    return groups


def notices(day):
    out = []
    for r in _records():
        try:
            when = date.fromisoformat(str(r.get("time", ""))[:10])
        except ValueError:
            continue
        if not day - timedelta(days=NOTICE_DAYS) <= when <= day:
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
    mine, others, me = [], {}, owner_names(VAULT)
    for path, held in rows:
        try:
            held_on = date.fromisoformat(held)
            body = frontmatter.parse((VAULT / path).read_text(encoding="utf-8")).body
        except (TypeError, ValueError, OSError, UnicodeDecodeError):
            continue
        for owners, bracket, text in open_actions(body):
            if any(o.casefold() in me for o in owners):
                days = (day - held_on).days
                mine.append(f"- [{bracket}] {text} ([[{Path(path).stem}]], {days} day{'' if days == 1 else 's'} open)")
    if day.weekday() < 5:
        for path, held, body in imported_notes(VAULT, day.isoformat()):
            for owners, _, text in open_actions(body):
                if any(o.casefold() in me for o in owners):
                    continue
                for owner in owners or [UNASSIGNED]:
                    others.setdefault(owner, []).append(f"- {text} ([[{Path(path).stem}]], {held})")
        others = merge_first_names(others)
    waiting = [line for owner in sorted(others, key=str.casefold) for line in (f"### {owner}", *others[owner])]
    print(f"# Meeting actions for {day}\n")
    for heading, lines in (("Yours", mine), ("Waiting on", waiting), ("Notices", notices(day))):
        print(f"## {heading}\n" + "\n".join(lines or ["None."]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
