"""foundry-review's diff checks (factory F4 §3.3): each check flags its seed (the line shape of a past defect) and
passes its near miss. Every case builds a small git repository: a base commit on master, then one commit."""
import subprocess
import sys

import pytest

from helpers import REPO

# The checks guard the template's change file rule; a vault has no change files to check.
pytestmark = pytest.mark.skipif(
    (REPO / "system/config.md").exists(),
    reason="this checkout is a vault (system/config.md exists); the checks guard the template")

SCRIPT = REPO / ".claude/skills/foundry-review/review_diff.py"
CHECKS = ["now-redaction", "gate-escape", "alert-text", "sleep-race", "skip-reason", "changelog-label",
          "read-source-check", "computed-session", "computed-config"]


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def write(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def case(tmp_path, before, after, branch="feat/x", args=("--base", "master")):
    """Commit `before` on master, then `after` on a branch; run the script from the repository."""
    git(tmp_path, "init", "-q", "-b", "master")
    write(tmp_path, {"changes/CHANGELOG.md": "## Changes\n", **before})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", branch)
    write(tmp_path, after)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "head")
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=tmp_path, capture_output=True, text=True)


SEEDS = [
    ("now-redaction", {"system/scripts/x.py": 'notify("work", one_line(text))\n'}, "system/scripts/x.py:1"),
    ("gate-escape", {"system/scripts/x.py": '(root / "wiki/work/x.md").write_text(body)\n'}, "system/scripts/x.py:1"),
    ("gate-escape", {".claude/settings.json": '"Edit(/wiki/**)"\n'}, ".claude/settings.json:1"),
    ("alert-text", {"extensions/x/scripts/x.sh": 'alert_once "x failed:" "$subject"\n'}, "extensions/x/scripts/x.sh:1"),
    ("alert-text", {"extensions/x/scripts/x.sh": 'alert_once "x failed:" "$note"\n'}, "extensions/x/scripts/x.sh:1"),
    ("now-redaction", {"extensions/x/scripts/x.sh": 'system/scripts/notify.sh "$text"\n'}, "extensions/x/scripts/x.sh:1"),
    ("gate-escape", {"system/scripts/x.py": 'f = Path("wiki/work/x.md").open("w")\n'}, "system/scripts/x.py:1"),
    ("read-source-check", {"extensions/x/scripts/café.sh": 'connector_run "$p" "$work"\n'},
     "extensions/x/scripts/café.sh:1"),
    ("sleep-race", {"system/tests/x.bats": "++ sleep 2\n"}, "system/tests/x.bats:1"),
    ("gate-escape", {"system/scripts/x.py": '(vault / "wiki" / p / "x.md").write_text(body)\n'}, "system/scripts/x.py:1"),
    ("computed-session", {"system/scripts/x.sh": 'timeout 60 "$tool" -p "$p"\n'}, "system/scripts/x.sh:1"),
    ("computed-session", {"system/scripts/x.sh": '"${TOOL:-claude}" -p "$p"\n'}, "system/scripts/x.sh:1"),
    ("computed-session", {"system/scripts/x.sh": 'exec "$tool" -p "$p"\n'}, "system/scripts/x.sh:1"),
    ("computed-session", {"system/scripts/x.sh": '"${cmd[@]}" -p "$p"\n'}, "system/scripts/x.sh:1"),
    ("skip-reason", {"system/tests/x.bats": "  [ -x foo ] || skip\n"}, "system/tests/x.bats:1"),
    ("sleep-race", {"system/tests/x.bats": "  sleep 2\n"}, "system/tests/x.bats:1"),
    ("skip-reason", {"system/tests/x.bats": "  skip\n"}, "system/tests/x.bats:1"),
    ("skip-reason", {"system/tests/python/test_x.py": "@pytest.mark.skip()\n"}, "system/tests/python/test_x.py:1"),
    ("changelog-label", {"system/scripts/x.sh": "echo hi\n"}, ""),
    ("read-source-check", {"extensions/x/scripts/x.sh": 'connector_run "$p" "$work"\n'}, "extensions/x/scripts/x.sh:1"),
    ("computed-session", {"system/scripts/x.sh": '"$tool" -p "$prompt"\n'}, "system/scripts/x.sh:1"),
    ("computed-config", {"system/scripts/x.py": 'p = root / "system" / ("config" + ".md")\n'}, "system/scripts/x.py:1"),
]

