"""Split and parse note frontmatter (spec §6.15)."""
from dataclasses import dataclass

import yaml

from . import yamlload


@dataclass
class Note:
    data: dict | None
    fm_text: str | None
    body: str
    body_line: int
    error: str | None = None
    error_line: int | None = None


def parse(text: str) -> Note:
    """Parse a note. Never raises on bad input; problems are reported in error/error_line."""
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return Note(None, None, text, 1)
    for i in range(1, len(lines)):
        if lines[i] in ("---", "..."):
            fm_text = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            body_line = i + 2
            try:
                data = yamlload.load(fm_text)
            except RecursionError:
                return Note(None, fm_text, body, body_line, "malformed frontmatter: nested too deeply", 2)
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                if mark is not None:
                    line = mark.line + 3 if "\n" not in fm_text else mark.line + 2
                else:
                    line = 1
                problem = getattr(exc, "problem", None) or str(exc)
                return Note(None, fm_text, body, body_line, f"malformed frontmatter: {problem}", line)
            if data is None:
                data = {}
            if not isinstance(data, dict):
                return Note(None, fm_text, body, body_line, "frontmatter is not a mapping", 2)
            return Note(data, fm_text, body, body_line)
    return Note(None, None, text, 1, "unterminated frontmatter", 1)


def key_line(note: Note, key: str) -> int:
    """Best-effort 1-based line number of a top-level key (2 if not found)."""
    if note.fm_text is None:
        return 1
    for i, line in enumerate(note.fm_text.split("\n")):
        if line.startswith(f"{key}:"):
            return i + 2
    return 2
