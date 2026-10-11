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
LOOKBACK_DAYS = briefings.LOOKBACK_DAYS
FAILURE_ALERT = 3
GH_TIMEOUT = 10
WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]")
LINE = re.compile(r"^- \[(?P<mark>.)\] (?P<kind>owed|waiting|draft): (?P<statement>.+) "
                  r"\((?:(?P<who>[^(),]+), )?since (?P<since>\d{4}-\d{2}-\d{2})(?:, (?P<evidence>[^\s(),]+))?\)"
                  r"(?: _\(closed: .*\)_)?$")
CLOSED = re.compile(r"^- \[[xX-]\] ")
STAMP = re.compile(r"_\(closed: .*?(\d{4}-\d{2}-\d{2})\)_\s*$")
PR_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+$")
ORDER_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
ORDER_CLOSED = ("done", "failed", "cancelled")
SINCE = re.compile(r"\s*_\(open since (\d{4}-\d{2}-\d{2})(?:, \d+ days?)?\)_")


class CheckFailed(Exception):
    pass


def page_path(vault, partition: str) -> Path:
    return Path(vault) / "wiki" / partition / "Now.md"


def new_page(vault, partition: str, today: str) -> str:
    template = (Path(vault) / "system" / "templates" / "now.md").read_text(encoding="utf-8")
    return template.replace("{{date}}", today).replace("{{partition}}", partition)


def render(kind: str, statement: str, since: str, who: str = "", evidence: str = "") -> str:
    meta = (f"{who}, " if who else "") + f"since {since}" + (f", {evidence}" if evidence else "")
    return f"- [ ] {kind}: {statement} ({meta})"


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


def validate(partition: str, kind: str, statement: str, who: str, evidence: str) -> None:
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


def add(vault, partition: str, kind: str, statement: str, today: str, who: str = "", evidence: str = "") -> tuple:
    """("added"|"exists", line). The same kind and statement already open is not added twice."""
    statement, who = statement.strip(), who.strip()
    validate(partition, kind, statement, who, evidence)
    text = read(vault, partition) or new_page(vault, partition, today)
    for existing in open_lines(text):
        m = LINE.match(existing)
        if m and m.group("kind") == kind and m.group("statement") == statement:
            return "exists", existing
    line = render(kind, statement, today, who, evidence)
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


def check(vault, today: str, alert, gh: str = "gh") -> int:
    """Close each open line whose evidence shows it is finished. Returns the lines closed.

    The page is written only when a line closes, and from a fresh read, so a tick made while gh ran is kept.
    The first failed pull-request check skips the others until the next tick."""
    closed, gh_down = 0, False
    for partition in PARTITIONS:
        found = {}
        for line in open_lines(read(vault, partition)):
            m = LINE.match(line)
            if not m or not m.group("evidence") or (gh_down and PR_URL.match(m.group("evidence"))):
                continue
            try:
                how = evidence_state(vault, m.group("evidence"), gh)
            except CheckFailed as exc:
                _failed(vault, today, line, str(exc), alert)
                gh_down = True
                continue
            if how:
                found[line] = how
        if not found:
            continue
        lines = read(vault, partition).split("\n")
        for i, line in enumerate(lines):
            if line in found:
                lines[i] = f"- [x]{line[5:]} _(closed: {found[line]} {today})_"
                closed += 1
        write(vault, partition, stamp_and_prune("\n".join(lines), today))
    return closed


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
