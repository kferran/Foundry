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
    git(vault, "push", "-q", str(remote), "feat/x")   # template items are read from the template remote
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
    assert (fm["state"], fm["reason"]) == ("blocked", "no commits")
    assert git(tmp / "remote.git", "branch", "--list", "nightshift/*").strip() == ""


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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the self-test plants its canary under $HOME
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


def test_template_clone_comes_from_the_template_remote(env):
    vault, _ = env
    on_remote = git(vault, "rev-parse", "feat/x").strip()
    assert add(vault) == 0
    git(vault, "checkout", "-q", "feat/x")
    write(vault, "vault-only.txt", "never pushed")
    git(vault, "add", "vault-only.txt")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "vault only")
    git(vault, "checkout", "-q", "master")
    path, fm = only_item(vault)
    clone = nr._clone(nr.Ctx(vault, NOW), fm)
    assert git(clone, "rev-parse", "HEAD").strip() == on_remote
    assert not (clone / "vault-only.txt").exists()
    assert git(clone, "for-each-ref", "--format=%(refname)").split() == [f"refs/heads/nightshift/{fm['id']}", "refs/remotes/base"]


def test_a_failed_fetch_leaves_no_clone_and_a_half_built_one_is_rebuilt(env):
    vault, tmp = env
    assert add(vault) == 0
    path, fm = only_item(vault)
    ctx = nr.Ctx(vault, NOW)
    half = ctx.workspace / f"nightshift-{fm['id']}"
    half.mkdir(parents=True)
    git(half, "init", "-q")   # a tick killed before its fetch
    clone = nr._clone(ctx, fm)
    assert git(clone, "rev-parse", "refs/remotes/base").strip() == git(tmp / "remote.git", "rev-parse", "feat/x").strip()
    shutil.rmtree(clone)
    git(tmp / "remote.git", "branch", "-D", "feat/x")
    with pytest.raises(RuntimeError):
        nr._clone(ctx, fm)
    assert not clone.exists()


def test_a_template_base_gone_from_the_remote_fails_at_once_with_a_needs_you_line(env):
    vault, tmp = env
    assert add(vault, "--now") == 0
    git(tmp / "remote.git", "branch", "-D", "feat/x")
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert (fm["state"], fm["reason"]) == ("failed", "base")
    out = json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "outcome.json").read_text())
    assert out["needs"][0].startswith(f"Push feat/x to the template remote, then queue {fm['id']} again")


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
    hook = tmp / "remote.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")   # the remote refuses pushes; the check and the clone still fetch
    hook.chmod(0o755)
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "delivering"
    hook.unlink()
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


def test_research_reads_a_pinned_copy_of_its_codebase(env, tmp_path):
    vault, tmp = env
    from test_nightshift_check import registered
    clone = registered(vault, tmp_path / "cb")
    fm = {"id": "2026-10-08-q", "kind": "research", "partition": "work", "repo": "shop"}
    ctx = nr.Ctx(vault, NOW)
    first = git(clone, "rev-parse", "origin/HEAD").strip()
    d = nr._research_dir(ctx, fm)
    assert git(d / "code", "rev-parse", "HEAD").strip() == first
    assert (d / "code" / "app.py").is_file()
    seed = tmp_path / "cb" / "shop-seed"   # a later commit reaches the registered clone's origin/HEAD
    write(seed, "later.py", "x\n")
    git(seed, "add", "later.py")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "later")
    git(seed, "push", "-q", str(tmp_path / "cb" / "shop.git"), "main")
    git(clone, "fetch", "-q")
    d = nr._research_dir(ctx, fm)   # a resumed attempt reads the same commit
    assert git(d / "code", "rev-parse", "HEAD").strip() == first
    assert not (d / "code" / "later.py").exists()
    assert str(clone) in nr._deny(ctx, fm)   # the live checkout stays denied


def test_research_code_is_one_commit_with_no_links_to_the_live_clone(env, tmp_path):
    vault, tmp = env
    from test_nightshift_check import registered
    clone = registered(vault, tmp_path / "cb")
    git(clone, "branch", "unpushed")
    ctx = nr.Ctx(vault, NOW)
    fm = {"id": "2026-10-08-q", "kind": "research", "partition": "work", "repo": "shop"}
    code = nr._research_dir(ctx, fm) / "code"
    assert "unpushed" not in git(code, "for-each-ref")
    assert all(p.stat().st_nlink == 1 for p in (code / ".git" / "objects").rglob("*") if p.is_file())


