# Nightshift Minors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four review findings in the Nightshift runner: local times in the report, no git run inside the session clone, a self-test that proves masking on every host, and validated queue-note identifiers.

**Architecture:** Four independent changes to `system/scripts/vaultlib/nightshift_*.py`, each test-first.
- The report converts outcome timestamps to the vault's `timezone` when it builds the table (`nightshift_report.build`), so `report [date]` fixes old reports too.
- `_deliver_plan` stops running `git rev-parse` in the clone. `nightshift_deliver.fetch_branch` fetches `refs/heads/nightshift/<id>` into the runner's bare repository and returns the tip it reads there.
- The self-test plants a canary file with a fresh token under `~/.config/foundry/` (denied by every profile), asks the session to `cat` it, fails if the read succeeds or the token shows up in the output, and removes the canary in a `finally`.
- A new `nightshift_check.identifiers(fm)` validates `id`, `partition`, `repo`, `base`, `pr_base` and `output`. `check()` runs it before any git call; `tick` screens every queue note with it before reconcile or pick, marks a live note that fails as `failed (invalid: …)`, alerts, and exits 2.

**Tech Stack:** Python 3.11 stdlib (`datetime`, `zoneinfo`, `secrets`, `re`), git 2.39, pytest 7, bats 1.8.

**Spec:** `docs/superpowers/specs/2026-10-06-nightshift-design.md` (§3.1, §3.2, §3.3 step 5, §4, §5.3, §6, §7). Read §3.3 and §5.3 before Tasks 2 and 3.

## Global Constraints

- Python stdlib only; no new dependencies.
- Every test runs offline inside the runner's verify sandbox (`nightshift_deliver.bwrap`): no network, `$HOME` an empty tmpfs, `PATH=/usr/local/bin:/usr/bin:/bin`, empty environment.
- Tests never write under the developer's real `$HOME`. Every test that reaches `nr.selftest` sets `HOME` to a directory under `tmp_path` first.
- After a session starts, the runner runs no git command with `-C <clone>` (spec §3.3: the clone is session-writable, so its `.git/config` is untrusted).
- Exit codes stay as spec §7 defines them: 0 ok or nothing due, 1 an item failed, 2 usage or invalid item, 4 locked.
- Queue-note `id` is `<YYYY-MM-DD>-<slug>` (spec §4); `nightshift_item.new_id` already produces exactly that shape.
- Commit after each task with a `fix(nightshift): …` subject. Never push and never open a pull request; the runner delivers.
- Verify commands for the whole plan: `python3 -m pytest system/tests/python -q` and `bats system/tests/nightshift.bats system/tests/vault_integrity.bats`.

## Decisions made while planning

