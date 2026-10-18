#!/usr/bin/env python3
"""Write this case's docx input into the directory named by argv[1] (the throwaway vault's raw/inbox/).
The template ships no binary file (ingest evals spec §3.1). Exit 3 when this machine cannot convert the format."""
import shutil  # noqa: F401
import sys
import zipfile  # noqa: F401
from pathlib import Path

FACT = "The shop's Dayton warehouse ships 412 orders a day."

files = {
    "[Content_Types].xml": '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
    "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                         '<w:p><w:r><w:t>Warehouse report</w:t></w:r></w:p>'
                         '<w:p><w:r><w:t>FACT</w:t></w:r></w:p></w:body></w:document>',
}
name = "warehouse-report.docx"

with zipfile.ZipFile(Path(sys.argv[1]) / name, "w") as z:
    for part, xml in files.items():
        z.writestr(part, xml.replace("FACT", FACT))
