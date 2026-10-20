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
STALE_DAYS = 14
MAX_LINE = 300   # an open line written in full (phase A spec §3.5); history goes to notes under it
MAX_OVERDUE = 10   # lines the brief's Overdue block prints
PAGE_BYTES = 25 * 1024   # review limit (#211; phase A target)
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
ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/\d+$")   # phase A spec §2.6
ORDER_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
ORDER_CLOSED = ("done", "failed", "cancelled")
SINCE = re.compile(r"\s*_\(open since (\d{4}-\d{2}-\d{2})(?:, \d+ days?)?\)_")
# The Now clock (Now clock spec §3): two optional Dataview inline fields inside the statement, before the parenthesis.
# Dataview reads the key in any case and "::" with or without spaces, so a hand edit may write either.
REC = re.compile(r"\[rec::\s*([^\[\]\n]*[^\[\]\s])\s*\]", re.IGNORECASE)
DUE = re.compile(r"\[due::\s*(\d{4}-\d{2}-\d{2})\s*\]", re.IGNORECASE)
FIELD_KEY = re.compile(r"\[(?:rec|due)::", re.IGNORECASE)
# A line now.py wrote, with text appended after its parenthesis by hand (#211): it no longer parses.
SCRIPT_META = re.compile(r"^- \[.\] (?:owed|waiting|draft): .*?\((?:[^(),]+, )?since \d{4}-\d{2}-\d{2}[^()]*\)(?=\s*\S)")


def parse(line: str):
    """LINE's match for an open line, also for one with text typed after its parenthesis (matched without that text,
    so recall can rank it and set can rewrite it); None for a hand-written line."""
    line = line.rstrip()
    m = LINE.match(line)
    if m is None and (s := SCRIPT_META.match(line)):
        m = LINE.match(line[:s.end()])
    return m


def named_dates(statement: str) -> list:
    """The real dates a statement names: not inside a URL or a path (a token holding "/"), not 2026-02-30."""
    return [d for token in statement.split() if "/" not in token for d in ISO_DATE.findall(token) if is_date(d)]
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


def stamp(text: str, today: str) -> str:
    """Stamp a ticked or dropped line that has no close date; a reopened line loses its old stamp. Closed lines stay
    until archive() moves them (phase A spec §3.4)."""
    out = []
    for line in text.split("\n"):
        if line.startswith("- [ ] "):
            line = STAMP.sub("", line).rstrip()
        elif CLOSED.match(line) and not STAMP.search(line):
            line = f"{line.rstrip()} _(closed: ticked {today})_"
        out.append(line)
    return "\n".join(out)


def _block_end(lines: list, i: int) -> int:
    """The index after line i and its notes: the indented lines right under a checklist line (phase A spec §3.5)."""
    j = i + 1
    if lines[i].startswith("- ["):
        while j < len(lines) and lines[j].startswith("  ") and lines[j].strip():
            j += 1
    return j


def archive_path(vault, partition: str, month: str) -> Path:
    return Path(vault) / "wiki" / partition / "now-archive" / f"{month}.md"


