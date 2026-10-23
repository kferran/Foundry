#!/usr/bin/env python3
"""@@description@@: the call's input, and the check of a @@name@@_fetch.sh session's stream.

Usage: @@name@@_check.py args               print the call's input as JSON (the fetch puts it in the prompt)
       @@name@@_check.py extract < stream   check the session; print the brief's lines
The session may call only @@tool@@, once, with exactly ARGS. ARGS and lines() are the feature's code.
Exit: 0 ok, 1 claude error, 2 usage, 3 no connector, 6 connector error or a result too large for the model,
7 unexpected tool use or a call with other arguments. A non-zero exit writes one reason line to stderr.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "system" / "scripts"))   # extensions/@@name@@/scripts/
from vaultlib.api import Fail, check_stream, messages  # noqa: E402

TOOL = "@@tool@@"
SERVER = "@@server@@"
ARGS = {}   # TODO(feature): the call's input


def accept(i):
    """The call's name for the one input built for this run; None (the walker's exit 7) for any other."""
    return "call" if i == ARGS else None


def lines(pages) -> list:
    """The brief's lines from the call's structuredContent pages. TODO(feature): the parse, written test first. Until
    then no lines, so no unparsed outside text reaches the brief."""
    return []


def extract(stream) -> list:
    """The brief's lines, after the shared checks. Without `persisted`, a result too large for the model fails 6."""
    return lines(check_stream(stream, TOOL, accept, max_pages=1, server=SERVER)[0].get("call", []))


def main(argv):
    try:
        if argv[1:] == ["args"]:
            print(json.dumps(ARGS))
        elif argv[1:] == ["extract"]:
            print("".join(f"{t}\n" for t in extract(messages(sys.stdin.read()))), end="")
        else:
            raise Fail(2, "usage: @@name@@_check.py args | extract")
    except Fail as f:
        print(f"@@name@@_check: {f.reason}", file=sys.stderr)
        return f.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
