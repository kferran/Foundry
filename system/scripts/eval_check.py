#!/usr/bin/env python3
"""Score ingest eval runs (ingest evals spec §3.3). Read-only; no model is called.

Usage: eval_check.py check <vault> <expect.yaml> <overlay dir> [<run id>…]   one line per failed check; exit 1 if any
       eval_check.py rate <expect.yaml>                                    print the case's min_pass_rate (default 1.0)
       eval_check.py cost <vault> [<run id>…]                              print the summed total_cost_usd
       eval_check.py summary <records.jsonl>                              one line per case; exit 1 when one fails
Exit 2 on usage or an expect.yaml that does not load as a mapping.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib import evals, yamlload  # noqa: E402


def expect(path: str) -> dict:
    try:
        data = yamlload.load(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the case's fault, reported by name
        raise SystemExit(f"eval_check: {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"eval_check: {path}: not a mapping")
    return data


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "check" and len(argv) >= 5:
        lines = evals.check(argv[2], argv[5:], expect(argv[3]), argv[4])
        print("\n".join(lines), end="\n" if lines else "")
        return 1 if lines else 0
    if cmd == "rate" and len(argv) == 3:
        print(float(expect(argv[2]).get("min_pass_rate", 1.0)))
        return 0
    if cmd == "cost" and len(argv) >= 3:
        print(evals.cost(Path(argv[2]), argv[3:]))
        return 0
    if cmd == "summary" and len(argv) == 3:
        records = [json.loads(line) for line in Path(argv[2]).read_text(encoding="utf-8").splitlines() if line.strip()]
        lines, ok = evals.summary(records)
        print("\n".join(lines))
        return 0 if ok else 1
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            sys.exit(2)
        raise
