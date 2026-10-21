"""The shared connector stream checker (F1 spec §3.1), ported from the watch, triage, calendar, meetings and RCA suites."""
import json

import pytest

from helpers import call, stream
from vaultlib import connector

TOOL = "mcp__claude_ai_Gmail__search_threads"
# What the model sees in place of an MCP result over the token limit (claude's own wording): no threads, no page token.
BIG = ("Error: result (123,456 characters) exceeds maximum allowed tokens. Output has been saved to "
       "/tmp/x/tool-results/mcp-search.txt.\nFormat: JSON\n")


def by_query(i):
    return {"q1": "first", "q2": "second"}.get(i.get("query"))


def fails(code, fn, *args, **kw):
    with pytest.raises(connector.Fail) as e:
        fn(*args, **kw)
    assert e.value.code == code
    return e.value.reason


def use(name):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "x1", "name": name, "input": {}}]}}


@pytest.mark.parametrize("text", [BIG, "<persisted-output>\nPreview…", '{"a": 1}\n\n[OUTPUT TRUNCATED - exceeded 25000 tokens]',
                                  "Output too large (78 KB). Full output saved to: /x/1.txt",
                                  "MCP tool response (31,000 tokens) exceeds maximum allowed tokens (25000).",
                                  [{"type": "text", "text": BIG}]])
def test_too_large_knows_each_stand_in(text):
    assert connector.too_large(text)


@pytest.mark.parametrize("text", ['{"results": "Error: result (9 characters) exceeds maximum allowed tokens"}',
                                  '[{"description": "Output too large"}]', '{"threads": []}'])
def test_result_text_cannot_fake_a_stand_in(text):
    assert not connector.too_large(text)
    assert not connector.too_large([{"type": "text", "text": text}])


def test_walk_refuses_another_tool_but_not_toolsearch_or_structured_output():
    s = stream(TOOL, [call({"query": "q1"})])
    assert connector.walk(s, TOOL, by_query).calls[0][0] == "first"
    bash = [*s[:-1], use("Bash"), s[-1]]
    assert fails(7, connector.walk, bash, TOOL, by_query) == "the session used an unexpected tool: Bash"
    so = [*s[:-1], use("StructuredOutput"), s[-1]]
    assert fails(7, connector.walk, so, TOOL, by_query) == "the session used an unexpected tool: StructuredOutput"
    assert connector.walk(so, TOOL, by_query, structured=True).result == s[-1]


def test_walk_refuses_an_input_accept_refuses_and_keeps_a_reason_accept_raises():
    s = stream(TOOL, [call({"query": "q1"}), call({"query": "evil"})])
    assert fails(7, connector.walk, s, TOOL, by_query) == (
        f"the session called {TOOL} with other arguments than the ones built for this run")

    def strict(i):
        raise connector.Fail(7, f"the session read a Doc that was not requested: {i.get('query')}")
    assert fails(7, connector.walk, s, TOOL, strict) == "the session read a Doc that was not requested: q1"


def test_walk_counts_calls_at_the_call():
    s = stream(TOOL, [call({"query": "q1"}, error=True), call({"query": "q1"})])
    assert fails(7, connector.walk, s, TOOL, by_query, max_calls=1) == "the session made 2 first calls; the limit is 1"
    # Before the error check: the second call fails 7 though the first result was an error.
    assert fails(7, connector.check_stream, s, TOOL, by_query, max_pages=1) == "the session made 2 first calls; the limit is 1"
    two = stream(TOOL, [call({"query": "q1"}), call({"query": "q2"})])
    assert len(connector.walk(two, TOOL, by_query, max_calls=1).calls) == 2   # the limit is per name


