#!/usr/bin/env python3
"""Redact secrets from stdin to stdout; print the count to stderr (spec §6.18)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.redact import redact  # noqa: E402

# Read bytes, decode with surrogateescape to preserve non-UTF-8 bytes
raw_bytes = sys.stdin.buffer.read()
text = raw_bytes.decode('utf-8', errors='surrogateescape')
text, count = redact(text)
# Encode back with surrogateescape to preserve any non-UTF-8 bytes
sys.stdout.buffer.write(text.encode('utf-8', errors='surrogateescape'))
print(f"redactions: {count}", file=sys.stderr)
