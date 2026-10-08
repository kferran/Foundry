# Nightshift Template Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Nightshift `template` item's base branch and plan are read from `template_remote`, at queue time and at run time, never from the vault.

**Architecture:** `nightshift_check` gains `remote_git(url)` (git `-c` options and environment for a remote) and `fetch_base(repo, url, base, dest, depth)`. The readiness check fetches the base one commit deep into a temporary bare repository and runs the existing plan checks there (`_plan_at`); `source(vault, "template")` returns `None`. The runner's `_clone` fetches the base from the remote at full depth; `nightshift_deliver.push` uses the same `remote_git`.

**Tech Stack:** Python 3.11, git, pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-nightshift-template-source-design.md`

## Global Constraints

- Work on branch `fix/nightshift-template-source` of `kferran/Foundry`. Commit there; do not push or open a pull request.
- Codebase items are unchanged: they read their registered clone.
- Nothing reads a template item's base or plan from the vault.
- A local bare repository stands in for the template remote in tests.
- Run the Nightshift suites as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch python3 -m pytest system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_report.py -q` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`.
- Bound tools: pytest (those four suites) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- A base that exists only in the vault must fail at queue time with a message that says to push it: `test_template_base_must_be_on_the_template_remote`.
- A missing `template_remote` must fail before any fetch, with only that error: `test_template_without_template_remote_fails_before_any_fetch`.
- The run must not pick up vault-only commits on the base: `test_template_clone_comes_from_the_template_remote`.
- A failed fetch at run time must not leave a half-made clone that the next tick reuses: `_clone` removes the directory before raising (the tick ends with the exception, as a failed fetch did before).
- A remote that refuses pushes must still be readable for the check and the clone: `test_delivery_failure_is_retried_without_a_new_session` now refuses pushes with a `pre-receive` hook instead of deleting the remote.

---

### Task 1: Read template items from the template remote

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/vaultlib/nightshift_deliver.py`, `.claude/skills/nightshift/SKILL.md`, `docs/superpowers/specs/2026-10-06-nightshift-design.md`, `docs/superpowers/roadmap.md`
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `nightshift_check.remote_git(url) -> (list, dict)`, `nightshift_check.fetch_base(repo, url, base, dest, depth=None) -> CompletedProcess`, `nightshift_check.source(vault, "template") -> None`.

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
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "https://github.com/o/r.git"\n---\n')
````

Replace with:

````text
    remote = tmp_path / "remote.git"   # a local bare repository stands in for the template remote
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(vault, "push", "-q", str(remote), "feat/x")
    write(vault, "system/config.md", f'---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "{remote}"\n---\n')
````

Edit 3 in `system/tests/python/test_nightshift_check.py`. Find:

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


def test_template_without_template_remote_fails_before_any_fetch(vault_repo):
    write(vault_repo, "system/config.md", '---\ntype: config\ntimezone: "UTC"\n---\n')
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == ["config has no template_remote"]
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
    assert git(tmp / "remote.git", "branch", "--list").strip() == ""
````

Replace with:

````text
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


- [ ] **Step 2: Run them to verify they fail**

Run: the suite command from Global Constraints.
Expected: FAIL, `2 failed, 71 passed`: `test_template_base_must_be_on_the_template_remote` (no "push it first" error: the old check reads the vault, where the branch exists) and `test_template_clone_comes_from_the_template_remote` (the clone holds the vault-only commit). The other changed tests pass on the old code too.

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


def fetch_base(repo, url: str, base: str, dest: str, depth: int | None = None) -> subprocess.CompletedProcess:
    """Fetch refs/heads/<base> from url into repo as dest."""
    opts, env = remote_git(url)
    cmd = ["git", "-C", str(repo), *opts, "fetch", "-q", "--no-tags", *(["--depth", str(depth)] if depth else []),
           url, f"refs/heads/{base}:{dest}"]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)
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
        with tempfile.TemporaryDirectory(prefix="nightshift-check-") as tmp:   # the base and plan, read from the remote
            subprocess.run(["git", "init", "-q", "--bare", tmp], check=True, capture_output=True)
            if not base or fetch_base(tmp, url, base, f"refs/heads/{base}", depth=1).returncode:
                return errs + [f"base {base or '(empty)'} is not on the template remote {url} (push it first)"]
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


- [ ] **Step 4: The clone and the push use the template remote**

Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
def _clone(ctx: Ctx, fm: dict) -> Path:
    src = nc.source(ctx.vault, fm["repo"])
````

Replace with:

````text
def _clone(ctx: Ctx, fm: dict) -> Path:
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        # The vault's object store holds private notes: copy only what the base reaches, with no alternates.
        ref = nc.git(src, "rev-parse", "--symbolic-full-name", fm["base"]).stdout.strip() or fm["base"]
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "fetch", "-q", "--no-tags", str(src), f"{ref}:refs/remotes/base"], check=True)
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", branch, "refs/remotes/base"], check=True)
    else:
````

Replace with:

````text
        # From the template remote, never the vault: the vault's object store holds private notes.
        url = str(nc.config(ctx.vault).get("template_remote") or "")
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        f = nc.fetch_base(clone, url, fm["base"], "refs/remotes/base")
        if f.returncode:
            shutil.rmtree(clone, ignore_errors=True)   # the next tick starts from an empty workspace again
            raise RuntimeError(f"fetch {fm['base']} from {url}: {f.stderr.strip()}")
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", branch, "refs/remotes/base"], check=True)
    else:
        src = nc.source(ctx.vault, fm["repo"])
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
    opts, env = nc.remote_git(url)
    cmd = ["git", "-C", str(runner_repo), "-c", "core.hooksPath=/dev/null", *opts]
````


- [ ] **Step 5: Run the tests to verify they pass**

Run: the suite command from Global Constraints.
Expected: PASS, `73 passed`.

- [ ] **Step 6: The skill, the Nightshift spec and the roadmap**

Edit 1 in `.claude/skills/nightshift/SKILL.md`. Find:

````text
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear.
````

Replace with:

````text
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear. For `template`, the branch that holds the plan must be pushed to the template remote first: the check and the run read it from there, never from the vault.
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
| **Fixes from live use** | Issues the live vault logs on this repository | Small fixes found by running the real vault. Merged: #32, #34, #36, #45, #50, #58, #60; fewer prompts (#68: seven read-only allow rules and the `CLAUDE.md` Bash line, byte for byte as in the vault); the Nightshift inactivity gate removed (#69); the Nightshift minors (#70) and setup and update fixes (#71), both opened by the Nightshift; the Nightshift template source (a `template` item is read from `template_remote`, never the vault). In review: #72 (lint warnings, #19) and #73 (meetings fixes, #37–#43), opened by the Nightshift. Next: the `/ingest` preference gap (design spec §6.21: digest Corrections never become `preference` notes) | Ongoing |
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
clones the base from the same remote. Nothing is read from the vault,
so template branches no longer live in the vault repository. The
check, the clone and the push share one helper for credentials. The
Nightshift skill says to push the base first; the Nightshift spec and
the roadmap record the change.

Claude-Session: https://claude.ai/code/session_01647fUGoWRjf3w7UNpdzKpF
```

Run: `git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_run.py system/scripts/vaultlib/nightshift_deliver.py system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py .claude/skills/nightshift/SKILL.md docs/superpowers/specs/2026-10-06-nightshift-design.md docs/superpowers/roadmap.md && git commit -q -F .scratch/msg-1.txt`
