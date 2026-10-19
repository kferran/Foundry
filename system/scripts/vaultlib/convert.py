"""Inbox drops to text (#166): OOXML with the standard library, pdf with pdftotext; refusal reasons are fixed text."""
import posixpath
import resource
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

SUFFIXES = (".xlsx", ".docx", ".pptx", ".pdf")
MAX_ROWS = 1000  # rows shown per sheet; the rest are counted and named
MAX_OUT = 5 * 2**20  # characters of converted text (pdftotext: bytes); past it the drop is refused
CHILD_AS, CHILD_CPU = 512 * 2**20, 60  # child limits: 2.5x the largest valid VSZ (45 MB of strings: 208 MB)
PDF_TIMEOUT = 120
_used = {"out": 0}  # ponytail: per-call module state, convert() is not reentrant


class ConversionError(Exception):
    """The drop cannot be read: corrupt, encrypted, too large, or its converter is missing."""


def convert(path, out=None) -> str:
    """pdf here; OOXML in a child under memory and CPU limits (the XML parser multiplies memory past any cap)."""
    _used["out"] = 0
    if path.suffix.lower() == ".pdf":
        return f"# {path.name}\n\n{_pdf(path)}\n"
    out = Path(out or path.with_name(f".{path.name}.converted"))
    try:
        rc = subprocess.run([sys.executable, "-I", __file__, str(path), str(out)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2 * CHILD_CPU).returncode
        if rc not in (0, 3):  # MemoryError, SIGXCPU, a signal
            raise ConversionError("conversion exceeded its limits")
        if rc:
            raise ConversionError(out.read_text(encoding="utf-8")[:200])  # the child's own fixed-text reason
        return out.read_text(encoding="utf-8")
    except subprocess.TimeoutExpired:
        raise ConversionError("conversion exceeded its limits")
    finally:
        out.unlink(missing_ok=True)


def _ooxml(path) -> str:  # an encrypted Office file is an OLE container, not a zip: "encrypted or corrupt"
    _used["out"] = 0
    suffix = path.suffix.lower()
    try:
        with zipfile.ZipFile(path) as z:
            return f"# {path.name}\n\n{ {'.xlsx': _xlsx, '.docx': _docx, '.pptx': _pptx}[suffix](z)}\n"
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise ConversionError(f"not a readable {suffix[1:]} file, encrypted or corrupt ({exc.__class__.__name__})")


def _spend(text: str) -> str:
    _used["out"] += len(text)
    if _used["out"] > MAX_OUT:
        raise ConversionError(f"text over the output limit of {MAX_OUT // 2**20} MB")
    return text


def _local(name: str) -> str:
    return name.rpartition("}")[2]


def _all(el, name):
    return [e for e in el.iter() if _local(e.tag) == name]


def _attr(el, name):  # a namespaced attribute (r:id, w:author) by local name; Strict OOXML has other namespaces
    return next((v for k, v in el.attrib.items() if k.startswith("{") and _local(k) == name), None)


def _info(z, name, optional=False):
    try:
        info = z.getinfo(name)
    except KeyError:
        if optional:
            return None
        raise ConversionError("a part it names is missing")
    return info


def _stream(z, part, tag):  # each `tag` element of a part, dropped once handled, so the part is never held
    if (info := _info(z, part, optional=tag == "si")) is None:  # shared strings are optional
        return
    parser, tail, parents, inside = ET.XMLPullParser(events=("start", "end")), b"", [], 0
    with z.open(info) as fh:
        while chunk := fh.read(2**16):
            if b"<!DOCTYPE" in tail + chunk or b"\0" in chunk:  # the tail catches one split across two reads
                raise ConversionError("a part is UTF-16" if b"\0" in chunk else "a part has a DOCTYPE")
            tail = chunk[-9:]
            parser.feed(chunk)
            for event, el in parser.read_events():
                hit = _local(el.tag) == tag
                if event == "start":
                    parents.append(el)
                    inside += hit
                    continue
                parents.pop()
                if hit:
                    inside -= 1
                    yield el
                if parents and (hit or not inside):
                    parents[-1].remove(el)  # its earlier siblings are gone already, so this is the only child
    parser.close()


def _xml(z, name, optional=False):
    data = z.read(info) if (info := _info(z, name, optional)) else b""
    if b"<!DOCTYPE" in data or b"\0" in data:  # OOXML has none, a DTD multiplies memory; a NUL is UTF-16 (BOM or
        raise ConversionError("a part is UTF-16" if b"\0" in data else "a part has a DOCTYPE")  # not), hiding one
    return ET.fromstring(data) if info else None


def _rels(z, part) -> dict:  # relationship id -> (type, part path)
    base, name = posixpath.split(part)
    root = _xml(z, f"{base}/_rels/{name}.rels", optional=True)
    return {r.get("Id"): (r.get("Type", ""), posixpath.normpath(posixpath.join(base, r.get("Target", ""))).lstrip("/"))
            for r in (_all(root, "Relationship") if root is not None else [])}  # an absolute Target wins the join


def _part(rels, el):  # an entry with no link names part "", which is missing
    return rels.get(_attr(el, "id"), ("", ""))[1]


def _col(ref: str, default: int) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()  # a column past XFD runs into the child's limits
    return sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(letters))) - 1 if letters else default


