import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from helpers import REPO, write
from test_nightshift_check import PLAN
from vaultlib import nightshift_item as ni
from vaultlib import nightshift_run as nr

FX = REPO / "system" / "tests" / "fixtures" / "nightshift"
NOW = datetime(2026, 10, 6, 18, 0, tzinfo=timezone.utc)   # 12:00 in Denver
RESULT = '{"status": "done", "summary": "did it", "tests_run": ["true"], "pr_title": "T", "pr_body": "B", "questions": []}'


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def env(vault: Path, tmp_path: Path, monkeypatch):
    shutil.copytree(REPO / "system" / "nightshift", vault / "system" / "nightshift")
    git(vault, "init", "-q", "-b", "master")
    write(vault, "docs/p.md", PLAN)
    git(vault, "add", "-A")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "base")
    git(vault, "branch", "feat/x")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    write(vault, "system/config.md", "---\ntype: config\ntimezone: \"America/Denver\"\nbrief_time: \"06:00\"\n"
          f"template_remote: \"{remote}\"\nnightshift_workspace: \"{tmp_path / 'ws'}\"\n---\n")
    stream = tmp_path / "stream.jsonl"
    shutil.copy(FX / "ok.jsonl", stream)
    writes = tmp_path / "writes.txt"
    writes.write_text(f"done.txt=yes\n.nightshift/result.json={RESULT}\n")
    monkeypatch.setenv("FOUNDRY_CLAUDE_BIN", str(REPO / "system/tests/stub_claude_nightshift"))
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(stream))
    monkeypatch.setenv("NIGHTSHIFT_STUB_WRITE", str(writes))
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "git add done.txt && git -c user.name=t -c user.email=t@e commit -qm work")
    monkeypatch.setattr(nr, "PR_FOR_LOCAL", "github:o/r")  # a local bare remote stands in for GitHub
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text('#!/bin/bash\n[[ "$1" == auth ]] && exit 0\necho https://github.com/o/r/pull/1\n')
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setattr(nr, "health", lambda vault, now, entries: {"claude": "ok", "sandbox": "ok", "usage7": 0.4})
    return vault, tmp_path


def add(vault, *extra):
    return nr.main(["add", "--kind", "plan", "--title", "dtcc watcher", "--partition", "work", "--repo", "template",
                    "--base", "feat/x", "--plan", "docs/p.md", "--tasks", "1-2", "--verify", "test -f done.txt", *extra],
                   vault, NOW)


def only_item(vault):
    (path, fm, body), = ni.items(vault)
    return path, fm


def test_add_refuses_unready(env):
    vault, _ = env
    assert nr.main(["add", "--kind", "plan", "--title", "x", "--partition", "work", "--repo", "template",
                    "--base", "feat/x", "--plan", "docs/p.md", "--verify", "true"], vault, NOW) == 2
    assert ni.items(vault) == []


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_now_item_runs_verifies_pushes_and_reports(env):
    vault, tmp = env
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    _, fm = only_item(vault)
    assert fm["state"] == "done" and fm["result"] == "https://github.com/o/r/pull/1"
    assert "nightshift/" in git(tmp / "remote.git", "branch", "--list")
    report = (vault / "system/logs/nightshift/2026-10-07.md").read_text()
    assert "Review and merge: https://github.com/o/r/pull/1" in report
    assert not list((tmp / "ws").glob("nightshift-2026*"))  # clone removed after delivery


def test_window_item_waits_in_daytime(env):
    vault, _ = env
    assert add(vault) == 0
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "queued"


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_failure_blocks_without_push(env, monkeypatch):
    vault, tmp = env
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "true")  # no commit, done.txt left uncommitted
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert fm["state"] in ("blocked", "failed") and fm["reason"] in ("verify", "no commits")
    assert git(tmp / "remote.git", "branch", "--list").strip() == ""


def test_usage_limit_waits_then_resumes(env, monkeypatch):
    vault, tmp = env
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(FX / "limited.jsonl"))
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    _, fm = only_item(vault)
    assert fm["state"] == "waiting_reset" and fm["reset_at"]


def test_profile_mismatch_kills_and_fails(env, monkeypatch):
    vault, _ = env
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(FX / "badinit.jsonl"))
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert fm["state"] == "failed" and fm["reason"] == "profile"


def test_no_result_is_failed(env, monkeypatch, tmp_path):
    vault, _ = env
    empty = tmp_path / "none.txt"
    empty.write_text("")
    monkeypatch.setenv("NIGHTSHIFT_STUB_WRITE", str(empty))
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "true")
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    assert only_item(vault)[1]["reason"] == "no result"


def test_cancel_and_list(env, capsys):
    vault, _ = env
    assert add(vault) == 0
    _, fm = only_item(vault)
    assert nr.main(["cancel", fm["id"]], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "cancelled"
    nr.main(["list"], vault, NOW)
    assert "cancelled" in capsys.readouterr().out


def test_lock_held_exits_4(env):
    import fcntl
    vault, _ = env
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / nr.LOCK, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert nr.main(["tick"], vault, NOW) == 4


def test_selftest_parses_tool_results(env, monkeypatch, tmp_path):
    vault, _ = env
    good = tmp_path / "good.jsonl"
    good.write_text((FX / "ok.jsonl").read_text().replace("CURL_EXIT=6", "CURL_EXIT=6 CAT_EXIT=1"))
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(good))
    assert nr.selftest(vault)[0] is True
    bad = tmp_path / "bad.jsonl"
    bad.write_text((FX / "ok.jsonl").read_text().replace("CURL_EXIT=6", "CURL_EXIT=0 CAT_EXIT=1"))
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(bad))
    ok, why = nr.selftest(vault)
    assert ok is False and "curl" in why
