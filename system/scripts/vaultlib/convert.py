"""Inbox drops to text (#166): OOXML with the standard library, pdf with pdftotext; refusal reasons are fixed text."""
import posixpath
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
import zipfile
import zlib

SUFFIXES = (".xlsx", ".docx", ".pptx", ".pdf")
MAX_ROWS = 1000  # rows shown per sheet; the rest are counted and named
MAX_COLS = 16384  # column XFD, the last one Excel has
MAX_PART = 5 * 2**20  # bytes of a part parsed as a tree, ~37x that in RSS (20 MB of <a b="1"/>: 745 MB)
MAX_UNPACKED = 50 * 2**20  # unpacked bytes of every part read, a part read twice counted twice: bounds parse time
MAX_OUT = 5 * 2**20  # characters of converted text (pdftotext: bytes); past it the drop is refused
MAX_DEPTH = 32  # streamed XML nesting; real OOXML stays under 10
MAX_HELD = 100_000  # elements inside one row or shared string; a full row of 16,384 cells is about 65k
MAX_ENTRIES = 10_000  # zip entries, checked from the end record before zipfile parses the directory
PDF_TIMEOUT = 120
_used = {"out": 0, "unpacked": 0}  # ponytail: per-call module state, convert() is not reentrant


class ConversionError(Exception):
    """The drop cannot be read: corrupt, encrypted, too large, or its converter is missing."""


def convert(path) -> str:
    _used.update(out=0, unpacked=0)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return f"# {path.name}\n\n{_pdf(path)}\n"
    with open(path, "rb") as fh:  # the end record, found as zipfile finds it, gives the directory's size
        fh.seek(max(0, path.stat().st_size - 65557))
        tail = fh.read()
    at = tail.rfind(b"PK\x05\x06")
    if at >= 0 and int.from_bytes(tail[at + 12:at + 16], "little") > MAX_ENTRIES * 300:  # bounds the parse
        raise ConversionError(f"the zip has over {MAX_ENTRIES} entries")
    try:
        with zipfile.ZipFile(path) as z:
            if len(z.infolist()) > MAX_ENTRIES:
                raise ConversionError(f"the zip has over {MAX_ENTRIES} entries")
            body = {".xlsx": _xlsx, ".docx": _docx, ".pptx": _pptx}[suffix](z)
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        # an encrypted Office file is an OLE container, not a zip, so it lands here too
        raise ConversionError(f"not a readable {suffix[1:]} file, encrypted or corrupt ({exc.__class__.__name__})")
    return f"# {path.name}\n\n{body}\n"


def _spend(text: str) -> str:
    _used["out"] += len(text)
    if _used["out"] > MAX_OUT:
        raise ConversionError(f"text over the output limit of {MAX_OUT // 2**20} MB")
    return text


def _local(name: str) -> str:
    return name.rpartition("}")[2]


def _all(el, name):
    return [e for e in el.iter() if _local(e.tag) == name]


def _attr(el, name):
    """A namespaced attribute by its local name (r:id, w:author), whatever the namespace (Strict OOXML differs)."""
    return next((v for k, v in el.attrib.items() if k.startswith("{") and _local(k) == name), None)


def _info(z, name, optional=False, streamed=False):
    try:
        info = z.getinfo(name)
    except KeyError:
        if optional:
            return None
        raise ConversionError("a part it names is missing")
    if not streamed and info.file_size > MAX_PART:
        raise ConversionError(f"a part unpacks to over {MAX_PART // 2**20} MB")
    _used["unpacked"] += info.file_size  # zipfile stops at the declared size (a lie fails its CRC): reads bounded
    if _used["unpacked"] > MAX_UNPACKED:
        raise ConversionError(f"the parts unpack to over {MAX_UNPACKED // 2**20} MB in total")
    return info


def _stream(z, part, tag, optional=False):
    """Each `tag` element of a part, dropped once handled: memory holds one element whatever the part's size."""
    info = _info(z, part, optional, streamed=True)
    if info is None:
        return
    parents, inside, held = [], 0, 0  # an open `tag` element keeps its `held` children until it is handled
    with z.open(info) as fh:
        for event, el in ET.iterparse(fh, events=("start", "end")):
            hit = _local(el.tag) == tag
            if event == "start":
                parents.append(el)
                inside += hit
                held += inside > 0
                if len(parents) > MAX_DEPTH or held > MAX_HELD:
                    raise ConversionError(f"XML over {MAX_DEPTH} deep or over {MAX_HELD} elements in one row or string")
                continue
            parents.pop()
            if hit:
                inside -= 1
                yield el
            if parents and (hit or not inside):
                parents[-1].remove(el)  # its earlier siblings are gone already, so this is the only child
            held *= inside > 0