def _cell(c, shared) -> str:  # shared strings go by reference; _line pays for the text once escaped
    kind = c.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in _all(c, "t"))
    value = next((e.text or "" for e in c if _local(e.tag) == "v"), "")
    if kind == "s":
        try:
            return shared[int(value)]
        except (ValueError, IndexError):
            raise ConversionError("a cell names a shared string that does not exist")
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value  # ponytail: dates stay Excel serial numbers; format them if drops show it matters


def _line(cells) -> str:
    _spend(" | " * len(cells))
    return "| " + " | ".join(_spend(c.replace("|", "\\|").replace("\n", " ")) for c in cells) + " |"


def _sheet(z, part, shared) -> str:
    rows, total = [], 0
    for el in _stream(z, part, "row"):  # a huge sheet is counted, never held
        total += 1
        if total <= MAX_ROWS:
            cells = {}
            for c in el:
                if _local(c.tag) == "c":
                    cells[_col(c.get("r", ""), len(cells))] = _cell(c, shared)
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    rows = [r for r in rows if any(r)]
    if not rows:
        return "(empty)"
    width = max(len(r) for r in rows)
    lines = [_line(r + [""] * (width - len(r))) for r in rows]
    lines.insert(1, "|" + " --- |" * width)
    if total > MAX_ROWS:
        lines.append(f"\n(Rows after {MAX_ROWS} not shown: the sheet has {total} rows.)")
    return "\n".join(lines)


def _xlsx(z) -> str:
    shared = ["".join(t.text or "" for t in _all(si, "t")) for si in _stream(z, "xl/sharedStrings.xml", "si")]
    sheets, rels = _all(_xml(z, "xl/workbook.xml"), "sheet"), _rels(z, "xl/workbook.xml")
    return "\n\n".join(_spend(f"## Sheet: {s.get('name')}\n\n") + _sheet(z, _part(rels, s), shared) for s in sheets)


def _paras(children) -> list:  # each paragraph once, in order; a text box's follow the paragraph holding it
    out = []
    for el in children:
        if _local(el.tag) == "p":
            parts, inner = [], []
            _runs(el, parts, inner)
            out += [_spend("".join(parts)), *inner]
        else:
            out += _paras(el)
    return out


def _runs(el, parts, inner) -> None:
    for e in el:
        tag = _local(e.tag)
        if tag == "p":
            inner += _paras([e])
        elif tag in ("t", "tab", "br", "cr"):
            parts.append(e.text or "" if tag == "t" else "\t" if tag == "tab" else "\n")
        elif tag in ("footnoteReference", "endnoteReference"):  # endnotes are [^eN], apart from footnote ids
            parts.append(f"[^{tag[0] if tag[0] == 'e' else ''}{_attr(e, 'id')}]")
        elif tag not in ("pPr", "rPr", "Fallback"):  # tab stops are not text; a Fallback repeats its Choice
            _runs(e, parts, inner)


