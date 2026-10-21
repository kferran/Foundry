import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from helpers import REPO, write
from test_nightshift_check import PLAN
from vaultlib import nightshift_item as ni
from vaultlib import nightshift_report as rep
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
          f"template_remote: \"{remote}\"\nnightshift_workspace: \"{tmp_path / 'ws'}\"\nrun_window: \"22:00-05:00\"\n---\n")
    stream = tmp_path / "stream.jsonl"
    shutil.copy(FX / "ok.jsonl", stream)
    writes = tmp_path / "writes.txt"
    writes.write_text(f"done.txt=yes\n.nightshift/result.json={RESULT}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # The session's environment is session_env() alone, so the stub's settings reach it through this wrapper.
    (bin_dir / "claude").write_text(f'#!/bin/bash\nset -a\n. "{tmp_path / "stub.env"}"\nset +a\n'
                                    f'exec "{REPO / "system/tests/stub_claude_nightshift"}" "$@"\n')
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("FOUNDRY_CLAUDE_BIN", str(bin_dir / "claude"))
    stub(tmp_path, STREAM=str(stream), WRITE=str(writes),
         SHELL="git add done.txt && git -c user.name=t -c user.email=t@e commit -qm work")
    monkeypatch.setattr(nr, "PR_FOR_LOCAL", "github:o/r")  # a local bare remote stands in for GitHub
    (bin_dir / "gh").write_text('#!/bin/bash\n[[ "$1" == auth ]] && exit 0\necho https://github.com/o/r/pull/1\n')
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setattr(nr, "health", lambda vault, now, entries: {"claude": "ok", "sandbox": "ok", "usage7": 0.4})
    return vault, tmp_path


def stub(tmp, **settings):
    """NIGHTSHIFT_STUB_<KEY> settings for the stub, exported by the fixture's wrapper (the session environment is
    session_env() alone and carries none of them)."""
    f = tmp / "stub.env"
    names = {f"NIGHTSHIFT_STUB_{k}" for k in settings}
    keep = [l for l in (f.read_text().splitlines() if f.is_file() else [])
            if l.removeprefix("export ").split("=", 1)[0] not in names]
    f.write_text("".join(f"{l}\n" for l in keep) +
                 "".join(f"export NIGHTSHIFT_STUB_{k}={shlex.quote(v)}\n" for k, v in settings.items()))


def add(vault, *extra):
    return nr.main(["add", "--kind", "plan", "--title", "dtcc watcher", "--partition", "work", "--repo", "template",
                    "--base", "feat/x", "--plan", "docs/p.md", "--tasks", "1-2", "--verify", "test -f done.txt", *extra],
                   vault, NOW)


def only_item(vault):
    (path, fm, body), = ni.items(vault)
    return path, fm


def test_add_refuses_unready(env):
    vault, tmp = env
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
    assert "order/" in git(tmp / "remote.git", "branch", "--list")
    report = (vault / "system/logs/nightshift/2026-10-07.md").read_text()
    assert "Review and merge: https://github.com/o/r/pull/1" in report
    assert not list((tmp / "ws").glob("nightshift-2026*"))  # clone removed after delivery
    body = (vault / "system/logs/nightshift/items" / fm["id"] / "pr_body.md").read_text()
    assert body.endswith(f"Queued as Work Order `{fm['id']}`.\n")


def test_first_tick_checks_health_even_when_a_usage_reading_made_the_file(env, monkeypatch):
    # run_headless.sh records usage into the day's health file before any tick (usage ceiling spec): the
    # first tick must still run the claude, gh and sandbox checks, and keep the newer reading.
    vault, tmp = env
    monkeypatch.setattr(nr, "health", lambda vault, now, entries: {"claude": "ok", "sandbox": "FAILED: canary read"})
    day = nr.Ctx(vault, NOW).date
    rep.record_usage(vault, day, {"five_hour": 0.3, "seven_day": 0.2}, NOW.isoformat())
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    h = json.loads((vault / rep.DIR / f"health-{day}.json").read_text())
    assert h["sandbox"] == "FAILED: canary read" and h["usage5"] == 0.3
    assert only_item(vault)[1]["state"] == "queued"


def test_window_item_waits_in_daytime(env):
    vault, tmp = env
    assert add(vault, "--window") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "queued"


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_failure_blocks_without_push(env, monkeypatch):
    vault, tmp = env
    stub(tmp, SHELL="true")  # no commit, done.txt left uncommitted
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert (fm["state"], fm["reason"]) == ("blocked", "no commits")
    assert git(tmp / "remote.git", "branch", "--list", "order/*").strip() == ""


def test_usage_limit_waits_then_resumes(env, monkeypatch):
    vault, tmp = env
    stub(tmp, STREAM=str(FX / "limited.jsonl"))
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    _, fm = only_item(vault)
    assert fm["state"] == "waiting_reset" and fm["reset_at"]


def test_profile_mismatch_kills_and_fails(env, monkeypatch):
    vault, tmp = env
    stub(tmp, STREAM=str(FX / "badinit.jsonl"))
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert fm["state"] == "failed" and fm["reason"] == "profile"


def test_the_session_gets_only_the_allowlisted_environment(needs_bwrap, env, monkeypatch):
    # audit S3/S7 spec §2: session_env() is the session's whole environment; a planted agent socket never reaches it
    vault, tmp = env
    stub(tmp, ENV=str(tmp / "env.txt"))
    monkeypatch.setenv("SSH_AUTH_SOCK", "/run/user/1/keyring/ssh")
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    names = {line.split("=", 1)[0] for line in (tmp / "env.txt").read_text().splitlines() if "=" in line}
    assert "SSH_AUTH_SOCK" not in names
    assert {"PATH", "HOME"} <= names
    bash_own = {"_", "SHLVL", "PWD", "OLDPWD"}
    assert names - bash_own - {n for n in names if n.startswith("NIGHTSHIFT_STUB_")} <= set(nr.ss.ENV)


def test_no_result_is_failed(env, monkeypatch, tmp_path):
    vault, tmp = env
    empty = tmp_path / "none.txt"
    empty.write_text("")
    stub(tmp, WRITE=str(empty))
    stub(tmp, SHELL="true")
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 1
    assert only_item(vault)[1]["reason"] == "no result"


def test_settings_read_the_old_keys_and_the_new_ones_win(env, tmp_path):
    vault, tmp = env
    assert nr.Ctx(vault, NOW).workspace == tmp_path / "ws"   # the fixture sets only nightshift_workspace
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\nnightshift_workspace: "/old"\n'
          'order_workspace: "/new"\nnightshift_window: "21:00-04:00"\n---\n')
    ctx = nr.Ctx(vault, NOW)
    assert ctx.workspace == Path("/new") and ctx.window == nr.ns.parse_window("21:00-04:00")
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\nnightshift_window: "21:00-04:00"\n'
          'run_window: "23:00-02:00"\n---\n')
    assert nr.Ctx(vault, NOW).window == nr.ns.parse_window("23:00-02:00")


