# system/tests/python/test_telemetry_run.py
import json
from datetime import datetime, timedelta, timezone

import pytest

from helpers import write
from telemetrylib import http, kusto, sentry, telemetry_run

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
DAY = NOW.astimezone().strftime("%Y-%m-%d")
CB = '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n'
ADX = ('---\ntype: telemetry_source\nname: "prod-adx"\ncodebase: "shop"\nenvironment: "prod"\nkind: "adx"\n'
       'adx_cluster: "https://example.kusto.windows.net"\nadx_database: "prod"\nadx_signals: ["logs"]\n{covers}---\n')
SEN = ('---\ntype: telemetry_source\nname: "prod-sentry"\ncodebase: "shop"\nenvironment: "prod"\nkind: "sentry"\n'
       'sentry_url: "https://sentry.example.com"\nsentry_org: "acme"\nsentry_projects: ["api"]\n---\n')
LOG_ROW = {"service": "api", "scope": "Shop.Orders", "event_id": "4012", "n": 3, "first_ts": "2026-10-05T10:00:00Z",
           "last_ts": "2026-10-05T11:00:00Z", "traces": 2, "sample_trace": "0af7651916cd43dd8448eb211c80319c"}


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


LOGS = ADX.format(covers="").replace("prod-adx", "prod-logs")


def _down(*a, **k):
    raise http.TelemetryError("transient", "HTTP 503")


def _source_alerts(v):
    """The [telemetry_source] lines of every alerts file, without their time stamp (#293)."""
    return [l.split(" ", 2)[2] for p in sorted((v / "system/logs").glob("alerts_*.md"))
            for l in p.read_text().splitlines() if "[telemetry_source]" in l]


def _at(h):
    return (NOW + timedelta(hours=h)).astimezone().strftime("%Y-%m-%d %H:%M")


def test_a_failing_source_posts_once_when_it_starts_and_its_failure_line_reaches_slack(v, monkeypatch):
    write(v, "system/telemetry/prod-logs.md", LOGS)
    monkeypatch.setattr(kusto, "query", _down)
    assert telemetry_run.main([], v, NOW) == 1
    assert _source_alerts(v) == [f"[telemetry_source] prod-logs: failing since {_at(0)} (transient: HTTP 503)"]
    for h in (1, 2, 3):   # still failing inside four hours: nothing more
        assert telemetry_run.main([], v, NOW + timedelta(hours=h)) == 1
    assert len(_source_alerts(v)) == 1
    alerts = "".join(p.read_text() for p in (v / "system/logs").glob("alerts_*.md"))
    assert "[telemetry] prod-logs" not in alerts   # the brief lists the failure once, under the new tag


def test_a_source_still_failing_posts_again_every_four_hours(v, monkeypatch):
    write(v, "system/telemetry/prod-logs.md", LOGS)
    monkeypatch.setattr(kusto, "query", _down)
    for h in range(10):
        telemetry_run.main([], v, NOW + timedelta(hours=h))
    assert _source_alerts(v)[1:] == [f"[telemetry_source] prod-logs: still failing for 4 h, since {_at(0)} "
                                     "(transient: HTTP 503)",
                                     f"[telemetry_source] prod-logs: still failing for 8 h, since {_at(0)} "
                                     "(transient: HTTP 503)"]


def test_an_hourly_run_a_few_seconds_early_still_posts_at_four_hours(v, monkeypatch):
    write(v, "system/telemetry/prod-logs.md", LOGS)
    monkeypatch.setattr(kusto, "query", _down)
    for h in range(5):   # the run at four hours, four seconds early, posts
        telemetry_run.main([], v, NOW + timedelta(hours=h, seconds=-h))
    assert [l.split(":", 1)[1] for l in _source_alerts(v)[1:]] == [
        f" still failing for 4 h, since {_at(0)} (transient: HTTP 503)"]


