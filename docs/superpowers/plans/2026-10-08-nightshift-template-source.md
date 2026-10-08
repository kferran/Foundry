# Nightshift Template Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Nightshift `template` item's base branch and plan are read from `template_remote`, at queue time and at run time, never from the vault; a failure to read it is reported plainly and ends the item at once.

**Architecture:** `nightshift_check` gains `remote_git(url)`, `shown(url)` and `fetch_base(...)` (refuses a URL starting with `-`, has a timeout). The readiness check fetches the base one commit deep into a temporary bare repository and runs the plan checks there (`_plan_at`); `source(vault, "template")` returns `None`. The runner's `_clone` fetches the base from the remote, rebuilds a half-built clone and raises `CloneError` on failure; `run_item` turns that into a `failed (base)` outcome with a Needs-you line; `_before` reads `base_sha` from the clone. `nightshift_deliver.push` uses `remote_git` and refuses an option-like URL.

**Tech Stack:** Python 3.11, git, pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-nightshift-template-source-design.md` (rev 2)

## Global Constraints

- Work on branch `fix/nightshift-template-source` of `kferran/Foundry`. Commit there; do not push or open a pull request.
- Codebase items are unchanged: they read their registered clone.
- Nothing reads a template item's base or plan from the vault.
- A local bare repository stands in for the template remote in tests; no test uses the network.
- Run the Nightshift suites as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch python3 -m pytest system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_report.py -q` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (those four suites) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- Every `nc.source` caller handles `None` for a template item: `_before` (reads the clone), `_deliver_plan` and `_deny` (skip template), `push_target` (template branch first). Pinned by the `base_sha` assertion in `test_delivery_runs_no_git_inside_the_session_clone` and, where bwrap exists, by `test_verify_failure_blocks_without_push` (`blocked`, `no commits`).
- A fetch failure at run time ends the item on its first tick with a report row and a Needs-you line: `test_a_template_base_gone_from_the_remote_fails_at_once_with_a_needs_you_line`.
- A network or auth failure at queue time is not reported as a missing branch: `test_an_unreadable_template_remote_is_not_a_missing_branch`.
- A `template_remote` such as `--upload-pack=…` never reaches git: `test_a_template_remote_that_looks_like_an_option_is_refused`; `push` refuses it too.
- A half-built clone is rebuilt, and a failed fetch leaves no clone: `test_a_failed_fetch_leaves_no_clone_and_a_half_built_one_is_rebuilt`.

---

