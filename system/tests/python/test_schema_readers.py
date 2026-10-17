"""Every schema field names the files that read it (#166): `readers: [path, ...]` in its field spec.

A reader is a file that names the field (a key lookup, an SQL column, a config_get argument, a prompt's backtick);
validation and the index's generic field table do not count. `readers: []` marks a field nothing reads: a warning
for now, so the list can be trimmed (#122 step 4)."""
import re
import warnings

import pytest

from helpers import REPO
from vaultlib import frontmatter

SCHEMAS = sorted((REPO / "system" / "schemas").glob("*.md"))


@pytest.mark.parametrize("path", SCHEMAS, ids=[p.stem for p in SCHEMAS])
def test_every_field_names_its_readers(path):
    fields = frontmatter.parse(path.read_text(encoding="utf-8")).data["fields"]
    problems, unread = [], []
    for name, spec in fields.items():
        readers = spec.get("readers") if isinstance(spec, dict) else None
        if not isinstance(readers, list):
            problems.append(f"{name}: no readers list")
            continue
        if not readers:
            unread.append(name)
        for rel in readers:
            reader = REPO / rel
            if not reader.is_file():
                problems.append(f"{name}: reader {rel} does not exist")
            elif not re.search(rf"\b{name}\b", reader.read_text(encoding="utf-8")):
                problems.append(f"{name}: reader {rel} never mentions {name}")
    if unread:
        warnings.warn(f"{path.stem}: fields with no reader: {', '.join(unread)}", stacklevel=1)
    assert problems == []
