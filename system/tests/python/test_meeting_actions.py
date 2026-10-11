"""meeting_actions.py: the brief's open action items and meeting notices (meetings spec §2.5)."""
import json
import shutil
import subprocess
import sys

import pytest

from helpers import REPO, meeting, transcript, write

ACTIONS = """## Summary
None.

## Action items
- [ ] [Avery Sample] Draft plan: Send the draft.
- [x] [Avery Sample] Book room: Done already.
- [ ] [Blake Sample, avery sample] Budget review: Review the budget.
- [ ] [Blake Sample] Slides: Prepare the slides.
- [ ] [Avery Samples] Lookalike: Not the user.
- [ ] Unowned: Someone should follow up.

## Details
- [ ] [Avery Sample] Not an action: outside the section.
"""


@pytest.fixture
def av(vault):
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\n'
          'debrief_time: "17:00"\nremote_mode: "none"\ndefault_partition: "personal"\n'
          'owner_names: ["AVERY SAMPLE", "Avery S."]\n---\n')
    return vault


def actions(vault, date="2026-10-06"):
    p = subprocess.run([sys.executable, str(vault / "system/scripts/meeting_actions.py"), date],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def section(text, heading):
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line == f"## {heading}"
            continue
        if on and line.strip():
            out.append(line)
    return out


def imported(vault, note, when):
    rec = {"time": when, "kind": "imported", "source": "raw/meetings/x.gdoc.md", "note": note, "complete": True}
    path = vault / f"system/logs/meetings-{when[:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def brief(vault, day):
    write(vault, f"briefings/{day}.md", f'---\ntype: briefing\ndate: "{day}"\nstatus: active\n---\n')


def test_the_users_open_actions_first_then_everyone_elses_by_owner(av):
    name = "2026-10-05-1500-weekly-sync"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    write(av, f"wiki/work/meetings/{name}.transcript.md", transcript("work", name, "- [ ] [Avery Sample] Not a note."))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-05T16:00:00-06:00")
    text = actions(av)
    assert text.startswith("# Meeting actions for 2026-10-06\n")
    assert section(text, "Yours") == [
        f"- [Avery Sample] Draft plan: Send the draft. ([[{name}]], 1 day open)",
        f"- [Blake Sample, avery sample] Budget review: Review the budget. ([[{name}]], 1 day open)"]
    assert section(text, "Waiting on") == [
        "### Avery Samples", f"- Lookalike: Not the user. ([[{name}]], 2026-10-05)",
        "### Blake Sample", f"- Slides: Prepare the slides. ([[{name}]], 2026-10-05)",
        "### Unassigned", f"- Unowned: Someone should follow up. ([[{name}]], 2026-10-05)"]


def test_waiting_on_lists_only_what_was_imported_since_the_previous_weekday_brief(av):
    brief(av, "2026-10-05")  # Monday, run at 06:00 America/Denver
    before, after = "2026-10-02-0900-friday", "2026-10-05-1500-monday"
    for name in (before, after):
        write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{before}.md", "2026-10-05T05:30:00-06:00")
    imported(av, f"wiki/work/meetings/{after}.md", "2026-10-05T16:00:00-06:00")
    waiting = section(actions(av, "2026-10-06"), "Waiting on")
    assert f"[[{after}]]" in "".join(waiting) and f"[[{before}]]" not in "".join(waiting)
    assert len(section(actions(av, "2026-10-06"), "Yours")) == 4  # the user's own, any age


def test_a_friday_meeting_imported_monday_morning_prints_on_tuesday(av):
    brief(av, "2026-10-05")
    name = "2026-10-02-1730-late-friday"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-05T08:00:00-06:00")
    assert f"[[{name}]]" in "".join(section(actions(av, "2026-10-06"), "Waiting on"))


def test_a_weekend_brief_lists_no_waiting_on_and_monday_covers_since_friday(av):
    brief(av, "2026-10-09")  # Friday
    name = "2026-10-09-1500-friday"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-09T16:00:00-06:00")
    assert section(actions(av, "2026-10-10"), "Waiting on") == ["None."]
    assert section(actions(av, "2026-10-11"), "Waiting on") == ["None."]
    assert f"[[{name}]]" in "".join(section(actions(av, "2026-10-12"), "Waiting on"))


def test_no_earlier_briefing_uses_a_seven_day_window(av):
    old, recent = "2026-09-27-0900-old", "2026-10-01-0900-recent"
    for name in (old, recent):
        write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{old}.md", "2026-09-28T10:00:00-06:00")
    imported(av, f"wiki/work/meetings/{recent}.md", "2026-10-01T10:00:00-06:00")
    waiting = "".join(section(actions(av, "2026-10-06"), "Waiting on"))
    assert f"[[{recent}]]" in waiting and f"[[{old}]]" not in waiting


def test_an_imported_note_that_is_gone_or_deprecated_is_skipped(av):
    brief(av, "2026-10-05")
    gone, dep = "2026-10-05-0900-gone", "2026-10-05-1000-dep"
    write(av, f"wiki/work/meetings/{dep}.md", meeting("work", dep, body=ACTIONS, status="deprecated"))
    imported(av, f"wiki/work/meetings/{gone}.md", "2026-10-05T16:00:00-06:00")
    imported(av, f"wiki/work/meetings/{dep}.md", "2026-10-05T16:00:00-06:00")
    assert section(actions(av, "2026-10-06"), "Waiting on") == ["None."]


def test_a_bare_first_name_joins_the_one_full_name_that_starts_with_it(av):
    brief(av, "2026-10-05")
    name = "2026-10-05-1500-sync"
    body = ("## Action items\n- [ ] [Gavin] Send link: Send the link.\n- [ ] [Gavin Sample] Fix 1133: Fix it.\n"
            "- [ ] [Blake] Spec: Update the spec.\n- [ ] [Blake Sample] Deck: Make the deck.\n"
            "- [ ] [Blake Samples] Other: Another Blake.\n")
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=body))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-05T16:00:00-06:00")
    waiting = section(actions(av, "2026-10-06"), "Waiting on")
    assert waiting.count("### Gavin Sample") == 1 and "### Gavin" not in waiting
    assert "### Blake" in waiting  # two full names start with Blake: left as written


