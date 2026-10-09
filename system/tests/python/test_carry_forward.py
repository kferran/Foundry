"""carry_forward.py: open objectives from the latest earlier briefing carry into today's brief."""
import subprocess
import sys

from helpers import REPO, write

SCRIPT = REPO / "system" / "scripts" / "carry_forward.py"


def briefing(objectives: str, extra: str = "") -> str:
    return ("---\ntype: briefing\ndate: \"x\"\nstatus: active\n---\n\n# Daily Briefing\n\n## 🌅 Morning Alignment (06:00)\n\n"
            "### 1. Active Objectives & Context Boundaries\n\n**Objectives**\n" + objectives +
            "\n### 2. Unavailable Sources\n- None.\n" + extra)


def run(vault, date):
    return subprocess.run([sys.executable, str(SCRIPT), date], cwd=vault, capture_output=True, text=True)


def test_open_items_carry_with_their_first_date(vault):
    write(vault, "briefings/2026-10-06.md", briefing(
        "- [ ] **Ask EDJ** about the 409.\n"
        "- [x] **Done thing.**\n"
        "- [-] **Dropped thing** (no longer needed).\n"
        "- [ ] **Old item** _(open since 2026-10-01)_\n"))
    out = run(vault, "2026-10-07")
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == [
        "- [ ] **Ask EDJ** about the 409. _(open since 2026-10-06)_",
        "- [ ] **Old item** _(open since 2026-10-01)_",
    ]


def test_a_stamp_with_an_age_keeps_its_date_and_two_stamps_keep_the_earlier(vault):
    write(vault, "briefings/2026-10-08.md", briefing(   # the brief adds the age; #84
        "- [ ] **Aged** _(open since 2026-10-06, 2 days)_\n"
        "- [ ] **Doubled** _(open since 2026-10-06, 1 day)_ _(open since 2026-10-07)_\n"))
    assert run(vault, "2026-10-09").stdout.splitlines() == [
        "- [ ] **Aged** _(open since 2026-10-06)_",
        "- [ ] **Doubled** _(open since 2026-10-06)_",
    ]


def test_skipped_days_look_further_back_and_debriefs_are_ignored(vault):
    write(vault, "briefings/2026-10-03.md", briefing("- [ ] **Friday item**\n"))
    write(vault, "briefings/2026-10-05.debrief.md", "- [ ] not an objective\n")
    out = run(vault, "2026-10-06")
    assert out.stdout.splitlines() == ["- [ ] **Friday item** _(open since 2026-10-03)_"]


def test_an_archived_briefing_still_carries(vault):
    write(vault, "briefings/archive/2026-10/2026-10-06.md", briefing("- [ ] **Archived item**\n"))
    assert run(vault, "2026-10-07").stdout.splitlines() == ["- [ ] **Archived item** _(open since 2026-10-06)_"]


def test_only_the_objectives_section_counts(vault):
    write(vault, "briefings/2026-10-06.md", briefing("- [ ] **Real**\n", extra="\n## Notes\n- [ ] a checkbox elsewhere\n"))
    assert run(vault, "2026-10-07").stdout.splitlines() == ["- [ ] **Real** _(open since 2026-10-06)_"]


def test_no_earlier_briefing_prints_nothing(vault):
    write(vault, "briefings/2026-10-07.md", briefing("- [ ] **Today, not earlier**\n"))
    out = run(vault, "2026-10-07")
    assert out.returncode == 0 and out.stdout == ""


def test_bad_date_exits_2(vault):
    assert run(vault, "yesterday").returncode == 2


def test_active_projects_section_never_carries(vault):
    write(vault, "briefings/2026-10-06.md", briefing(
        "- [ ] **Real**\n", extra="\n## 🎯 Active Projects\n\n### [[Alpha]]\nNext:\n- [ ] a project checkbox\n"))
    assert run(vault, "2026-10-07").stdout.splitlines() == ["- [ ] **Real** _(open since 2026-10-06)_"]
