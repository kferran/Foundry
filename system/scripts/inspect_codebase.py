#!/usr/bin/env python3
"""Print stack evidence for one codebase as a JSON object (spec §6.13)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.codebase_inspect import NotARepo, inspect_repo  # noqa: E402

PER_KIND = 5  # manifests shown per kind; --all-manifests lists every one
args = sys.argv[1:]
every = args[:1] == ["--all-manifests"]
if every:
    args = args[1:]
if len(args) != 1:
    print("usage: inspect_codebase.sh [--all-manifests] <path>", file=sys.stderr)
    sys.exit(2)
try:
    print(json.dumps(inspect_repo(Path(args[0]).resolve(), per_kind=None if every else PER_KIND)))
except NotARepo:
    print(f"inspect_codebase: not a git work tree: {args[0]}", file=sys.stderr)
    sys.exit(2)
