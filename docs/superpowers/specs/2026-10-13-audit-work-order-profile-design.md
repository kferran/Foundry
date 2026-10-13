# Work Order profile: the session reads nothing of the vault and inherits no environment

**Date:** 2026-10-13
**Status:** Draft for the owner's review.
**Issue:** #136 (S3, S7). From the 2026-10-13 audit (`docs/superpowers/2026-10-13-audit.md` on the audit branch).

## 1. Problem

`nightshift_run._deny` denies a Work Order session four vault folders (`wiki`, `raw`, `briefings`, `system/logs`) and the other registered codebases. The rest of the vault is readable from the sandboxed Bash: `system/index.db` (every note body, all partitions), `.git` (every note's history), `system/quarantine`, `system/nightshift`, `CLAUDE.md`. Outside the vault, `~/.claude/projects/` (the Foreman's transcripts) and `~/.gitconfig` are readable; `headless.settings.json` denies `~/.claude/projects/**` to headless runs, the Work Order profile does not. The two profiles hold no `Read(...)` deny rule: `denyRead` governs sandboxed Bash, and the sources do not show that it governs the Read tool. A prompt-injected codebase can read these and commit them to `order/<id>`, which the runner pushes and opens as a pull request.

The session also inherits the runner's whole environment (`subprocess.Popen(cmd, cwd=cwd, …)` in `_run_session`, `subprocess.run` in `_selftest_once`): `SSH_AUTH_SOCK`, `GH_TOKEN`, `GITHUB_TOKEN` and `DBUS_SESSION_BUS_ADDRESS` survive every file deny. With the git host in `order_hosts`, the session can push on its own; the contract asks it not to, and the containment check compares local refs only. `FOUNDRY.md` says the session "holds no credential", which is false today.

## 2. Decisions

- **`_deny` returns the vault root** in place of the four folders, plus the other codebases as now. The clone, a research item's `context/` copy and its `out/` all live under `order_workspace`, so a session needs nothing from the vault. `nightshift_check.check` refuses an item while `order_workspace` resolves under the vault ("not ready: order_workspace is inside the vault"), and `run_item` fails a queued item the same way a missing base does (a Needs-you line: move the workspace, queue again), since the deny would cover the session's own working directory.
- **`CREDENTIALS` gains `~/.claude/projects`, `~/.claude/settings.json`, `~/.claude/settings.local.json` and `~/.gitconfig`.** Not `~/.claude` wholesale: `--plugin-dir` points under `~/.claude/plugins/cache`, and the session's Bash runs the plugin's scripts from there.
- **`profile()` mirrors every `denyRead` entry into `permissions.deny` as `Read(//<path>/**)`** (the form `headless.settings.json` uses), so the Read tool is bound whether or not the sandbox list reaches it.
- **One environment allowlist, `nightshift_session.session_env()`:** `PATH`, `HOME`, `USER`, `LANG`, `TZ`, `TMPDIR`, `FOUNDRY_CLAUDE_BIN` and `CLAUDE_CONFIG_DIR`, each copied when set, nothing else. It is the list `nightshift_deliver.bwrap()` already gives the verify step, plus the variables the runner itself reads. An allowlist because the next token variable is on no denylist. `_run_session` and `_selftest_once` pass it as `env=`. Delivery (`push`, `gh pr create`) runs in the runner's own process with its own environment and is unchanged.
- **The self-test runs a third command,** `printenv SSH_AUTH_SOCK GH_TOKEN GITHUB_TOKEN DBUS_SESSION_BUS_ADDRESS; echo ENV_DONE`; any output line before `ENV_DONE` fails it ("the session environment carries <variable>"). The verdict reads the output, since `printenv`'s exit is 1 as soon as one named variable is unset. It is offline, so it needs no allowed host; the audit's `git ls-remote` variant needs one and is dropped.
- **Owner decision:** a vault whose `claude` authenticates only through `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` in the unit's environment stops starting sessions (the self-test's session has no init event, the sandbox alert says so, no item runs). Recommendation: keep both out of the allowlist; an env token would reach every sandboxed Bash, and `~/.claude/.credentials.json` is the login the health check already tests.

## 3. Changes

- `vaultlib/nightshift_run.py`: `_deny`; `env=` in `_run_session` and `_selftest_once`; the third self-test command and its verdict; the workspace failure in `run_item`.
- `vaultlib/nightshift_session.py`: `CREDENTIALS`, the `Read(...)` mirror in `profile()`, `session_env()`.
- `vaultlib/nightshift_check.py`: the workspace refusal.
- `FOUNDRY.md`: the Work Orders paragraph's "holds no credential" becomes "reads nothing of the vault, gets eight named environment variables and holds no credential"; Headless isolation names the two lists.
- `system/tests/stub_claude_nightshift` reads its `NIGHTSHIFT_STUB_*` settings from a wrapper the runner fixture writes, since the scrubbed environment no longer carries them.

**Existing vault:** no config or unit change. A vault with `order_workspace` under its root gets the readiness refusal on the next `/order add` and a Needs-you line for each queued plan item until the workspace moves.

## 4. Tests

pytest `test_nightshift_session.py`: `session_env()` from an environ holding `SSH_AUTH_SOCK`, `GH_TOKEN`, `GITHUB_TOKEN`, `DBUS_SESSION_BUS_ADDRESS` and `ANTHROPIC_API_KEY` returns none of them and keeps `PATH`, `HOME`, `TZ` and `FOUNDRY_CLAUDE_BIN`; `profile()` denies `~/.claude/projects` and `~/.gitconfig` and carries a `Read(//…/**)` deny for every `denyRead` entry. `test_nightshift_run.py`: the `settings.json` a run writes denies the vault root and none of the four folders; the stub records its environment and a planted `SSH_AUTH_SOCK` is absent from it; `add` refuses an `order_workspace` under the vault and a tick fails such a queued item with the Needs-you line; the self-test fails on a recorded stream with a value line before `ENV_DONE` and passes on one with `ENV_DONE` alone. Each fails before the change. Bound tools: pytest and the gate.

## 5. Out of scope

- `~/.claude` denied wholesale (the plugin directory).
- The headless profile (S4, S10): `headless.settings.json` already carries its Read denies.
- `git ls-remote` in the self-test.
