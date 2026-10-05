#!/usr/bin/env python3
"""Intake daemon (spec §6.4)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.intake import Intake  # noqa: E402

parser = argparse.ArgumentParser(prog="intake_daemon.sh")
group = parser.add_mutually_exclusive_group()
group.add_argument("--retry", metavar="RUN_ID")
group.add_argument("--retry-all", action="store_true")
args = parser.parse_args()
intake = Intake(Path(__file__).resolve().parents[2])
if args.retry or args.retry_all:
    for restored in intake.retry(args.retry):
        print(restored)
else:
    intake.run()