def archived(vault, partition: str, first: str, last: str) -> list:
    """The texts of the archive notes for the months first[:7] to last[:7]."""
    folder = Path(vault) / "wiki" / partition / "now-archive"
    return [p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md")) if first[:7] <= p.stem <= last[:7]]


def archive(vault, partition: str, today: str) -> int:
    """Move every closed line and its notes to the archive note of its stamp's month, in page order; return the count.
    The archive is written before the page, so a crash between the two repeats nothing: a line already in its
    archive note is not written twice. The callers hold run.lock."""
    text = read(vault, partition)
    if not text:
        return 0
    lines, keep, moved, i = stamp(text, today).split("\n"), [], {}, 0
    while i < len(lines):
        j = _block_end(lines, i)
        if CLOSED.match(lines[i]):
            moved.setdefault(STAMP.search(lines[i]).group(1)[:7], []).append(lines[i:j])
        else:
            keep += lines[i:j]
        i = j
    for month, blocks in moved.items():
        path = archive_path(vault, partition, month)
        old = path.read_text(encoding="utf-8") if path.is_file() else (
            (Path(vault) / "system" / "templates" / "now_archive.md").read_text(encoding="utf-8")
            .replace("{{date}}", today).replace("{{partition}}", partition).replace("{{month}}", month))
        have = {line.rstrip() for line in old.split("\n")}
        new = [line for block in blocks if block[0].rstrip() not in have for line in block]
        if new:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.tmp")
            tmp.write_text(old.rstrip("\n") + "\n" + "\n".join(new) + "\n", encoding="utf-8")
            os.replace(tmp, path)
    if moved:
        write(vault, partition, "\n".join(keep))
    return sum(len(blocks) for blocks in moved.values())


def note(vault, partition: str, match: str, text: str, today: str) -> str:
    """Under run.lock: add `  - <today>: <text>` after the notes of the one open line whose statement contains
    `match` (any case), so a line keeps its statement short and its history under it (phase A spec §3.5)."""
    text, page, match = " ".join(text.split()), read(vault, partition), match.strip().lower()
    if not match or not text:
        raise ValueError("--match and --text need text")
    if FIELD_KEY.search(text):
        raise ValueError("a note must not hold [rec:: or [due::")
    lines = page.split("\n")
    found = [i for i, line in enumerate(lines) if line.startswith("- [ ] ") and (m := parse(line))
             and match in fields(m.group("statement"))[0].lower()]
    if len(found) != 1:
        raise ValueError(f"{len(found)} open lines match {match!r}; give text that names exactly one")
    line = f"  - {today}: {text}"
    end = _block_end(lines, found[0])
    write(vault, partition, "\n".join(lines[:end] + [line] + lines[end:]))
    return line


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


def _fits(line: str, old: str = "") -> str:
    """line, or ValueError when it is over MAX_LINE and longer than the line it replaces (a long line written before
    the cap may keep its length)."""
    if len(line) > MAX_LINE and len(line) > len(old.rstrip()):
        raise ValueError(f"the line is {len(line)} characters; the limit is {MAX_LINE}: "
                         "keep the statement short and add history with now.py note")
    return line


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
    named = named_dates(statement)
    soon = any(0 <= (date.fromisoformat(d) - start).days <= LONG_DAYS for d in named)
    return (start + timedelta(days=SHORT_DAYS if who or soon else LONG_DAYS)).isoformat()


def add(vault, partition: str, kind: str, statement: str, today: str, who: str = "", evidence: str = "",
        rec: str = "", due: str = "", fit: bool = False) -> tuple:
    """("added"|"exists"|"tightened"|"updated", line). An open line with the same kind and bare statement is not
    added twice: a repeat add moves its clock earlier ("tightened"), sets or replaces rec and sets missing evidence
    ("updated"), writes nothing when nothing is new, and raises ValueError when it would move the clock later.
    fit (machine writers: triage, the watch) cuts a statement that would put the line over MAX_LINE."""
    statement, who, rec = statement.strip(), who.strip(), rec.strip()
    validate(partition, kind, statement, who, evidence, rec, due)
    over = len(render(kind, statement, today, who, evidence, rec, due or default_due(statement, today, who))) - MAX_LINE
    if fit and over > 0:
        statement = statement[:max(len(statement) - over - 1, 40)].rstrip() + "…"
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
        line = _fits(render(kind, bare, m.group("since"), m.group("who") or "", new_evidence, new_rec, new_due), existing)
        lines = text.split("\n")
        lines[[x.rstrip() for x in lines].index(existing.rstrip())] = line
        write(vault, partition, stamp("\n".join(lines), today))
        return "tightened" if new_due != old_due else "updated", line
    line = _fits(render(kind, statement, today, who, evidence, rec, due or default_due(statement, today, who)))
    text = _insert(stamp(text, today), WAITING if kind == "waiting" else NEEDS, line)
    write(vault, partition, text)
    return "added", line


def set_statement(vault, partition: str, match: str, statement: str, today: str) -> str:
    """Under run.lock: the one open line whose statement contains `match` (any case) gets `statement` as its bare
    statement, keeping kind, who, since, evidence, rec and due (#211: rewrite a line instead of appending updates).
    ValueError, writing nothing, on no match, several matches or an invalid statement."""
    statement, text, match = statement.strip(), read(vault, partition), match.strip().lower()
    if not match:
        raise ValueError("--match needs text from the line's statement")
    if FIELD_KEY.search(statement):
        raise ValueError("the new statement holds a [rec::] or [due::] field; set keeps the line's own")
    parsed = [(line, m) for line in open_lines(text) if (m := parse(line))]
    found = [(line, m) for line, m in parsed if match in fields(m.group("statement"))[0].lower()]
    if len(found) != 1:
        raise ValueError(f"{len(found)} open lines match {match!r}; give text that names exactly one")
    old, m = found[0]
    _, rec, due = fields(m.group("statement"))
    if any(o != old and p.group("kind") == m.group("kind") and fields(p.group("statement"))[0] == statement
           for o, p in parsed):
        raise ValueError("another open line of the same kind already has that statement")
    validate(partition, m.group("kind"), statement, m.group("who") or "", m.group("evidence") or "", rec, due)
    line = _fits(render(m.group("kind"), statement, m.group("since"), m.group("who") or "", m.group("evidence") or "",
                        rec, due))
    lines = text.split("\n")
    lines[[x.rstrip() for x in lines].index(old.rstrip())] = line
    write(vault, partition, stamp("\n".join(lines), today))
    return line


def evidence_state(vault, evidence: str, gh: str = "gh"):
    """The close reason ("PR merged", "Work Order done", …), None while still open, or CheckFailed."""
    if PR_URL.match(evidence) or ISSUE_URL.match(evidence):
        what = "pr" if PR_URL.match(evidence) else "issue"
        try:
            out = subprocess.run([gh, what, "view", evidence, "--json", "state", "-q", ".state"],
                                 capture_output=True, text=True, timeout=GH_TIMEOUT)
        except FileNotFoundError:
            raise CheckFailed("gh is not installed")
        except subprocess.TimeoutExpired:
            raise CheckFailed("gh timed out")
        if out.returncode != 0:
            raise CheckFailed(f"gh exit {out.returncode}: {out.stderr.strip()[:200]}")
        state = out.stdout.strip().upper()
        return f"{'PR' if what == 'pr' else 'issue'} {state.lower()}" if state in ("MERGED", "CLOSED") else None
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
        if not m or not m.group("evidence") or (gh_down and (PR_URL.match(m.group("evidence")) or ISSUE_URL.match(m.group("evidence")))):
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
        write(vault, partition, stamp("\n".join(lines), today))
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
            "unreadable": [line for line, m in parsed if not m and (FIELD_KEY.search(line) or SCRIPT_META.search(line))],
            "long": [line for line in lines if len(line) > MAX_LINE and parse(line)],   # set and note split each
            "page_bytes": page_path(vault, partition).stat().st_size if page_path(vault, partition).is_file() else 0}


