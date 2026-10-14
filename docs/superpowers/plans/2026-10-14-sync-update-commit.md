# Sync Commit in the Update and Past a Refused Run: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `update_template.sh --unattended` commits a dirty tree the way the sync does and then merges (audit C4), and the sync carries on past a published run the pre-commit hook refuses, leaving that run's notes out of the sync commit (audit C7).

**Architecture:** The sync's commit step (`commit_runs.py`, `git add -A`, the scripted `sync(<role>)` message, a reset on refusal) moves from `vault_sync.sh` into `lib_git.sh` as `git_sync_commit <role>`, called by `vault_sync.sh` and by the unattended update in place of the clean-tree die. `commit_runs.py` continues past a refused run, prints `refused <run_id> <path>` lines and alerts once a day per run through a `<run dir>/refused` marker; `git_sync_commit` excludes those paths from the sync commit and reports them in `GIT_SYNC_REFUSED`.

**Tech Stack:** bash, Python 3, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-audit-update-dirty-tree-design.md` (C4) and `docs/superpowers/specs/2026-10-13-audit-sync-refused-commit-design.md` (C7), built in that order because both touch `system/scripts/vault_sync.sh`.

## Global Constraints

- Work on branch `feat/sync-update-commit` in worktree `.scratch/syncfix`. Commit there; do not push or open a pull request.
- Run one suite at a time through `system/scripts/test.sh <suite.bats | pytest path> [args…]`. The gate (`verify_setup.sh`) is the main session's.
- Bound tools: bats (`sync.bats`, `remote.bats`, `commands.bats`, `units.bats`, `lib.bats`), pytest (`test_commit_runs.py`), the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- `git_sync_commit` runs under `set -e` in `update_template.sh` and without it in `vault_sync.sh`: every command that can fail is guarded.
- Every git child of the commit step runs with run.lock's fd 9 closed (`9>&-`), `commit_runs.py` included.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- The sync commit message is byte-identical after the move (`sync.bats` "local changes get one scripted sync commit" passes unchanged).
- The unattended update commits before the fetch and under `run.lock`; the interactive update still refuses a dirty tree (`remote.bats` "refuses a dirty working tree before fetching" passes unchanged).
- A hook refusal of the sync commit stops the update with the hook's first line and nothing fetched; the refused note stays uncommitted and unstaged.
- `commit_runs.py` exits 1 with `refused` lines only when a run was refused; exit 1 without them, or exit 2, still maps to `fail commit`.
- The `[commit_runs]` alert for one refused run is written once a day, and a later successful commit removes the marker.
- The refused paths stay modified and unstaged after the sync commit, and `origin` changing one of them ends the next cycle in `fail merge`.

---

### Task 1: `git_sync_commit` in `lib_git.sh`, called by `vault_sync.sh` (C4 §3)

**Files:**
- Modify: `system/scripts/lib_git.sh`, `system/scripts/vault_sync.sh`
- Test: `system/tests/sync.bats` (the existing commit cases)

**Interfaces:**
- Produces: `git_sync_commit <role>`: runs `system/scripts/commit_runs.py`, `git add -A`, one `sync(<role>): N file(s)` commit with the `Foundry-Command: sync` and `Foundry-Role` trailers when anything is staged. Returns 0; on a refusal unstages, sets `GIT_SYNC_ERROR` and returns 1. Every git child runs with fd 9 closed.
- Consumes (in `vault_sync.sh`): `git_sync_commit "$role" || fail commit "$GIT_SYNC_ERROR"`.

- [ ] **Step 1: Run the commit cases red against the plan.** This task moves code; its tests are the existing `sync.bats` cases "local changes get one scripted sync commit", "commit_runs.py runs first", "a commit the hook refuses is unstaged and alerted, exit 1" and "no git child inherits run.lock's fd 9". Extend the fd 9 case with a pending published run (`commit_runs.py`'s own git children must lose fd 9; today its call does not close it). Run `system/scripts/test.sh system/tests/sync.bats -f 'fd 9'`. Expected: FAIL.
- [ ] **Step 2: Implement.** Move `sync_message` (as `git_sync_message <role>`) and the commit step into `lib_git.sh` as `git_sync_commit`; `command git … 9>&-` for every call, `system/scripts/commit_runs.py > /dev/null 9>&-`; `vault_sync.sh` sources it already and calls it.
- [ ] **Step 3: Run the suite.** `system/scripts/test.sh system/tests/sync.bats`. Expected: PASS, every commit case unchanged.
- [ ] **Step 4: Commit.** `refactor(sync): the sync commit step moves to lib_git.sh as git_sync_commit`.

### Task 2: The unattended update commits before it merges (C4 §2, §4)

**Files:**
- Modify: `system/scripts/update_template.sh`, `system/systemd/foundry-update.service.in`, `FOUNDRY.md`, `docs/superpowers/specs/2026-10-09-auto-update-design.md`
- Test: `system/tests/remote.bats` (the `--unattended` cases)

**Interfaces:**
- Consumes: `git_sync_commit "$role"` under `run.lock`, before the fetch, in `--unattended` only.
- Produces: alert `template update failed: the sync commit was refused: <hook line>` and exit 1 on a refusal, nothing fetched; the success alert names the commits made first.

- [ ] **Step 1: Write the tests.** Rewrite "--unattended fails with an alert on uncommitted changes and never commits them (#87)" as "--unattended commits uncommitted changes as the sync does, then merges (audit C4 spec §4)": a new note and a pending published run (`commit_runs.since` far in the past, a run dir with `publish.json`, the briefing file); exit 0, `git log --first-parent --format=%s -3` is the merge, `sync(standalone): 1 file(s)`, `brief 2026-10-04: briefings/2026-10-04.md`; the update alert names both commits. Add "--unattended stops on a note the hook refuses, before fetching (audit C4 spec §4)": hooks installed, an invalid note; exit 1, no `refs/remotes/template`, the note untracked and unstaged, alert `template update failed: the sync commit was refused:`. Add "--unattended: no git child of the commit step inherits run.lock's fd 9 (audit C4 spec §4)": `stub_git` on `PATH` with `WRAP_EACH`, a pending run and a dirty note. Keep "update_template refuses a dirty working tree before fetching".
- [ ] **Step 2: Run them red.** `system/scripts/test.sh system/tests/remote.bats -f 'unattended'`. Expected: the three new cases FAIL.
- [ ] **Step 3: Implement.** `source system/scripts/lib_git.sh`; `role` from config; in `--unattended` the clean-tree `die` becomes `git_sync_commit "$role" || die 1 "the sync commit was refused: $GIT_SYNC_ERROR"`, with `HEAD` recorded before it so the success alert can list the subjects committed; the interactive branch keeps the porcelain check. The unit comment names the commit. `FOUNDRY.md` Updating bullet: "refuses uncommitted changes" becomes the commit, the clean-tree sentence goes; the #87 spec's three stale lines get the new rule.
- [ ] **Step 4: Run the suites.** `remote.bats`, `commands.bats`, `units.bats`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(update): --unattended commits a dirty tree as the sync does, then merges` with the Ruling on the rewritten #87 test.

