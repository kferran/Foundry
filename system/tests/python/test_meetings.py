"""vaultlib/meetings.py: parsing Gemini Docs and dropped transcripts (meetings spec §2.3 step 1, §6)."""
import re
from dataclasses import replace
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


def as_gemini_writes_it(text):
    """The layout of real Docs (Plan 11 acceptance probe, 2026-10-06): every heading's text in bold, bullets
    indented two spaces, and a Quick notes block first whose level-2 Next steps repeats the actions."""
    text = re.sub(r"^(#{1,6}) (.+)$", r"\1 **\2**", text, flags=re.M)
    text = re.sub(r"^- ", "  - ", text, flags=re.M)
    quick = ("# **✍️ Quick notes**  \n\n## **Next steps**\n\n  - \\[Avery Sample\\] Draft plan: Send the draft.\n\n"
             "# **📝 Full notes***  \n\n")
    return quick + text.replace("📖 Transcript", "# **📖 Transcript***  ")


def test_gemini_doc_as_gemini_writes_it_parses_like_the_plain_layout():
    plain = meetings.parse_gdoc(gdoc(), TZ)
    real = meetings.parse_gdoc(gdoc(as_gemini_writes_it(NOTES + TRANSCRIPT + END)), TZ)
    # The real "# **📖 Transcript***" heading ends Details; the plain fixture's bare "📖 Transcript" line does not.
    assert real.details == plain.details.split("\n\n")[0]
    assert replace(real, details=plain.details) == plain


def test_topic_headings_inside_a_section_stay_in_it_as_bold_lines():
    body = NOTES.replace("### Decisions\n\n- The launch moves to Friday.\n",
                         "### **Decisions**\n\n## **Launch**\n\n  - **Date** The launch moves to Friday.\n\n"
                         "### **Pricing**\n\n  - **Tiers** Two tiers stay.\n")
    m = meetings.parse_gdoc(gdoc(body + "\n# **📖 Transcript***\n" + TRANSCRIPT + END), TZ)
    assert m.decisions == "**Launch**\n\n  - **Date** The launch moves to Friday.\n\n**Pricing**\n\n  - **Tiers** Two tiers stay."
    assert len(m.actions) == 2 and m.details.startswith("- **Plan**")


def test_gemini_doc_without_decisions_and_cut_short():
    m = meetings.parse_gdoc(gdoc(NOTES.replace("### Decisions\n\n- The launch moves to Friday.\n", "") + TRANSCRIPT), TZ)
    assert m.decisions == ""
    assert m.complete is False
    assert len(m.turns) == 3


NOT_PRODUCED = """📝 Notes

Oct 9, 2026

## Weekly sync - Planning

### Summary

A summary wasn't produced for this meeting because there wasn't enough conversation in a supported language.

If the meeting was transcribed, you can review the transcript linked in the meeting records section of this document.

[Visit the help center for troubleshooting information](https://support.google.com/meet?p=tnfm_troubleshooting)

### Details

Details weren't produced for this meeting.
"""
FOOTER = """

*You should review Gemini's notes to make sure they're accurate.* [*Get tips and learn how Gemini takes notes*](https://support.google.com/meet/answer/14754931)

*How is the quality of* ***these specific notes?*** [*Take a short survey*](https://example.com/survey) *to let us know your feedback*
"""


def test_googles_not_produced_notice_is_not_meeting_content():
    m = meetings.parse_gdoc(gdoc(NOT_PRODUCED + TRANSCRIPT + END), TZ)
    assert (m.summary, m.decisions, m.details, m.actions) == ("", "", "", [])
    assert len(m.turns) == 3 and m.complete is True


def test_a_doc_with_no_notes_and_no_transcript_is_a_parse_error():
    with pytest.raises(meetings.ParseError, match="no notes and no transcript"):
        meetings.parse_gdoc(gdoc(NOT_PRODUCED), TZ)
    with pytest.raises(meetings.ParseError, match="no notes and no transcript"):
        meetings.parse_drop("sync.md", (NOT_PRODUCED + "\n## Weekly sync - Transcript\n").encode(), TZ,
                            datetime(2026, 10, 9, 10, 0, tzinfo=TZ))