def overdue(vault, day: str) -> str:
    """The brief's Overdue block (Now clock spec §7), read-only: the open lines of both pages whose due is before day,
    grouped by days over, oldest due first, at most MAX_OVERDUE lines (1 to 7 days over first) and a count of the
    rest, then the count of open lines with no clock; "" when there is neither."""
    groups, clockless, total = ([], [], []), 0, 0
    for partition in PARTITIONS:
        for line in open_lines(read(vault, partition)):
            total += 1
            due = DUE.search(line)
            if not (due and is_date(due.group(1))):
                clockless += 1
                continue
            over = (date.fromisoformat(day) - date.fromisoformat(due.group(1))).days
            if over > 0:
                groups[0 if over <= 7 else 1 if over <= 30 else 2].append((due.group(1), f"- {line.rstrip()[6:]}"))
    # One block per group and one for the count, joined by a blank line, so Markdown keeps each bold label on its own
    # line and the count out of the last bullet.
    # At most MAX_OVERDUE lines, the fewest days over first, then one count line (phase A follow-up).
    blocks, left, over_total = [], MAX_OVERDUE, sum(len(g) for g in groups)
    for heading, lines in zip(OVERDUE_HEADINGS, groups):
        shown = [line for _, line in sorted(lines, key=lambda t: t[0])][:left]
        if shown:
            blocks.append("\n".join([heading] + shown))
            left -= len(shown)
    if over_total > MAX_OVERDUE:
        blocks.append(f"and {over_total - MAX_OVERDUE} more of {over_total} overdue lines; the Now pages hold them all.")
    if clockless:
        # A count prints its denominator (#166).
        blocks.append(f"{clockless} of {total} open line{'s' * (total > 1)} carr{'ies' if clockless == 1 else 'y'} no clock.")
    return "\n\n".join(blocks)


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
    """Once: create a partition's missing Now page from the latest earlier briefing's open objectives. With none it
    writes nothing: brief prep runs this, and a page written just before the brief publishes trips the gate's 60 s check."""
    if partition not in PARTITIONS or page_path(vault, partition).exists():
        return 0
    text = new_page(vault, partition, day)
    items = [(t, s) for t, s in latest_open_objectives(vault, day) if t]
    if not items:
        return 0
    for statement, since in items:
        text = _insert(text, NEEDS, render("owed", statement, since))
    write(vault, partition, text)
    return len(items)
