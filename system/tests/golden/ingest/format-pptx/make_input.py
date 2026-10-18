#!/usr/bin/env python3
"""Write this case's pptx input into the directory named by argv[1] (the throwaway vault's raw/inbox/).
The template ships no binary file (ingest evals spec §3.1). Exit 3 when this machine cannot convert the format."""
import shutil  # noqa: F401
import sys
import zipfile  # noqa: F401
from pathlib import Path

FACT = "The shop's Dayton warehouse ships 412 orders a day."

files = {
    "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
    "ppt/presentation.xml": '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                            '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>',
    "ppt/_rels/presentation.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                       '<Relationship Id="rId1" Type="slide" Target="slides/slide1.xml"/></Relationships>',
    "ppt/slides/slide1.xml": '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                             'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody>'
                             '<a:p><a:r><a:t>Warehouse update</a:t></a:r></a:p><a:p><a:r><a:t>FACT</a:t></a:r></a:p>'
                             '</p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
}
name = "warehouse-update.pptx"

with zipfile.ZipFile(Path(sys.argv[1]) / name, "w") as z:
    for part, xml in files.items():
        z.writestr(part, xml.replace("FACT", FACT))