def test_walk_pairs_results_with_calls_and_reads_the_named_check():
    s = stream(TOOL, [call({"query": "q1"}, sc={"threads": [1]}), call({"query": "q2"})])
    w = connector.walk(s, TOOL, by_query)
    assert [(n, b["id"]) for n, b in w.calls] == [("first", "t1"), ("second", "t2")]
    assert [(n, b["tool_use_id"]) for n, b, _ in w.results] == [("first", "t1"), ("second", "t2")]
    assert w.results[0][2]["tool_use_result"] == {"structuredContent": {"threads": [1]}}
    assert w.named and w.result == s[-1]
    assert not connector.walk(stream(TOOL, named=False), TOOL, by_query).named


def test_free_text_naming_the_tool_is_not_a_connector():
    # A "not found" ToolSearch reply that repeats the tool's name is no connector: exit 3, never 1 (#38).
    s = stream(TOOL, named=False)
    assert TOOL in json.dumps(s[1])
    assert fails(3, connector.check_stream, s, TOOL, by_query, server="Gmail") == "no Gmail connector reachable"


def test_check_stream_order():
    errored = stream(TOOL, [call({"query": "q1"}, text="rate limited", error=True)])
    assert fails(1, connector.check_stream, errored[:-1], TOOL, by_query) == "claude produced no result"
    assert fails(6, connector.check_stream, errored, TOOL, by_query) == 'the connector returned an error: "rate limited"'
    assert fails(1, connector.check_stream, stream(TOOL), TOOL, by_query, server="Gmail") == f"the session never called {TOOL}"
    assert fails(3, connector.check_stream, stream(TOOL, named=False), TOOL, by_query, server="Gmail") == "no Gmail connector reachable"
    turns = stream(TOOL, [call({"query": "q1"})], result="error_max_turns")
    assert fails(1, connector.check_stream, turns, TOOL, by_query) == "claude returned an error result (error_max_turns)"


def test_pages_group_by_name_and_take():
    s = stream(TOOL, [call({"query": "q1"}, sc={"threads": [1]}), call({"query": "q2"}, sc={"threads": [2]}),
                      call({"query": "q1"}, sc={"threads": [3]})])
    pages, result = connector.check_stream(s, TOOL, by_query)
    assert pages == {"first": [{"threads": [1]}, {"threads": [3]}], "second": [{"threads": [2]}]}
    assert result == s[-1]
    assert connector.check_stream(stream(TOOL, [call({"query": "q1"})]), TOOL, by_query)[0] == {"first": [{}]}
    slack = stream(TOOL, [call({"query": "q1"}, text=[{"type": "text", "text": '{"results": "# Search"}'}])])
    assert connector.check_stream(slack, TOOL, by_query, take=connector.text_json)[0] == {"first": [{"results": "# Search"}]}
    assert connector.text_json({"content": "not json"}, {}) == {} and connector.structured({}, {}) == {}
    assert connector.strip_cursor({"query": "q", "cursor": "c"}) == {"query": "q"}


def test_a_too_large_result_fails_6_or_counts_into_persisted():
    s = stream(TOOL, [call({"query": "q1"}, text=BIG, sc={"threads": [1]}, error=True), call({"query": "q2"}, sc={"threads": [2]})])
    assert fails(6, connector.check_stream, s, TOOL, by_query) == "a first result was too large for the model to read"
    persisted = {}
    pages, _ = connector.check_stream(s, TOOL, by_query, persisted=persisted)
    assert persisted == {"first": 1}
    assert pages == {"first": [{"threads": [1]}], "second": [{"threads": [2]}]}   # the stream holds the whole result


def test_need_result_false_returns_pages_without_a_result_message():
    s = stream(TOOL, [call({"query": "q1"}, sc={"key": "EX-1"})])[:-1]
    assert connector.check_stream(s, TOOL, by_query, max_pages=1, need_result=False) == ({"first": [{"key": "EX-1"}]}, None)
    assert fails(3, connector.check_stream, stream(TOOL, named=False)[:-1], TOOL, by_query, server="Google Drive",
                 need_result=False) == "no Google Drive connector reachable"
