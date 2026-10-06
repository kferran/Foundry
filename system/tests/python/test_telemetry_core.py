# system/tests/python/test_telemetry_core.py
from datetime import datetime, timedelta, timezone

from helpers import write
from vaultlib import telemetry as t

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def adx(**kw):
    base = dict(path="system/telemetry/p.md", name="p", codebase="shop", partition="work", environment="prod", kind="adx",
                enabled=True, rank=50, sentry_url=None, sentry_org=None, sentry_projects=[], sentry_query="",
                adx_cluster="https://example.kusto.windows.net", adx_database="prod", adx_filter={},
                adx_signals=["logs", "spans"], adx_group_keys=[], covers=None)
    base.update(kw)
    return t.Source(**base)


def test_window_first_run_cap_and_lag():
    s, e, moved = t.window(None, NOW, "adx")
    assert (s, e, moved) == (NOW - timedelta(hours=24), NOW - timedelta(minutes=10), False)
    s, e, moved = t.window((NOW - timedelta(days=30)).isoformat(), NOW, "sentry")
    assert s == NOW - timedelta(minutes=2) - timedelta(days=7) and moved is True
    s, e, _ = t.window((NOW - timedelta(hours=1)).isoformat(), NOW, "adx")
    assert s == NOW - timedelta(hours=1)


def test_kql_filter_and_group_keys_are_quoted():
    q = t.kql_logs(adx(adx_filter={"deployment.instance": 'u"at'}, adx_group_keys=["app.module"]),
                   NOW - timedelta(hours=1), NOW)
    assert q.startswith("Logs\n")
    assert 'tostring(ResourceAttributes["deployment.instance"]) == "u\\"at"' in q
    assert 'module_0 = tostring(LogsAttributes["app.module"])' in q
    assert "SeverityNumber >= 17" in q and "| order by n desc\n| take 500" in q
    assert "Body" not in q
    s = t.kql_spans(adx(), NOW - timedelta(hours=1), NOW)
    assert s.startswith("Traces\n") and 'SpanKind == "SPAN_KIND_SERVER"' in s


def test_sanitize_and_fingerprint_collapse_ids():
    assert t.sanitize("GET /items/12345?sig=abc") == "GET /items/<n>"
    assert t.sanitize("ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b by bob@example.com") == "ticket <guid> by <email>"
    a = t.fingerprint("p", "span", {"route": t.sanitize("GET /items/1234")})
    b = t.fingerprint("p", "span", {"route": t.sanitize("GET /items/5678")})
    assert a == b and a.startswith("a-") and len(a) == 14
    assert t.fingerprint("p", "span", {"x": "1", "y": "2"}) == t.fingerprint("p", "span", {"y": "2", "x": "1"})
    assert t.event_id("40123") == "40123" and t.event_id("id 12345678901") == "id <n>"
    assert t.trace_id("0af7651916cd43dd8448eb211c80319c") == "0af7651916cd43dd8448eb211c80319c"
    assert t.trace_id("not a trace") == ""


def test_load_sources_reads_partition_and_skips_example(vault):
    write(vault, "system/codebases/shop.md", '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "personal"\nsearch_globs: ["*"]\n---\n')
    write(vault, "system/telemetry/example.md", '---\ntype: telemetry_source\nname: "example"\n---\n')
    write(vault, "system/telemetry/b.md", '---\ntype: telemetry_source\nname: "b"\ncodebase: "shop"\nenvironment: "uat"\nkind: "adx"\nrank: "60"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n')
    write(vault, "system/telemetry/a.md", '---\ntype: telemetry_source\nname: "a"\ncodebase: "shop"\nenvironment: "prod"\nkind: "sentry"\nrank: "10"\nenabled: "false"\nsentry_url: "https://s"\nsentry_org: "o"\nsentry_projects: ["api"]\n---\n')
    got = t.load_sources(vault)
    assert [s.name for s in got] == ["a", "b"]
    assert got[1].partition == "personal" and got[0].enabled is False and got[1].adx_signals == ["logs", "spans"]


def test_sanitize_decodes_urls_and_collapses_long_hex():
    assert "<email>" in t.sanitize("user bob%40example.com failed")
    assert "bob" not in t.sanitize("user bob%40example.com failed")
    assert t.sanitize("id 3f2b8a1e9c4d4e1f8a2b1c3d4e5f6a7b x") == "id <hex> x"
    assert t.event_id("4012") == "4012" and t.trace_id("0af7651916cd43dd8448eb211c80319c")


def test_kql_reopen_logs_no_duplicate_timestamp():
    first = (NOW - timedelta(hours=1)).isoformat()
    last = NOW.isoformat()
    q = t.kql_reopen("log", [], first, last, {"service": "api", "scope": "handler", "event_id": "123"})
    lines = q.split("\n")
    assert lines[0] == "Logs"
    # The second line should have the time range without duplicating the column name
    where_line = lines[1]
    assert where_line.startswith("| where Timestamp >=")
    assert "Timestamp >= Timestamp" not in where_line, f"Found duplicate 'Timestamp >= Timestamp' in: {where_line}"
    assert "and SeverityNumber >= 17" in where_line
    # Verify it contains the datetime range correctly
    assert "datetime(" in where_line and "and Timestamp <" in where_line


def test_kql_reopen_spans_no_duplicate_starttime():
    first = (NOW - timedelta(hours=1)).isoformat()
    last = NOW.isoformat()
    q = t.kql_reopen("span", [], first, last, {"service": "api", "route": "GET /items"})
    lines = q.split("\n")
    assert lines[0] == "Traces"
    where_line = lines[1]
    assert where_line.startswith("| where StartTime >=")
    assert "StartTime >= StartTime" not in where_line, f"Found duplicate 'StartTime >= StartTime' in: {where_line}"
    assert 'SpanKind == "SPAN_KIND_SERVER"' in where_line
    # Verify error conditions are present
    assert "SpanStatus" in where_line or "http.response.status_code" in where_line
    assert "datetime(" in where_line and "and StartTime <" in where_line