def _xml(z, name, optional=False):
    info = _info(z, name, optional)
    return None if info is None else ET.fromstring(z.read(info))


def _rels(z, part) -> dict:
    """Relationship id -> (type, part path) for one part."""
    base, name = posixpath.split(part)
    root = _xml(z, f"{base}/_rels/{name}.rels", optional=True)
    return {r.get("Id"): (r.get("Type", ""), posixpath.normpath(posixpath.join(base, r.get("Target", ""))).lstrip("/"))
            for r in (_all(root, "Relationship") if root is not None else [])}  # an absolute Target wins the join


def _targets(rels, els):
    """The part each sheet or slide entry links, each part once (a repeated part would multiply the output)."""
    parts = [rels.get(_attr(el, "id"), ("", None))[1] for el in els]
    if None in parts:
        raise ConversionError("a sheet or slide has no link")
    if len(set(parts)) < len(parts):
        raise ConversionError("two sheets or slides name one part")
    return parts


def _col(ref: str, default: int) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    n = sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(letters[:4])))  # four letters pass XFD already
    if n > MAX_COLS:
        raise ConversionError(f"a cell column is past {MAX_COLS}")
    return n - 1 if letters else default


def _cell(c, shared) -> str:
    """The cell's text; shared strings are returned by reference and paid for in _line, once escaped."""
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
    shared = ["".join(t.text or "" for t in _all(si, "t")) for si in _stream(z, "xl/sharedStrings.xml", "si", True)]
    sheets = _all(_xml(z, "xl/workbook.xml"), "sheet")
    parts = _targets(_rels(z, "xl/workbook.xml"), sheets)
    return "\n\n".join(_spend(f"## Sheet: {sheet.get('name', '?')}\n\n") + _sheet(z, part, shared)
                       for sheet, part in zip(sheets, parts))


def _paras(children) -> list:
    """Paragraph texts in document order, each once: a text box's paragraphs follow the paragraph that holds it."""
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
        if tag in ("pPr", "rPr", "Fallback"):  # tab stops are not text; a Fallback repeats its Choice
            continue
        if tag == "p":
            inner += _paras([e])
        elif tag in ("t", "tab", "br", "cr"):
            parts.append(e.text or "" if tag == "t" else "\t" if tag == "tab" else "\n")
        elif tag in ("footnoteReference", "endnoteReference"):  # endnotes are [^eN], apart from footnote ids
            parts.append(f"[^{tag[0] if tag[0] == 'e' else ''}{_attr(e, 'id')}]")
        else:
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


def _slide_text(root) -> str:
    """Text runs only: slide-number and date fields drop out."""
    texts = ("".join("\n" if _local(e.tag) == "br" else "".join(t.text or "" for t in e if _local(t.tag) == "t")
                     for e in p if _local(e.tag) in ("r", "br")) for p in _all(root, "p"))
    return "\n".join(_spend(t) for t in texts if t.strip())


def _pptx(z) -> str:
    slides = _all(_xml(z, "ppt/presentation.xml"), "sldId")
    blocks = []
    for n, part in enumerate(_targets(_rels(z, "ppt/presentation.xml"), slides), 1):
        block = _spend(f"## Slide {n}\n\n") + _slide_text(_xml(z, part))
        notes = next((p for kind, p in _rels(z, part).values() if kind.endswith("/notesSlide")), None)
        text = _slide_text(_xml(z, notes)) if notes else ""
        blocks.append(block + (f"\n\n### Speaker notes\n\n{text}" if text else ""))
    return "\n\n".join(blocks)


def _pdf(path) -> str:
    exe = shutil.which("pdftotext")
    if exe is None:
        raise ConversionError("pdftotext is not installed (package poppler or poppler-utils)")
    proc = subprocess.Popen([exe, "-layout", "-enc", "UTF-8", str(path), "-"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    timer = threading.Timer(PDF_TIMEOUT, proc.kill)
    timer.start()
    try:
        with proc:  # closes stdout and waits on the way out
            data = proc.stdout.read(MAX_OUT + 1)  # bounded: the kill at the timeout ends a stalled read too
            if len(data) > MAX_OUT:
                proc.kill()
                raise ConversionError(f"text over the output limit of {MAX_OUT // 2**20} MB")
    finally:
        timer.cancel()
    if proc.returncode:  # negative: killed, at the timeout
        raise ConversionError(f"pdftotext failed (exit {proc.returncode})")
    pages = data.decode("utf-8", "replace").removesuffix("\f").split("\f")  # the last page ends with one too
    if not any(p.strip() for p in pages):
        raise ConversionError("the pdf has no text layer (a scan needs OCR first)")
    return "\n\n".join(_spend(f"## Page {n}\n\n{p.rstrip()}") for n, p in enumerate(pages, 1))
