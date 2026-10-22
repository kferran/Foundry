"""calendar_tsv.py: validate the calendar fetch's stream-json and print TSV (calendar spec §4.4)."""
import json
import subprocess
import sys

import pytest

from helpers import REPO, call, stream

SCRIPT = REPO / "system" / "scripts" / "calendar_tsv.py"
TOOL = "mcp__claude_ai_Google_Calendar__list_events"
DAY = "2026-10-05"


def ev(start_date=DAY, start_time="09:00", end_date=DAY, end_time="09:30", title="Standup"):
    return {"start_date": start_date, "start_time": start_time, "end_date": end_date,
            "end_time": end_time, "title": title}


def session(output=None, calls=(call(),), others=(), named=True, result=None):
    """A --json-schema calendar session on helpers.stream: the init message, ToolSearch, a list_events call per
    `calls`, a call of each of `others`, StructuredOutput, then the result carrying `output` (or `result`)."""
    s = stream(TOOL, calls, named=named, num_turns=4, total_cost_usd=0.2, permission_denials=[],
               structured_output=output)
    uses = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"x{n}", "name": name, "input": {}}]}}
            for n, name in enumerate((*others, "StructuredOutput"))]
    lines = [{"type": "system", "subtype": "init", "tools": ["ToolSearch", "Bash"]}, *s[:-1], *uses,
             result if result is not None else s[-1]]
    return "\n".join(json.dumps(x) for x in lines) + "\n"


def ok(events):
    return {"status": "ok", "reason": "", "events": events}


def run(text, tmp_path, day=DAY):
    summary = tmp_path / "summary.json"
    p = subprocess.run([sys.executable, str(SCRIPT), day, "--summary", str(summary)],
                       input=text, capture_output=True, text=True)
    data = json.loads(summary.read_text()) if summary.exists() else None
    return p, data


def test_valid_events_become_sorted_sanitized_tsv(tmp_path):
    events = [
        ev(start_time="13:00", end_time="13:45", title="Dentist\t(Dr. O)\nroom 2"),
        ev(start_time="", end_time="", title="Holiday"),
        ev(start_date="2026-10-04", start_time="", end_date="2026-10-06", end_time="", title="Conference"),
        ev(title="x" * 300),
    ]
    p, data = run(session(ok(events)), tmp_path)
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == [
        "2026-10-04\t\t2026-10-06\t\tConference",
        f"{DAY}\t\t{DAY}\t\tHoliday",
        f"{DAY}\t09:00\t{DAY}\t09:30\t" + "x" * 200,
        f"{DAY}\t13:00\t{DAY}\t13:45\tDentist (Dr. O) room 2",
    ]
    assert data["events"] == 4 and data["cost_usd"] == 0.2 and data["turns"] == 4
    assert data["denials"] == 0 and data["tools"] == ["ToolSearch", "Bash"] and data["unexpected_tools"] == []


def test_empty_list_prints_nothing(tmp_path):
    p, data = run(session(ok([])), tmp_path)
    assert (p.returncode, p.stdout, data["events"]) == (0, "", 0)


@pytest.mark.parametrize("status, code", [("no_tool", 3), ("tool_error", 6), ("too_many", 8)])
def test_statuses(tmp_path, status, code):
    p, _ = run(session({"status": status, "reason": "quota exceeded", "events": []}), tmp_path)
    assert p.returncode == code
    assert p.stdout == ""
    assert p.stderr.startswith("calendar_tsv: ")


def test_tool_error_reason_is_reported(tmp_path):
    p, data = run(session({"status": "tool_error", "reason": "quota exceeded", "events": []}), tmp_path)
    assert "quota exceeded" in p.stderr
    assert data["reason"] == "quota exceeded"


OVERFLOW = "Error: result (54,846 characters) exceeds maximum allowed tokens. Output has been saved to /x/tool-results/1.txt."


@pytest.mark.parametrize("content", [
    OVERFLOW,
    [{"type": "text", "text": OVERFLOW}],
    "Output too large (78 KB). Full output saved to: /x/1.txt",
    "MCP tool response (31,000 tokens) exceeds maximum allowed tokens (25000).",
])
def test_an_oversized_list_events_result_exits_6_even_with_an_ok_output(tmp_path, content):
    # The harness replaced a page with a note that it was saved to disk; the session cannot read it (#164).
    p, data = run(session(ok([]), calls=(call(), call(text=content, error=True))), tmp_path)
    assert p.returncode == 6, p.stderr
    assert p.stdout == ""
    assert "exceeded the result limit" in p.stderr and "pageSize" in p.stderr
    assert "exceeded the result limit" in data["reason"]


