#!/usr/bin/env python3
"""Write this case's xlsx input into the directory named by argv[1] (the throwaway vault's raw/inbox/).
The template ships no binary file (ingest evals spec §3.1). Exit 3 when this machine cannot convert the format."""
import shutil  # noqa: F401
import sys
import zipfile  # noqa: F401
from pathlib import Path

FACT = "The shop's Dayton warehouse ships 412 orders a day."

files = {
    "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
    "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                       '<sheets><sheet name="Warehouses" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                  '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Warehouse</t></is></c><c r="B1" t="inlineStr"><is><t>Orders a day</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Dayton</t></is></c><c r="B2"><v>412</v></c></row></sheetData></worksheet>',
}
name = "warehouses.xlsx"

with zipfile.ZipFile(Path(sys.argv[1]) / name, "w") as z:
    for part, xml in files.items():
        z.writestr(part, xml.replace("FACT", FACT))