def test_the_review_and_survey_footer_is_dropped_from_a_full_doc():
    m = meetings.parse_gdoc(gdoc(NOTES + FOOTER + TRANSCRIPT + END), TZ)
    assert m.details == "- **Plan**: Avery proposed moving the launch ([00:01:10](https://docs.google.com/document/d/FAKE-doc-0001/edit#heading=h.fake1))."
    assert "Gemini" not in m.details and "survey" not in m.details


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


@pytest.mark.parametrize("when, start", [("15:00 MDT", "2026-10-05T15:00:00-06:00"),
                                         ("15:00 CDT", "2026-10-05T14:00:00-06:00"),
                                         ("15:00 MST", "2026-10-05T16:00:00-06:00"),
                                         ("00:30 EDT", "2026-10-04T22:30:00-06:00"),
                                         ("15:00 IST", "2026-10-05T15:00:00-06:00")])
def test_the_title_zone_sets_the_start_when_it_is_known(when, start):
    m = meetings.parse_gdoc(gdoc(title=f"Weekly sync - 2026/10/05 {when} - Notes by Gemini"), TZ)
    assert m.start.isoformat() == start
    assert m.start.tzinfo == TZ


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


def test_a_utf16_drop_parses_like_its_utf8_twin():
    start = datetime(2026, 10, 5, 15, 0, tzinfo=TZ)
    text = "Avery Sample: Hello.\n**Blake Sample:** Hi.\n"
    twin = meetings.parse_drop("notes.txt", text.encode(), TZ, start).turns
    assert meetings.parse_drop("notes.txt", text.encode("utf-16"), TZ, start).turns == twin
    assert meetings.parse_drop("notes.txt", b"\xfe\xff" + text.encode("utf-16-be"), TZ, start).turns == twin
    assert (meetings.parse_drop("call.vtt", VTT.encode("utf-16"), TZ, start).turns
            == meetings.parse_drop("call.vtt", VTT.encode(), TZ, start).turns)
    with pytest.raises(meetings.ParseError, match="not UTF-8 text"):
        meetings.parse_drop("notes.txt", text.encode("utf-16-le"), TZ, start)  # no byte-order mark


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


@pytest.mark.parametrize("said", ["[[[Foo]]", "[[[[x]]]]", "a [[[b]] [[c]]", "[ [[d]]"])
def test_safe_escapes_runs_of_brackets(said):
    assert links.extract(meetings.safe(said), 1) == ([], set())


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


# -- import (meetings spec §2.3 steps 2-9) -------------------------------------------------------
import fcntl  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from helpers import meeting, write  # noqa: E402
from test_intake import calls, iv, later  # noqa: E402,F401  (iv is a fixture)
from vaultlib import publish  # noqa: E402
from vaultlib.intake import Intake  # noqa: E402

NAME = "2026-10-05-1500-weekly-sync-planning"
HOURS = 3600


def fetched(vault, doc_id=DOC_ID, **kw):
    return write(vault, f"raw/meetings/{doc_id}.gdoc.md", gdoc(doc_id=doc_id, **kw))


def dropped(vault, rel, text, age=HOURS):
    path = write(vault, f"meetings/drop/{rel}", text)
    os.utime(path, (later() - age, later() - age))
    return path


def tick(vault, **kw):
    Intake(vault, now=later(), **kw).import_meetings()


def runs(vault):
    return [json.loads(line) for p in sorted((vault / "system/logs").glob("runs-*.jsonl"))
            for line in p.read_text().splitlines()]


def meeting_runs(vault):
    return [r for r in runs(vault) if r.get("command") == "meeting"]


def solo(vault):
    path = vault / "system/logs/intake_solo.json"
    return set(json.loads(path.read_text())) if path.exists() else set()


def sha(path):
    return publish.sha256_file(path)


def alerts(vault):
    return "".join(p.read_text() for p in (vault / "system/logs").glob("alerts_*.md"))


def config(vault, **keys):
    keys = {"timezone": "America/Denver", "brief_time": "06:00", "debrief_time": "17:00", "remote_mode": "none",
            "default_partition": "personal", **keys}
    write(vault, "system/config.md", "---\ntype: config\n" + "".join(f'{k}: "{v}"\n' for k, v in keys.items()) + "---\n")


