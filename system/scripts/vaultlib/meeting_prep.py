"""Before today's meetings (one-screen brief spec §3.6): for each calendar event that names an entity note, the
entity's open Now lines and open meeting actions, at most five entities and five lines each. No model reads a note.
"""
import re
import sqlite3
from pathlib import Path

from . import frontmatter, meetings, now
from .index import Index

MAX_ENTITIES = 5
MAX_LINES = 5
WORD = re.compile(r"[\w.]+")
KIND_ORDER = {"owed": 0, "waiting": 1, "draft": 2}


def _words(text: str) -> list:
    return [w for w in WORD.findall(text.lower()) if w.strip(".")]


def matches(title: str, name: str) -> bool:
    """True when name's words occur as a contiguous run in the event title's words (case-folded, whole words)."""
    needle, hay = _words(name), _words(title)
    if not needle or len(needle) > len(hay):
        return False
    return any(hay[i:i + len(needle)] == needle for i in range(len(hay) - len(needle) + 1))


def _config(vault) -> dict:
    try:
        return frontmatter.parse((Path(vault) / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return {}


def entities(vault, conn, partitions) -> list:
    """(path, title, aliases) for each active note under wiki/<p>/entities/ with <p> in partitions."""
    out = []
    rows = conn.execute("SELECT path, title, partition FROM notes WHERE active = 1 AND path LIKE 'wiki/%/entities/%' "
                        "ORDER BY path").fetchall()
    for path, title, partition in rows:
        if partition not in partitions:
            continue
        try:
            data = frontmatter.parse((Path(vault) / path).read_text(encoding="utf-8")).data or {}
        except (OSError, UnicodeDecodeError):
            data = {}
        aliases = [str(a) for a in data.get("aliases", []) if str(a).strip()] if isinstance(data.get("aliases"), list) else []
        out.append((path, title, aliases))
    return out


def _events(calendar: Path) -> list:
    """(start_time, title) rows of calendar.tsv in start order."""
    try:
        text = calendar.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows = []
    for line in text.splitlines():
        cells = line.split("\t")
        if len(cells) >= 5 and cells[4].strip():
            rows.append((cells[0], cells[1], cells[4].strip()))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [(start, title) for _, start, title in rows]


def _now_lines(text: str, title: str) -> list:
    found = []
    for line in now.open_lines(text):
        match = now.LINE.match(line)
        if not match:
            continue
        who = (match.group("who") or "").strip()
        if who.casefold() == title.casefold() or matches(match.group("statement"), title):
            found.append((KIND_ORDER.get(match.group("kind"), 9), f"- {line[6:]}"))
    return [line for _, line in sorted(found, key=lambda x: x[0])]


def _actions(vault, conn, title: str) -> list:
    out = []
    for path, in conn.execute("SELECT path FROM v_meeting ORDER BY date DESC, path DESC").fetchall():
        try:
            body = frontmatter.parse((Path(vault) / path).read_text(encoding="utf-8")).body
        except (OSError, UnicodeDecodeError):
            continue
        for owners, _, text in meetings.open_actions(body):
            if any(o.casefold() == title.casefold() for o in owners):
                out.append(f"- action: {text} ([[{Path(path).stem}]])")
    return out


def render(vault, day: str, calendar) -> str:
    """The Before today's meetings blocks for the events in calendar (a Path), or "" when no event names an entity."""
    config = _config(vault)
    partition = str(config.get("default_partition") or "personal")
    events = _events(Path(calendar))
    if not events:
        return ""
    idx = Index(vault)
    idx.refresh(timeout=60)
    conn = sqlite3.connect(idx.db_path)
    try:
        known = entities(vault, conn, (partition, "shared"))
        chosen = []  # (path, title, start, event title), first five distinct in calendar order
        for start, event in events:
            for path, title, aliases in known:
                if any(p == path for p, *_ in chosen):
                    continue
                if any(matches(event, name) for name in (title, *aliases)):
                    chosen.append((path, title, start, event))
            if len(chosen) >= MAX_ENTITIES:
                chosen = chosen[:MAX_ENTITIES]
                break
        if not chosen:
            return ""
        page = now.read(vault, partition) if partition in now.PARTITIONS else ""
        blocks = []
        for _, title, start, event in chosen:
            lines = _now_lines(page, title) + _actions(vault, conn, title)
            heading = f"### [[{title}]] ({start or 'all day'} {event})"
            blocks.append("\n".join([heading, *lines[:MAX_LINES]]) + "\n")
    finally:
        conn.close()
    return "\n".join(blocks)
