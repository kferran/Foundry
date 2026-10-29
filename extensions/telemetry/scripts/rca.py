#!/usr/bin/env python3
"""RCA-to-Jira helpers for rca_file.sh and the intake tick (RCA spec §3.3).

Usage: rca.py pending                          print "<file|reject> <partition> <stem>" per approved or dropped draft
       rca.py args <partition> <stem>          print the createJiraIssue arguments as JSON
       rca.py extract <args file>              check a filer session's stream on stdin against the arguments sent (the
                                               JSON in <args file>); print the new issue key
       rca.py called                           exit 0 when the stream on stdin called the create tool, 1 when not
       rca.py rejected                         print Jira's rejection and exit 0 when every create call in the stream on
                                               stdin was a client rejection (nothing created), 1 otherwise (#175)
       rca.py reopen <partition> <stem> <why>  return the note to draft and untick its Now line with the reason
       rca.py filed <partition> <stem> <key>   write the key back to the note and its Now line, under run.lock, and
                                               clear the filer's .key and .attempt markers
       rca.py tick                             the intake tick (extensions spec §3, `tick`): file the drafts you
                                               approved, at most PER_TICK, and reject the dropped ones; off while
                                               rca_project is empty
Exit: 0 ok, 1 claude error or no key, 2 usage or incomplete settings or draft, 3 no connector, 4 run.lock busy,
6 connector error, 7 unexpected tool use or other arguments. A non-zero exit writes one reason line to stderr.
"""
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(VAULT / "system" / "scripts"), str(Path(__file__).resolve().parent)]
from telemetrylib import rca  # noqa: E402
from vaultlib.api import alert, Intake, messages, now, UsageError  # noqa: E402

FILED_LOCK_WAIT = 120   # seconds `filed` and `reopen` wait for run.lock (the manifest's budget sums it per filing)


def target(partition: str, stem: str) -> tuple:
    if partition not in ("work", "personal") or not rca.STEM.match(stem) or not rca.note_path(VAULT, partition, stem).is_file():
        raise rca.Fail(2, f"no RCA note wiki/{partition}/rca/{stem}.md")
    return partition, stem


def refused(intake, exc) -> None:
    alert(VAULT, intake.today(), intake.dt().strftime("%H:%M:%S"), "rca", f"a Now line was refused ({now.refusal(exc)})",
          key="a Now line was refused")


def main(argv) -> int:
    try:
        if argv[1:] == ["tick"]:
            rca.tick(VAULT)
        elif argv[1:] == ["pending"]:
            print("".join(f"{a} {p} {s}\n" for a, p, s in rca.pending(VAULT)), end="")
        elif len(argv) == 4 and argv[1] == "args":
            print(json.dumps(rca.arguments(VAULT, *target(argv[2], argv[3]))))
        elif len(argv) == 3 and argv[1] == "extract":
            args = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
            print(rca.extract(messages(sys.stdin.read()), args))
        elif argv[1:] == ["called"]:
            return 0 if rca.called(messages(sys.stdin.read())) else 1
        elif argv[1:] == ["rejected"]:
            line = rca.rejected_create(messages(sys.stdin.read()))
            if line is None:
                return 1
            print(line)
        elif len(argv) == 5 and argv[1] == "reopen":
            intake = Intake(VAULT)
            with intake.lock("run.lock", timeout=FILED_LOCK_WAIT):
                try:
                    rca.reopen(VAULT, *target(argv[2], argv[3]), argv[4], intake.today())
                except ValueError as exc:   # the reason only, never the line (factory F5 spec §4.2)
                    refused(intake, exc)
                    raise rca.Fail(1, f"the Now check refused the reason ({exc})")
        elif len(argv) == 5 and argv[1] == "filed" and rca.KEY.match(argv[4]):
            intake = Intake(VAULT)
            with intake.lock("run.lock", timeout=FILED_LOCK_WAIT):
                try:
                    rca.filed(VAULT, *target(argv[2], argv[3]), argv[4], intake.today())
                except ValueError as exc:   # the note holds the key; only the Now line's stamp is missing
                    refused(intake, exc)
            for marker in ("key", "attempt"):  # a key written back, by rca_file.sh or by hand, ends the filing
                (VAULT / "system" / "logs" / "rca" / f"{argv[2]}-{argv[3]}.{marker}").unlink(missing_ok=True)
        else:
            raise rca.Fail(2, "usage: rca.py pending | args <p> <stem> | extract <args file> | called | rejected | "
                              "filed <p> <stem> <key> | reopen <p> <stem> <why> | tick")
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