- **D1 Fix 2 reads the tip from the runner's repository after the fetch.** `git fetch <clone>` from the runner's bare repository is the only git process that touches the clone, and that process is `git-upload-pack`, which git documents as the safe way to read an untrusted repository: "upload-pack tries to avoid any dangerous configuration options or hooks from the repository it's serving, making it safe to clone an untrusted directory" (git-upload-pack(1), SECURITY; also git(1), SECURITY). Repo-level `uploadpack.packObjectsHook` is ignored for this reason (git-config(1)). The fetch uses the full refspec `+refs/heads/<branch>:refs/heads/<branch>`, because a short name lets a session-planted tag of the same name win. Rejected: running `rev-parse` in the clone with `GIT_CONFIG_NOSYSTEM=1 -c core.fsmonitor=false …`. Repo config still loads (including `include.path`), so that is a deny-list over an open set of keys. The old "branch moved after the check" guard goes away: the sha the runner verifies and pushes is the one it read in its own repository, so there is no second read to race.
- **D2 `identifiers()` also checks `partition` and `repo`.** Both become paths (`wiki/<partition>/` is copied into a research session's `context/`; `system/codebases/<repo>.md` picks the source and push target), and a synced or hand-edited note is the same trust boundary as `id`. `output` also refuses a leading `/`, because `staging_dir / "/etc/x.md"` is `/etc/x.md`.
- **D3 A refused note is marked `failed` and the tick exits 2 before reconcile.** The next tick sees a `failed` note, skips it silently, and runs normally. Reconcile and pick only ever see screened entries, so the 7-day clean-up never builds an `rmtree` path from an unsafe `id`.
- **D4 Times convert at build time.** Outcome files keep their ISO timestamps; `build` reads `timezone` through `nightshift_check.config` with the same `"UTC"` default as `Ctx`.

## Review Focus

- An outcome with an empty or unparsable `started_at`/`finished_at` (an item that failed before it started): the Time cell is empty and the report still builds. Pinned in Task 1.
- A vault whose `system/config.md` has no `timezone` key: the report shows UTC, the same default `Ctx` uses. Pinned in Task 1.
- A session that plants a tag named `nightshift/<id>`, or deletes its branch: the runner fetches only `refs/heads/nightshift/<id>`, and a missing branch is an error the runner reports, never a crash. Pinned in Task 2.
- A self-test session that cannot start (missing binary, timeout): the canary is still removed. Pinned in Task 3.
- An already-finished queue note with an unsafe `id` (synced from another machine or edited by hand) and a `finished_at` older than 7 days: the clean-up never removes a directory built from that `id`. Pinned in Task 4.

---

### Task 1: Report times in the vault's timezone

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_report.py:1-4` (imports), `:46-62` (`build`)
- Test: `system/tests/python/test_nightshift_report.py`

**Interfaces:**
- Consumes: `nightshift_check.config(vault) -> dict` (existing).
- Produces: `nightshift_report._hm(value, tz) -> str` (HH:MM or `""`). `build(vault, date)` keeps its signature.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_nightshift_report.py`, change the imports at the top to:

```python
from pathlib import Path

from helpers import write
from vaultlib import nightshift_report as nr
```

Append:

```python


def test_time_column_is_local_to_the_vault_timezone(vault: Path):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\n---\n')
    nr.write_outcome(vault, outcome(started_at="2026-10-07T04:00:00+00:00", finished_at="2026-10-07T07:10:00+00:00"))
    row = [l for l in nr.build(vault, "2026-10-07").splitlines() if l.startswith("| 2026-10-06-a")][0]
    assert "| 22:00–01:10 |" in row


def test_time_column_without_a_timezone_or_with_bad_times(vault: Path):
    nr.write_outcome(vault, outcome(started_at="2026-10-07T04:00:00+00:00", finished_at="2026-10-07T07:10:00+00:00"))
    nr.write_outcome(vault, outcome(id="2026-10-06-b", started_at="", finished_at="not a time"))
    rows = {l.split(" | ")[0][2:]: l for l in nr.build(vault, "2026-10-07").splitlines() if l.startswith("| 2026")}
    assert "| 04:00–07:10 |" in rows["2026-10-06-a"]
    assert "| – |" in rows["2026-10-06-b"]
```

The fixture vault has no `system/config.md`, so the second test covers the UTC default.

- [ ] **Step 2: Run the tests to verify the first one fails**

Run: `python3 -m pytest system/tests/python/test_nightshift_report.py -q`
Expected: `test_time_column_is_local_to_the_vault_timezone` FAILS (the row shows `04:00–07:10`, the UTC slice). `test_time_column_without_a_timezone_or_with_bad_times` passes already; it guards the new code against regressions.

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/nightshift_report.py`, replace the imports

```python
import json
import os
from pathlib import Path
```

with

```python
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import nightshift_check as nc
```

Add above `def build`:

```python
def _hm(value, tz) -> str:
    """An ISO timestamp as HH:MM in the vault's timezone; empty when it is missing or unreadable."""
    try:
        return datetime.fromisoformat(str(value)).astimezone(tz).strftime("%H:%M")
    except ValueError:
        return ""


```

In `build`, replace

```python
    lines += ["## Items", "| Item | Kind | Result | Time | Notes |", "|---|---|---|---|---|"]
    for o in outcomes:
        state = o["state"] + (f" ({o['reason']})" if o.get("reason") else "")
        span = f"{str(o.get('started_at', ''))[11:16]}–{str(o.get('finished_at', ''))[11:16]}"
```

with

```python
    tz = ZoneInfo(str(nc.config(vault).get("timezone") or "UTC"))
    lines += ["## Items", "| Item | Kind | Result | Time | Notes |", "|---|---|---|---|---|"]
    for o in outcomes:
        state = o["state"] + (f" ({o['reason']})" if o.get("reason") else "")
        span = f"{_hm(o.get('started_at'), tz)}–{_hm(o.get('finished_at'), tz)}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_nightshift_report.py system/tests/python/test_nightshift_run.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/nightshift_report.py system/tests/python/test_nightshift_report.py
git commit -m "fix(nightshift): report times in the vault's timezone"
```

---

### Task 2: Read the branch tip in the runner's repository

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_deliver.py:64-74` (`fetch_branch`)
- Modify: `system/scripts/vaultlib/nightshift_run.py:351-358` (`_deliver_plan`)
- Test: `system/tests/python/test_nightshift_deliver.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `nightshift_deliver._git_env() -> dict` (existing).
- Produces: `nightshift_deliver.fetch_branch(runner_repo, clone, branch: str) -> tuple` returning `(True, tip_sha)` or `(False, reason)`. The `sha` parameter is removed; every caller changes.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_nightshift_deliver.py`:

Replace the line in `test_fetch_push_and_github_pr`

```python
    assert nd.fetch_branch(runner, src, "nightshift/x", sha) == (True, "")
```

with

```python
    assert nd.fetch_branch(runner, src, "nightshift/x") == (True, sha)
```

Replace the whole of `test_fetch_refuses_a_moved_tip` (its contract no longer exists) with:

```python
def test_fetch_reads_the_tip_from_the_runner_repository(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    git(src, "checkout", "-q", "-b", "nightshift/x")
    git(src, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "work")
    tip = git(src, "rev-parse", "HEAD").strip()
    git(src, "tag", "nightshift/x", "HEAD~1")  # a tag named like the branch must not be what is fetched
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "nightshift/x") == (True, tip)
    assert git(runner, "rev-parse", "refs/heads/nightshift/x").strip() == tip


def test_fetch_of_a_missing_branch_fails(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    ok, why = nd.fetch_branch(tmp_path / "runner.git", src, "nightshift/gone")
    assert not ok and why
```

In `test_verify_runs_on_a_private_checkout_of_the_sha` and `test_protected_files_are_committed_by_the_runner`, replace each

```python
    assert nd.fetch_branch(runner, src, "master", sha)[0]
```

with

```python
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
```

Append to `system/tests/python/test_nightshift_run.py`:

```python


def test_delivery_runs_no_git_inside_the_session_clone(env, monkeypatch):
    vault, tmp = env
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
    monkeypatch.setattr(nr.nd, "verify_sha", lambda *a: (True, ""))  # bwrap is covered by the end-to-end tests
    calls, real = [], subprocess.run

    def spy(cmd, *a, **kw):
        calls.append([str(c) for c in cmd])
        return real(cmd, *a, **kw)
    monkeypatch.setattr(subprocess, "run", spy)
    out = nr._deliver_plan(ctx, fm, clone, idir, before)
    assert out["state"] == "done", out
    assert [c for c in calls if c[:3] == ["git", "-C", str(clone)]] == []
```

The spy matches `git -C <clone>` only: `fetch_branch` legitimately passes the clone path as the fetch source while running in the runner's repository.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py -q -k "fetch or no_git or private_checkout or protected_files_are"`
Expected: the five `test_nightshift_deliver.py` tests that call `fetch_branch` FAIL with `TypeError: fetch_branch() missing 1 required positional argument: 'sha'`; `test_delivery_runs_no_git_inside_the_session_clone` FAILS on the last assert (it lists a `git -C <clone> rev-parse …` call).

- [ ] **Step 3: Implement `fetch_branch`**

In `system/scripts/vaultlib/nightshift_deliver.py`, replace the whole `fetch_branch` function with:

```python
def fetch_branch(runner_repo, clone, branch: str) -> tuple:
    """Copy the session's branch into the runner's repository and return (True, its tip) or (False, reason).
    The tip is read in the runner's repository: the only git process that touches the session-writable clone is
    upload-pack, which ignores the clone's dangerous config and hooks (git-upload-pack(1), SECURITY)."""
    runner_repo = Path(runner_repo)
    if not (runner_repo / "HEAD").exists():
        subprocess.run(["git", "init", "-q", "--bare", str(runner_repo)], check=True)
    ref = f"refs/heads/{branch}"
    f = subprocess.run(["git", "-C", str(runner_repo), "fetch", "-q", "--no-tags", str(clone), f"+{ref}:{ref}"],
                       capture_output=True, text=True, env=_git_env())
    if f.returncode:
        return False, f.stderr.strip() or f"fetch failed (exit {f.returncode})"
    tip = subprocess.run(["git", "-C", str(runner_repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                         capture_output=True, text=True, env=_git_env()).stdout.strip()
    return (True, tip) if tip else (False, f"{ref} is not a commit")
```

- [ ] **Step 4: Implement the caller**

In `system/scripts/vaultlib/nightshift_run.py` `_deliver_plan`, replace

```python
    branch = f"nightshift/{fm['id']}"
    sha = nc.git(clone, "rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}").stdout.strip()
    if not sha or sha == before["base_sha"]:
        return {"state": "blocked", "reason": "no commits"}
    runner = ctx.workspace / "nightshift-runner.git"
    ok, why = nd.fetch_branch(runner, clone, branch, sha)
    if not ok:
        return {"state": "failed", "reason": "containment" if "moved" in why else "delivery", "notes": why}
```

with

```python
    branch = f"nightshift/{fm['id']}"
    runner = ctx.workspace / "nightshift-runner.git"
    ok, sha = nd.fetch_branch(runner, clone, branch)
    if not ok:
        return {"state": "blocked", "reason": "no commits", "notes": sha}
    if sha == before["base_sha"]:
        return {"state": "blocked", "reason": "no commits"}
```

A fetch that fails here almost always means the session deleted or never created its branch, which the old code also reported as `blocked (no commits)`; git's message goes into `notes`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py -q`
Expected: all PASS (the bwrap end-to-end tests included, about 90 s).

- [ ] **Step 6: Commit**

```bash
git add system/scripts/vaultlib/nightshift_deliver.py system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py
git commit -m "fix(nightshift): read the branch tip in the runner's repository, never in the session clone"
```

---

### Task 3: Self-test reads a planted canary

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py:2-14` (imports), `:26-31` (`SELFTEST_PROMPT`), `:110-133` (`_selftest_once`)
- Modify: `docs/superpowers/specs/2026-10-06-nightshift-design.md:124` (§5.3)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `nightshift_session.profile`, `command`, `parse_stream`, `init_problem` (existing).
- Produces: `nightshift_run.CANARY = "~/.config/foundry/nightshift-canary"`. `selftest(vault) -> (bool, str)` keeps its signature; a failed read now reports `the canary ~/.config/foundry/nightshift-canary was readable`.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_nightshift_run.py`, add a `HOME` line as the second line of `test_selftest_parses_tool_results` and of `test_selftest_retries_when_the_model_declines`, right after `vault, _ = env`:

```python
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the self-test plants its canary under $HOME
```

Replace `test_selftest_prompt_says_failures_are_expected` with:

```python
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
```

The stub `claude` (`system/tests/stub_claude_nightshift`) runs `NIGHTSHIFT_STUB_SHELL` before it prints the stream, so the leak script appends a tool result holding the canary's token, as an unmasked session would.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_nightshift_run.py -q -k selftest`
Expected: `test_selftest_prompt_says_failures_are_expected` FAILS with `AttributeError: … has no attribute 'CANARY'`; `test_selftest_plants_a_canary_and_fails_if_the_session_reads_it` FAILS on the `seen` assert (no canary is planted). The two existing self-test tests pass.

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/nightshift_run.py`, add `import secrets` between `import os` and `import shutil`.

Replace the `SELFTEST_PROMPT` assignment with:

```python
CANARY = "~/.config/foundry/nightshift-canary"  # planted by the self-test under a path every profile denies
SELFTEST_PROMPT = ("This is the Nightshift runner's sandbox self-test, run by the vault's owner. Both commands below "
                   "are expected to fail inside the sandbox; the test needs their real exit codes, so run each one with "
                   "the Bash tool even if you expect a denial, and do not explain or refuse. "
                   "Run exactly these two Bash commands, one at a time, and nothing else: "
                   "`curl -sS -m 5 -o /dev/null https://example.com; echo CURL_EXIT=$?` and "
                   f"`cat {CANARY}; echo CAT_EXIT=$?`. Then stop.")
```

Replace the whole `_selftest_once` function with:

```python
def _selftest_once(vault) -> tuple:
    """(verdict, reason): verdict True passed, False failed, None the commands did not run. A canary with a fresh token
    is planted under a denied path for the session to try to read, so the test proves masking on every host."""
    canary = Path(os.path.expanduser(CANARY))
    token = secrets.token_hex(16)
    canary.parent.mkdir(parents=True, exist_ok=True)
    canary.write_text(token + "\n")
    try:
        with __import__("tempfile").TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps(ss.profile(vault, "plan", [])))
            stream = Path(tmp) / "stream.jsonl"
            cmd = ss.command("plan", SELFTEST_PROMPT, settings, "haiku", str(uuid.uuid4()), [])
            with open(stream, "w") as out:
                try:
                    subprocess.run(cmd, cwd=tmp, stdout=out, stderr=subprocess.DEVNULL, timeout=300)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    return False, f"self-test session failed: {exc.__class__.__name__}"
            s = ss.parse_stream(stream)
    finally:
        canary.unlink(missing_ok=True)
    problem = ss.init_problem(s["init"], "plan")
    if problem:
        return False, f"profile: {problem}"
    text = " ".join(s["tool_results"])
    if "CURL_EXIT=0" in text:
        return False, "curl reached a host outside the allowlist"
    if "CAT_EXIT=0" in text or token in text:
        return False, f"the canary {CANARY} was readable"
    if "CURL_EXIT=" not in text or "CAT_EXIT=" not in text:
        return None, "the self-test commands did not run"
    return True, ""