def test_the_failure_line_is_a_slack_event_and_routine_telemetry_is_not(v, monkeypatch):
    from vaultlib import notify
    write(v, "system/config.md", '---\ntype: config\nextensions: ["handoffs", "telemetry"]\n---\n')
    write(v, "system/telemetry/prod-logs.md", LOGS)
    notify.commit(v, notify.collect(v, NOW)[1])   # the first collect only sets the cursor
    monkeypatch.setattr(kusto, "query", _down)
    telemetry_run.main([], v, NOW)
    with open(v / f"system/logs/alerts_{DAY}.md", "a", encoding="utf-8") as f:
        f.write("- 12:00:01 [telemetry] prod-logs: 900 groups; only 500 kept\n")
    events, _ = notify.collect(v, NOW)
    assert events == [f"Alert {NOW.astimezone():%H:%M:%S} [telemetry_source] prod-logs: failing since {_at(0)} "
                      "(transient: HTTP 503)"]


def test_a_recovered_source_posts_once_with_the_backfilled_window_and_its_counts(v, monkeypatch):
    write(v, "system/telemetry/prod-logs.md", LOGS)
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    telemetry_run.main([], v, NOW)
    monkeypatch.setattr(kusto, "query", _down)
    for h in (1, 2):
        telemetry_run.main([], v, NOW + timedelta(hours=h))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW, dict(LOG_ROW, event_id="5000")])
    assert telemetry_run.main([], v, NOW + timedelta(hours=3)) == 0
    lag = timedelta(minutes=10)
    start, end = (NOW - lag).astimezone(), (NOW + timedelta(hours=3) - lag).astimezone()
    assert _source_alerts(v)[1:] == [f"[telemetry_source] prod-logs: recovered after 2 h; backfilled "
                                     f"{start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M}: 1 new, 0 resolved"]
    assert telemetry_run.main([], v, NOW + timedelta(hours=4)) == 0
    assert len(_source_alerts(v)) == 2
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())["sources"]["prod-logs"]
    assert "failing_since" not in state and "failure_posted" not in state


def test_a_corrupt_state_file_does_not_stop_the_fetch_or_its_failure_alert(v, monkeypatch):
    write(v, "system/telemetry/prod-logs.md", LOGS)
    write(v, "system/logs/telemetry_state.json", "{not json")
    monkeypatch.setattr(kusto, "query", _down)
    assert telemetry_run.main([], v, NOW) == 1
    assert len(_source_alerts(v)) == 1
    assert json.loads((v / "system/logs/telemetry_state.json").read_text())["sources"]["prod-logs"]["failing_since"]


def test_the_source_tag_is_now_through_the_manifest_and_routine_telemetry_waits_for_the_brief(v):
    from vaultlib import alerts
    write(v, "system/config.md", '---\ntype: config\nextensions: ["handoffs", "telemetry"]\n---\n')
    ext = alerts.extension_tags(v)
    assert ext == {"telemetry_source": "now"}
    assert alerts.severity("- 06:10:00 [telemetry_source] prod-logs: failing since 2026-10-05 06:00 (x)", ext) == "now"
    assert alerts.severity("- 06:10:00 [telemetry] prod-logs: 900 groups; only 500 kept", ext) == "brief"
    assert alerts.severity("- 06:10:00 [incident] prod-logs: new production error in api", ext) == "now"


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


def _issue(i, status="unresolved"):
    return {"id": str(i), "shortId": f"API-{i}", "permalink": f"https://sentry.example.com/i/{i}/", "project": "api",
            "level": "error", "status": status, "substatus": "new", "firstSeen": "2026-10-05T10:00:00Z",
            "lastSeen": "2026-10-05T11:00:00Z", "count": "4", "type": f"KeyError{i}", "culprit": "a.py in f",
            "environment": "api"}


def _incidents(v):
    path = v / f"system/logs/alerts_{DAY}.md"
    return [l for l in path.read_text().splitlines() if "[incident]" in l] if path.exists() else []


