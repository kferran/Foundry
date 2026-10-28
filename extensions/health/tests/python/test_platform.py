"""The platform metrics (health scorecard spec §3.2): a passing week, a breaching week, and missing files as
unavailable, never zero or ok. The window for 2026-10-26 (a Monday) is 2026-10-19 to 2026-10-25."""
from datetime import date

import pytest

DAY = date(2026, 10, 26)


@pytest.fixture
def run(h, vault):
    """run(name): the metric's (value, text, threshold, state) over the fixture vault's week."""
    def one(name, **kw):
        th = h.thresholds(h.config(vault))
        args = (vault, h.Window(DAY), th)
        if name == "brief_on_time":
            from zoneinfo import ZoneInfo
            return h.brief_on_time(*args, ZoneInfo("America/Denver"))
        return getattr(h, name)(*args)
    return one


def logs(vault):
    return vault / "system" / "logs"


def test_tick_success_per_source_counts_only_the_window(run, vault, jsonl):
    jsonl(logs(vault) / "triage_fetch-2026-10.jsonl",
          *[{"time": f"2026-10-2{i}T08:00:00-06:00", "exit": 0, "reason": ""} for i in range(5)],
          {"time": "2026-10-12T08:00:00-06:00", "exit": 4, "reason": "old"})
    jsonl(logs(vault) / "calendar_fetch-2026-10.jsonl", {"date": "2026-10-20", "time": "2026-10-20T05:50:00-06:00", "exit": 0})
    value, text, _, state = run("tick_success")
    assert value == {"calendar_fetch": 100, "triage_fetch": 100}
    assert state == "ok" and "triage_fetch 100%" in text


def test_tick_success_breaks_under_95_and_skips_the_ledger_and_smoke(run, vault, jsonl):
    rows = [{"time": "2026-10-20T08:00:00-06:00", "exit": 0}] * 18 + [{"time": "2026-10-21T08:00:00-06:00", "exit": 6}] * 2
    jsonl(logs(vault) / "watch_fetch-2026-10.jsonl", *rows)
    jsonl(logs(vault) / "runs-2026-10.jsonl", {"started_at": "2026-10-20T05:00:00-06:00", "exit": 1})
    jsonl(logs(vault) / "smoke-2026-10.jsonl", {"time": "2026-10-20T05:00:00-06:00", "exit": 1})
    value, _, _, state = run("tick_success")
    assert value == {"watch_fetch": 90}
    assert state == "breach"


def test_no_fetch_log_is_unavailable(run, h):
    with pytest.raises(h.Unavailable):
        run("tick_success")


def ledger(vault, jsonl, *rows):
    jsonl(logs(vault) / "runs-2026-10.jsonl", *rows)


def brief(day, finished, status="published"):
    return {"command": "brief", "started_at": f"{day}T05:55:00-06:00", "finished_at": f"{day}T{finished}:00-06:00",
            "exit": 0, "publish": {"status": status}}


def test_runs_published_counts_published_and_noop_against_the_rest(run, vault, jsonl):
    ledger(vault, jsonl, *[brief(f"2026-10-{d}", "06:05") for d in range(19, 24)],
           {"command": "ingest", "started_at": "2026-10-20T10:00:00-06:00", "publish": {"status": "noop"}},
           {"command": "ingest", "started_at": "2026-10-21T10:00:00-06:00", "exit": 4, "publish": {}})
    value, text, _, state = run("runs_published")
    assert (value, state) == (100, "ok")
    assert text == "100% (6 of 6)"
    ledger(vault, jsonl, {"command": "ingest", "started_at": "2026-10-22T10:00:00-06:00", "publish": {"status": "rejected"}})
    value, text, _, state = run("runs_published")
    assert (value, state, text) == (86, "breach", "86% (6 of 7)")


def test_no_ledger_is_unavailable(run, h):
    for name in ("runs_published", "brief_on_time"):
        with pytest.raises(h.Unavailable):
            run(name)


def test_brief_on_time_every_workday_in_the_vault_timezone(run, vault, jsonl):
    ledger(vault, jsonl, *[brief(f"2026-10-{d}", "06:20") for d in range(19, 24)])
    value, text, threshold, state = run("brief_on_time")
    assert (value, state, text, threshold) == (5, "ok", "5 of 5 workdays", "every workday by 06:30")