def test_research_code_half_built_or_moved_is_rebuilt_at_the_recorded_commit(env, tmp_path):
    vault, tmp = env
    from test_nightshift_check import registered
    clone = registered(vault, tmp_path / "cb")
    ctx = nr.Ctx(vault, NOW)
    fm = {"id": "2026-10-08-q", "kind": "research", "partition": "work", "repo": "shop"}
    first = git(clone, "rev-parse", "origin/HEAD").strip()
    code = nr._research_dir(ctx, fm) / "code"
    shutil.rmtree(code)   # a killed tick left a clone with a HEAD and no files
    git(tmp_path, "clone", "-q", "--no-checkout", str(clone), str(code))
    assert (nr._research_dir(ctx, fm) / "code" / "app.py").is_file()
    write(code, "app.py", "changed\n")   # a session that moved code/ on
    git(code, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qam", "moved")
    nr._research_dir(ctx, fm)
    assert git(code, "rev-parse", "HEAD").strip() == first
    assert (code / "app.py").read_text() == "print(1)\n"


def test_research_reads_the_template_from_its_remote_and_needs_no_code_without_a_repo(env):
    vault, tmp = env
    ctx = nr.Ctx(vault, NOW)
    d = nr._research_dir(ctx, {"id": "2026-10-08-t", "kind": "research", "partition": "work", "repo": "template",
                               "base": "feat/x"})
    assert git(d / "code", "rev-parse", "HEAD").strip() == git(tmp / "remote.git", "rev-parse", "feat/x").strip()
    d = nr._research_dir(ctx, {"id": "2026-10-08-n", "kind": "research", "partition": "work"})
    assert not (d / "code").exists()


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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the self-test plants its canary under $HOME
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
    assert nr.CANARY in nr.SELFTEST_PROMPT and ".ssh" not in nr.SELFTEST_PROMPT


def test_selftest_plants_a_canary_and_fails_if_the_session_reads_it(env, monkeypatch, tmp_path):
    vault, _ = env
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    canary = home / ".config" / "foundry" / "nightshift-canary"
    stream = tmp_path / "s.jsonl"
    clean = (FX / "ok.jsonl").read_text().replace("CURL_EXIT=6", "CURL_EXIT=6 CAT_EXIT=1")
    stream.write_text(clean)
    monkeypatch.setenv("NIGHTSHIFT_STUB_STREAM", str(stream))
    # A masked sandbox: the canary exists while the session runs, the read fails, and the canary is gone afterwards.
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", f"test -s {canary} && touch {tmp_path}/seen")
    assert nr.selftest(vault) == (True, "")
    assert (tmp_path / "seen").exists() and not canary.exists()
    # An unmasked sandbox: the session's output carries the canary's content, even with a non-zero exit code.
    line = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "LEAK CAT_EXIT=1"}]}})
    leak = tmp_path / "leak.sh"
    leak.write_text(f"echo '{line}' | sed \"s/LEAK/$(cat {canary})/\" >> {stream}\n")
    monkeypatch.setenv("NIGHTSHIFT_STUB_SHELL", f"bash {leak}")
    ok, why = nr.selftest(vault)
    assert ok is False and "canary" in why
    assert not canary.exists()
    # A session that cannot start still leaves no canary behind.
    monkeypatch.setenv("FOUNDRY_CLAUDE_BIN", str(tmp_path / "missing"))
    assert nr.selftest(vault)[0] is False and not canary.exists()



def test_delivery_runs_no_git_inside_the_session_clone(env, monkeypatch):
    vault, tmp = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    ctx = nr.Ctx(vault, NOW)
    clone = nr._clone(ctx, fm)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    before = nr._before(ctx, fm, idir)
    assert before["base_sha"] == git(tmp / "remote.git", "rev-parse", "feat/x").strip()
    (clone / "done.txt").write_text("yes")
    git(clone, "add", "done.txt")
    git(clone, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "work")
    (clone / ".nightshift").mkdir()
    (clone / ".nightshift" / "result.json").write_text(RESULT)
    monkeypatch.setattr(nr.nd, "verify_sha", lambda *a: (True, ""))  # bwrap is covered by the end-to-end tests
    calls, real = [], subprocess.run

    def spy(cmd, *a, **kw):
        calls.append([str(c) for c in cmd])
        return real(cmd, *a, **kw)
    monkeypatch.setattr(subprocess, "run", spy)
    out = nr._deliver_plan(ctx, fm, clone, idir, before)
    assert out["state"] == "done", out
    assert [c for c in calls if c[:3] == ["git", "-C", str(clone)]] == []



def test_tick_refuses_a_note_with_an_unsafe_id(env):
    vault, tmp = env
    from test_nightshift_item import plan_fm
    path = ni.note_path(vault, "work", "2026-10-06-evil")
    ni.save(path, plan_fm(id="../../../evil", start="now", tasks="1-2", verify=["true"]), "")
    old = ni.note_path(vault, "work", "2026-09-01-old")
    long_ago = (NOW - __import__("datetime").timedelta(days=8)).isoformat()
    ni.save(old, plan_fm(id="../../victim", state="failed", reason="budget", finished_at=long_ago), "")
    (tmp / "victim").mkdir()  # where the 7-day clean-up would point for that id
    assert nr.main(["tick"], vault, NOW) == 2
    fm, _ = ni.load(path)
    assert fm["state"] == "failed" and fm["reason"].startswith("invalid: id must look like")
    assert not (vault / "system" / "evil").exists() and not (tmp / "evil").exists()
    alerts = "".join(p.read_text() for p in (vault / "system" / "logs").glob("alerts_*.md"))
    assert "2026-10-06-evil.md refused" in alerts
    assert nr.main(["tick"], vault, NOW) == 0  # refused once; later ticks skip both notes
    assert (tmp / "victim").is_dir()