def test_alerts_carry_the_orders_tag(env):
    vault, tmp = env
    ctx = nr.Ctx(vault, NOW)
    ctx.alert("k", "something broke")
    text = "".join(p.read_text() for p in (vault / "system" / "logs").glob("alerts_*.md"))
    assert "[orders] something broke" in text and "[nightshift]" not in text


def test_add_starts_now_unless_told_otherwise(env):
    vault, tmp = env
    assert add(vault) == 0
    path, fm = only_item(vault)
    assert fm["start"] == "now"
    path.unlink()
    assert add(vault, "--window") == 0
    assert only_item(vault)[1]["start"] == "window"


def test_a_finished_session_stores_the_five_hour_usage(env, monkeypatch, tmp_path):
    vault, tmp = env
    empty = tmp_path / "none.txt"
    empty.write_text("")
    stub(tmp, WRITE=str(empty))
    stub(tmp, SHELL="true")
    assert add(vault) == 0
    nr.main(["tick"], vault, NOW)
    h = json.loads((vault / "system/logs/nightshift/health-2026-10-07.json").read_text())
    assert (h["usage5"], h["usage7"]) == (0.12, 0.48)
    assert NOW <= datetime.fromisoformat(h["usage5_at"]) < NOW + timedelta(minutes=5)


def health_at(vault, usage5, age_hours, date="2026-10-07"):
    nr.rep.write_health(vault, date, {"claude": "ok", "sandbox": "ok", "usage5": usage5,
                                      "usage5_at": (NOW - timedelta(hours=age_hours)).isoformat()})


def test_a_hold_reaches_the_report_file_the_brief_copies(env):
    vault, tmp = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1)
    nr.main(["tick"], vault, NOW)
    assert "> Held: 5-hour usage 70% at or above 60%" in (vault / nr.rep.DIR / "2026-10-07.md").read_text()


def test_a_cancelled_held_item_clears_the_held_line(env):
    vault, tmp = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1)
    nr.main(["tick"], vault, NOW)
    assert nr.main(["cancel", only_item(vault)[1]["id"]], vault, NOW) == 0
    nr.main(["tick"], vault, NOW)
    assert "Held" not in (vault / nr.rep.DIR / "2026-10-07.md").read_text()


def test_a_new_report_day_keeps_the_last_five_hour_reading(env):
    vault, tmp = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1, date="2026-10-06")   # read by the last session before the brief
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "queued"
    assert "> Held: 5-hour usage 70%" in (vault / nr.rep.DIR / "2026-10-07.md").read_text()


def test_the_five_hour_ceiling_holds_a_new_item_and_says_why(env, capsys):
    vault, tmp = env
    assert add(vault) == 0
    health_at(vault, 0.7, 1)
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "queued"
    nr.main(["report"], vault, NOW)
    assert "> Held: 5-hour usage 70% at or above 60%" in capsys.readouterr().out


@pytest.mark.parametrize("age,config", [(6, ""), (1, 'order_max_five_hour: "0.8"\n')])
def test_an_old_reading_or_a_higher_ceiling_lets_it_start(env, monkeypatch, capsys, age, config):
    vault, tmp = env
    if config:
        cfg = vault / "system/config.md"
        cfg.write_text(cfg.read_text().rsplit("---\n", 1)[0] + config + "---\n")
    stub(tmp, STREAM=str(FX / "limited.jsonl"))
    assert add(vault) == 0
    health_at(vault, 0.7, age)
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "waiting_reset"
    nr.main(["report"], vault, NOW)
    assert "Held" not in capsys.readouterr().out


@pytest.mark.parametrize("state", ["running", "waiting_reset"])
def test_the_five_hour_ceiling_never_stops_an_item_already_started(env, monkeypatch, state):
    vault, tmp = env
    stub(tmp, STREAM=str(FX / "limited.jsonl"))
    assert add(vault) == 0
    path, _ = only_item(vault)
    ni.update(path, state=state, attempts="1", session_id="old", reset_at=(NOW - timedelta(hours=1)).isoformat())
    health_at(vault, 0.9, 1)
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["attempts"] == "2"