### Task 1: Read template items from the template remote

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/vaultlib/nightshift_deliver.py`, `.claude/skills/nightshift/SKILL.md`, `README.md`, `docs/superpowers/specs/2026-10-06-nightshift-design.md`, `docs/superpowers/roadmap.md`
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `nightshift_check.remote_git(url) -> (list, dict)`, `nightshift_check.shown(url) -> str`, `nightshift_check.fetch_base(repo, url, base, dest, depth=None, timeout=600) -> CompletedProcess` (raises `ValueError` for a URL starting with `-`), `nightshift_check.source(vault, "template") -> None`, `nightshift_run.CloneError`.

- [ ] **Step 1: Write the failing tests**

Edit 1 in `system/tests/python/test_nightshift_check.py`. Find:

````text
def vault_repo(vault: Path) -> Path:
````

Replace with:

````text
def vault_repo(vault: Path, tmp_path: Path) -> Path:
````

Edit 2 in `system/tests/python/test_nightshift_check.py`. Find:

````text
    git(vault, "branch", "feat/x")
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "https://github.com/o/r.git"\n---\n')
````

Replace with:

````text
    remote = tmp_path / "remote.git"   # a local bare repository stands in for the template remote
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(vault, "push", "-q", str(remote), "HEAD:refs/heads/feat/x")   # the base exists only on the remote
    write(vault, "system/config.md", f'---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "{remote}"\n---\n')
````

Edit 3 in `system/tests/python/test_nightshift_check.py`. Find:

````text
    assert any("9" in e for e in errs)
````

Replace with:

````text
    assert any(e.startswith("tasks not in the plan") and e.endswith("9") for e in errs)
````

Edit 4 in `system/tests/python/test_nightshift_check.py`. Find:

````text
    assert any("budget" in e for e in errs)
````

Replace with:

````text
    assert any("budget" in e for e in errs)


def test_template_base_must_be_on_the_template_remote(vault_repo):
    git(vault_repo, "branch", "only-here")   # in the vault, never pushed
    errs = nc.check(vault_repo, plan_fm(base="only-here", tasks="1-2"), "")
    assert any("base only-here is not on the template remote" in e and "push it first" in e for e in errs)
    assert nc.source(vault_repo, "template") is None


def test_template_without_template_remote_fails_before_any_fetch(vault_repo, monkeypatch):
    monkeypatch.setattr(nc, "fetch_base", lambda *a, **k: pytest.fail("fetched"))
    write(vault_repo, "system/config.md", '---\ntype: config\ntimezone: "UTC"\n---\n')
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == ["config has no template_remote"]


def test_an_unreadable_template_remote_is_not_a_missing_branch(vault_repo, tmp_path):
    write(vault_repo, "system/config.md", f'---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "{tmp_path / "gone.git"}"\n---\n')
    errs = nc.check(vault_repo, plan_fm(tasks="1-2"), "")
    assert any(e.startswith("cannot read the template remote") for e in errs)
    assert not any("push it first" in e for e in errs)


def test_a_template_remote_that_looks_like_an_option_is_refused(vault_repo, monkeypatch):
    monkeypatch.setattr(nc, "fetch_base", lambda *a, **k: pytest.fail("fetched"))
    write(vault_repo, "system/config.md", '---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "--upload-pack=touch x"\n---\n')
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == ["template_remote must be a URL or a path"]


def test_remote_git_uses_gh_credentials_for_github_https_only():
    opts, env = nc.remote_git("https://github.com/o/r.git")
    assert "credential.helper=!gh auth git-credential" in opts and env["GIT_TERMINAL_PROMPT"] == "0"
    assert nc.remote_git("/srv/r.git")[0] == []
    assert nc.shown("https://user:tok@github.com/o/r.git") == "https://github.com/o/r.git"
````


Edit 1 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    git(tmp_path, "init", "-q", "--bare", str(remote))
````

Replace with:

````text
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(vault, "push", "-q", str(remote), "feat/x")   # template items are read from the template remote
````

Edit 2 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert fm["state"] in ("blocked", "failed") and fm["reason"] in ("verify", "no commits")
    assert git(tmp / "remote.git", "branch", "--list").strip() == ""
````

Replace with:

````text
    assert (fm["state"], fm["reason"]) == ("blocked", "no commits")
    assert git(tmp / "remote.git", "branch", "--list", "nightshift/*").strip() == ""
````

Edit 3 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists()


````

Replace with:

````text
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


````

Edit 4 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    shutil.rmtree(tmp / "remote.git")
````

Replace with:

````text
    hook = tmp / "remote.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")   # the remote refuses pushes; the check and the clone still fetch
    hook.chmod(0o755)
````

Edit 5 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    git(tmp, "init", "-q", "--bare", str(tmp / "remote.git"))
````

Replace with:

````text
    hook.unlink()
````

Edit 6 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    before = nr._before(ctx, fm, idir)
````

Replace with:

````text
    before = nr._before(ctx, fm, idir)
    assert before["base_sha"] == git(tmp / "remote.git", "rev-parse", "feat/x").strip()
````


- [ ] **Step 2: Run them to verify they fail**

Run: the suite command from Global Constraints.
Expected: FAIL, `11 failed, 67 passed`. The check tests fail because the old check reads the vault (the fixture's base now lives only on the remote) or lacks `fetch_base`, `shown` and the new messages; `test_template_clone_comes_from_the_template_remote`, `test_a_failed_fetch_leaves_no_clone_and_a_half_built_one_is_rebuilt` and `test_a_template_base_gone_from_the_remote_fails_at_once_with_a_needs_you_line` fail because the old clone reads the vault. The `base_sha` assertion and the exact `no commits` assertion pass on the old code (which reads the vault correctly); they guard against a change that breaks `_before`.

- [ ] **Step 3: The check reads the template remote**

Edit 1 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
import re
import subprocess
````

Replace with:

````text
import os
import re
import subprocess
import tempfile
````

Edit 2 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    if repo == "template":
        return Path(vault)
````

Replace with:

````text
    """A codebase's registered clone. A template item has none: it is read from template_remote, never the vault."""
    if repo == "template":
        return None
````

Edit 3 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
````

Replace with:

````text
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def remote_git(url: str) -> tuple:
    """git -c options and environment for talking to a remote: no prompts; the gh credential helper for GitHub HTTPS."""
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    opts = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"] \
        if url.startswith("https://github.com/") else []
    return opts, env


def shown(url: str) -> str:
    """The URL without any user:password@ part, for messages and logs."""
    return re.sub(r"//[^/@]+@", "//", url)


def fetch_base(repo, url: str, base: str, dest: str, depth: int | None = None, timeout: int = 600):
    """Fetch refs/heads/<base> from url into repo as dest. A URL that starts with "-" is refused: git reads it as an option."""
    if url.startswith("-"):
        raise ValueError("template_remote must be a URL or a path")
    opts, env = remote_git(url)
    cmd = ["git", "-C", str(repo), *opts, "fetch", "-q", "--no-tags", *(["--depth", str(depth)] if depth else []),
           url, f"refs/heads/{base}:{dest}"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {timeout}s")
````

Edit 4 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    repo, base, plan = fm.get("repo", ""), fm.get("base", ""), fm.get("plan", "")
````

Replace with:

````text
    repo, base = fm.get("repo", ""), fm.get("base", "")
    errs = [] if fm.get("verify") else ["verify needs at least one command"]
    if repo == "template":
        url = str(config(vault).get("template_remote") or "")
        if not url:
            return ["config has no template_remote"]
        if url.startswith("-"):
            return ["template_remote must be a URL or a path"]
        if not base:
            return errs + ["base (empty) must name a branch on the template remote"]
        with tempfile.TemporaryDirectory(prefix="nightshift-check-") as tmp:   # the base and plan, read from the remote
            subprocess.run(["git", "init", "-q", "--bare", tmp], check=True, capture_output=True)
            f = fetch_base(tmp, url, base, f"refs/heads/{base}", depth=1, timeout=120)
            if f.returncode and "couldn't find remote ref" in f.stderr:
                return errs + [f"base {base} is not on the template remote {shown(url)} (push it first)"]
            if f.returncode:
                why = (f.stderr.strip().splitlines() or ["no error text"])[-1]
                return errs + [f"cannot read the template remote {shown(url)}: {why}"]
            return errs + _plan_at(tmp, fm)
````

Edit 5 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    errs = []
    if repo != "template" and not (codebase(vault, repo) or {}).get("nightshift_pr"):
        errs.append(f"codebase {repo} has no nightshift_pr (github:<owner>/<repo> or bitbucket-link)")
    if repo == "template" and not config(vault).get("template_remote"):
        errs.append("config has no template_remote")
    if not fm.get("verify"):
        errs.append("verify needs at least one command")
    if not base or git(src, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode:
        return errs + [f"base {base or '(empty)'} does not resolve in {src}"]
````

Replace with:

````text
    if not (codebase(vault, repo) or {}).get("nightshift_pr"):
        errs.append(f"codebase {repo} has no nightshift_pr (github:<owner>/<repo> or bitbucket-link)")
    if not base or git(src, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode:
        return errs + [f"base {base or '(empty)'} does not resolve in {src}"]
    return errs + _plan_at(src, fm)


def _plan_at(src, fm: dict) -> list:
    """Checks on the plan committed at the item's base in src."""
    base, plan, errs = fm.get("base", ""), fm.get("plan", ""), []
````


- [ ] **Step 4: The clone, the run and the push use the template remote**

Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
def _clone(ctx: Ctx, fm: dict) -> Path:
    src = nc.source(ctx.vault, fm["repo"])
    clone = ctx.workspace / f"nightshift-{fm['id']}"
    if clone.exists():
        return clone
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    branch = f"nightshift/{fm['id']}"
    if fm["repo"] == "template":
        # The vault's object store holds private notes: copy only what the base reaches, with no alternates.
        ref = nc.git(src, "rev-parse", "--symbolic-full-name", fm["base"]).stdout.strip() or fm["base"]
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "fetch", "-q", "--no-tags", str(src), f"{ref}:refs/remotes/base"], check=True)
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", branch, "refs/remotes/base"], check=True)
    else:
````

Replace with:

````text
class CloneError(RuntimeError):
    """A template item's base could not be fetched from the template remote."""


def _clone(ctx: Ctx, fm: dict) -> Path:
    clone = ctx.workspace / f"nightshift-{fm['id']}"
    template = fm["repo"] == "template"
    if clone.exists():
        if not template or nc.git(clone, "rev-parse", "--verify", "--quiet", "refs/remotes/base").returncode == 0:
            return clone
        shutil.rmtree(clone)   # half-built by a killed tick: start again
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    branch = f"nightshift/{fm['id']}"
    if template:
        # From the template remote, never the vault: the vault's object store holds private notes.
        url = str(nc.config(ctx.vault).get("template_remote") or "")
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        try:
            f = nc.fetch_base(clone, url, fm["base"], "refs/remotes/base")
        except ValueError as exc:
            f = subprocess.CompletedProcess([], 2, "", str(exc))
        if f.returncode:
            shutil.rmtree(clone, ignore_errors=True)   # the next tick starts from an empty workspace again
            why = (f.stderr.strip().splitlines() or ["no error text"])[-1]
            raise CloneError(f"fetch {fm['base']} from {nc.shown(url)}: {why}")
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", branch, "refs/remotes/base"], check=True)
    else:
        src = nc.source(ctx.vault, fm["repo"])
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    src = nc.source(ctx.vault, fm["repo"])
    b = {"src": nd.protected_refs(src) if fm["repo"] != "template" else {}, "code": nd.code_status(ctx.vault),
         "base_sha": nc.git(src, "rev-parse", f"{fm['base']}^{{commit}}").stdout.strip()}
````

Replace with:

````text
    if fm["repo"] == "template":   # the commit the session starts from, fetched from the template remote
        at, ref, refs = ctx.workspace / f"nightshift-{fm['id']}", "refs/remotes/base", {}
    else:
        at = nc.source(ctx.vault, fm["repo"])
        ref, refs = fm["base"], nd.protected_refs(at)
    b = {"src": refs, "code": nd.code_status(ctx.vault),
         "base_sha": nc.git(at, "rev-parse", f"{ref}^{{commit}}").stdout.strip()}
````

Edit 3 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        cwd = _clone(ctx, fm)
````

Replace with:

````text
        try:
            cwd = _clone(ctx, fm)
        except CloneError as exc:   # ends now, with a report row and a Needs-you line, and frees the queue
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "base", "needs": [
                f"Push {fm['base']} to the template remote, then queue {fm['id']} again ({exc})"]})
````


Edit 1 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
    env = dict(_git_env(), GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    cmd = ["git", "-C", str(runner_repo), "-c", "core.hooksPath=/dev/null"]
    if url.startswith("https://github.com/"):
        cmd += ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
````

Replace with:

````text
    if url.startswith("-"):   # git would read it as an option
        return False, f"refused: the remote {url!r} looks like an option"
    opts, env = nc.remote_git(url)
    cmd = ["git", "-C", str(runner_repo), "-c", "core.hooksPath=/dev/null", *opts]
````


- [ ] **Step 5: Run the tests to verify they pass**

Run: the suite command from Global Constraints.
Expected: PASS, `78 passed`.

- [ ] **Step 6: The skill, the README, the Nightshift spec and the roadmap**

Edit 1 in `.claude/skills/nightshift/SKILL.md`. Find:

````text
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear.
2. Read the plan. Propose `--verify` commands from its test lines (its Global Constraints or the last task's suite run) and a `--tasks` range that leaves out any task on the vault's `master`, a deploy, or a step needing the user. Show both and get the user's yes.
````

Replace with:

````text
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear. For `template`, the branch that holds the plan must be pushed to the template remote first: the check and the run read it from there, never from the vault, and `--base` is that branch's name.
2. Read the plan (for `template`: `git fetch -q template <branch>`, then `git show FETCH_HEAD:<plan path>`). Propose `--verify` commands from its test lines (its Global Constraints or the last task's suite run) and a `--tasks` range that leaves out any task on the vault's `master`, a deploy, or a step needing the user. Show both and get the user's yes.
````


Edit 1 in `README.md`. Find:

````text
**Next:** fewer permission prompts, a Nightshift fix, RCA-to-Jira (phase 1), preference notes from `/ingest`, then the Foreman orchestrator (Sub-project 2). Preferences (Plan 5) and style lint (Plan 7) wait for a few weeks of real use.
````

Replace with:

````text
**Next:** RCA-to-Jira (phase 1), preference notes from `/ingest`, then the Foreman orchestrator (Sub-project 2). Preferences (Plan 5) and style lint (Plan 7) wait for a few weeks of real use.
````

Edit 2 in `README.md`. Find:

````text
**The Nightshift.** `/nightshift` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the nightly window (`nightshift_window`, default `22:00-05:00`), at a set time, or now. A plan item runs in a private clone under `nightshift_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report, `system/logs/nightshift/<date>.md`, starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server.
````

