#!/usr/bin/env python3
"""Inbox triage helpers for triage_fetch.sh (inbox triage spec §3.1).

Usage: triage.py query                 print this tick's Gmail query
       triage.py hold                  print why this tick is skipped (usage ceiling), or nothing
       triage.py extract <query>       check a session's stream on stdin; print {"items": [...], "full": bool}
       triage.py record <start epoch>  read extract's JSON on stdin; add the new Now lines under run.lock and print them
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
    try:
        if argv[1:] == ["query"]:
            print(triage.query(VAULT, int(time.time()), intake.today()))
        elif argv[1:] == ["hold"]:
            reason = triage.hold(VAULT, intake.dt())
            if reason:
                print(reason)
        elif len(argv) == 3 and argv[1] == "extract":
            print(json.dumps(triage.extract(messages(sys.stdin.read()), argv[2])))
        elif len(argv) == 3 and argv[1] == "record" and argv[2].isdigit():
            # argv[2] is the epoch the tick started at, before its search: the next tick searches from there.
            found = json.loads(sys.stdin.read())
            partition = triage.partition(VAULT)
            with intake.lock("run.lock", timeout=120):
                added = triage.record(VAULT, partition, found, intake.today(), intake.dt().isoformat(timespec="seconds"),
                                      int(argv[2]))
            print("".join(f"{a}\n" for a in added), end="")
        else:
            raise triage.Fail(2, "usage: triage.py query | hold | extract <query> | record <start epoch>")
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
