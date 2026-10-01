#!/usr/bin/env python3
"""The Ark: schema validation and index CLI for the Jarvis vault (spec §6.16)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.cli import main  # noqa: E402

sys.exit(main())
