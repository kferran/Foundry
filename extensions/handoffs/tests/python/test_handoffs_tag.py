"""The [handoffs] alert tag waits for the brief, through this extension's manifest (factory F2, #307)."""
import shutil
from pathlib import Path

from helpers import write
from vaultlib import alerts

EXT = Path(__file__).resolve().parents[2]


def test_a_handoffs_line_waits_for_the_brief(tmp_path):
    shutil.copytree(EXT, tmp_path / "extensions" / "handoffs", ignore=shutil.ignore_patterns("tests"))
    write(tmp_path, "system/config.md", '---\ntype: config\nextensions: ["handoffs"]\n---\n')
    ext = alerts.extension_tags(tmp_path)
    assert ext == {"handoffs": "brief"}
    assert alerts.severity("- 06:10:00 [handoffs] search failed (exit 6)", ext) == "brief"
