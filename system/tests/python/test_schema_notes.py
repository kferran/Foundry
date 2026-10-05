import re

from helpers import REPO
from vaultlib import frontmatter, schema

SAMPLE = {
    "date": "2026-09-30", "partition": "work", "codebase": "ultron", "capability": "code",
    "source_stem": "SampleSource", "title": "Sample", "status": "active", "brief_time": "06:00",
    "debrief_time": "17:00", "branch_name": "fm/sample", "strategic_focus": "Stability",
    "short_feature_description": "Sample", "strategic_planning_note": "SamplePlan",
}
TEMPLATE_TARGETS = {
    "wiki-concept.md": "wiki/work/concepts/Sample.md",
    "daily-briefing.md": "briefings/2026-09-30.md",
    "daily-debrief.md": "briefings/2026-09-30.debrief.md",
    "intent-shaper.md": "wiki/work/plans/Sample.md",
}
NOT_NOTES = {"production-error.md"}  # body fragment filled by telemetry_store.render_body, no frontmatter
EXPECTED = {"schema", "concept", "index", "briefing", "debrief", "plan_gate",
            "production_error", "config", "codebase", "session_digest", "preference", "workcell", "telemetry_source"}


def load():
    return schema.load_schemas(REPO), schema.Context(REPO)


def test_all_schemas_load():
    schemas, _ = load()
    assert set(schemas) == EXPECTED


def test_schema_notes_validate_against_schema_schema():
    schemas, ctx = load()
    for path in (REPO / "system" / "schemas").glob("*.md"):
        note = frontmatter.parse(path.read_text(encoding="utf-8"))
        ntype, issues = schema.validate_note(schemas, f"system/schemas/{path.name}", note, ctx)
        assert ntype == "schema"
        assert [i for i in issues if i.severity == "error"] == [], path.name


def render(text):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: SAMPLE[m.group(1)], text)


def test_every_template_is_mapped():
    names = {p.name for p in (REPO / "system" / "templates").glob("*.md")}
    assert names - NOT_NOTES == set(TEMPLATE_TARGETS)


def test_templates_validate_against_their_schema():
    schemas, ctx = load()
    for name, target in TEMPLATE_TARGETS.items():
        text = render((REPO / "system" / "templates" / name).read_text(encoding="utf-8"))
        ntype, issues = schema.validate_note(schemas, target, frontmatter.parse(text), ctx)
        assert ntype is not None, name
        assert [i.message for i in issues if i.severity == "error"] == [], name


def test_config_sample_validates():
    schemas, ctx = load()
    text = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
            'remote_mode: "none"\ntemplate_remote: ""\ndefault_partition: "personal"\n---\n')
    _, issues = schema.validate_note(schemas, "system/config.md", frontmatter.parse(text), ctx)
    assert [i.message for i in issues if i.severity == "error"] == []
