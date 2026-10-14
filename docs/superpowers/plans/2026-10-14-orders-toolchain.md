# Orders Toolchain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A codebase can declare, in `system/codebases/<name>.md`, the directories its toolchain lives in (`order_toolchain`) and one install command (`order_install`); the sealed verify sees those directories first on its PATH with the rest of `$HOME` still empty, the install runs once before verify with the network open, and the plan session's own PATH starts with the same directories.

**Architecture:** `nightshift_deliver.bwrap()` gains `toolchain` and `net` parameters (read-only binds after the `$HOME` tmpfs, PATH built from the directories, `--unshare-net` dropped for the install step); `run_verify` carries them and a failure-line label, `run_install` is `run_verify` on one command with the network; `verify_sha` runs the install before the verify commands. `nightshift_check` gains one helper, `toolchain(cb)`, that expands the directories, and two readiness errors. `nightshift_run` reads both keys with `cb.get` in `_deliver_plan` and prepends the directories to the `Popen` environment's PATH in `_run_session`. The schema, the manual and the codebase example name the keys.

**Tech Stack:** Python 3 (`vaultlib`), bubblewrap, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-13-orders-toolchain-design.md` (issue #138; owner decisions 2026-10-14: open network for the install command, toolchain directories also on the session's PATH).

## Global Constraints

- Work on branch `feat/orders-toolchain` in worktree `.scratch/toolchain`. Commit there; do not push or open a pull request.
- Run one suite at a time through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, outside a sandbox. Never run the gate from this worktree.
- Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_check.py`, `test_nightshift_run.py`, `test_schema_notes.py`), bats (`commands.bats`, `nightshift.bats`, `vault_integrity.bats`), the gate (run by the main session).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Tests need no network and no real toolchain: a stub script in a temporary directory stands in for the tool; the network decision is checked on the bwrap argument list.
- Read the keys with the codebase getter only (`cb.get`); the keys are new and have no `nightshift_*` names.
- Do not change `nightshift_session.profile()` or `session_env()` (another branch owns them); the session's PATH change lives in `_run_session`.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- The read-only binds come after `--tmpfs $HOME` in the argv, so a listed directory under `$HOME` is visible and a `.netrc` beside it is not.
- The install argv has no `--unshare-net`; every verify argv has it. The install never runs when the key is absent, and a failing install stops before the first verify command.
- An install failure reaches the Needs-you line as `Fix the failing check: order_install: <command>: exit <code>`, with the exit 127 wording when the command is not found.
- `verify_sha` is monkeypatched as `lambda *a: (True, "")` in two runner tests: the new arguments are passed positionally.
- A codebase without the keys runs today's sandbox and passes readiness as before.

---

