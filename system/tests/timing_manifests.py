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
    budget = data.get("budget") or {}
    values = budget.get("values") or {}
    out = [f"V {ext}.{k} {v}" for k, v in values.items()]
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
    if data.get("tick"):
        out += [f"V tick.{ext} {data['tick'].get('timeout')}", f"S intake 1 - tick.{ext}"]
    for row in data.get("smoke") or []:
        out += [f"V row.{row['source']} {row['timeout']}", f"S smoke {2 if row.get('each') else 1} - row.{row['source']}"]
    if budget.get("out"):
        out += [f"O {u['name'].removeprefix('foundry-')}" for u in data.get("units") or []]
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve()
    for p in sorted(root.glob("extensions/*/extension.md")):
        print("\n".join(lines(root, p.parent.name)))
