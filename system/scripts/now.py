#!/usr/bin/env python3
"""The Now page (Now page spec §3.2). Exit 0 ok, 2 usage or an invalid line, 4 run.lock busy.

  now.py add --partition <work|personal> --kind <owed|waiting|draft> --statement "<text>" [--who <name>]
             [--evidence <PR URL, Work Order id or key>] [--rec "<option>: <why>"] [--due YYYY-MM-DD]
                                  a new line gets [due::] (--due, else since + 3 days with --who or a date in the
                                  statement, else + 30); a repeat add may move it earlier (exit 2 if later), set
                                  --rec, or set missing evidence, and writes nothing when nothing is new
  now.py list [--partition <p>]   the open lines; without --partition, both pages under "## <partition>"
  now.py check                    close lines on checked evidence, stamp hand ticks, prune (the intake timer runs it)
  now.py review --partition <p> [--stale-days N]
                                  read-only: lines closed by their evidence, open more than N days (14) with no
                                  evidence, or duplicated; nothing printed when there is nothing to review
  now.py seed YYYY-MM-DD          once: a missing default-partition page takes the previous brief's open objectives
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import now  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402
from vaultlib.recall import default_partition  # noqa: E402

p = argparse.ArgumentParser(prog="now.py")
sub = p.add_subparsers(dest="cmd", required=True)
a = sub.add_parser("add")
a.add_argument("--partition", required=True)
a.add_argument("--kind", required=True)
a.add_argument("--statement", required=True)
a.add_argument("--who", default="")
a.add_argument("--evidence", default="")
a.add_argument("--rec", default="")
a.add_argument("--due", default="")
sub.add_parser("list").add_argument("--partition", choices=now.PARTITIONS)
sub.add_parser("check")
r = sub.add_parser("review")
r.add_argument("--partition", required=True, choices=now.PARTITIONS)
r.add_argument("--stale-days", type=int, default=now.STALE_DAYS)
sub.add_parser("seed").add_argument("date")
args = p.parse_args()

intake = Intake(VAULT)
if args.cmd == "list":
    for part in [args.partition] if args.partition else now.PARTITIONS:
        lines = now.open_lines(now.read(VAULT, part))
        if lines:
            print("\n".join(lines if args.partition else [f"## {part}", *lines]))
    sys.exit(0)
if args.cmd == "review":  # read-only, so no run.lock
    found = now.review(VAULT, args.partition, intake.today(), args.stale_days,
                       on_fail=lambda line, reason: print(f"now.py review: pull requests not checked ({reason})",
                                                          file=sys.stderr))
    for heading, key in (("## Closed by evidence", "closed"),
                         (f"## Stale: open more than {args.stale_days} days with no evidence", "stale"),
                         ("## Duplicates", "duplicate")):
        if found[key]:
            print("\n".join([heading, *found[key]]))
    sys.exit(0)
if args.cmd == "seed":
    try:
        date.fromisoformat(args.date)
    except ValueError:
        print("usage: now.py seed YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)
try:
    with intake.lock("run.lock", timeout=float(os.environ.get("NOW_LOCK_WAIT", "60"))):
        if args.cmd == "add":
            # The one-time seed keys on the default page existing: a session must not create it first.
            if args.partition == default_partition(VAULT):
                now.seed(VAULT, args.partition, intake.today())
            status, line = now.add(VAULT, args.partition, args.kind, args.statement, intake.today(),
                                   args.who, args.evidence, args.rec, args.due)
            print(f"{status}: {line}")
        elif args.cmd == "check":
            print(f"closed: {now.check(VAULT, intake.today(), intake.alert)}")
        else:
            print(f"seeded: {now.seed(VAULT, default_partition(VAULT), args.date)}")
except ValueError as exc:
    print(f"now.py: {exc}", file=sys.stderr)
    sys.exit(2)
except TimeoutError:
    print("now.py: run.lock busy (a headless run or a sync holds it); nothing written. Retry in a few minutes.",
          file=sys.stderr)
    sys.exit(4)
