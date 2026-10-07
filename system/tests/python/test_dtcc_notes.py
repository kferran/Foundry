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
