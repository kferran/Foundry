#!/usr/bin/env python3
"""Inbox triage helpers for triage_fetch.sh (inbox triage spec §3.1; chat triage spec §3.2).

Usage: triage.py query [--source chat]                 print this tick's Gmail query, or the Slack search input as JSON
       triage.py chat-tool                             print the Slack search tool's name
       triage.py hold                                  print why this tick is skipped (usage ceiling), or nothing
       triage.py extract [--source chat] <query>       check a session's stream on stdin; print {"items": [...], "full": bool,
                                                       "hold": bool, "stats": {counts for the log line}}
       triage.py record [--source chat] <start epoch>  read extract's JSON on stdin; add the new Now lines under run.lock
                                                       and print them (a held tick keeps the cursor)
Exit: 0 ok, 1 claude error or a result in an unexpected shape, 2 usage, 3 no connector, 4 run.lock busy,
6 connector error, 7 unexpected tool use or another query. A non-zero exit writes one reason line to stderr.
"""
import json
import sys
import time
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import triage  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402
from vaultlib.stream import messages  # noqa: E402


def main(argv) -> int:
    intake = Intake(VAULT)
    args = argv[1:]
    chat = args[1:3] == ["--source", "chat"]
    if chat:
        del args[1:3]
    try:
        if args == ["query"]:
            now = int(time.time())
            print(json.dumps(triage.chat_query(VAULT, now, intake.today()), sort_keys=True) if chat
                  else triage.query(VAULT, now, intake.today()))
        elif args == ["chat-tool"] and not chat:
            print(triage.chat_tool(VAULT))
        elif args == ["hold"] and not chat:
            reason = triage.hold(VAULT, intake.dt())
            if reason:
                print(reason)
        elif len(args) == 2 and args[0] == "extract":
            stream = messages(sys.stdin.read())
            found = (triage.chat_extract(stream, json.loads(args[1]), triage.chat_tool(VAULT),
                                         str(triage.config(VAULT).get("slack_notify_channel") or ""))
                     if chat else triage.extract(stream, args[1]))
            print(json.dumps(found))
        elif len(args) == 2 and args[0] == "record" and args[1].isdigit():
            # args[1] is the epoch the tick started at, before its search: the next tick searches from there.
            found = json.loads(sys.stdin.read())
            partition = triage.partition(VAULT)
            with intake.lock("run.lock", timeout=120):
                added = triage.record(VAULT, partition, found, intake.today(), intake.dt().isoformat(timespec="seconds"),
                                      int(args[1]), "chat" if chat else "mail")
            print("".join(f"{a}\n" for a in added), end="")
        else:
            raise triage.Fail(2, "usage: triage.py query | chat-tool | hold | extract <query> | record <start epoch>"
                                 " (query, extract and record take --source chat after the command)")
    except triage.Fail as f:
        print(f"triage: {f.reason}", file=sys.stderr)
        return f.code
    except TimeoutError:
        print("triage: run.lock busy; nothing written", file=sys.stderr)
        return 4
    except (ValueError, KeyError, TypeError) as exc:
        print(f"triage: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
