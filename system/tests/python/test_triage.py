"""Inbox triage (inbox triage spec §3.1): the query, the session check and the write."""
import json
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from helpers import REPO, write
from vaultlib import now, triage as tr

TODAY = "2026-10-09"
Q = "in:inbox after:1000 " + tr.EXCLUDE
LINK = "https://mail.google.com/mail/#all/thread-f:1"


def thread(tid="a1", sender="Blake Sample <blake@example.com>", date="2026-10-09T20:24:00Z", link=None):
    return {"id": tid, "viewUrl": link or f"https://mail.google.com/mail/#all/{tid}",
            "messages": [{"id": "m0", "date": "2026-10-08T10:00:00Z", "sender": "me@example.com"},
                         {"id": "m1", "date": date, "sender": sender, "subject": "Rejected case", "snippet": "How to proceed?"}]}


def stream(*page_threads, items=(), q=Q, tool=tr.TOOL, error=False, token="", reply=None, result="success"):
    s = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0", "name": "ToolSearch", "input": {}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0",
                                                   "content": [{"type": "tool_reference", "tool_name": tr.TOOL}]}]}}]
    for n, threads in enumerate(page_threads, 1):
        s.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{n}", "name": tool, "input": {"query": q, "pageSize": 50}}]}})
        sc = {"threads": threads, **({"nextPageToken": token} if token else {})}
        s.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}", "is_error": error,
                                                           "content": "…"}]},
                  "tool_use_result": {"structuredContent": sc}})
    text = reply if reply is not None else json.dumps({"items": list(items)})
    s.append({"type": "result", "subtype": result, "is_error": result != "success", "result": text})
    return s


def item(tid="a1", who="Blake", ask="asks how to proceed with a rejected case", nxt="reply with the fix plan"):
    return {"thread_id": tid, "who": who, "ask": ask, "next_step": nxt}


def fails(code, s):
    with pytest.raises(tr.Fail) as e:
        tr.extract(s, Q)
    assert e.value.code == code
    return e.value.reason


def test_the_query_starts_after_the_last_tick_or_two_hours_back(vault):
    assert tr.query(vault, 10_000, TODAY) == f"in:inbox after:{10_000 - 7200} {tr.EXCLUDE}"
    write(vault, "system/logs/triage-2026-10.jsonl", json.dumps({"kind": "tick", "epoch": 9_000}) + "\n")
    assert tr.query(vault, 10_000, TODAY) == f"in:inbox after:{9_000 - 300} {tr.EXCLUDE}"


def test_links_dates_and_senders_come_from_the_search_results_only():
    got = tr.extract(stream([thread()], items=[{**item(), "link": "https://evil.example", "date": "1999"}]), Q)
    assert got == {"full": False, "items": [{
        "thread_id": "a1", "date": "2026-10-09T20:24:00Z", "link": "https://mail.google.com/mail/#all/a1",
        "sender": "blake@example.com", "who": "Blake", "ask": "asks how to proceed with a rejected case",
        "next_step": "reply with the fix plan"}]}


def test_a_thread_the_search_never_returned_is_dropped():
    assert tr.extract(stream([thread()], items=[item("zz"), item("a1"), item("a1")]), Q)["items"][0]["thread_id"] == "a1"
    assert len(tr.extract(stream([thread()], items=[item("zz")]), Q)["items"]) == 0


def test_texts_are_one_short_line():
    got = tr.extract(stream([thread()], items=[item(ask="line one\nline [two] " + "x" * 300)]), Q)["items"][0]
    assert "\n" not in got["ask"] and "[" not in got["ask"] and len(got["ask"]) == tr.TEXT_MAX


@pytest.mark.parametrize("kwargs,code", [
    ({"tool": "mcp__claude_ai_Gmail__get_thread"}, 7),
    ({"q": "in:inbox"}, 7),
    ({"error": True}, 6),
    ({"result": "error_max_turns"}, 1),
    ({"reply": "Here is what I found"}, 1),
])
def test_a_session_outside_the_rules_fails_closed(kwargs, code):
    fails(code, stream([thread()], items=[item()], **kwargs))


