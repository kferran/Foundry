#!/usr/bin/env python3
"""The intraday watch's helpers for watch_fetch.sh (phase D spec §3.2 to §3.7).

Usage: watch.py slack-input                       print this tick's Slack search inputs as {query name: input} JSON
       watch.py slack-tool                        print the Slack search tool's name
       watch.py mail-query [--inbound-since <epoch>]
                                                  print the mail session's queries as {query name: query} JSON ({}: off);
                                                  the epoch (last 7 days) replaces the incoming search's cursor
       watch.py hold                              print why this tick is skipped (usage ceiling), or nothing
       watch.py extract-slack <inputs JSON>       check a Slack session's stream on stdin; print the found JSON
       watch.py extract-mail <queries JSON>       check a Gmail session's stream on stdin; print the found JSON
       watch.py slot-days <found file>…           print the workdays whose calendar the free slots need, one a line
       watch.py route <start epoch> [--slack <found file> <inputs JSON>] [--mail <found file> <queries JSON>]
                      [--today <tsv file>] [--day <date> <tsv file>]…
                                                  under run.lock: the calendar diff, the cross-check, the Now lines,
                                                  the alerts, the capture file and the cursors of the sessions given
Exit: 0 ok, 1 claude error or a result in an unexpected shape, 2 usage or a bad setting, 3 no connector, 4 run.lock
busy, 6 connector error, 7 unexpected tool use or another query. A non-zero exit writes one reason line to stderr.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(VAULT / "system" / "scripts")]
from vaultlib import triage  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402
from vaultlib.stream import messages  # noqa: E402
from watchlib import calendar as cal, capture, check, common, query, route  # noqa: E402
from watchlib.common import Fail  # noqa: E402


def _found(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def do_route(intake, args: list) -> str:
    start = int(args[0])
    slack = mail = today_tsv = None
    days, i = {}, 1
    while i < len(args):
        if args[i] == "--slack":
            slack, i = (_found(args[i + 1]), json.loads(args[i + 2])), i + 3
        elif args[i] == "--mail":
            mail, i = (_found(args[i + 1]), json.loads(args[i + 2])), i + 3
        elif args[i] == "--today":
            today_tsv, i = Path(args[i + 1]).read_text(encoding="utf-8"), i + 2
        elif args[i] == "--day":
            days[args[i + 1]], i = Path(args[i + 2]).read_text(encoding="utf-8"), i + 3
        else:
            raise Fail(2, f"route: unknown argument {args[i]}")
    day, now = intake.today(), intake.dt()
    clock = now.strftime("%H:%M:%S")
    partition = common.partition(VAULT)
    found = {"items": [*(slack[0]["items"] if slack else []), *(mail[0]["items"] if mail else [])]}
    events = cal.parse_tsv(today_tsv) if today_tsv is not None else []
    fetched = [day] if today_tsv is not None else []
    for d, text in days.items():
        events += [e for e in cal.parse_tsv(text) if e["date"] == d]
        fetched.append(d)
    with intake.lock("run.lock", timeout=120):
        flags = cal.snapshot(VAULT, day, events) if today_tsv is not None else []
        crossed = cal.cross(found["items"], events, day)
        counts = route.route(VAULT, partition, found, flags, crossed, events, fetched, day, clock)
        caps = capture.keep(VAULT, route.new_captures(VAULT, day, slack[0].get("captures") or [])) if slack else []
        if caps:
            cap_partition = common.capture_partition(VAULT)
            path = capture.write(VAULT, caps, cap_partition, str(triage.config(VAULT).get("capture_channel") or ""), now)
            route.captured(VAULT, day, clock, path.relative_to(VAULT).as_posix(), caps, cap_partition)
            counts["captured"] = len(caps)
        names = list(slack[1]) if slack else []
        if slack and query.first_capture(VAULT):
            names.append("capture")
        if mail is not None:
            names += list(mail[1])
        resume = {n: e for n, e in (slack[0].get("resume") or {}).items() if n in names} if slack else {}
        hold = mail[0].get("hold") or [] if mail else []   # a page the model never read: that search's cursor stays
        query.advance(VAULT, [n for n in names if n not in resume and n not in hold], start)
        for n, epoch in resume.items():
            query.advance(VAULT, [n], epoch)
        for name in slack[0].get("full") or [] if slack else []:
            key = f"the {name} search read its full page limit:"
            rest = ("the next tick reads on from the last message read" if name in resume
                    else "the oldest messages since the last tick were not read")
            common.alert(VAULT, day, clock, "intraday", f"{key} {rest}", key=key)
        for name in mail[0].get("full") or [] if mail else []:
            key = f"the {name} search left result pages unread:"
            common.alert(VAULT, day, clock, "intraday", f"{key} the oldest threads since the last tick were not read", key=key)
        for name in hold:
            key = f"the {name} search returned a page too large for the model to read:"
            common.alert(VAULT, day, clock, "intraday", f"{key} its cursor stays, so the next tick reads it again (the "
                         "persisted count in system/logs/watch_fetch-*.jsonl)", key=key)
    return " ".join(f"{k} {v}" for k, v in counts.items())


def main(argv) -> int:
    intake = Intake(VAULT)
    args = argv[1:]
    try:
        now = int(intake.dt().timestamp())
        if args == ["slack-input"]:
            print(json.dumps(query.slack(VAULT, now), sort_keys=True))
        elif args == ["slack-tool"]:
            print(query.slack_tool(VAULT))
        elif args[:1] == ["mail-query"] and (len(args) == 1 or (len(args) == 3 and args[1] == "--inbound-since")):
            print(json.dumps(query.mail(VAULT, now, args[2] if len(args) == 3 else None)))
        elif args == ["hold"]:
            reason = triage.hold(VAULT, intake.dt())
            if reason:
                print(reason)
        elif len(args) == 2 and args[0] == "extract-slack":
            print(json.dumps(check.slack_extract(messages(sys.stdin.read()), query.slack_tool(VAULT), json.loads(args[1]),
                                                 str(triage.config(VAULT).get("slack_notify_channel") or ""))))
        elif len(args) == 2 and args[0] == "extract-mail":
            print(json.dumps(check.mail_extract(messages(sys.stdin.read()), json.loads(args[1]), query.inbound_rules(VAULT))))
        elif args[:1] == ["slot-days"] and len(args) > 1:
            items = [i for p in args[1:] for i in _found(p).get("items") or []]
            print("".join(f"{d}\n" for d in cal.slot_days(intake.today(), items)), end="")
        elif args[:1] == ["route"] and len(args) >= 2 and args[1].isdigit():
            print(do_route(intake, args[1:]))
        else:
            raise Fail(2, "usage: watch.py slack-input | slack-tool | mail-query [--inbound-since <epoch>] | hold | extract-slack <inputs> | "
                          "extract-mail <queries> | slot-days <found>… | route <start epoch> [options]")
    except Fail as f:
        print(f"watch: {f.reason}", file=sys.stderr)
        return f.code
    except TimeoutError:
        print("watch: run.lock busy; nothing written", file=sys.stderr)
        return 4
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"watch: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