NEAR_MISSES = [
    ("now-redaction", {"system/scripts/x.py": 'text = redact_credentials(text)\nnotify("work", one_line(text))\n'}, {}),
    ("now-redaction", {"system/scripts/x.py": 'now.add("work", "owed", one_line(text))\n'}, {}),
    ("gate-escape", {"system/scripts/x.py": '(root / "wiki/work/x.md").read_text()\n'}, {}),
    ("gate-escape", {"system/scripts/vaultlib/publish.py": '(root / "wiki/work/x.md").write_text(body)\n'}, {}),
    ("alert-text", {"extensions/x/scripts/x.sh": 'fail 7 "$CONNECTOR_REASON"\n'}, {}),
    ("alert-text", {"extensions/x/scripts/x.sh": 'alert_once "x failed:" "$n threads"\n'}, {}),
    ("sleep-race", {"system/tests/x.bats": '  STUB_SLEEP=3 X_TIMEOUT=1 run "$F"\n'}, {}),
    ("skip-reason", {"system/tests/x.bats": '  skip "environment: no bwrap"\n'}, {}),
    ("skip-reason", {"system/tests/python/test_x.py": '@pytest.mark.skipif(c, reason="vault")\n'}, {}),
    ("changelog-label", {"docs/x.md": "words\n"}, {}),
    ("changelog-label", {"system/scripts/x.sh": "echo hi\n", "changes/2026-10-01-x.md": "- Fixed: x. (#5)\n"}, {}),
    ("read-source-check", {"extensions/x/scripts/x.sh": 'fetch_check_arg "$@"\nconnector_run "$p" "$work"\n'}, {}),
    ("computed-session", {"system/scripts/x.sh": '"${CLAUDE_BIN:-claude}" -p "$prompt"\n'}, {}),
    ("computed-config", {"system/scripts/x.py": "from vaultlib.api import config\n"}, {}),
    ("computed-config", {"system/scripts/x.py": 'log(f"bad config: {e}")\n'}, {}),
    ("gate-escape", {"system/scripts/x.py": 'open("wiki/work/x.md").read()\n'}, {}),
    ("gate-escape", {"system/scripts/x.py": 'if n > 3: p = vault / "wiki" / "x.md"\n'}, {}),
    ("gate-escape", {"docs/x.md": "write <x> to wiki/work/\n"}, {}),
    ("alert-text", {"extensions/x/scripts/x.sh": 'connector_run "$prompt" "$work" || fail $? "$CONNECTOR_REASON"\n'}, {}),
    ("alert-text", {"extensions/x/scripts/x.sh": 'fail "$CONNECTOR_EXIT" "$CONNECTOR_REASON"\n'}, {}),
    ("alert-text", {"extensions/x/scripts/x.sh": 'fail "$qrc" "$FETCH_REASON"\n'}, {}),
    ("alert-text", {"system/scripts/x.py": 'p = root / f"alerts_{day}.md"\n'}, {}),
    ("alert-text", {"system/scripts/x.py": 'alert_once(f"x failed: {n:>3} threads")\n'}, {}),
    ("now-redaction", {"docs/x.md": "call notify( to post it\n"}, {}),
    ("skip-reason", {"system/tests/python/test_x.py": "@pytest.mark.skipif(cond,\n    reason=\"vault\")\n"}, {}),
]


def lines(result):
    return result.stdout.splitlines()


@pytest.mark.parametrize("check,files,where", SEEDS)
def test_a_seed_is_flagged(tmp_path, check, files, where):
    result = case(tmp_path, {}, files)
    assert result.returncode == 1, result.stdout + result.stderr
    assert any(line.startswith(f"{check}: {where}") for line in lines(result)), result.stdout
    assert f"{check}: pass" not in lines(result)


@pytest.mark.parametrize("check,files,before", NEAR_MISSES)
def test_a_near_miss_passes(tmp_path, check, files, before):
    result = case(tmp_path, before, files)
    assert f"{check}: pass" in lines(result), result.stdout + result.stderr


def test_a_clean_diff_exits_0(tmp_path):
    result = case(tmp_path, {}, {"docs/x.md": "words\n"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert lines(result) == [f"{c}: pass" for c in CHECKS]


def test_an_unknown_base_exits_2(tmp_path):
    result = case(tmp_path, {}, {"docs/x.md": "words\n"}, args=("--base", "nope"))
    assert result.returncode == 2
    assert "review_diff:" in result.stderr


def test_a_bad_argument_exits_2(tmp_path):
    assert case(tmp_path, {}, {"docs/x.md": "words\n"}, args=("--base",)).returncode == 2


def test_outside_a_repository_exits_2(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 2
    assert "not a git repository" in result.stderr


def test_no_origin_falls_back_to_master(tmp_path):
    result = case(tmp_path, {}, {"system/tests/x.bats": "  sleep 2\n"}, args=())
    assert result.returncode == 1, result.stdout + result.stderr
    assert any(line.startswith("sleep-race: system/tests/x.bats:1") for line in lines(result))


def test_a_vault_skips_the_changelog_half(tmp_path):
    result = case(tmp_path, {"system/config.md": "---\n---\n"}, {"system/scripts/x.sh": "echo hi\n"})
    assert "changelog-label: pass" in lines(result), result.stdout + result.stderr


def test_a_fix_branch_asks_for_a_label(tmp_path):
    result = case(tmp_path, {}, {"system/scripts/x.sh": "echo hi\n", "changes/2026-10-01-x.md": "- Fixed: x. (#5)\n"},
                  "fix/x")
    assert any(line.startswith("changelog-label:") and "defect:" in line for line in lines(result)), result.stdout


def test_a_removed_line_is_not_a_hit(tmp_path):
    seed = '(root / "wiki/work/x.md").write_text(body)\n'
    result = case(tmp_path, {"system/scripts/x.py": seed}, {"system/scripts/x.py": "x = 1\n"})
    assert "gate-escape: pass" in lines(result), result.stdout + result.stderr