def test_cancel_and_list(env, capsys):
    vault, tmp = env
    assert add(vault) == 0
    _, fm = only_item(vault)
    assert nr.main(["cancel", fm["id"]], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "cancelled"
    nr.main(["list"], vault, NOW)
    assert "cancelled" in capsys.readouterr().out


def test_lock_held_exits_4(env):
    import fcntl
    vault, tmp = env
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / nr.LOCK, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert nr.main(["tick"], vault, NOW) == 4


GOOD = ["CURL_EXIT=6", "CAT_EXIT=1", "ENV_DONE=1"]   # the three self-test commands, each its own tool result


def selftest_stream(tmp_path, name, results):
    """ok.jsonl with one tool_result event per entry of results in place of its single CURL_EXIT=6 result."""
    lines = (FX / "ok.jsonl").read_text().splitlines()
    events = [json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": r}]}}) for r in results]
    p = tmp_path / name
    p.write_text("\n".join(lines[:2] + events + lines[3:]) + "\n")
    return p


def test_selftest_parses_tool_results(env, monkeypatch, tmp_path):
    vault, tmp = env
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the self-test plants its canary under $HOME
    stub(tmp, STREAM=str(selftest_stream(tmp_path, "good.jsonl", GOOD)))
    assert nr.selftest(vault)[0] is True
    stub(tmp, STREAM=str(selftest_stream(tmp_path, "bad.jsonl", ["CURL_EXIT=0", "CAT_EXIT=1", "ENV_DONE=1"])))
    ok, why = nr.selftest(vault)
    assert ok is False and "curl" in why


def test_selftest_fails_when_the_session_environment_carries_a_token(env, monkeypatch, tmp_path):
    # audit S3/S7 spec §2: the third command prints the names of the token variables that are set, then ENV_DONE
    vault, tmp = env
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    stub(tmp, STREAM=str(selftest_stream(tmp_path, "leak.jsonl", ["CURL_EXIT=6", "CAT_EXIT=1", "GH_TOKEN=\nENV_DONE=0"])))
    assert nr.selftest(vault) == (False, "the session environment carries GH_TOKEN")
    stub(tmp, STREAM=str(selftest_stream(tmp_path, "clean.jsonl", ["CURL_EXIT=6", "CAT_EXIT=1", "ENV_DONE=1"])))
    assert nr.selftest(vault) == (True, "")
    stub(tmp, STREAM=str(selftest_stream(tmp_path, "short.jsonl", ["CURL_EXIT=6", "CAT_EXIT=1"])))
    ok, why = nr.selftest(vault)
    assert ok is False and "did not run" in why
    stub(tmp, STREAM=str(selftest_stream(tmp_path, "broken.jsonl", ["CURL_EXIT=6", "CAT_EXIT=1", "ENV_DONE=2"])))
    ok, why = nr.selftest(vault)   # grep exit 2 is a failed probe, which proves nothing either way
    assert ok is False and "probe" in why and "exit 2" in why
    assert "GH_TOKEN" in nr.SELFTEST_PROMPT and "ENV_DONE=$?" in nr.SELFTEST_PROMPT
    assert {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"} <= set(nr.TOKEN_VARS)


def test_selftest_runs_under_the_production_deny_and_a_start_failure_names_its_cause(env, monkeypatch, tmp_path):
    # review of audit S3/S7: the self-test proves the profile items run under, and a start failure keeps its evidence
    vault, tmp = env
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    profiles, real = [], nr.ss.profile
    monkeypatch.setattr(nr.ss, "profile", lambda *a, **k: profiles.append(real(*a, **k)) or profiles[-1])
    lines = (FX / "ok.jsonl").read_text().splitlines()
    error = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                        "result": "Invalid API key. Please run /login"})
    (tmp_path / "error.jsonl").write_text("\n".join([lines[0], error]) + "\n")
    stub(tmp, STREAM=str(tmp_path / "error.jsonl"))
    ok, why = nr.selftest(vault)
    assert ok is False and "did not start" in why and "Invalid API key. Please run /login" in why
    assert str(vault) in profiles[-1]["sandbox"]["filesystem"]["denyRead"]
    (tmp_path / "empty.jsonl").write_text("")
    stub(tmp, STREAM=str(tmp_path / "empty.jsonl"), SHELL="echo 'OAuth token has expired' >&2")
    ok, why = nr.selftest(vault)
    assert ok is False and why.endswith("OAuth token has expired")


def test_selftest_names_the_env_token_login_when_the_session_does_not_start(env, monkeypatch, tmp_path):
    # owner decision (audit S3/S7 spec §2): a login held only in the unit's environment starts no session
    vault, tmp = env
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    stub(tmp, STREAM=str(empty))
    ok, why = nr.selftest(vault)
    assert ok is False and "CLAUDE_CODE_OAUTH_TOKEN" in why and "ANTHROPIC_API_KEY" in why


def note_of(vault):
    return only_item(vault)[0]


def test_template_clone_holds_no_private_vault_objects(env):
    vault, tmp = env
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
    vault, tmp = env
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
    assert git(clone, "for-each-ref", "--format=%(refname)").split() == [f"refs/heads/order/{fm['id']}", "refs/remotes/base"]


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


def set_workspace(vault, ws):
    cfg = vault / "system/config.md"
    cfg.write_text(cfg.read_text().rsplit("---\n", 1)[0] + f'order_workspace: "{ws}"\n---\n')


def test_add_refuses_a_workspace_inside_the_vault_and_a_tick_fails_a_queued_one(env, capsys):
    # audit S3/S7 spec §2: the deny would cover the session's own working directory
    vault, tmp = env
    assert add(vault, "--now") == 0   # queued while the workspace was outside the vault
    set_workspace(vault, vault / ".scratch" / "ws")
    assert nr.main(["add", "--kind", "plan", "--title", "second", "--partition", "work", "--repo", "template",
                    "--base", "feat/x", "--plan", "docs/p.md", "--tasks", "1-2", "--verify", "true", "--now"], vault, NOW) == 2
    assert "not ready: order_workspace is inside the vault" in capsys.readouterr().out
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert (fm["state"], fm["reason"]) == ("failed", "workspace")
    out = json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "outcome.json").read_text())
    assert out["needs"][0].startswith("Move order_workspace outside the vault")
    assert f"then queue {fm['id']} again" in out["needs"][0]
    assert not (vault / ".scratch" / "ws").exists()


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_vault_master_moving_during_a_run_is_not_a_containment_failure(env, monkeypatch):
    vault, tmp = env
    stub(tmp, SHELL="git add done.txt && git -c user.name=t -c user.email=t@e commit -qm work"
                       f" && git -C {vault} -c user.name=t -c user.email=t@e commit -q --allow-empty -m ingest")
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "done"


