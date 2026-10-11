"""RCA-to-Jira (RCA spec §3.3): which approved drafts to file, the filer's arguments, the check of its session, and the
write-back. The arguments come from the settings and the note's Ticket draft only; the key comes from the tool result."""
import json
import re
from pathlib import Path

from . import frontmatter, now as nowmod
from .cli import set_scalar
from .stream import blocks

TOOL = "mcp__claude_ai_Atlassian__createJiraIssue"
PROJECT = re.compile(r"^[A-Z][A-Z0-9_]{0,30}$")
KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,30}-[0-9]{1,9}$")
SITE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,200}$")
STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
SUMMARY_MAX = 255
DESCRIPTION_MAX = 32000
PER_TICK = 3


class Fail(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code, self.reason = code, reason


def config(vault) -> dict:
    path = Path(vault) / "system" / "config.md"
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def note_path(vault, partition: str, stem: str) -> Path:
    return Path(vault) / "wiki" / partition / "rca" / f"{stem}.md"


def _status(path: Path):
    data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
    return None if data.get("type") != "rca" or data.get("ticket") else str(data.get("status") or "draft")


def pending(vault) -> list:
    """(action, partition, stem) for each Now line with rca:<stem> evidence that you ticked (file) or dropped (reject)
    while its note is a draft without a ticket, then each note already approved without a ticket (its Now line may be
    pruned by now)."""
    out = []
    for partition in nowmod.PARTITIONS:
        for line in nowmod.read(vault, partition).split("\n"):
            m = nowmod.LINE.match(line)
            ev = (m.group("evidence") or "") if m else ""
            if not ev.startswith("rca:") or m.group("mark") not in "xX-":
                continue
            stem = ev[4:]
            path = note_path(vault, partition, stem)
            if STEM.match(stem) and path.is_file() and _status(path) == "draft":
                out.append(("reject" if m.group("mark") == "-" else "file", partition, stem))
        for path in sorted((Path(vault) / "wiki" / partition / "rca").glob("*.md")):
            if STEM.match(path.stem) and _status(path) == "approved":
                out.append(("file", partition, path.stem))
    return out


def approve(vault, partition: str, stem: str) -> None:
    """Under run.lock: a ticked draft is approved, so the approval outlives its Now line."""
    path = note_path(vault, partition, stem)
    if _status(path) == "draft":
        set_scalar(path, "status", "approved")


def draft(text: str) -> tuple:
    """(summary, description) from the note's ## Ticket draft section."""
    body = frontmatter.parse(text).body
    section = re.search(r"(?ms)^## Ticket draft\s*$(.*)\Z", body)  # the last section: the description may hold ## headings
    if not section:
        raise Fail(2, "the note has no ## Ticket draft section")
    m = re.search(r"(?ms)^\*\*Summary:\*\*[ \t]*(.*?)[ \t]*$\s*^\*\*Description:\*\*[ \t]*$(.*)", section.group(1))
    summary, description = (m.group(1).strip(), m.group(2).strip()) if m else ("", "")
    if not summary or "\n" in summary or len(summary) > SUMMARY_MAX:
        raise Fail(2, f"the Ticket draft needs a one-line **Summary:** of at most {SUMMARY_MAX} characters")
    if not description or len(description) > DESCRIPTION_MAX:
        raise Fail(2, "the Ticket draft needs a **Description:**")
    return summary, description


def arguments(vault, partition: str, stem: str) -> dict:
    """The createJiraIssue arguments, from the settings and the note only."""
    cfg = config(vault)
    site, project = str(cfg.get("handoffs_site") or ""), str(cfg.get("rca_project") or "")
    if not SITE.match(site):
        raise Fail(2, "handoffs_site is not set to a Jira site such as example.atlassian.net")
    if not PROJECT.match(project):
        raise Fail(2, "rca_project is not set to a Jira project key")
    labels = cfg.get("rca_labels") if isinstance(cfg.get("rca_labels"), list) else []
    summary, description = draft(note_path(vault, partition, stem).read_text(encoding="utf-8"))
    args = {"cloudId": site, "projectKey": project, "issueTypeName": str(cfg.get("rca_issue_type") or "Bug"),
            "summary": summary, "description": description, "contentFormat": "markdown"}
    if labels:
        args["additional_fields"] = {"labels": [str(x) for x in labels]}
    if cfg.get("rca_assignee"):
        args["assignee_account_id"] = str(cfg["rca_assignee"])
    return args


def _find_key(value):
    if isinstance(value, dict):
        if isinstance(value.get("key"), str) and KEY.match(value["key"]):
            return value["key"]
        for v in value.values():
            found = _find_key(v)
            if found:
                return found
    if isinstance(value, list):
        for v in value:
            found = _find_key(v)
            if found:
                return found
    return None


def called(stream) -> bool:
    """Whether the session called the create tool at all: if it did, a ticket may exist whatever extract says."""
    return any(b.get("name") == TOOL for m in stream if m.get("type") == "assistant" for b in blocks(m, "tool_use"))


def extract(stream, args: dict) -> str:
    """The new issue's key, after checking the session called only the create tool, once, with exactly `args`."""
    calls, named, created, errors = {}, False, [], []
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", TOOL):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                if b.get("name") == TOOL:
                    if b.get("input") != args:
                        raise Fail(7, "the session called the create tool with other arguments than the approved draft")
                    if any(c.get("name") == TOOL for c in calls.values()):
                        raise Fail(7, "the session called the create tool more than once")
                calls[b.get("id")] = b
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                call = calls.get(b.get("tool_use_id")) or {}
                content = b.get("content")
                if call.get("name") == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("tool_name") == TOOL for c in content):
                    named = True
                if call.get("name") != TOOL:
                    continue
                if b.get("is_error"):
                    errors.append(json.dumps(content)[:200])
                    continue
                tur = m.get("tool_use_result")
                created.append(tur.get("structuredContent") if isinstance(tur, dict) else None)
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
    if not any(c.get("name") == TOOL for c in calls.values()):
        raise Fail(1 if named else 3, f"the session never called {TOOL}" if named else "no Atlassian connector reachable")
    key = _find_key(created[0]) if created else None
    if not key:
        raise Fail(1, "the create call returned no issue key")
    return key


def filed(vault, partition: str, stem: str, key: str, today: str) -> None:
    """Under run.lock: the note records the ticket, and its Now line's stamp names it."""
    path = note_path(vault, partition, stem)
    set_scalar(path, "ticket", key)
    set_scalar(path, "status", "filed")
    lines = nowmod.read(vault, partition).split("\n")
    for i, line in enumerate(lines):
        m = nowmod.LINE.match(line)
        if m and m.group("evidence") == f"rca:{stem}" and m.group("mark") in "xX":
            lines[i] = f"{nowmod.STAMP.sub('', line).rstrip()} _(closed: filed {key} {today})_"
    nowmod.write(vault, partition, "\n".join(lines))


def rejected(vault, partition: str, stem: str) -> None:
    set_scalar(note_path(vault, partition, stem), "status", "rejected")
