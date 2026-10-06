#!/usr/bin/env python3
"""Print the open objectives of the latest briefing before <date>, each with the date it was first raised.

Usage: carry_forward.py YYYY-MM-DD. Reads briefings/<earlier date>.md (never a debrief), section
"### 1." up to "### 2.", lines starting "- [ ] ". "[x]" is done and "[-]" is dropped; neither carries.
That briefing already carried the older items, so one file is enough. Exit 0, or 2 on a bad date.
"""
import re
import sys
from datetime import date, timedelta
from pathlib import Path

LOOKBACK_DAYS = 30
SINCE = re.compile(r"\s*_\(open since (\d{4}-\d{2}-\d{2})\)_\s*$")


def open_items(text: str):
    section = re.search(r"(?ms)^### 1\..*?(?=^### 2\.|\Z)", text)
    return [line for line in (section.group(0) if section else "").splitlines() if line.startswith("- [ ] ")]


def main(argv) -> int:
    try:
        today = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        today = None
    if today is None:
        print("usage: carry_forward.py YYYY-MM-DD", file=sys.stderr)
        return 2
    for back in range(1, LOOKBACK_DAYS + 1):
        day = (today - timedelta(days=back)).isoformat()
        path = Path("briefings") / f"{day}.md"
        if not path.is_file():
            continue
        for line in open_items(path.read_text(encoding="utf-8")):
            m = SINCE.search(line)
            print(f"{SINCE.sub('', line)} _(open since {m.group(1) if m else day})_")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