def test_no_search_call_means_no_connector():
    s = [{"type": "result", "subtype": "success", "is_error": False, "result": "{}"}]
    assert "no Gmail connector" in fails(3, s)


def test_more_than_three_pages_is_refused_and_a_full_third_page_is_flagged():
    fails(7, stream([thread("a")], [thread("b")], [thread("c")], [thread("d")]))
    assert tr.extract(stream([thread("a")], [thread("b")], [thread("c")], token="next"), Q)["full"] is True


def prepare(vault):
    shutil.copytree(REPO / "system" / "templates", vault / "system" / "templates", dirs_exist_ok=True)
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\ndefault_partition: "work"\n---\n')


def test_record_adds_one_owed_line_per_new_message_and_records_the_tick(vault):
    prepare(vault)
    found = tr.extract(stream([thread()], items=[item()]), Q)
    assert tr.record(vault, "work", found, TODAY, "t", 5_000) == ["Blake: asks how to proceed with a rejected case"]
    lines = now.open_lines(now.read(vault, "work"))
    assert lines == ["- [ ] owed: Blake: asks how to proceed with a rejected case. Next: reply with the fix plan "
                     "(blake@example.com, since 2026-10-09, https://mail.google.com/mail/#all/a1)"]
    assert tr.record(vault, "work", found, TODAY, "t", 6_000) == []  # a rerun adds nothing
    newer = tr.extract(stream([thread(date="2026-10-09T22:00:00Z")], items=[item(ask="asks again")]), Q)
    assert tr.record(vault, "work", newer, TODAY, "t", 7_000) == ["Blake: asks again"]
    ticks = [r["epoch"] for r in tr.records(vault, TODAY) if r["kind"] == "tick"]
    assert ticks == [5_000, 6_000, 7_000]


def test_a_link_the_now_line_cannot_hold_keeps_the_item(vault):
    prepare(vault)
    found = tr.extract(stream([thread(link="https://mail.example/a,b")], items=[item()]), Q)
    assert len(tr.record(vault, "work", found, TODAY, "t", 5_000)) == 1
    assert "(https://mail.example/a,b)" in now.read(vault, "work")


def test_hold_reads_the_newest_usage_reading(vault):
    stamp = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    write(vault, "system/logs/nightshift/health-2026-10-09.json",
          json.dumps({"usage5": 0.8, "usage5_at": (stamp - timedelta(hours=1)).isoformat()}))
    assert "80%" in tr.hold(vault, stamp)
    assert tr.hold(vault, stamp + timedelta(hours=5)) == ""


def test_the_owners_own_replies_never_make_a_thread_new():
    t = thread()
    t["messages"].append({"id": "m2", "date": "2026-10-09T22:00:00Z", "sender": "me@example.com", "labelIds": ["SENT"]})
    sent_only = {**thread("b2"), "messages": [
        {"id": "m3", "date": "2026-10-09T23:00:00Z", "sender": "me@example.com", "labelIds": ["SENT", "INBOX"]}]}
    got = tr.extract(stream([t, sent_only], items=[item(), item("b2")]), Q)
    assert [(i["thread_id"], i["date"], i["sender"]) for i in got["items"]] == [("a1", "2026-10-09T20:24:00Z", "blake@example.com")]


def test_angle_brackets_cannot_reach_the_now_page():
    assert tr.one_line("<!-- hide --> <b>x</b>") == "‹!-- hide --› ‹b›x‹/b›"


def test_a_bad_triage_partition_is_a_settings_error_before_any_session(vault):
    write(vault, "system/config.md", '---\ntype: config\ntriage_partition: "shared"\n---\n')
    with pytest.raises(tr.Fail) as e:
        tr.query(vault, 10_000, TODAY)
    assert e.value.code == 2 and "triage_partition" in e.value.reason
