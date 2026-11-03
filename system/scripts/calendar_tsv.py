#!/usr/bin/env python3
"""Validate the calendar fetch's stream-json and print the day's events as TSV (calendar spec §4.4).

Usage: calendar_tsv.py YYYY-MM-DD --summary FILE < claude-stream-json
Exit: 0 ok, 1 claude error result (or an ok reply from a session that found the tool and never called it), 2 usage,
3 no connector (or an ok reply from a session that never found the tool), 5 invalid list, 6 connector error or a page
over the harness's result limit, 7 unexpected tool use, 8 more than 100 events. A non-zero exit writes one reason line
to stderr. FILE always receives {events, reason, cost_usd, turns, denials, tools, unexpected_tools, unverified}; rows
that disagree with the raw list_events results still exit 0, with unverified set and printed on stderr.
"""
import datetime
import json
import os
import re
import sys
import zoneinfo

from vaultlib.connector import Fail, structured, text_json, too_large, walk
from vaultlib.stream import messages as read_stream

TOOL = "mcp__claude_ai_Google_Calendar__list_events"
EXPECTED_TOOLS = {"ToolSearch", TOOL, "StructuredOutput"}
FIELDS = ("start_date", "start_time", "end_date", "end_time", "title")
STATUSES = {"ok", "no_tool", "tool_error", "too_many"}
TIME = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_EVENTS = 100
MAX_TITLE = 200


def real_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def check_output(output):
    """Hand-written check of calendar_schema.json (the standard library has no validator)."""
    if not isinstance(output, dict) or set(output) != {"status", "reason", "events"}:
        raise Fail(5, "structured output is missing or has the wrong keys")
    if output["status"] not in STATUSES or not isinstance(output["reason"], str):
        raise Fail(5, "structured output has a bad status or reason")
    events = output["events"]
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise Fail(5, "events is not a list of at most 100 items")
    for e in events:
        if not isinstance(e, dict) or set(e) != set(FIELDS) or not all(isinstance(e[f], str) for f in FIELDS):
            raise Fail(5, "an event does not have exactly the five string fields")
    return output


def rows(events, day):
    out = []
    for e in events:
        start, end = real_date(e["start_date"]), real_date(e["end_date"])
        if start is None or end is None:
            raise Fail(5, f"an event has an invalid date: {e['start_date']} / {e['end_date']}")
        if not start <= day <= end:
            raise Fail(5, f"an event is not on {day}: {e['start_date']}..{e['end_date']}")
        st, et = e["start_time"], e["end_time"]
        if (st == "") != (et == ""):
            raise Fail(5, "an event has one time set and the other empty")
        if st and not (TIME.fullmatch(st) and TIME.fullmatch(et)):
            raise Fail(5, f"an event has an invalid time: {st}-{et}")
        if st and start == end and et < st:
            raise Fail(5, f"an event ends before it starts: {st}-{et}")
        out.append((e["start_date"], st, e["end_date"], et, clean(e["title"])))
    return sorted(out, key=lambda r: (r[0], r[1] != "", r[1], r[4]))


def clean(title):
    return CONTROL.sub(" ", title).strip()[:MAX_TITLE]


def verify(results, table, tz):
    """"" when the raw list_events events and the rows hold the same (start date, start time, title) triples, else the
    first difference, without event text (#436 S8). An all-day start.date is a midnight-UTC time whose first 10
    characters are the date (spike 2026-11-03); a timed start converts to tz. A failed page is skipped."""
    def key(t):
        return t[0], t[1] != "", t[1], t[2]
    pages = [structured(b, m) or text_json(b, m) for _, b, m in results if not b.get("is_error")]
    try:
        raw = []
        for p in pages or [{}]:   # no page at all is unreadable too
            for e in p["events"]:
                s, title = e["start"], clean(e.get("summary", ""))
                if "dateTime" in s:
                    t = datetime.datetime.fromisoformat(s["dateTime"]).astimezone(zoneinfo.ZoneInfo(tz))
                    raw.append((t.date().isoformat(), t.strftime("%H:%M"), title))
                else:
                    raw.append((real_date(s["date"][:10]).isoformat(), "", title))
    except (KeyError, TypeError, ValueError, AttributeError):
        return "the connector's results could not be read"
    if len(raw) != len(table):
        return f"the connector listed {len(raw)} events, the rows hold {len(table)}"
    mine = sorted(((r[0], r[1], r[4]) for r in table), key=key)
    for k, (a, r) in enumerate(zip(sorted(raw, key=key), mine), 1):
        if a != r:
            return f"row {k} ({r[0]} {r[1] or 'all day'}) differs from the connector's results"
    return ""


