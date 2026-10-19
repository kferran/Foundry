"""The calendar diff, routing and captures (phase D spec §3.4, §3.5, §3.7; plan Tasks 5 to 7)."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from vaultlib import now as nowmod
from vaultlib.intake import RAW_NAME
from watchlib import calendar as cal, capture, route
from watchlib.common import records

DAY = "2026-10-19"   # a Monday
LINK = "https://example.slack.com/archives/C0OPS/p1792430610351069"


def ev(title, start="09:00", end="09:30", day=DAY):
    return {"date": day, "start": start, "end": end, "title": title}


def test_the_diff_flags_cancelled_moved_and_new_events_by_title():
    old = [ev("Weekly Huddle"), ev("1:1 Pat", "10:00", "10:30"), ev("Standup", "08:30", "08:45"), ev("Standup", "16:00", "16:15")]
    new = [ev("1:1 Pat", "11:00", "11:30"), ev("Standup", "08:30", "08:45"), ev("Deck review", "14:00", "15:00")]
    got = {(f["change"], f["title"]) for f in cal.diff(old, new)}
    assert got == {("cancelled", "Weekly Huddle"), ("moved", "1:1 Pat"), ("cancelled", "Standup"), ("new", "Deck review")}
    assert next(f for f in cal.diff(old, new) if f["change"] == "moved")["was"] == "10:00-10:30"


def test_the_days_first_snapshot_is_a_baseline_and_a_change_shows_when_the_next_tick_still_has_it(vault):
    assert cal.snapshot(vault, DAY, [ev("Weekly Huddle")]) == []
    assert cal.snapshot(vault, DAY, []) == []
    assert [f["change"] for f in cal.snapshot(vault, DAY, [])] == ["cancelled"]
    assert cal.snapshot(vault, DAY, []) == []
    assert cal.snapshot(vault, "2026-10-20", []) == []


def test_an_event_one_tick_drops_and_the_next_lists_again_flags_nothing(vault):
    events = [ev("Weekly Huddle"), ev("Deck review", "14:00", "15:00")]
    cal.snapshot(vault, DAY, events)
    assert cal.snapshot(vault, DAY, events[1:]) == []
    assert cal.snapshot(vault, DAY, events) == []
    assert cal.snapshot(vault, DAY, [ev("Weekly huddle "), events[1]]) == []   # reworded: same title once folded


def test_tsv_rows_parse_and_all_day_events_keep_no_times():
    rows = cal.parse_tsv("2026-10-19\t09:00\t2026-10-19\t09:30\tWeekly Huddle\n2026-10-19\t\t2026-10-19\t\tOut\nbad\n")
    assert rows == [ev("Weekly Huddle"), {"date": DAY, "start": "", "end": "", "title": "Out"}]


def item(kind="meeting_change", what="Weekly Huddle cancelled today", change="cancelled", query="watch", **kw):
    base = {"query": query, "key": "C0OPS/1792430610.351069", "kind": kind, "what": what, "who": "Pat Sample", "by": "",
            "meeting": False, "change": change, "link": LINK, "ts": "1792430610.351069", "label": "#ops",
            "text": "The 09:00 Weekly Huddle is cancelled today."}
    return {**base, **kw}


def test_the_cross_check_flags_a_meeting_a_channel_cancels_while_the_calendar_keeps_it():
    events = [ev("Weekly Huddle"), ev("1:1", "10:00", "10:30")]
    assert [e["title"] for _, e in cal.cross([item()], events, DAY)] == ["Weekly Huddle"]
    assert cal.cross([item(change="moved")], events, DAY) == []
    assert cal.cross([item(text="the 1:1 is cancelled", what="1:1 off")], events, DAY) == []   # too short to match


def test_free_slots_skip_busy_times_and_all_day_events_and_stay_within_work_hours():
    events = [ev("Busy", "09:00", "11:00", "2026-10-20"), ev("Out", "", "", "2026-10-21")]
    days = cal.workdays(DAY, "2026-10-23")
    assert days == ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]
    assert cal.free_slots(events, days[:2]) == ["2026-10-20 11:00", "2026-10-20 13:00", "2026-10-20 15:00"]
    assert cal.workdays("2026-10-23", "") == ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]


def test_slot_days_fetch_at_most_two_workdays_for_the_meeting_commitments():
    items = [{"kind": "commitment", "meeting": True, "by": ""}, {"kind": "commitment", "meeting": False, "by": ""},
             {"kind": "deadline", "meeting": True, "by": ""}]
    assert cal.slot_days(DAY, items) == ["2026-10-20", "2026-10-21"]   # each fetch is one 190 s calendar session
    assert cal.slot_days(DAY, items[1:]) == []


def run(vault, found,flags=(), crossed=(), events=(), fetched=(DAY,), clock="09:10:00"):
    return route.route(vault, "work", found, list(flags), list(crossed), list(events), list(fetched), DAY, clock)


def ledger(vault):
    return records(route.ledger_path(vault, DAY))


def alerts(vault):
    p = vault / "system" / "logs" / f"alerts_{DAY}.md"
    return p.read_text().splitlines() if p.is_file() else []


def test_a_meeting_change_is_logged_and_alerted_once_and_never_routes_twice(vault):
    assert run(vault, {"items": [item()]}) == {"items": 1, "now": 0, "alerts": 1}
    assert alerts(vault) == [f"- 09:10:00 [watch] Weekly Huddle cancelled today (#ops) {LINK}"]
    assert run(vault, {"items": [item()]}) == {"items": 0, "now": 0, "alerts": 0}
    assert [(r["kind"], r["partition"]) for r in ledger(vault)] == [("meeting", "work")]


def test_each_kind_goes_where_the_spec_routes_it(vault):
    items = [item(kind="deadline", what="QBR deck before next week's meeting", by="2026-10-26", key="k1", link=LINK + "1"),
             item(kind="blocked", what="UAT waits on your sign-off", who="QA team", key="k2", link=LINK + "2"),
             item(kind="decision", what="Moving to the new node pool", key="k3", link=LINK + "3"),
             item(kind="incident", what="Prod login errors", key="k4", link=LINK + "4"),
             item(kind="commitment", query="own", what="Add Sam to the partner meeting", who="Sam Sample", key="k5",
                  link=LINK + "5", label="group DM")]
    assert run(vault, {"items": items}) == {"items": 5, "now": 3, "alerts": 1}
    page = nowmod.read(vault, "work")
    assert f"- [ ] owed: QBR deck before next week's meeting (in #ops) [due:: 2026-10-26] (Pat Sample, since {DAY}, {LINK}1)" in page
    assert re.search(r"- \[ \] waiting: UAT waits on your sign-off \(in #ops\) \[due:: [\d-]+\] \(QA team, since", page)
    assert "owed: Add Sam to the partner meeting (in group DM)" in page
    assert "Moving to the new node pool" not in page
    assert [r["now"] for r in ledger(vault)] == ["added", "added", "", "", "added"]
    assert alerts(vault) == [f"- 09:10:00 [watch] Prod login errors (#ops) {LINK}4"]


def test_a_link_already_on_the_now_page_or_archive_and_a_said_commitment_are_covered(vault):
    nowmod.add(vault, "work", "owed", "Pat: asks about the deck", DAY, "Pat", LINK)   # chat triage's line
    nowmod.add(vault, "work", "owed", "Send Pat the capability doc today", DAY)
    items = [item(kind="deadline", what="Deck before Friday"),
             item(kind="commitment", query="own", what="send Pat the capability doc", key="k2", link=LINK + "2")]
    run(vault, {"items": items})
    assert [r["now"] for r in ledger(vault)] == ["covered", "covered"]
    assert len(nowmod.open_lines(nowmod.read(vault, "work"))) == 2


def test_a_thread_link_a_short_phrase_or_a_partial_name_does_not_cover_a_commitment(vault):
    thread = "https://mail.google.com/mail/#all/thread-a:1"
    nowmod.add(vault, "work", "owed", "Send the export numbers", DAY, "Pat", thread)   # an earlier commitment in the thread
    nowmod.add(vault, "work", "owed", "Follow up with the vendor on the export retries", DAY)
    items = [item(kind="commitment", query="mail", what="Book the review room", key="m1", link=thread, label="mail"),
             item(kind="commitment", query="own", what="follow up", key="k2", link=LINK + "2"),
             item(kind="commitment", query="own", what="Set up a sync with the team", who="the team", meeting=True,
                  key="k3", link=LINK + "3"),
             item(kind="commitment", query="own", what="Set up a call with Sam", who="Sam", meeting=True, key="k4",
                  link=LINK + "4")]
    run(vault, {"items": items}, events=[ev("Other vendors sync", "15:00", "15:30"), ev("Samsung review", "16:00", "16:30")])
    assert [r["now"] for r in ledger(vault)] == ["added", "added", "added", "added"]


def test_a_meeting_commitment_gets_free_slots_unless_the_calendar_already_names_the_person(vault):
    c = item(kind="commitment", query="own", what="Set up a sync with Sam", who="Sam Sample", meeting=True, by="2026-10-21",
             key="k1", link=LINK + "1", label="group DM")
    events = [ev("Busy", "09:00", "17:00", "2026-10-20"), ev("Planning", "09:00", "10:00", "2026-10-21")]
    run(vault, {"items": [c]}, events=events, fetched=[DAY, "2026-10-20", "2026-10-21"])
    page = nowmod.read(vault, "work")
    assert f"  - {DAY}: free: 2026-10-21 10:00, 2026-10-21 12:00, 2026-10-21 14:00" in page
    c2 = {**c, "what": "Set up a review with Jordan", "who": "Jordan Sample", "key": "k2", "link": LINK + "2"}
    run(vault, {"items": [c2]}, events=[ev("Jordan / Alex sync", "15:00", "15:30", "2026-10-20")])
    assert ledger(vault)[-1]["now"] == "covered"


def test_calendar_flags_and_cross_hits_are_logged_and_cancellations_and_moves_alert(vault):
    flags = [{"change": "cancelled", "title": "Weekly Huddle", "start": "09:00", "end": "09:30", "was": ""},
             {"change": "moved", "title": "1:1 Pat", "start": "11:00", "end": "11:30", "was": "10:00-10:30"},
             {"change": "new", "title": "Deck review", "start": "14:00", "end": "15:00", "was": ""}]
    cancel = item()
    crossed = [(cancel, ev("Standup", "08:30", "08:45"))]
    run(vault, {"items": [cancel]}, flags=flags, crossed=crossed)
    assert [r["text"] for r in ledger(vault)] == [
        "Standup 08:30-08:45 cancelled per #ops (calendar still confirmed)",
        "Weekly Huddle 09:00-09:30 is gone from the calendar", "1:1 Pat moved from 10:00-10:30 to 11:00-11:30",
        "new in the calendar: Deck review 14:00-15:00"]
    assert len(alerts(vault)) == 3


def test_a_cancellation_the_calendar_still_lists_is_one_alert_and_one_today_line(vault):
    cancel = item()
    assert run(vault, {"items": [cancel]}, crossed=[(cancel, ev("Weekly Huddle"))]) == {"items": 1, "now": 0, "alerts": 1}
    assert alerts(vault) == [f"- 09:10:00 [watch] Weekly Huddle 09:00-09:30 cancelled per #ops (calendar still confirmed) {LINK}"]
    assert run(vault, {"items": [cancel]}, crossed=[(cancel, ev("Weekly Huddle"))]) == {"items": 0, "now": 0, "alerts": 0}


def test_more_than_three_alerts_in_a_tick_end_with_one_count_line(vault):
    items = [item(kind="incident", what=f"Incident {n}", key=f"k{n}", link=f"{LINK}{n}") for n in range(5)]
    run(vault, {"items": items})
    got = alerts(vault)
    assert len(got) == 4 and got[-1] == "- 09:10:00 [watch] and 2 more meeting changes or incidents; see the today file"


def test_a_capture_file_holds_each_message_and_its_link_under_a_name_the_intake_accepts(vault):
    now = datetime(2026, 10, 19, 9, 10, tzinfo=ZoneInfo("America/Denver"))
    msgs = [{"ts": "1792429200.000100", "channel": "C0CAP", "sender": "Alex Owner", "text": "idea: retry the export\nsecond line",
             "link": "https://example.slack.com/archives/C0CAP/p1792429200000100"}]
    path = capture.write(vault, msgs, "work", "C0CAP", now)
    assert RAW_NAME.match(path.name) and path.parent == vault / "raw" / "inbox"
    text = path.read_text()
    assert text.startswith('---\npartition: "work"\nsource: "slack"\nchannel: "C0CAP"\ncaptured_at: "2026-10-19T09:10:00-06:00"\n---\n')
    assert "## 11:00 Alex Owner\n\nidea: retry the export\nsecond line\n\nLink: https://example.slack.com/archives/C0CAP/p1792429200000100" in text
    assert capture.write(vault, msgs, "work", "C0CAP", now).name == "slack-2026-10-19T091000-2.md"
    route.captured(vault, DAY, "09:10:00", "raw/inbox/slack-2026-10-19T091000.md", msgs, "personal")
    assert ledger(vault)[-1]["text"] == "1 message → raw/inbox/slack-2026-10-19T091000.md"
    assert ledger(vault)[-1]["partition"] == "personal"
    # The next tick's overlap reads the same message again: only the new one is captured.
    later = {**msgs[0], "ts": "1792429300.000100"}
    assert route.new_captures(vault, DAY, [msgs[0], later]) == [later]
    assert json.loads(json.dumps(ledger(vault)[-1]))["kind"] == "capture"
