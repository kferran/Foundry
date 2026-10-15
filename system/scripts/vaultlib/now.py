"""The Now page (Now page spec): one open-loop checklist per partition at wiki/<partition>/Now.md.

A line is `- [ ] <kind>: <statement> (<who>, since <date>[, <evidence>])`. owed and draft lines sit under
"## Needs you", waiting lines under "## Waiting". The callers hold run.lock around every write.
"""
import json
import os
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

from . import briefings, frontmatter, nightshift_item

PARTITIONS = ("work", "personal")
KINDS = ("owed", "waiting", "draft")
NEEDS, WAITING = "## Needs you", "## Waiting"
KEEP_DAYS = 7
STALE_DAYS = 14
LOOKBACK_DAYS = briefings.LOOKBACK_DAYS
FAILURE_ALERT = 3
GH_TIMEOUT = 10
WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]")
LINE = re.compile(r"^- \[(?P<mark>.)\] (?P<kind>owed|waiting|draft): (?P<statement>.+) "
                  r"\((?:(?P<who>[^(),]+), )?since (?P<since>\d{4}-\d{2}-\d{2})(?:, (?P<evidence>[^\s(),]+))?\)"
                  r"(?: _\(closed: .*\)_)?\s*$")  # an editor's trailing space or CRLF must not hide a line (audit C12)
CLOSED = re.compile(r"^- \[[xX-]\] ")
STAMP = re.compile(r"_\(closed: .*?(\d{4}-\d{2}-\d{2})\)_\s*$")
PR_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+$")
ORDER_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
ORDER_CLOSED = ("done", "failed", "cancelled")
SINCE = re.compile(r"\s*_\(open since (\d{4}-\d{2}-\d{2})(?:, \d+ days?)?\)_")
# The Now clock (Now clock spec §3): two optional Dataview inline fields inside the statement, before the parenthesis.
# Dataview reads the key in any case and "::" with or without spaces, so a hand edit may write either.
REC = re.compile(r"\[rec::\s*([^\[\]\n]*[^\[\]\s])\s*\]", re.IGNORECASE)
DUE = re.compile(r"\[due::\s*(\d{4}-\d{2}-\d{2})\s*\]", re.IGNORECASE)
FIELD_KEY = re.compile(r"\[(?:rec|due)::", re.IGNORECASE)
ISO_DATE = re.compile(r"(?<![\w-])(\d{4}-\d{2}-\d{2})(?=T\d{2}:\d{2}|(?![\w-]|\.\w))")
SHORT_DAYS, LONG_DAYS = 3, 30
OVERDUE_HEADINGS = ("**1 to 7 days over**", "**8 to 30 days over**", "**More than 30 days over**")


class CheckFailed(Exception):
    pass


def page_path(vault, partition: str) -> Path:
    return Path(vault) / "wiki" / partition / "Now.md"


def new_page(vault, partition: str, today: str) -> str:
    template = (Path(vault) / "system" / "templates" / "now.md").read_text(encoding="utf-8")
    return template.replace("{{date}}", today).replace("{{partition}}", partition)


def fields(statement: str) -> tuple:
    """(bare statement, rec, due): the statement without its two fields, whitespace collapsed; "" for a missing field
    and for a due that is not a real date (a hand edit such as 2026-02-30)."""
    rec, due = REC.search(statement), DUE.search(statement)
    bare = " ".join(DUE.sub("", REC.sub("", statement)).split())
    return bare, rec.group(1) if rec else "", due.group(1) if due and is_date(due.group(1)) else ""


def render(kind: str, statement: str, since: str, who: str = "", evidence: str = "", rec: str = "",
           due: str = "") -> str:
    meta = (f"{who}, " if who else "") + f"since {since}" + (f", {evidence}" if evidence else "")
    clock = (f" [rec:: {rec}]" if rec else "") + (f" [due:: {due}]" if due else "")
    return f"- [ ] {kind}: {statement}{clock} ({meta})"