def test_an_event_whose_text_mentions_the_limit_is_not_an_overflow(tmp_path):
    # Only a tool result that is the harness's notice counts, never event text that quotes it (#164).
    p, _ = run(session(ok([ev()]), calls=(call(text='{"events": [{"description": "' + OVERFLOW + '"}]}'),)), tmp_path)
    assert p.returncode == 0, p.stderr


def test_unexpected_tool_use_fails_even_with_valid_output(tmp_path):
    p, data = run(session(ok([ev()]), others=("mcp__claude_ai_Gmail__send_message",)), tmp_path)
    assert p.returncode == 7
    assert p.stdout == ""
    assert data["unexpected_tools"] == ["mcp__claude_ai_Gmail__send_message"]


def test_two_unexpected_tools_exit_7_and_both_reach_the_summary(tmp_path):
    p, data = run(session(ok([ev()]), others=("Bash", "mcp__claude_ai_Gmail__send_message")), tmp_path)
    assert p.returncode == 7
    assert p.stderr == "calendar_tsv: the session used an unexpected tool: Bash\n"
    assert data["unexpected_tools"] == ["Bash", "mcp__claude_ai_Gmail__send_message"]


@pytest.mark.parametrize("named, code, reason", [
    (True, 1, f"the session never called {TOOL}"),
    (False, 3, "no Google Calendar connector reachable"),
])
def test_an_ok_status_without_a_list_events_call_exits_1_or_3(tmp_path, named, code, reason):
    # An ok reply from a session that never read the calendar is not an empty day (F1 spec §3.6 item 5).
    p, data = run(session(ok([ev()]), calls=(), named=named), tmp_path)
    assert p.returncode == code, p.stderr
    assert p.stdout == ""
    assert p.stderr == f"calendar_tsv: {reason}\n"
    assert data["events"] is None


@pytest.mark.parametrize("result", [
    {"type": "result", "subtype": "success", "is_error": True, "structured_output": None},
    {"type": "result", "subtype": "error_max_turns", "is_error": False, "errors": ["Reached maximum number of turns (15)"]},
])
def test_error_results_exit_1(tmp_path, result):
    p, _ = run(session(result=result), tmp_path)
    assert p.returncode == 1
    assert p.stderr.startswith("calendar_tsv: ")


def test_no_result_message_exits_1(tmp_path):
    text = json.dumps({"type": "system", "subtype": "init", "tools": []}) + "\n"
    p, _ = run(text, tmp_path)
    assert p.returncode == 1


@pytest.mark.parametrize("output", [
    None,
    {"status": "ok", "events": []},
    {"status": "ok", "reason": "", "events": [], "extra": 1},
    {"status": "maybe", "reason": "", "events": []},
    ok([{"start_date": DAY, "start_time": "09:00", "end_date": DAY, "end_time": "09:30"}]),
    ok([dict(ev(), color="red")]),
    ok([ev(start_time=9)]),
    ok([ev()] * 101),
    ok([ev(start_date="2026-10-06", end_date="2026-10-06")]),
    ok([ev(start_date="2026-02-30", end_date="2026-02-30")]),
    ok([ev(start_time="", end_time="10:00")]),
    ok([ev(start_time="25:00")]),
    ok([ev(start_time="09:00\n")]),
    ok([ev(end_time="09:3٠")]),
    ok([ev(start_time="10:00", end_time="09:00")]),
])
def test_invalid_outputs_exit_5(tmp_path, output):
    p, _ = run(session(output), tmp_path)
    assert p.returncode == 5, (output, p.stderr)
    assert p.stdout == ""


def test_unparseable_line_exits_1(tmp_path):
    p, _ = run("not json\n", tmp_path)
    assert p.returncode == 1


def test_cut_off_stream_still_checks_tools(tmp_path):
    text = session(ok([]), calls=(), others=("mcp__claude_ai_Gmail__send_message",))
    p, data = run(text.rsplit("\n", 2)[0] + '\n{"type": "assi\n', tmp_path)
    assert p.returncode == 7, p.stderr
    assert data["unexpected_tools"] == ["mcp__claude_ai_Gmail__send_message"]


def test_bad_date_argument_exits_2(tmp_path):
    p, _ = run(session(ok([])), tmp_path, day="2026-13-01")
    assert p.returncode == 2
