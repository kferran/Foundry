"""Digest follow-ups become proposed Now lines (#476, digest follow-ups spec §3). Intake queues each digest it archives;
this step, under run.lock, adds each `## Follow-ups` bullet as an owed line tagged [via:: digest], with the archived
digest as evidence, unless an open line or one closed lately already covers it. No model call: a script copies text a
session wrote, as triage copies a mail subject, and nowmod.add redacts it and holds the cap and the walls."""
import os
import re
from datetime import date, timedelta
from pathlib import Path

from . import frontmatter, held, now as nowmod

QUEUE = Path("system") / "logs" / "followups_queue.txt"
PER_DIGEST, PER_DAY, CLOSED_DAYS = 5, 10, 14   # spec §3.5, §3.6
MIN_CONTAINED, MIN_SHARED, SHARED_SHARE = 12, 3, 0.6
SECTION = re.compile(r"^#{1,6}\s*follow[- ]?ups?\b", re.IGNORECASE)
BULLET = re.compile(r"^(?:[-*]|\d+\.)\s+(.+)")   # top level only: an indented line is a continuation
NOTHING = re.compile(r"(?:none|nothing|n/a)\.?", re.IGNORECASE)
ARCHIVED = re.compile(r"raw/(?:work|personal|shared)/archive/[^/\s]+\.md")


def queue(vault, rels: list) -> None:
    """Append each archived digest's vault path, one a line; the caller holds intake.lock."""
    path = Path(vault) / QUEUE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("".join(f"{rel}\n" for rel in rels))


def bullets(text: str) -> list:
    """A session digest's Follow-ups bullets, an open checkbox stripped; a done ([x]) or empty one is left out."""
    note = frontmatter.parse(text)
    if not isinstance(note.data, dict) or note.data.get("type") != "session_digest":
        return []
    out, inside = [], False
    for line in note.body.splitlines():
        if line.startswith("#"):
            inside = bool(SECTION.match(line))
        elif inside and (m := BULLET.match(line)):
            item = " ".join(m.group(1).split())
            if item[:4] in ("[x] ", "[X] "):
                continue
            item = item[4:] if item.startswith("[ ] ") else item
            if not NOTHING.fullmatch(item):
                out.append(item)
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", nowmod.WIKILINK.sub(r"\1", text).lower()).strip()


def _words(text: str) -> set:
    return {w[:-1] if w.endswith("s") else w for w in text.split() if len(w) >= 4 and w.isalpha()}


def _candidates(vault, page: str, today: str) -> list:
    """(normalized statement, evidence, since) of each open line, and each closed in the last CLOSED_DAYS, on the page
    and in its archive months."""
    cutoff = (date.fromisoformat(today) - timedelta(days=CLOSED_DAYS)).isoformat()
    out = []
    for text in [nowmod.read(vault, page), *nowmod.archived(vault, page, cutoff, today)]:
        for line in text.splitlines():
            m, stamp = nowmod.LINE.match(line.rstrip()), nowmod.STAMP.search(line)
            if m and (not stamp or stamp.group(1) >= cutoff):
                out.append((_norm(nowmod.fields(m["statement"])[0]), m["evidence"] or "", m["since"]))
    return out


def _matches(bullet: str, cands: list, created: str) -> bool:
    """Spec §3.5: equal or contained text, the line's own evidence named in the bullet, or enough shared words with a
    line from the session's own day. A miss costs the owner one [-]; a false match loses a follow-up."""
    b, day_before = _norm(bullet), (date.fromisoformat(created) - timedelta(days=1)).isoformat()
    for text, evidence, since in cands:
        short, long_ = sorted((b, text), key=len)
        if b == text or (len(short) >= MIN_CONTAINED and short in long_):
            return True
        if evidence and not evidence.startswith("raw/") and evidence in bullet:
            return True
        x, y = _words(b), _words(text)
        shared = x & y
        if since >= day_before and len(shared) >= MIN_SHARED and len(shared) >= SHARED_SHARE * min(len(x), len(y)):
            return True
    return False


def _today(vault, page: str, today: str) -> int:
    """The page's digest lines from today, open or closed and not yet archived."""
    return sum(bool((m := nowmod.LINE.match(line.rstrip())) and m["since"] == today
                    and nowmod.via(m["statement"]) == "digest") for line in nowmod.read(vault, page).splitlines())


def _propose(vault, rel: str, text: str, today: str, alert) -> bool:
    """Add rel's bullets to its partition's page; False when the page's day cap stops it before its last bullet."""
    items, name, page = bullets(text), Path(rel).stem, held.page(rel.split("/")[1])
    created = str((frontmatter.parse(text).data or {}).get("created_at", ""))[:10]
    created = created if nowmod.is_date(created) else today
    cands, count = _candidates(vault, page, today), _today(vault, page, today)
    for item in items[:PER_DIGEST]:
        if _matches(item, cands, created):
            continue
        if count >= PER_DAY:
            return False
        try:
            status, _ = nowmod.add(vault, page, "owed", item, today, evidence=rel, fit=True, via="digest")
        except ValueError as exc:
            alert(f"digest {name}: a follow-up was skipped: {nowmod.refusal(exc)}")
            continue
        count += status == "added"
        cands.append((_norm(item), rel, today))
    if len(items) > PER_DIGEST:
        alert(f"digest {name}: {len(items)} follow-ups, {PER_DIGEST} proposed")
    return True


def step(vault, today: str, alert) -> None:
    """Intake's follow-ups step, under run.lock (spec §3.2): each queued digest leaves the queue once its bullets are
    handled; one the day cap stops waits for the next day, and §3.5 skips what it already added."""
    path = Path(vault) / QUEUE
    if not path.is_file():
        return
    left = []
    for rel in path.read_text(encoding="utf-8").split():
        if not ARCHIVED.fullmatch(rel):
            alert("a follow-ups queue line is not an archived digest")
            continue
        try:
            text = (Path(vault) / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            alert(f"follow-ups of {rel} skipped: {exc.__class__.__name__}")
            continue
        if not _propose(vault, rel, text, today, alert):
            left.append(rel)
    if not left:
        path.unlink()
        return
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("".join(f"{rel}\n" for rel in left), encoding="utf-8")
    os.replace(tmp, path)