def read(vault, partition: str) -> str:
    path = page_path(vault, partition)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def write(vault, partition: str, text: str) -> None:
    path = page_path(vault, partition)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".Now.md.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def open_lines(text: str) -> list:
    return [line for line in frontmatter.parse(text).body.splitlines() if line.startswith("- [ ] ")]


def stamp_and_prune(text: str, today: str) -> str:
    """Stamp a ticked or dropped line that has no close date; drop one closed more than KEEP_DAYS ago; a reopened
    line loses its old stamp."""
    cutoff = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS)).isoformat()
    out = []
    for line in text.split("\n"):
        if line.startswith("- [ ] "):
            line = STAMP.sub("", line).rstrip()
        elif CLOSED.match(line):
            stamp = STAMP.search(line)
            if not stamp:
                line = f"{line.rstrip()} _(closed: ticked {today})_"
            elif stamp.group(1) < cutoff:
                continue
        out.append(line)
    return "\n".join(out)


def _insert(text: str, heading: str, line: str) -> str:
    """Add line as the last line of the heading's section; add the heading at the end when it is missing."""
    lines = text.rstrip("\n").split("\n")
    if heading not in lines:
        return "\n".join(lines + ["", heading, line]) + "\n"
    end = lines.index(heading) + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    while end > lines.index(heading) + 1 and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[:end] + [line] + lines[end:]) + "\n"


def validate(partition: str, kind: str, statement: str, who: str, evidence: str, rec: str = "", due: str = "") -> None:
    if partition not in PARTITIONS:
        raise ValueError(f"partition must be one of {', '.join(PARTITIONS)}; shared holds no Now page")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not statement.strip() or "\n" in statement or "\r" in statement:
        raise ValueError("the statement must be one non-empty line")
    if any(c in who for c in "(),\n"):
        raise ValueError("who must not hold a comma, a parenthesis or a newline")
    if evidence and not re.fullmatch(r"[^\s(),]+", evidence):
        raise ValueError("evidence must be one URL or key without spaces, commas or parentheses")
    if FIELD_KEY.search(statement):
        raise ValueError("the statement must not hold [rec:: or [due::; pass --rec and --due")
    if any(c in rec for c in "[]\n\r"):
        raise ValueError("rec must not hold a bracket or a newline")
    if due and not is_date(due):
        raise ValueError("due must be a date, YYYY-MM-DD")


def is_date(text: str) -> bool:
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)) and bool(date.fromisoformat(text))
    except ValueError:
        return False


def default_due(statement: str, since: str, who: str) -> str:
    """The decide-by date (Now clock spec §4): since + SHORT_DAYS when someone is named or the statement names a date
    of its own within LONG_DAYS of since, else since + LONG_DAYS. A Work Order id, a file name and a date inside a URL
    or a path (a token holding "/") do not count; a date with a time (2026-10-20T09:00) does."""
    start = date.fromisoformat(since)
    named = [d for token in statement.split() if "/" not in token for d in ISO_DATE.findall(token) if is_date(d)]
    soon = any(0 <= (date.fromisoformat(d) - start).days <= LONG_DAYS for d in named)
    return (start + timedelta(days=SHORT_DAYS if who or soon else LONG_DAYS)).isoformat()


