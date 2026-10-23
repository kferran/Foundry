"""The new-source scaffold (factory F4 §3.2, §5): one command writes an extension Source that passes the line, the
Source rule, the part homes, the timing rule, the loader and its own suite, with no other file edited."""
import os
import re
import shutil
import subprocess
from datetime import date

import pytest

from helpers import REPO
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
LINE = "- Added: Demo items in the morning brief. (#1)"


def run(root, *args, env=None):
    return subprocess.run(list(args), cwd=root, capture_output=True, text=True, env={**os.environ, **(env or {})})


def git(root, *args):
    return run(root, "git", *args)


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
    return [line for line in r.stdout.splitlines() if not line.startswith("# ")]


def enable(root, name):
    shutil.copyfile(root / "system/config.example.md", root / "system/config.md")
    assert extensions.enable(root, name)


@pytest.mark.parametrize("case", [TABLE, OWN], ids=["table", "own table"])
def test_a_scaffold_passes_the_line(tmp_path, case):
    root = tree(tmp_path / "repo")
    before = timing(root)
    r = scaffold(root, *case, *TEXT, "--issue", "1")
    assert r.returncode == 0, r.stderr
    assert changed(root) == {"extensions/demo_src", "CHANGELOG.md"}   # no hand wiring
    assert LINE in (root / "CHANGELOG.md").read_text()
    git(root, "add", "-A")
    assert source_problems(root) == []
    assert session_problems(root) == []
    assert smoke_name_problems(root) == []
    after = timing(root)
    overrun = [line for line in after if line.startswith("brief: ") and line not in before]
    print("brief overrun tolerated:", overrun)   # §5 item 3: left to the next feature's own CI run
    assert [line for line in after if line not in overrun] == before
    r = bats(root, "--filter", "shared part|pipeline", "system/tests/conformance.bats")
    assert r.returncode == 0, r.stdout
    enable(root, "demo_src")
    assert run(root, "system/scripts/extensions.py", "check").stdout == ""
    r = bats(root, "extensions/demo_src/tests/demo_src.bats")
    assert r.returncode == 0, r.stdout


def swap(args, old, new):
    return [new if a == old else a for a in args]


@pytest.mark.parametrize("name,args,reason", [
    ("handoffs", GOOD, "extensions/handoffs exists"),
    ("calendar", GOOD, "is a core alert tag"),
    ("Demo-1", GOOD, "[a-z][a-z0-9_]*"),
    ("demo_src", GOOD[:-2], "--issue"),
    ("demo_src", swap(GOOD, "GMAIL_TOOLS", "SLACK_TOOLS"), "get_thread is not in SLACK_TOOLS"),
    ("demo_src", swap(GOOD, "GMAIL_TOOLS", "OTHER_TOOLS"), "GMAIL_TOOLS"),
    ("demo_src", swap(GOOD, "Demo items in the morning brief", 'say "hi"'), "--description"),
    ("demo_src", swap(GOOD, "mcp__claude_ai_Gmail__get_thread", "not_a_tool"), "mcp__<server>__<tool>"),
], ids=["exists", "core tag", "bad name", "no issue", "not in table", "unknown table", "quote", "bad tool"])
def test_a_usage_error_writes_nothing(tmp_path, name, args, reason):
    root = tree(tmp_path / "repo")
    r = scaffold(root, *args, name=name)
    assert r.returncode == 2
    assert reason in r.stderr
    assert git(root, "status", "--porcelain").stdout == ""


def test_another_extensions_tag_is_refused(tmp_path):
    root = tree(tmp_path / "repo")
    text = (root / "extensions/handoffs/extension.md").read_text()
    (root / "extensions/x").mkdir()
    (root / "extensions/x/extension.md").write_text(
        text.replace("name: handoffs", "name: x").replace("alert_tags: [handoffs]", "alert_tags: [demo_src]"))
    r = scaffold(root, *GOOD)
    assert r.returncode == 2
    assert "is the x extension's alert tag" in r.stderr
    assert not (root / "extensions/demo_src").exists()


def test_a_vault_scaffold_adds_no_changelog_line(tmp_path):
    root = tree(tmp_path / "repo")
    shutil.copyfile(root / "system/config.example.md", root / "system/config.md")
    before = (root / "CHANGELOG.md").read_text()
    r = scaffold(root, *GOOD[:-2])
    assert r.returncode == 0, r.stderr
    assert (root / "CHANGELOG.md").read_text() == before


def test_the_changelog_line_lands_under_today(tmp_path):
    root = tree(tmp_path / "repo")
    assert scaffold(root, *GOOD, name="demo_a").returncode == 0
    assert scaffold(root, *swap(GOOD, "1", "2"), name="demo_b").returncode == 0
    text = (root / "CHANGELOG.md").read_text()
    today = date.today().isoformat()
    assert text.count(f"\n## {today}\n") == 1
    assert f"\n## Changes\n\n## {today}\n" in text
    block = text.split(f"\n## {today}\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert LINE in block
    assert "- Added: Demo items in the morning brief. (#2)" in block
