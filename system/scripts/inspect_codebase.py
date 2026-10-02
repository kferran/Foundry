#!/usr/bin/env python3
"""Print stack evidence for one codebase as a JSON object (spec §6.13)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.codebase_inspect import NotARepo, inspect_repo  # noqa: E402

if len(sys.argv) != 2:
    print("usage: inspect_codebase.sh <path>", file=sys.stderr)
    sys.exit(2)
try:
    print(json.dumps(inspect_repo(Path(sys.argv[1]).resolve())))
except NotARepo:
    print(f"inspect_codebase: not a git work tree: {sys.argv[1]}", file=sys.stderr)
    sys.exit(2)
