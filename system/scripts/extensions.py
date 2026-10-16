#!/usr/bin/env python3
"""What each enabled extension gives the shared scripts, as lines bash can read (extensions spec §3).

Usage: extensions.py list | check | field <name> <key> | smoke | brief | units <role> | allow [--write | --remove <name>] | ignore | link | migrate
Exit: 0; 1 from `check` when an extension cannot load; 2 usage.
"""
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import extensions  # noqa: E402

ROLES = ("standalone", "server", "client")


def usage() -> int:
    print(__doc__.strip().splitlines()[2], file=sys.stderr)
    return 2


def _truthy(value) -> bool:
    return str(value).lower() == "true"


def main(argv: list) -> int:
    if not argv:
        return usage()
    cmd, args = argv[0], argv[1:]
    out: list = []
    if cmd == "check" and not args:
        reasons = extensions.check(VAULT)
        for line in reasons:
            print(line)
        return 1 if reasons else 0
    loaded = extensions.enabled(VAULT)
    if cmd == "list" and not args:
        out = [n for n, _ in loaded]
    elif cmd == "field" and len(args) == 2:
        data = dict(loaded).get(args[0])
        if data is None or args[1] not in extensions.FIELDS:
            return usage()
        value = data.get(args[1], [] if args[1] in ("requires", "deps", "allow", "alert_tags", "index_ignore") else "")
        out = [value if isinstance(value, str) else json.dumps(value)]
    elif cmd == "smoke" and not args:
        for name, d in loaded:
            for s in d.get("smoke") or []:
                out.append("\t".join([str(s.get("source") or name), str(s.get("timeout", "")), "1" if _truthy(s.get("connector")) else "0",
                                      f"extensions/{name}/{s.get('run', '')}"]))
    elif cmd == "brief" and not args:
        out = [n for n, d in loaded if _truthy(d.get("brief"))]
    elif cmd == "units" and len(args) == 1 and args[0] in ROLES:
        for name, d in loaded:
            for u in d.get("units") or []:
                if args[0] in (u.get("roles") or []):
                    out.append(f"{name}\t{u.get('name', '')}")
    elif cmd == "allow" and args and args[0] in ("--write", "--remove"):
        if args[0] == "--write" and len(args) == 1:
            done, err = extensions.write_allow(VAULT)
        elif args[0] == "--remove" and len(args) == 2:
            done, err = extensions.remove_allow(VAULT, args[1])
        else:
            return usage()
        for rule in done:
            print(f"{'added' if args[0] == '--write' else 'removed'} {rule}")
        if err:
            print(f"extensions: {err}", file=sys.stderr)
            return 1
    elif cmd == "allow" and not args:
        out = [r for _, d in loaded for r in extensions._strs(d.get("allow"))]
    elif cmd == "link" and not args:
        out = extensions.link(VAULT)
    elif cmd == "ignore" and not args:
        out = extensions.ignore(VAULT)
    elif cmd == "migrate" and not args:
        out = [f"enabled {n}" for n in extensions.migrate(VAULT)]
    else:
        return usage()
    for line in out:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
