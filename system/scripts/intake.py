#!/usr/bin/env python3
"""Intake daemon (spec §6.4). --retry-input <name> restores one poisoned input by its file name in
system/quarantine/poisoned/ (exit 2 when none matches); --quarantine prints one line per held thing (quarantine-in-brief
spec §2)."""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib import quarantine  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402

parser = argparse.ArgumentParser(prog="intake_daemon.sh")
group = parser.add_mutually_exclusive_group()
group.add_argument("--retry", metavar="RUN_ID")
group.add_argument("--retry-all", action="store_true")
group.add_argument("--retry-input", metavar="NAME")
group.add_argument("--quarantine", action="store_true")
parser.add_argument("--date", type=date.fromisoformat, help="with --quarantine: count the days to this date")
args = parser.parse_args()
vault = Path(__file__).resolve().parents[2]
intake = Intake(vault)
if args.quarantine:
    print(quarantine.render(quarantine.items(vault, args.date or intake.dt().date())), end="")
elif args.retry_input:
    restored = intake.retry(name=args.retry_input)
    if not restored:
        print(f"intake: no poisoned input named {args.retry_input} with an origin to restore", file=sys.stderr)
        sys.exit(2)
    print("\n".join(restored))
elif args.retry or args.retry_all:
    for restored in intake.retry(args.retry):
        print(restored)
else:
    intake.run()
