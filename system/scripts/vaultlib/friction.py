"""Friction notes new since the last brief, plus a count (one-screen brief spec §3.3).

"Listed before" is read from the briefings themselves, never from a ledger: a note was listed when its [[Name]]
appears under the **Friction** part (or the old **Friction notes** bullet) of any briefing dated before today.
"""
import re
import sqlite3

from . import briefings
from .index import Index
from .now import WIKILINK

PART = re.compile(r"^(\s*)-\s+\*\*Friction( notes)?\*\*")
SIBLING = re.compile(r"^(\s*)-\s+\*\*")


def _friction_links(text: str) -> set:
    out, indent = set(), None
    for line in text.splitlines():
        if indent is None:
            match = PART.match(line)
            if match:
                indent = len(match.group(1))
                out.update(WIKILINK.findall(line))
            continue
        sibling = SIBLING.match(line)
        if line.startswith("#") or (sibling and len(sibling.group(1)) <= indent):
            indent = None
            match = PART.match(line)
            if match:  # a second Friction part in the same briefing
                indent = len(match.group(1))
                out.update(WIKILINK.findall(line))
            continue
        out.update(WIKILINK.findall(line))
    return {name.strip() for name in out if name.strip()}


def listed_before(vault, day: str) -> set:
    """The friction note names every briefing dated before day has printed."""
    names = set()
    for _, path in briefings.earlier_briefings(vault, day, lookback=None):
        try:
            names |= _friction_links(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return names


def render(vault, day: str) -> str:
    """One `- [[Name]]` line per active flagged note not listed before, newest compiled_at first, then the count."""
    idx = Index(vault)
    idx.refresh(timeout=60)
    conn = sqlite3.connect(idx.db_path)
    try:
        rows = conn.execute("SELECT path FROM v_concept WHERE is_friction = 1 ORDER BY compiled_at DESC, path").fetchall()
    finally:
        conn.close()
    seen = listed_before(vault, day)
    stems = [path.rsplit("/", 1)[-1][:-3] for (path,) in rows]
    lines = [f"- [[{stem}]]" for stem in stems if stem not in seen]
    count = len(stems)
    lines.append(f"{count} open friction note{'' if count == 1 else 's'}")
    return "\n".join(lines) + "\n"
