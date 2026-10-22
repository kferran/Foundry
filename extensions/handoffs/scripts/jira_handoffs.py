#!/usr/bin/env python3
"""Handoffs from Jira (delivered work spec §3.2): the query, and the check of a fetch session's stream.

Usage: jira_handoffs.py query             print the site, then the JQL, built from system/config.md
       jira_handoffs.py extract [--date D] < stream  check a jira_fetch.sh session; print the brief's lines: up to
                                          10 tickets, then counts (phase A spec §3.3)
A handoff is a ticket in handoffs_projects that the owner reported and someone else holds, open and with no
status-category change for 7 days. The lines come from each search result's structuredContent (the shared connector checks);
the model's own words are never used.
Exit: 0 ok, 1 claude error or a result in an unexpected shape, 2 usage or incomplete settings, 3 no connector,
6 connector error, 7 unexpected tool use or a call with other arguments. A non-zero exit writes one reason line
to stderr.
"""
import re
import sys
from datetime import date, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parents[3]   # extensions/handoffs/scripts/
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib.api import Fail, check_stream, config, cut, messages  # noqa: E402

TOOL = "mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql"
PROJECT = re.compile(r"^[A-Z][A-Z0-9_]{0,30}$")
KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,30}-[0-9]{1,9}$")
SITE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,200}$")
CHANGED = re.compile(r"unchanged since (\d{4}-\d{2}-\d{2})\)$")
MAX_LISTED, OLD_DAYS = 10, 90


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


def pages(stream, site, jql, persisted):
    """The structuredContent of each search result, after the shared connector's tool-use, argument and error checks.
    A page the model saw only as too large is counted in `persisted` and still read: structuredContent holds the
    whole page, and extract's last-page check catches a model that could not see hasNextPage."""
    def accept(i):
        if i.get("jql") != jql or i.get("cloudId") != site:
            raise Fail(7, "the session searched with other arguments than the ones built from the settings")
        return "search"
    return check_stream(stream, TOOL, accept, server="Atlassian", persisted=persisted)[0].get("search", [])


def cell(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().replace("[", "(").replace("]", ")")


def line(node, site) -> str:
    f = node.get("fields") if isinstance(node.get("fields"), dict) else {}
    status = f.get("status") if isinstance(f.get("status"), dict) else {}
    key, changed = node.get("key"), str(f.get("statuscategorychangedate") or "")
    if not (isinstance(key, str) and KEY.match(key) and status.get("name") and re.match(r"\d{4}-\d{2}-\d{2}", changed)):
        raise Fail(1, f"a ticket lacks a key, a status or a statuscategorychangedate: {cell(key)[:40]}")
    assignee = f.get("assignee") if isinstance(f.get("assignee"), dict) else {}
    return (f"- [ ] [{key}](https://{site}/browse/{key}) {cut(cell(f.get('summary')))} "
            f"({cell(assignee.get('displayName')) or 'unassigned'}, {cell(status['name'])}, unchanged since {changed[:10]})")


def extract(stream, cfg, persisted=None) -> list:
    """The brief's lines: every page merged, each ticket once. A result in any other shape fails closed (exit 1).
    `persisted` (a dict) counts the pages the model saw only as too large."""
    site, jql = query(cfg)
    got = pages(stream, site, jql, {} if persisted is None else persisted)
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


def chase(lines: list, today: str) -> list:
    """The brief's list (phase A spec §3.3): oldest change first, at most MAX_LISTED changed within OLD_DAYS, then a
    count of the rest, then one line for every ticket unchanged longer."""
    dated = sorted((CHANGED.search(t).group(1), t) for t in lines)
    cutoff = (date.fromisoformat(today) - timedelta(days=OLD_DAYS)).isoformat()
    old, recent = [d for d in dated if d[0] < cutoff], [t for c, t in dated if c >= cutoff]
    out = recent[:MAX_LISTED] + ([f"- and {len(recent) - MAX_LISTED} more"] if len(recent) > MAX_LISTED else [])
    if old:
        key = re.search(r"\[([A-Z][A-Z0-9_]*-\d+)\]", old[0][1]).group(1)
        out.append(f"- {len(old)} handoffs unchanged for more than {OLD_DAYS} days (oldest: {key}, since {old[0][0]})")
    return out


def main(argv):
    try:
        if argv[1:] == ["query"]:
            print("\n".join(query(config(VAULT))))
        elif argv[1:2] == ["extract"] and (argv[2:] == [] or argv[2:3] == ["--date"] and len(argv) == 4):
            today = argv[3] if len(argv) == 4 else date.today().isoformat()
            print("".join(f"{t}\n" for t in chase(extract(messages(sys.stdin.read()), config(VAULT)), today)), end="")
        else:
            raise Fail(2, "usage: jira_handoffs.py query | extract [--date YYYY-MM-DD]")
    except Fail as f:
        print(f"jira_handoffs: {f.reason}", file=sys.stderr)
        return f.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
