#!/usr/bin/env python3
"""Factory F6 (#477): check system/pipeline.yml against the code.

Usage: pipeline_graph.py <root> [gaps-file] [--extensions] [--mermaid]
Prints one `<subject>: <problem>` line per problem, sorted, and exits 0; pipeline.bats asserts on the output, as
conformance.bats does with timing_problems. --extensions adds every extensions/<name>/pipeline.yml in the tree and
every unit under extensions/<name>/units/ (F6 PR 2a): an extension's `nodes` are its own units, and its `extends`
adds the scripts, reads, writes and locks of its steps to a core node. --mermaid prints the graph as a Mermaid
flowchart instead of the problems. A gaps-file line is `<node> <rule> <issue>  # what is missing`; it
silences that rule for that node, and a listed gap that no longer fails prints `<node> <rule>: gap closed, delete
its line`, so the list only shrinks. Standard library and PyYAML only; it reads files and runs nothing.
"""
import ast
import fnmatch
import re
import sys
from pathlib import Path

import yaml

LOCKS = ("run", "intake", "nightshift", "meetings", "notify", "index", "stage", "telemetry")
# A lock file name as text: `intake.lock` followed by `(` is vaultlib's intake.lock() helper, not a lock file.
LOCK_RE = re.compile(r"(?<![\w.])(" + "|".join(LOCKS) + r")\.lock(?![\w(])")
EDGE_RE = re.compile(r"^(alert:[a-z_]+|quarantine|retry-next-tick|restart|caller:[a-z_-]+|unavailable|ledger|none)$")
RESTART_RE = re.compile(r"^Restart=(on-failure|always)\s*$", re.M)   # restart: systemd starts the unit again
MERGED = ("scripts", "reads", "writes", "locks")   # the fields an extension's `extends` appends to a core node
LEDGER_TRAP = "trap write_ledger EXIT"   # run_headless.sh: each exit is a ledger line; notify posts a failed one
# A crash handler per language: crash_trap (lib_fetch.sh), or alerts.guard, also as vaultlib.api's guard.
HANDLER = {".sh": re.compile(r"crash_trap "), ".py": re.compile(r"alerts\.guard\(|^from vaultlib\.api import .*\bguard\b", re.M)}


