#!/usr/bin/env python3
"""Fetch error groups from Sentry and ADX into raw/telemetry/ (Plan 11). Exit 0 ok, 1 a source failed, 2 usage, 4 busy,
70 a crash (alerted)."""
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(VAULT / "system" / "scripts"), str(Path(__file__).resolve().parent)]
from telemetrylib import telemetry_run  # noqa: E402
from vaultlib import alerts  # noqa: E402

# Only the unit's own call (no arguments) alerts: the smoke check's --check and --sources report their own failure.
sys.exit(alerts.guard(lambda: telemetry_run.main(sys.argv[1:], VAULT), VAULT, "foundry-telemetry", "telemetry",
                     alerting=not sys.argv[1:]))
