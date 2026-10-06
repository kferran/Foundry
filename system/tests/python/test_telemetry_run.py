# system/tests/python/test_telemetry_run.py
import json
from datetime import datetime, timedelta, timezone

import pytest

from helpers import write
from vaultlib import http, kusto, sentry, telemetry_run

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
DAY = NOW.astimezone().strftime("%Y-%m-%d")
CB = '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n'
ADX = ('---\ntype: telemetry_source\nname: "prod-adx"\ncodebase: "shop"\nenvironment: "prod"\nkind: "adx"\n'
       'adx_cluster: "https://example.kusto.windows.net"\nadx_database: "prod"\nadx_signals: ["logs"]\n{covers}---\n')
SEN = ('---\ntype: telemetry_source\nname: "prod-sentry"\ncodebase: "shop"\nenvironment: "prod"\nkind: "sentry"\n'
       'sentry_url: "https://sentry.example.com"\nsentry_org: "acme"\nsentry_projects: ["api"]\n---\n')
LOG_ROW = {"service": "api", "scope": "Shop.Orders", "event_id": "4012", "n": 3, "first": "2026-10-05T10:00:00Z",
           "last": "2026-10-05T11:00:00Z", "traces": 2, "sample_trace": "0af7651916cd43dd8448eb211c80319c"}


@pytest.fixture
def v(vault, monkeypatch):
    write(vault, "system/codebases/shop.md", CB)
    monkeypatch.setattr(kusto, "token", lambda c: "tok")
    return vault


def jsonl(v):
    return [json.loads(l) for l in (v / "system/logs/telemetry-2026-10.jsonl").read_text().splitlines()]


def test_adx_run_writes_note_logs_and_advances_checkpoint(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main([], v, NOW) == 0
    notes = list((v / "raw/telemetry").glob("prod-adx-a-*.md"))
    assert len(notes) == 1
    line = jsonl(v)[-1]
    assert line["source"] == "prod-adx" and line["new"] == 1 and line["exit"] == 0
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())
    assert state["sources"]["prod-adx"]["checkpoint"] == (NOW - timedelta(minutes=10)).isoformat()


def _count(v):
    note = next((v / "raw/telemetry").glob("prod-adx-a-*.md"))
    return int([l for l in note.read_text().splitlines() if l.startswith("count:")][0].split('"')[1])


def test_failed_source_keeps_checkpoint_and_does_not_double_count(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    telemetry_run.main([], v, NOW)
    def boom(*a, **k):
        raise http.TelemetryError("transient", "HTTP 503")
    monkeypatch.setattr(kusto, "query", boom)
    assert telemetry_run.main([], v, NOW + timedelta(hours=1)) == 1
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())
    assert state["sources"]["prod-adx"]["checkpoint"] == (NOW - timedelta(minutes=10)).isoformat()
    assert state["sources"]["prod-adx"]["failures"] == 1
    fail = jsonl(v)[-1]
    assert fail["exit"] == 1 and fail["new"] == 0 and "window" in fail
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main([], v, NOW + timedelta(hours=2)) == 0
    assert _count(v) == 6


def test_lost_state_is_rebuilt_from_notes(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    telemetry_run.main([], v, NOW)
    (v / "system/logs/telemetry_state.json").unlink()
    assert telemetry_run.main([], v, NOW + timedelta(hours=1)) == 0
    # rebuild keeps the note's count (3) and the rerun adds the same 3 rows again: 6
    assert _count(v) == 6


def test_unexpected_error_does_not_stop_other_sources_and_state_is_saved(v, monkeypatch):
    write(v, "system/telemetry/a-bad.md", ADX.format(covers="").replace("prod-adx", "a-bad"))
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    calls = []
    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("secret detail")
        return [LOG_ROW]
    monkeypatch.setattr(kusto, "query", flaky)
    assert telemetry_run.main([], v, NOW) == 1
    assert len(list((v / "raw/telemetry").glob("prod-adx-a-*.md"))) == 1
    lines = jsonl(v)
    assert any("ValueError" in l.get("error", "") and "secret" not in l["error"] for l in lines)
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())
    assert state["sources"]["a-bad"]["failures"] == 1 and "checkpoint" not in state["sources"]["a-bad"]
    assert state["sources"]["prod-adx"]["checkpoint"]


