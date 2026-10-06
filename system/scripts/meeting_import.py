#!/usr/bin/env python3
"""Import fetched Gemini Docs and dropped transcripts as meeting notes, once (meetings spec §2.3).

The intake daemon runs the same import on every tick; this entry point is for a manual run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.intake import Intake  # noqa: E402

intake = Intake(Path(__file__).resolve().parents[2])
try:
    with intake.lock("intake.lock", timeout=0):  # never beside a running intake tick
        intake.import_meetings()
except TimeoutError:
    print("meeting_import: intake is running; nothing done (it imports on its own tick)", file=sys.stderr)