def add(vault, partition: str, kind: str, statement: str, today: str, who: str = "", evidence: str = "",
        rec: str = "", due: str = "") -> tuple:
    """("added"|"exists"|"tightened"|"updated", line). An open line with the same kind and bare statement is not
    added twice: a repeat add moves its clock earlier ("tightened"), sets or replaces rec and sets missing evidence
    ("updated"), writes nothing when nothing is new, and raises ValueError when it would move the clock later."""
    statement, who, rec = statement.strip(), who.strip(), rec.strip()
    validate(partition, kind, statement, who, evidence, rec, due)
    text = read(vault, partition) or new_page(vault, partition, today)
    for existing in open_lines(text):
        m = LINE.match(existing)
        if not (m and m.group("kind") == kind):
            continue
        bare, old_rec, old_due = fields(m.group("statement"))
        if bare != fields(statement)[0]:
            continue
        if due and old_due and due > old_due:
            raise ValueError(f"would loosen the clock (due {old_due})")
        new_due = due if due and (not old_due or due < old_due) else old_due
        new_rec, new_evidence = rec or old_rec, m.group("evidence") or evidence
        if (new_due, new_rec, new_evidence) == (old_due, old_rec, m.group("evidence") or ""):
            return "exists", existing
        line = render(kind, bare, m.group("since"), m.group("who") or "", new_evidence, new_rec, new_due)
        lines = text.split("\n")
        lines[[x.rstrip() for x in lines].index(existing.rstrip())] = line
        write(vault, partition, stamp_and_prune("\n".join(lines), today))
        return "tightened" if new_due != old_due else "updated", line
    line = render(kind, statement, today, who, evidence, rec, due or default_due(statement, today, who))
    text = _insert(stamp_and_prune(text, today), WAITING if kind == "waiting" else NEEDS, line)
    write(vault, partition, text)
    return "added", line


def evidence_state(vault, evidence: str, gh: str = "gh"):
    """The close reason ("PR merged", "Work Order done", …), None while still open, or CheckFailed."""
    if PR_URL.match(evidence):
        try:
            out = subprocess.run([gh, "pr", "view", evidence, "--json", "state", "-q", ".state"],
                                 capture_output=True, text=True, timeout=GH_TIMEOUT)
        except FileNotFoundError:
            raise CheckFailed("gh is not installed")
        except subprocess.TimeoutExpired:
            raise CheckFailed("gh timed out")
        if out.returncode != 0:
            raise CheckFailed(f"gh exit {out.returncode}: {out.stderr.strip()[:200]}")
        state = out.stdout.strip().upper()
        return f"PR {state.lower()}" if state in ("MERGED", "CLOSED") else None
    if ORDER_ID.match(evidence):
        for _, fm, _ in nightshift_item.items(vault):
            if fm.get("id") == evidence:
                return f"Work Order {fm.get('state')}" if fm.get("state") in ORDER_CLOSED else None
    return None


def _failed(vault, today: str, line: str, reason: str, alert) -> None:
    """Log one failed check; the third failure of the same line on one day raises one alert."""
    log = Path(vault) / "system" / "logs" / f"now-{today[:7]}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": today, "line": line, "reason": reason}) + "\n")
    count = 0
    for raw in log.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        count += isinstance(record, dict) and record.get("date") == today and record.get("line") == line
    if count == FAILURE_ALERT:
        alert(f"Now check failed {FAILURE_ALERT} times today for: {line} ({reason})")


def closures(vault, lines: list, gh: str = "gh", on_fail=lambda line, reason: None) -> dict:
    """{line: how} for the open lines whose evidence shows them finished. Read-only. The first failed pull-request
    check (reported through on_fail) skips the other pull requests."""
    found, gh_down = {}, False
    for line in lines:
        m = LINE.match(line)
        if not m or not m.group("evidence") or (gh_down and PR_URL.match(m.group("evidence"))):
            continue
        try:
            how = evidence_state(vault, m.group("evidence"), gh)
        except CheckFailed as exc:
            on_fail(line, str(exc))
            gh_down = True
            continue
        if how:
            found[line.rstrip()] = how
    return found


def check(vault, today: str, alert, gh: str = "gh") -> int:
    """Close each open line whose evidence shows it is finished. Returns the lines closed.

    The page is written only when a line closes, and from a fresh read, so a tick made while gh ran is kept.
    The first failed pull-request check skips the others until the next tick."""
    closed = 0
    pages = {partition: open_lines(read(vault, partition)) for partition in PARTITIONS}
    found = closures(vault, [line for lines in pages.values() for line in lines], gh,
                     lambda line, reason: _failed(vault, today, line, reason, alert))
    for partition, open_ in pages.items():
        if not any(line.rstrip() in found for line in open_):
            continue
        lines = read(vault, partition).split("\n")
        for i, line in enumerate(lines):
            key = line.rstrip()
            if key in found:
                lines[i] = f"- [x]{key[5:]} _(closed: {found[key]} {today})_"
                closed += 1
        write(vault, partition, stamp_and_prune("\n".join(lines), today))
    return closed


