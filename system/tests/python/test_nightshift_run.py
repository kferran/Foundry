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


def note_of(vault):
    return only_item(vault)[0]


def test_template_clone_holds_no_private_vault_objects(env):
    vault, _ = env
    write(vault, "wiki/work/concepts/Secret.md", "private")
    git(vault, "add", "-A")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "private note")
    secret = git(vault, "rev-parse", "HEAD").strip()
    assert add(vault) == 0
    path, fm = only_item(vault)
    clone = nr._clone(nr.Ctx(vault, NOW), fm)
    assert subprocess.run(["git", "-C", str(clone), "cat-file", "-e", secret]).returncode != 0
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists()


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_vault_master_moving_during_a_run_is_not_a_containment_failure(env, monkeypatch):
    vault, _ = env
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "git add done.txt && git -c user.name=t -c user.email=t@e commit -qm work"
                       f" && git -C {vault} -c user.name=t -c user.email=t@e commit -q --allow-empty -m ingest")
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "done"


def test_resume_stops_a_session_left_running(env):
    vault, _ = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    stale = subprocess.Popen(["sleep", "300"], start_new_session=True)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    (idir / "session.pid").write_text(str(stale.pid))
    ni.update(path, state="running", attempts="1", session_id="old")
    nr.main(["tick"], vault, NOW)
    assert stale.poll() is not None


def test_cancel_stops_a_live_session(env):
    vault, _ = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    live = subprocess.Popen(["sleep", "300"], start_new_session=True)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    (idir / "session.pid").write_text(str(live.pid))
    ni.update(path, state="cancelled")
    nr.main(["tick"], vault, NOW)
    assert live.poll() is not None


def test_budget_spans_attempts(env, monkeypatch):
    vault, _ = env
    monkeypatch.setattr(nr, "POLL", 1)
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "sleep 4")
    assert add(vault, "--now") == 0
    _, fm = only_item(vault)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    (idir / "elapsed").write_text(str(4 * 3600 - 2))
    assert nr.main(["tick"], vault, NOW) == 1
    assert only_item(vault)[1]["reason"] == "budget"


def test_no_init_event_requeues_with_a_fresh_session(env, monkeypatch, tmp_path):
    vault, _ = env
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(empty))
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    _, fm = only_item(vault)
    assert fm["state"] == "queued" and fm["reason"] == "session did not start" and "session_id" not in fm


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_delivery_failure_is_retried_without_a_new_session(env, monkeypatch, tmp_path):
    vault, tmp = env
    shutil.rmtree(tmp / "remote.git")
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "delivering"
    git(tmp, "init", "-q", "--bare", str(tmp / "remote.git"))
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(tmp_path / "missing.jsonl"))  # a new session would fail
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "done"


def test_failed_clones_are_removed_after_seven_days(env):
    vault, tmp = env
    assert add(vault) == 0
    path, fm = only_item(vault)
    old = (NOW - __import__("datetime").timedelta(days=8)).isoformat()
    ni.update(path, state="failed", reason="budget", finished_at=old)
    clone = tmp / "ws" / f"nightshift-{fm['id']}"
    clone.mkdir(parents=True)
    nr.main(["tick"], vault, NOW)
    assert not clone.exists()


def test_research_runs_on_a_context_copy_and_publishes(env, monkeypatch, tmp_path):
    vault, _ = env
    from helpers import concept
    write(vault, "wiki/work/concepts/Background.md", concept("work", "Background"))
    note = concept("work", "Answer", "Found it.", provenance='["headless"]').replace("\n", "\\n")
    writes = tmp_path / "rw.txt"
    writes.write_text(f'out/Answer.md={note}\nout/result.json={{"status": "done", "summary": "ok", "questions": []}}\n')
    monkeypatch.setenv("NIGHTSHIFT_STUB_WRITE", str(writes))
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "test -f context/concepts/Background.md")
    monkeypatch.setenv("NIGHTSHIFT_STUB_ARGS", str(tmp_path / "args.txt"))
    shutil.copy(FX / "ok.jsonl", tmp_path / "r.jsonl")
    (tmp_path / "r.jsonl").write_text((FX / "ok.jsonl").read_text().replace(
        '"tools":["Read","Glob","Grep","Edit","Write","Bash","Skill","Agent","TodoWrite"]', '"tools":["Read","Write"]'))
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(tmp_path / "r.jsonl"))
    brief = tmp_path / "brief.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", "q", "--partition", "work", "--brief-file", str(brief),
                    "--output", "wiki/work/concepts/Answer.md", "--now"], vault, NOW) == 0
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "done"
    assert (vault / "wiki/work/concepts/Answer.md").is_file()
    assert "--add-dir" not in (tmp_path / "args.txt").read_text()


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_protected_files_reach_the_pushed_branch(env, monkeypatch, tmp_path):
    vault, tmp = env
    writes = tmp_path / "pw.txt"
    writes.write_text(f"done.txt=yes\n.nightshift/protected/.claude/skills/demo/SKILL.md=hello\\n\n"
                      f".nightshift/result.json={RESULT}\n")
    monkeypatch.setenv("NIGHTSHIFT_STUB_WRITE", str(writes))
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    branch = git(tmp / "remote.git", "branch", "--list").split()[-1]
    assert git(tmp / "remote.git", "show", f"{branch}:.claude/skills/demo/SKILL.md") == "hello\n"
    assert git(tmp / "remote.git", "show", f"{branch}:done.txt") == "yes"


def test_selftest_retries_when_the_model_declines(env, monkeypatch, tmp_path):
    vault, _ = env
    declined = tmp_path / "declined.jsonl"
    declined.write_text((FX / "ok.jsonl").read_text().replace('"content":"CURL_EXIT=6"', '"content":"no"'))
    good = tmp_path / "good.jsonl"
    good.write_text((FX / "ok.jsonl").read_text().replace("CURL_EXIT=6", "CURL_EXIT=6 CAT_EXIT=1"))
    stream = tmp_path / "s.jsonl"
    shutil.copy(declined, stream)
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(stream))
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", f"if [ -f {tmp_path}/once ]; then cp {good} {stream}; else touch {tmp_path}/once; fi")
    assert nr.selftest(vault)[0] is True
    shutil.copy(declined, stream)
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", "true")
    ok, why = nr.selftest(vault)
    assert ok is False and "did not run" in why


def test_selftest_prompt_says_failures_are_expected():
    assert "expected" in nr.SELFTEST_PROMPT and "self-test" in nr.SELFTEST_PROMPT