def test_a_fetched_doc_is_published_as_a_meeting_run_and_handed_to_compile(iv):
    config(iv, meetings_partition="work")
    src = fetched(iv)
    tick(iv)
    note, tr = (iv / f"wiki/work/meetings/{NAME}.md"), (iv / f"wiki/work/meetings/{NAME}.transcript.md")
    assert frontmatter.parse(note.read_text()).data["provenance"] == ["headless"]
    assert frontmatter.parse(tr.read_text()).data["complete"] == "true"
    [run] = meeting_runs(iv)
    assert run["run_id"].split("-")[1:3] == ["meeting", run["run_id"][-4:]] and run["partition"] == "work"
    assert run["inputs"] == [f"raw/meetings/{DOC_ID}.gdoc.md"] and run["exit"] == 0
    assert run["publish"] == {"status": "published", "published": [f"wiki/work/meetings/{NAME}.md",
                              f"wiki/work/meetings/{NAME}.transcript.md"], "rejected": [], "conflicts": []}
    assert {"started_at", "finished_at"} <= set(run)
    report = json.loads((iv / "system/logs/runs" / run["run_id"] / "publish.json").read_text())
    assert report["status"] == "published"
    inp = iv / f"raw/work/notes/{NAME}.meeting-input.md"
    data = frontmatter.parse(inp.read_text()).data
    assert (data["type"], data["meeting"], data["partition"]) == ("meeting_input", f"[[{NAME}]]", "work")
    assert solo(iv) == {sha(inp)}
    assert not src.exists()


def test_the_doc_id_survives_redaction_and_a_secret_in_the_body_does_not(iv):
    doc_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_ab"
    fetched(iv, doc_id=doc_id)
    tick(iv)
    note = (iv / f"wiki/personal/meetings/{NAME}.md").read_text()
    assert frontmatter.parse(note).data["source"] == f"gdoc:{doc_id}"
    tr = (iv / f"wiki/personal/meetings/{NAME}.transcript.md").read_text()
    assert "hunter2" not in tr and "[REDACTED:assignment]" in tr


@pytest.mark.parametrize("keys, partition", [({}, "personal"), ({"default_partition": "work"}, "work"),
                                             ({"default_partition": "shared"}, "personal"),
                                             ({"meetings_partition": "work", "default_partition": "personal"}, "work")])
def test_a_fetched_doc_goes_to_meetings_partition_or_the_default(iv, keys, partition):
    if keys:
        config(iv, **keys)
    fetched(iv)
    tick(iv)
    assert (iv / f"wiki/{partition}/meetings/{NAME}.md").is_file()


def test_a_drop_is_imported_into_its_folder_partition_and_deleted(iv):
    src = dropped(iv, "work/2026-10-05 1500 Vendor call.vtt", VTT)
    digest = sha(src)
    tick(iv)
    name = "2026-10-05-1500-vendor-call"
    data = frontmatter.parse((iv / f"wiki/work/meetings/{name}.md").read_text()).data
    assert data["source"] == f"drop:{digest}"
    assert data["source_name"] == "2026-10-05 1500 Vendor call.vtt"
    assert (iv / f"raw/work/notes/{name}.meeting-input.md").is_file()
    assert not src.exists()


def test_two_drops_with_the_same_file_name_stay_apart(iv):
    dropped(iv, "work/transcript.vtt", VTT, age=10 * HOURS)
    tick(iv)
    dropped(iv, "work/transcript.vtt", VTT.replace("Hello there.", "Hello again."), age=2 * HOURS)
    tick(iv)
    notes = sorted(p.name for p in (iv / "wiki/work/meetings").glob("*.md") if not p.name.endswith(".transcript.md"))
    assert len(notes) == 2 and len({frontmatter.parse((iv / "wiki/work/meetings" / n).read_text()).data["source"]
                                    for n in notes}) == 2


def test_a_young_drop_waits(iv):
    dropped(iv, "work/call.vtt", VTT, age=10)
    tick(iv)
    assert meeting_runs(iv) == [] and (iv / "meetings/drop/work/call.vtt").exists()


def test_first_source_wins_a_drop_after_a_doc_is_archived(iv):
    config(iv, meetings_partition="work")
    fetched(iv)
    tick(iv)
    dup = dropped(iv, "work/2026-10-05 1510 Weekly sync - Planning.vtt", VTT)
    tick(iv)
    assert len(meeting_runs(iv)) == 1 and not dup.exists()
    assert (iv / "raw/archive" / dup.name).is_file()
    assert f"wiki/work/meetings/{NAME}.md" in alerts(iv)


