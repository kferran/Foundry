#!/usr/bin/env python3
"""Ultra Magnus: validate and publish a headless run's staged output (spec §6.20)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.publish_cli import main  # noqa: E402

sys.exit(main())
