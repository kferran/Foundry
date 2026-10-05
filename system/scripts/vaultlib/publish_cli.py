"""CLI for publish_staged.py (spec §6.20)."""
import argparse
import json
import sys
from pathlib import Path

from . import publish, schema as schemamod

OK_STATUSES = {"published", "noop", "aborted"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="publish_staged.py", description="Publish gate: publish headless output")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot")
    p.add_argument("run_id")
    p.add_argument("--targets", nargs="+", required=True)
    p = sub.add_parser("commit")
    p.add_argument("run_id")
    p = sub.add_parser("abort")
    p.add_argument("run_id")
    sub.add_parser("recover")
    args = parser.parse_args(argv)
    vault = Path(__file__).resolve().parents[3]
    try:
        if args.command == "snapshot":
            print(json.dumps({"snapshot": str(publish.snapshot(vault, args.run_id, args.targets).relative_to(vault))}))
            return 0
        if args.command == "recover":
            print(json.dumps(publish.recover(vault)))
            return 0
        report = (publish.commit_run if args.command == "commit" else publish.abort_run)(vault, args.run_id)
        print(json.dumps(report))
        return 0 if report["status"] in OK_STATUSES else 5
    except publish.PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except schemamod.SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return 1
