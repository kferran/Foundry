#!/usr/bin/env python3
"""The market page's brief line and after-publish step (market watch spec §3.5).
Usage: market_page.py line <YYYY-MM-DD> | after <YYYY-MM-DD>. Exit 0, 2 usage."""
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(VAULT / "system" / "scripts"), str(Path(__file__).resolve().parent)]
from marketlib import page  # noqa: E402

args = sys.argv[1:]
if len(args) != 2 or args[0] not in ("line", "after") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[1]):
    print(__doc__.strip().splitlines()[1], file=sys.stderr)
    sys.exit(2)
if args[0] == "line":
    print(page.line(VAULT, args[1]))
else:
    page.after_publish(VAULT, args[1])