def test_resume_stops_a_session_left_running(needs_bwrap, env):
    vault, tmp = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    stale = subprocess.Popen(["sleep", "300"], start_new_session=True)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    (idir / "session.pid").write_text(str(stale.pid))
    ni.update(path, state="running", attempts="1", session_id="old")
    nr.main(["tick"], vault, NOW)
    assert stale.poll() is not None


def test_a_running_item_failed_by_the_reconciler_writes_its_outcome(env):
    """A notice reads outcome.json, so the third failed attempt must write one (#28)."""
    vault, tmp = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    ni.update(path, state="running", attempts="3", session_id="old")
    nr.main(["tick"], vault, NOW)
    assert only_item(vault)[1]["state"] == "failed"
    out = json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "outcome.json").read_text())
    assert out["state"] == "failed" and out["reason"] == "no result"


def test_cancel_stops_a_live_session(env):
    vault, tmp = env
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
    vault, tmp = env
    monkeypatch.setattr(nr, "POLL", 1)
    stub(tmp, SHELL="sleep 4")
    assert add(vault, "--now") == 0
    _, fm = only_item(vault)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    (idir / "elapsed").write_text(str(4 * 3600 - 2))
    assert nr.main(["tick"], vault, NOW) == 1
    assert only_item(vault)[1]["reason"] == "budget"


def test_no_init_event_requeues_with_a_fresh_session(env, monkeypatch, tmp_path):
    vault, tmp = env
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    stub(tmp, STREAM=str(empty))
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
    stub(tmp, STREAM=str(tmp_path / "missing.jsonl"))  # a new session would fail
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
    vault, tmp = env
    from helpers import concept
    write(vault, "wiki/work/concepts/Background.md", concept("work", "Background"))
    note = concept("work", "Answer", "Found it.", provenance='["headless"]').replace("\n", "\\n")
    writes = tmp_path / "rw.txt"
    writes.write_text(f'out/Answer.md={note}\nout/result.json={{"status": "done", "summary": "ok", "questions": []}}\n')
    stub(tmp, WRITE=str(writes))
    stub(tmp, SHELL="test -f context/concepts/Background.md")
    stub(tmp, ARGS=str(tmp_path / "args.txt"))
    shutil.copy(FX / "ok.jsonl", tmp_path / "r.jsonl")
    (tmp_path / "r.jsonl").write_text((FX / "ok.jsonl").read_text().replace(
        '"tools":["Read","Glob","Grep","Edit","Write","Bash","Skill","Agent","TodoWrite"]', '"tools":["Read","Write"]'))
    stub(tmp, STREAM=str(tmp_path / "r.jsonl"))
    brief = tmp_path / "brief.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", "q", "--partition", "work", "--brief-file", str(brief),
                    "--output", "wiki/work/concepts/Answer.md", "--now"], vault, NOW) == 0
    assert nr.main(["tick"], vault, NOW) == 0
    assert only_item(vault)[1]["state"] == "done"
    assert (vault / "wiki/work/concepts/Answer.md").is_file()
    assert "--add-dir" not in (tmp_path / "args.txt").read_text()
    out = json.loads((vault / "system/logs/nightshift/items" / only_item(vault)[1]["id"] / "outcome.json").read_text())
    assert out["output"] == "wiki/work/concepts/Answer.md"  # the notice links the item's own note (#157)


def test_an_item_finishes_after_it_starts(env, tmp_path):
    # Both stamps came from the tick's one clock reading, so every report row read "07:00–07:00" (live vault, 31 of 31).
    vault, tmp = env
    note = __import__("helpers").concept("work", "Answer", "Found it.", provenance='["headless"]').replace("\n", "\\n")
    writes = tmp_path / "rw.txt"
    writes.write_text(f'out/Answer.md={note}\nout/result.json={{"status": "done", "summary": "ok", "questions": []}}\n')
    stub(tmp, WRITE=str(writes), SHELL="sleep 0.2")
    (tmp_path / "r.jsonl").write_text((FX / "ok.jsonl").read_text().replace(
        '"tools":["Read","Glob","Grep","Edit","Write","Bash","Skill","Agent","TodoWrite"]', '"tools":["Read","Write"]'))
    stub(tmp, STREAM=str(tmp_path / "r.jsonl"))
    brief = tmp_path / "brief.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", "q", "--partition", "work", "--brief-file", str(brief),
                    "--output", "wiki/work/concepts/Answer.md", "--now"], vault, NOW) == 0
    assert nr.main(["tick"], vault, NOW) == 0
    fm = only_item(vault)[1]
    assert fm["state"] == "done"
    assert datetime.fromisoformat(fm["finished_at"]) > datetime.fromisoformat(fm["started_at"])
    out = json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "outcome.json").read_text())
    assert out["started_at"] == fm["started_at"]
    assert datetime.fromisoformat(out["finished_at"]) > datetime.fromisoformat(out["started_at"])


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