def review(vault, partition: str, today: str, stale_days: int = STALE_DAYS, gh: str = "gh",
           on_fail=lambda line, reason: None) -> dict:
    """The lull review (#145), read-only: "closed" (open lines whose evidence shows them finished, each with its
    close reason), "stale" (open more than stale_days with no evidence) and "duplicate" (the same bare statement after
    lowercasing, whatever the kind and clock), in page order. A hand-written line that does not parse has no date or
    evidence and is left out of those groups; one that holds a [rec::] or [due::] field it cannot read (written after
    the parenthesis) is listed under "unreadable" for the Foreman to fix by hand."""
    lines = [line.rstrip() for line in open_lines(read(vault, partition))]  # an editor's trailing space (C12)
    cutoff = (date.fromisoformat(today) - timedelta(days=stale_days)).isoformat()
    parsed = [(line, LINE.match(line)) for line in lines]
    found = closures(vault, lines, gh, on_fail)
    statements = {}
    for line, m in parsed:
        if m:
            statements.setdefault(fields(m.group("statement"))[0].lower(), []).append(line)
    return {"closed": [f"{line} _(closed: {found[line]})_" for line in lines if line in found],
            "stale": [line for line, m in parsed if m and not m.group("evidence") and m.group("since") < cutoff],
            "duplicate": [line for group in statements.values() if len(group) > 1 for line in group],
            "unreadable": [line for line, m in parsed if not m and FIELD_KEY.search(line)]}


def overdue(vault, day: str) -> str:
    """The brief's Overdue block (Now clock spec §7), read-only: the open lines of both pages whose due is before day,
    grouped by days over, oldest due first, then the count of open lines with no clock; "" when there is neither."""
    groups, clockless = ([], [], []), 0
    for partition in PARTITIONS:
        for line in open_lines(read(vault, partition)):
            due = DUE.search(line)
            if not (due and is_date(due.group(1))):
                clockless += 1
                continue
            over = (date.fromisoformat(day) - date.fromisoformat(due.group(1))).days
            if over > 0:
                groups[0 if over <= 7 else 1 if over <= 30 else 2].append((due.group(1), f"- {line.rstrip()[6:]}"))
    out = []
    for heading, lines in zip(OVERDUE_HEADINGS, groups):
        if lines:
            out += [heading] + [line for _, line in sorted(lines, key=lambda t: t[0])]
    if clockless:
        out.append(f"{clockless} open lines carry no clock.")
    return "\n".join(out)


def latest_open_objectives(vault, day: str) -> list:
    """(text, since) for each open objective of the latest briefing before day (the retired carry-forward)."""
    for earlier, path in briefings.earlier_briefings(vault, day):
        section = re.search(r"(?ms)^### 1\..*?(?=^### 2\.|\Z)", path.read_text(encoding="utf-8"))
        out = []
        for line in (section.group(0) if section else "").splitlines():
            if line.startswith("- [ ] "):
                # Plain text: a link may point into the other partition, and the seed bypasses the publish gate.
                text = WIKILINK.sub(r"\1", re.sub(r"^\*\*stale\*\*\s*", "", SINCE.sub("", line[6:]).strip()))
                out.append((text, min(SINCE.findall(line), default=earlier)))
        return out
    return []


def seed(vault, partition: str, day: str) -> int:
    """Once: create a partition's missing Now page from the latest earlier briefing's open objectives."""
    if partition not in PARTITIONS or page_path(vault, partition).exists():
        return 0
    text = new_page(vault, partition, day)
    items = [(t, s) for t, s in latest_open_objectives(vault, day) if t]
    for statement, since in items:
        text = _insert(text, NEEDS, render("owed", statement, since))
    write(vault, partition, text)
    return len(items)
