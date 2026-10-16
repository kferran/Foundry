#!/usr/bin/env python3
# extensions/dtcc/scripts/dtcc_watch.py
"""Watch DTCC I&RS for changes (DTCC watcher spec). Exit 0 ok or no map, 1 a source failed or was held, 2 usage or invalid map, 4 locked."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(VAULT / "system" / "scripts")]
from dtcclib import dtcc_run  # noqa: E402

sys.exit(dtcc_run.main(sys.argv[1:], VAULT))