### Task 3: `commit_runs.py` carries on past a refused run (C7 §2, §4)

**Files:**
- Modify: `system/scripts/commit_runs.py`
- Test: `system/tests/python/test_commit_runs.py`

**Interfaces:**
- Produces: stdout `refused <run_id> <path>` per path of a refused run; exit 1 at the end when any run was refused; `<run dir>/refused` (JSON: `day`, `error`) written with the alert, the alert skipped while the marker holds today's day, the marker removed by a later successful commit.

- [ ] **Step 1: Write the tests.** Flip `test_a_hook_failure_alerts_leaves_the_run_pending_and_stops` into `test_a_refused_run_stays_pending_and_the_later_run_is_committed`: exit 1, stdout has `refused <BRIEF> wiki/work/concepts/Bad.md`, `ING` committed with its marker, `BRIEF` without, one alert. Add `test_a_refused_run_alerts_once_a_day`: a second call adds no alert line; the marker's day rewritten to yesterday, a third call adds one. Add `test_a_run_committed_after_a_refusal_has_no_refused_marker`: fix the note, rerun, exit 0, no `refused` file.
- [ ] **Step 2: Run them red.** `system/scripts/test.sh system/tests/python/test_commit_runs.py -k 'refused'`. Expected: FAIL.
- [ ] **Step 3: Implement.** In `main`, on `error`: alert unless the marker holds today, write the marker, print the `refused` lines, set `refused = True`, `continue`; on success `unlink` the marker; return `1 if refused else 0`.
- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/python/test_commit_runs.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(commit_runs): a refused run stays pending and the later runs are committed`.

### Task 4: The sync leaves refused paths out and goes on (C7 §2, §4)

**Files:**
- Modify: `system/scripts/lib_git.sh`, `system/scripts/update_template.sh`, `.claude/commands/backup.md`, `FOUNDRY.md`, `docs/superpowers/specs/2026-10-03-two-machines-design.md`
- Test: `system/tests/sync.bats` (after "a commit the hook refuses is unstaged and alerted, exit 1"), `system/tests/remote.bats`

**Interfaces:**
- Produces: `git_sync_commit` captures `commit_runs.py`'s stdout, sets `GIT_SYNC_REFUSED` (one path per line) and stages with `git add -A -- . ':!<path>'…`; exit 1 without `refused` lines, or exit 2, is still a return 1. `update_template.sh --unattended` dies on a non-empty `GIT_SYNC_REFUSED` (C7 §3 cross-reference).

- [ ] **Step 1: Write the tests.** `sync.bats`: "a run the hook refuses is left out of the sync commit and the cycle goes on (audit C7 spec §4)": a pending run whose note is invalid plus an edit to `Kafka.md`; exit 0, the edit pushed, the note untracked and unstaged, one `[commit_runs]` alert, no `[sync]` alert. "origin changing a refused note ends the next cycle in fail merge (audit C7 spec §4)": the same, then the client pushes a note of that name; exit 1, `sync failed (merge)`. "commit_runs.py exiting 1 without a refused line is still fail commit (audit C7 spec §4)": a stub `commit_runs.py` that exits 1. `remote.bats`: "--unattended stops on a published run the hook refused (audit C7 spec §3)": exit 1, alert names the path, no `refs/remotes/template`.
- [ ] **Step 2: Run them red.** `system/scripts/test.sh system/tests/sync.bats -f 'C7'`, then `remote.bats -f 'C7'`. Expected: FAIL.
- [ ] **Step 3: Implement.** The capture, the pathspec array, the exit mapping in `git_sync_commit`; the `die` in `update_template.sh`; `backup.md` step 3; the sync sentence in `FOUNDRY.md` Machine roles; the two-machines spec §5.1 steps 1 and 2.
- [ ] **Step 4: Run the suites.** `sync.bats`, `remote.bats`, `commands.bats`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(sync): a refused run stays behind and the cycle goes on`.
