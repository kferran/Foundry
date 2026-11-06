"""The market page (market watch spec §3.4, §3.5; plan 3, rulings 3-5): reading it, the brief's one Market line, and
what happens after a rating run publishes it (Slack threats, proposed changes as owed Now lines, the inbox copy).
Only this script posts or writes the Now page; the rating session never does."""
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from vaultlib.api import alert, config, frontmatter, load, save

from .unit import NOTIFY_LIMIT

SECTIONS = {"Threats": "threat", "Openings": "opening", "Watch": "watch", "News": "news"}
TOP_ORDER = ("threat", "opening", "news", "watch")
ITEM = re.compile(r"^- \*\*(?P<entry>[^*]+)\*\*: (?P<text>.*?)\s*\[[^\]]*\]\((?P<link>[^)\s]+)\)\s*$")
PROPOSED = re.compile(r"^- \[\[(?P<note>[^\]|]+)(?:\|[^\]]*)?\]\]: (?P<change>.*?)\s*(?:\((?P<link>[^)\s]+)\))?\s*$")
KEEP_DAYS = 14
HEADLINE = 80


@dataclass
class Entry:
    entry: str
    text: str
    link: str

    @property
    def headline(self) -> str:
        return self.text.split(". ", 1)[0].rstrip(".")[:HEADLINE]


@dataclass
class Page:
    date: str
    partition: str
    items: dict = field(default_factory=lambda: {k: [] for k in SECTIONS.values()})
    proposed: list = field(default_factory=list)


def path_for(vault: Path, day: str) -> Path:
    return vault / "briefings" / "market" / f"{day}.md"


def read(path: Path):
    try:
        note = frontmatter.parse(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    data = note.data or {}
    page = Page(str(data.get("date") or ""), str(data.get("partition") or "work"))
    section = None
    for line in note.body.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            section = SECTIONS.get(name, "proposed" if name == "Proposed changes" else None)
            continue
        if section == "proposed":
            m = PROPOSED.match(line)
            if m:
                page.proposed.append((m["note"].strip(), m["change"].strip(), m["link"] or ""))
        elif section:
            m = ITEM.match(line)
            if m:
                page.items[section].append(Entry(m["entry"].strip(), m["text"].strip(), m["link"]))
    return page


def line(vault: Path, day: str) -> str:
    page = read(path_for(vault, day))
    if page is not None:
        n = sum(len(v) for v in page.items.values())
        if not n:
            return "No market changes"
        kind = next(k for k in TOP_ORDER if page.items[k])
        return f"Market: {n} changes, top: {page.items[kind][0].headline} ({kind}) [[briefings/market/{day}|market]]"
    status = load(vault / "system" / "logs" / "market_run.json", {})
    status = status if isinstance(status, dict) and status.get("date") == day else {}
    s = status.get("status")
    if s == "none":
        return "No market changes"
    if s == "running":
        return "Market: unavailable (still running)"
    if s in ("timeout", "busy", "rejected", "failed"):
        return f"Market: unavailable ({s})"
    return "Market: unavailable (no run)"


def _recent(entries, day: str) -> dict:
    cutoff = (date.fromisoformat(day) - timedelta(days=KEEP_DAYS)).isoformat()
    return {k: v for k, v in (entries or {}).items() if isinstance(v, str) and v >= cutoff} \
        if isinstance(entries, dict) else {}


def _candidate_links(vault: Path, day: str) -> list:
    out = []
    try:
        with open(vault / "raw" / "market" / day / "candidates.jsonl", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("link"), str):
                    out.append(row["link"])
    except OSError:
        pass
    return out


def after_publish(vault: Path, day: str, run=subprocess.run) -> None:
    page = read(path_for(vault, day))
    if page is None:
        return
    cfg = config(vault)
    groups = {str(e.get("name")): str(e.get("group") or "") for e in cfg.get("market_watch") or [] if isinstance(e, dict)}
    alert_groups = [str(g) for g in cfg.get("market_alert_groups") or []]
    partition = str(cfg.get("market_partition") or "work")
    state_path = vault / "system" / "logs" / "market_state.json"
    state = load(state_path, {})
    state = state if isinstance(state, dict) else {}
    posted, proposed = _recent(state.get("posted"), day), _recent(state.get("proposed"), day)
    clock = datetime.now().strftime("%H:%M:%S")
    # The page is model output from web text: a link posts only when the day's candidates hold it.
    known = set(_candidate_links(vault, day))
    for item in page.items["threat"]:
        group = groups.get(item.entry)
        if (group is None or item.link not in known or item.link in posted
                or (alert_groups and group not in alert_groups)):
            continue
        alert(vault, day, clock, "market", f"Market threat: {item.entry}: {item.headline} {item.link}")
        posted[item.link] = day
    state.update(posted=posted)
    save(state_path, state)  # before the Now step, so a failure there never reposts a threat
    if page.partition != partition:  # the partition wall holds whatever the page says
        alert(vault, day, clock, "market_source", f"market page {day} says partition {page.partition}, not "
              f"market_partition {partition}; its Now lines and inbox copy are skipped", key=f"partition {day}")
        return
    deadline = time.monotonic() + NOTIFY_LIMIT
    for note, change, _link in page.proposed:
        statement = f"Review a proposed change to {note}: {change}"
        left = deadline - time.monotonic()
        if statement in proposed or left <= 0:
            continue
        try:
            rc = run(["system/scripts/now.py", "add", "--partition", partition, "--kind", "owed", "--statement",
                      statement, "--rec", f"review: proposed by the market page of {day}"],
                     cwd=vault, timeout=left).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        except OSError as exc:
            rc = type(exc).__name__
        if rc == 0:
            proposed[statement] = day
        else:
            alert(vault, day, clock, "market_source",
                  f"now.py add failed ({rc}) for a proposed change to {note}; the next run tries again")
    state.update(proposed=proposed)
    save(state_path, state)
    inbox = vault / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path_for(vault, day), inbox / f"market-{day}.md")