def known_tags(root, extensions):
    """vaultlib/alerts.py TAGS, plus each extension manifest's alert_tags with --extensions."""
    tags = set()
    tree = ast.parse((root / "system/scripts/vaultlib/alerts.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TAGS" for t in node.targets):
            tags = set(ast.literal_eval(node.value))
    for m in sorted((root / "extensions").glob("*/extension.md")) if extensions else []:
        head = m.read_text(encoding="utf-8").split("---")
        meta = yaml.safe_load(head[1]) if len(head) > 2 else {}
        tags |= {t["tag"] if isinstance(t, dict) else t for t in (meta or {}).get("alert_tags") or []}
    return tags


def unit_files(root, extensions):
    """{unit name: its .service.in path}: core's, plus each extension's units with --extensions."""
    found = list((root / "system/systemd").glob("foundry-*.service.in"))
    if extensions:
        found += (root / "extensions").glob("*/units/foundry-*.service.in")
    return {p.name[: -len(".service.in")]: p for p in sorted(found)}


def secs(text):
    """conformance.bats' secs(): <n>[s|m|min|h] in seconds."""
    m = re.fullmatch(r"(\d+)(s|min|m|h)?", text.strip())
    return int(m.group(1)) * {"min": 60, "m": 60, "h": 3600}.get(m.group(2), 1) if m else None


def timing_values(root):
    """{key: seconds} for each TIMING_VALUES line in conformance.bats whose ERE finds its value in its file."""
    bats = (root / "system/tests/conformance.bats")
    text = bats.read_text(encoding="utf-8") if bats.is_file() else ""
    block = re.search(r"^TIMING_VALUES='\n(.*?)^'", text, re.S | re.M)
    out = {}
    for line in (block.group(1) if block else "").splitlines():
        key, path, ere = (line.split(" ", 2) + ["", ""])[:3]
        f = root / path
        m = re.search(ere, f.read_text(encoding="utf-8", errors="replace"), re.M) if ere and f.is_file() else None
        if m and secs(m.group(1)) is not None:
            out[key] = secs(m.group(1))
    return out


def limit(unit_file):
    """A unit's TimeoutStartSec in seconds, which bounds how long it can hold a lock; no limit is infinite."""
    text = unit_file.read_text(encoding="utf-8", errors="replace") if unit_file else ""
    m = re.search(r"^TimeoutStartSec=(\S+)", text, re.M)
    return (secs(m.group(1)) if m else None) or float("inf")


def load(root, extensions):
    """(sources, sinks, nodes, problems): core's manifest, plus each extension's with --extensions."""
    data = yaml.safe_load((root / "system/pipeline.yml").read_text(encoding="utf-8")) or {}
    nodes = {k: dict(v) for k, v in (data.get("nodes") or {}).items()}
    sources = [s["path"] for s in data.get("sources") or []]
    sinks = [s["path"] for s in data.get("sinks") or []]
    out = []
    for f in sorted((root / "extensions").glob("*/pipeline.yml")) if extensions else []:
        ext = f.parent.name
        extra = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for name, n in (extra.get("nodes") or {}).items():
            if name in nodes:
                out.append((name, "P1", f"{ext}: node {name} is already declared"))
            else:
                nodes[name] = dict(n)
        for name, more in (extra.get("extends") or {}).items():
            if name not in nodes:
                out.append((ext, "P1", f"{ext}: extends no node {name}"))
                continue
            for key in MERGED:   # a lock the node already takes keeps its place in the order (P9)
                have = list(nodes[name].get(key) or [])
                nodes[name][key] = have + [x for x in (more or {}).get(key) or [] if key != "locks" or x not in have]
        sources += [s["path"] for s in extra.get("sources") or []]
        sinks += [s["path"] for s in extra.get("sinks") or []]
    return sources, sinks, nodes, out


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


def check(root, gaps, extensions=False):
    """The problem lines, sorted, after gaps are applied."""
    sources, sinks, nodes, out = load(root, extensions)
    tags = known_tags(root, extensions)
    units = unit_files(root, extensions)

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
            handler = HANDLER.get(Path(entry).suffix)
            if not (handler and handler.search(text)):
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
                  and not units[n["unit"]].with_name(f"{n['unit']}.timer.in").is_file()):
                out.append((name, "P5", f"{name}: retry-next-tick on a unit with no timer"))
            elif (edge == "restart" and n.get("unit") in units
                  and not RESTART_RE.search(units[n["unit"]].read_text(encoding="utf-8", errors="replace"))):
                out.append((name, "P5", f"{name}: restart on a unit with no Restart="))
            elif edge.startswith("caller:") and edge[7:] not in nodes:
                out.append((name, "P4", f"{name}: {key} names no node {edge[7:]}"))

    # P9: locks are listed outermost first; two nodes that take two locks in opposite orders can deadlock.
    first = {}
    for name in sorted(nodes):
        locks = list(nodes[name].get("locks") or [])
        for i, a in enumerate(locks):
            for b in locks[i + 1:]:
                first.setdefault((a, b), name)
    for (a, b), name in sorted(first.items()):
        if a < b and (b, a) in first:
            out.append((f"{a}, {b}", "P9", f"{a}, {b}: {name} takes {a} first, {first[(b, a)]} takes {b} first"))

    # P10: a lock another node also takes needs a busy edge, unless the node's wait (a TIMING_VALUES key in `waits`)
    # outlasts the other node's unit limit, which bounds its hold. flock -n waits 0 s, so it always needs one.
    values = timing_values(root)
    for name, n in sorted(nodes.items()):
        failure = n.get("failure") or {}
        if failure.get("busy") not in (None, "none"):
            continue
        waits = n.get("waits") or {}
        for lock in n.get("locks") or []:
            others = sorted(m for m, o in nodes.items() if m != name and lock in (o.get("locks") or []))
            if not others:
                continue
            hold, holder = max((limit(units.get(nodes[m].get("unit"))), m) for m in others)
            if lock not in waits:
                out.append((name, "P10", f"{name}: shares {lock} with {', '.join(others)} and has no busy edge"))
            elif waits[lock] not in values:
                out.append((name, "P10", f"{name}: waits names no TIMING_VALUES key {waits[lock]}"))
            elif values[waits[lock]] < hold:
                h = "unlimited" if hold == float("inf") else f"{int(hold)} s"
                out.append((name, "P10", f"{name}: waits {values[waits[lock]]} s for {lock}, which {holder} can "
                                         f"hold for {h}, and has no busy edge"))

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


def mermaid(root, extensions):
    """The graph as a Mermaid flowchart: each node a box, each declared path a folder between its writers and
    readers, and `outside` feeding the sources and taking the sinks. Locks are left out (spec G3). Sorted, so the
    same manifests always print the same text."""
    sources, sinks, nodes, _ = load(root, extensions)
    paths = sorted({p for n in nodes.values() for k in ("reads", "writes") for p in n.get(k) or []}
                   | set(sources) | set(sinks))
    pid = {p: f"p{i}" for i, p in enumerate(paths)}
    lines = ["flowchart LR", "  outside([outside])"]
    lines += [f"  {name}[{name}]" for name in sorted(nodes)]
    lines += [f'  {pid[p]}[("{p}")]' for p in paths]
    edges = set()
    for name, n in nodes.items():
        edges |= {f"  {name} --> {pid[p]}" for p in n.get("writes") or []}
        edges |= {f"  {pid[p]} --> {name}" for p in n.get("reads") or []}
    edges |= {f"  outside --> {pid[p]}" for p in sources} | {f"  {pid[p]} --> outside" for p in sinks}
    return lines + sorted(edges)


def main(argv):
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if not args or len(args) > 2 or flags - {"--extensions", "--mermaid"}:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    root, extensions = Path(args[0]), "--extensions" in flags
    if "--mermaid" in flags:
        print("\n".join(mermaid(root, extensions)))
        return 0
    for line in check(root, read_gaps(args[1] if len(args) > 1 else None), extensions):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