def test_a_run_denies_the_vault_root_and_not_only_its_four_folders(needs_bwrap, env):
    # audit S3/S7 spec §2: the clone, context/ and out/ live under order_workspace, so a session needs nothing from the vault
    vault, tmp = env
    assert add(vault, "--now") == 0
    nr.main(["tick"], vault, NOW)
    _, fm = only_item(vault)
    settings = json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "settings.json").read_text())
    deny = settings["sandbox"]["filesystem"]["denyRead"]
    assert str(vault) in deny
    assert not any(d.startswith(str(vault) + "/") for d in deny)   # the root alone, none of the four folders
    assert f"Read(//{str(vault).lstrip('/')}/**)" in settings["permissions"]["deny"]


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


@pytest.mark.skipif(not shutil.which("git-lfs"), reason="git-lfs not installed")
def test_research_copy_of_an_lfs_codebase_holds_the_files(env, tmp_path, monkeypatch):
    vault, tmp = env
    from test_nightshift_deliver import lfs_repo
    src = lfs_repo(tmp_path / "cb" / "shop", monkeypatch)
    git(src, "update-ref", "refs/remotes/origin/HEAD", "HEAD")   # research reads the remote's default branch
    write(vault, "system/codebases/shop.md", f'---\ntype: codebase\nname: "shop"\npath: "{src}"\npartition: "work"\n'
          'search_globs: ["*"]\n---\n')
    ctx = nr.Ctx(vault, NOW)
    fm = {"id": "2026-10-09-q", "kind": "research", "partition": "work", "repo": "shop"}
    code = nr._research_dir(ctx, fm) / "code"
    assert (code / "a.png").read_bytes() == b"PNGDATA\n"
    assert "lfs.storage" not in git(code, "config", "--list", "--local")   # no link to the live clone (#77)
    (code / "a.png").unlink()   # a resumed attempt checks the copy out again
    assert (nr._research_dir(ctx, fm) / "code" / "a.png").read_bytes() == b"PNGDATA\n"


@pytest.mark.skipif(not shutil.which("git-lfs"), reason="git-lfs not installed")
def test_research_reads_a_pointer_for_an_lfs_file_the_live_clone_never_downloaded(env, tmp_path, monkeypatch):
    vault, tmp = env
    from test_nightshift_deliver import lfs_repo
    src = lfs_repo(tmp_path / "cb" / "shop", monkeypatch)
    (src / "b.png").write_bytes(b"NEWPNG\n")   # a commit fetched but never checked out: its object is not in the store
    git(src, "add", "b.png")
    git(src, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "b")
    oid = git(src, "show", "HEAD:b.png").split("sha256:")[1].split()[0]
    (src / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4] / oid).unlink()
    git(src, "update-ref", "refs/remotes/origin/HEAD", "HEAD")
    write(vault, "system/codebases/shop.md", f'---\ntype: codebase\nname: "shop"\npath: "{src}"\npartition: "work"\n'
          'search_globs: ["*"]\n---\n')
    code = nr._research_dir(nr.Ctx(vault, NOW), {"id": "2026-10-09-q", "kind": "research", "partition": "work", "repo": "shop"}) / "code"
    assert (code / "a.png").read_bytes() == b"PNGDATA\n"
    assert (code / "b.png").read_text().startswith("version https://git-lfs.github.com/spec/v1")


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
    writes.write_text(f"done.txt=yes\n.nightshift/protected/claude/skills/demo/SKILL.md=hello\\n\n"
                      f".nightshift/result.json={RESULT}\n")
    stub(tmp, WRITE=str(writes))
    assert add(vault, "--now") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    branch = git(tmp / "remote.git", "branch", "--list").split()[-1]
    assert git(tmp / "remote.git", "show", f"{branch}:.claude/skills/demo/SKILL.md") == "hello\n"
    assert git(tmp / "remote.git", "show", f"{branch}:done.txt") == "yes"


def codebase_item(vault, tmp_path, verify, **keys):
    """A plan item on a registered codebase (shop, main) whose file carries order_pr and the given keys."""
    from test_nightshift_check import registered, set_codebase
    registered(vault, tmp_path / "cb")
    set_codebase(vault, "shop", order_pr="github:o/shop", **keys)
    args = [a for v in verify for a in ("--verify", v)]
    assert nr.main(["add", "--kind", "plan", "--title", "shop work", "--partition", "work", "--repo", "shop",
                    "--base", "main", "--plan", "docs/p.md", "--tasks", "1-2", *args, "--now"], vault, NOW) == 0


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_codebase_item_runs_its_install_before_verify_and_the_session_sees_the_toolchain(env, monkeypatch, tmp_path):
    """Orders toolchain spec §2: order_install runs first in the verify checkout; the session's PATH starts with the
    order_toolchain directories (owner decision 2026-10-14)."""
    vault, tmp = env
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "hello-tool").write_text("#!/bin/sh\necho hi\n")
    (tools / "hello-tool").chmod(0o755)
    stub(tmp, SHELL=f'echo "$PATH" > {tmp_path}/path.txt && git add done.txt && '
                    "git -c user.name=t -c user.email=t@e commit -qm work")
    codebase_item(vault, tmp_path, ["test -f done.txt", "test -f installed"], order_toolchain=[str(tools)],
                  order_install="hello-tool > installed")
    assert nr.main(["tick"], vault, NOW) == 0
    _, fm = only_item(vault)
    assert fm["state"] == "done", fm
    log = (vault / "system/logs/nightshift/items" / fm["id"] / "verify.log").read_text()
    assert log.index("$ hello-tool > installed\n") < log.index("$ test -f done.txt\n")
    assert (tmp_path / "path.txt").read_text().startswith(f"{tools}:")


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_corepack_download_from_the_install_reaches_the_sealed_verify(env, monkeypatch, tmp_path):
    """#189 (orders corepack home spec §2): the package manager order_install stores under COREPACK_HOME is the one
    the offline verify runs, so the item is delivered."""
    from test_nightshift_deliver import corepack_tool
    vault, tmp = env
    tools = corepack_tool(tmp_path / "tools")
    codebase_item(vault, tmp_path, ["test -f done.txt", "corepack-pm run"], order_toolchain=[str(tools)],
                  order_install="corepack-pm install")
    assert nr.main(["tick"], vault, NOW) == 0
    _, fm = only_item(vault)
    assert fm["state"] == "done", fm