def test_cap_leftovers_are_retried_next_run(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='covers: "prod-sentry"\n'))
    rows = [dict(LOG_ROW, event_id=str(1000 + i)) for i in range(25)]
    monkeypatch.setattr(kusto, "query", lambda *a, **k: rows)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    looked = []
    monkeypatch.setattr(sentry, "issue_for_trace", lambda b, o, t: looked.append(t) or {"id": "101", "shortId": "API-1"})
    telemetry_run.main([], v, NOW)
    assert len(looked) == 20
    looked.clear()
    telemetry_run.main([], v, NOW + timedelta(hours=1))
    assert len(looked) == 5
    covered = [n for n in (v / "raw/telemetry").glob("prod-adx-*.md") if 'covered: "true"' in n.read_text()]
    assert len(covered) == 25


def test_three_failures_alert_once_a_day(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    def boom(*a, **k):
        raise http.TelemetryError("transient", "HTTP 503")
    monkeypatch.setattr(kusto, "query", boom)
    for h in range(5):
        telemetry_run.main([], v, NOW + timedelta(hours=h))
    alerts = (v / f"system/logs/alerts_{DAY}.md").read_text().splitlines()
    assert len([a for a in alerts if "[telemetry]" in a and "prod-adx" in a]) == 1


def test_auth_failure_alerts_immediately(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    def noauth(c):
        raise http.TelemetryError("auth", "run az login")
    monkeypatch.setattr(kusto, "token", noauth)
    monkeypatch.setattr(kusto, "query", lambda *a, **k: kusto.token("x"))
    assert telemetry_run.main([], v, NOW) == 1
    assert "run az login" in (v / f"system/logs/alerts_{DAY}.md").read_text()


def test_covered_group_links_sentry_issue_and_lookup_cap(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='covers: "prod-sentry"\n'))
    rows = [dict(LOG_ROW, event_id=str(1000 + i)) for i in range(25)]
    monkeypatch.setattr(kusto, "query", lambda *a, **k: rows)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    looked = []
    monkeypatch.setattr(sentry, "issue_for_trace", lambda b, o, t: looked.append(t) or {"id": "101", "shortId": "API-1"})
    telemetry_run.main([], v, NOW)
    assert len(looked) == 20
    covered = [n for n in (v / "raw/telemetry").glob("prod-adx-*.md") if 'covered: "true"' in n.read_text()]
    assert len(covered) == 20


def test_sentry_issue_resolved_in_sentry_resolves_note(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    issue = {"id": "101", "shortId": "API-1", "permalink": "https://sentry.example.com/i/101/", "project": "api",
             "level": "error", "status": "unresolved", "substatus": "new", "firstSeen": "2026-10-05T10:00:00Z",
             "lastSeen": "2026-10-05T11:00:00Z", "count": "4", "type": "KeyError", "culprit": "a.py in f", "environment": "api"}
    monkeypatch.setattr(sentry, "issues", lambda *a: [issue])
    telemetry_run.main([], v, NOW)
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    monkeypatch.setattr(sentry, "issue_status", lambda *a: "resolved")
    telemetry_run.main([], v, NOW + timedelta(hours=1))
    assert 'status: "resolved"' in (v / "raw/telemetry/prod-sentry-s-101.md").read_text()


def test_dry_run_and_check_write_nothing(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main(["--dry-run"], v, NOW) == 0
    assert telemetry_run.main(["--check", "prod-adx"], v, NOW) == 0
    assert not (v / "raw/telemetry").exists() or not list((v / "raw/telemetry").glob("*.md"))
    assert not (v / "system/logs/telemetry_state.json").exists()


OFF = ('---\ntype: telemetry_source\nname: "off"\ncodebase: "shop"\nenvironment: "prod"\nkind: "adx"\nenabled: "false"\n'
       'adx_cluster: "https://example.kusto.windows.net"\nadx_database: "prod"\nadx_signals: ["logs"]\n---\n')


def test_dry_run_writes_no_alerts(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    def noauth(*a, **k):
        raise http.TelemetryError("auth", "run az login")
    monkeypatch.setattr(kusto, "query", noauth)
    assert telemetry_run.main(["--dry-run"], v, NOW) == 1
    assert not list((v / "system/logs").glob("alerts_*.md"))


def test_list_prints_enabled_sources(v, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    write(v, "system/telemetry/off.md", OFF)
    assert telemetry_run.main(["--list"], v, NOW) == 0
    assert capsys.readouterr().out.split() == ["prod-adx"]


def test_usage_errors_exit_2(v):
    assert telemetry_run.main(["--bogus"], v, NOW) == 2
    assert telemetry_run.main(["--source", "nope"], v, NOW) == 2
