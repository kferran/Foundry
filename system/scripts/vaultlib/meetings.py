"""Meetings: parse Gemini Docs and dropped transcripts into meeting notes (meetings spec §2.3)."""
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from . import frontmatter, redact as redactmod

HEADING = re.compile(r"^(#{1,6})\s+\**(.*?)\**\s*$")  # real Docs bold every heading: "### **Summary**"
DOC_TITLE = re.compile(r"^(.*) - (\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) \S+ - Notes by Gemini$")
IMPROMPTU = re.compile(r"^(Meeting started) (\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) \S+ - Notes by Gemini$")
MAILTO = re.compile(r"\[([^\]]+)\]\(mailto:[^)]*\)")
ACTION = re.compile(r"^\s*[-*]\s+(?:\[ \]\s+)?\\?\[(.+?)\\?\]\s*(.*)$")
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}$")
ENDED = re.compile(r"^#{1,6}\s+\**Transcription ended after\b")
BOLD_TURN = re.compile(r"^\*\*([^*\n]{1,80}?):\*\*\s*(.*)$")
NAME_TURN = re.compile(r"^([A-Z][\w.'’-]*(?: [A-Z][\w.'’-]*){0,3}):\s+(.+)$")
CUE_TIME = re.compile(r"^(?:(\d+):)?(\d{2}):(\d{2})[.,]\d{3}\s+-->")
VOICE = re.compile(r"^<v(?:\.[^ >]*)?\s+([^>]+)>(.*?)(?:</v>)?$")
TAG = re.compile(r"<[^>]+>")
STARTS = [  # (pattern, zone): a start in a drop's file name
    (re.compile(r"GMT(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}"), timezone.utc),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})"), None),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2})(\d{2})(?!\d)"), None),
]
DRIVE_URL = re.compile(r"https?://(?:drive|docs)\.google\.com/[^\s)\]>]*")
EMPTY_LINK = re.compile(r"\[([^\[\]\n]*)\]\(\s*\)")
CONTROL = re.compile(r"[\x00-\x1f\x7f\x85  ]+")
SECTIONS = {"summary": "summary", "decisions": "decisions", "next steps": "actions", "details": "details"}
HEADING_EVERY = 300  # seconds of cue offsets between ### headings in a plain transcript
SLUG_MAX = 60


class ParseError(ValueError):
    pass


@dataclass
class Meeting:
    title: str
    start: datetime
    source: str
    source_name: str
    attendees: list = field(default_factory=list)
    summary: str = ""
    decisions: str = ""
    actions: list = field(default_factory=list)  # (owners, "Title: text")
    details: str = ""
    turns: list = field(default_factory=list)  # (HH:MM:SS heading, speaker or "", text)
    complete: bool = True


# -- parsing -------------------------------------------------------------
def _speakers(turns) -> list:
    out = []
    for _, speaker, _ in turns:
        if speaker and speaker not in out:
            out.append(speaker)
    return out


def _is_gemini(text: str) -> bool:
    heads = [m.group(2) for m in map(HEADING.match, text.splitlines()) if m]
    return any(h.lower() == "summary" for h in heads) and any(h.endswith(" - Transcript") for h in heads)


def _gemini_body(text: str):
    """(attendees, sections, turns, complete) from a Gemini Doc's text."""
    lines = text.replace("\r\n", "\n").split("\n")
    sections = {k: [] for k in SECTIONS.values()}
    current, invited, turns, complete, in_transcript, heading = None, [], [], False, False, "00:00:00"
    for line in lines:
        match = HEADING.match(line)
        if in_transcript:
            if ENDED.match(line):
                complete = True
                break
            if match and TIMESTAMP.match(match.group(2)):
                heading = match.group(2)
                continue
            turn = BOLD_TURN.match(line.strip())
            if turn:
                turns.append((heading, turn.group(1).strip(), turn.group(2).strip()))
            elif line.strip() and turns:
                h, speaker, said = turns[-1]
                turns[-1] = (h, speaker, f"{said} {line.strip()}".strip())
            elif line.strip():
                turns.append((heading, "", line.strip()))
            continue
        if match:
            title = match.group(2)
            level = len(match.group(1))
            if title.endswith(" - Transcript"):
                in_transcript, current = True, None
            elif level >= 3 and title.lower() in SECTIONS:
                current = SECTIONS[title.lower()]
            elif level == 1 or not current:
                current = None
            else:  # a topic heading inside a section (real Docs group Decisions under "## **Topic**")
                sections[current].append(f"**{title}**")
            continue
        if line.startswith("Invited "):
            invited = MAILTO.findall(line)
            continue
        if current:
            sections[current].append(line)
    actions = []
    for line in sections["actions"]:
        owned = ACTION.match(line)
        if owned:
            actions.append(([o.strip() for o in owned.group(1).split(",") if o.strip()], owned.group(2).strip()))
        elif BULLET.match(line):
            actions.append(([], BULLET.match(line).group(1).strip()))
    text_of = {k: "\n".join(v).strip() for k, v in sections.items()}
    return invited or _speakers(turns), text_of, actions, turns, complete


