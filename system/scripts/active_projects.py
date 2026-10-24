#!/usr/bin/env python3
"""Active projects for the brief (active projects spec, issue #65).

Usage: active_projects.py YYYY-MM-DD   prints projects.md: for wiki/<partition>/ActiveProjects.md in work and
personal, the "## Active" entries in order, each with its first 3 open checkboxes and the first 3 open checkboxes
under its "Decisions…" headings. Run from the vault root. Exit 0, 2 on a bad date, 1 on any other failure.
       active_projects.py YYYY-MM-DD --json
                                     the same as one JSON object (#375): {"v": 1, "date", "partitions": {<p>:
                                     {"projects", "also_active"}}, "notices"}, items uncut
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib import frontmatter  # noqa: E402
from vaultlib.briefings import cut  # noqa: E402
from vaultlib.index import PRIVATE  # noqa: E402
from vaultlib.links import FENCE, Resolver, wiki_target  # noqa: E402

PARTITIONS = ("work", "personal")
LIST_NAME = "ActiveProjects.md"
MAX_ACTIVE = 10
MAX_NEXT = 3
MAX_DECISIONS = 3
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


def list_problems(text: str) -> list[str]:
    """Why a list would silently show fewer projects: no "## Active" heading, or Active lines with a link
    that are not entries (a numbered or bold line, say)."""
    lines = frontmatter.parse(text).body.split("\n")
    if not any(line.strip() == "## Active" for line in lines):
        return ['ActiveProjects has no "## Active" heading.']
    out, on = [], False
    for line in lines:
        if line.startswith("## "):
            on = line.strip() == "## Active"
            continue
        if on and "[[" in line and not ENTRY.match(line):
            out.append(f"line in ActiveProjects is not an entry: {line.strip()}")
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


def project_data(raw: str, path: str, focus: str, text: str) -> dict:
    """One project as --json prints it (#375): at most MAX_NEXT next actions and MAX_DECISIONS decisions, uncut."""
    nxt, decisions = page_items(text)
    return {"link": raw, "path": path, "focus": focus, "next": nxt, "decisions": decisions[:MAX_DECISIONS],
            "decisions_more": max(len(decisions) - MAX_DECISIONS, 0), "stale": None}


def render_project(project: dict) -> list[str]:
    """The brief's block for one project, each item cut to one brief item (phase A spec §3.1)."""
    lines = ["", f"### [[{project['link']}]]" + (f": {project['focus']}" if project["focus"] else ""), "Next:"]
    lines += [f"- {cut(t)}" for t in project["next"]] or ["- None open."]
    if project["decisions"]:
        lines += ["Decisions waiting:", *[f"- {cut(t)}" for t in project["decisions"]]]
        if project["decisions_more"]:
            lines.append(f"- and {project['decisions_more']} more decisions on the page")
    return lines


def project_block(raw: str, focus: str, text: str) -> list[str]:
    return render_project(project_data(raw, "", focus, text))


def partition_data(part: str, resolver: Resolver, notices: list[str]):
    """The partition's projects in list order, or None when it has no ActiveProjects list."""
    listing = Path("wiki") / part / LIST_NAME
    if not listing.is_file():
        return None
    list_text = listing.read_text(encoding="utf-8")
    notices += [f"- {part}: {problem}" for problem in list_problems(list_text)]
    entries = active_entries(list_text)
    if len(entries) > MAX_ACTIVE:
        notices.append(f"- {part}: only the first {MAX_ACTIVE} active projects are shown.")
        entries = entries[:MAX_ACTIVE]
    projects = []
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
        projects.append(project_data(raw, path, focus, text))
    return projects


def main(argv) -> int:
    as_json = argv[2:] == ["--json"]
    try:
        day = date.fromisoformat(argv[1]) if len(argv) == 2 or as_json else None
    except ValueError:
        day = None
    if day is None:
        print("usage: active_projects.py YYYY-MM-DD [--json]", file=sys.stderr)
        return 2
    files = [p.as_posix() for p in Path("wiki").rglob("*.md") if not PRIVATE.match(p.as_posix())] if Path("wiki").is_dir() else []
    resolver = Resolver(files, name_exclude=("wiki/.staging/",))
    notices, data = [], {}
    for part in PARTITIONS:
        projects = partition_data(part, resolver, notices)
        if projects is not None:
            data[part] = {"projects": projects, "also_active": []}
    if as_json:
        print(json.dumps({"v": 1, "date": day.isoformat(), "partitions": data, "notices": notices}, ensure_ascii=False))
        return 0
    blocks = []
    for part, d in data.items():
        lines = [line for project in d["projects"] for line in render_project(project)]
        blocks += ["", f"## {part}", *lines] if lines else []
    print(f"# Active projects for {day}")
    print("\n".join(blocks) if blocks else "\nNone.")
    if notices:
        print("\n## Notices\n" + "\n".join(notices))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