def test_a_new_production_error_pushes_one_incident_line_and_the_first_run_pushes_none(v, monkeypatch):
    # incident push (#158 follow-up): Slack hears about a new production error group at the next tick
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [_issue(101)])
    telemetry_run.main([], v, NOW)                       # first run: every existing group is new, none is pushed
    assert _incidents(v) == []
    monkeypatch.setattr(sentry, "issues", lambda *a: [_issue(101), _issue(102)])
    telemetry_run.main([], v, NOW + timedelta(minutes=10))
    assert [l.split(" ", 2)[2] for l in _incidents(v)] == [
        "[incident] prod-sentry: new production error in api: KeyError102 (4 events) raw/telemetry/prod-sentry-s-102.md"]
    telemetry_run.main([], v, NOW + timedelta(minutes=20))
    assert len(_incidents(v)) == 1


def test_a_source_outside_production_pushes_nothing(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN.replace('environment: "prod"', 'environment: "staging"'))
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    telemetry_run.main([], v, NOW)
    monkeypatch.setattr(sentry, "issues", lambda *a: [_issue(102)])
    telemetry_run.main([], v, NOW + timedelta(minutes=10))
    assert _incidents(v) == []


def test_a_resolved_production_error_that_comes_back_pushes_and_a_burst_is_capped(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [_issue(101)])
    telemetry_run.main([], v, NOW)
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    monkeypatch.setattr(sentry, "issue_status", lambda *a: "resolved")
    telemetry_run.main([], v, NOW + timedelta(minutes=10))
    monkeypatch.setattr(sentry, "issues", lambda *a: [_issue(101)] + [_issue(i) for i in range(201, 206)])
    telemetry_run.main([], v, NOW + timedelta(minutes=20))
    got = [l.split(" ", 2)[2] for l in _incidents(v)]
    assert got[0] == ("[incident] prod-sentry: a resolved production error is back in api: KeyError101 (4 events) "
                      "raw/telemetry/prod-sentry-s-101.md")
    assert len(got) == 4 and got[3] == "[incident] prod-sentry: and 3 more new production errors (see the brief)"


