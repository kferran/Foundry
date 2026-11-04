"""Digest follow-ups become proposed Now lines (#476, digest follow-ups spec)."""
import shutil

import pytest

from helpers import REPO, write
from vaultlib import followups, now

TODAY = "2026-10-12"
KEY = "ghp_" + "a" * 36
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar").split()


@pytest.fixture
def fv(vault):
    shutil.copytree(REPO / "system" / "templates", vault / "system" / "templates", dirs_exist_ok=True)
    return vault


def digest(vault, p, name, body, created="2026-10-12T09:00:00-06:00", provenance="session", kind="session_digest"):
    rel = f"raw/{p}/archive/{name}.md"
    write(vault, rel, f'---\ntype: {kind}\npartition: {p}\ncodebase: "vault"\nsession_id: "{name}"\n'
                      f'created_at: "{created}"\nprovenance: ["{provenance}"]\n---\n{body}')
    followups.queue(vault, [rel])
    return rel


def fu(*bullets):
    return "## Outcome\nShipped it.\n\n## Follow-ups\n" + "".join(f"- {b}\n" for b in bullets)


def step(vault, day=TODAY, keys=None):
    got = []

    def sink(text, key=""):
        got.append(text)
        if keys is not None:
            keys.append(key)
    followups.step(vault, day, sink)
    return got


def proposed(vault, p="work"):
    return [line for line in now.read(vault, p).splitlines() if line.startswith("- [ ] ") and "[via:: digest]" in line]


def statements(vault, p="work"):
    return [now.fields(now.LINE.match(line).group("statement"))[0] for line in proposed(vault, p)]


def queued(vault):
    q = vault / followups.QUEUE
    return q.read_text(encoding="utf-8").split() if q.exists() else []


def page_with(vault, p, *lines):
    now.write(vault, p, now.new_page(vault, p, "2026-10-01").rstrip("\n") + "\n" + "\n".join(lines) + "\n")


def test_three_follow_ups_become_three_digest_lines_with_the_archive_path(fv):
    rel = digest(fv, "work", "2026-10-12-0900-a1b2c3d4-ship", "## Outcome\nx\n\n## Follow-ups\n- Write the release notes\n"
                 "- Book the venue review\n* Send the survey summary\n\n## Notes\n- Not a follow-up\n")
    assert step(fv) == []
    lines = proposed(fv)
    assert len(lines) == 3
    assert all(line.startswith("- [ ] owed: ") and "[due:: " in line and line.endswith(f"(since {TODAY}, {rel})")
               for line in lines)
    assert statements(fv) == ["Write the release notes", "Book the venue review", "Send the survey summary"]
    assert not (fv / followups.QUEUE).exists()


def test_a_bullet_equal_to_or_inside_an_open_line_is_skipped(fv):
    now.add(fv, "work", "waiting", "Write the release notes for the November cut", "2026-10-01")
    now.add(fv, "work", "owed", "Book the venue review", "2026-10-01")
    digest(fv, "work", "d1", fu("Write the release notes", "book the venue review.", "Answer the vendor about pricing"))
    step(fv)
    assert statements(fv) == ["Answer the vendor about pricing"]


def test_a_bullet_naming_an_open_lines_pull_request_is_skipped(fv):
    now.add(fv, "work", "owed", "Get the export change reviewed", "2026-10-01",
            evidence="https://github.com/acme/tpl/pull/7")
    digest(fv, "work", "d1", fu("Chase the second look at https://github.com/acme/tpl/pull/7"))
    step(fv)
    assert proposed(fv) == []


@pytest.mark.parametrize("since, added", [(TODAY, 0), ("2026-10-11", 0), ("2026-10-05", 1)])
def test_shared_words_match_a_same_day_line_and_not_a_week_old_one(fv, since, added):
    now.add(fv, "work", "owed", "Draft quarterly budget proposal for finance", since)
    digest(fv, "work", "d1", fu("Finish the budget proposal draft, quarterly numbers"))
    step(fv)
    assert len(proposed(fv)) == added


