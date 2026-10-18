#!/usr/bin/env python3
"""Write this case's pdf input into the directory named by argv[1] (the throwaway vault's raw/inbox/).
The template ships no binary file (ingest evals spec §3.1). Exit 3 when this machine cannot convert the format."""
import shutil  # noqa: F401
import sys
import zipfile  # noqa: F401
from pathlib import Path

FACT = "The shop's Dayton warehouse ships 412 orders a day."

if shutil.which("pdftotext") is None:
    print("pdftotext missing")
    sys.exit(3)
text = FACT.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
           b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
           b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
           b"/Resources << /Font << /F1 5 0 R >> >> >>",
           b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
           b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
out, offsets = bytearray(b"%PDF-1.4\n"), []
for n, body in enumerate(objects, 1):
    offsets.append(len(out))
    out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
xref = len(out)
out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
(Path(sys.argv[1]) / "warehouse-report.pdf").write_bytes(bytes(out))
