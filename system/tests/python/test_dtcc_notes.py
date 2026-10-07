from pathlib import Path

from helpers import REPO
from vaultlib import frontmatter, schema

GOOD = """---
type: "dtcc_change"
partition: "work"
detected_at: "2026-10-06T11:30:00+00:00"
kind: "version_gap"
key: "gap:stl:v26-7"
title: "stl: published v26-7, pinned v25-3"
paths: ["src/dtcc/stl/"]
deadlines: []
impact: "pending"
capability: "code"
---
# stl: published v26-7, pinned v25-3
"""


def test_dtcc_change_schema_accepts_a_note(vault: Path):
    schemas = schema.load_schemas(vault)
    ntype, issues = schema.validate_note(schemas, "wiki/work/changes/dtcc-gap-stl-v26-7.md",
                                         frontmatter.parse(GOOD), schema.Context(vault))
    assert ntype == "dtcc_change"
    assert [i.message for i in issues if i.severity == "error"] == []


def test_dtcc_change_partition_must_match_folder(vault: Path):
    schemas = schema.load_schemas(vault)
    _, issues = schema.validate_note(schemas, "wiki/personal/changes/x.md", frontmatter.parse(GOOD), schema.Context(vault))
    assert any(i.code == "partition-folder" for i in issues)


def test_example_map_is_generic():
    text = (REPO / "system" / "dtcc" / "map.example.yaml").read_text(encoding="utf-8")
    assert "example-app" in text
    for word in ("ultron", "porch", "edj"):
        assert word not in text.lower()

from vaultlib import dtcc_notes


def fm(**extra):
    base = {"type": "dtcc_change", "partition": "work", "detected_at": "2026-10-06T11:30:00+00:00",
            "kind": "notice", "key": "notice:a9809", "title": "Notice a9809: [[evil]] <b>x</b>",
            "impact": "pending", "capability": "code", "paths": ["src/x/"], "deadlines": ["Production 2027-04-15 (a9809)"]}
    base.update(extra)
    return base


def test_rel_path():
    assert dtcc_notes.rel_path("work", "notice:a9809") == "wiki/work/changes/dtcc-notice-a9809.md"
    assert dtcc_notes.rel_path("work", "api:Profile Management: OAuth2:1.0.3") == \
        "wiki/work/changes/dtcc-api-profile-management-oauth2-1.0.3.md"


def test_render_is_valid_and_inert(vault: Path):
    f = fm(title=dtcc_notes.clean("Notice a9809: [[evil]] <b>x</b>"))
    text = dtcc_notes.render(f, ["Category: [[x]] INSURANCE"], ["src/x/ (missing at origin/main)"], ["[[Dtcc]]"])
    assert "[[evil]]" not in text and "<b>" not in text and "[[x]]" not in text
    assert "## Evidence" in text and "## Mapped paths" in text and "## Related\n- [[Dtcc]]" in text
    assert text.rstrip().endswith("## Impact")
    rel = dtcc_notes.rel_path("work", f["key"])
    assert dtcc_notes.create(vault, rel, text, schema.load_schemas(vault)) is True
    assert dtcc_notes.create(vault, rel, text, schema.load_schemas(vault)) is False


def test_create_refuses_an_invalid_note(vault: Path):
    import pytest
    text = dtcc_notes.render(fm(kind="bogus"), [], [], [])
    with pytest.raises(ValueError):
        dtcc_notes.create(vault, "wiki/work/changes/dtcc-x.md", text, schema.load_schemas(vault))
    assert not (vault / "wiki/work/changes/dtcc-x.md").exists()
