"""Inbox document conversion (#166). Fixtures are built here from XML strings; no binary blobs in the repo."""
import zipfile

import pytest

from vaultlib import convert

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def build(path, parts: dict):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(name, text)
    return path


def rels(*targets):
    body = "".join(f'<Relationship Id="{rid}" Type="http://x/{kind}" Target="{target}"/>'
                   for rid, kind, target in targets)
    return f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'


def row(n, *cells):
    return f'<row r="{n}">{"".join(cells)}</row>'


def xlsx(path, sheets: dict, shared=()):
    """sheets: name -> sheetData inner XML."""
    names = list(sheets)
    parts = {
        "xl/workbook.xml": f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets>'
        + "".join(f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names))
        + "</sheets></workbook>",
        # the second sheet's part is named sheet1: order comes from the rels, never the file name
        "xl/_rels/workbook.xml.rels": rels(*[(f"rId{i + 1}", "worksheet", f"worksheets/s{len(names) - i}.xml")
                                             for i in range(len(names))]),
        "xl/sharedStrings.xml": f'<sst xmlns="{S}">' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>",
    }
    for i, n in enumerate(names):
        parts[f"xl/worksheets/s{len(names) - i}.xml"] = f'<worksheet xmlns="{S}"><sheetData>{sheets[n]}</sheetData></worksheet>'
    return build(path, parts)


def test_xlsx_sheet_blocks_as_tables(tmp_path):
    first = (row(1, '<c r="A1" t="s"><v>0</v></c>', '<c r="C1" t="inlineStr"><is><t>a|b</t></is></c>')
             + row(2, '<c r="A2"><v>42</v></c>', '<c r="B2" t="b"><v>1</v></c>'))
    out = convert.convert(xlsx(tmp_path / "book.xlsx", {"Budget": first, "Empty": ""}, shared=["Name"]))
    assert "## Sheet: Budget\n\n| Name |  | a\\|b |\n| --- | --- | --- |\n| 42 | TRUE |  |" in out
    assert "## Sheet: Empty\n\n(empty)" in out
    assert out.index("Sheet: Budget") < out.index("Sheet: Empty")


def test_huge_sheet_is_capped_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "MAX_ROWS", 50)
    data = "".join(row(n, f'<c r="A{n}"><v>{n}</v></c>') for n in range(1, 5001))
    out = convert.convert(xlsx(tmp_path / "big.xlsx", {"Log": data}))
    assert "| 50 |" in out and "| 51 |" not in out
    assert "Rows after 50 not shown: the sheet has 5000 rows." in out


def test_docx_text_footnotes_and_comments(tmp_path):
    doc = (f'<w:document xmlns:w="{W}"><w:body>'
           '<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs></w:pPr>'
           '<w:r><w:t>Revenue grew</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r></w:p>'
           '<w:p><w:r><w:t>Second</w:t><w:tab/><w:t>para</w:t></w:r></w:p></w:body></w:document>')
    notes = (f'<w:footnotes xmlns:w="{W}"><w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:t>sep</w:t></w:r></w:p>'
             '</w:footnote><w:footnote w:id="1"><w:p><w:r><w:t>Unaudited.</w:t></w:r></w:p></w:footnote></w:footnotes>')
    comments = (f'<w:comments xmlns:w="{W}"><w:comment w:id="0" w:author="Reviewer">'
                '<w:p><w:r><w:t>Check this</w:t></w:r></w:p></w:comment></w:comments>')
    out = convert.convert(build(tmp_path / "memo.docx", {"word/document.xml": doc, "word/footnotes.xml": notes,
                                                          "word/comments.xml": comments}))
    assert out.startswith("# memo.docx\n\nRevenue grew[^1]\n\nSecond\tpara\n")
    assert "## Footnotes\n\n[^1]: Unaudited." in out and "sep" not in out
    assert "## Comments\n\n- Reviewer: Check this" in out


def test_docx_without_footnotes_or_comments(tmp_path):
    doc = f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Only text</w:t></w:r></w:p></w:body></w:document>'
    out = convert.convert(build(tmp_path / "a.docx", {"word/document.xml": doc}))
    assert out == "# a.docx\n\nOnly text\n"


