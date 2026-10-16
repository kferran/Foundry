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


def _demo(vault, listed=True):
    import shutil
    from helpers import REPO
    shutil.copytree(REPO / "system/tests/fixtures/extensions/demo", vault / "extensions/demo")
    write(vault, "system/config.md", f'---\ntype: config\nextensions: [{"demo" if listed else ""}]\n---\n')


def test_report_lists_enabled_extension_sources_and_off_when_not_listed(vault):
    _demo(vault)
    smoke(vault, ("2026-10-01", "demo", 0, ""))
    out = sources.report(vault, "2026-10-01", {})
    assert "- demo: ok" in out
    assert out.index("- demo: ok") < out.index("- dtcc: off")
    _demo_off = [ln for ln in sources.report(vault, "2026-10-01", {}) if ln.startswith("- demo")]
    assert _demo_off == ["- demo: ok"]


def test_report_without_the_listing_shows_no_extension_source(vault):
    _demo(vault, listed=False)
    assert not [ln for ln in sources.report(vault, "2026-10-01", {}) if "demo" in ln]


def test_a_listed_extension_with_no_folder_reads_failed(vault):
    write(vault, "system/config.md", '---\ntype: config\nextensions: ["gone"]\n---\n')
    out = sources.report(vault, "2026-10-01", {})
    assert any(ln.startswith("- gone: failed: other: extensions/gone/ is missing") for ln in out)


def test_credential_comes_from_the_manifest(vault):
    _demo(vault)
    assert sources.credential(vault, "demo", "auth: HTTP 401") == ("Demo connector", "reconnect it at example.invalid")
    report = sources.report(vault, "2026-10-01", {"demo": ("failed", "auth: HTTP 401")})
    assert any("demo: failed: auth: HTTP 401" in ln and "expired: Demo connector; renew: reconnect it at example.invalid"
               in ln for ln in report)
