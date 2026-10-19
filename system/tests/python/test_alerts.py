"""The alert tag registry (alert tags spec §2, §3.1)."""
import pytest

from vaultlib import alerts


@pytest.mark.parametrize("tag,want", [
    ("foreman", "now"), ("incident", "now"), ("orders", "now"), ("sync", "now"), ("update", "now"), ("rca", "now"), ("intake", "now"),
    ("commit_runs", "brief"), ("calendar", "brief"), ("meetings", "brief"),
    ("handoffs", "brief"), ("telemetry", "brief"), ("memory", "brief"), ("notify", "never"),
])
def test_each_tag_has_the_owners_severity(tag, want):
    assert alerts.severity(f"- 06:10:00 [{tag}] text") == want


@pytest.mark.parametrize("line,want", [
    ("- 06:10:00 [triage] 3 new: from a, b", "now"),
    ("- 06:10:00 [triage] Inbox triage failed (exit 6): x", "brief"),
    ("- 06:10:00 [smoke] foundry-brief.timer stale: no run since 2026-10-14 06:00", "now"),
    ("- 06:10:00 [smoke] calendar: failed: auth: expired", "brief"),
    ("- 06:10:00 [telemetry] prod-adx: a log line in raw/telemetry/prod-adx-a-0123456789ab.md holds a credential "
     "shape: assignment", "now"),
    ("- 06:10:00 [telemetry] prod-adx: and 2 more new groups hold a credential shape (see raw/telemetry/)", "now"),
    ("- 06:10:00 [telemetry] prod-adx: run az login", "brief"),
    ("- 06:10:00 [telemetry] prod-adx: 900 groups; only 500 kept", "brief"),
])
def test_triage_smoke_and_telemetry_decide_by_their_text(line, want):
    assert alerts.severity(line) == want


@pytest.mark.parametrize("line", ["- 06:10:00 no tag", "- 06:10:00 [nosuch] text", "- 06:10:00 [Sync] text",
                                  "[sync] text", "- 6:10:00 [sync] text", ""])
def test_an_untagged_or_unknown_line_waits_for_the_brief(line):
    assert alerts.severity(line) == "brief"


def test_an_extension_tag_takes_its_manifest_severity_and_core_tags_keep_theirs():
    ext = {"watch": "now"}
    assert alerts.severity("- 06:10:00 [watch] x", ext) == "now"
    assert alerts.severity("- 06:10:00 [watch] x") == "brief"
    assert alerts.severity("- 06:10:00 [sync] x", {"sync": "brief"}) == "now"
    assert alerts.severity("- 06:10:00 [other] x", ext) == "brief"


def test_extension_tags_reads_tag_entries_with_a_severity_from_enabled_manifests(vault):
    from helpers import write
    write(vault, "system/config.md", '---\ntype: config\nextensions: ["w"]\n---\n')
    write(vault, "extensions/w/extension.md", "---\nname: w\ncontract: 1\nalert_tags: [plain, {tag: watch, severity: now},"
          " {tag: odd, severity: loud}]\n---\nbody\n")
    assert alerts.extension_tags(vault) == {"watch": "now"}
    (vault / "extensions" / "w" / "extension.md").write_bytes(b"---\nname: w\xff\n---\n")
    assert alerts.extension_tags(vault) == {}   # an unreadable manifest stops no Slack notice
