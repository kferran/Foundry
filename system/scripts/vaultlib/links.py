"""Wikilink, markdown-link and tag extraction and resolution (spec §6.16)."""
import posixpath
import re
from dataclasses import dataclass

WIKI = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
MD = re.compile(r"(?<![!\]])\[[^\[\]\n]*\]\(([^()\s]+)\)")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
TAG = re.compile(r"(?<![\w/&#(\]])#([A-Za-z][\w/-]*)")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE = re.compile(r"`[^`\n]*`")


@dataclass
class Link:
    target_raw: str
    target: str | None
    line: int
    kind: str


def code_free_lines(body: str, body_line: int):
    """Yield (line_number, text) with fenced blocks dropped and inline code removed."""
    fence = None
    for i, line in enumerate(body.split("\n")):
        match = FENCE.match(line)
        if match:
            if fence is None:
                fence = match.group(1)
            elif match.group(1) == fence:
                fence = None
            continue
        if fence is None:
            yield body_line + i, INLINE.sub("", line)


def wiki_target(raw: str) -> str | None:
    """'A|alias' -> 'A'; 'A#h' -> 'A'; '#h' -> None (self link)."""
    name = raw.split("|", 1)[0].split("#", 1)[0].strip()
    return name or None


def extract(body: str, body_line: int):
    """Return (links, tags) from a note body, ignoring code."""
    found, tags = [], set()
    for lineno, line in code_free_lines(body, body_line):
        for m in WIKI.finditer(line):
            found.append(Link(m.group(2), wiki_target(m.group(2)), lineno, "embed" if m.group(1) else "link"))
        for m in MD.finditer(line):
            href = m.group(1)
            if SCHEME.match(href) or href.startswith("#"):
                continue
            found.append(Link(href, href.split("#", 1)[0] or None, lineno, "md"))
        # Remove link syntax before matching tags to prevent tag leakage
        line_for_tags = MD.sub(" ", WIKI.sub(" ", line))
        for m in TAG.finditer(line_for_tags):
            tags.add(m.group(1))
    return found, tags


class Resolver:
    """Resolve link targets against the set of vault files, Obsidian-style."""

    def __init__(self, files, name_exclude=()):
        """name_exclude: path prefixes still reachable by explicit path but never by bare name."""
        self.by_lower = {}
        self.by_name = {}
        for path in files:
            self.by_lower.setdefault(path.lower(), path)
            if path.startswith(tuple(name_exclude)):
                continue
            base = posixpath.basename(path).lower()
            self.by_name.setdefault(base, []).append(path)
            if base.endswith(".md"):
                self.by_name.setdefault(base[:-3], []).append(path)

    def resolve(self, target, src, kind, prefer):
        if target is None:
            return src, False
        if kind == "md":
            joined = posixpath.normpath(posixpath.join(posixpath.dirname(src), target))
            return self.by_lower.get(joined.lower()), False
        name = target.strip().lstrip("/")
        if "/" in name:
            ext = posixpath.splitext(name)[1]
            candidates = [name] if ext == ".md" else [name + ".md", name]
            for candidate in candidates:
                hit = self.by_lower.get(candidate.lower())
                if hit:
                    return hit, False
            return None, False
        options = sorted(set(self.by_name.get(name.lower(), [])))
        if not options:
            return None, False
        if len(options) == 1:
            return options[0], False
        options.sort(key=prefer)
        return options[0], True