def test_a_research_session_on_the_same_codebase_keeps_its_own_path(env, monkeypatch, tmp_path):
    """Orders toolchain spec §2: the toolchain leads the plan session's PATH; a research item has no verify to match."""
    vault, tmp = env
    from test_nightshift_check import registered, set_codebase
    registered(vault, tmp_path / "cb")
    tools = tmp_path / "tools"
    tools.mkdir()
    set_codebase(vault, "shop", order_toolchain=[str(tools)])
    empty = tmp_path / "none.txt"
    empty.write_text("")
    stub(tmp, WRITE=str(empty), SHELL=f'echo "$PATH" > {tmp_path}/path.txt')
    brief = tmp_path / "brief.md"
    brief.write_text("## Question\nQ\n## Scope\nCode.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", "q", "--partition", "work", "--brief-file", str(brief),
                    "--output", "wiki/work/concepts/Answer.md", "--repo", "shop", "--now"], vault, NOW) == 0
    nr.main(["tick"], vault, NOW)
    assert (tmp_path / "path.txt").read_text().strip() == os.environ["PATH"]   # the service PATH, unchanged


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_toolchain_dir_gone_at_run_time_blocks_before_the_session_starts(env, monkeypatch, tmp_path):
    """Orders toolchain spec §2: an nvm upgrade or a client's paths can remove a directory between queue and run; the
    item blocks with the readiness wording before any budget is spent, instead of bwrap blaming the first command."""
    vault, tmp = env
    tools = tmp_path / "tools"
    tools.mkdir()
    stub(tmp, SHELL=f"touch {tmp_path}/session-ran")
    codebase_item(vault, tmp_path, ["test -f done.txt"], order_toolchain=[str(tools)])
    tools.rmdir()
    assert nr.main(["tick"], vault, NOW) == 1
    _, fm = only_item(vault)
    assert (fm["state"], fm["reason"]) == ("blocked", "toolchain"), fm
    out = json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "outcome.json").read_text())
    assert out["needs"] == [f"codebase shop: order_toolchain {tools} is not a directory"]
    assert not (tmp_path / "session-ran").exists()


def test_selftest_retries_when_the_model_declines(env, monkeypatch, tmp_path):
    vault, tmp = env
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the self-test plants its canary under $HOME
    declined = selftest_stream(tmp_path, "declined.jsonl", ["no"])
    good = selftest_stream(tmp_path, "good.jsonl", GOOD)
    stream = tmp_path / "s.jsonl"
    shutil.copy(declined, stream)
    stub(tmp, STREAM=str(stream))
    stub(tmp, SHELL=f"if [ -f {tmp_path}/once ]; then cp {good} {stream}; else touch {tmp_path}/once; fi")
    assert nr.selftest(vault)[0] is True
    shutil.copy(declined, stream)
    stub(tmp, SHELL="true")
    ok, why = nr.selftest(vault)
    assert ok is False and "did not run" in why


def test_selftest_prompt_says_failures_are_expected():
    assert "expected" in nr.SELFTEST_PROMPT and "self-test" in nr.SELFTEST_PROMPT
    assert nr.CANARY in nr.SELFTEST_PROMPT and ".ssh" not in nr.SELFTEST_PROMPT


def test_selftest_plants_a_canary_and_fails_if_the_session_reads_it(env, monkeypatch, tmp_path):
    vault, tmp = env
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    canary = home / ".config" / "foundry" / "nightshift-canary"
    stream = selftest_stream(tmp_path, "s.jsonl", GOOD)
    stub(tmp, STREAM=str(stream))
    # A masked sandbox: the canary exists while the session runs, the read fails, and the canary is gone afterwards.
    stub(tmp, SHELL=f"test -s {canary} && touch {tmp_path}/seen")
    assert nr.selftest(vault) == (True, "")
    assert (tmp_path / "seen").exists() and not canary.exists()
    # An unmasked sandbox: the session's output carries the canary's content, even with a non-zero exit code.
    line = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "LEAK CAT_EXIT=1"}]}})
    leak = tmp_path / "leak.sh"
    leak.write_text(f"echo '{line}' | sed \"s/LEAK/$(cat {canary})/\" >> {stream}\n")
    stub(tmp, SHELL=f"bash {leak}")
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


def test_a_clone_made_before_the_rename_delivers_its_nightshift_branch(env, monkeypatch):
    vault, tmp = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    ctx = nr.Ctx(vault, NOW)
    clone = nr._clone(ctx, fm)
    git(clone, "branch", "-m", f"nightshift/{fm['id']}")   # an item already running when the vault updated
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    before = nr._before(ctx, fm, idir)
    (clone / "done.txt").write_text("yes")
    git(clone, "add", "done.txt")
    git(clone, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "work")
    (clone / ".nightshift").mkdir()
    (clone / ".nightshift" / "result.json").write_text(RESULT)
    monkeypatch.setattr(nr.nd, "verify_sha", lambda *a: (True, ""))
    assert nr._deliver_plan(ctx, fm, clone, idir, before)["state"] == "done"
    assert f"nightshift/{fm['id']}" in git(tmp / "remote.git", "branch", "--list")



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


