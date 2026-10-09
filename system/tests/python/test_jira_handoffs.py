"""jira_handoffs.py: the handoff query and the check of a fetch session's stream (delivered work spec §3.2, §4)."""
import io
import json

import pytest

import jira_handoffs as jh

CFG = {"handoffs_site": "example.atlassian.net", "handoffs_projects": ["EX", "OPS"]}
SITE, JQL = jh.query(CFG)


def node(key="EX-1", assignee="Blake Sample", **fields):
    f = {"summary": f"Fix [{key}]\twith a tab", "status": {"name": "In Review", "statusCategory": {"key": "indeterminate"}},
         "assignee": {"displayName": assignee, "emailAddress": "blake@example.com"} if assignee else None,
         "statuscategorychangedate": "2026-09-28T09:00:00.000-0600"}
    f.update(fields)
    return {"key": key, "fields": f, "webUrl": f"https://elsewhere.example/{key}"}


def stream(*page_nodes, jql=JQL, site=SITE, tool=jh.TOOL, error=False, more=False, result="success"):
    """A session that loads the tool and searches once per page."""
    s = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0", "name": "ToolSearch", "input": {}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0",
                                                   "content": [{"type": "tool_reference", "tool_name": jh.TOOL}]}]}}]
    for n, nodes in enumerate(page_nodes, 1):
        s.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{n}", "name": tool, "input": {"cloudId": site, "jql": jql, "maxResults": 100}}]}})
        info = {"hasNextPage": more and n == len(page_nodes), "endCursor": "c"}
        s.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}", "is_error": error,
                                                           "content": "<persisted-output>…"}]},
                  "tool_use_result": {"structuredContent": {"issues": {"nodes": nodes, "pageInfo": info}}}})
    s.append({"type": "result", "subtype": result, "is_error": result != "success"})
    return s


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
    lines = jh.extract(stream([node("EX-1")], [node("EX-1"), node("OPS-2", assignee=None)]), CFG)
    assert lines == [
        "- [ ] [EX-1](https://example.atlassian.net/browse/EX-1) Fix (EX-1) with a tab (Blake Sample, In Review, unchanged since 2026-09-28)",
        "- [ ] [OPS-2](https://example.atlassian.net/browse/OPS-2) Fix (OPS-2) with a tab (unassigned, In Review, unchanged since 2026-09-28)"]
    assert "blake@example.com" not in json.dumps(lines)


def test_a_session_that_stopped_before_the_last_page_fails_closed():
    assert "last page" in fails(1, stream([node()], more=True))


@pytest.mark.parametrize("kw,code", [
    ({"tool": "mcp__claude_ai_Atlassian__createJiraIssue"}, 7),
    ({"jql": "project = EX"}, 7),
    ({"site": "other.atlassian.net"}, 7),
    ({"error": True}, 6),
    ({"result": "error_max_turns"}, 1),
])
def test_unexpected_tools_arguments_and_errors(kw, code):
    fails(code, stream([node()], **kw))


def test_no_connector_and_no_call():
    s = stream([node()])
    assert fails(3, [s[0], s[-1]]) == "no Atlassian connector reachable"
    assert "never called" in fails(1, s[:2] + [s[-1]])


@pytest.mark.parametrize("bad", [
    {"key": "not a key", "fields": node()["fields"]},
    node(statuscategorychangedate=None),
    node(status={}),
    "a string",
])
def test_malformed_tickets_fail_closed(bad):
    fails(1, stream([node("EX-9"), bad]))


def test_a_result_without_an_issues_list_fails_closed():
    s = stream([node()])
    s[3]["tool_use_result"] = {"structuredContent": {"text": "no issues here"}}
    assert "no issues list" in fails(1, s)


def test_main_prints_the_lines_and_one_reason_line(monkeypatch, capsys):
    monkeypatch.setattr(jh, "config", lambda: CFG)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(json.dumps(m) for m in stream([node()]))))
    assert jh.main(["x", "extract"]) == 0
    assert capsys.readouterr().out.startswith("- [ ] [EX-1]")
    monkeypatch.setattr(jh, "config", lambda: {})
    assert jh.main(["x", "query"]) == 2
    assert capsys.readouterr().err == "jira_handoffs: handoffs_projects lists no Jira project keys\n"
