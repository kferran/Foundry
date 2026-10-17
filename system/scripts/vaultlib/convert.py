"""Inbox document conversion (#166): xlsx, docx and pptx with the standard library, pdf with pdftotext, to text."""
import posixpath
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import zlib

SUFFIXES = (".xlsx", ".docx", ".pptx", ".pdf")
MAX_ROWS = 1000  # rows shown per sheet; the rest are counted and named
MAX_PART = 100 * 2**20  # unpacked bytes of one XML part; a larger part is refused (a zip bomb)
PDF_TIMEOUT = 120


class ConversionError(Exception):
    """The drop cannot be read: corrupt, encrypted, or its converter is missing."""


def convert(path) -> str:
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
        raise ConversionError(f"missing part {name}")
    if info.file_size > MAX_PART:
        raise ConversionError(f"part {name} unpacks to over {MAX_PART // 2**20} MB")
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


def _target(rels, el, part):
    hit = rels.get(_attr(el, "id"))
    if hit is None:
        raise ConversionError(f"{part} names a part it does not link")
    return hit[1]


# -- xlsx ---------------------------------------------------------------------
def _col(ref: str, default: int) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1 if letters else default


def _cell(c, shared) -> str:
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
    rels = _rels(z, "xl/workbook.xml")
    blocks = []
    for sheet in _all(_xml(z, "xl/workbook.xml"), "sheet"):
        part = _target(rels, sheet, "xl/workbook.xml")
        blocks.append(f"## Sheet: {sheet.get('name', '?')}\n\n{_sheet(z, part, shared)}")
    return "\n\n".join(blocks)


# -- docx ---------------------------------------------------------------------
def _para(p) -> str:
    parts = []
    for run in _all(p, "r"):  # runs only: a paragraph's tab-stop list is not text
        for e in run:
            tag = _local(e.tag)
            if tag == "t":
                parts.append(e.text or "")
            elif tag == "tab":
                parts.append("\t")
            elif tag in ("br", "cr"):
                parts.append("\n")
            elif tag in ("footnoteReference", "endnoteReference"):
                parts.append(f"[^{_attr(e, 'id')}]")
    return "".join(parts)


def _docx(z) -> str:
    out = ["\n\n".join(t for t in map(_para, _all(_xml(z, "word/document.xml"), "p")) if t.strip())]
    notes = _xml(z, "word/footnotes.xml", optional=True)
    if notes is not None:  # typed footnotes are Word's separators
        lines = [f"[^{_attr(f, 'id')}]: " + " ".join(map(_para, _all(f, "p"))).strip()
                 for f in _all(notes, "footnote") if not _attr(f, "type")]
        if lines:
            out.append("## Footnotes\n\n" + "\n".join(lines))
    comments = _xml(z, "word/comments.xml", optional=True)
    if comments is not None:
        lines = [f"- {_attr(c, 'author') or 'unknown'}: " + " ".join(map(_para, _all(c, "p"))).strip()
                 for c in _all(comments, "comment")]
        if lines:
            out.append("## Comments\n\n" + "\n".join(lines))
    return "\n\n".join(out)


# -- pptx ---------------------------------------------------------------------
def _slide_text(root) -> str:
    """Text runs only: slide-number and date fields drop out."""
    lines = []
    for p in _all(root, "p"):
        text = "".join("\n" if _local(e.tag) == "br" else "".join(t.text or "" for t in e if _local(t.tag) == "t")
                       for e in p if _local(e.tag) in ("r", "br"))
        if text.strip():
            lines.append(text)
    return "\n".join(lines)


def _pptx(z) -> str:
    rels = _rels(z, "ppt/presentation.xml")
    blocks = []
    for n, sid in enumerate(_all(_xml(z, "ppt/presentation.xml"), "sldId"), 1):
        part = _target(rels, sid, "ppt/presentation.xml")
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
    try:
        out = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True,
                             timeout=PDF_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ConversionError(f"pdftotext ran past {PDF_TIMEOUT} s")
    if out.returncode:
        last = (out.stderr.decode("utf-8", "replace").strip().splitlines() or ["no output"])[-1]
        raise ConversionError(f"pdftotext failed (exit {out.returncode}: {last})")
    pages = out.stdout.decode("utf-8", "replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()  # pdftotext ends the last page with a form feed too
    if not any(p.strip() for p in pages):
        raise ConversionError("the pdf has no text layer (a scan needs OCR first)")
    return "\n\n".join(f"## Page {n}\n\n{p.rstrip()}" for n, p in enumerate(pages, 1))