def test_a_late_or_rejected_brief_breaks_it(run, vault, jsonl):
    ledger(vault, jsonl, brief("2026-10-19", "06:20"), brief("2026-10-20", "06:41"), brief("2026-10-21", "06:00", "rejected"),
           brief("2026-10-22", "06:10"), brief("2026-10-23", "06:10"))
    value, text, _, state = run("brief_on_time")
    assert (value, state) == (3, "breach")
    assert text == "3 of 5 workdays (late or missing: Tue, Wed)"


def test_brief_size_reads_the_newest_briefing_before_today(run, vault, h):
    (vault / "briefings").mkdir()
    (vault / "briefings" / "2026-10-23.md").write_text("x" * 4096)
    (vault / "briefings" / "2026-10-26.md").write_text("x" * 20000)
    (vault / "briefings" / "2026-10-23.debrief.md").write_text("x" * 20000)
    assert run("brief_size")[::3] == (4.0, "ok")
    (vault / "briefings" / "2026-10-25.md").write_text("x" * 9000)
    assert run("brief_size")[::3] == (8.8, "breach")


def page(vault, partition, *lines):
    path = vault / "wiki" / partition / "Now.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\ntype: now\n---\n## Needs you\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def archive(vault, partition, *lines):
    path = vault / "wiki" / partition / "now-archive" / "2026-10.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\ntype: now_archive\n---\n" + "\n".join(lines) + "\n", encoding="utf-8")


def test_now_metrics_without_a_page_are_unavailable(run, h):
    for name in ("now_size", "now_open", "now_flow", "dismissed"):
        with pytest.raises(h.Unavailable):
            run(name)


def test_now_size_and_open_lines(run, vault):
    page(vault, "work", *[f"- [ ] owed: Task {i} (since 2026-10-01)" for i in range(3)])
    assert run("now_open")[::3] == (3, "ok")
    assert run("now_size")[3] == "ok"
    page(vault, "personal", *[f"- [ ] owed: Item {i} with a long statement {'x' * 400} (since 2026-10-01)" for i in range(61)])
    value, _, _, state = run("now_size")
    assert state == "breach" and value["personal"] > 25
    assert run("now_open")[::3] == (64, "breach")


def test_now_flow_counts_inflow_against_closures_and_evidence(run, vault):
    page(vault, "work", "- [ ] owed: New A (since 2026-10-20)", "- [ ] owed: New B (since 2026-10-21)",
         "- [ ] owed: Old (since 2026-09-01)")
    archive(vault, "work",
            "- [x] owed: Done (since 2026-10-02, https://github.com/o/r/pull/1) _(closed: merged 2026-10-20)_",
            "- [x] owed: Ticked (since 2026-10-22) _(closed: ticked 2026-10-23)_",
            "- [x] owed: Earlier (since 2026-09-02) _(closed: ticked 2026-10-02)_")
    value, text, _, state = run("now_flow")
    assert value == {"inflow": 3, "closures": 2, "evidence": 1}
    assert state == "breach"
    assert text == "2 closed against 3 added (1 on evidence)"


def test_dismissed_share_per_evidence_host_with_five_closed(run, vault):
    mail = "https://mail.google.com/mail/u/0/#all/abc"
    lines = [f"- [-] owed: Mail {i} (since 2026-10-19, {mail}{i}) _(closed: ticked 2026-10-2{i})_" for i in range(3)]
    lines += [f"- [x] owed: Mail done {i} (since 2026-10-19, {mail}x{i}) _(closed: ticked 2026-10-2{i})_" for i in range(2)]
    lines += ["- [-] owed: Slack (since 2026-10-19, https://x.slack.com/archives/C1/p1) _(closed: ticked 2026-10-20)_"]
    archive(vault, "work", *lines)
    value, text, _, state = run("dismissed")
    assert value == {"guess:mail": 60}   # slack has 1 closed: below the 5 a host needs
    assert state == "breach" and text == "guess:mail 60%"


