"""The alert tag registry (alert tags spec §2, §3.1)."""
import pytest

from vaultlib import alerts


@pytest.mark.parametrize("tag,want", [
    ("foreman", "now"), ("orders", "now"), ("sync", "now"), ("update", "now"), ("intake", "now"),
    ("commit_runs", "brief"), ("calendar", "brief"), ("meetings", "brief"), ("memory", "brief"), ("notify", "never"),
])
def test_each_tag_has_the_owners_severity(tag, want):
    assert alerts.severity(f"- 06:10:00 [{tag}] text") == want


@pytest.mark.parametrize("line,want", [
    ("- 06:10:00 [triage] 3 new: from a, b", "now"),
    ("- 06:10:00 [triage] Inbox triage failed (exit 6): x", "brief"),
    ("- 06:10:00 [smoke] foundry-brief.timer stale: no run since 2026-10-14 06:00", "now"),
    ("- 06:10:00 [smoke] calendar: failed: auth: expired", "brief"),
])
def test_triage_and_smoke_decide_by_their_text(line, want):
    assert alerts.severity(line) == want


def test_core_names_no_extension_tag():
    """Factory F2 §3.1: an extension's tags and text rules live in its manifest."""
    assert not {"incident", "rca", "handoffs", "telemetry"} & (set(alerts.TAGS) | set(alerts.NOW_WHEN))
    assert alerts.severity("- 06:10:00 [incident] x") == "brief"   # no manifest says otherwise


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


def test_a_now_when_tag_is_now_when_its_pattern_matches_the_text_after_the_tag_else_its_severity():
    import re
    ext = {"w": ("brief", re.compile(r"\S+: urgent")), "n": ("never", re.compile("x"))}
    assert alerts.severity("- 06:10:00 [w] api: urgent now", ext) == "now"
    assert alerts.severity("- 06:10:00 [w] says api: urgent", ext) == "brief"   # matched from the start of the text
    assert alerts.severity("- 06:10:00 [n] y", ext) == "never"


def test_extension_tags_reads_every_tag_of_enabled_manifests(vault):
    from helpers import write
    write(vault, "system/config.md", '---\ntype: config\nextensions: ["w"]\n---\n')
    write(vault, "extensions/w/extension.md", "---\nname: w\ncontract: 1\nalert_tags: [plain, {tag: watch, severity: now},"
          " {tag: odd, severity: loud}]\n---\nbody\n")
    assert alerts.extension_tags(vault) == {"plain": "brief", "watch": "now", "odd": "brief"}
    write(vault, "extensions/w/extension.md", "---\nname: w\ncontract: 1\nalert_tags:\n"
          "  - {tag: t, severity: brief, now_when: '\\S+ holds a key'}\n  - {tag: bad, severity: now, now_when: '('}\n---\n")
    ext = alerts.extension_tags(vault)
    assert ext["bad"] == "now"   # a pattern that does not compile falls back to the tag's severity
    assert alerts.severity("- 06:10:00 [t] api holds a key", ext) == "now"
    assert alerts.severity("- 06:10:00 [t] api is fine", ext) == "brief"
    (vault / "extensions" / "w" / "extension.md").write_bytes(b"---\nname: w\xff\n---\n")
    assert alerts.extension_tags(vault) == {}   # an unreadable manifest stops no Slack notice


def test_alert_writes_once_a_day_per_key(vault):
    assert alerts.alert(vault, "2026-10-23", "09:00:00", "triage", "k1 first", key="k1")
    assert not alerts.alert(vault, "2026-10-23", "09:05:00", "triage", "k1 again", key="k1")
    assert alerts.alert(vault, "2026-10-23", "09:06:00", "triage", "no key")
    text = (vault / "system/logs/alerts_2026-10-23.md").read_text(encoding="utf-8")
    assert text == "- 09:00:00 [triage] k1 first\n- 09:06:00 [triage] no key\n"