def test_dry_run_and_check_write_nothing(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main(["--dry-run"], v, NOW) == 0
    assert telemetry_run.main(["--check", "prod-adx"], v, NOW) == 0
    assert not (v / "raw/telemetry").exists() or not list((v / "raw/telemetry").glob("*.md"))
    assert not (v / "system/logs/telemetry_state.json").exists()


@pytest.mark.parametrize("kind, reason, line", [
    ("auth", "run az login", "auth: run az login"),
    ("transient", "network: URLError", "network: example.kusto.windows.net (URLError)"),
    ("transient", "az timed out", "timeout: az timed out"),
    ("transient", "HTTP 503", "connector: HTTP 503"),
    ("bad", "no primary result", "other: no primary result"),
])
def test_check_prints_the_failure_class(v, monkeypatch, capsys, kind, reason, line):
    # connector health spec §2: the smoke check reads the class to name the credential or the host
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    def fail(*a, **k):
        raise http.TelemetryError(kind, reason)
    monkeypatch.setattr(kusto, "query", fail)
    assert telemetry_run.main(["--check", "prod-adx"], v, NOW) == 1
    assert capsys.readouterr().out.strip() == f"telemetry_fetch: prod-adx: {line}"


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


def _count_of(v, eid):
    for n in (v / "raw/telemetry").glob("prod-adx-a-*.md"):
        if f"#{eid}" in n.read_text():
            return int([l for l in n.read_text().splitlines() if l.startswith("count:")][0].split('"')[1])


def test_missing_note_drops_group_and_does_not_block_or_inflate(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    rows = [dict(LOG_ROW, event_id="1"), dict(LOG_ROW, event_id="2")]
    monkeypatch.setattr(kusto, "query", lambda *a, **k: rows)
    telemetry_run.main([], v, NOW)
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())
    gone = next(k for k, g in state["groups"].items() if "#1" in (v / g["note"]).read_text())
    (v / state["groups"][gone]["note"]).unlink()
    later = NOW + timedelta(days=8)
    for h in range(2):
        t = later + timedelta(hours=h)
        monkeypatch.setattr(kusto, "query", lambda *a, **k: [dict(LOG_ROW, event_id="2")])
        assert telemetry_run.main([], v, t) == 0
    assert _count_of(v, "2") == 3 + 3 + 3
    assert gone not in json.loads((v / "system/logs/telemetry_state.json").read_text())["groups"]


def test_failed_source_leaves_state_counts_and_checkpoint_unchanged(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    telemetry_run.main([], v, NOW)
    path = v / "system/logs/telemetry_state.json"
    before = json.loads(path.read_text())
    real = telemetry_run.Store.resolve_stale
    def boom(*a, **k):
        raise RuntimeError("after upsert")
    monkeypatch.setattr(telemetry_run.Store, "resolve_stale", boom)
    assert telemetry_run.main([], v, NOW + timedelta(hours=1)) == 1
    after = json.loads(path.read_text())
    assert after["groups"] == before["groups"]
    assert after["sources"]["prod-adx"]["checkpoint"] == before["sources"]["prod-adx"]["checkpoint"]
    assert after["sources"]["prod-adx"]["failures"] == 1
    monkeypatch.setattr(telemetry_run.Store, "resolve_stale", real)
    assert telemetry_run.main([], v, NOW + timedelta(hours=2)) == 0
    assert _count(v) == 6


def _sentry_issue(i):
    return {"id": str(i), "shortId": f"API-{i}", "permalink": f"https://sentry.example.com/i/{i}/", "project": "api",
            "level": "error", "status": "unresolved", "substatus": "new", "firstSeen": "2026-10-05T10:00:00Z",
            "lastSeen": "2026-10-05T11:00:00Z", "count": "4", "type": "KeyError", "culprit": "a.py in f", "environment": "api"}


def _two_sentry_notes(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [_sentry_issue(101), _sentry_issue(102)])
    telemetry_run.main([], v, NOW)
    monkeypatch.setattr(sentry, "issues", lambda *a: [])


def test_deleted_sentry_issue_404_counts_as_resolved(v, monkeypatch):
    _two_sentry_notes(v, monkeypatch)
    def status(b, o, i):
        if i == "101":
            raise http.TelemetryError("bad", "HTTP 404")
        return "unresolved"
    monkeypatch.setattr(sentry, "issue_status", status)
    assert telemetry_run.main([], v, NOW + timedelta(hours=1)) == 0
    assert 'status: "resolved"' in (v / "raw/telemetry/prod-sentry-s-101.md").read_text()
    assert 'status: "active"' in (v / "raw/telemetry/prod-sentry-s-102.md").read_text()


def test_one_issue_status_error_skips_that_issue_only(v, monkeypatch):
    _two_sentry_notes(v, monkeypatch)
    def status(b, o, i):
        if i == "101":
            raise http.TelemetryError("transient", "HTTP 429")
        return "resolved"
    monkeypatch.setattr(sentry, "issue_status", status)
    assert telemetry_run.main([], v, NOW + timedelta(hours=1)) == 0
    assert 'status: "active"' in (v / "raw/telemetry/prod-sentry-s-101.md").read_text()
    assert 'status: "resolved"' in (v / "raw/telemetry/prod-sentry-s-102.md").read_text()


def test_dry_run_reads_the_saved_checkpoint(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    telemetry_run.main([], v, NOW)
    seen = []
    monkeypatch.setattr(kusto, "query", lambda c, d, kql, n: seen.append(kql) or [LOG_ROW])
    assert telemetry_run.main(["--dry-run"], v, NOW + timedelta(hours=1)) == 0
    assert f"datetime({(NOW - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')})" in seen[0]
    # a corrupt state file is neither moved nor rewritten by a dry run
    sp = v / "system/logs/telemetry_state.json"
    sp.write_text("{bad")
    assert telemetry_run.main(["--dry-run"], v, NOW) == 0
    assert sp.read_text() == "{bad" and not (v / "system/quarantine").exists()


def test_bad_source_file_is_reported_and_others_still_run(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    write(v, "system/telemetry/bad-rank.md", ADX.format(covers="rank: \"high\"\n").replace("prod-adx", "bad-rank"))
    write(v, "system/telemetry/bad-cb.md", ADX.format(covers="").replace("prod-adx", "bad-cb").replace('"shop"', '"nope"'))
    write(v, "system/telemetry/bad-en.md", ADX.format(covers="enabled: \"maybe\"\n").replace("prod-adx", "bad-en"))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main(["--list"], v, NOW) == 0
    assert capsys.readouterr().out.split() == ["prod-adx"]
    assert telemetry_run.main([], v, NOW) == 1
    lines = {l["source"]: l for l in jsonl(v)}
    assert lines["prod-adx"]["exit"] == 0
    assert lines["bad-rank"]["error"] == "invalid source: rank"
    assert lines["bad-cb"]["error"] == "invalid source: codebase"
    assert lines["bad-en"]["error"] == "invalid source: enabled"


GUID = "3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b"
APP = "A1-23B4C-D-56"
DIRTY = (f"Ticket {GUID} for application {APP} failed for bob@example.com and bob%40example.com "
         "Authorization: Bearer abc.def.ghi Bearer Zm9vYmFyYmF6cXV4MTIzNDU2 password=hunter2 "
         "Server=db;Pwd=s3cretPwd;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==;Database=x "
         "https://x.example.com/p?sig=AbCdEfSAS postgres://app:pgpass99@db/x AKIAIOSFODNN7EXAMPLE "
         '{"password":"jsonpass1"}')
NEVER = ["bob@example.com", "bob%40example.com", "abc.def.ghi", "Zm9vYmFyYmF6cXV4MTIzNDU2", "hunter2", "s3cretPwd",
         "Zm9vYmFyQUNDT1VOVEtFWQ", "AbCdEfSAS", "pgpass99", "AKIAIOSFODNN7EXAMPLE", "jsonpass1"]


def test_privacy_end_to_end(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='covers: "prod-sentry"\n').replace(
        'adx_signals: ["logs"]', 'adx_signals: ["logs", "spans"]'))
    log = dict(LOG_ROW, scope=DIRTY, event_id=DIRTY, service=DIRTY, message=DIRTY)
    span = {"service": DIRTY, "route": "GET /a/" + DIRTY, "status": "500", "n": 2, "first_ts": "2026-10-05T10:00:00Z",
            "last_ts": "2026-10-05T11:00:00Z", "traces": 1, "sample_trace": DIRTY}
    monkeypatch.setattr(kusto, "query", lambda c, d, kql, n: [log] if "Logs" in kql.split("\n")[0] else [span])
    issue = dict(_sentry_issue(101), title=DIRTY, culprit=DIRTY, type=DIRTY, environment=DIRTY,
                 metadata={"value": DIRTY, "type": DIRTY}, permalink="https://sentry.example.com/i/101/?sig=AbCdEfSAS")
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [issue])
    monkeypatch.setattr(sentry, "issue_for_trace", lambda *a: None)
    assert telemetry_run.main([], v, NOW) == 0
    assert telemetry_run.main(["--dry-run"], v, NOW + timedelta(hours=1)) == 0
    assert telemetry_run.main([], v, NOW + timedelta(hours=2)) == 0
    out = capsys.readouterr().out
    files = [p for p in v.rglob("*") if p.is_file() and ("raw/telemetry" in str(p) or "system/logs" in str(p))]
    blobs = [out] + [p.read_text() for p in files]
    assert len(blobs) > 5
    for s in NEVER:
        assert all(s not in b for b in blobs), s
    notes = {p.name: p.read_text() for p in files if p.suffix == ".md" and "raw/telemetry" in str(p)}
    log_note = next(n for n in notes.values() if 'kind: "log"' in n)
    for note in (notes["prod-sentry-s-101.md"], log_note):
        msg = [l for l in note.splitlines() if l.startswith("message:")][0]
        assert GUID in msg and APP in msg and "Ticket " in msg


def test_log_group_shows_real_scope_and_message(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    scope = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
    row = dict(LOG_ROW, service="worker", scope=scope, event_id="9908", message=f"Ticket {GUID} failed")
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [row])
    assert telemetry_run.main([], v, NOW) == 0
    [note] = [p.read_text() for p in (v / "raw/telemetry").glob("prod-adx-a-*.md")]
    assert f'exception: "{scope}#9908"' in note and "high_entropy" not in note
    assert f'message: "Ticket {GUID} failed"' in note


def test_sentry_title_becomes_the_message(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    title = f"InvalidOperationException: ticket {GUID} for {APP}"
    monkeypatch.setattr(sentry, "issues", lambda *a: [dict(_sentry_issue(101), title=title)])
    assert telemetry_run.main([], v, NOW) == 0
    assert f'message: "{title}"' in (v / "raw/telemetry/prod-sentry-s-101.md").read_text()


def _two_signal_source(v, name):
    write(v, f"system/telemetry/{name}.md", ADX.format(covers="").replace('"prod-adx"', f'"{name}"').replace(
        'adx_signals: ["logs"]', 'adx_signals: ["logs", "spans"]\nadx_group_keys: ["app.partition", "app.slice"]'))


def _rows(logs, spans):
    return lambda c, d, kql, n: logs if kql.startswith("Logs") else spans


SPAN_ROW = {"service": "core-api", "status": 500, "n": 1, "first_ts": "2026-10-05T10:00:00Z",
            "last_ts": "2026-10-05T11:00:00Z", "traces": 1, "sample_trace": "0af7651916cd43dd8448eb211c80319c"}


def test_vault_fingerprints_without_the_marker_do_not_change(v, monkeypatch):
    """Groups with no [REDACTED:high_entropy] in their keys: their fingerprints, and so their note file names, must
    not move. The names were computed by the code before Task 2; the test passes before and after it."""
    _two_signal_source(v, "shop-uat-adx")
    _two_signal_source(v, "shop-prod-adx")
    logs = [dict(LOG_ROW, service="core-worker", scope="Acme.Platform.Services.MailService", event_id="1800",
                 module_0="Acme.Core.Partitions.Orders.OrderPartition",
                 module_1="Acme.Core.Partitions.Orders.OrderEmailNotificationSlice"),
            dict(LOG_ROW, service="batch-worker", scope="Quartz.Impl.AdoJobStore.ClusterManager", event_id="",
                 module_0="", module_1="")]
    spans = [dict(SPAN_ROW, route="api/vendor/agent-credentials/order-credential-check")]
    monkeypatch.setattr(kusto, "query", _rows(logs, spans))
    assert telemetry_run.main([], v, NOW) == 0
    assert sorted(p.name for p in (v / "raw/telemetry").glob("*.md")) == [
        "shop-prod-adx-a-1ac755ccca34.md", "shop-prod-adx-a-2a9d42e61b13.md", "shop-prod-adx-a-8818b5096c41.md",
        "shop-uat-adx-a-0e5b4bafc506.md", "shop-uat-adx-a-30e079fb650d.md", "shop-uat-adx-a-f7890ec560a5.md"]


def test_marker_groups_split_into_real_routes_and_type_names(v, monkeypatch):
    """Before 2026-10-07 both routes hashed to a-8513424e6ee9 (route key "[REDACTED:high_entropy]") and the long scope
    to a-2f59495da85c; now each lands in its own group under its real shape."""
    _two_signal_source(v, "shop-uat-adx")
    _two_signal_source(v, "shop-prod-adx")
    spans = [dict(SPAN_ROW, route=f"api/orders/{GUID}/credential-check"),
             dict(SPAN_ROW, route=f"api/vendor/agent-credentials/{GUID}/order-credential-check")]
    log = dict(LOG_ROW, service="core-worker", scope="Acme.Core.Plugins.Vendor.VendorAccountSuitabilitySubmissionFetchXML",
               event_id="9908", module_0="", module_1="")
    monkeypatch.setattr(kusto, "query", _rows([log], spans))
    assert telemetry_run.main([], v, NOW) == 0
    tele = v / "raw/telemetry"
    assert not (tele / "shop-prod-adx-a-8513424e6ee9.md").exists()
    assert not (tele / "shop-uat-adx-a-2f59495da85c.md").exists()
    notes = [p.read_text() for p in tele.glob("shop-prod-adx-a-*.md")]
    assert sorted(l for n in notes for l in n.splitlines() if l.startswith("exception:")) == [
        'exception: "Acme.Core.Plugins.Vendor.VendorAccountSuitabilitySubmissionFetchXML#9908"',
        'exception: "api/orders/<guid>/credential-check 500"',
        'exception: "api/vendor/agent-credentials/<guid>/order-credential-check 500"']
    assert all("high_entropy" not in n and "message:" not in n for n in notes)


def test_an_adx_source_runs_one_query_per_signal_and_nothing_else(v, monkeypatch):
    """#171: dependency status is held (telemetry escalation spec §9), so a fetch sends only the logs and spans queries."""
    _two_signal_source(v, "shop-uat-adx")
    seen = []
    span = dict(SPAN_ROW, route="api/orders")
    monkeypatch.setattr(kusto, "query", lambda c, d, kql, n: seen.append(kql.split("\n")[0]) or (
        [span] if kql.startswith("Traces") else []))
    assert telemetry_run.main([], v, NOW) == 0
    assert seen == ["Logs", "Traces"]


SECRET_ROW = dict(LOG_ROW, message="login failed for svc password=hunter2xyz")


def _secret_alerts(v):
    path = v / f"system/logs/alerts_{DAY}.md"
    return [l.split(" ", 2)[2] for l in path.read_text().splitlines() if "credential shape" in l] if path.exists() else []


def test_secrets_scan_alerts_once_per_new_group_naming_group_and_shape_never_the_value(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='secrets_scan: "true"\n'))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [SECRET_ROW])
    assert telemetry_run.main(["--dry-run"], v, NOW) == 0
    assert _secret_alerts(v) == []
    assert telemetry_run.main([], v, NOW) == 0          # a first run alerts too: a backlog credential is still a leak
    note = next((v / "raw/telemetry").glob("prod-adx-a-*.md")).relative_to(v).as_posix()
    assert _secret_alerts(v) == [f"[telemetry] prod-adx: a log line in {note} holds a credential shape: assignment"]
    assert telemetry_run.main([], v, NOW + timedelta(days=1)) == 0
    files = [p for p in (v / "system/logs").glob("alerts_*.md")]
    assert sum("credential shape" in p.read_text() for p in files) == 1
    written = [p for p in v.rglob("*") if p.is_file() and p.suffix in (".md", ".json", ".jsonl")]
    assert any(p.suffix == ".jsonl" for p in written)
    assert all("hunter2xyz" not in p.read_text() for p in written)


def test_secrets_scan_alerts_at_most_three_groups_a_run_then_counts_the_rest(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='secrets_scan: "true"\n'))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [dict(SECRET_ROW, scope=f"S{i}") for i in range(5)])
    assert telemetry_run.main([], v, NOW) == 0
    got = _secret_alerts(v)
    assert len(got) == 4 and all(" a log line in raw/telemetry/prod-adx-a-" in l for l in got[:3])
    assert got[3] == "[telemetry] prod-adx: and 2 more new groups hold a credential shape (see raw/telemetry/)"
    from vaultlib.alerts import severity   # the owner's decision: these lines reach Slack now
    lines = (v / f"system/logs/alerts_{DAY}.md").read_text().splitlines()
    assert [severity(l) for l in lines if "credential shape" in l] == ["now"] * 4


def test_secrets_scan_is_off_by_default_and_ignores_a_line_redacted_upstream(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [SECRET_ROW])
    telemetry_run.main([], v, NOW)
    assert _secret_alerts(v) == []
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='secrets_scan: "true"\n'))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [dict(LOG_ROW, scope="Other", message="token [REDACTED:jwt]")])
    telemetry_run.main([], v, NOW + timedelta(hours=1))
    assert _secret_alerts(v) == []
