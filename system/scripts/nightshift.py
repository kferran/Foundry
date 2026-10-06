#!/usr/bin/env python3
# system/scripts/nightshift.py
"""The Nightshift runner (Nightshift spec). Exit 0 ok or nothing due, 1 an item failed, 2 usage or invalid item, 4 locked."""
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import nightshift_run  # noqa: E402

sys.exit(nightshift_run.main(sys.argv[1:], VAULT))
