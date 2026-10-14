#!/usr/bin/env python3
"""Redact secrets from stdin to stdout; print the count to stderr (spec §6.18).

With --drop, stdin is a meeting transcript drop: decoded as the import does (UTF-8 with or without a byte-order
mark, or UTF-16 with one), redacted, written as UTF-8. A drop the import would quarantine exits 1 with its reason
and writes nothing (audit S6 spec §2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.redact import redact  # noqa: E402

raw_bytes = sys.stdin.buffer.read()
if sys.argv[1:] == ["--drop"]:
    from vaultlib import meetings  # here only: the digest path stays free of meetings' PyYAML import
    try:
        text, count = redact(meetings.decode(raw_bytes))
    except meetings.ParseError as e:
        print(f"redact: {e}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.buffer.write(text.encode("utf-8"))
    print(f"redactions: {count}", file=sys.stderr)
    sys.exit(0)
# Read bytes, decode with surrogateescape to preserve non-UTF-8 bytes
text = raw_bytes.decode('utf-8', errors='surrogateescape')
text, count = redact(text)
# Encode back with surrogateescape to preserve any non-UTF-8 bytes
sys.stdout.buffer.write(text.encode('utf-8', errors='surrogateescape'))
print(f"redactions: {count}", file=sys.stderr)
