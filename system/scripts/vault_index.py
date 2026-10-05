#!/usr/bin/env python3
"""Schema validation and index CLI for the vault (spec §6.16)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.cli import main  # noqa: E402

sys.exit(main())
