# Work Order Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Work Order session reads nothing of the vault and nothing of the other codebases, gets eight named environment variables and no credential; the self-test proves the environment is clean; readiness and the tick refuse an `order_workspace` inside the vault.

**Architecture:** `nightshift_session.py` owns the profile (`CREDENTIALS`, the `Read(...)` mirror) and the one environment allowlist `session_env()`; `nightshift_run.py` denies the vault root, passes `env=` to both `claude` launches and runs a third self-test command; `nightshift_check.py` resolves the workspace and refuses one under the vault. No config key, no unit change, no new dependency.

**Tech Stack:** Python 3 (stdlib), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-13-audit-work-order-profile-design.md` (audit S3, S7; issue #136)

## Global Constraints

- Work on branch `feat/work-order-profile` in worktree `.scratch/profile`. Commit there; do not push or open a pull request.
- Run the suites through `<worktree>/system/scripts/test.sh <suite.bats | pytest path> [args…]`, one suite per call, outside a sandbox. Never run the gate from this worktree.
- Bound tools: pytest (`test_nightshift_session.py`, `test_nightshift_run.py`, `test_nightshift_check.py`, `test_nightshift_deliver.py`), bats (`nightshift.bats`, `commands.bats`), the gate (run by the main session).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- The environment allowlist is a safety list: no test widens it. Tests that need the stub's settings reach it through a wrapper the fixture writes.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- `session_env()` is the only source of a session's environment; `_run_session` and `_selftest_once` both pass it, and delivery (`push`, `gh pr create`) still runs with the runner's own environment.
- Every `denyRead` entry has a matching `permissions.deny` Read rule, in a form that matches a file as well as a directory (`~/.netrc` is a file).
- The self-test's third command prints only variable names, never values, and the verdict reads the tool result that holds `ENV_DONE`.
- A workspace under the vault is refused at `/order add` and fails a queued item with a Needs-you line; the fixture's workspace stays outside its vault, so every existing end-to-end test is unchanged.
- No document says the session "holds no credential" without also saying what it does get.

---

### Task 1: `session_env()`, the new credential paths and the Read mirror

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_session.py`
- Test: `system/tests/python/test_nightshift_session.py` (after `test_profile_denies_common_credentials_and_extra_paths`)

**Interfaces:**
- Produces: `ss.ENV` (the eight names), `ss.session_env() -> dict` (each named variable copied from `os.environ` when set, nothing else); `CREDENTIALS` gains `~/.claude/projects`, `~/.claude/settings.json`, `~/.claude/settings.local.json`, `~/.gitconfig`; `profile()` appends to `permissions.deny` a `Read(//<path>)` and a `Read(//<path>/**)` for every `denyRead` entry (the bare form only for a glob entry).

- [ ] **Step 1: Write the tests.** `test_session_env_passes_only_the_named_variables` (spec §4): set `SSH_AUTH_SOCK`, `GH_TOKEN`, `GITHUB_TOKEN`, `DBUS_SESSION_BUS_ADDRESS`, `ANTHROPIC_API_KEY`, `TZ`, `FOUNDRY_CLAUDE_BIN` with monkeypatch; `session_env()` holds none of the first five, holds `PATH`, `HOME`, `TZ`, `FOUNDRY_CLAUDE_BIN`, and its keys are a subset of `ss.ENV`. `test_profile_denies_the_claude_transcripts_and_mirrors_every_deny_into_read`: `denyRead` holds `<home>/.claude/projects`, `<home>/.gitconfig`, both `settings*.json`; for every `denyRead` entry `p`, `Read(//<p without its leading slash>/**)` is in `permissions.deny` when `p` has no `*`, and `Read(//<p>)` is there for every entry.
- [ ] **Step 2: Run them to verify they fail.** `test.sh system/tests/python/test_nightshift_session.py -k "session_env or mirrors"`. Expected: FAIL (`session_env` missing; no Read rules).
- [ ] **Step 3: Implement:** `ENV` tuple and `session_env()`; the four paths in `CREDENTIALS`; in `profile()`, after `denyRead` is built, extend `data["permissions"]["deny"]` with the mirror.
- [ ] **Step 4: Run the suite.** `test.sh system/tests/python/test_nightshift_session.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): session_env() allowlist, Read mirror and the Claude transcript, settings and gitconfig denies`.

