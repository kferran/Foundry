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


def test_the_users_open_actions_first_then_everyone_elses_by_owner(av):
    name = "2026-10-05-1500-weekly-sync"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    write(av, f"wiki/work/meetings/{name}.transcript.md", transcript("work", name, "- [ ] [Avery Sample] Not a note."))
    text = actions(av)
    assert text.startswith("# Meeting actions for 2026-10-06\n")
    assert section(text, "Yours") == [
        f"- [Avery Sample] Draft plan: Send the draft. ([[{name}]], 1 day open)",
        f"- [Blake Sample, avery sample] Budget review: Review the budget. ([[{name}]], 1 day open)"]
    assert section(text, "Waiting on") == [
        "### Avery Samples", f"- Lookalike: Not the user. ([[{name}]], 2026-10-05)",
        "### Blake Sample", f"- Slides: Prepare the slides. ([[{name}]], 2026-10-05)",
        "### Unassigned", f"- Unowned: Someone should follow up. ([[{name}]], 2026-10-05)"]


def test_others_actions_drop_off_after_14_days_and_the_users_stay(av):
    old = "2026-09-20-0900-kickoff"
    write(av, f"wiki/personal/meetings/{old}.md", meeting("personal", old, "Kickoff", body=ACTIONS))
    text = actions(av)
    assert len(section(text, "Yours")) == 2 and "16 days open" in section(text, "Yours")[0]
    assert section(text, "Waiting on") == ["None."]
    assert len(section(actions(av, "2026-10-04"), "Waiting on")) == 6


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