### Task 1: `bwrap`, `run_verify`, `run_install` and `verify_sha`

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_deliver.py`
- Test: `system/tests/python/test_nightshift_deliver.py` (after `test_verify_exit_127_names_the_sealed_sandbox_as_the_cause`)

**Interfaces:**
- `bwrap(workdir, cmd, toolchain=(), net=False) -> list`: `--ro-bind <d> <d>` per directory after `--tmpfs $HOME`; `PATH` is the directories then `/usr/local/bin:/usr/bin:/bin`; `--unshare-net` only when `net` is false.
- `run_verify(clone, cmds, log_path, timeout=1800, toolchain=(), net=False, label="") -> (ok, out)`: the failure line is `{label}{cmd}: exit {code}{why}`.
- `run_install(clone, cmd, toolchain, log_path) -> (ok, out)`: `run_verify` on `[cmd]` with `net=True` and `label="order_install: "`.
- `verify_sha(runner_repo, sha, vdir, cmds, log_path, lfs_store="", install="", toolchain=())`: runs `run_install` first when `install` is set.

- [ ] **Step 1: Write the tests** (spec §4):
  - `test_bwrap_binds_the_toolchain_after_home_and_opens_the_network_only_for_install` (argv): `--unshare-net` in `bwrap(d, "x")`, absent from `bwrap(d, "x", net=True)`; with `toolchain=["/opt/a/bin", "/opt/b/bin"]` each `--ro-bind` pair comes after `--tmpfs <home>` and before `--bind <workdir>`, and the `PATH` value is `/opt/a/bin:/opt/b/bin:/usr/local/bin:/usr/bin:/bin`.
  - `test_toolchain_dirs_are_visible_and_first_on_path_while_home_stays_empty` (bwrap): a `hello-tool` script under `<home>/.tools/bin`, a `.netrc` under `<home>`, `HOME` set to `<home>`; `run_verify` with `toolchain=[<home>/.tools/bin]` passes `hello-tool`, `test ! -e "$HOME/.netrc"` and a check that `${PATH%%:*}` is the directory.
  - `test_verify_sha_runs_the_install_first_with_network_and_keeps_it_out_of_the_commit` (bwrap): a spy on `nd.bwrap` records `(cmd, toolchain, net)`; install `echo "$PATH" | tee installed`, verify `test -f installed`; passes; the spy saw the install with `net=True` then the verify with `net=False`; `git ls-tree` of the sha has no `installed`; `verify.log` has `$ echo` before `$ test`.
  - `test_a_failing_install_blocks_before_verify_with_the_exit_127_wording` (bwrap): install `no-such-tool-xyz install`, verify `touch ran-verify`; the first output line is `order_install: no-such-tool-xyz install: exit 127 (command not found in the sealed verify sandbox)` and the log has no `$ touch`.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/python/test_nightshift_deliver.py -k "bwrap or toolchain or install"`. Expected: TypeError on the new keyword arguments.
- [ ] **Step 3: Implement** the four signatures above; the `# 127:` comment names the toolchain binds.
- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/python/test_nightshift_deliver.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): bwrap binds a codebase's toolchain and runs its install with the network`.

### Task 2: Readiness refuses a missing toolchain directory

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py`
- Test: `system/tests/python/test_nightshift_check.py` (after `test_a_codebase_plan_needs_order_pr_or_its_old_name`; `set_codebase` writes values with `json.dumps` so a list stays a list)

**Interfaces:**
- `toolchain(cb) -> list`: the codebase's `order_toolchain` entries, `~` expanded, as strings, in the listed order; a scalar value is one entry.
- `_plan` errors: `codebase <repo>: order_toolchain <dir> is not a directory`; `codebase <repo>: order_install must be one command (a string)`.

- [ ] **Step 1: Write the test** `test_a_codebase_plan_refuses_a_missing_toolchain_dir_and_a_list_valued_install`: with `order_pr` set and `order_toolchain: [<tmp_path>/tools]` (an existing directory) and `order_install: "true"`, `check` is `[]`; with `order_toolchain: [<tmp_path>/gone]` an error names `order_toolchain` and the path; with `order_install: ["a", "b"]` an error names `order_install`; `nc.toolchain({"order_toolchain": ["~/x"]})` ends with `/x` and does not start with `~`.
- [ ] **Step 2: Run it to verify it fails.** Expected: no `toolchain` attribute, then no error for the missing directory.
- [ ] **Step 3: Implement** `toolchain()` and the two checks after the `order_pr` check in `_plan`, reading `cb.get` only.
- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/python/test_nightshift_check.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): readiness refuses a missing order_toolchain directory`.

