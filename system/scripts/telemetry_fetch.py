#!/usr/bin/env python3
"""Fetch error groups from Sentry and ADX into raw/telemetry/ (Plan 11). Exit 0 ok, 1 a source failed, 2 usage, 4 busy."""
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import telemetry_run  # noqa: E402

sys.exit(telemetry_run.main(sys.argv[1:], VAULT))
