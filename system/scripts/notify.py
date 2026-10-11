#!/usr/bin/env python3
"""Slack notice helpers for notify.sh (Slack notices spec §3.1).

Usage: notify.py collect              print {"message", "lines", "cursor"} for what happened since the last notice,
                                      or nothing; the first run only sets the cursor
       notify.py tool                 print the send tool's name for the configured connector
       notify.py check <collected>    check a session's stream on stdin against collect's JSON file; prints the
                                      drift when the post reached the channel but not exactly
       notify.py commit <collected>   move the cursor to the one in collect's JSON file
Exit: 0 ok (or posted with drift), 1 claude error, 2 usage, 3 no connector, 4 the account usage limit, 6 connector
error, 7 the session broke its rules (another tool, channel or argument, or text nobody collected).
A non-zero exit writes one reason line to stderr.
"""
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import notify  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402
from vaultlib.stream import messages  # noqa: E402

DEFAULT_CONNECTOR = "plugin:slack:slack"


def tool() -> str:
    return notify.prefix(str(notify.config(VAULT).get("slack_connector") or DEFAULT_CONNECTOR)) + "__slack_send_message"


def main(argv) -> int:
    try:
        if argv[1:] == ["collect"]:
            events, cursor = notify.collect(VAULT, Intake(VAULT).dt().replace(tzinfo=None))
            if not events:
                notify.commit(VAULT, cursor)  # nothing to send: the cursor moves past what was skipped
                return 0
            text, lines = notify.message(VAULT, events)
            print(json.dumps({"message": text, "lines": lines, "cursor": cursor}))
        elif argv[1:] == ["tool"]:
            print(tool())
        elif len(argv) == 3 and argv[1] == "check":
            collected = json.loads(Path(argv[2]).read_text())
            channel = str(notify.config(VAULT).get("slack_notify_channel") or "")
            drift = notify.check(messages(sys.stdin.read()), tool(), channel, collected["message"], collected["lines"])
            if drift:
                print(drift)
        elif len(argv) == 3 and argv[1] == "commit":
            notify.commit(VAULT, json.loads(Path(argv[2]).read_text())["cursor"])
        else:
            raise notify.Fail(2, "usage: notify.py collect | tool | check <collected> | commit <collected>")
    except notify.Fail as f:
        print(f"notify: {f.reason}", file=sys.stderr)
        return f.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
