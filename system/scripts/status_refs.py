#!/usr/bin/env python3
"""Mark the GitHub pull requests, issues and Work Orders the brief's inputs name that are no longer open (#353).

  status_refs.py <prep dir> <orders.json> [owner/repo…]

Reads the prep inputs the brief copies status from, checks up to MAX references in file order (one `gh api` call
each under STATUS_TIMEOUT seconds, or the order list), and writes each non-open state right after its reference, in
place: (merged 2026-10-21 08:16), (closed 2026-10-20), (done), (failed), (cancelled) or (unverified: <why>). An open
reference stays as written. A bare #N resolves only when exactly one repository is given. Prints the Sources line's
`status: N checked, M closed, K unverified`. Exit 0, or 2 on a usage error.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FILES = ("yesterday.md", "away.md", "now.md", "overdue.md", "people.md", "actions.md", "projects.md")
MAX = 20
REF = re.compile(r"(?P<url>https://github\.com/(?P<uo>[\w.-]+)/(?P<ur>[\w.-]+)/(?:pull|issues)/(?P<un>\d+))"
                 r"|(?<![\w/.-])(?P<so>[\w.-]+)/(?P<sr>[\w.-]+)#(?P<sn>\d+)\b"
                 r"|(?<![\w/#])#(?P<bn>\d+)\b"
                 r"|\b(?P<order>\d{4}-\d{2}-\d{2}-[a-z0-9-]+)")
MARKED = re.compile(r" \((?:merged|closed|done|failed|cancelled|unverified)\b")
FINISHED = ("done", "failed", "cancelled")


def key(m: re.Match, repos: list, orders: dict):
    """(kind, identity) of a match, or None for a date-slug no order list names."""
    if m["url"]:
        return "gh", (m["uo"], m["ur"], m["un"])
    if m["sn"]:
        return "gh", (m["so"], m["sr"], m["sn"])
    if m["bn"]:
        return ("gh", (*repos[0].split("/", 1), m["bn"])) if len(repos) == 1 else ("bare", m["bn"])
    return ("order", m["order"]) if m["order"] in orders else None


def local(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()


def check(kind: str, ident, orders: dict, timeout: float) -> tuple:
    """(mark, closed?, unverified?) for one reference; mark is "" for an open one."""
    if kind == "bare":
        return " (unverified: ambiguous)", False, True
    if kind == "order":
        state = orders[ident]
        return (f" ({state})", True, False) if state in FINISHED else ("", False, False)
    o, r, n = ident
    try:
        out = subprocess.run(["gh", "api", f"repos/{o}/{r}/issues/{n}"], capture_output=True, text=True,
                             timeout=timeout)
    except subprocess.TimeoutExpired:
        return " (unverified: timeout)", False, True
    except OSError:
        return " (unverified: no gh)", False, True
    try:
        item = json.loads(out.stdout) if out.returncode == 0 else None
    except json.JSONDecodeError:
        item = None
    if not isinstance(item, dict):
        return " (unverified: gh failed)", False, True
    merged = (item.get("pull_request") or {}).get("merged_at")
    if merged:
        return f" (merged {local(merged):%Y-%m-%d %H:%M})", True, False
    if item.get("state") == "closed" and item.get("closed_at"):
        return f" (closed {local(item['closed_at']):%Y-%m-%d})", True, False
    return "", False, False


def main(argv: list) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    prep, repos = Path(argv[0]), argv[2:]
    try:
        orders = {i["id"]: i["state"] for i in json.loads(Path(argv[1]).read_text(encoding="utf-8"))["items"]}
    except (OSError, ValueError, KeyError, TypeError):
        orders = {}
    timeout = float(os.environ.get("STATUS_TIMEOUT", "10"))
    seen, counts = {}, {"checked": 0, "closed": 0, "unverified": 0}
    for name in FILES:
        path = prep / name
        if not path.is_file():
            continue
        text, out, at = path.read_text(encoding="utf-8"), [], 0
        for m in REF.finditer(text):
            k = key(m, repos, orders)
            if k is None:
                continue
            if k not in seen:
                if len(seen) >= MAX:
                    continue
                mark, closed, unverified = check(*k, orders, timeout)
                seen[k] = mark
                counts["checked"] += 1
                counts["closed"] += closed
                counts["unverified"] += unverified
            end = m.end()
            if m["url"] and text[m.start() - 2:m.start()] == "](" and text[end:end + 1] == ")":
                end += 1   # a markdown link: the mark goes after it, never inside the URL
            if seen[k] and not MARKED.match(text, end):
                out.append(text[at:end] + seen[k])
                at = end
        if at:
            path.write_text("".join(out) + text[at:], encoding="utf-8")
    print(f"status: {counts['checked']} checked, {counts['closed']} closed, {counts['unverified']} unverified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
