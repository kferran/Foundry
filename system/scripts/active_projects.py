#!/usr/bin/env python3
"""Active projects for the brief (active projects spec, issue #65).

Usage: active_projects.py YYYY-MM-DD   prints projects.md: for wiki/<partition>/ActiveProjects.md in work and
personal, the "## Active" entries in order, each with its first 3 open checkboxes and the open checkboxes under
its "Decisions…" headings. Run from the vault root. Exit 0, 2 on a bad date, 1 on any other failure.
"""
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib import frontmatter  # noqa: E402
from vaultlib.links import FENCE, Resolver, wiki_target  # noqa: E402

PARTITIONS = ("work", "personal")
LIST_NAME = "ActiveProjects.md"
MAX_ACTIVE = 10
MAX_NEXT = 3
ENTRY = re.compile(r"^- \[\[([^\[\]\n]+?)\]\](?::\s*(.*\S))?\s*$")
OPEN = re.compile(r"^\s*- \[ \] (.+)$")
HEADING = re.compile(r"^(#{1,6}) (.*)$")


def active_entries(text: str) -> list[tuple[str, str]]:
    """(raw link text, focus) for each entry under "## Active", in order."""
    out, on = [], False
    for line in frontmatter.parse(text).body.split("\n"):
        if line.startswith("## "):
            on = line.strip() == "## Active"
            continue
        match = ENTRY.match(line) if on else None
        if match:
            out.append((match.group(1), match.group(2) or ""))
    return out


def page_items(text: str) -> tuple[list[str], list[str]]:
    """(first MAX_NEXT open checkboxes outside Decisions sections, every open checkbox inside them)."""
    nxt, decisions = [], []
    fence, decisions_level = None, None
    for line in frontmatter.parse(text).body.split("\n"):
        fenced = FENCE.match(line)
        if fenced:
            if fence is None:
                fence = fenced.group(1)
            elif fenced.group(1) == fence:
                fence = None
            continue
        if fence is not None:
            continue
        heading = HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            if decisions_level is not None and level <= decisions_level:
                decisions_level = None
            if decisions_level is None and heading.group(2).strip().lower().startswith("decisions"):
                decisions_level = level
            continue
        item = OPEN.match(line)
        if not item:
            continue
        if decisions_level is not None:
            decisions.append(item.group(1).strip())
        elif len(nxt) < MAX_NEXT:
            nxt.append(item.group(1).strip())
    return nxt, decisions


def main(argv) -> int:
    print("usage: active_projects.py YYYY-MM-DD", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
