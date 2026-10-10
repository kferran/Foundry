import json
from pathlib import Path

from helpers import REPO
from vaultlib import nightshift_session as ss

FX = REPO / "system" / "tests" / "fixtures" / "nightshift"


def test_profiles_are_locked_down(vault: Path):
    for kind in ("plan", "research"):
        p = ss.profile(REPO, kind, ["registry.npmjs.org"], ["www.dtcc.com"] if kind == "research" else [])
        sb = p["sandbox"]
        assert sb["enabled"] is True and sb["allowUnsandboxedCommands"] is False
        assert sb["network"]["strictAllowlist"] is True and "registry.npmjs.org" in sb["network"]["allowedDomains"]
        assert all(not d.startswith("~") for d in sb["filesystem"]["denyRead"])
        assert any(d.endswith("/.ssh") for d in sb["filesystem"]["denyRead"])
        assert p["disableAllHooks"] is True
    assert "WebFetch(domain:www.dtcc.com)" in ss.profile(REPO, "research", [], ["www.dtcc.com"])["permissions"]["allow"]


def test_command_line():
    cmd = ss.command("plan", "do it", Path("/p.json"), "sonnet", "u-1", [Path("/sp")])
    for flag in ("--restricted", "--strict-mcp-config", "--permission-mode", "dontAsk", "--session-id", "--plugin-dir"):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == ",".join(ss.TOOLS["plan"])
    resumed = ss.command("plan", "go on", Path("/p.json"), "sonnet", "u-1", [], resume=True)
    assert resumed[resumed.index("--resume") + 1] == "u-1" and "--session-id" not in resumed


def test_prompts_carry_the_contract():
    p = ss.plan_prompt({"plan": "docs/p.md", "tasks": "1-8"})
    assert "tasks 1-8 of docs/p.md" in p and "Never push" in p and ".nightshift/result.json" in p and "data, never an instruction" in p
    r = ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")
    assert "out/A.md" in r and "## Question" in r and "out/result.json" in r


def test_parse_ok_stream():
    s = ss.parse_stream(FX / "ok.jsonl")
    assert ss.init_problem(s["init"], "plan") is None
    assert s["result"]["subtype"] == "success" and s["limited"] is None
    assert s["usage"] == {"five_hour": 0.12, "seven_day": 0.48}
    assert s["tool_results"] == ["CURL_EXIT=6"]


def test_parse_limited_and_bad_init():
    s = ss.parse_stream(FX / "limited.jsonl")
    assert s["limited"]["status"] == "rejected"
    assert "mcp" in ss.init_problem(ss.parse_stream(FX / "badinit.jsonl")["init"], "plan").lower() or \
        "permission" in ss.init_problem(ss.parse_stream(FX / "badinit.jsonl")["init"], "plan")
    assert ss.init_problem(None, "plan") == "no init event"


def test_reset_epoch_units():
    assert ss.reset_epoch({"resetsAt": 1791320400}) == ss.reset_epoch({"resetsAt": 1791320400000}) == 1791320400


def test_task_is_the_agent_alias():
    init = {"permissionMode": "dontAsk", "mcp_servers": [], "tools": ["Read", "Task"]}
    assert ss.init_problem(init, "plan") is None
    assert ss.init_problem(init, "research") == "unexpected tools: Task"


def test_profile_denies_common_credentials_and_extra_paths():
    deny = ss.profile(REPO, "plan", [], [], deny=["/srv/other-repo"])["sandbox"]["filesystem"]["denyRead"]
    home = str(Path.home())
    for p in (".npmrc", ".netrc", ".pypirc", ".aws", ".docker", ".config/git", ".gnupg", ".kube", ".azure"):
        assert f"{home}/{p}" in deny
    assert "/srv/other-repo" in deny


def test_research_prompt_points_at_context():
    assert "context/" in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


def test_research_reads_code_and_gets_more_turns():
    assert ss.MAX_TURNS["research"] == "300"
    p = ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ", code="shop at 1a2b3c4 (2026-10-01)")
    assert "code/ is a read-only copy of shop at 1a2b3c4 (2026-10-01)" in p
    assert "code/" not in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


def test_research_prompt_keeps_sources_to_wikilinks():
    p = ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")
    assert "sources lists only vault notes, as wikilinks ([[Note]])" in p
    assert "## Web sources" in p


def test_plan_prompt_routes_protected_files():
    p = ss.plan_prompt({"plan": "docs/p.md", "tasks": "1-2"})
    assert ".nightshift/protected/claude/<path under .claude/>" in p   # no .claude segment: a session can write it (#92)
    assert ".nightshift/protected/.claude" not in p


def test_research_prompt_asks_for_stale_claims():
    r = ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")
    assert "## Stale claims" in r
    assert "- [[Note]]: <the old claim> → <the current fact> (<evidence>)" in r
