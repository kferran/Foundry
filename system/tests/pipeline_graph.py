#!/usr/bin/env python3
"""Factory F6 (#477): check system/pipeline.yml against the code.

Usage: pipeline_graph.py <root> [gaps-file]
Prints one `<subject>: <problem>` line per problem, sorted, and exits 0; pipeline.bats asserts on the output, as
conformance.bats does with timing_problems. A gaps-file line is `<node> <rule> <issue>  # what is missing`; it
silences that rule for that node, and a listed gap that no longer fails prints `<node> <rule>: gap closed, delete
its line`, so the list only shrinks. Standard library and PyYAML only; it reads files and runs nothing.
"""
import ast
import fnmatch
import re
import sys
from pathlib import Path

import yaml

LOCKS = ("run", "intake", "nightshift", "meetings", "notify", "index", "stage")
# A lock file name as text: `intake.lock` followed by `(` is vaultlib's intake.lock() helper, not a lock file.
LOCK_RE = re.compile(r"(?<![\w.])(" + "|".join(LOCKS) + r")\.lock(?![\w(])")
EDGE_RE = re.compile(r"^(alert:[a-z_]+|quarantine|retry-next-tick|caller:[a-z_-]+|unavailable|ledger|none)$")
LEDGER_TRAP = "trap write_ledger EXIT"   # run_headless.sh: each exit is a ledger line; notify posts a failed one
HANDLER = {".sh": "crash_trap ", ".py": "alerts.guard("}


def known_tags(root):
    tree = ast.parse((root / "system/scripts/vaultlib/alerts.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TAGS" for t in node.targets):
            return set(ast.literal_eval(node.value))
    return set()


def unit_names(root):
    return sorted(p.name[: -len(".service.in")] for p in (root / "system/systemd").glob("foundry-*.service.in"))


def parts(path):
    return [p for p in path.rstrip("/").split("/") if p]


def covers(folder, path):
    """True when `folder` (a path ending in /) holds `path`, part by part, `*` matching one part."""
    if not folder.endswith("/"):
        return False
    f, p = parts(folder), parts(path)
    return len(f) <= len(p) and all(fnmatch.fnmatchcase(b, a) or fnmatch.fnmatchcase(a, b) for a, b in zip(f, p))


def same(a, b):
    pa, pb = parts(a), parts(b)
    return len(pa) == len(pb) and all(fnmatch.fnmatchcase(x, y) or fnmatch.fnmatchcase(y, x) for x, y in zip(pa, pb))


def meets(a, b):
    return same(a, b) or covers(a, b) or covers(b, a)


def check(root, gaps):
    """[(node or path, rule, problem line)] for every problem, before gaps are applied."""
    data = yaml.safe_load((root / "system/pipeline.yml").read_text(encoding="utf-8")) or {}
    nodes = data.get("nodes") or {}
    sources = [s["path"] for s in data.get("sources") or []]
    sinks = [s["path"] for s in data.get("sinks") or []]
    tags = known_tags(root)
    units = unit_names(root)
    out = []

    # P1: one node per unit, and no node without its unit.
    declared = {n.get("unit"): name for name, n in nodes.items()}
    for unit in units:
        if unit not in declared:
            out.append((unit, "P1", f"{unit}: no node"))
    for name, n in nodes.items():
        if n.get("unit") not in units:
            out.append((name, "P1", f"{name}: no unit {n.get('unit')}"))

    for name, n in nodes.items():
        scripts = n.get("scripts") or []
        failure = n.get("failure") or {}
        # P2: the declared locks are the lock files the node's scripts name.
        found = set()
        for s in scripts:
            p = root / s
            if p.is_file():
                found |= {m + ".lock" for m in LOCK_RE.findall(p.read_text(encoding="utf-8", errors="replace"))}
            else:
                out.append((name, "P2", f"{name}: script {s} does not exist"))
        want = set(n.get("locks") or [])
        if want != found:
            out.append((name, "P2", f"{name}: locks [{', '.join(sorted(want))}] but its scripts name "
                                    f"[{', '.join(sorted(found))}]"))
        # P3: a catch-all edge, backed by a crash handler when it is an alert; none needs a gap line.
        other = failure.get("other")
        if other is None:
            out.append((name, "P3", f"{name}: no other edge"))
        elif other == "none":
            out.append((name, "P3", f"{name}: other is none with no PIPELINE_GAPS line"))
        elif other.startswith("alert:"):
            entry = n.get("entry") or (scripts[0] if scripts else "")
            text = (root / entry).read_text(encoding="utf-8", errors="replace") if (root / entry).is_file() else ""
            if HANDLER.get(Path(entry).suffix, "\0") not in text:
                out.append((name, "P3", f"{name}: other is {other} but {entry} installs no crash handler"))
        elif other == "ledger":   # every exit is a run ledger line, which notify posts when it failed
            entry = n.get("entry") or (scripts[0] if scripts else "")
            text = (root / entry).read_text(encoding="utf-8", errors="replace") if (root / entry).is_file() else ""
            if LEDGER_TRAP not in text:
                out.append((name, "P3", f"{name}: other is ledger but {entry} writes no ledger line on exit"))
        for key, edge in failure.items():
            edge = str(edge)
            if not EDGE_RE.match(edge):
                out.append((name, "P4", f"{name}: {key} has unknown edge {edge}"))
            elif edge.startswith("alert:") and edge[6:] not in tags:
                out.append((name, "P4", f"{name}: {edge} is not a known tag"))
            elif (edge == "retry-next-tick" and n.get("unit") in units
                  and not (root / "system/systemd" / f"{n.get('unit')}.timer.in").is_file()):
                out.append((name, "P5", f"{name}: retry-next-tick on a unit with no timer"))
            elif edge.startswith("caller:") and edge[7:] not in nodes:
                out.append((name, "P4", f"{name}: {key} names no node {edge[7:]}"))

    # P6, P7: every path written has a reader or a sink; every path read has a writer or a source.
    reads = [(r, name) for name, n in nodes.items() for r in n.get("reads") or []]
    writes = [(w, name) for name, n in nodes.items() for w in n.get("writes") or []]
    for w, name in writes:
        if not any(meets(w, r) for r, _ in reads) and not any(meets(w, s) for s in sinks):
            out.append((w, "P6", f"{w}: written by {name}, read by no node and not a sink"))
    for r, name in reads:
        if not any(meets(r, w) for w, _ in writes) and not any(meets(r, s) for s in sources):
            out.append((r, "P7", f"{r}: read by {name}, written by no node and not a source"))

    # P8: the gaps list silences a node's rule and must shrink.
    lines, failing = [], {(subj, rule) for subj, rule, _ in out}
    for subj, rule, line in out:
        if (subj, rule) not in gaps:
            lines.append(line)
    for subj, rule in sorted(gaps):
        if (subj, rule) not in failing:
            lines.append(f"{subj} {rule}: gap closed, delete its line")
    return sorted(set(lines))


def read_gaps(path):
    gaps = set()
    if path:
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].split()
            if len(line) >= 2:
                gaps.add((line[0], line[1]))
    return gaps


def main(argv):
    if not argv or len(argv) > 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    for line in check(Path(argv[0]), read_gaps(argv[1] if len(argv) > 1 else None)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
