"""Which briefings came before a day (one-screen brief spec §3.2, §3.3).

A briefing lives at briefings/<date>.md while it is today's or yesterday's, then at
briefings/archive/<YYYY-MM>/<date>.md. The live file wins over an archive copy of the same date.
"""
import re
from datetime import date, timedelta
from pathlib import Path

LOOKBACK_DAYS = 30
ITEM_CHARS = 160   # one brief item (phase A spec §3.1)
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def cut(text: str, limit: int = ITEM_CHARS) -> str:
    """text, or its first `limit` characters cut back to a word boundary (mid-word for one long word) plus "…"."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    space = head.rfind(" ")
    return (head[:space] if space > 0 else head).rstrip() + "…"


def _paths(root: Path, day: str) -> tuple:
    return root / f"{day}.md", root / "archive" / day[:7] / f"{day}.md"


def earlier_briefings(vault, day: str, lookback=LOOKBACK_DAYS) -> list:
    """(date, path) for each briefing dated before day, newest first: within lookback days, or every dated
    briefing file under briefings/ and briefings/archive/ when lookback is None."""
    root = Path(vault) / "briefings"
    found = {}
    if lookback is None:
        for path in list(root.glob("*.md")) + list(root.glob("archive/*/*.md")):
            match = DATED.match(path.name)
            if match and match.group(1) < day:
                live = path.parent == root
                if match.group(1) not in found or live:
                    found[match.group(1)] = path
    else:
        start = date.fromisoformat(day)
        for back in range(1, lookback + 1):
            earlier = (start - timedelta(days=back)).isoformat()
            for path in _paths(root, earlier):
                if path.is_file():
                    found[earlier] = path
                    break
    return [(d, found[d]) for d in sorted(found, reverse=True)]


def previous_weekday_briefing(vault, day: str):
    """The newest earlier briefing's date that falls on a Monday to Friday, or None."""
    for earlier, _ in earlier_briefings(vault, day):
        if date.fromisoformat(earlier).weekday() < 5:
            return earlier
    return None
