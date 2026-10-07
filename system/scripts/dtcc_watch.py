#!/usr/bin/env python3
# system/scripts/dtcc_watch.py
"""Watch DTCC I&RS for changes (DTCC watcher spec). Exit 0 ok or no map, 1 a source failed or was held, 2 usage or invalid map, 4 locked."""
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import dtcc_run  # noqa: E402

sys.exit(dtcc_run.main(sys.argv[1:], VAULT))
