"""Inbox document conversion (#166): xlsx, docx and pptx with the standard library, pdf with pdftotext, to text.
Every refusal reason is fixed text: nothing from the document reaches an alert line."""
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
MAX_PART = 20 * 2**20  # unpacked bytes of one XML part; a larger part is refused (a zip bomb)
MAX_OUT = 5 * 2**20  # characters of converted text (pdftotext: bytes); past it the drop is refused
PDF_TIMEOUT = 120
_spent = 0  # ponytail: per-call module state, convert() is not reentrant; pass a budget object if it ever runs threaded


class ConversionError(Exception):
    """The drop cannot be read: corrupt, encrypted, too large, or its converter is missing."""


def convert(path) -> str:
    global _spent
    _spent = 0
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return f"# {path.name}\n\n{_pdf(path)}\n"
    try:
        with zipfile.ZipFile(path) as z:
            body = {".xlsx": _xlsx, ".docx": _docx, ".pptx": _pptx}[suffix](z)
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        # an encrypted Office file is an OLE container, not a zip, so it lands here too
        raise ConversionError(f"not a readable {suffix[1:]} file, encrypted or corrupt ({exc.__class__.__name__})")
    return f"# {path.name}\n\n{body}\n"


def _spend(text: str) -> str:
    global _spent
    _spent += len(text)
    if _spent > MAX_OUT:
        raise ConversionError(f"text over the output limit of {MAX_OUT // 2**20} MB")
    return text


def _local(name: str) -> str:
    return name.rpartition("}")[2]


def _all(el, name):
    return [e for e in el.iter() if _local(e.tag) == name]


def _attr(el, name):
    """A namespaced attribute by its local name (r:id, w:author), whatever the namespace (Strict OOXML differs)."""
    return next((v for k, v in el.attrib.items() if k.startswith("{") and _local(k) == name), None)


def _info(z, name, optional=False):
    try:
        info = z.getinfo(name)
    except KeyError:
        if optional:
            return None
        raise ConversionError("a part it names is missing")
    if info.file_size > MAX_PART:
        raise ConversionError(f"a part unpacks to over {MAX_PART // 2**20} MB")
    return info


def _xml(z, name, optional=False):
    info = _info(z, name, optional)
    return None if info is None else ET.fromstring(z.read(info))


def _rels(z, part) -> dict:
    """Relationship id -> (type, part path) for one part."""
    folder, name = posixpath.split(part)
    root = _xml(z, f"{folder}/_rels/{name}.rels", optional=True)
    out = {}
    for r in _all(root, "Relationship") if root is not None else []:
        target = r.get("Target", "")
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        out[r.get("Id")] = (r.get("Type", ""), path)
    return out


def _targets(rels, els):
    """The part each sheet or slide entry links, each part once (a repeated part would multiply the output)."""
    parts = []
    for el in els:
        hit = rels.get(_attr(el, "id"))
        if hit is None:
            raise ConversionError("a sheet or slide has no link")
        if hit[1] in parts:
            raise ConversionError("two sheets or slides name one part")
        parts.append(hit[1])
    return parts


# -- xlsx ---------------------------------------------------------------------
def _col(ref: str, default: int) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    n = 0
    for ch in letters[:4]:  # XFD is three letters; four is enough to be past the cap
        n = n * 26 + ord(ch) - 64
    if n > MAX_COLS:
        raise ConversionError(f"a cell column is past {MAX_COLS}")
    return n - 1 if letters else default


def _cell(c, shared) -> str:
    kind = c.get("t")
    if kind == "inlineStr":
        return _spend("".join(t.text or "" for t in _all(c, "t")))
    value = next((e.text or "" for e in c if _local(e.tag) == "v"), "")
    if kind == "s":
        try:
            return _spend(shared[int(value)])
        except (ValueError, IndexError):
            raise ConversionError("a cell names a shared string that does not exist")
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    return _spend(value)  # ponytail: dates stay Excel serial numbers; format them if drops show it matters


def _line(cells) -> str:
    _spend(" | " * len(cells))
    return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |"


