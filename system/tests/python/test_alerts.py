"""The alert tag registry (alert tags spec §2, §3.1)."""
import pytest

from vaultlib import alerts


@pytest.mark.parametrize("tag,want", [
    ("foreman", "now"), ("orders", "now"), ("sync", "now"), ("update", "now"), ("rca", "now"), ("intake", "now"),
    ("triage", "now"), ("commit_runs", "brief"), ("smoke", "brief"), ("calendar", "brief"), ("meetings", "brief"),
    ("handoffs", "brief"), ("telemetry", "brief"), ("dtcc", "brief"), ("memory", "brief"), ("notify", "never"),
])
def test_each_tag_has_the_owners_severity(tag, want):
    assert alerts.severity(f"- 06:10:00 [{tag}] text") == want


@pytest.mark.parametrize("line", ["- 06:10:00 no tag", "- 06:10:00 [nosuch] text", "- 06:10:00 [Sync] text",
                                  "[sync] text", "- 6:10:00 [sync] text", ""])
def test_an_untagged_or_unknown_line_waits_for_the_brief(line):
    assert alerts.severity(line) == "brief"
