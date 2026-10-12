#!/usr/bin/env python3
"""The brief's Before today's meetings blocks (one-screen brief spec §3.6).

Usage: meeting_prep.py YYYY-MM-DD   prints people.md from system/logs/inputs/<date>/calendar.tsv: for each event
that names an entity note, the entity's open Now lines and open meeting actions. Empty without a calendar.
"""
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import meeting_prep  # noqa: E402


def main(argv):
    try:
        day = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        day = None
    if day is None:
        print("usage: meeting_prep.py YYYY-MM-DD (invalid date)", file=sys.stderr)
        return 2
    calendar = VAULT / "system" / "logs" / "inputs" / day.isoformat() / "calendar.tsv"
    sys.stdout.write(meeting_prep.render(VAULT, day.isoformat(), calendar))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
