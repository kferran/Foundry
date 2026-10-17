"""RCA-to-Jira (RCA spec §3.3): which approved drafts to file, the filer's arguments, the check of its session, and the
write-back. The arguments come from the settings and the note's Ticket draft only; the key comes from the tool result."""
import json
import re
import subprocess
from pathlib import Path

from vaultlib import cli, frontmatter, now as nowmod
from vaultlib.cli import set_scalar
from vaultlib.stream import blocks

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
    pruned by now). A dropped line whose ticket was already created (a saved .key) files instead of rejecting."""
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
                # A saved key means the ticket exists: a drop still files, which only writes the key back (#106).
                saved = (Path(vault) / "system" / "logs" / "rca" / f"{partition}-{stem}.key").is_file()
                out.append(("reject" if m.group("mark") == "-" and not saved else "file", partition, stem))
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
    extra = cfg.get("rca_extra_fields") if isinstance(cfg.get("rca_extra_fields"), dict) else {}
    if "labels" in extra:
        raise Fail(2, "rca_extra_fields may not set labels: use rca_labels")
    summary, description = draft(note_path(vault, partition, stem).read_text(encoding="utf-8"))
    args = {"cloudId": site, "projectKey": project, "issueTypeName": str(cfg.get("rca_issue_type") or "Bug"),
            "summary": summary, "description": description, "contentFormat": "markdown"}
    fields = {"labels": [str(x) for x in labels]} if labels else {}
    fields.update({str(k): _field_value(v) for k, v in extra.items()})   # #175: a project's required fields
    if fields:
        args["additional_fields"] = fields
    if cfg.get("rca_assignee"):
        args["assignee_account_id"] = str(cfg["rca_assignee"])
    return args


def _field_value(value):
    """A value written as JSON (a select's '{"id": "10042"}') is sent as that JSON; any other is sent as text."""
    try:
        return json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return value


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


REJECTED = re.compile(r"\b(400|401|403|404|422)\b|Bad Request|is required|is not valid|does not exist")


def _text(content) -> str:
    """A tool result's text: a string as it is, a list of blocks as their text joined."""
    if isinstance(content, list):
        return " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def rejected_create(stream):
    """The first error line when every create call came back as a client rejection, which proves Jira created
    nothing (#175); None after any other outcome, since a ticket may exist."""
    calls, results = set(), []
    for m in stream:
        if m.get("type") == "assistant":
            calls |= {b.get("id") for b in blocks(m, "tool_use") if b.get("name") == TOOL}
        if m.get("type") == "user":
            results += [b for b in blocks(m, "tool_result") if b.get("tool_use_id") in calls]
    texts = [_text(b.get("content")) for b in results]
    if not calls or len(results) != len(calls) or not all(b.get("is_error") for b in results):
        return None
    if not all(REJECTED.search(t) for t in texts):
        return None
    return " ".join(texts[0].split())[:200]


def reopen(vault, partition: str, stem: str, reason: str, today: str) -> None:
    """Under run.lock, after a rejected create: the note goes back to draft and its Now line is unticked with the
    reason in its statement, so nothing retries until you tick it again (#175)."""
    set_scalar(note_path(vault, partition, stem), "status", "draft")
    why = " ".join(re.sub(r"[()]", "", reason).split())[:160]
    lines = nowmod.read(vault, partition).split("\n")
    for i, line in enumerate(lines):
        m = nowmod.LINE.match(line)
        if m and m.group("evidence") == f"rca:{stem}":
            # The reason joins the bare statement; the Now clock's fields stay after it (Now clock spec §3).
            bare, rec, due = nowmod.fields(m.group("statement"))
            bare = re.sub(r": not filed \d{4}-\d{2}-\d{2}, .*$", "", bare)
            clock = (f" [rec:: {rec}]" if rec else "") + (f" [due:: {due}]" if due else "")
            rest = line[m.end("statement"):]
            lines[i] = (f"- [ ] {m.group('kind')}: {bare}: not filed {today}, {why}{clock}"
                        f"{nowmod.STAMP.sub('', rest).rstrip()}")
    nowmod.write(vault, partition, "\n".join(lines))


def filed(vault, partition: str, stem: str, key: str, today: str) -> None:
    """Under run.lock: the note records the ticket and its status in one write (#106), and its Now line's stamp
    names it."""
    path = note_path(vault, partition, stem)
    text = cli.set_scalar_text(path.read_text(encoding="utf-8"), "ticket", key)
    cli.write_atomic(path, cli.set_scalar_text(text, "status", "filed"))
    lines = nowmod.read(vault, partition).split("\n")
    for i, line in enumerate(lines):
        m = nowmod.LINE.match(line)
        if m and m.group("evidence") == f"rca:{stem}" and m.group("mark") in "xX":
            lines[i] = f"{nowmod.STAMP.sub('', line).rstrip()} _(closed: filed {key} {today})_"
    nowmod.write(vault, partition, "\n".join(lines))


def rejected(vault, partition: str, stem: str) -> None:
    set_scalar(note_path(vault, partition, stem), "status", "rejected")


def tick(vault) -> None:
    """The intake tick (extensions spec §3, `tick`): file the drafts you approved on the Now page, at most PER_TICK a
    tick, and reject the dropped ones; off while rca_project is empty. A busy run.lock ends the tick: the next one
    retries."""
    from vaultlib.intake import Intake  # intake imports much of vaultlib; only the tick needs it

    vault = Path(vault)
    intake = Intake(vault)
    if not intake.config("rca_project", ""):
        return
    filed = 0
    for action, partition, stem in pending(vault):
        try:
            if action == "reject":
                with intake.lock("run.lock", timeout=0):
                    rejected(vault, partition, stem)
                continue
            if filed >= PER_TICK:
                continue
            filed += 1  # rca_file.sh logs and alerts its own failures; the next tick retries
            with intake.lock("run.lock", timeout=0):
                approve(vault, partition, stem)
        except TimeoutError:
            return
        try:
            subprocess.run([str(vault / "extensions" / "telemetry" / "scripts" / "rca_file.sh"), partition, stem],
                           cwd=vault, capture_output=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as exc:
            intake.alert(f"RCA filing of {stem} did not finish ({exc.__class__.__name__}); will retry")
