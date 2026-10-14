# Stage Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two concurrent `vault_index.py stage` calls in one headless run both land in `snapshot.json`, and a publish that held back a changed note (`status: conflict`) counts as a success whose alert names the held-back paths.

**Architecture:** `publish.record_stage` holds an exclusive `fcntl.flock` on `<run dir>/stage.lock` from the snapshot load to the write. `publish_cli.OK_STATUSES` gains `conflict`, so the commit exits 0; `run_headless.sh` reads `.status` and `.conflicts` from the `publish.json` it already summarises and alerts the held-back paths. No new exit code, no change to the gate's checks, no retry of a held-back note (owner decision 2026-10-14).

**Tech Stack:** Python (`fcntl`), bash, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-13-audit-stage-lock-design.md` (audit C1 + C2, issue #136)

## Global Constraints

- Work on branch `feat/stage-lock` in worktree `.scratch/stagelock`. Commit there; do not push or open a pull request.
- Run the suites from the repository root through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, which sets the gate's environment, outside a sandbox. The gate is `system/scripts/verify_setup.sh` and the main session runs it.
- Bound tools: pytest (`test_publish.py`, `test_stage_cli.py`), bats (`headless.bats`, `commands.bats`, `scripts.bats`), the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- The gate's checks (`_check`, `_conflict`, `_apply`) do not change. The three exit-code exclusion lists (`write_ledger`'s jq, `runs_today`, `NOT_INPUT_FAULT`) do not change.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- The lock path is built only after `check_run_id`, so an unchecked run id never names a lock file outside `system/logs/runs/`.
- The lock is released on every path (a `with` block over the handle), including a `PublishError` raised under it.
- An unknown run still raises `PublishError`, never `FileNotFoundError` from the lock open.
- `publish_cli` exit codes: `conflict` 0; `rejected` and `empty` stay 5.
- The alert names the run id and every held-back path, and only a `conflict` status produces it.
- `recover`, `nightshift_deliver.publish_research` and the meeting import are untouched (spec §3, §5).

---

### Task 1: The lock in `record_stage`

**Files:**
- Modify: `system/scripts/vaultlib/publish.py` (`record_stage`)
- Test: `system/tests/python/test_publish.py` (after `test_record_stage_refuses_non_targets_and_unknown_runs`), `system/tests/python/test_stage_cli.py` (after `test_stage_subcommand`)

**Interfaces:**
- Produces: `<run dir>/stage.lock`, created on the first `record_stage` of a run and held exclusively while `snapshot.json` is loaded, the note copied and the snapshot written.

- [ ] **Step 1: Write the tests.** `test_publish.py`: patch `publish._write_json` with a wrapper that opens `<run dir>/stage.lock` on a fresh descriptor and asserts `fcntl.flock(fd, LOCK_EX | LOCK_NB)` raises `BlockingIOError`, then calls the real writer; `record_stage` must have called it once. `test_stage_cli.py`: write 20 concept notes under `wiki/work/concepts/`, snapshot, start 20 `vault_index.py stage` subprocesses with `Popen` (the `cli` fixture's argv and environment), wait for all, assert every exit is 0 and `snapshot.json` holds 20 `staged` entries.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/python/test_publish.py -k stage_lock` (expected: `DID NOT RAISE`) and `system/scripts/test.sh system/tests/python/test_stage_cli.py -k concurrent` (expected: fewer than 20 entries on most runs; the spec says the race is probabilistic, so run it more than once and record what was seen).
- [ ] **Step 3: Implement.** `check_run_id(run_id)`; `rd = run_dir(vault, run_id)`; `PublishError("unknown run")` when `rd / "snapshot.json"` is not a file; `with open(rd / "stage.lock", "w") as handle: fcntl.flock(handle.fileno(), fcntl.LOCK_EX)` and the existing body from `load_snapshot` to `_write_json` under it.
- [ ] **Step 4: Run the suites.** `test_publish.py`, `test_stage_cli.py`, `test_publish_commit.py`, `test_cli.py`.
- [ ] **Step 5: Commit.** `fix(publish): record_stage holds stage.lock across load, copy and write`.

