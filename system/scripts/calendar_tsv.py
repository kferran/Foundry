#!/usr/bin/env python3
"""Validate the calendar fetch's stream-json and print the day's events as TSV (calendar spec §4.4).

Usage: calendar_tsv.py YYYY-MM-DD --summary FILE < claude-stream-json
Exit: 0 ok, 1 claude error result, 2 usage, 3 no connector, 5 invalid list, 6 connector error,
7 unexpected tool use, 8 more than 100 events. A non-zero exit writes one reason line to stderr.
FILE always receives {events, reason, cost_usd, turns, denials, tools, unexpected_tools}.
"""
import datetime
import json
import re
import sys

EXPECTED_TOOLS = {"ToolSearch", "mcp__claude_ai_Google_Calendar__list_events", "StructuredOutput"}
FIELDS = ("start_date", "start_time", "end_date", "end_time", "title")
STATUSES = {"ok", "no_tool", "tool_error", "too_many"}
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
MAX_EVENTS = 100
MAX_TITLE = 200


class Fail(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def real_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def parse_stream(text):
    messages = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            messages.append(json.loads(line))
        except ValueError:
            raise Fail(1, "claude output is not stream-json")
    return messages


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
        if st and not (TIME.match(st) and TIME.match(et)):
            raise Fail(5, f"an event has an invalid time: {st}-{et}")
        if st and start == end and et < st:
            raise Fail(5, f"an event ends before it starts: {st}-{et}")
        title = CONTROL.sub(" ", e["title"]).strip()[:MAX_TITLE]
        out.append((e["start_date"], st, e["end_date"], et, title))
    return sorted(out, key=lambda r: (r[0], r[1] != "", r[1], r[4]))


def main(argv):
    if len(argv) != 4 or argv[2] != "--summary":
        print("usage: calendar_tsv.py YYYY-MM-DD --summary FILE", file=sys.stderr)
        return 2
    day = real_date(argv[1])
    summary_path = argv[3]
    summary = {"events": None, "reason": "", "cost_usd": None, "turns": None, "denials": None,
               "tools": [], "unexpected_tools": []}
    code, text = 0, ""
    try:
        if day is None:
            raise Fail(2, f"invalid date: {argv[1]}")
        messages = parse_stream(sys.stdin.read())
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
        if summary["unexpected_tools"]:
            raise Fail(7, "the session used unexpected tools: " + ", ".join(summary["unexpected_tools"]))
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
        table = rows(output["events"], day)
        summary["events"] = len(table)
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
