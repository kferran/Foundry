#!/usr/bin/env python3
"""The Now page (Now page spec §3.2). Exit 0 ok, 2 usage or an invalid line, 4 run.lock busy.

  now.py add --partition <work|personal> --kind <owed|waiting|draft> --statement "<text>" [--who <name>]
             [--evidence <PR URL, Work Order id or key>]
  now.py list [--partition <p>]   the open lines; without --partition, both pages under "## <partition>"
  now.py check                    close lines on checked evidence, stamp hand ticks, prune (the intake timer runs it)
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
sub.add_parser("list").add_argument("--partition")
sub.add_parser("check")
sub.add_parser("seed").add_argument("date")
args = p.parse_args()

intake = Intake(VAULT)
if args.cmd == "list":
    for part in [args.partition] if args.partition else now.PARTITIONS:
        lines = now.open_lines(now.read(VAULT, part))
        if lines:
            print("\n".join(lines if args.partition else [f"## {part}", *lines]))
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
            status, line = now.add(VAULT, args.partition, args.kind, args.statement, intake.today(),
                                   args.who, args.evidence)
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