def test_dismissed_share_is_keyed_by_writer(run, vault):
    lines = [f"- [-] owed: Watch {i} [via:: watch] (since 2026-10-19) _(closed: expired 2026-10-2{i})_" for i in range(3)]
    lines += [f"- [x] owed: Watch done {i} [via:: watch] (since 2026-10-19) _(closed: ticked 2026-10-2{i})_" for i in range(2)]
    archive(vault, "work", *lines)
    value, text, _, _ = run("dismissed")
    assert value == {"watch": 60}
    assert text == "watch 60%"


def test_cost_sums_headless_runs_and_fetch_log_costs(run, vault, jsonl):
    ledger(vault, jsonl, {"run_id": "r1", "command": "brief", "started_at": "2026-10-20T05:55:00-06:00"})
    (logs(vault) / "runs" / "r1").mkdir(parents=True)
    (logs(vault) / "runs" / "r1" / "claude.json").write_text('{"total_cost_usd": 0.7}')
    jsonl(logs(vault) / "calendar_fetch-2026-10.jsonl", {"time": "2026-10-21T05:50:00-06:00", "exit": 0, "cost_usd": 0.0}
          , {"time": "2026-10-22T05:50:00-06:00", "exit": 0, "cost_usd": 0.7})
    value, text, threshold, state = run("cost_per_day")
    assert (value, state, threshold) == (0.2, "trend", "trend")
    assert text == "$0.20 (calendar_fetch, headless runs)"


def test_cost_with_nothing_logged_is_unavailable(run, h):
    with pytest.raises(h.Unavailable):
        run("cost_per_day")


def test_cost_cap_from_config_breaks(run, vault, jsonl, config):
    config('health_thresholds: {cost_cap_usd: "0"}')
    jsonl(logs(vault) / "triage_fetch-2026-10.jsonl", {"time": "2026-10-21T08:00:00-06:00", "exit": 0, "cost_usd": 1.4})
    assert run("cost_per_day")[::3] == (0.2, "breach")


def test_sync_blocked_counts_alerts_and_the_marker(run, vault):
    assert run("sync_blocked")[::3] == (0, "ok")
    (logs(vault) / "alerts_2026-10-21.md").write_text("- 09:00:00 [sync] sync blocked: diverged; intake skipped\n")
    (logs(vault) / "alerts_2026-10-27.md").write_text("- 09:00:00 [sync] sync blocked: later\n")
    assert run("sync_blocked")[::3] == (1, "breach")
    (logs(vault) / "sync-blocked").write_text("reason: x\n")
    assert run("sync_blocked")[1] == "2 (blocked now)"


def test_headroom_reads_the_caps_from_the_tests(run, vault, h):
    import subprocess
    t = vault / "system" / "tests"
    t.mkdir(parents=True)
    (t / "vault_integrity.bats").write_text('CORE_CAP=100\n  [ "$(git ls-files system/schemas | wc -l)" -le 2 ]\n')
    (t / "commands.bats").write_text('  [ "$(wc -l < "$f")" -le 50 ]\n')
    (t / "prep.bats").write_text('  [ "$words" -le 2500 ]\n')
    (vault / "system" / "scripts").mkdir()
    (vault / "system" / "scripts" / "a.sh").write_text("x\n" * 90)
    (vault / "system" / "schemas").mkdir()
    (vault / "system" / "schemas" / "a.md").write_text("x\n")
    (vault / "system" / "schemas" / "b.md").write_text("x\n")
    (vault / "CLAUDE.md").write_text("x\n" * 50)
    (vault / ".claude" / "commands").mkdir(parents=True)
    (vault / ".claude" / "commands" / "brief.md").write_text("word " * 1000)
    subprocess.run(["git", "-C", str(vault), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(vault), "add", "-A"], check=True)
    value, text, _, state = run("headroom")
    # Core lines: 90 script lines, and the command has no newline; full ratchets do not break it.
    assert value == {"core lines": 10, "schemas": 0, "CLAUDE.md lines": 0, "brief words": 60}
    assert state == "ok"
    assert text == "core lines 90 of 100, schemas 2 of 2, CLAUDE.md lines 50 of 50, brief words 1000 of 2500"
    (vault / "system" / "scripts" / "a.sh").write_text("x\n" * 99)
    assert run("headroom")[3] == "breach"


def test_headroom_without_its_tests_is_unavailable(run, h):
    with pytest.raises(h.Unavailable):
        run("headroom")
