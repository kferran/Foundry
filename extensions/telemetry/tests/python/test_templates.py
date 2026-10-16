"""The extension's templates: the rca note template validates against its schema, and the production-error body
fragment holds no frontmatter (telemetry_store.render_body fills it)."""
import re
from pathlib import Path

from vaultlib import frontmatter, schema

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]

SAMPLE = {"date": "2026-09-30", "partition": "work", "codebase": "sample", "title": "Sample",
          "source": "raw/telemetry/sample.md", "environment": "prod"}


def test_the_rca_template_validates_against_its_schema():
    schemas, ctx = schema.load_schemas(VAULT), schema.Context(VAULT)
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: SAMPLE[m.group(1)], (EXT / "templates" / "rca.md").read_text(encoding="utf-8"))
    ntype, issues = schema.validate_note(schemas, "wiki/work/rca/2026-09-30-sample.md", frontmatter.parse(text), ctx)
    assert ntype == "rca"
    assert [i.message for i in issues if i.severity == "error"] == []


def test_the_production_error_template_is_a_body_fragment():
    assert not (EXT / "templates" / "production-error.md").read_text(encoding="utf-8").startswith("---")


def test_the_example_source_is_a_telemetry_source():
    note = frontmatter.parse((EXT / "templates" / "telemetry-source.example.md").read_text(encoding="utf-8"))
    assert note.data["type"] == "telemetry_source"
