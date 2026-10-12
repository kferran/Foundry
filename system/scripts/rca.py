#!/usr/bin/env python3
"""RCA-to-Jira helpers for rca_file.sh and the intake tick (RCA spec §3.3).

Usage: rca.py pending                          print "<file|reject> <partition> <stem>" per approved or dropped draft
       rca.py args <partition> <stem>          print the createJiraIssue arguments as JSON
       rca.py extract <partition> <stem>       check a filer session's stream on stdin; print the new issue key
       rca.py called                           exit 0 when the stream on stdin called the create tool, 1 when not
       rca.py filed <partition> <stem> <key>   write the key back to the note and its Now line, under run.lock
Exit: 0 ok, 1 claude error or no key, 2 usage or incomplete settings or draft, 3 no connector, 4 run.lock busy,
6 connector error, 7 unexpected tool use or other arguments. A non-zero exit writes one reason line to stderr.
"""
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import rca  # noqa: E402
from vaultlib.cli import UsageError  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402
from vaultlib.stream import messages  # noqa: E402


def target(partition: str, stem: str) -> tuple:
    if partition not in ("work", "personal") or not rca.STEM.match(stem) or not rca.note_path(VAULT, partition, stem).is_file():
        raise rca.Fail(2, f"no RCA note wiki/{partition}/rca/{stem}.md")
    return partition, stem


def main(argv) -> int:
    try:
        if argv[1:] == ["pending"]:
            print("".join(f"{a} {p} {s}\n" for a, p, s in rca.pending(VAULT)), end="")
        elif len(argv) == 4 and argv[1] == "args":
            print(json.dumps(rca.arguments(VAULT, *target(argv[2], argv[3]))))
        elif len(argv) == 4 and argv[1] == "extract":
            args = rca.arguments(VAULT, *target(argv[2], argv[3]))
            print(rca.extract(messages(sys.stdin.read()), args))
        elif argv[1:] == ["called"]:
            return 0 if rca.called(messages(sys.stdin.read())) else 1
        elif len(argv) == 5 and argv[1] == "filed" and rca.KEY.match(argv[4]):
            intake = Intake(VAULT)
            with intake.lock("run.lock", timeout=120):
                rca.filed(VAULT, *target(argv[2], argv[3]), argv[4], intake.today())
        else:
            raise rca.Fail(2, "usage: rca.py pending | args <p> <stem> | extract <p> <stem> | filed <p> <stem> <key>")
    except rca.Fail as f:
        print(f"rca: {f.reason}", file=sys.stderr)
        return f.code
    except UsageError as e:
        print(f"rca: {e}", file=sys.stderr)
        return 2
    except TimeoutError:
        print("rca: run.lock busy; nothing written", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
