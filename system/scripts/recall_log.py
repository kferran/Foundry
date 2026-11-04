#!/usr/bin/env python3
"""The recall log's pull entry point (recall R0 spec §3.3): `recall_log.py pull` with the PostToolUse JSON on stdin.
Skips the CLI's scope resolution, which runs git once per codebase; the scope comes from the frozen session state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.recall_log import main  # noqa: E402

sys.exit(main())