### Task 2: The session gets `session_env()`; the stub reads its settings through a wrapper

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_run_session`, `_selftest_once`), `system/tests/stub_claude_nightshift`, `system/tests/python/test_nightshift_run.py` (the `env` fixture and every `NIGHTSHIFT_STUB_*` setter)
- Test: `system/tests/python/test_nightshift_run.py` (after `test_profile_mismatch_kills_and_fails`)

**Interfaces:**
- Consumes: `ss.session_env()` (Task 1).
- Produces: `subprocess.Popen(cmd, cwd=cwd, env=ss.session_env(), …)` in `_run_session`; `subprocess.run(cmd, cwd=tmp, env=ss.session_env(), …)` in `_selftest_once`. The stub writes `env` to `$NIGHTSHIFT_STUB_ENV` when set. The fixture writes `tmp_path/stub.env` and a wrapper `tmp_path/bin/claude` that exports that file and execs the stub; `FOUNDRY_CLAUDE_BIN` names the wrapper; a module helper `stub(tmp, **settings)` merges `NIGHTSHIFT_STUB_<KEY>=<shlex-quoted value>` lines into the file.

- [ ] **Step 1: Write the test.** `test_the_session_gets_only_the_allowlisted_environment` (spec §4): `stub(tmp, ENV=str(tmp / "env.txt"))`, `monkeypatch.setenv("SSH_AUTH_SOCK", "/run/sock")`, `add --now`, `tick`; the recorded file has no `SSH_AUTH_SOCK=` line, has `PATH=` and `HOME=` lines, and every recorded name outside `NIGHTSHIFT_STUB_*` and bash's own (`_`, `SHLVL`, `PWD`, `OLDPWD`) is in `ss.ENV`.
- [ ] **Step 2: Run it to verify it fails.** `test.sh system/tests/python/test_nightshift_run.py -k allowlisted_environment`. Expected: FAIL (`SSH_AUTH_SOCK` recorded).
- [ ] **Step 3: Implement:** `env=ss.session_env()` in both launches; `NIGHTSHIFT_STUB_ENV` in the stub; the wrapper and `stub()` in the fixture; replace each `monkeypatch.setenv("NIGHTSHIFT_STUB_…", v)` with `stub(tmp, …=v)` (tests that unpack `vault, _ = env` take `tmp`). `HOME`, `PATH` and `FOUNDRY_CLAUDE_BIN` setters stay: those names are on the allowlist.
- [ ] **Step 4: Run the suite.** `test.sh system/tests/python/test_nightshift_run.py`. Expected: PASS (the bwrap tests run when bwrap is installed).
- [ ] **Step 5: Commit.** `feat(orders): the session and the self-test get session_env() and nothing else`.

### Task 3: `_deny` returns the vault root; a workspace inside the vault is refused

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py` (`workspace()`, `workspace_inside_vault()`, `check()`), `system/scripts/vaultlib/nightshift_run.py` (`Ctx.__init__`, `_deny`, `run_item`)
- Test: `system/tests/python/test_nightshift_check.py` (after `test_plan_errors`), `system/tests/python/test_nightshift_run.py` (after `test_a_template_base_gone_from_the_remote_fails_at_once_with_a_needs_you_line`, and after `test_research_reads_a_pinned_copy_of_its_codebase`)

**Interfaces:**
- Produces: `nc.workspace(cfg) -> Path` (`order_workspace`, else `nightshift_workspace`, else `~/code/worktrees`, expanded); `nc.workspace_inside_vault(vault, ws) -> bool` (resolved paths, `is_relative_to`); `check()` appends `order_workspace is inside the vault`; `run_item` ends such an item `failed` with `reason: workspace` and the Needs-you line `Move order_workspace outside the vault (<ws> is inside it), then queue <id> again`; `_deny` returns `[<vault root>] + <other codebases>`.

