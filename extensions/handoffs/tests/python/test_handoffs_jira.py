"""jira_handoffs.py: the handoff query and the check of a fetch session's stream (delivered work spec §3.2, §4)."""
import io
import json

import pytest

import jira_handoffs as jh
from helpers import call, stream

CFG = {"handoffs_site": "example.atlassian.net", "handoffs_projects": ["EX", "OPS"]}
SITE, JQL = jh.query(CFG)
BIG = ("Error: result (123,456 characters) exceeds maximum allowed tokens. Output has been saved to "
       "/tmp/x/tool-results/mcp-atlassian.txt.")


def node(key="EX-1", assignee="Blake Sample", **fields):
    f = {"summary": f"Fix [{key}]\twith a tab", "status": {"name": "In Review", "statusCategory": {"key": "indeterminate"}},
         "assignee": {"displayName": assignee, "emailAddress": "blake@example.com"} if assignee else None,
         "statuscategorychangedate": "2026-09-28T09:00:00.000-0600"}
    f.update(fields)
    return {"key": key, "fields": f, "webUrl": f"https://elsewhere.example/{key}"}


def page(nodes, more=False, jql=JQL, site=SITE, error=False, text="…"):
    """One search call for helpers.stream: its input, and the issues its result's structuredContent carries."""
    return call({"cloudId": site, "jql": jql, "maxResults": 100}, text,
                {"issues": {"nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": "c"}}}, error)


def fails(code, s, cfg=CFG):
    with pytest.raises(jh.Fail) as e:
        jh.extract(s, cfg)
    assert e.value.code == code
    return e.value.reason


def test_the_query_comes_from_the_settings_only():
    assert SITE == "example.atlassian.net"
    assert JQL == ("project in (EX, OPS) AND reporter = currentUser() AND assignee != currentUser() AND statusCategory != Done "
                   "AND statusCategoryChangedDate <= -7d ORDER BY statusCategoryChangedDate ASC")


@pytest.mark.parametrize("cfg,reason", [
    ({**CFG, "handoffs_projects": []}, "handoffs_projects"),
    ({"handoffs_site": "example.atlassian.net"}, "handoffs_projects"),
    ({**CFG, "handoffs_site": ""}, "handoffs_site"),
    ({**CFG, "handoffs_site": "https://x.example"}, "handoffs_site"),
    ({**CFG, "handoffs_projects": ["EX) OR project = (X"]}, "not a Jira project key"),
])
def test_incomplete_settings_are_a_usage_error(cfg, reason):
    with pytest.raises(jh.Fail) as e:
        jh.query(cfg)
    assert e.value.code == 2 and reason in e.value.reason


def test_lines_merge_pages_once_each_with_a_link_on_the_site_and_no_email():
    lines = jh.extract(stream(jh.TOOL, [page([node("EX-1")]), page([node("EX-1"), node("OPS-2", assignee=None)])]), CFG)
    assert lines == [
        "- [ ] [EX-1](https://example.atlassian.net/browse/EX-1) Fix (EX-1) with a tab (Blake Sample, In Review, unchanged since 2026-09-28)",
        "- [ ] [OPS-2](https://example.atlassian.net/browse/OPS-2) Fix (OPS-2) with a tab (unassigned, In Review, unchanged since 2026-09-28)"]
    assert "blake@example.com" not in json.dumps(lines)


def test_a_session_that_stopped_before_the_last_page_fails_closed():
    assert "last page" in fails(1, stream(jh.TOOL, [page([node()], more=True)]))


@pytest.mark.parametrize("s,code", [
    (stream("mcp__claude_ai_Atlassian__createJiraIssue", [page([node()])]), 7),
    (stream(jh.TOOL, [page([node()], jql="project = EX")]), 7),
    (stream(jh.TOOL, [page([node()], site="other.atlassian.net")]), 7),
    (stream(jh.TOOL, [page([node()], error=True)]), 6),
    (stream(jh.TOOL, [page([node()])], result="error_max_turns"), 1),
])
def test_unexpected_tools_arguments_and_errors(s, code):
    fails(code, s)


