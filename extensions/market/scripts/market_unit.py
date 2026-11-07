#!/usr/bin/env python3
"""The foundry-market unit (market watch spec §3.6): the fetch, then the rating run when there are new candidates,
then the after-publish step. Exit 0 ok or nothing new, 1 the rating did not publish, 70 a crash (alerted)."""
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(VAULT / "system" / "scripts"), str(Path(__file__).resolve().parent)]
from marketlib import unit  # noqa: E402
from vaultlib.api import guard  # noqa: E402

if sys.argv[1:]:
    print("usage: market_unit.py", file=sys.stderr)
    sys.exit(2)
sys.exit(guard(lambda: unit.main(VAULT, date.today()), VAULT, "foundry-market", "market_source"))