def run_research_with_denials(env, tmp_path, writes_text, denied):
    """A research item whose stub writes writes_text and whose result event denies a Write at each path in denied
    (relative to the item's workspace directory, which the stub fills in at run time). Returns (fm, outcome)."""
    vault, tmp = env
    writes = tmp_path / "rw.txt"
    writes.write_text(writes_text)
    head = (FX / "ok.jsonl").read_text().replace(
        '"tools":["Read","Glob","Grep","Edit","Write","Bash","Skill","Agent","TodoWrite"]', '"tools":["Read","Write"]')
    res = {"type": "result", "subtype": "success", "is_error": False, "permission_denials": [
        {"tool_name": "Write", "tool_use_id": f"t{i}", "tool_input": {"file_path": f"@W@/{p}", "content": "x"}}
        for i, p in enumerate(denied)]}
    tpl, stream = tmp_path / "r.tpl", tmp_path / "r.jsonl"
    tpl.write_text("".join(f"{l}\n" for l in head.splitlines()[:-1]) + json.dumps(res) + "\n")
    stub(tmp, WRITE=str(writes), STREAM=str(stream), SHELL=f'sed "s#@W@#$PWD#g" "{tpl}" > "{stream}"')
    brief = tmp_path / "brief.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", "q", "--partition", "work", "--brief-file", str(brief),
                    "--output", "wiki/work/concepts/Answer.md", "--now"], vault, NOW) == 0
    nr.main(["tick"], vault, NOW)
    fm = only_item(vault)[1]
    return fm, json.loads((vault / "system/logs/nightshift/items" / fm["id"] / "outcome.json").read_text())


def test_research_out_write_denied_is_its_own_reason(env, tmp_path):
    # #314: the session's Write to out/ was denied, out/ stayed empty, and the item said only "no result"
    fm, out = run_research_with_denials(env, tmp_path, "", ["out/Answer.md"])
    assert (fm["state"], fm["reason"]) == ("failed", "out write denied")
    assert "out/Answer.md" in out["needs"][0] and "stream.jsonl" in out["needs"][0]


def test_research_no_write_and_no_denial_is_no_result(env, tmp_path):
    fm, out = run_research_with_denials(env, tmp_path, "", [])
    assert (fm["state"], fm["reason"]) == ("failed", "no result")


def test_research_denial_outside_out_is_no_result(env, tmp_path):
    fm, out = run_research_with_denials(env, tmp_path, "", ["code/out/Answer.md"])
    assert fm["reason"] == "no result"


def test_research_result_json_denied_names_it(env, tmp_path):
    note = __import__("helpers").concept("work", "Answer", "Found it.", provenance='["headless"]').replace("\n", "\\n")
    fm, out = run_research_with_denials(env, tmp_path, f"out/Answer.md={note}\n", ["out/result.json"])
    assert fm["reason"] == "out write denied" and "out/result.json" in out["needs"][0]


# --- #298: the tick screens what it runs, when it runs it ------------------------------------------------

def add_research(vault, tmp, *extra):
    brief = tmp / "brief.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", "q", "--partition", "work", "--brief-file", str(brief),
                    "--output", "wiki/work/concepts/Answer.md", "--host", "docs.example.com", "--now", *extra],
                   vault, NOW) == 0
    return only_item(vault)


def refused_at_tick(vault, path, fm, prefix):
    assert nr.main(["tick"], vault, NOW) == 2
    now, _ = ni.load(path)
    assert now["state"] == "failed" and now["reason"].startswith(prefix), now
    assert not (vault / "system/logs/nightshift/items" / fm["id"] / "settings.json").exists()   # no session ran
    alerts = "".join(p.read_text() for p in (vault / "system" / "logs").glob("alerts_*.md"))
    assert f"[orders] {path.name} refused: " in alerts
    assert nr.main(["tick"], vault, NOW) == 0   # refused once; the next tick skips it


@pytest.mark.parametrize("host", ["*", "169.254.169.254"])
def test_a_hosts_edit_after_add_is_refused_at_the_tick(env, host):
    vault, tmp = env
    path, fm = add_research(vault, tmp)
    ni.update(path, hosts=["docs.example.com", host])
    refused_at_tick(vault, path, fm, "invalid: host")


def test_an_output_edit_after_add_is_refused_and_never_written(env):
    vault, tmp = env
    path, fm = add_research(vault, tmp)
    ni.update(path, output="docs/injected.md")
    refused_at_tick(vault, path, fm, "invalid: output")
    assert not (vault / "docs/injected.md").exists()


@pytest.mark.parametrize("edit,prefix", [
    ({"output": "extensions/telemetry/skills/evil/SKILL.md"}, "invalid: output"),
    ({"output": "wiki/personal/concepts/X.md"}, "invalid: output"),
    ({"output": "wiki/work/private/X.md"}, "invalid: output"),
    ({"output": "wiki/work/meetings/X.md"}, "invalid: output"),
    ({"partition": "personal", "output": "wiki/personal/concepts/X.md"}, "invalid: partition personal")])
def test_outputs_outside_the_three_folders_and_a_moved_partition_are_refused_at_the_tick(env, edit, prefix):
    vault, tmp = env
    path, fm = add_research(vault, tmp)
    ni.update(path, **edit)
    refused_at_tick(vault, path, fm, prefix)


def test_a_blocked_note_keeps_the_identifiers_screen_only(env):
    # A parked order never runs, and flipping it back to queued screens it in full (spec §6).
    vault, tmp = env
    path, fm = add_research(vault, tmp)
    ni.update(path, state="blocked", output="docs/x.md")
    assert nr.main(["tick"], vault, NOW) == 0
    assert ni.load(path)[0]["state"] == "blocked"


