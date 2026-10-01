#!/usr/bin/env python3
"""Redact secrets from stdin to stdout; print the count to stderr (spec §6.18)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.redact import redact  # noqa: E402

text, count = redact(sys.stdin.read())
sys.stdout.write(text)
print(f"redactions: {count}", file=sys.stderr)
