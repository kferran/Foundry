#!/usr/bin/env python3
"""Fetch the watch list's newsrooms and feeds and the press feeds into raw/market/<date>/ (market watch spec §3.2).
Exit 0 ok, 1 a source failed, 2 usage, 70 a crash (alerted). --check reports the day's fetch from its state."""
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(VAULT / "system" / "scripts"), str(Path(__file__).resolve().parent)]
from marketlib import run  # noqa: E402
from vaultlib.api import guard  # noqa: E402

# Only the unit's own call (no arguments) alerts: the smoke check's --check reports its own failure.
sys.exit(guard(lambda: run.main(sys.argv[1:], VAULT), VAULT, "foundry-market", "market_source",
               alerting=not sys.argv[1:]))