### Task 3: The runner passes the keys and the session sees the toolchain

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py`
- Test: `system/tests/python/test_nightshift_run.py` (after `test_protected_files_reach_the_pushed_branch`)

**Interfaces:**
- `_deliver_plan`: `cb = nc.codebase(ctx.vault, fm["repo"]) or {}`; `verify_sha(..., nc.lfs_store(src), str(cb.get("order_install") or ""), nc.toolchain(cb))`, positionally.
- `_run_session`: `env = dict(os.environ)` with the toolchain directories prepended to `PATH`, passed as `env=` to `Popen`.

- [ ] **Step 1: Write the tests.** A helper `codebase_item(vault, tmp_path, **keys)`: `registered(vault, tmp_path / "cb")`, `docs/p.md` (the `PLAN`) committed on `main` in the clone and pushed to its bare origin, `set_codebase(order_pr="github:o/shop", **keys)`, `add --repo shop --base main --plan docs/p.md --tasks 1-2 --verify "test -f done.txt" --verify "test -f installed" --now`.
  - `test_a_codebase_item_runs_its_install_before_verify_and_the_session_sees_the_toolchain` (bwrap): a `hello-tool` script in `<tmp>/tools`; `order_toolchain: [<tmp>/tools]`, `order_install: "hello-tool > installed"`; `NIGHTSHIFT_STUB_SHELL` writes `$PATH` to `<tmp>/path.txt` before the commit; the tick ends `done`; `verify.log` lists `$ hello-tool > installed` before `$ test -f done.txt`; `path.txt` starts with `<tmp>/tools:`.
  - `test_a_codebase_without_the_keys_runs_no_install` (bwrap): no keys, verify `test -f done.txt` only; the tick ends `done` and `verify.log` has exactly one `$ ` line.
- [ ] **Step 2: Run them to verify they fail.** Expected: `blocked (verify)` on `installed`, and `path.txt` starting with the fixture's `bin` directory.
- [ ] **Step 3: Implement** the two changes.
- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/python/test_nightshift_run.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): the runner passes order_install and order_toolchain; the session's PATH starts with the toolchain`.

### Task 4: Schema

**Files:**
- Modify: `system/schemas/codebase.md`
- Test: `system/tests/python/test_schema_notes.py` (after `test_config_meeting_keys`)

- [ ] **Step 1: Write the test** `test_codebase_schema_accepts_the_toolchain_keys`: a codebase note with `path` set to `tmp_path`, `order_toolchain: ["~/.tools/bin"]` and `order_install: "true"` validates as `codebase` with no issue at all.
- [ ] **Step 2: Run it to verify it fails.** Expected: two `unknown field` warnings.
- [ ] **Step 3: Implement:** `order_toolchain: {kind: list, of: string}` and `order_install: {kind: string}` after `order_pr`, and one body sentence for each.
- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/python/test_schema_notes.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(orders): the codebase schema takes order_toolchain and order_install`.

### Task 5: Documents

**Files:**
- Modify: `FOUNDRY.md` (the Work Orders paragraph), `system/codebases/example.md` (body), `docs/superpowers/specs/2026-10-13-orders-toolchain-design.md` (Status, the two owner decisions, `nc.setting` to `cb.get`)
- Test: `system/tests/commands.bats` (after "Work Orders: the /order skill, CLAUDE.md, the README and the schemas use the new names")

- [ ] **Step 1: Write the test** `Work Orders: the manual, the schema and the codebase example name order_toolchain and order_install (orders toolchain spec §3)`: `FOUNDRY.md` has `` `order_toolchain` ``, `` `order_install` `` and `a shim directory that needs its manager's environment does not work`; `system/schemas/codebase.md` has `^  order_toolchain:` and `^  order_install:`; `system/codebases/example.md` has both key names.
- [ ] **Step 2: Run it to verify it fails.** `system/scripts/test.sh system/tests/commands.bats -f 'order_toolchain'`.
- [ ] **Step 3: Write the sentences:** the sealed-verify sentence in the Work Orders paragraph gains the two keys, the shim sentence and the readiness refusal; the example's body gains one paragraph with both keys; the spec records the owner's decisions and the getter.
- [ ] **Step 4: Run `commands.bats`, `nightshift.bats` and `vault_integrity.bats`.** Expected: PASS.
- [ ] **Step 5: Commit.** `docs(orders): order_toolchain and order_install in the manual, the example and the spec`.