def test_the_loop_screen_leaves_a_note_a_worker_holds(env):
    # ni.update is read-modify-write with no lock: marking a running note would race the worker's _finish.
    vault, tmp = env
    path, fm = add_research(vault, tmp)
    ni.update(path, state="running", hosts=["*"])
    entries, refused = nr._screen(nr.Ctx(vault, NOW), {fm["id"]: None})
    assert [e[0] for e in entries] == [path] and refused == []
    assert ni.load(path)[0]["state"] == "running"


RFM = {"id": "2026-10-08-q", "kind": "research", "partition": "work", "output": "wiki/work/concepts/Answer.md"}


def test_research_context_holds_background_notes_only(env, tmp_path):
    vault, tmp = env
    from helpers import concept
    outside = tmp_path / "outside.md"
    outside.write_text("secret outside the vault\n")
    write(vault, "wiki/work/concepts/Background.md", concept("work", "Background"))
    write(vault, "wiki/work/private/Secret.md", "private\n")
    write(vault, "wiki/work/Now.md", "- [ ] owed: x\n")
    write(vault, "wiki/work/meetings/M.md", "transcript\n")
    write(vault, "wiki/work/preferences/P.md", "pref\n")
    (vault / "wiki/work/concepts/Link.md").symlink_to(outside)
    ctx = nr.Ctx(vault, NOW)
    c = nr._research_dir(ctx, RFM) / "context"
    files = {str(p.relative_to(c)) for p in c.rglob("*") if p.is_file()}
    assert "concepts/Background.md" in files and {f.split("/")[0] for f in files} <= {"concepts", "entities", "summaries"}
    assert not (c / "concepts/Link.md").exists() and not (c / "concepts/Link.md").is_symlink()


def test_a_resumed_order_loses_a_context_built_before_the_fix(env):
    vault, tmp = env
    write(vault, "wiki/work/concepts/Background.md", "x\n")
    d = tmp / "ws" / f"nightshift-{RFM['id']}"
    write(d, "context/private/Secret.md", "copied by the old runner\n")
    nr._research_dir(nr.Ctx(vault, NOW), RFM)
    assert not (d / "context/private").exists() and (d / "context/concepts/Background.md").is_file()


def test_a_context_replaced_by_a_link_is_unlinked_and_its_target_kept(env, tmp_path):
    vault, tmp = env
    write(vault, "wiki/work/concepts/Background.md", "x\n")
    target = tmp_path / "elsewhere"
    write(target, "keep.md", "kept\n")
    d = tmp / "ws" / f"nightshift-{RFM['id']}"
    d.mkdir(parents=True)
    (d / "context").symlink_to(target)
    nr._research_dir(nr.Ctx(vault, NOW), RFM)
    assert (target / "keep.md").is_file() and not (target / "concepts").exists()
    assert not (d / "context").is_symlink() and (d / "context/concepts/Background.md").is_file()


@pytest.mark.parametrize("linked", ["file", "folder"])
def test_a_linked_research_output_is_refused(env, tmp_path, linked):
    # A session can ln -s out/<name> (or out/) to a note it cannot read; the runner reads it outside the sandbox.
    vault, tmp = env
    write(vault, "wiki/work/private/Secret.md", __import__("helpers").concept("work", "Answer", "secret"))
    d = tmp / "ws" / "nightshift-x"
    if linked == "file":
        write(d, "out/result.json", '{"status": "done", "summary": "ok"}')
        (d / "out/Answer.md").symlink_to(vault / "wiki/work/private/Secret.md")
    else:
        write(vault, "wiki/work/private/result.json", '{"status": "done", "summary": "ok"}')
        d.mkdir(parents=True)
        (d / "out").symlink_to(vault / "wiki/work/private")
        (vault / "wiki/work/private/Answer.md").write_text((vault / "wiki/work/private/Secret.md").read_text())
    out = nr._deliver_research(nr.Ctx(vault, NOW), RFM, d)
    assert out == {"state": "failed", "reason": "invalid: output is a link"}
    assert not (vault / "wiki/work/concepts/Answer.md").exists()
    alerts = "".join(p.read_text() for p in (vault / "system" / "logs").glob("alerts_*.md"))
    assert alerts.count(f"{RFM['id']}: the research output is a link") == 1


def test_delivery_after_a_repo_edit_pushes_to_the_recorded_repo(env, monkeypatch, tmp_path):
    # A retry reads the note again; a repo swapped while the order sits in delivering must not redirect the push.
    vault, tmp = env
    from test_nightshift_check import registered
    registered(vault, tmp_path / "cb")   # shop, a work codebase with its own origin
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    ctx = nr.Ctx(vault, NOW)
    clone = nr._clone(ctx, fm)
    idir = vault / "system/logs/nightshift/items" / fm["id"]
    idir.mkdir(parents=True)
    before = nr._before(ctx, fm, idir)
    (clone / "done.txt").write_text("yes")
    git(clone, "add", "done.txt")
    git(clone, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "work")
    (clone / ".nightshift").mkdir()
    (clone / ".nightshift" / "result.json").write_text(RESULT)
    monkeypatch.setattr(nr.nd, "verify_sha", lambda *a: (True, ""))
    urls, bases = [], []
    monkeypatch.setattr(nr.nd, "push", lambda runner, sha, branch, url: (urls.append(url), (len(urls) > 1, "log"))[1])
    monkeypatch.setattr(nr.nd, "open_pr", lambda pr, branch, base, *a: (bases.append(base), (True, "https://x/pull/1"))[1])
    assert nr._deliver_plan(ctx, fm, clone, idir, before)["state"] == "delivering"
    edited = ni.update(path, repo="shop", pr_base="main")
    assert nr._deliver(ctx, edited, idir)["state"] == "done"
    assert urls == [str(tmp / "remote.git")] * 2 and bases == ["master"]