```

The token check runs before the "did not run" check, so a leaked read fails at once instead of being retried.

- [ ] **Step 4: Update the spec**

In `docs/superpowers/specs/2026-10-06-nightshift-design.md` §5.3, replace the paragraph

```markdown
`nightshift.py selftest` runs the plan profile's sandbox with two commands that must fail: a request to a host outside the allowlist, and a read of a file under `~/.ssh`. Either succeeding fails the self-test.
```

with

```markdown
`nightshift.py selftest` plants a canary file holding a fresh token at `~/.config/foundry/nightshift-canary` (a denied path), then runs the plan profile's sandbox with two commands that must fail: a request to a host outside the allowlist, and a read of the canary. Either succeeding, or the token appearing in the session's output, fails the self-test. The canary is removed afterwards, whatever the outcome.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_nightshift_run.py -q -k selftest`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_run.py docs/superpowers/specs/2026-10-06-nightshift-design.md
git commit -m "fix(nightshift): self-test reads a planted canary under a denied path"
```

---

### Task 4: Validate queue-note identifiers in check and tick

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py:15` (constants), `:62-82` (`check`)
- Modify: `system/scripts/vaultlib/nightshift_run.py:482-503` (`_reconcile`, `tick`)
- Modify: `docs/superpowers/specs/2026-10-06-nightshift-design.md:46` (§3.1)
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `nightshift_item.PARTITIONS`, `nightshift_item.items`, `nightshift_item.update`, `Ctx.alert` (existing).
- Produces: `nightshift_check.identifiers(fm: dict) -> list[str]` (error strings, empty when valid); `nightshift_run._screen(ctx) -> (entries, refused)` where `entries` is a list of `(path, fm, body)` and `refused` a list of paths; `nightshift_run._reconcile(ctx, entries: list) -> None` (new second parameter).

- [ ] **Step 1: Write the failing tests**

Append to `system/tests/python/test_nightshift_check.py`:

```python


