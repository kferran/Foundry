#!/usr/bin/env python3
"""The extension timing budgets (factory F3 §3.4) for conformance.bats, from <root>'s extensions/*/extension.md.

Usage: timing_manifests.py <root>. Prints one line per fact: `V <key> <seconds>`, `S <unit> <count> <grace> <key>`,
`O <unit>` (a unit the manifest's budget.out takes out of the sum) and `P <problem>`. A name in an extension's
budget.values becomes `<ext>.<NAME>`, its `tick` unit `tick/<ext>`.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "system" / "scripts"))
from vaultlib import extensions  # noqa: E402

NAME = re.compile(r"[A-Z][A-Z0-9_]*")


def defaults(root: Path, ext: str, name: str) -> list:
    """[(file, value)] for each `${NAME:-N}` or `NAME = N` line start in the extension's scripts tree."""
    n = re.escape(name)
    pat = re.compile(rf"\$\{{{n}:-([0-9]+)\}}|^\s*{n} = ([0-9]+)\b", re.M)
    return [(p.relative_to(root).as_posix(), a or b)
            for p in sorted((root / "extensions" / ext / "scripts").rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
            for a, b in pat.findall(p.read_text(encoding="utf-8", errors="ignore"))]


def lines(root: Path, ext: str) -> list:
    data, why = extensions.manifest(root, ext)
    if why:
        return [f"P {why}"]
    out = []

    def value(key, v, what):  # a V line, or a P line when v is not a whole number (bash arithmetic reads only those)
        out.append(f"V {key} {v}" if str(v).isdigit() else f"P {ext}: {what} is {v!r}, not a whole number of seconds")
        return str(v).isdigit()

    budget = data.get("budget") or {}
    values = {}
    for k, v in (budget.get("values") or {}).items():
        if not NAME.fullmatch(str(k)):   # core keys are lower-case, so an extension value never shadows one
            out.append(f"P {ext}: budget value name {k!r} is not [A-Z][A-Z0-9_]*")
        elif value(f"{ext}.{k}", v, f"budget value {k}"):
            values[k] = v
    for k, v in values.items():
        found = defaults(root, ext, k)
        if len(found) != 1:
            out.append(f"P {ext}: budget value {k}: {len(found)} defaults in scripts/")
        elif found[0][1] != v:
            out.append(f"P {ext}: budget value {k} is {v}; {found[0][0]} says {found[0][1]}")
    for step in budget.get("steps") or []:
        t = step.split()
        if len(t) != 4:
            out.append(f"P {ext}: budget step {step!r} is not four tokens")
            continue
        unit = f"tick/{ext}" if t[0] == "tick" else t[0]
        out.append(" ".join(["S", unit, *(f"{ext}.{x}" if x in values else x for x in t[1:])]))
    if data.get("tick"):   # core runs a tick with no timeout at 600 s (vaultlib/intake.py)
        value(f"tick.{ext}", data["tick"].get("timeout", "600"), "tick timeout")
        out.append(f"S intake 1 - tick.{ext}")
    for row in data.get("smoke") or []:
        value(f"row.{row['source']}", row.get("timeout"), f"smoke row {row['source']} timeout")
        out.append(f"S smoke {2 if row.get('each') else 1} - row.{row['source']}")
    if budget.get("out"):
        out += [f"O {u['name'].removeprefix('foundry-')}" for u in data.get("units") or []]
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve()
    for p in sorted(root.glob("extensions/*/extension.md")):
        print("\n".join(lines(root, p.parent.name)))
