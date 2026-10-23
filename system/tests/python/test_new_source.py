"""The new-source scaffold (factory F4 §3.2, §5): one command writes an extension Source that passes the line, the
Source rule, the part homes, the timing rule, the loader and its own suite, with no other file edited."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
from datetime import date

import pytest

from helpers import REPO, call, stream
from test_source_rule import session_problems, smoke_name_problems, source_problems, tree
from vaultlib import extensions

# tree() copies the whole checkout, and conformance.bats skips in a vault.
pytestmark = pytest.mark.skipif(
    (REPO / "system/config.md").exists(),
    reason="this checkout is a vault (system/config.md exists); the scaffold test guards the template")

SCRIPT = ".claude/skills/new-source/new_source.py"
TABLE = ["--tool", "mcp__claude_ai_Gmail__get_thread", "--server", "claude.ai Gmail", "--tools", "GMAIL_TOOLS"]
OWN = ["--tool", "mcp__claude_ai_Example__read_item", "--server", "claude.ai Example",
       "--server-tool", "read_item", "list_items", "delete_item"]
TEXT = ["--description", "Demo items in the morning brief", "--credential", "Demo connector",
        "--renew", "reconnect it at claude.ai, Settings, Connectors"]
GOOD = TABLE + TEXT + ["--issue", "1"]
OWN_GOOD = OWN + TEXT + ["--issue", "1"]
LINE = "- Added: Demo items in the morning brief. (#1)"


def run(root, *args, env=None):
    return subprocess.run(list(args), cwd=root, capture_output=True, text=True, env={**os.environ, **(env or {})})


def git(root, *args):
    return run(root, "git", *args)


def repo(tmp_path):
    """tree() with its files committed, so git status names only what the scaffold writes."""
    root = tree(tmp_path / "repo")
    git(root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "-qm", "base")
    return root


def scaffold(root, *args, name="demo_src"):
    return run(root, "python3", SCRIPT, name, *args)


def bats(root, *args):
    tmp = root.parent / "tmp"
    tmp.mkdir(exist_ok=True)
    return run(root, "bats", *args, env={"TMPDIR": str(tmp)})


def changed(root):
    """The paths git status names, each cut to extensions/<name> under extensions/."""
    out = git(root, "status", "--porcelain", "--untracked-files=all").stdout
    return {re.sub(r"^(extensions/[^/]+)/.*", r"\1", line[3:]) for line in out.splitlines()}


def timing(root):
    """conformance.bats' timing rule on root: its problem lines, without the per-unit sums."""
    r = run(root, "bash", "-c", r'''eval "$(sed -n "/^TIMING_VALUES='/,/^)$/p" system/tests/conformance.bats)"; '''
            r'''timing_problems "$VAULT_ROOT"''', env={"VAULT_ROOT": str(root)})
    assert r.returncode == 0, r.stderr
    assert any(line.startswith("# brief: ") for line in r.stdout.splitlines()), r.stdout   # the rule ran
    return [line for line in r.stdout.splitlines() if not line.startswith("# ")]


def enable(root, name):
    shutil.copyfile(root / "system/config.example.md", root / "system/config.md")
    assert extensions.enable(root, name)


@pytest.mark.parametrize("case,name", [(TABLE, "demo_src"), (OWN, "demo_own")], ids=["table", "own table"])
def test_a_scaffold_passes_the_line(tmp_path, case, name):
    root = repo(tmp_path)
    before = timing(root)
    r = scaffold(root, *case, *TEXT, "--issue", "1", name=name)
    assert r.returncode == 0, r.stderr
    assert changed(root) == {f"extensions/{name}", "CHANGELOG.md"}   # no hand wiring
    assert LINE in (root / "CHANGELOG.md").read_text()
    git(root, "add", "-A")
    assert source_problems(root) == []
    assert session_problems(root) == []
    assert smoke_name_problems(root) == []
    after = timing(root)
    overrun = [line for line in after if re.match(r"brief: \d+ s of waits against", line) and line not in before]
    print("brief overrun tolerated:", overrun)   # §5 item 3: left to the next feature's own CI run
    assert [line for line in after if line not in overrun] == before
    r = bats(root, "--filter", "shared part|pipeline", "system/tests/conformance.bats")
    assert r.returncode == 0, r.stdout
    r = bats(root, "--filter", "brief prompt is at most", "system/tests/prep.bats")   # the brief's word cap
    assert r.returncode == 0, r.stdout
    enable(root, name)
    r = run(root, "system/scripts/extensions.py", "check")
    assert (r.returncode, r.stdout) == (0, "")
    r = bats(root, f"extensions/{name}/tests/{name}.bats")
    assert r.returncode == 0, r.stdout


def swap(args, old, new):
    return [new if a == old else a for a in args]


