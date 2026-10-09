#!/usr/bin/env python3
"""Handoffs from Jira (delivered work spec §3.2): the query, and the check of a fetch session's stream.

Usage: jira_handoffs.py query             print the site, then the JQL, built from system/config.md
       jira_handoffs.py extract < stream  check a jira_fetch.sh session; print one brief line per ticket
A handoff is a ticket in handoffs_projects that the owner reported and someone else holds, open and with no
status-category change for 7 days. The lines come from each user event's tool_use_result.structuredContent, paired
with its call by tool_use_id; the model's own words are never used.
Exit: 0 ok, 1 claude error or a result in an unexpected shape, 2 usage or incomplete settings, 3 no connector,
6 connector error, 7 unexpected tool use or a call with other arguments. A non-zero exit writes one reason line
to stderr.
"""
import json
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import frontmatter  # noqa: E402
from vaultlib.stream import blocks, messages  # noqa: E402

TOOL = "mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql"
PROJECT = re.compile(r"^[A-Z][A-Z0-9_]{0,30}$")
KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,30}-[0-9]{1,9}$")
SITE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,200}$")


class Fail(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code, self.reason = code, reason


def config() -> dict:
    path = VAULT / "system" / "config.md"
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def query(cfg: dict) -> tuple:
    """(site, JQL) from the settings, never from free text."""
    site = str(cfg.get("handoffs_site") or "")
    projects = [str(p) for p in cfg.get("handoffs_projects") or []] if isinstance(cfg.get("handoffs_projects"), list) else []
    if not projects:
        raise Fail(2, "handoffs_projects lists no Jira project keys")
    if not SITE.match(site):
        raise Fail(2, "handoffs_site is not set to a Jira site such as example.atlassian.net")
    bad = [p for p in projects if not PROJECT.match(p)]
    if bad:
        raise Fail(2, f"not a Jira project key: {bad[0]}")
    return site, (f"project in ({', '.join(projects)}) AND reporter = currentUser() AND assignee != currentUser() "
                  "AND statusCategory != Done AND statusCategoryChangedDate <= -7d ORDER BY statusCategoryChangedDate ASC")


def pages(stream, site, jql):
    """The structuredContent of each search result, after the tool-use, argument and error checks."""
    calls, out, errors, named = {}, [], [], False
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", TOOL):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                i = b.get("input") if isinstance(b.get("input"), dict) else {}
                if b.get("name") == TOOL and (i.get("jql") != jql or i.get("cloudId") != site):
                    raise Fail(7, "the session searched with other arguments than the ones built from the settings")
                calls[b.get("id")] = b
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                call = calls.get(b.get("tool_use_id")) or {}
                content = b.get("content")
                if call.get("name") == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("tool_name") == TOOL for c in content):
                    named = True   # a tool_reference block; free text never counts
                if call.get("name") != TOOL:
                    continue
                if b.get("is_error"):
                    errors.append(json.dumps(content)[:200])
                    continue
                tur = m.get("tool_use_result")
                sc = tur.get("structuredContent") if isinstance(tur, dict) else None
                out.append(sc if isinstance(sc, dict) else {})
    result = next((m for m in reversed(stream) if m.get("type") == "result"), None)
    if result is None:
        raise Fail(1, "claude produced no result")
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
    if not any(c.get("name") == TOOL for c in calls.values()):
        raise Fail(1 if named else 3, f"the session never called {TOOL}" if named else "no Atlassian connector reachable")
    if result.get("is_error") or result.get("subtype") != "success":
        raise Fail(1, f"claude returned an error result ({result.get('subtype')})")
    return out


def cell(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().replace("[", "(").replace("]", ")")


def line(node, site) -> str:
    f = node.get("fields") if isinstance(node.get("fields"), dict) else {}
    status = f.get("status") if isinstance(f.get("status"), dict) else {}
    key, changed = node.get("key"), str(f.get("statuscategorychangedate") or "")
    if not (isinstance(key, str) and KEY.match(key) and status.get("name") and re.match(r"\d{4}-\d{2}-\d{2}", changed)):
        raise Fail(1, f"a ticket lacks a key, a status or a statuscategorychangedate: {cell(key)[:40]}")
    assignee = f.get("assignee") if isinstance(f.get("assignee"), dict) else {}
    return (f"- [ ] [{key}](https://{site}/browse/{key}) {cell(f.get('summary'))} "
            f"({cell(assignee.get('displayName')) or 'unassigned'}, {cell(status['name'])}, unchanged since {changed[:10]})")


def extract(stream, cfg) -> list:
    """The brief's lines: every page merged, each ticket once. A result in any other shape fails closed (exit 1)."""
    site, jql = query(cfg)
    got = pages(stream, site, jql)
    if not got:
        raise Fail(1, "the search call has no result")
    out, seen = [], set()
    for sc in got:
        nodes = sc.get("issues", {}).get("nodes") if isinstance(sc.get("issues"), dict) else None
        if not isinstance(nodes, list):
            raise Fail(1, "the search result carries no issues list")
        for node in nodes:
            text = line(node if isinstance(node, dict) else {}, site)
            if node["key"] not in seen:
                seen.add(node["key"])
                out.append(text)
    info = got[-1]["issues"].get("pageInfo")
    if isinstance(info, dict) and info.get("hasNextPage") is True:
        raise Fail(1, "the session stopped before the last page")
    return out


def main(argv):
    try:
        if argv[1:] == ["query"]:
            print("\n".join(query(config())))
        elif argv[1:] == ["extract"]:
            print("".join(f"{t}\n" for t in extract(messages(sys.stdin.read()), config())), end="")
        else:
            raise Fail(2, "usage: jira_handoffs.py query | extract")
    except Fail as f:
        print(f"jira_handoffs: {f.reason}", file=sys.stderr)
        return f.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
