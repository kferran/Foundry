# Crash alerts for the other eight core units (#436) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An unexpected failure in brief, debrief, intake, meetings, notify, sync, triage or update exits 70 and raises one alert a day naming the unit. Every handled failure keeps its exit and alert, and each unit's `PIPELINE_GAPS` line is deleted.

**Architecture:**
- Reuse S3's two handlers: `crash_trap` in `lib_fetch.sh` and `alerts.guard` in `vaultlib/alerts.py`.
- Add one variant, `crash_trap --exit-only`, for the two scripts that run without `-e`.
- Ship in three PRs grouped by risk (spec §3).

**Tech Stack:** bash, Python 3 stdlib, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-crash-alerts-core-units-design.md`

## Global Constraints

- **Exit codes and alerts:** every existing exit code, handled failure and alert stays (spec §2). `SuccessExitStatus` is unchanged (`units.bats` pins it).
- **Crash alert:** `<unit> crashed: <what>; journalctl --user -u <unit>`, once a day per unit, under the unit's existing tag: `intake` for intake, brief and debrief; `meetings`, `notify`, `sync`, `triage` and `update` for the others. `scripts.bats` checks every tag a writer uses.
- **Who alerts:** only the unit's own run. A `--check`, a person's command and a call from another script do not (the `alerting=` rule in `alerts.guard`, and the `(( check )) ||` pattern of `watch_fetch.sh:47`).
- **Core cap:** measured once per PR and raised in that PR with a comment naming this spec. Expect about 10 lines per PR.
- **Bats ruling R1:** no mid-test `!`, no `&&` assertion chains, no wall-clock assertions. Tests stub claude.
- **Change files:** one `changes/` file per PR, `- Changed: a crash in <units> now alerts (#436)`.
- **Delivery:** PR A (Tasks 1–4), PR B (Tasks 5–7), PR C (Tasks 8–10), each branched from master after the previous one merges. The owner merges each.

## Review Focus

1. In every trapped script, each command whose non-zero exit is expected sits in an `||` list, an `if`, or a `trap - ERR` window. Task 1, 5 and 8 each start with that audit, written into the PR body.
2. `run_headless.sh` names the unit running it (debrief, brief or intake), and its `set +e` windows are outside the ERR trap.
3. `vault_sync.sh --pre` and `--post` keep their exit mapping. `brief_run.sh` keeps passing `run_headless.sh`'s exit through.

## PR A: fetch scripts and intake

### Task 1: audit
- [ ] For `meetings_fetch.sh`, `triage_fetch.sh` and `notify.sh`, list every command that can exit non-zero without being an `||` list or an `if`, and confirm each is a stop today under `set -e`. Write the list in the PR body.

### Task 2: the trap in the three fetch scripts
- [ ] **Failing test**, one per suite (`meetings.bats`, `triage.bats`, `notify.bats`): a stub `jq` on `PATH` that exits 5 makes the run exit 70 and write one `[<tag>] foundry-<unit> crashed:` line.
- [ ] **Second test:** the script's usual failure path keeps its exit and alert.
- [ ] **Implement:** `(( check )) || crash_trap foundry-<unit>` after `FETCH_TAG` is set. `notify.sh` traps on every run.
- [ ] Run the suites and commit.

### Task 3: `alerts.guard` in `intake.py`
- [ ] **Failing pytest:** a monkeypatched step raises `RuntimeError`. A no-argument run returns 70 and writes one `[intake] foundry-intake crashed: RuntimeError` line, while `--quarantine` returns 70 with no alert.
- [ ] **Implement:** wrap the run in `alerts.guard(..., VAULT, "foundry-intake", "intake", alerting=not sys.argv[1:])`.
- [ ] Run and commit.

### Task 4: gaps, cap and PR
- [ ] Delete the `intake`, `meetings`, `notify` and `triage` lines from `PIPELINE_GAPS`, and run `bats system/tests/pipeline.bats`.
- [ ] Measure the core cap and raise it.
- [ ] Add the change file.
- [ ] Run lint, `/foundry-review`, and open PR A.

## PR B: `update_template.sh` and `run_headless.sh`

### Task 5: audit
- [ ] Same audit as Task 1 for both scripts.
- [ ] List `run_headless.sh`'s `set +e` windows (`:76`, `:132-135`, `:190-205`, `:230`).

### Task 6: `update_template.sh`
- [ ] **Failing test** in `remote.bats` (where `update_template.sh` is tested): an injected failure under `--unattended` exits 70 with one `[update] foundry-update crashed:` line. A conflict keeps exit 1 and its `[update]` alert. A manual run (no `--unattended`) does not alert.
- [ ] **Implement:** source `lib_fetch.sh`, set `FETCH_TAG=update`, and add `(( unattended )) && crash_trap foundry-update`, written as an `if` per R1.
- [ ] Run and commit.

### Task 7: `run_headless.sh`
- [ ] **Failing tests** in `headless.bats`: an injected failure outside the claude call exits 70 with `foundry-debrief crashed:` for `debrief`, `foundry-brief crashed:` for `brief`, and `foundry-intake crashed:` for `ingest`. A claude exit inside a `set +e` window keeps today's exit and alert.
- [ ] **Implement:** `crash_trap` with the unit picked from the command, plus `trap - ERR` and a restore around each `set +e` window.
- [ ] Delete the `debrief` and `update` gap lines.
- [ ] Measure the cap, add the change file, run `/foundry-review`, and open PR B.

## PR C: `brief_run.sh` and `vault_sync.sh`

### Task 8: `crash_trap --exit-only`
- [ ] **Failing test** in `scripts.bats`: a script without `-e` that sources `lib_fetch.sh` and calls `crash_trap --exit-only foundry-x`. A handled `false; echo ok` exits 0. An unset variable under `set -u` exits 70 with one alert. An explicit `exit 3` exits 3.
- [ ] **Implement:** the flag skips the ERR trap and keeps the TERM and EXIT traps.
- [ ] Run and commit.

### Task 9: the two scripts
- [ ] **Failing tests** in `headless.bats` (where `brief_run.sh` is tested) and `sync.bats`: an unset-variable crash exits 70 with one `[intake] foundry-brief crashed:` or `[sync] foundry-sync crashed:` line. `brief_run.sh` still passes through `run_headless.sh`'s exit 5. `vault_sync.sh --pre` still maps exits to 0 or 3, and `--post` still exits 0.
- [ ] **Implement:** source `lib_fetch.sh` where it is missing, set `FETCH_TAG`, and call `crash_trap --exit-only foundry-<unit>` for the unit's own run.
- [ ] Run and commit.

### Task 10: close
- [ ] Delete the `brief` and `sync` gap lines. `PIPELINE_GAPS` is then empty.
- [ ] Measure the cap, add the change file, run the full gate where the host allows, run `/foundry-review`, and open PR C.
- [ ] On merge, tick the F6 gaps on #436.
