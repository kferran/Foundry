from datetime import datetime, time
from zoneinfo import ZoneInfo

from vaultlib import nightshift_sched as ns

TZ = ZoneInfo("America/Denver")
W = ns.parse_window("22:00-05:00")


def at(h, m=0, day=6):
    return datetime(2026, 10, day, h, m, tzinfo=TZ)


def item(**kw):
    fm = {"state": "queued", "start": "window", "kind": "plan", "budget": "4h", "queued_at": "2026-10-06T12:00:00-06:00"}
    fm.update(kw)
    return fm


def test_window_crosses_midnight():
    assert ns.in_window(time(23, 30), *W) and ns.in_window(time(2), *W)
    assert not ns.in_window(time(5), *W) and not ns.in_window(time(12), *W)
    assert ns.window_end(at(23), *W) == at(5, day=7)
    assert ns.window_end(at(2, day=7), *W) == at(5, day=7)


def test_window_item_rules():
    assert ns.due(item(), at(23), W, usage7=0.4)[0]
    assert ns.due(item(), at(12), W, 0.4) == (False, "outside the window")
    assert ns.due(item(budget="8h"), at(23), W, 0.4) == (False, "budget does not fit before the window ends")
    assert ns.due(item(), at(23), W, 0.9) == (False, "7-day usage above 80%")
    assert not ns.due(item(state="done"), at(23), W, 0.4)[0]


def test_now_and_at_skip_the_window():
    assert ns.due(item(start="now"), at(12), W, 0.4)[0]
    assert ns.due(item(start="at", start_at="2026-10-06T15:00:00-06:00"), at(15, 5), W, 0.4)[0]
    assert not ns.due(item(start="at", start_at="2026-10-06T15:00:00-06:00"), at(14), W, 0.4)[0]


def test_waiting_reset_is_due_after_reset():
    fm = item(state="waiting_reset", start="now", reset_at="2026-10-06T13:00:00-06:00")
    assert not ns.due(fm, at(12), W, 0.4)[0]
    assert ns.due(fm, at(13, 1), W, 0.4)[0]


def test_pick_order():
    entries = [("w", item(queued_at="2026-10-06T09:00:00-06:00"), ""),
               ("a", item(start="at", start_at="2026-10-06T22:30:00-06:00", queued_at="2026-10-06T11:00:00-06:00"), ""),
               ("n", item(start="now", queued_at="2026-10-06T12:00:00-06:00"), "")]
    assert ns.pick(entries, at(23), W, 0.4)[0] == "n"
    assert ns.pick(entries[:2], at(23), W, 0.4)[0] == "a"


def test_report_date():
    assert ns.report_date(at(5), "06:00") == "2026-10-06"
    assert ns.report_date(at(23), "06:00") == "2026-10-07"


def test_waiting_reset_window_item_still_obeys_the_window():
    fm = item(state="waiting_reset", reset_at="2026-10-06T11:00:00-06:00")
    assert not ns.due(fm, at(12), W, 0.4)[0]
    assert ns.due(fm, at(23), W, 0.4)[0]


def test_a_window_item_needs_no_inactivity():
    assert ns.due(item(), at(23), W, 0.4) == (True, "")
    assert not hasattr(ns, "IDLE")
    assert not hasattr(ns, "idle_seconds")


def test_an_empty_or_full_day_run_window_is_always_open():
    for text in (None, "", "00:00-24:00"):
        w = ns.parse_window(text)
        assert ns.due(item(), at(12), w, 0.4) == (True, "")
        assert ns.due(item(budget="20h"), at(4), w, 0.4) == (True, "")
        assert ns.due(item(), at(12), w, 0.9) == (False, "7-day usage above 80%")
    assert ns.due(item(), at(12), W, 0.4) == (False, "outside the window")   # a set window is kept


def test_five_hour_hold():
    h = {"usage5": 0.7, "usage5_at": at(11).isoformat()}
    assert ns.five_hour_hold(h, at(12), 0.6) == "5-hour usage 70% at or above 60%"
    assert ns.five_hour_hold({**h, "usage5": 0.6}, at(12), 0.6) == "5-hour usage 60% at or above 60%"
    assert ns.five_hour_hold({**h, "usage5": 0.59}, at(12), 0.6) == ""
    assert ns.five_hour_hold({**h, "usage5_at": at(6, 59).isoformat()}, at(12), 0.6) == ""   # the window has reset
    assert ns.five_hour_hold(h, at(12), 0.8) == ""
    assert ns.five_hour_hold({}, at(12), 0.6) == ""