@pytest.mark.parametrize("field,value,needle", [
    ("id", "../../evil", "id must look like"), ("id", "2026-10-06-Bad_Name", "id must look like"),
    ("id", "evil", "id must look like"), ("base", "--output=/tmp/x", "base must not start with '-'"),
    ("pr_base", "-x", "pr_base must not start with '-'"), ("repo", "../x", "repo must be a plain name")])
def test_identifiers_are_refused_before_any_git_call(vault_repo, field, value, needle):
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", **{field: value}), "")
    assert any(needle in e for e in errs), errs


@pytest.mark.parametrize("output", ["wiki/work/../personal/x.md", "/etc/x.md"])
def test_output_must_stay_inside_the_vault(vault_repo, output):
    fm = plan_fm(kind="research", output=output, hosts=[])
    assert any("no '..'" in e for e in nc.check(vault_repo, fm, BRIEF))
```

Append to `system/tests/python/test_nightshift_run.py`:

```python


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
```

`../../victim` resolves, through `<workspace>/nightshift-../../victim`, to `tmp/victim`: the directory the current reconcile would `rmtree`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py -q -k "identifiers or output_must or unsafe_id"`
Expected: all 9 FAIL. The `id`, `pr_base` and `output` cases return no matching error; `base` and `repo` return the old "does not resolve" and "not a registered codebase" messages; the tick test fails before reaching its first assert (the current tick runs the note).