def test_deprecated_meetings_are_ignored(av):
    name = "2026-10-05-1500-weekly-sync"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS, status="deprecated"))
    text = actions(av)
    assert section(text, "Yours") == ["None."] and section(text, "Waiting on") == ["None."]


def test_notices_from_the_last_7_days(av):
    records = [
        {"time": "2026-10-05T16:00:00-06:00", "kind": "imported", "source": "raw/meetings/FAKE-a.gdoc.md",
         "note": "wiki/work/meetings/a.md", "complete": False},
        {"time": "2026-10-05T16:00:00-06:00", "kind": "imported", "source": "raw/meetings/FAKE-b.gdoc.md",
         "note": "wiki/work/meetings/b.md", "complete": True},
        {"time": "2026-10-04T10:00:00-06:00", "kind": "quarantined", "source": "meetings/drop/work/x.pdf",
         "file": "x.pdf", "reason": "not a transcript file type (.vtt, .srt, .txt, .md)"},
        {"time": "2026-10-03T10:00:00-06:00", "kind": "duplicate", "source": "meetings/drop/work/s.vtt",
         "note": "wiki/work/meetings/a.md"},
        {"time": "2026-09-20T10:00:00-06:00", "kind": "quarantined", "source": "raw/meetings/FAKE-old.gdoc.md",
         "file": "FAKE-old.gdoc.md", "reason": "old"},
    ]
    write(av, "system/logs/meetings-2026-10.jsonl", "".join(json.dumps(r) + "\n" for r in records[:4]))
    write(av, "system/logs/meetings-2026-09.jsonl", json.dumps(records[4]) + "\nnot json\n")
    assert section(actions(av), "Notices") == [
        "- wiki/work/meetings/a.md was imported from a transcript cut short (complete: false).",
        "- Quarantined meeting source x.pdf: not a transcript file type (.vtt, .srt, .txt, .md). "
        "It is in system/quarantine/meetings/.",
        "- meetings/drop/work/s.vtt was archived: the same meeting is already wiki/work/meetings/a.md."]


def test_no_meetings_gives_empty_sections(av):
    text = actions(av)
    assert [section(text, h) for h in ("Yours", "Waiting on", "Notices")] == [["None."]] * 3


def test_a_bad_date_exits_2(av):
    p = subprocess.run([sys.executable, str(av / "system/scripts/meeting_actions.py"), "2026-13-01"],
                       capture_output=True, text=True)
    assert p.returncode == 2 and "invalid date" in p.stderr
