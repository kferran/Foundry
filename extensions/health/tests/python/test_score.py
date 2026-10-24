"""Scoring and history (health scorecard spec §3.1, §3.3, §3.4): one line per metric a day, the trend rule, and the
brief's lines (the whole scorecard on a Monday, only breaches on other days)."""
from datetime import date, timedelta

MONDAY = date(2026, 10, 26)


def logs(vault):
    return vault / "system" / "logs"


def cost_week(jsonl, vault, monday, usd):
    """A fetch log line costing `usd` inside the week scored on `monday`."""
    day = (monday - timedelta(days=3)).isoformat()
    jsonl(logs(vault) / f"triage_fetch-{day[:7]}.jsonl", {"time": f"{day}T08:00:00-06:00", "exit": 0, "cost_usd": usd})


def row(h, vault, day, metric):
    return next(r for r in h.records(h.history_path(vault, day)) if r.get("metric") == metric and r["date"] == day.isoformat())


def test_score_appends_one_line_per_metric_once_a_day(h, vault):
    h.score(vault, MONDAY, dry=False)
    first = h.history_path(vault, MONDAY).read_text()
    rows = [r for r in h.records(h.history_path(vault, MONDAY)) if r.get("metric")]
    assert {r["metric"] for r in rows} == set(list(h.LABELS)[:11])
    assert all(set(r) == {"date", "metric", "value", "text", "threshold", "state"} for r in rows)
    h.score(vault, MONDAY, dry=False)
    assert h.history_path(vault, MONDAY).read_text() == first


def test_dry_run_appends_nothing(h, vault):
    out = h.score(vault, MONDAY, dry=True)
    assert out and not h.history_path(vault, MONDAY).exists()


def test_a_missing_log_is_unavailable_never_ok(h, vault):
    lines = h.score(vault, MONDAY, dry=True)
    assert "- ❔ Headless runs published: unavailable (no run ledger for the window)" in lines
    assert not any(x.startswith("- ✅ Headless runs") for x in lines)


def test_a_trend_metric_shows_trend_until_four_weeks_then_breaks_at_one_and_a_half_times_the_median(h, vault, jsonl):
    weeks = [MONDAY - timedelta(weeks=k) for k in (4, 3, 2, 1)]
    for monday, usd in zip(weeks[:3], (0.7, 0.7, 1.4)):
        cost_week(jsonl, vault, monday, usd)
        h.score(vault, monday, dry=False)
    assert row(h, vault, weeks[2], "cost_per_day")["state"] == "trend"
    cost_week(jsonl, vault, weeks[3], 0.7)
    h.score(vault, weeks[3], dry=False)
    assert row(h, vault, weeks[3], "cost_per_day")["state"] == "trend"   # 3 weeks before it
    cost_week(jsonl, vault, MONDAY, 1.4)   # 0.2 a day against a median of 0.1
    h.score(vault, MONDAY, dry=False)
    r = row(h, vault, MONDAY, "cost_per_day")
    assert (r["value"], r["state"]) == (0.2, "breach")
    assert r["threshold"] == "≤ 1.5× the 4-week median"


def test_a_trend_metric_at_the_median_is_ok(h, vault, jsonl):
    for k in (4, 3, 2, 1, 0):
        monday = MONDAY - timedelta(weeks=k)
        cost_week(jsonl, vault, monday, 0.7)
        h.score(vault, monday, dry=False)
    assert row(h, vault, MONDAY, "cost_per_day")["state"] == "ok"


def test_monday_prints_the_whole_scorecard_with_last_week(h, vault, jsonl):
    cost_week(jsonl, vault, MONDAY - timedelta(weeks=1), 0.7)
    h.score(vault, MONDAY - timedelta(weeks=1), dry=False)
    lines = h.score(vault, MONDAY, dry=False)
    assert len(lines) == 11
    assert "- ✅ Sync blocked: 0 (healthy 0; last week 0)" in lines
    assert any(x.startswith("- ❔ Claude cost per day: unavailable") for x in lines)


def test_tuesday_prints_only_breaches_and_nothing_when_all_pass(h, vault):
    tuesday = MONDAY + timedelta(days=1)
    assert h.score(vault, tuesday, dry=True) == []
    (logs(vault) / "sync-blocked").write_text("reason: x\n")
    assert h.score(vault, tuesday, dry=False) == ["- ⚠️ health: Sync blocked 1 (blocked now) (healthy 0)"]


def test_thresholds_from_config_override_the_defaults(h, config, vault):
    config('health_thresholds: {now_open: "10", brief_by: "07:00"}')
    th = h.thresholds(h.config(vault))
    assert (th["now_open"], th["brief_by"], th["tick_success_pct"]) == (10, "07:00", 95)


def test_usage(h):
    assert h.main([]) == 2
    assert h.main(["score", "nope"]) == 2
    assert h.main(["score", "2026-10-26", "--other"]) == 2
