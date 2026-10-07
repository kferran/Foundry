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


def project_block(raw: str, focus: str, text: str) -> list[str]:
    nxt, decisions = page_items(text)
    lines = ["", f"### [[{raw}]]" + (f": {focus}" if focus else ""), "Next:"]
    lines += [f"- {t}" for t in nxt] or ["- None open."]
    if decisions:
        lines += ["Decisions waiting:", *[f"- {t}" for t in decisions]]
    return lines


def partition_blocks(part: str, resolver: Resolver, notices: list[str]) -> list[str]:
    listing = Path("wiki") / part / LIST_NAME
    if not listing.is_file():
        return []
    entries = active_entries(listing.read_text(encoding="utf-8"))
    if len(entries) > MAX_ACTIVE:
        notices.append(f"- {part}: only the first {MAX_ACTIVE} active projects are shown.")
        entries = entries[:MAX_ACTIVE]
    lines = []
    for raw, focus in entries:
        link = f"[[{raw}]]"
        path, ambiguous = resolver.resolve(wiki_target(raw), listing.as_posix(), "link", len)
        if path is None:
            notices.append(f"- {part}: {link} in ActiveProjects does not resolve to a note.")
            continue
        if ambiguous:
            notices.append(f"- {part}: {link} in ActiveProjects matches more than one note; use a path link.")
            continue
        other = path.split("/")[1]
        if other != part:
            notices.append(f"- {part}: {link} is in {other}; list it in that partition's ActiveProjects.")
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            notices.append(f"- {part}: {link} could not be read.")
            continue
        lines += project_block(raw, focus, text)
    return ["", f"## {part}", *lines] if lines else []


def main(argv) -> int:
    try:
        day = date.fromisoformat(argv[1]) if len(argv) == 2 else None
    except ValueError:
        day = None
    if day is None:
        print("usage: active_projects.py YYYY-MM-DD", file=sys.stderr)
        return 2
    files = [p.as_posix() for p in Path("wiki").rglob("*.md")] if Path("wiki").is_dir() else []
    resolver = Resolver(files, name_exclude=("wiki/.staging/",))
    notices, blocks = [], []
    for part in PARTITIONS:
        blocks += partition_blocks(part, resolver, notices)
    print(f"# Active projects for {day}")
    print("\n".join(blocks) if blocks else "\nNone.")
    if notices:
        print("\n## Notices\n" + "\n".join(notices))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
