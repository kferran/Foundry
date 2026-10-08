import json
import os
from datetime import datetime, timezone

import pytest

from vaultlib import http, sentry

ISSUE = {"id": "101", "shortId": "API-1", "permalink": "https://sentry.example.com/organizations/acme/issues/101/",
         "project": {"slug": "api"}, "level": "error", "status": "unresolved", "substatus": "new",
         "firstSeen": "2026-10-05T10:00:00Z", "lastSeen": "2026-10-05T11:00:00Z", "count": "4", "userCount": 2,
         "title": "Failed for ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b", "culprit": "orders/Submit.cs in Submit",
         "metadata": {"type": "System.InvalidOperationException", "value": "user bob@example.com"},
         "tags": [{"key": "environment", "value": "api"}]}


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    f = tmp_path / "sentry.token"
    f.write_text("sntrys_abc\n")
    os.chmod(f, 0o600)
    monkeypatch.setenv("FOUNDRY_SENTRY_TOKEN_FILE", str(f))
    return f


def test_token_refuses_group_readable_file(token_file):
    os.chmod(token_file, 0o644)
    with pytest.raises(http.TelemetryError) as exc:
        sentry.token()
    assert exc.value.kind == "auth" and "0600" in exc.value.reason


def test_issues_keep_only_allowed_fields_and_follow_cursor(token_file, monkeypatch):
    pages = [([ISSUE], {"Link": '<https://x/?cursor=0:100:0>; rel="next"; results="true"; cursor="0:100:0"'}),
             ([dict(ISSUE, id="102", shortId="API-2")], {"Link": '<https://x>; rel="next"; results="false"; cursor="0:200:0"'})]
    urls = []

    def fake(method, url, headers, body=None):
        urls.append(url)
        return pages[len(urls) - 1]

    monkeypatch.setattr(http, "json_call", fake)
    got = sentry.issues("https://sentry.example.com", "acme", ["7"], "is:unresolved",
                        datetime(2026, 10, 5, 9, tzinfo=timezone.utc))
    assert [g["shortId"] for g in got] == ["API-1", "API-2"]
    assert set(got[0]) <= set(sentry.KEEP)
    assert got[0]["type"] == "System.InvalidOperationException" and got[0]["environment"] == "api"
    assert got[0]["title"] == ISSUE["title"] and "bob@example.com" not in json.dumps(got)
    assert "lastSeen%3A%3E%3D2026-10-05T09%3A00%3A00" in urls[0] and "project=7" in urls[0]
    assert "cursor=0%3A100%3A0" in urls[1]


def test_page_cap_is_five(token_file, monkeypatch):
    link = {"Link": '<https://x>; rel="next"; results="true"; cursor="c"'}
    monkeypatch.setattr(http, "json_call", lambda *a, **k: ([ISSUE], link))
    assert len(sentry.issues("https://sentry.example.com", "acme", ["7"], "", datetime.now(timezone.utc))) == 5


def test_issue_for_trace(token_file, monkeypatch):
    monkeypatch.setattr(http, "json_call", lambda *a, **k: ({"data": [{"issue": "API-1", "issue.id": 101}]}, {}))
    assert sentry.issue_for_trace("https://sentry.example.com", "acme", "abc") == {"id": "101", "shortId": "API-1"}
    monkeypatch.setattr(http, "json_call", lambda *a, **k: ({"data": []}, {}))
    assert sentry.issue_for_trace("https://sentry.example.com", "acme", "abc") is None


def test_issue_for_trace_rejects_unchecked_ids(token_file, monkeypatch):
    for row in ({"issue.id": 5}, {"issue": "A B", "issue.id": 5},
                {"issue": "API-1", "issue.id": "x1"}, {"issue": "API-1"}):
        monkeypatch.setattr(http, "json_call", lambda *a, **k: ({"data": [row]}, {}))
        assert sentry.issue_for_trace("https://sentry.example.com", "acme", "abc") is None, row