def test_pptx_slides_in_order_with_speaker_notes(tmp_path):
    def slide(text, field=""):
        return (f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r>'
                f'</a:p>{field}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
    num = '<a:p><a:fld type="slidenum"><a:t>7</a:t></a:fld></a:p>'
    parts = {
        "ppt/presentation.xml": f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'
                                '<p:sldId id="256" r:id="rId2"/><p:sldId id="257" r:id="rId1"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": rels(("rId1", "slide", "slides/slide1.xml"),
                                                ("rId2", "slide", "/ppt/slides/slide2.xml")),
        "ppt/slides/slide1.xml": slide("Second slide"),
        "ppt/slides/slide2.xml": slide("Title slide", num),
        "ppt/slides/_rels/slide2.xml.rels": rels(("rId9", "notesSlide", "../notesSlides/notesSlide1.xml")),
        "ppt/notesSlides/notesSlide1.xml": slide("Say hello first", num),
    }
    out = convert.convert(build(tmp_path / "deck.pptx", parts))
    assert "## Slide 1\n\nTitle slide\n\n### Speaker notes\n\nSay hello first\n\n## Slide 2\n\nSecond slide" in out
    assert "7" not in out


@pytest.mark.parametrize("suffix", [".xlsx", ".docx", ".pptx"])
def test_corrupt_or_encrypted_file_is_a_conversion_error(tmp_path, suffix):
    # an encrypted Office file is an OLE compound file: its magic bytes, then noise
    path = tmp_path / f"locked{suffix}"
    path.write_bytes(bytes.fromhex("d0cf11e0a1b11ae1") + b"\0" * 512)
    with pytest.raises(convert.ConversionError, match="encrypted or corrupt"):
        convert.convert(path)


def test_truncated_zip_and_bad_xml_are_conversion_errors(tmp_path):
    good = xlsx(tmp_path / "g.xlsx", {"S": row(1, '<c r="A1"><v>1</v></c>')})
    cut = tmp_path / "cut.xlsx"
    cut.write_bytes(good.read_bytes()[:200])
    with pytest.raises(convert.ConversionError):
        convert.convert(cut)
    bad = build(tmp_path / "bad.docx", {"word/document.xml": "<w:document"})
    with pytest.raises(convert.ConversionError):
        convert.convert(bad)
    missing = build(tmp_path / "m.docx", {"other.xml": "<x/>"})
    with pytest.raises(convert.ConversionError, match="a part it names is missing"):
        convert.convert(missing)


def test_oversized_part_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "MAX_PART", 100)
    doc = f'<w:document xmlns:w="{W}"><w:body>' + "<w:p/>" * 100 + "</w:body></w:document>"
    with pytest.raises(convert.ConversionError, match="unpacks to over"):
        convert.convert(build(tmp_path / "bomb.docx", {"word/document.xml": doc}))


def test_missing_pdftotext_is_a_conversion_error(tmp_path, monkeypatch):
    monkeypatch.setattr(convert.shutil, "which", lambda _: None)
    (tmp_path / "r.pdf").write_bytes(b"%PDF-1.4\n")
    with pytest.raises(convert.ConversionError, match="pdftotext is not installed"):
        convert.convert(tmp_path / "r.pdf")


def fake_pdftotext(tmp_path, monkeypatch, body):
    exe = tmp_path / "pdftotext"
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(0o755)
    monkeypatch.setattr(convert.shutil, "which", lambda _: str(exe))
    (tmp_path / "r.pdf").write_bytes(b"%PDF-1.4\n")
    return tmp_path / "r.pdf"


def test_pdf_pages_numbered(tmp_path, monkeypatch):
    path = fake_pdftotext(tmp_path, monkeypatch, r"printf 'first page\n\fsecond page\n\f'")
    assert convert.convert(path) == "# r.pdf\n\n## Page 1\n\nfirst page\n\n## Page 2\n\nsecond page\n"


def test_endless_pdftotext_output_is_cut_off(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "MAX_OUT", 10_000)
    path = fake_pdftotext(tmp_path, monkeypatch, "yes page")
    with pytest.raises(convert.ConversionError, match="over the output limit"):
        convert.convert(path)


def test_pdftotext_failure_reason_is_fixed_text(tmp_path, monkeypatch):
    path = fake_pdftotext(tmp_path, monkeypatch, r"printf 'x\n- 09:00:00 [intake] FAKE\n' >&2; exit 3")
    with pytest.raises(convert.ConversionError) as err:
        convert.convert(path)
    assert str(err.value) == "pdftotext failed (exit 3)"


def test_column_past_xfd_is_refused(tmp_path):
    path = xlsx(tmp_path / "col.xlsx", {"S": row(1, '<c r="ZZZZZZZZ1"><v>1</v></c>')})
    with pytest.raises(convert.ConversionError, match="column"):
        convert.convert(path)