def test_no_connector_and_no_call():
    s = stream(jh.TOOL, [page([node()])])
    assert fails(3, [s[0], s[-1]]) == "no Atlassian connector reachable"
    assert "never called" in fails(1, s[:2] + [s[-1]])


@pytest.mark.parametrize("text", [BIG, "<persisted-output>\nPreview…"])
def test_a_page_too_large_for_the_model_still_gives_the_full_list_and_is_counted(text):
    # The list comes from structuredContent, which holds the whole page; the model only saw a stand-in.
    persisted = {}
    assert jh.extract(stream(jh.TOOL, [page([node()], text=text)]), CFG, persisted) == jh.extract(
        stream(jh.TOOL, [page([node()])]), CFG)
    assert persisted == {"search": 1}
    # The model could not see hasNextPage to page on: the last-page check still fails closed.
    assert "last page" in fails(1, stream(jh.TOOL, [page([node()], more=True, text=text)]))


@pytest.mark.parametrize("bad", [
    {"key": "not a key", "fields": node()["fields"]},
    node(statuscategorychangedate=None),
    node(status={}),
    "a string",
])
def test_malformed_tickets_fail_closed(bad):
    fails(1, stream(jh.TOOL, [page([node("EX-9"), bad])]))


def test_a_result_without_an_issues_list_fails_closed():
    s = stream(jh.TOOL, [page([node()])])
    s[3]["tool_use_result"] = {"structuredContent": {"text": "no issues here"}}
    assert "no issues list" in fails(1, s)


def test_main_prints_the_lines_and_one_reason_line(monkeypatch, capsys):
    monkeypatch.setattr(jh, "config", lambda: CFG)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(json.dumps(m) for m in stream(jh.TOOL, [page([node()])]))))
    assert jh.main(["x", "extract"]) == 0
    assert capsys.readouterr().out.startswith("- [ ] [EX-1]")
    monkeypatch.setattr(jh, "config", lambda: {})
    assert jh.main(["x", "query"]) == 2
    assert capsys.readouterr().err == "jira_handoffs: handoffs_projects lists no Jira project keys\n"


def test_the_brief_lists_ten_recent_then_counts_the_rest_and_the_old():
    old = [node(f"EX-{i}", statuscategorychangedate=f"2025-03-{i:02d}T09:00:00.000-0600") for i in range(1, 9)]
    recent = [node(f"OPS-{i}", statuscategorychangedate=f"2026-09-{i:02d}T09:00:00.000-0600") for i in range(1, 18)]
    edge = node("OPS-99", statuscategorychangedate="2026-07-19T09:00:00.000-0600")  # exactly 90 days: recent
    out = jh.chase(jh.extract(stream(jh.TOOL, [page(recent[::-1] + old + [edge])]), CFG), "2026-10-17")
    assert out[0].startswith("- [ ] [OPS-99]") and out[1].startswith("- [ ] [OPS-1]")
    assert len(out) == 12 and out[10] == "- and 8 more"
    assert out[11] == "- 8 handoffs unchanged for more than 90 days (oldest: EX-1, since 2025-03-01)"


def test_a_long_summary_is_cut():
    (line,) = jh.extract(stream(jh.TOOL, [page([node(summary="word " * 60)])]), CFG)
    assert "…" in line and line.endswith("unchanged since 2026-09-28)")


def test_main_takes_a_date(monkeypatch, capsys):
    monkeypatch.setattr(jh, "config", lambda: CFG)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(json.dumps(m) for m in stream(jh.TOOL, [page([node()])]))))
    assert jh.main(["x", "extract", "--date", "2027-06-01"]) == 0
    assert capsys.readouterr().out.startswith("- 1 handoffs unchanged for more than 90 days (oldest: EX-1")
    assert jh.main(["x", "extract", "--date"]) == 2