def test_sibling_follow_ups_that_share_words_are_all_proposed(fv):
    bullets = ("Update the billing service docs", "Update the billing service tests",
               "Merge PR 504 after owner review", "Merge PR 501 after owner review")
    digest(fv, "work", "d1", fu(*bullets))
    step(fv)
    assert statements(fv) == list(bullets)


def test_a_same_day_machine_line_sharing_words_does_not_swallow_a_follow_up(fv):
    now.add(fv, "work", "owed", "Reply to the vendor about the billing service outage", TODAY, via="mail")
    digest(fv, "work", "d1", fu("Write the billing service outage postmortem"))
    step(fv)
    assert statements(fv) == ["Write the billing service outage postmortem"]


def test_an_unreadable_archive_keeps_the_queue_and_alerts_with_a_key(fv):
    (fv / "wiki/work/now-archive").mkdir(parents=True)
    (fv / "wiki/work/now-archive/2026-10.md").write_bytes(b"\xff\xfe not text")
    rel = digest(fv, "work", "d1", fu("Write the release notes"))
    keys = []
    got = step(fv, keys=keys)
    assert got == ["follow-ups step failed for raw/work/archive/d1.md: UnicodeDecodeError; it waits for the next tick"]
    assert keys == ["follow-ups step failed"]
    assert queued(fv) == [rel]


def test_a_line_dropped_within_14_days_skips_the_bullet_on_the_page_and_in_the_archive(fv):
    page_with(fv, "work", "- [-] owed: Write the release notes [via:: digest] (since 2026-10-05, raw/work/archive/old.md)"
                          " _(closed: ticked 2026-10-06)_")
    write(fv, "wiki/work/now-archive/2026-10.md", "---\ntype: concept\n---\n"
          "- [-] owed: Book the venue review (since 2026-10-01) _(closed: ticked 2026-10-03)_\n")
    write(fv, "wiki/work/now-archive/2026-09.md", "---\ntype: concept\n---\n"
          "- [-] owed: Send the survey summary (since 2026-09-01) _(closed: ticked 2026-09-20)_\n")
    digest(fv, "work", "d1", fu("Write the release notes", "Book the venue review", "Send the survey summary"))
    step(fv)
    assert statements(fv) == ["Send the survey summary"]


def test_a_handled_digest_leaves_the_queue_and_a_second_run_adds_nothing(fv):
    digest(fv, "work", "d1", fu("Write the release notes"))
    step(fv)
    assert queued(fv) == []
    before = now.read(fv, "work")
    step(fv)
    assert now.read(fv, "work") == before


def test_a_rerun_after_a_crash_before_the_queue_rewrite_adds_nothing(fv):
    rel = digest(fv, "work", "d1", fu("Write the release notes", "Book the venue review"))
    step(fv)
    followups.queue(fv, [rel])   # the queue as it was before the crash
    assert step(fv) == []
    assert len(proposed(fv)) == 2
    assert queued(fv) == []


def test_six_bullets_add_five_and_alert_once(fv):
    digest(fv, "work", "d6", fu(*(f"Check the {w} report" for w in WORDS[:6])))
    assert step(fv) == ["digest d6: 6 follow-ups, 5 proposed"]
    assert len(proposed(fv)) == 5


def test_eleven_digests_add_ten_lines_and_the_rest_waits_for_tomorrow(fv):
    rels = [digest(fv, "work", f"d{i:02d}", fu(f"Check the {w} report")) for i, w in enumerate(WORDS[:11])]
    step(fv)
    assert len(proposed(fv)) == 10
    assert queued(fv) == rels[10:]
    step(fv, "2026-10-13")
    assert len(proposed(fv)) == 11
    assert queued(fv) == []


def test_a_digest_cut_off_by_the_day_cap_doubles_nothing_and_alerts_once_next_day(fv):
    digest(fv, "work", "a", fu(*(f"Check the {w} report" for w in WORDS[0:4])))
    digest(fv, "work", "b", fu(*(f"Check the {w} report" for w in WORDS[4:8])))
    digest(fv, "work", "c", fu(*(f"Check the {w} report" for w in WORDS[8:14])))
    assert step(fv) == []
    assert queued(fv) == ["raw/work/archive/c.md"]
    assert step(fv, "2026-10-13") == ["digest c: 6 follow-ups, 5 proposed"]
    assert len(statements(fv)) == 13
    assert len(set(statements(fv))) == 13