def _sheet(z, part, shared) -> str:
    rows, total = [], 0
    with z.open(_info(z, part)) as fh:
        for _, el in ET.iterparse(fh):  # streamed: a huge sheet is counted, never held
            if _local(el.tag) != "row":
                continue
            total += 1
            if total <= MAX_ROWS:
                cells = {}
                for c in el:
                    if _local(c.tag) == "c":
                        cells[_col(c.get("r", ""), len(cells))] = _cell(c, shared)
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
            el.clear()
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
    strings = _xml(z, "xl/sharedStrings.xml", optional=True)
    shared = [] if strings is None else ["".join(t.text or "" for t in _all(si, "t")) for si in _all(strings, "si")]
    sheets = _all(_xml(z, "xl/workbook.xml"), "sheet")
    parts = _targets(_rels(z, "xl/workbook.xml"), sheets)
    return "\n\n".join(_spend(f"## Sheet: {sheet.get('name', '?')}\n\n") + _sheet(z, part, shared)
                       for sheet, part in zip(sheets, parts))


# -- docx ---------------------------------------------------------------------
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
        elif tag == "t":
            parts.append(e.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag in ("br", "cr"):
            parts.append("\n")
        elif tag == "footnoteReference":
            parts.append(f"[^{_attr(e, 'id')}]")
        elif tag == "endnoteReference":
            parts.append(f"[^e{_attr(e, 'id')}]")
        else:
            _runs(e, parts, inner)


def _notes(z, part, tag, mark, heading) -> str:
    root = _xml(z, part, optional=True)
    if root is None:
        return ""
    lines = [f"[^{mark}{_attr(n, 'id')}]: " + " ".join(_paras(n)).strip()
             for n in _all(root, tag) if not _attr(n, "type")]  # typed notes are Word's separators
    return f"## {heading}\n\n" + "\n".join(lines) if lines else ""


def _docx(z) -> str:
    out = ["\n\n".join(t for t in _paras(_xml(z, "word/document.xml")) if t.strip()),
           _notes(z, "word/footnotes.xml", "footnote", "", "Footnotes"),
           _notes(z, "word/endnotes.xml", "endnote", "e", "Endnotes")]
    comments = _xml(z, "word/comments.xml", optional=True)
    if comments is not None:
        lines = [_spend(f"- {_attr(c, 'author') or 'unknown'}: ") + " ".join(_paras(c)).strip()
                 for c in _all(comments, "comment")]
        if lines:
            out.append("## Comments\n\n" + "\n".join(lines))
    return "\n\n".join(t for t in out if t)


# -- pptx ---------------------------------------------------------------------
def _slide_text(root) -> str:
    """Text runs only: slide-number and date fields drop out."""
    lines = []
    for p in _all(root, "p"):
        text = "".join("\n" if _local(e.tag) == "br" else "".join(t.text or "" for t in e if _local(t.tag) == "t")
                       for e in p if _local(e.tag) in ("r", "br"))
        if text.strip():
            lines.append(_spend(text))
    return "\n".join(lines)


def _pptx(z) -> str:
    slides = _all(_xml(z, "ppt/presentation.xml"), "sldId")
    blocks = []
    for n, part in enumerate(_targets(_rels(z, "ppt/presentation.xml"), slides), 1):
        block = f"## Slide {n}\n\n{_slide_text(_xml(z, part))}"
        notes = next((p for kind, p in _rels(z, part).values() if kind.endswith("/notesSlide")), None)
        text = _slide_text(_xml(z, notes)) if notes else ""
        if text:
            block += f"\n\n### Speaker notes\n\n{text}"
        blocks.append(block)
    return "\n\n".join(blocks)


# -- pdf ----------------------------------------------------------------------
def _pdf(path) -> str:
    exe = shutil.which("pdftotext")
    if exe is None:
        raise ConversionError("pdftotext is not installed (package poppler or poppler-utils)")
    proc = subprocess.Popen([exe, "-layout", "-enc", "UTF-8", str(path), "-"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    timer = threading.Timer(PDF_TIMEOUT, proc.kill)
    timer.start()
    try:
        data = proc.stdout.read(MAX_OUT + 1)  # bounded: the kill at the timeout ends a stalled read too
        if len(data) > MAX_OUT:
            proc.kill()
        rc = proc.wait()
    finally:
        timer.cancel()
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if len(data) > MAX_OUT:
        raise ConversionError(f"text over the output limit of {MAX_OUT // 2**20} MB")
    if rc:
        raise ConversionError(f"pdftotext failed or ran past {PDF_TIMEOUT} s (exit {rc})" if rc < 0
                              else f"pdftotext failed (exit {rc})")
    pages = data.decode("utf-8", "replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()  # pdftotext ends the last page with a form feed too
    if not any(p.strip() for p in pages):
        raise ConversionError("the pdf has no text layer (a scan needs OCR first)")
    return "\n\n".join(f"## Page {n}\n\n{p.rstrip()}" for n, p in enumerate(pages, 1))