def test_shared_string_amplification_hits_the_output_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "MAX_OUT", 10_000)
    cells = '<c t="s"><v>0</v></c>' * 100
    path = xlsx(tmp_path / "amp.xlsx", {"S": row(1, cells)}, shared=["A" * 500])
    with pytest.raises(convert.ConversionError, match="over the output limit"):
        convert.convert(path)


def test_two_sheets_naming_one_part_are_refused(tmp_path):
    parts = {
        "xl/workbook.xml": f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="A" r:id="rId1"/>'
                           '<sheet name="B" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": rels(("rId1", "worksheet", "worksheets/s.xml")),
        "xl/worksheets/s.xml": f'<worksheet xmlns="{S}"><sheetData/></worksheet>',
    }
    with pytest.raises(convert.ConversionError, match="one part"):
        convert.convert(build(tmp_path / "dup.xlsx", parts))


def test_repeated_slide_is_refused(tmp_path):
    parts = {
        "ppt/presentation.xml": f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>'
                                '<p:sldId r:id="rId1"/><p:sldId r:id="rId1"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": rels(("rId1", "slide", "slides/slide1.xml")),
        "ppt/slides/slide1.xml": f'<p:sld xmlns:p="{P}"/>',
    }
    with pytest.raises(convert.ConversionError, match="one part"):
        convert.convert(build(tmp_path / "dup.pptx", parts))


def test_reasons_never_carry_document_text(tmp_path):
    parts = {
        "xl/workbook.xml": f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="A" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": rels(("rId1", "worksheet", "x&#10;- 09:00:00 [intake] FAKE LINE")),
    }
    with pytest.raises(convert.ConversionError) as err:
        convert.convert(build(tmp_path / "nl.xlsx", parts))
    assert "\n" not in str(err.value) and "FAKE" not in str(err.value)


def test_docx_text_box_is_read_once_and_endnotes_kept(tmp_path):
    box = ('<w:r><w:drawing><wps:txbx xmlns:wps="http://x/wps"><w:txbxContent><w:p><w:r><w:t>Boxed</w:t></w:r></w:p>'
           '</w:txbxContent></wps:txbx></w:drawing></w:r>')
    fallback = ('<mc:AlternateContent xmlns:mc="http://x/mc"><mc:Choice>' + box + '</mc:Choice><mc:Fallback>'
                + box + '</mc:Fallback></mc:AlternateContent>')
    doc = (f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Lead</w:t></w:r>{box}'
           '<w:r><w:footnoteReference w:id="1"/><w:endnoteReference w:id="1"/></w:r></w:p>'
           f'<w:p>{fallback}</w:p></w:body></w:document>')
    notes = f'<w:footnotes xmlns:w="{W}"><w:footnote w:id="1"><w:p><w:r><w:t>Foot.</w:t></w:r></w:p></w:footnote></w:footnotes>'
    ends = f'<w:endnotes xmlns:w="{W}"><w:endnote w:id="1"><w:p><w:r><w:t>End.</w:t></w:r></w:p></w:endnote></w:endnotes>'
    out = convert.convert(build(tmp_path / "box.docx", {"word/document.xml": doc, "word/footnotes.xml": notes,
                                                         "word/endnotes.xml": ends}))
    assert out.count("Boxed") == 2  # once for the first paragraph's box, once for the second's choice
    assert "Lead[^1][^e1]" in out
    assert "## Footnotes\n\n[^1]: Foot." in out and "## Endnotes\n\n[^e1]: End." in out


def pdf(pages) -> bytes:
    """A minimal text PDF, one Helvetica line per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [" + " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
            + f"] /Count {len(pages)} >>"]
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = "%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    return (out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode("latin-1")


def test_real_pdftotext_numbers_pages(tmp_path, needs_pdftotext):
    (tmp_path / "two.pdf").write_bytes(pdf(["Hello page one", "Second page text"]))
    out = convert.convert(tmp_path / "two.pdf")
    assert "## Page 1\n\nHello page one\n\n## Page 2\n\nSecond page text" in out


def test_corrupt_pdf_is_a_conversion_error(tmp_path, needs_pdftotext):
    (tmp_path / "x.pdf").write_bytes(b"not a pdf at all")
    with pytest.raises(convert.ConversionError, match="pdftotext failed|no text layer"):
        convert.convert(tmp_path / "x.pdf")