- [ ] **Step 1: Write the tests.** `test_nightshift_check.py::test_a_workspace_inside_the_vault_is_not_ready`: with `order_workspace` set to `<vault>/.scratch/ws`, `check()` holds `order_workspace is inside the vault`; with `<tmp>/ws` it does not. `test_nightshift_run.py::test_a_run_denies_the_vault_root_and_not_only_its_four_folders`: after a tick the item's `settings.json` has `str(vault)` in `denyRead`, none of the four folder paths, and `Read(//<vault without leading slash>/**)` in `permissions.deny`. `test_add_refuses_a_workspace_inside_the_vault_and_a_tick_fails_a_queued_one` (spec §4): `add` after rewriting the config exits 2 and prints `not ready: order_workspace is inside the vault`; an item queued with the good workspace, then the config rewritten, ticks to `failed`/`workspace` with the Needs-you line in `outcome.json`.
- [ ] **Step 2: Run them to verify they fail.** `-k "workspace or vault_root"` in both modules. Expected: FAIL.
- [ ] **Step 3: Implement** the two helpers, `Ctx.workspace = nc.workspace(cfg)`, the `check()` line after `identifiers`, the `run_item` branch after the state update and before the kind branch, and `_deny`'s first line.
- [ ] **Step 4: Run both suites.** Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): sessions deny the vault root; a workspace inside the vault is refused`.

### Task 4: The self-test's third command

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`SELFTEST_PROMPT`, `_selftest_once`)
- Test: `system/tests/python/test_nightshift_run.py` (after `test_selftest_plants_a_canary_and_fails_if_the_session_reads_it`; the existing self-test tests gain the third result through a `selftest_stream()` helper)

**Interfaces:**
- Produces: the third command `env | grep -oE '^(SSH_AUTH_SOCK|GH_TOKEN|GITHUB_TOKEN|DBUS_SESSION_BUS_ADDRESS)='; echo ENV_DONE`; the verdict reads the tool result that holds `ENV_DONE` and fails on any `<NAME>=` line before it (`the session environment carries <NAME>`); a stream with no `ENV_DONE` is "did not run"; a stream with no init event fails with a reason that names an expired login or a login held only in `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`.

- [ ] **Step 1: Write the tests.** `selftest_stream(tmp_path, name, results)` builds a stream from `ok.jsonl` with one `tool_result` per entry. `test_selftest_fails_when_the_session_environment_carries_a_token` (spec §4): results `["CURL_EXIT=6", "CAT_EXIT=1", "GH_TOKEN=\nENV_DONE"]` give `(False, "the session environment carries GH_TOKEN")`; `["CURL_EXIT=6", "CAT_EXIT=1", "ENV_DONE"]` pass; `["CURL_EXIT=6", "CAT_EXIT=1"]` is "did not run". `test_selftest_names_the_env_token_login_when_the_session_does_not_start`: an empty stream fails with `CLAUDE_CODE_OAUTH_TOKEN` in the reason. Rewrite the existing self-test tests' streams with the helper.
- [ ] **Step 2: Run them to verify they fail.** `-k selftest`. Expected: the new tests FAIL; the rewritten ones PASS only after Step 3 (a passing one before it is a finding about the test).
- [ ] **Step 3: Implement** the prompt (three commands), the env verdict and the no-init reason.
- [ ] **Step 4: Run the suite.** Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): the self-test proves the session environment carries no token`.

### Task 5: Documents

**Files:**
- Modify: `FOUNDRY.md` (Work Orders paragraph; Headless isolation bullet), `docs/superpowers/specs/2026-10-06-nightshift-design.md` (§5.1, §5.3), `docs/superpowers/specs/2026-10-13-audit-work-order-profile-design.md` (the `printenv` and `Read(//<path>/**)` sentences, status)
- Test: `system/tests/commands.bats` (after "Work Orders start now by default; tonight, hold, the window and the 5-hour ceiling are documented")

- [ ] **Step 1: Write the test:** `FOUNDRY.md` contains `reads nothing of the vault, gets eight named environment variables and holds no credential`, `` `order_workspace` must sit outside the vault `` and `CLAUDE_CODE_OAUTH_TOKEN`.
- [ ] **Step 2: Verify it fails.** `test.sh system/tests/commands.bats -f 'reads nothing'`.
- [ ] **Step 3: Write the paragraphs.** Work Orders: the eight variables, that a token only in the unit's environment does not reach the session and such a login stops sessions with the sandbox alert, the workspace rule. Headless isolation: the deny list (vault root, other codebases, `CREDENTIALS`) and the `session_env()` list. Nightshift spec §5.1 and §5.3 to the current facts. Audit spec: the two sentences the rulings changed.
- [ ] **Step 4: Run `commands.bats` and `nightshift.bats`.** Expected: PASS.
- [ ] **Step 5: Commit.** `docs(orders): what a Work Order session reads and gets; the workspace rule`.