def _notes(z, part, tag, heading, prefix) -> str:
    root = _xml(z, part, optional=True)
    lines = [] if root is None else [_spend(prefix(n)) + " ".join(_paras(n)).strip()
                                     for n in _all(root, tag) if not _attr(n, "type")]  # typed: Word's separators
    return f"## {heading}\n\n" + "\n".join(lines) if lines else ""


def _docx(z) -> str:
    out = ["\n\n".join(t for t in _paras(_xml(z, "word/document.xml")) if t.strip()),
           _notes(z, "word/footnotes.xml", "footnote", "Footnotes", lambda n: f"[^{_attr(n, 'id')}]: "),
           _notes(z, "word/endnotes.xml", "endnote", "Endnotes", lambda n: f"[^e{_attr(n, 'id')}]: "),
           _notes(z, "word/comments.xml", "comment", "Comments", lambda n: f"- {_attr(n, 'author') or 'unknown'}: ")]
    return "\n\n".join(t for t in out if t)


def _slide_text(root) -> str:  # text runs only: slide-number and date fields drop out
    texts = ("".join("\n" if _local(e.tag) == "br" else "".join(t.text or "" for t in e if _local(t.tag) == "t")
                     for e in p if _local(e.tag) in ("r", "br")) for p in _all(root, "p"))
    return "\n".join(_spend(t) for t in texts if t.strip())


def _pptx(z) -> str:
    slides, rels = _all(_xml(z, "ppt/presentation.xml"), "sldId"), _rels(z, "ppt/presentation.xml")
    blocks = []
    for n, part in enumerate((_part(rels, s) for s in slides), 1):
        block = _spend(f"## Slide {n}\n\n") + _slide_text(_xml(z, part))
        notes = next((p for kind, p in _rels(z, part).values() if kind.endswith("/notesSlide")), None)
        text = _slide_text(_xml(z, notes)) if notes else ""
        blocks.append(block + (f"\n\n### Speaker notes\n\n{text}" if text else ""))
    return "\n\n".join(blocks)


def _pdf(path) -> str:
    if (exe := shutil.which("pdftotext")) is None:
        raise ConversionError("pdftotext is not installed (package poppler or poppler-utils)")
    proc = subprocess.Popen([exe, "-layout", str(path), "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            preexec_fn=_limit)  # the child's limits; the read cap and the kill below still apply
    timer = threading.Timer(PDF_TIMEOUT, proc.kill)
    timer.start()
    try:
        with proc:  # closes stdout and waits on the way out
            data = proc.stdout.read(MAX_OUT + 1)  # bounded: the kill at the timeout ends a stalled read too
            if len(data) > MAX_OUT:  # closing the pipe ends pdftotext (SIGPIPE)
                raise ConversionError(f"text over the output limit of {MAX_OUT // 2**20} MB")
    finally:
        timer.cancel()
        proc.kill()  # a no-op once it is reaped
    if proc.returncode:  # negative: killed, at the timeout
        raise ConversionError(f"pdftotext failed (exit {proc.returncode})")
    pages = data.decode("utf-8", "replace").removesuffix("\f").split("\f")  # the last page ends with one too
    if not any(p.strip() for p in pages):
        raise ConversionError("the pdf has no text layer (a scan needs OCR first)")
    return "\n\n".join(_spend(f"## Page {n}\n\n{p.rstrip()}") for n, p in enumerate(pages, 1))


def _limit():  # on the OOXML child and on pdftotext; a lower hard limit already set is kept
    for limit, value in ((resource.RLIMIT_AS, CHILD_AS), (resource.RLIMIT_CPU, CHILD_CPU), (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(limit, (value,) * 2 if (h := resource.getrlimit(limit)[1]) < 0 or h >= value else (h, h))


if __name__ == "__main__":  # the child convert() starts: limits on itself first, then one OOXML file
    _limit()
    try:
        Path(sys.argv[2]).write_text(_ooxml(Path(sys.argv[1])), encoding="utf-8")
    except ConversionError as exc:
        Path(sys.argv[2]).write_text(str(exc), encoding="utf-8")
        sys.exit(3)