def test_first_source_wins_a_doc_after_a_drop_is_archived_and_skipped_by_the_fetch(iv):
    dropped(iv, "work/2026-10-05 1505 Weekly sync - Planning.vtt", VTT)
    tick(iv)
    config(iv, meetings_partition="work")
    fetched(iv)
    tick(iv)
    assert len(meeting_runs(iv)) == 1
    assert (iv / f"raw/archive/{DOC_ID}.gdoc.md").is_file()
    log = [json.loads(line) for p in (iv / "system/logs").glob("meetings_fetch-*.jsonl") for line in p.read_text().splitlines()]
    assert [(r["doc"], r["skipped"]) for r in log] == [(DOC_ID, True)]


def test_two_docs_with_the_same_title_minutes_apart_are_two_meetings(iv):
    config(iv, meetings_partition="work")
    fetched(iv, doc_id="FAKE-doc-a", title="Meeting started 2026/10/05 10:00 MDT - Notes by Gemini")
    tick(iv)
    fetched(iv, doc_id="FAKE-doc-b", title="Meeting started 2026/10/05 10:12 MDT - Notes by Gemini")
    tick(iv)
    assert len(meeting_runs(iv)) == 2
    assert not list((iv / "raw/archive").glob("*.gdoc.md"))


def test_a_name_taken_by_another_meeting_gets_a_suffix(iv):
    config(iv, meetings_partition="work")
    write(iv, f"wiki/work/meetings/{NAME}.md", meeting("work", NAME, "Weekly sync - Planning",
                                                         start='"2026-10-05T09:00:00-06:00"', source='"drop:other"'))
    fetched(iv)
    tick(iv)
    assert (iv / f"wiki/work/meetings/{NAME}-2.md").is_file()
    assert (iv / f"wiki/work/meetings/{NAME}-2.transcript.md").is_file()


