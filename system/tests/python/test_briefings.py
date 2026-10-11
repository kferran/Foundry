"""vaultlib/briefings.py: the briefings that came before a day (one-screen brief spec §3.2, §3.3)."""
from helpers import write
from vaultlib import briefings


def brief(vault, day, archived=False):
    rel = f"briefings/archive/{day[:7]}/{day}.md" if archived else f"briefings/{day}.md"
    return write(vault, rel, f'---\ntype: briefing\ndate: "{day}"\nstatus: active\n---\n# {day}\n')


def test_earlier_briefings_newest_first_from_live_and_archive(vault):
    brief(vault, "2026-10-09", archived=True)
    brief(vault, "2026-10-10")
    brief(vault, "2026-10-12")  # today: excluded
    brief(vault, "2026-09-01", archived=True)  # beyond the lookback
    assert [d for d, _ in briefings.earlier_briefings(vault, "2026-10-12")] == ["2026-10-10", "2026-10-09"]


def test_no_lookback_walks_the_whole_archive(vault):
    brief(vault, "2026-09-01", archived=True)
    brief(vault, "2026-10-10")
    brief(vault, "2026-10-12")
    write(vault, "briefings/archive/2026-10/2026-10-10.debrief.md", "---\ntype: debrief\ndate: \"2026-10-10\"\n---\n")
    assert [d for d, _ in briefings.earlier_briefings(vault, "2026-10-12", lookback=None)] == ["2026-10-10", "2026-09-01"]


def test_a_live_file_wins_over_its_archive_copy(vault):
    brief(vault, "2026-10-10", archived=True)
    live = brief(vault, "2026-10-10")
    assert briefings.earlier_briefings(vault, "2026-10-11") == [("2026-10-10", live)]
    assert briefings.earlier_briefings(vault, "2026-10-11", lookback=None) == [("2026-10-10", live)]


def test_previous_weekday_briefing_skips_the_weekend(vault):
    for day in ("2026-10-09", "2026-10-10", "2026-10-11"):  # Fri, Sat, Sun
        brief(vault, day)
    assert briefings.previous_weekday_briefing(vault, "2026-10-12") == "2026-10-09"
    assert briefings.previous_weekday_briefing(vault, "2026-10-10") == "2026-10-09"


def test_no_earlier_briefing_is_none(vault):
    assert briefings.earlier_briefings(vault, "2026-10-12") == []
    assert briefings.previous_weekday_briefing(vault, "2026-10-12") is None
