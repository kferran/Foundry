import re

import pytest

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
            "production_error", "config", "codebase", "session_digest", "preference", "workcell",
            "meeting", "meeting_transcript", "meeting_input", "telemetry_source", "nightshift_item", "dtcc_change"}


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


MEETING = ('---\ntype: meeting\ntitle: "Weekly sync"\ndate: "2026-10-05"\nstart: "2026-10-05T15:00:00-06:00"\n'
           'partition: work\nattendees: ["Avery Sample", "Blake Sample"]\nsource: "gdoc:FAKE-doc-0001"\n'
           'source_name: "Weekly sync - 2026/10/05 15:00 MDT - Notes by Gemini"\n'
           'transcript: "[[2026-10-05-1500-weekly-sync.transcript]]"\nstatus: canonical\nprovenance: [headless]\n---\n')
TRANSCRIPT = ('---\ntype: meeting_transcript\nmeeting: "[[2026-10-05-1500-weekly-sync]]"\npartition: work\n'
              'source: "gdoc:FAKE-doc-0001"\ncomplete: true\nprovenance: [headless]\n---\n')
INPUT = ('---\ntype: meeting_input\nmeeting: "[[2026-10-05-1500-weekly-sync]]"\npartition: work\n'
         'created_at: "2026-10-05T16:05:00-06:00"\n---\n')


@pytest.mark.parametrize("rel, text", [
    ("wiki/work/meetings/2026-10-05-1500-weekly-sync.md", MEETING),
    ("wiki/work/meetings/2026-10-05-1500-weekly-sync.transcript.md", TRANSCRIPT),
    ("raw/work/notes/2026-10-05-1500-weekly-sync.meeting-input.md", INPUT),
    ("raw/work/archive/2026-10-05-1500-weekly-sync.meeting-input.md", INPUT),
], ids=["meeting", "transcript", "input", "archived-input"])
def test_meeting_notes_validate(rel, text):
    schemas, ctx = load()
    ntype, issues = schema.validate_note(schemas, rel, frontmatter.parse(text), ctx)
    assert ntype == frontmatter.parse(text).data["type"]
    assert [i.message for i in issues] == []


@pytest.mark.parametrize("rel, text, field", [
    ("wiki/personal/meetings/m.md", MEETING, "partition"),
    ("wiki/work/meetings/m.md", MEETING.replace("transcript: ", "x_transcript: "), "transcript"),
    ("wiki/work/meetings/m.md", MEETING.replace("source: ", "x_source: "), "source"),
    ("wiki/work/meetings/m.md", MEETING.replace("partition: work", "partition: shared"), "partition"),
    ("wiki/work/meetings/m.transcript.md", TRANSCRIPT.replace("complete: true", "complete: maybe"), "complete"),
    ("raw/work/notes/m.meeting-input.md", INPUT.replace("meeting: ", "x_meeting: "), "meeting"),
    ("wiki/shared/meetings/m.md", MEETING.replace("partition: work", "partition: shared"), "type"),
], ids=["wrong-folder", "no-transcript", "no-source", "shared", "bad-complete", "no-meeting", "shared-folder"])
def test_meeting_notes_reject_bad_fields(rel, text, field):
    schemas, ctx = load()
    _, issues = schema.validate_note(schemas, rel, frontmatter.parse(text), ctx)
    assert any(i.severity == "error" and field in i.message for i in issues), [i.message for i in issues]


def test_config_meeting_keys():
    schemas, ctx = load()
    example = (REPO / "system" / "config.example.md").read_text(encoding="utf-8")
    note = frontmatter.parse(example)
    assert note.data["meetings_enabled"] == "false" and note.data["owner_names"] == []
    assert [i.message for i in schema.validate_note(schemas, "system/config.md", note, ctx)[1]] == []
    for line, field in (('meetings_partition: "shared"', "meetings_partition"), ('meetings_enabled: "yes"', "meetings_enabled"),
                        ('owner_names: "Avery"', "owner_names")):
        key = line.split(":")[0]
        text = re.sub(rf"^{key}: .*$", line, example, flags=re.M)
        _, issues = schema.validate_note(schemas, "system/config.md", frontmatter.parse(text), ctx)
        assert any(i.severity == "error" and field in i.message for i in issues), line
