"""vaultlib/meetings.py: parsing Gemini Docs and dropped transcripts (meetings spec §2.3 step 1, §6)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from vaultlib import frontmatter, links, meetings

TZ = ZoneInfo("America/Denver")
DOC_ID = "FAKE-doc-0001"
DOC_TITLE = "Weekly sync - Planning - 2026/10/05 15:00 MDT - Notes by Gemini"
NOTES = """📝 Notes

Oct 5, 2026

## Weekly sync - Planning

Invited [Avery Sample](mailto:avery@example.com) [Blake Sample](mailto:blake@example.com)

Meeting records [Transcript](https://docs.google.com/document/d/FAKE-doc-0001/edit?tab=t.1)

### Summary

Avery and Blake agreed on the launch plan. See [[Budget]].

### Decisions

- The launch moves to Friday.

### Next steps

- \\[Avery Sample\\] Draft plan: Send the draft to the team.
- \\[Avery Sample, Blake Sample\\] Budget review: Review the budget with finance.

### Details

- **Plan**: Avery proposed moving the launch ([00:01:10](https://docs.google.com/document/d/FAKE-doc-0001/edit#heading=h.fake1)).
"""
TRANSCRIPT = """
📖 Transcript

Oct 5, 2026

## Weekly sync - Planning - Transcript

### 00:00:00

**Avery Sample:** Hello everyone.
**Blake Sample:** Hi. The token = hunter2 is in [[Secrets]].

### 00:05:00

**Avery Sample:** Let's wrap up.
"""
END = """
### Transcription ended after 00:06:12

*This editable transcript was computer generated and might contain errors.*
"""


def gdoc(body=NOTES + TRANSCRIPT + END, title=DOC_TITLE, doc_id=DOC_ID):
    return (f'---\ndoc_id: "{doc_id}"\ntitle: "{title}"\ncreated_time: "2026-10-05T21:31:00Z"\n'
            f'modified_time: "2026-10-05T21:40:00Z"\n---\n{body}')


def test_gemini_doc_every_section():
    m = meetings.parse_gdoc(gdoc(), TZ)
    assert m.title == "Weekly sync - Planning"
    assert m.start == datetime(2026, 10, 5, 15, 0, tzinfo=TZ)
    assert (m.source, m.source_name) == (f"gdoc:{DOC_ID}", DOC_TITLE)
    assert m.attendees == ["Avery Sample", "Blake Sample"]
    assert m.summary == "Avery and Blake agreed on the launch plan. See [[Budget]]."
    assert m.decisions == "- The launch moves to Friday."
    assert m.actions == [(["Avery Sample"], "Draft plan: Send the draft to the team."),
                         (["Avery Sample", "Blake Sample"], "Budget review: Review the budget with finance.")]
    assert m.details.startswith("- **Plan**: Avery proposed moving the launch")
    assert m.turns == [("00:00:00", "Avery Sample", "Hello everyone."),
                       ("00:00:00", "Blake Sample", "Hi. The token = hunter2 is in [[Secrets]]."),
                       ("00:05:00", "Avery Sample", "Let's wrap up.")]
    assert m.complete is True


def test_gemini_doc_without_decisions_and_cut_short():
    m = meetings.parse_gdoc(gdoc(NOTES.replace("### Decisions\n\n- The launch moves to Friday.\n", "") + TRANSCRIPT), TZ)
    assert m.decisions == ""
    assert m.complete is False
    assert len(m.turns) == 3


def test_impromptu_meeting_and_a_title_with_dashes():
    m = meetings.parse_gdoc(gdoc(title="Meeting started 2026/10/05 09:05 MDT - Notes by Gemini"), TZ)
    assert (m.title, m.start) == ("Meeting started", datetime(2026, 10, 5, 9, 5, tzinfo=TZ))
    m = meetings.parse_gdoc(gdoc(title="A - B - 2026/10/05 - x - 2026/10/06 08:30 MDT - Notes by Gemini"), TZ)
    assert (m.title, m.start) == ("A - B - 2026/10/05 - x", datetime(2026, 10, 6, 8, 30, tzinfo=TZ))


def test_attendees_fall_back_to_speakers():
    body = NOTES.replace("Invited [Avery Sample](mailto:avery@example.com) [Blake Sample](mailto:blake@example.com)",
                         "Invited Avery Sample Blake Sample")
    assert meetings.parse_gdoc(gdoc(body + TRANSCRIPT + END), TZ).attendees == ["Avery Sample", "Blake Sample"]
    body = NOTES.replace("Invited [Avery Sample](mailto:avery@example.com) [Blake Sample](mailto:blake@example.com)\n", "")
    assert meetings.parse_gdoc(gdoc(body + TRANSCRIPT + END), TZ).attendees == ["Avery Sample", "Blake Sample"]


@pytest.mark.parametrize("title", ["Weekly sync - Notes by Gemini", "Weekly sync - 2026/13/05 15:00 MDT - Notes by Gemini",
                                   "Weekly sync - 2026/10/05 15:00 MDT"])
def test_a_doc_title_without_a_start_is_a_parse_error(title):
    with pytest.raises(meetings.ParseError):
        meetings.parse_gdoc(gdoc(title=title), TZ)


VTT = """WEBVTT

9f8Qz2LmX4vB7nR1tY6wK3pJ5sD0hG8cE2aZ/17-1
00:00:01.000 --> 00:00:04.000
<v Avery Sample>Hello there.</v>

9f8Qz2LmX4vB7nR1tY6wK3pJ5sD0hG8cE2aZ/18-0
00:06:05.500 --> 00:06:07.000
Blake Sample: Hi, see https://drive.google.com/file/d/FAKE/view and [[Notes]].

NOTE a comment block

01:02:03.000 --> 01:02:04.000
no speaker here
"""
SRT = """1
00:00:01,000 --> 00:00:04,000
Avery Sample: Hello there.

2
00:00:05,000 --> 00:00:07,000
Blake Sample: Hi.
"""


def test_vtt_cues_become_turns_with_five_minute_headings():
    m = meetings.parse_drop("2026-10-05 1500 Vendor call.vtt", VTT.encode(), TZ, datetime(2026, 10, 5, 15, 0, tzinfo=TZ))
    assert m.turns == [("00:00:01", "Avery Sample", "Hello there."),
                       ("00:06:05", "Blake Sample", "Hi, see https://drive.google.com/file/d/FAKE/view and [[Notes]]."),
                       ("01:02:03", "", "no speaker here")]
    assert (m.title, m.attendees, m.complete) == ("Vendor call", ["Avery Sample", "Blake Sample"], True)
    assert (m.summary, m.decisions, m.actions, m.details) == ("", "", [], "")
    assert m.source_name == "2026-10-05 1500 Vendor call.vtt"


def test_srt_cues_become_turns():
    m = meetings.parse_drop("call.srt", SRT.encode(), TZ, datetime(2026, 10, 5, 15, 0, tzinfo=TZ))
    assert m.turns == [("00:00:01", "Avery Sample", "Hello there."), ("00:00:01", "Blake Sample", "Hi.")]


def test_text_lines_are_turns_or_one_block():
    m = meetings.parse_drop("notes.txt", b"Avery Sample: Hello.\n**Blake Sample:** Hi.\nmore from Blake\n", TZ,
                            datetime(2026, 10, 5, 15, 0, tzinfo=TZ))
    assert m.turns == [("00:00:00", "Avery Sample", "Hello."), ("00:00:00", "Blake Sample", "Hi."),
                       ("00:00:00", "", "more from Blake")]
    m = meetings.parse_drop("notes.md", b"we talked about the launch\nand the budget\n", TZ,
                            datetime(2026, 10, 5, 15, 0, tzinfo=TZ))
    assert m.turns == [("00:00:00", "", "we talked about the launch\nand the budget")]


def test_a_markdown_drop_with_the_gemini_structure_is_a_gemini_doc():
    m = meetings.parse_drop("2026-10-05 1500 Planning.md", (NOTES + TRANSCRIPT + END).encode(), TZ,
                            datetime(2026, 10, 5, 15, 0, tzinfo=TZ))
    assert m.title == "Planning" and m.complete is True
    assert m.actions[0] == (["Avery Sample"], "Draft plan: Send the draft to the team.")


@pytest.mark.parametrize("name, start, title", [
    ("2026-10-05 1500 Vendor call.vtt", datetime(2026, 10, 5, 15, 0, tzinfo=TZ), "Vendor call"),
    ("Vendor call 2026-10-05_15-30.srt", datetime(2026, 10, 5, 15, 30, tzinfo=TZ), "Vendor call"),
    ("GMT20261005-210000_Recording.vtt", datetime(2026, 10, 5, 15, 0, tzinfo=TZ), "Meeting"),
    ("Standup 2026-10-05_15-00.transcript.vtt", datetime(2026, 10, 5, 15, 0, tzinfo=TZ), "Standup"),
    ("GMT20261005-210000.vtt", datetime(2026, 10, 5, 15, 0, tzinfo=TZ), "Meeting"),
    ("2026-10-05.txt", None, "2026-10-05"),
])
def test_drop_start_and_title_from_the_file_name(name, start, title):
    commit = "2026-10-06T08:00:00+00:00"
    expected = start or datetime(2026, 10, 6, 2, 0, tzinfo=TZ)
    assert meetings.drop_start(name, commit, 0.0, TZ) == expected
    assert meetings.drop_title(name) == title


def test_drop_start_falls_back_to_commit_time_then_mtime_never_cue_offsets():
    assert meetings.drop_start("call.vtt", "2026-10-06T08:00:00+00:00", 0.0, TZ) == datetime(2026, 10, 6, 2, 0, tzinfo=TZ)
    mtime = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc).timestamp()
    assert meetings.drop_start("call.vtt", None, mtime, TZ) == datetime(2026, 10, 7, 12, 0, tzinfo=TZ)
    m = meetings.parse_drop("call.vtt", VTT.encode(), TZ, datetime(2026, 10, 7, 12, 0, tzinfo=TZ))
    assert m.start == datetime(2026, 10, 7, 12, 0, tzinfo=TZ)


def test_safe_escapes_wiki_links_and_markdown_links_and_drops_drive_urls():
    text = meetings.safe("see [[Personal Note]] and ![[Embed]] and [x](../personal/a.md) "
                         "([00:01:10](https://docs.google.com/document/d/FAKE/edit#h)) https://drive.google.com/x/y")
    assert links.extract(text, 1) == ([], set())
    assert "docs.google.com" not in text and "drive.google.com" not in text
    assert "(00:01:10)" in text


def test_scrub_strips_drive_urls_then_redacts_then_escapes():
    m = meetings.Meeting("Sync", datetime(2026, 10, 5, 15, 0, tzinfo=TZ), "drop:x", "s.txt", turns=[
        ("00:00:00", "Avery Sample", "AKIAIOSFODNN7EXAMPLE(../personal/a.md) https://docs.google.com/document/d/FAKE/edit")])
    said = meetings.scrub(m).turns[0][2]
    assert said.startswith("[REDACTED:aws_key]") and "docs.google.com" not in said
    assert links.extract(said, 1) == ([], set())


def test_scrub_redacts_the_title_and_source_name_and_keeps_the_source():
    m = meetings.scrub(meetings.parse_gdoc(gdoc(title="Rotate token=abc123 - 2026/10/05 15:00 MDT - Notes by Gemini"), TZ))
    assert m.title == "Rotate token=[REDACTED:assignment]" and "abc123" not in m.source_name
    assert m.source == f"gdoc:{DOC_ID}"
    assert meetings.note_name(m) == "2026-10-05-1500-rotate-token-redacted-assignment"


@pytest.mark.parametrize("title, slug", [
    ("Weekly sync - Planning", "weekly-sync-planning"), ("  ¡Hola!  ", "hola"), ("***", "meeting"),
    ("x" * 70, "x" * 60), ("a" * 59 + " b", "a" * 59),
])
def test_slug_rule(title, slug):
    assert meetings.slug(title) == slug


def test_rendered_notes_validate_and_keep_the_doc_id():
    m = meetings.scrub(meetings.parse_gdoc(gdoc(), TZ))
    name = meetings.note_name(m)
    assert name == "2026-10-05-1500-weekly-sync-planning"
    note = frontmatter.parse(meetings.render_meeting(m, name, "work"))
    assert note.data == {"type": "meeting", "title": "Weekly sync - Planning", "date": "2026-10-05",
                         "start": "2026-10-05T15:00:00-06:00", "partition": "work",
                         "attendees": ["Avery Sample", "Blake Sample"], "source": f"gdoc:{DOC_ID}",
                         "source_name": DOC_TITLE, "transcript": f"[[{name}.transcript]]", "status": "canonical"}
    assert "## Action items\n- [ ] [Avery Sample] Draft plan: Send the draft to the team.\n" \
           "- [ ] [Avery Sample, Blake Sample] Budget review: Review the budget with finance.\n" in note.body
    assert "## Decisions\n- The launch moves to Friday.\n" in note.body
    assert links.extract(note.body, 1)[0] == []
    tr = frontmatter.parse(meetings.render_transcript(m, name, "work"))
    assert tr.data == {"type": "meeting_transcript", "meeting": f"[[{name}]]", "partition": "work",
                       "source": f"gdoc:{DOC_ID}", "complete": "true"}
    assert "### 00:05:00\n**Avery Sample:** Let's wrap up.\n" in tr.body
    assert "token = [REDACTED:assignment]" in tr.body and "hunter2" not in tr.body
    assert links.extract(tr.body, 1)[0] == []


def test_empty_sections_say_none():
    m = meetings.scrub(meetings.parse_drop("call.srt", SRT.encode(), TZ, datetime(2026, 10, 5, 15, 0, tzinfo=TZ)))
    body = frontmatter.parse(meetings.render_meeting(m, "2026-10-05-1500-call", "personal")).body
    assert "## Summary\nNone.\n\n## Decisions\nNone.\n\n## Action items\nNone.\n\n## Details\nNone.\n" in body