Replace with:

````text
**The Nightshift.** `/nightshift` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the nightly window (`nightshift_window`, default `22:00-05:00`), at a set time, or now. A plan item runs in a private clone under `nightshift_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report, `system/logs/nightshift/<date>.md`, starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials.
````


Edit 1 in `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Find:

````text
**Changed:** 2026-10-07, the inactivity gate is removed (`2026-10-07-nightshift-no-idle-design.md`)
````

Replace with:

````text
**Changed:** 2026-10-07, the inactivity gate is removed (`2026-10-07-nightshift-no-idle-design.md`); 2026-10-08, template items are read from `template_remote`, never the vault (`2026-10-08-nightshift-template-source-design.md`)
````

Edit 2 in `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Find:

````text
- `repo` is a registered codebase, or `template` (resolved through the config key `template_remote`);
````

Replace with:

````text
- `repo` is a registered codebase, or `template` (resolved through the config key `template_remote`; the base and plan are read from that remote);
````


Edit 1 in `docs/superpowers/roadmap.md`. Find:

````text
| **Fixes from live use** | Issues the live vault logs on this repository | Small fixes found by running the real vault. Merged: #32, #34, #36, #45, #50, #58, #60. In review: the Nightshift pull requests opened 2026-10-08 (template issue fixes, telemetry identifiers). Next: fewer prompts (seven read-only allow rules in `.claude/settings.json` and the `CLAUDE.md` Bash line, byte for byte as in the vault); the Nightshift source fix (a `template` item resolves to the development clone or the remote, not the vault); the `/ingest` preference gap (design spec §6.21: digest Corrections never become `preference` notes) | Ongoing |
````

Replace with:

````text
| **Fixes from live use** | Issues the live vault logs on this repository | Small fixes found by running the real vault. Merged: #32, #34, #36, #45, #50, #58, #60; fewer prompts (#68: seven read-only allow rules and the `CLAUDE.md` Bash line, byte for byte as in the vault); the Nightshift inactivity gate removed (#69); the Nightshift minors (#70) and setup and update fixes (#71), both opened by the Nightshift. In review: the Nightshift template source (a `template` item is read from `template_remote`, never the vault); #72 (lint warnings, #19) and #73 (meetings fixes, #37–#43), opened by the Nightshift. Next: the `/ingest` preference gap (design spec §6.21: digest Corrections never become `preference` notes) | Ongoing |
````

Edit 2 in `docs/superpowers/roadmap.md`. Find:

````text
**Next, in order** (user, 2026-10-07): fewer prompts; the Nightshift source fix; RCA-to-Jira phase 1; `/ingest` preference notes; the Sub-project 2 brainstorm; then the reorganization (#62). Plans 5 and 7 wait for a few weeks of real use. Plan 12 runs in its own session.
````

Replace with:

````text
**Next, in order** (user, 2026-10-07): RCA-to-Jira phase 1; `/ingest` preference notes; the Sub-project 2 brainstorm; then the reorganization (#62). Plans 5 and 7 wait for a few weeks of real use. Plan 12 runs in its own session.
````


- [ ] **Step 7: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 8: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(nightshift): template items come from the template remote

The readiness check fetches a template item's base from template_remote
into a temporary bare repository and checks the plan there; the runner
clones the base from the same remote and reads base_sha from that
clone, so the no-commits guard holds. A fetch failure at run time ends
the item at once with a Needs-you line; at queue time it says whether
the branch is missing or the remote unreadable. A template_remote that
starts with "-" is refused; a half-built clone is rebuilt. The skill,
README, Nightshift spec and roadmap follow.

Claude-Session: https://claude.ai/code/session_01647fUGoWRjf3w7UNpdzKpF
```

Run: `git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_run.py system/scripts/vaultlib/nightshift_deliver.py system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py .claude/skills/nightshift/SKILL.md README.md docs/superpowers/specs/2026-10-06-nightshift-design.md docs/superpowers/roadmap.md`

Run: `git commit -q -F .scratch/msg-1.txt`
