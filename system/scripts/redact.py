#!/usr/bin/env python3
"""Redact secrets from stdin to stdout; print the count to stderr (spec §6.18).

With --kinds, print the named detectors that fire on stdin instead, one per line (meetings spec §2.2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.redact import named_kinds, redact  # noqa: E402

# Read bytes, decode with surrogateescape to preserve non-UTF-8 bytes
raw_bytes = sys.stdin.buffer.read()
text = raw_bytes.decode('utf-8', errors='surrogateescape')
if sys.argv[1:] == ["--kinds"]:
    print("".join(f"{kind}\n" for kind in named_kinds(text)), end="")
    sys.exit(0)
text, count = redact(text)
# Encode back with surrogateescape to preserve any non-UTF-8 bytes
sys.stdout.buffer.write(text.encode('utf-8', errors='surrogateescape'))
print(f"redactions: {count}", file=sys.stderr)
