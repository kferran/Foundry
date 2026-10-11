#!/usr/bin/env python3
"""The brief's Friction lines (one-screen brief spec §3.3).

Usage: friction_notes.py YYYY-MM-DD   prints friction.md: one `- [[Name]]` line per active friction note that no
earlier briefing has listed, newest first, then `N open friction notes`.
"""
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import friction  # noqa: E402


def main(argv):
    try:
        day = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        day = None
    if day is None:
        print("usage: friction_notes.py YYYY-MM-DD (invalid date)", file=sys.stderr)
        return 2
    sys.stdout.write(friction.render(VAULT, day.isoformat()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
