# system/tests/python/test_sources.py: source health for the smoke check and the brief (connector health spec §2).
import json

from helpers import write
from vaultlib import sources

CB = '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n'
ADX = ('---\ntype: telemetry_source\nname: "prod-adx"\ncodebase: "shop"\nenvironment: "prod"\nkind: "adx"\n'
       'adx_cluster: "https://example.kusto.windows.net"\nadx_database: "prod"\nadx_signals: ["logs"]\n---\n')
TRIAGE_ON = '---\ntype: config\ntriage_enabled: "true"\n---\n'


def smoke(v, *rows):
    """rows: (date, source, exit, reason), appended to that month's smoke log in order."""
    for day, source, code, reason in rows:
        p = v / f"system/logs/smoke-{day[:7]}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps({"time": f"{day}T05:45:00-06:00", "source": source, "exit": code, "reason": reason}) + "\n")


def test_classed_puts_other_in_front_of_a_reason_without_a_class():
    assert sources.classed("auth: run az login") == "auth: run az login"
    assert sources.classed("no Google Calendar connector") == "other: no Google Calendar connector"
    assert sources.classed("") == "other: no reason given"


def test_streak_counts_trailing_failures_across_months_and_skips_held(vault):
    smoke(vault, ("2026-09-29", "calendar", 0, ""), ("2026-09-30", "calendar", 6, "auth: HTTP 401"),
          ("2026-10-01", "calendar", 0, "held: usage"), ("2026-10-01", "handoffs", 6, "connector: x"),
          ("2026-10-02", "calendar", 6, "auth: HTTP 401"))
    assert sources.streak(vault, "calendar") == (2, "2026-09-30", "auth: HTTP 401")
    assert sources.streak(vault, "calendar", until="2026-09-29") == (0, "", "")


def test_streak_of_a_class_stops_at_another_class(vault):
    smoke(vault, ("2026-10-01", "telemetry/prod-adx", 1, "timeout: az timed out"),
          ("2026-10-02", "telemetry/prod-adx", 1, "network: example.kusto.windows.net (URLError)"),
          ("2026-10-03", "telemetry/prod-adx", 1, "network: example.kusto.windows.net (URLError)"))
    assert sources.streak(vault, "telemetry/prod-adx", "network")[:2] == (2, "2026-10-02")
    assert sources.streak(vault, "telemetry/prod-adx")[:2] == (3, "2026-10-01")


def test_credential_by_source_and_by_telemetry_kind(vault):
    write(vault, "system/codebases/shop.md", CB)
    write(vault, "system/telemetry/prod-adx.md", ADX)
    assert sources.credential(vault, "calendar", "auth: no connector")[0] == "Google connector"
    assert sources.credential(vault, "handoffs", "auth: HTTP 401")[0] == "Atlassian connector"
    assert sources.credential(vault, "telemetry/prod-adx", "auth: run az login") == ("Azure CLI", "az login on the server")
    assert sources.credential(vault, "calendar", "claude: not logged in")[0] == "claude login"
    assert sources.credential(vault, "calendar", "claude: claude not found (claude)") is None
    assert sources.credential(vault, "calendar", "connector: HTTP 500") is None


def test_report_lists_every_source_with_its_state_since_date_and_renewal(vault):
    write(vault, "system/codebases/shop.md", CB)
    write(vault, "system/telemetry/prod-adx.md", ADX)
    write(vault, "system/config.md", TRIAGE_ON)
    smoke(vault, ("2026-10-12", "telemetry/prod-adx", 1, "network: example.kusto.windows.net (URLError)"),
          ("2026-10-13", "telemetry/prod-adx", 1, "network: example.kusto.windows.net (URLError)"),
          ("2026-10-13", "calendar", 6, "auth: HTTP 401"), ("2026-10-13", "triage", 0, "1 threads"))
    lines = sources.report(vault, "2026-10-13", {"calendar": ("failed", "auth: HTTP 401")})
    assert lines == [
        "- calendar: failed: auth: HTTP 401 (since 2026-10-13); expired: Google connector; "
        "renew: reconnect it at claude.ai, Settings, Connectors",
        "- meetings: off",
        "- handoffs: off",
        "- triage: ok",
        "- telemetry/prod-adx: failed: network: example.kusto.windows.net (URLError) (since 2026-10-12)",
        "- dtcc: off",
        "- notify: off",
    ]


def test_report_without_a_smoke_reading_says_unknown(vault):
    write(vault, "system/config.md", TRIAGE_ON)
    lines = sources.report(vault, "2026-10-13", {"calendar": ("ok", "")})
    assert "- triage: unknown (no smoke check reading today)" in lines
    assert "- telemetry: off" in lines