def main(argv):
    if len(argv) != 4 or argv[2] != "--summary":
        print("usage: calendar_tsv.py YYYY-MM-DD --summary FILE", file=sys.stderr)
        return 2
    day = real_date(argv[1])
    summary_path = argv[3]
    summary = {"events": None, "reason": "", "cost_usd": None, "turns": None, "denials": None,
               "tools": [], "unexpected_tools": [], "unverified": ""}
    code, text = 0, ""
    try:
        if day is None:
            raise Fail(2, f"invalid date: {argv[1]}")
        raw = sys.stdin.read()
        messages = read_stream(raw)   # a session cut off by a timeout still gets its tool check
        if raw.strip() and not messages:
            raise Fail(1, "claude output is not stream-json")
        for m in messages:
            if m.get("type") == "system" and m.get("subtype") == "init":
                summary["tools"] = [t for t in m.get("tools") or [] if isinstance(t, str)]
            if m.get("type") == "assistant":
                for block in (m.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = str(block.get("name"))
                        if name not in EXPECTED_TOOLS and name not in summary["unexpected_tools"]:
                            summary["unexpected_tools"].append(name)
        result = next((m for m in reversed(messages) if m.get("type") == "result"), None)
        if result is not None:
            summary["cost_usd"] = result.get("total_cost_usd")
            summary["turns"] = result.get("num_turns")
            denials = result.get("permission_denials")
            summary["denials"] = len(denials) if isinstance(denials, list) else None
        w = walk(messages, TOOL, lambda i: "events", structured=True)   # exit 7 names the first unexpected tool
        if any(too_large(b.get("content")) for _, b, _ in w.results):
            raise Fail(6, "the connector returned an error: a list_events page exceeded the result limit "
                          "(lower pageSize in calendar_fetch.sh)")
        if result is None:
            raise Fail(1, "claude produced no result")
        if result.get("is_error") or result.get("subtype") != "success":
            errors = result.get("errors") or []
            raise Fail(1, f"claude returned an error result ({result.get('subtype')}): "
                          + "; ".join(str(x) for x in errors))
        output = check_output(result.get("structured_output"))
        summary["reason"] = output["reason"]
        if output["status"] == "no_tool":
            raise Fail(3, "no Google Calendar connector reachable")
        if output["status"] == "tool_error":
            raise Fail(6, f"the connector returned an error: {output['reason']}")
        if output["status"] == "too_many":
            raise Fail(8, f"more than 100 events: {output['reason']}")
        if not w.calls:   # an ok reply that never read the calendar is not an empty day (C4)
            raise Fail(1, f"the session never called {TOOL}") if w.named else Fail(3, "no Google Calendar connector reachable")
        table = rows(output["events"], day)
        summary["events"] = len(table)
        summary["unverified"] = verify(w.results, table, os.environ.get("TZ") or "UTC")
        if summary["unverified"]:
            print(f"calendar_tsv: unverified: {summary['unverified']}", file=sys.stderr)
        text = "".join("\t".join(r) + "\n" for r in table)
    except Fail as f:
        code = f.code
        if not summary["reason"]:
            summary["reason"] = f.reason
        print(f"calendar_tsv: {f.reason}", file=sys.stderr)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
