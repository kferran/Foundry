#!/usr/bin/env python3
"""Scaffold an extension Source (factory F4 §3.2) from the template folder beside this script.

Usage: python3 .claude/skills/new-source/new_source.py <name> --tool <mcp__server__tool> --server "<server>"
         (--tools <lib_fetch.sh table> | --server-tool <tool>…) --description "<one line>" --credential "<what>"
         --renew "<how>" [--issue <n>]
Run from the repository root. Writes extensions/<name>/ and, in the template repository (no system/config.md), one
`- Added: <description>. (#<issue>)` line under today's date in CHANGELOG.md.
Exit: 0 written; 2 usage, with one `new_source: <reason>` line on stderr and nothing written.
"""
import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template"
NAME = re.compile(r"[a-z][a-z0-9_]*")
TOOL = re.compile(r"mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+")
BARE = re.compile(r"[A-Za-z0-9_-]+")
UNSAFE = re.compile(r'["\\$`\n]')   # each value lands in a bash string, a YAML string or a prompt


class Usage(Exception):
    pass


def tables(root: Path) -> dict:
    """lib_fetch.sh's server tables: {"GMAIL_TOOLS": [tool, …], …}."""
    text = (root / "system/scripts/lib_fetch.sh").read_text(encoding="utf-8")
    return {m[1]: m[2].split() for m in re.finditer(r"^(\w+_TOOLS)=\(([^)]*)\)", text, re.M)}


def check(root: Path, a, table: dict) -> None:
    """Raise Usage for the first argument that cannot make a Source, in the order the skill documents."""
    sys.path.insert(0, str(root / "system" / "scripts"))
    from vaultlib import alerts, frontmatter

    if not NAME.fullmatch(a.name):
        raise Usage(f"{a.name}: a Source name is [a-z][a-z0-9_]*")
    if not TOOL.fullmatch(a.tool):
        raise Usage(f"--tool {a.tool} is not mcp__<server>__<tool>")
    for flag in ("server", "description", "credential", "renew"):
        if UNSAFE.search(getattr(a, flag)):
            raise Usage(f"--{flag} holds a quote, backslash, $, backtick or newline")
    if (root / "extensions" / a.name).exists():
        raise Usage(f"extensions/{a.name} exists")
    if a.name in alerts.TAGS:
        raise Usage(f"{a.name} is a core alert tag")
    for p in sorted(root.glob("extensions/*/extension.md")):
        tags = (frontmatter.parse(p.read_text(encoding="utf-8")).data or {}).get("alert_tags") or []
        if a.name in [t.get("tag") if isinstance(t, dict) else t for t in tags]:
            raise Usage(f"{a.name} is the {p.parent.name} extension's alert tag")
    bare = a.tool.rsplit("__", 1)[1]
    if a.tools and bare not in table[a.tools]:
        raise Usage(f"{bare} is not in {a.tools}")
    if a.server_tool:
        bad = [t for t in a.server_tool if not BARE.fullmatch(t)]
        if bad:
            raise Usage(f"--server-tool {bad[0]} is not a tool name")
        if bare not in a.server_tool:
            raise Usage(f"{bare} is not in --server-tool")
    if a.issue is None and not (root / "system/config.md").exists():
        raise Usage("--issue is required in the template repository")


def changelog(text: str, line: str) -> str:
    """text with line under today's heading in Changes, the heading added first when it is missing."""
    lines, head = text.split("\n"), f"## {date.today().isoformat()}"
    if head in lines:
        lines.insert(lines.index(head) + 1, line)
    else:
        at = lines.index("## Changes") + 2   # after its blank line
        lines[at:at] = [head, line, ""]
    return "\n".join(lines)


def main(argv: list) -> int:
    root = Path.cwd()
    if not (root / "system/scripts/lib_fetch.sh").is_file():
        print("new_source: run it from the repository root (no system/scripts/lib_fetch.sh here)", file=sys.stderr)
        return 2
    table = tables(root)
    p = argparse.ArgumentParser(prog="new_source", description="Scaffold an extension Source.")
    p.add_argument("name")
    p.add_argument("--tool", required=True)
    p.add_argument("--server", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tools", choices=list(table))
    g.add_argument("--server-tool", nargs="+")
    p.add_argument("--description", required=True)
    p.add_argument("--credential", required=True)
    p.add_argument("--renew", required=True)
    p.add_argument("--issue", type=int)
    a = p.parse_args(argv)
    try:
        check(root, a, table)
    except Usage as u:
        print(f"new_source: {u}", file=sys.stderr)
        return 2
    vault = (root / "system/config.md").exists()
    log = root / "CHANGELOG.md"
    new_log = None if vault else changelog(log.read_text(encoding="utf-8"), f"- Added: {a.description}. (#{a.issue})")
    own = ("# The server's full tool list, the tool included (lib_fetch.sh has no table for this server).\n"
           f"SERVER_TOOLS=({' '.join(a.server_tool)})") if a.server_tool else ""
    subs = {"@@name@@": a.name, "@@NAME@@": a.name.upper(), "@@tool@@": a.tool,
            "@@prefix@@": a.tool.rsplit("__", 1)[0], "@@server@@": a.server, "@@description@@": a.description,
            "@@credential@@": a.credential, "@@renew@@": a.renew,
            "@@tools@@": f'"${{{a.tools or "SERVER_TOOLS"}[@]}}"', "@@server_tools@@": own}

    def fill(s: str) -> str:
        for k, v in subs.items():
            s = s.replace(k, v)
        return s

    for src in sorted(TEMPLATE.rglob("*")):
        if src.is_file():
            out = root / "extensions" / a.name / fill(src.relative_to(TEMPLATE).as_posix())
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(fill(src.read_text(encoding="utf-8")), encoding="utf-8")
            shutil.copymode(src, out)
    if new_log is not None:
        log.write_text(new_log, encoding="utf-8")
    print(f"new_source: wrote extensions/{a.name}/" + ("" if vault else " and a CHANGELOG.md line"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