def parse_gdoc(text: str, tz) -> Meeting:
    """A fetched raw/meetings/<id>.gdoc.md: the extractor's header, then the Doc text."""
    note = frontmatter.parse(text)
    head = note.data or {}
    doc_id, doc_title = head.get("doc_id"), head.get("title")
    if not isinstance(doc_id, str) or not doc_id or not isinstance(doc_title, str):
        raise ParseError("the header has no doc_id or title")
    match = DOC_TITLE.match(doc_title) or IMPROMPTU.match(doc_title)
    if not match:
        raise ParseError("the Doc title carries no start date and time")
    try:
        start = datetime(*map(int, match.groups()[1:]), tzinfo=tz)
    except ValueError:
        raise ParseError("the Doc title carries an invalid start date or time")
    attendees, sections, actions, turns, complete = _gemini_body(note.body)
    return Meeting(match.group(1).strip(), start, f"gdoc:{doc_id}", doc_title, attendees, sections["summary"],
                   sections["decisions"], actions, sections["details"], turns, complete)


def _offset(match) -> int:
    hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _speaker_line(line: str):
    voice = VOICE.match(line)
    if voice:
        return voice.group(1).strip(), TAG.sub("", voice.group(2)).strip()
    line = TAG.sub("", line).strip()
    named = BOLD_TURN.match(line) or NAME_TURN.match(line)
    return (named.group(1).strip(), named.group(2).strip()) if named else ("", line)


def _cues(text: str) -> list:
    """(offset seconds, speaker, text) for each .vtt or .srt cue; cue IDs and NOTE blocks are skipped."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        timing = next((i for i, line in enumerate(lines) if CUE_TIME.match(line.strip())), None)
        if timing is None:
            continue
        said = [_speaker_line(line.strip()) for line in lines[timing + 1:] if line.strip()]
        if not said:
            continue
        speaker = next((s for s, _ in said if s), "")
        cues.append((_offset(CUE_TIME.match(lines[timing].strip())), speaker, " ".join(t for _, t in said if t)))
    return cues


def _cue_turns(cues) -> list:
    turns, last = [], None
    for offset, speaker, said in cues:
        if last is None or offset - last >= HEADING_EVERY:
            last = offset
        turns.append((_hms(last), speaker, said))
    return turns


def _line_turns(text: str) -> list:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    said = [_speaker_line(line) for line in lines]
    if not any(speaker for speaker, _ in said):
        return [("00:00:00", "", "\n".join(lines))] if lines else []
    return [("00:00:00", speaker, line) for speaker, line in said]


def drop_title(name: str) -> str:
    stem = re.sub(r"(?i)(_recording)?(\.transcript)?$", "", Path(name).stem)
    for pattern, _ in STARTS:
        stem = pattern.sub(" ", stem, count=1)
    title = " ".join(stem.replace("_", " ").split()).strip(" -_")
    return title or "Meeting"


def drop_start(name: str, commit_iso, mtime: float, tz) -> datetime:
    """The start from the file name; else the drop's commit time; else its modification time."""
    for pattern, zone in STARTS:
        match = pattern.search(Path(name).stem)
        if match:
            try:
                return datetime(*map(int, match.groups()), tzinfo=zone or tz).astimezone(tz)
            except ValueError:
                continue
    if commit_iso:
        return datetime.fromisoformat(commit_iso).astimezone(tz)
    return datetime.fromtimestamp(mtime, tz)