### Task 2: `conflict` is a successful publish

**Files:**
- Modify: `system/scripts/vaultlib/publish_cli.py` (`OK_STATUSES`)
- Test: `system/tests/python/test_stage_cli.py` (after `test_publish_cli_exit_codes`)

**Interfaces:**
- Produces: `publish_staged.py commit` exits 0 on `status: conflict`; `rejected` and `empty` keep 5.

- [ ] **Step 1: Write the test.** Through the copied script: snapshot, stage a new note with its decision, make `wiki/work/concepts` read-only (`chmod 555`; skip as root), commit. Validation passes, the rename raises `PermissionError`, `_apply` holds the note back and the report is `conflict`. Assert exit 0 and `status == "conflict"`, `conflicts == [target]`. In the same test, a `-brief-` run with nothing staged commits `empty` with exit 5. Restore the mode in a `finally`.
- [ ] **Step 2: Run it to verify it fails.** `system/scripts/test.sh system/tests/python/test_stage_cli.py -k conflict`. Expected: exit 5 asserted as 0.
- [ ] **Step 3: Implement.** Add `"conflict"` to `OK_STATUSES`.
- [ ] **Step 4: Run the suite.** `test_stage_cli.py`.
- [ ] **Step 5: Commit.** `fix(publish): a conflict publish exits 0`.

### Task 3: The held-back alert

**Files:**
- Modify: `system/scripts/run_headless.sh` (after `publish_staged.py commit`)
- Test: `system/tests/headless.bats` (after "successful ingest publishes with provenance and writes a ledger line")

**Interfaces:**
- Consumes: `system/logs/runs/<run_id>/publish.json` (`.status`, `.conflicts`).
- Produces: one alert line `<cmd> <run_id>: published; held back <paths> (changed during the run; staged copies in system/quarantine/<run_id>/staged/)`, paths joined by `, `.

- [ ] **Step 1: Write the test.** Replace `$V/system/scripts/publish_staged.py` with a stub: `recover` prints `{}`; `snapshot` creates `wiki/.staging/<run_id>/` and `system/logs/runs/<run_id>/`; `abort` exits 0; `commit` writes `publish.json` with `status: conflict`, `conflicts: ["wiki/work/concepts/New.md"]`, `published: []`, `problems: []` and exits 0. Run `ingest`: status 0, `.publish.conflicts[0]` in the ledger is the path, one alert line holds the run id, the path and `system/quarantine/<run_id>/staged/`, and `stream.jsonl` is gone.
- [ ] **Step 2: Run it to verify it fails.** `system/scripts/test.sh system/tests/headless.bats -f 'held back'`. Expected: FAIL on the alert grep (no line is written today).
- [ ] **Step 3: Implement.** In the `prc == 0` branch, inside the `set +e` window: `held="$(jq -r 'select(.status == "conflict") | (.conflicts // []) | map(strings) | join(", ")' "system/logs/runs/$run_id/publish.json" 2>/dev/null)"`; `[[ -z "$held" ]] || alert "…"`.
- [ ] **Step 4: Run the suites.** `headless.bats`, `scripts.bats`.
- [ ] **Step 5: Commit.** `feat(headless): alert the held-back paths of a conflict publish`.

### Task 4: Documents

**Files:**
- Modify: `FOUNDRY.md` (Daily use, Publish step), `docs/superpowers/specs/2026-09-30-vault-template-design.md` (§6.3 exit codes, §6.20 commit phase), `docs/superpowers/specs/2026-10-13-audit-stage-lock-design.md` (status, owner decision)

- [ ] **Step 1: Write the sentences.** `FOUNDRY.md` after "your edit is kept": a note you edited while the gate was renaming is held back, the rest publishes, and the alert names the staged copy under `system/quarantine/<run_id>/staged/`. Template spec §6.3: exit 5 is a rejected or empty publish; §6.20 step 3: the held-back note is alerted and the run succeeds. Audit spec: status accepted, owner decision recorded.
- [ ] **Step 2: Run `commands.bats`.**
- [ ] **Step 3: Commit.** `docs(publish): held-back notes in the manual and the specs`.
