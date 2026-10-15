#!/usr/bin/env python3
"""Source health for the smoke check and the brief (connector health spec §2).

Usage:
  sources.py report YYYY-MM-DD [--given FILE]   prints sources.md: one line per source, ok, off, unknown or
                                                failed: <class>: <reason> (since <date>), with the renewal of an
                                                expired credential. FILE holds the brief's own readings, one
                                                "<source><TAB><ok|off|failed><TAB><reason>" line each.
  sources.py streak SOURCE [--class CLASS]      prints "<count><TAB><since date><TAB><last reason>" of the
                                                source's trailing failed smoke readings (of that class).
  sources.py credential SOURCE REASON           prints "<credential><TAB><renewal>" when the failure needs the
                                                owner's login, else nothing.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import sources  # noqa: E402


def _given(path):
    out = {}
    if path:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0]:
                out[parts[0]] = (parts[1], parts[2] if len(parts) > 2 else "")
    return out


def main(argv):
    p = argparse.ArgumentParser(prog="sources.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("day")
    r.add_argument("--given")
    s = sub.add_parser("streak")
    s.add_argument("source")
    s.add_argument("--class", dest="cls", default="")
    c = sub.add_parser("credential")
    c.add_argument("source")
    c.add_argument("reason")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    if args.cmd == "report":
        try:
            date.fromisoformat(args.day)
        except ValueError:
            print(f"sources: invalid date: {args.day}", file=sys.stderr)
            return 2
        print("\n".join(sources.report(VAULT, args.day, _given(args.given))))
    elif args.cmd == "streak":
        print("\t".join(str(x) for x in sources.streak(VAULT, args.source, args.cls)))
    else:
        found = sources.credential(VAULT, args.source, args.reason)
        if found:
            print("\t".join(found))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