def _decode(data: bytes) -> str:
    """UTF-8 (a byte-order mark is dropped), or UTF-16 with its byte-order mark, as Windows tools save it (#41).
    Any other text holds NULs once decoded and is a ParseError, so it is quarantined with a reason."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    text = data.decode("utf-8", errors="replace").lstrip("\ufeff")
    if "\x00" in text:
        raise ParseError("not UTF-8 text (save the transcript as UTF-8)")
    return text


def parse_drop(name: str, data: bytes, tz, start: datetime) -> Meeting:
    """A dropped transcript (.vtt, .srt, .txt or .md); a .md with the Gemini structure is a Gemini Doc."""
    text = _decode(data)
    suffix = Path(name).suffix.lower()
    meeting = Meeting(drop_title(name), start, "", name)
    if suffix == ".md" and _is_gemini(text):
        attendees, sections, actions, turns, complete = _gemini_body(text)
        return replace(meeting, attendees=attendees, summary=sections["summary"], decisions=sections["decisions"],
                       actions=actions, details=sections["details"], turns=turns, complete=complete)
    if suffix in (".vtt", ".srt"):
        turns = _cue_turns(_cues(text))
    elif suffix in (".txt", ".md"):
        turns = _line_turns(text)
    else:
        raise ParseError(f"not a transcript file type: {suffix or name}")
    if not turns:  # an empty file (a new note not yet filled in) is not a meeting
        raise ParseError("the drop has no transcript text")
    return replace(meeting, attendees=_speakers(turns), turns=turns)


# -- making text safe for the vault ----------------------------------------
def _strip_drive(text: str) -> str:
    return EMPTY_LINK.sub(r"\1", DRIVE_URL.sub("", text))


def _escape(text: str) -> str:
    """Every "[" that touches another "[" is escaped (so "[[[x]]" leaves no "[[" behind), and every "](" too."""
    return re.sub(r"\[(?=\[)|(?<=\[)\[", r"\\[", text).replace("](", "]\\(")


def safe(text: str) -> str:
    """Participant text can never become a link: Drive links removed, wiki and Markdown links escaped."""
    return _escape(_strip_drive(text))


def _clean(text: str) -> str:
    """Drive links stripped, then redacted, then escaped: a redaction placeholder can never open a link."""
    return _escape(redactmod.redact(_strip_drive(text))[0])


def scrub(m: Meeting) -> Meeting:
    """Every participant text field cleaned, and the title and source name redacted. Start and source stay."""
    return replace(m, title=redactmod.redact(m.title)[0], source_name=redactmod.redact(m.source_name)[0],
                   attendees=[_clean(a) for a in m.attendees], summary=_clean(m.summary),
                   decisions=_clean(m.decisions), details=_clean(m.details),
                   actions=[([_clean(o) for o in owners], _clean(said)) for owners, said in m.actions],
                   turns=[(h, _clean(s), _clean(t)) for h, s, t in m.turns])


# -- names and rendering -----------------------------------------------------
def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:SLUG_MAX].strip("-") or "meeting"


def note_name(m: Meeting) -> str:
    return f"{m.start:%Y-%m-%d-%H%M}-{slug(m.title)}"


def _one_line(text: str) -> str:
    return " ".join(CONTROL.sub(" ", text).split())


def _q(value: str) -> str:
    return json.dumps(_one_line(value), ensure_ascii=False)


def render_meeting(m: Meeting, name: str, partition: str) -> str:
    owners = lambda os: f"[{', '.join(_one_line(o) for o in os)}] " if os else ""  # noqa: E731
    actions = "\n".join(f"- [ ] {owners(os)}{_one_line(said)}" for os, said in m.actions)
    return (f"---\ntype: meeting\ntitle: {_q(m.title)}\ndate: \"{m.start:%Y-%m-%d}\"\n"
            f"start: \"{m.start.isoformat()}\"\npartition: {partition}\n"
            f"attendees: [{', '.join(_q(a) for a in m.attendees)}]\nsource: {_q(m.source)}\n"
            f"source_name: {_q(m.source_name)}\ntranscript: \"[[{name}.transcript]]\"\nstatus: canonical\n---\n"
            f"# {_one_line(safe(m.title))}\n\n## Summary\n{m.summary or 'None.'}\n\n"
            f"## Decisions\n{m.decisions or 'None.'}\n\n## Action items\n{actions or 'None.'}\n\n"
            f"## Details\n{m.details or 'None.'}\n")


def render_transcript(m: Meeting, name: str, partition: str) -> str:
    out, heading = [], None
    for h, speaker, said in m.turns:
        if h != heading:
            out.append(f"\n### {h}")
            heading = h
        out.append(f"**{_one_line(speaker)}:** {said}" if speaker else said)
    return (f"---\ntype: meeting_transcript\nmeeting: \"[[{name}]]\"\npartition: {partition}\n"
            f"source: {_q(m.source)}\ncomplete: {'true' if m.complete else 'false'}\n---\n"
            f"# {_one_line(safe(m.title))}: transcript\n" + "\n".join(out) + "\n")


def render_input(m: Meeting, name: str, partition: str, created_at: datetime) -> str:
    return (f"---\ntype: meeting_input\nmeeting: \"[[{name}]]\"\npartition: {partition}\n"
            f"created_at: \"{created_at.isoformat(timespec='seconds')}\"\n---\n"
            f"# Meeting: {_one_line(safe(m.title))}\n\n## Summary\n{m.summary or 'None.'}\n\n"
            f"## Decisions\n{m.decisions or 'None.'}\n\n## Details\n{m.details or 'None.'}\n")