def test_a_crash_after_publish_is_completed_by_the_next_tick(iv, monkeypatch):
    config(iv, meetings_partition="work")
    src = fetched(iv)
    real = meetings.render_input
    monkeypatch.setattr(meetings, "render_input", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    tick(iv)
    assert (iv / f"wiki/work/meetings/{NAME}.md").is_file() and src.exists()
    monkeypatch.setattr(meetings, "render_input", real)
    tick(iv)
    assert len(meeting_runs(iv)) == 1 and not src.exists()
    assert (iv / f"raw/work/notes/{NAME}.meeting-input.md").is_file()


def test_an_input_already_handed_over_is_not_written_again(iv):
    config(iv, meetings_partition="work")
    fetched(iv)
    tick(iv)
    inp = iv / f"raw/work/notes/{NAME}.meeting-input.md"
    (iv / "raw/work/archive").mkdir()
    inp.rename(iv / f"raw/work/archive/{NAME}.meeting-input-1.md")
    fetched(iv)
    tick(iv)
    assert not inp.exists() and not (iv / f"raw/meetings/{DOC_ID}.gdoc.md").exists()


def test_a_target_created_during_the_run_is_not_a_failure(iv, monkeypatch):
    config(iv, meetings_partition="work")
    src = fetched(iv)
    real = publish.commit_run

    def racing(vault, run_id, now=None):
        write(vault, f"wiki/work/meetings/{NAME}.md", "someone else\n")
        return real(vault, run_id, now)
    monkeypatch.setattr(publish, "commit_run", racing)
    tick(iv)
    assert src.exists() and not (iv / "system/quarantine/meetings").exists()
    assert meeting_runs(iv)[0]["publish"]["status"] == "rejected"


def test_a_target_changed_at_apply_time_leaves_the_source_for_the_next_tick(iv, monkeypatch):
    config(iv, meetings_partition="work")
    src = fetched(iv)
    real = publish._apply
    transcript = f"wiki/work/meetings/{NAME}.transcript.md"

    def racing(vault, journal):  # an edit lands between validation and apply
        write(vault, transcript, "someone else\n")
        return real(vault, journal)
    monkeypatch.setattr(publish, "_apply", racing)
    tick(iv)
    assert src.exists() and not (iv / "system/quarantine/meetings").exists()
    assert meeting_runs(iv)[0]["publish"]["status"] == "conflict"
    assert f"held back {transcript}" in alerts(iv)
    monkeypatch.setattr(publish, "_apply", real)
    tick(iv)
    assert not src.exists() and (iv / f"raw/work/notes/{NAME}.meeting-input.md").is_file()


def meeting_log(vault):
    return [json.loads(line) for p in sorted((vault / "system/logs").glob("meetings-*.jsonl"))
            for line in p.read_text().splitlines()]


def test_a_crash_before_the_imported_line_is_logged_by_the_next_tick(iv, monkeypatch):
    config(iv, meetings_partition="work")
    fetched(iv, body=NOTES + TRANSCRIPT)  # no end marker: complete is false
    real = Intake._meeting_log

    def dies_once(self, record):
        if record.get("kind") == "imported":
            raise OSError("killed")
        real(self, record)
    monkeypatch.setattr(Intake, "_meeting_log", dies_once)
    tick(iv)
    assert [r for r in meeting_log(iv) if r["kind"] == "imported"] == []
    monkeypatch.setattr(Intake, "_meeting_log", real)
    tick(iv)
    tick(iv)
    [line] = [r for r in meeting_log(iv) if r["kind"] == "imported"]
    assert (line["note"], line["complete"]) == (f"wiki/work/meetings/{NAME}.md", False)


def test_a_bad_source_is_quarantined_and_the_rest_continue(iv):
    config(iv, meetings_partition="work")
    bad = fetched(iv, doc_id="FAKE-doc-bad", title="Weekly sync - Notes by Gemini")
    odd = dropped(iv, "work/slides.pdf", "x")
    fetched(iv)
    tick(iv)
    q = iv / "system/quarantine/meetings"
    assert sorted(p.name for p in q.iterdir()) == ["FAKE-doc-bad.gdoc.md", "FAKE-doc-bad.gdoc.md.reason.txt",
                                                   "slides.pdf", "slides.pdf.reason.txt"]
    assert "no start date" in (q / "FAKE-doc-bad.gdoc.md.reason.txt").read_text()
    assert not bad.exists() and not odd.exists()
    assert (iv / f"wiki/work/meetings/{NAME}.md").is_file()
    assert "quarantined" in alerts(iv)
    log = [json.loads(line) for p in (iv / "system/logs").glob("meetings-*.jsonl") for line in p.read_text().splitlines()]
    assert sorted(r["kind"] for r in log) == ["imported", "quarantined", "quarantined"]


def test_a_restored_input_gets_its_solo_flag_back(iv):
    inp = write(iv, f"raw/work/notes/{NAME}.meeting-input.md",
                f'---\ntype: meeting_input\nmeeting: "[[{NAME}]]"\npartition: work\n'
                f'created_at: "2026-10-05T16:05:00-06:00"\n---\nx\n')
    tick(iv)
    assert solo(iv) == {sha(inp)}


def test_a_busy_run_lock_or_a_client_does_nothing(iv):
    src = fetched(iv)
    with open(iv / "system/run.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        tick(iv)
    assert src.exists() and meeting_runs(iv) == []
    config(iv, machine_role="client")
    tick(iv)
    assert src.exists() and meeting_runs(iv) == []


def test_intake_imports_before_compiling_and_ingests_the_input_alone(iv):
    dropped(iv, "work/2026-10-05 1500 Vendor call.vtt", VTT)
    from test_intake_digests import digest
    digest(iv, "work", "d1")
    Intake(iv, now=later()).run()
    assert sorted(c["args"][1:] for c in calls(iv)) == [["raw/work/notes/2026-10-05-1500-vendor-call.meeting-input.md"],
                                                       ["raw/work/notes/d1.md"]]


def test_the_import_run_is_committed_under_its_title(iv):
    config(iv, meetings_partition="work", machine_role="server")
    fetched(iv)
    tick(iv)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base",
                                                 "--", "system/schemas"]):
        subprocess.run(["git", "-C", str(iv), *args], check=True, capture_output=True)
    write(iv, "system/logs/commit_runs.since", "20000101T000000\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    p = subprocess.run([sys.executable, str(iv / "system/scripts/commit_runs.py")], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    subject = subprocess.run(["git", "-C", str(iv), "log", "-1", "--format=%s"], capture_output=True, text=True).stdout
    assert subject.strip() == "meeting(work): Weekly sync - Planning"


def test_meeting_import_script_runs_one_tick(iv):
    config(iv, meetings_partition="work")
    fetched(iv)
    p = subprocess.run([sys.executable, str(iv / "system/scripts/meeting_import.py")], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert (iv / f"wiki/work/meetings/{NAME}.md").is_file()


def test_a_note_whose_start_has_no_offset_is_read_in_the_config_timezone(iv):
    write(iv, "wiki/work/meetings/2026-10-05-1505-vendor-call.md",
          meeting("work", "2026-10-05-1505-vendor-call", "Vendor call", start='"2026-10-05T15:05:00"', source='"drop:other"'))
    src = dropped(iv, "work/2026-10-05 1500 Vendor call.vtt", VTT)
    tick(iv)
    assert meeting_runs(iv) == [] and not src.exists() and (iv / "raw/archive" / src.name).is_file()


@pytest.mark.parametrize("name, text", [("Untitled.md", ""), ("call.vtt", "WEBVTT\n\n"), ("notes.txt", " \n\n ")])
def test_a_drop_with_no_transcript_text_is_quarantined_not_published(iv, name, text):
    dropped(iv, f"work/{name}", text)
    tick(iv)
    assert meeting_runs(iv) == []
    assert "no transcript text" in (iv / "system/quarantine/meetings" / f"{name}.reason.txt").read_text()


def test_a_drop_of_nul_bytes_is_quarantined_as_not_utf8(iv):
    dropped(iv, "work/notes.txt", "\x00" * 8)
    tick(iv)
    assert meeting_runs(iv) == []
    assert "not UTF-8 text" in (iv / "system/quarantine/meetings/notes.txt.reason.txt").read_text()


def test_a_source_that_keeps_failing_is_quarantined_on_the_third_tick(iv, monkeypatch):
    src = dropped(iv, "work/2026-10-05 1500 Vendor call.vtt", VTT)
    monkeypatch.setattr(meetings, "render_meeting", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    tick(iv)
    tick(iv)
    assert src.exists()
    tick(iv)
    assert not src.exists()
    reason = (iv / "system/quarantine/meetings" / f"{src.name}.reason.txt").read_text()
    assert "failed 3 times" in reason and "boom" in reason


def test_an_import_error_outside_a_source_is_alerted_and_intake_goes_on(iv, monkeypatch):
    monkeypatch.setattr(Intake, "_meeting_sources", lambda self: 1 / 0)
    write(iv, "raw/inbox/note.md", "plain note\n")
    Intake(iv, now=later()).run()
    assert [c["args"][1] for c in calls(iv)] == ["raw/inbox/.staging/note.md"]
    assert "meeting import failed (ZeroDivisionError" in alerts(iv)


def test_drops_outside_a_partition_folder_are_quarantined_at_any_depth(iv):
    for rel in ("call.vtt", "team/call.vtt", "work/old/call.vtt"):
        dropped(iv, rel, VTT)
    tick(iv)
    held = [p for p in (iv / "system/quarantine/meetings").iterdir() if not p.name.endswith(".reason.txt")]
    assert len(held) == 3 and meeting_runs(iv) == []
    assert list((iv / "meetings/drop").rglob("*.vtt")) == []


def test_a_drop_without_a_start_in_its_name_starts_at_its_commit_time(iv):
    dropped(iv, "work/Vendor call.vtt", VTT)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_COMMITTER_DATE": "2026-10-02T16:30:00-06:00"}
    for args in (["init", "-q"], ["add", "meetings"], ["commit", "-qm", "drop"]):
        subprocess.run(["git", "-C", str(iv), *args], check=True, capture_output=True, env=env)
    tick(iv)
    assert (iv / "wiki/work/meetings/2026-10-02-1630-vendor-call.md").is_file()


def test_the_manual_import_does_nothing_while_intake_runs(iv):
    src = fetched(iv)
    with open(iv / "system/intake.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        p = subprocess.run([sys.executable, str(iv / "system/scripts/meeting_import.py")], capture_output=True, text=True)
    assert p.returncode == 0 and "intake is running" in p.stderr
    assert src.exists() and meeting_runs(iv) == []