- [ ] **Step 3: Implement `identifiers` and use it in `check`**

In `system/scripts/vaultlib/nightshift_check.py`, add below the `HOST = …` line:

```python
ID = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
```

Replace the start of `check`

```python
def check(vault, fm: dict, body: str) -> list:
    errs = []
    kind = fm.get("kind")
    if fm.get("partition") not in ni.PARTITIONS:
        errs.append("partition must be work, personal or shared")
    try:
```

with

```python
def identifiers(fm: dict) -> list:
    """The fields the runner turns into file paths and git arguments. check() and the tick refuse a note that fails."""
    errs = []
    if not ID.fullmatch(str(fm.get("id") or "")):
        errs.append("id must look like 2026-10-07-some-slug (lower-case letters, digits and dashes)")
    if fm.get("partition") not in ni.PARTITIONS:
        errs.append("partition must be work, personal or shared")
    if fm.get("repo") and not NAME.fullmatch(str(fm["repo"])):
        errs.append("repo must be a plain name (a registered codebase or template)")
    errs += [f"{k} must not start with '-'" for k in ("base", "pr_base") if str(fm.get(k) or "").startswith("-")]
    out = str(fm.get("output") or "")
    if out.startswith("/") or ".." in out.split("/"):
        errs.append("output must be a relative path with no '..' segments")
    return errs


def check(vault, fm: dict, body: str) -> list:
    errs = identifiers(fm)
    if errs:
        return errs  # nothing below may pass a bad ref or path to git
    kind = fm.get("kind")
    try:
```

