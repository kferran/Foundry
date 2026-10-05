import json

import pytest

from vaultlib import http, kusto

V2 = [
    {"FrameType": "DataSetHeader"},
    {"FrameType": "DataTable", "TableKind": "QueryProperties", "Columns": [], "Rows": []},
    {"FrameType": "DataTable", "TableKind": "PrimaryResult",
     "Columns": [{"ColumnName": "service"}, {"ColumnName": "n"}], "Rows": [["api", 3], ["worker", 1]]},
    {"FrameType": "DataSetCompletion", "HasErrors": False},
]


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(method, url, headers, body):
        seen.append((method, url, headers, json.loads(body) if body else None))
        return 200, json.dumps(V2).encode()

    monkeypatch.setattr(http, "request", fake)
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    return seen


def test_query_returns_primary_rows_as_dicts(calls):
    rows = kusto.query("https://example.kusto.windows.net", "prod", "Logs | take 1")
    assert rows == [{"service": "api", "n": 3}, {"service": "worker", "n": 1}]
    method, url, headers, body = calls[0]
    assert url == "https://example.kusto.windows.net/v2/rest/query"
    assert headers["Authorization"] == "Bearer tok"
    assert body["db"] == "prod" and body["properties"]["Options"]["request_readonly"] is True


@pytest.mark.parametrize("kql", [".show tables", "  .drop table Logs", "\n.set-or-append x <| print 1"])
def test_management_commands_are_refused(calls, kql):
    with pytest.raises(http.TelemetryError) as exc:
        kusto.query("https://example.kusto.windows.net", "prod", kql)
    assert exc.value.kind == "bad"
    assert calls == []


def test_status_mapping(monkeypatch):
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    for status, kind in ((401, "auth"), (403, "auth"), (429, "transient"), (503, "transient"), (400, "bad")):
        monkeypatch.setattr(http, "request", lambda *a, s=status: (s, b'{"error":{"message":"secret detail"}}'))
        with pytest.raises(http.TelemetryError) as exc:
            kusto.query("https://example.kusto.windows.net", "prod", "print 1")
        assert exc.value.kind == kind
        assert "secret detail" not in exc.value.reason


def test_missing_az_is_an_auth_error(monkeypatch):
    monkeypatch.setattr(kusto, "TOKEN_CMD", ["/nonexistent/az"])
    with pytest.raises(http.TelemetryError) as exc:
        kusto.token("https://example.kusto.windows.net")
    assert exc.value.kind == "auth"


def test_stub_directory_serves_fixtures_by_route(tmp_path, monkeypatch):
    (tmp_path / "kusto-logs.json").write_text(json.dumps(V2))
    monkeypatch.setenv("FOUNDRY_TELEMETRY_STUB", str(tmp_path))
    status, body = http.request("POST", "https://example.kusto.windows.net/v2/rest/query", {},
                                json.dumps({"csl": "Logs | where x"}).encode())
    assert status == 200 and json.loads(body) == V2
    (tmp_path / "kusto-spans.status").write_text("503")
    status, _ = http.request("POST", "https://example.kusto.windows.net/v2/rest/query", {},
                             json.dumps({"csl": "Traces | where x"}).encode())
    assert status == 503


def test_query_with_errors_after_primary_result(monkeypatch):
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    v2_with_error = [
        {"FrameType": "DataSetHeader"},
        {"FrameType": "DataTable", "TableKind": "PrimaryResult",
         "Columns": [{"ColumnName": "x"}], "Rows": [[1], [2]]},
        {"FrameType": "DataSetCompletion", "HasErrors": True},
    ]
    monkeypatch.setattr(http, "request", lambda *a: (200, json.dumps(v2_with_error).encode()))
    with pytest.raises(http.TelemetryError) as exc:
        kusto.query("https://example.kusto.windows.net", "prod", "Logs | take 2")
    assert exc.value.kind == "bad"


def test_query_without_primary_result(monkeypatch):
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    v2_no_primary = [
        {"FrameType": "DataSetHeader"},
        {"FrameType": "DataTable", "TableKind": "QueryProperties", "Columns": [], "Rows": []},
        {"FrameType": "DataSetCompletion", "HasErrors": False},
    ]
    monkeypatch.setattr(http, "request", lambda *a: (200, json.dumps(v2_no_primary).encode()))
    with pytest.raises(http.TelemetryError) as exc:
        kusto.query("https://example.kusto.windows.net", "prod", "Logs")
    assert exc.value.kind == "bad"


def test_last_headers_reset_between_calls(monkeypatch):
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    http.request.last_headers = {"Link": "x"}
    monkeypatch.setattr(http, "request", lambda *a: (200, json.dumps(V2).encode()))
    _, headers = http.json_call("POST", "https://example.kusto.windows.net/v2/rest/query", {})
    assert "Link" not in headers