@pytest.mark.parametrize("name,args,reason", [
    ("handoffs", GOOD, "extensions/handoffs exists"),
    ("calendar", GOOD, "is a core alert tag"),
    ("Demo-1", GOOD, "[a-z][a-z_]*"),
    ("demo_src2", GOOD, "demo_src2: a Source name is [a-z][a-z_]*"),
    ("demo_src", GOOD[:-2], "--issue"),
    ("demo_src", swap(GOOD, "GMAIL_TOOLS", "SLACK_TOOLS"), "get_thread is not in SLACK_TOOLS"),
    ("demo_src", swap(GOOD, "GMAIL_TOOLS", "OTHER_TOOLS"), "GMAIL_TOOLS"),
    ("demo_src", swap(GOOD, "Demo items in the morning brief", 'say "hi"'), "--description"),
    ("demo_src", swap(GOOD, "mcp__claude_ai_Gmail__get_thread", "not_a_tool"), "mcp__<server>__<tool>"),
    ("demo_src", swap(GOOD, "claude.ai Gmail", "a'b"), "--server"),
    ("demo_src", swap(GOOD, "Demo connector", "a\\b"), "--credential"),
    ("demo_src", swap(GOOD, "reconnect it at claude.ai, Settings, Connectors", "run $x"), "--renew"),
    ("demo_src", swap(GOOD, "Demo items in the morning brief", ""), "--description is empty"),
    ("demo_src", swap(GOOD, "claude.ai Gmail", " "), "--server is empty"),
    ("demo_src", swap(OWN_GOOD, "read_item", "get_item"), "read_item is not in --server-tool"),
    ("demo_src", swap(OWN_GOOD, "list_items", "list/items"), "--server-tool list/items is not a tool name"),
    ("jira", GOOD, "extensions/handoffs/scripts/jira_fetch.sh exists"),
    ("triage_chat", GOOD, "triage_chat is a core smoke row"),
], ids=["exists", "core tag", "bad name", "digit", "no issue", "not in table", "unknown table", "quote", "bad tool",
        "apostrophe", "backslash", "dollar", "empty description", "blank server", "tool not in own table",
        "bad own tool", "fetch name taken", "core smoke row"])
def test_a_usage_error_writes_nothing(tmp_path, name, args, reason):
    root = repo(tmp_path)
    r = scaffold(root, *args, name=name)
    assert r.returncode == 2
    assert reason in r.stderr
    assert git(root, "status", "--porcelain").stdout == ""


def test_another_extensions_tag_is_refused(tmp_path):
    root = repo(tmp_path)
    text = (root / "extensions/handoffs/extension.md").read_text()
    (root / "extensions/x").mkdir()
    (root / "extensions/x/extension.md").write_text(
        text.replace("name: handoffs", "name: x").replace("alert_tags: [handoffs]", "alert_tags: [demo_src]"))
    r = scaffold(root, *GOOD)
    assert r.returncode == 2
    assert "is the x extension's alert tag" in r.stderr
    assert not (root / "extensions/demo_src").exists()


def test_a_vault_scaffold_adds_no_changelog_line(tmp_path):
    root = repo(tmp_path)
    shutil.copyfile(root / "system/config.example.md", root / "system/config.md")
    before = (root / "CHANGELOG.md").read_text()
    r = scaffold(root, *GOOD[:-2])
    assert r.returncode == 0, r.stderr
    assert (root / "CHANGELOG.md").read_text() == before


def test_the_changelog_line_lands_under_today(tmp_path):
    root = repo(tmp_path)
    assert scaffold(root, *GOOD, name="demo_a").returncode == 0
    assert scaffold(root, *swap(GOOD, "1", "2"), name="demo_b").returncode == 0
    text = (root / "CHANGELOG.md").read_text()
    today = date.today().isoformat()
    assert text.count(f"\n## {today}\n") == 1
    assert f"\n## Changes\n\n## {today}\n" in text
    block = text.split(f"\n## {today}\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert LINE in block
    assert "- Added: Demo items in the morning brief. (#2)" in block


def writer():
    spec = importlib.util.spec_from_file_location("new_source", REPO / SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_changelog_writer_adds_or_reuses_todays_heading():
    ns, today = writer(), date.today().isoformat()
    text = "# Changelog\n\n## Changes\n\n## 2000-01-01\n- Fixed: old. (#9)\n"
    assert ns.changelog(text, "- Added: a. (#1)") == (
        f"# Changelog\n\n## Changes\n\n## {today}\n- Added: a. (#1)\n\n## 2000-01-01\n- Fixed: old. (#9)\n")
    text = f"# Changelog\n\n## Changes\n\n## {today}\n- Added: a. (#1)\n\n## 2000-01-01\n"
    assert ns.changelog(text, "- Added: b. (#2)") == (
        f"# Changelog\n\n## Changes\n\n## {today}\n- Added: b. (#2)\n- Added: a. (#1)\n\n## 2000-01-01\n")
    text = "# Changelog\n\n## Changes\n## 2000-01-01\n"   # no blank line after the heading
    assert ns.changelog(text, "- Added: c. (#3)") == (
        f"# Changelog\n\n## Changes\n## {today}\n- Added: c. (#3)\n\n## 2000-01-01\n")


def test_a_second_call_is_named_by_its_tool(tmp_path):
    root = repo(tmp_path)
    assert scaffold(root, *GOOD).returncode == 0
    s = "\n".join(json.dumps(m) for m in stream(TABLE[1], [call(sc={}), call(sc={})]))
    r = subprocess.run(["extensions/demo_src/scripts/demo_src_check.py", "extract"], cwd=root, input=s,
                       capture_output=True, text=True)
    assert (r.returncode, r.stderr) == (7, "demo_src_check: the session made 2 get_thread calls; the limit is 1\n")


def test_a_changelog_with_no_changes_heading_writes_nothing(tmp_path):
    root = repo(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n")
    git(root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "-qam", "no heading")
    r = scaffold(root, *GOOD)
    assert r.returncode == 2
    assert "new_source: CHANGELOG.md has no ## Changes heading" in r.stderr
    assert git(root, "status", "--porcelain").stdout == ""


def test_a_closing_period_is_not_doubled(tmp_path):
    root = repo(tmp_path)
    assert scaffold(root, *swap(GOOD, "Demo items in the morning brief", "Demo items.")).returncode == 0
    assert "- Added: Demo items. (#1)" in (root / "CHANGELOG.md").read_text()
    assert "**Demo items.**" in (root / "extensions/demo_src/extension.md").read_text()