The rest of `check` is unchanged.

- [ ] **Step 4: Implement the tick screen**

In `system/scripts/vaultlib/nightshift_run.py`, replace

```python
def _reconcile(ctx: Ctx) -> None:
    for path, fm, _ in ni.items(ctx.vault):
```

with

```python
def _screen(ctx: Ctx) -> tuple:
    """(entries, refused). Only notes whose identifiers pass nc.identifiers are returned: their id, refs and output
    become paths and git arguments. A live note that fails is marked failed and alerted once."""
    entries, refused = [], []
    for path, fm, body in ni.items(ctx.vault):
        errs = nc.identifiers(fm)
        if not errs:
            entries.append((path, fm, body))
        elif fm.get("state") not in ("failed", "done", "cancelled"):
            why = "; ".join(errs)
            ni.update(path, state="failed", reason=f"invalid: {why}")
            ctx.alert(f"invalid/{path.name}", f"{path.name} refused: {why}")
            refused.append(path)
    return entries, refused


def _reconcile(ctx: Ctx, entries: list) -> None:
    for path, fm, _ in entries:
```

In `tick`, replace

```python
def tick(ctx: Ctx) -> int:
    _reconcile(ctx)
    entries = [(p, fm, b) for p, fm, b in ni.items(ctx.vault)]
```

with

```python
def tick(ctx: Ctx) -> int:
    entries, refused = _screen(ctx)
    if refused:
        return 2
    _reconcile(ctx, entries)
    entries, _ = _screen(ctx)
```

The second `_screen` call re-reads the notes after reconcile changed them, as the old second `ni.items` call did.

- [ ] **Step 5: Update the spec**

In `docs/superpowers/specs/2026-10-06-nightshift-design.md` §3.1, insert this paragraph between the `/nightshift add` paragraph and `Readiness, plan:`:

```markdown
Identifiers, both kinds: `id` is `<YYYY-MM-DD>-<slug>` (lower-case letters, digits and dashes); `partition` is `work`, `personal` or `shared`; `repo` is a plain name; `base` and `pr_base` do not start with `-`; `output` is a relative path with no `..` segment. `check` tests these first and runs no git command for a note that fails. Every tick applies the same test to every queue note before anything else: a live note that fails becomes `failed (invalid: …)` with an alert, the tick exits 2, and no tick reads that note again.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_item.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py docs/superpowers/specs/2026-10-06-nightshift-design.md
git commit -m "fix(nightshift): validate queue-note identifiers in check and refuse them in tick"
```

---

### Task 5: Full suite

**Files:** none changed unless a test fails.

- [ ] **Step 1: Run the Python suite**

Run: `python3 -m pytest system/tests/python -q`
Expected: `695 passed` (681 before this plan plus 14 new), no failures. A failure here is fixed in the task that owns the file, with a new commit.

- [ ] **Step 2: Run the bats suites**

Run: `bats system/tests/nightshift.bats system/tests/vault_integrity.bats`
Expected: every line `ok`, none `not ok`.

- [ ] **Step 3: Confirm the branch holds four commits**

Run: `git log --oneline -5`
Expected: the four `fix(nightshift): …` commits from Tasks 1 to 4 on top of the plan's commit; `git status --short` prints nothing.