def test_a_personal_digest_goes_only_on_the_personal_page_and_shared_on_work(fv):
    digest(fv, "personal", "p1", fu("Renew the passport"))
    digest(fv, "shared", "s1", fu("Tidy the glossary"))
    step(fv)
    assert statements(fv, "personal") == ["Renew the passport"]
    assert statements(fv, "work") == ["Tidy the glossary"]


def test_a_cross_wall_bullet_is_skipped_with_an_alert_naming_no_note(fv):
    write(fv, "wiki/personal/concepts/diary.md", "---\ntype: concept\n---\n")
    digest(fv, "work", "d1", fu("Read [[diary]] again", "Write the release notes"))
    got = step(fv)
    assert got == ["digest d1: a follow-up was skipped: partition wall"]
    assert statements(fv) == ["Write the release notes"]


def test_a_bullet_with_a_field_key_is_skipped_and_the_others_added(fv):
    digest(fv, "work", "d1", fu("Set [due:: 2026-10-20] for it", "Write the release notes"))
    got = step(fv)
    assert len(got) == 1
    assert got[0].startswith("digest d1: a follow-up was skipped: ")
    assert statements(fv) == ["Write the release notes"]


def test_a_credential_shaped_bullet_lands_redacted(fv):
    digest(fv, "work", "d1", fu(f"Rotate the token {KEY}"))
    step(fv)
    text = now.read(fv, "work")
    assert KEY not in text
    assert "[REDACTED:" in proposed(fv)[0]


def test_a_long_bullet_is_cut_and_keeps_its_tag_and_evidence(fv):
    rel = digest(fv, "work", "d1", fu("w" * 400))
    step(fv)
    line = proposed(fv)[0]
    assert len(line) <= now.MAX_LINE
    assert line.endswith(f"[via:: digest] (since {TODAY}, {rel})")


@pytest.mark.parametrize("body, kind", [
    (fu("Write the release notes"), "meeting_input"),
    ("## Stale claims\n- [[Note]]: a → b (doc)\n", "session_digest"),
    ("## Outcome\nShipped it.\n", "session_digest"),
    ("## Follow-ups\n- None.\n", "session_digest"),
    ("## Follow-ups\n1. n/a\n", "session_digest"),
])
def test_non_digests_stale_claims_and_empty_sections_add_nothing(fv, body, kind):
    digest(fv, "work", "d1", body, kind=kind)
    assert step(fv) == []
    assert proposed(fv) == []
    assert queued(fv) == []


def test_a_done_checkbox_bullet_is_skipped_and_numbered_items_count(fv):
    digest(fv, "work", "d1", "### follow-up\n- [x] Merged the fix\n- [ ] Write the release notes\n"
                             "1. Book the venue review\n2. Send the survey summary\n  - an indented detail\n")
    step(fv)
    assert statements(fv) == ["Write the release notes", "Book the venue review", "Send the survey summary"]


def test_a_backfilled_digest_is_proposed_like_any_other(fv):
    rel = digest(fv, "work", "2026-10-12-0900-a1b2c3d4-backfill", fu("Write the release notes"), provenance="headless")
    step(fv)
    assert proposed(fv)[0].endswith(f"(since {TODAY}, {rel})")


def test_a_missing_file_and_a_bad_queue_line_alert_once_and_leave_the_queue(fv):
    followups.queue(fv, ["raw/work/archive/gone.md", "wiki/work/Now.md"])
    got = step(fv)
    assert len(got) == 2
    assert got[0].startswith("follow-ups of raw/work/archive/gone.md skipped: ")
    assert got[1] == "a follow-ups queue line is not an archived digest"
    assert queued(fv) == []
    assert step(fv) == []
