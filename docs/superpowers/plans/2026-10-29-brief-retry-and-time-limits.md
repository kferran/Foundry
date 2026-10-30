# Brief retry and unit time limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A brief the publish gate rejects gets one fresh run before anyone is told, and every unit's `TimeoutStartSec` holds its worst case, so `TIMING_OVERRUNS` is empty.

**Architecture:** A small wrapper, `brief_run.sh`, becomes the brief unit's `ExecStart`: it runs the prep and the brief, and on exit 5 runs both once more. Intake bounds ingest's lock wait and ends a tick on a busy lock. Each unit's limit rises to its `conformance.bats` sum; the smoke check stops starting telemetry rows when its budget runs short.

**Tech Stack:** bash, Python (`vaultlib/intake.py`), systemd unit templates, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-brief-retry-and-time-limits-design.md` (approved by the owner's merge of #419, 2026-10-29)

## Global Constraints

- Run only the changed files' suites locally; CI is the gate.
- Unit templates, `run_headless.sh` and `install_units.sh` change: the owner merges the PR.
- No `/setup`, `install_units.sh`, `install_hooks.sh`, `update_template.sh` or `vault_sync.sh` runs against a real session; `units.bats` renders into its own temp directory.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.

## Rulings against the spec

- **Ruling 1, the retry is a wrapper, not `Restart=`** (spec §3.1 named systemd's restart): with `Restart=on-failure`, a timeout kill restarts too, so only a start limit bounds a hung brief; a one-day limit would also refuse the owner's manual rerun until `systemctl --user reset-failed`; and the server's drop-in replaces `ExecStartPre`. A wrapper retries exactly once, on exit 5 only, holds no lock while the prep runs, and gives each run its own process and ledger line. Cost if wrong: the wrapper is one more script in core.
- **Ruling 2, ingest waits 60 s for `run.lock`, not `HEADLESS_LOCK_WAIT`** (spec §3.2): 1,400 s × 5 runs would add 7,000 s to an intake tick; a busy lock already ends the tick, and the inputs wait 5 minutes for the next one. Cost if wrong: an ingest behind a long brief starts one tick later.

- **Ruling 3, the scaffold test tolerates a smoke overrun the way it tolerates the brief's** (found by CI after the plan): on master the smoke unit's known-overrun line hid the 360 s a scaffolded source adds; with smoke now at 3,150 of 3,300 s, `test_new_source.py::test_a_scaffold_passes_the_line` sees `smoke: 3510 s of waits against a 3300 s limit`. A new source's smoke row past `SMOKE_BUDGET` is skipped at run time with one line, so the overrun is left to that source's own CI run, as the brief's is (§5 item 3): one regex in the test, no limit raised. Cost if wrong: the next source PR has to raise the smoke limit or add a known-overrun line.

## Review Focus

1. A brief rejected twice: one "rejected twice" alert, and the second run's own rejection alert; no third run.
2. A brief that exits 4 (usage limit) or 1: no retry, the alert it raises today.
3. The server drop-in: `vault_sync.sh --pre`, then the wrapper (which runs the prep), then `--post`; the prep is not run twice.
4. An intake tick whose ingest finds `run.lock` busy: exit 6, the tick ends, no batch split, no "will retry" alert.
5. A smoke run with several telemetry sources: rows past the budget are skipped with their line; the timer and unit-drift rows still run.

---

### Task 1: The brief wrapper

**Files:**
- Create: `system/scripts/brief_run.sh`
- Modify: `system/systemd/foundry-brief.service.in`, `system/scripts/install_units.sh` (`DROPIN_PREP[foundry-brief]`, `DROPIN_TIMEOUT[foundry-brief]`), `system/scripts/run_headless.sh` (no rejection alert when `BRIEF_RETRY_PENDING=1`)
- Test: `system/tests/headless.bats`, `system/tests/units.bats`

- [ ] **Step 1: Failing tests.** `headless.bats` "a rejected brief runs once more and publishes": a stub `run_headless.sh` exits 5 then 0; `brief_run.sh` exits 0, ran the prep twice, and raised no alert. "a brief rejected twice raises one alert and runs no third time": exits 5, 5; `brief_run.sh` exits 5; one `[intake] the brief was rejected twice` line; two runs. "a brief that exits 4 or 1 is not retried": one run each. `units.bats`: the brief unit's `ExecStart` is `brief_run.sh` with no `ExecStartPre`; the drop-in has `vault_sync.sh --pre`, the wrapper, `--post`; limits 110 min and 125 min.
- [ ] **Step 2:** Run them; they fail (no wrapper).
- [ ] **Step 3:** Write `brief_run.sh` (prep with its failure ignored, as `ExecStartPre=-` did; brief with `BRIEF_RETRY_PENDING=1` on the first run; on exit 5, wait `BRIEF_RETRY_WAIT` (60 s), prep and brief again; a second 5 alerts once and exits 5). The unit and the drop-in follow. `run_headless.sh` skips the rejection alert line when `BRIEF_RETRY_PENDING=1` and logs it.
- [ ] **Step 4:** Run `headless.bats` and `units.bats`; they pass.
- [ ] **Step 5:** Commit.

### Task 2: Intake's lock wait

**Files:** Modify `system/scripts/run_headless.sh` (ingest `flock -w "${INGEST_LOCK_WAIT:-60}" 9`), `system/scripts/vaultlib/intake.py` (exit 6 ends the tick like `CAP_EXIT`), `system/systemd/foundry-intake.service.in`, `install_units.sh` drop-in. Test: `system/tests/python/test_intake.py`, `system/tests/units.bats`.

- [ ] **Step 1: Failing tests.** `test_intake.py`: an inbox ingest whose stub exits 6 leaves its input, starts no further run and raises no "will retry" alert; a digest batch whose stub exits 6 is not split. `units.bats`: intake 130 min, drop-in 145 min.
- [ ] **Step 2-4:** Fail, implement, pass.
- [ ] **Step 5:** Commit.

### Task 3: Smoke budget, watch and row limits

**Files:** Modify `system/systemd/foundry-smoke.service.in` (`Environment=SMOKE_BUDGET=…`, `TimeoutStartSec`), `system/scripts/smoke_check.sh` (skip a telemetry row the budget cannot hold), the smoke calendar row timeout, the intraday watch unit, manifest prose and `watch_fetch.sh` comment, the smoke watch row timeout. Test: the smoke bats suite, `extensions/intraday/tests`.

- [ ] **Step 1: Failing test.** A smoke run with `SMOKE_BUDGET` short of a telemetry row's limit prints `smoke: time left too short for <row>; skipped` and still runs the timer and unit rows.
- [ ] **Step 2-4:** Fail, implement, pass.
- [ ] **Step 5:** Commit.

### Task 4: The timing table

**Files:** Modify `system/tests/conformance.bats` (`TIMING_VALUES` for `brief_run.sh`, `ingest.lock`, `SMOKE_BUDGET`; `TIMING_STEPS` brief × 2 with the wait, intake runs × (`ingest.lock` + `headless`); `TIMING_OVERRUNS` empty; the unbounded-wait comment removed).

- [ ] **Step 1:** Edit the table; run `conformance.bats`; every unit fits and no overrun line remains.
- [ ] **Step 2:** Change file `changes/2026-10-29-feat-brief-retry-time-limits.md`; FOUNDRY.md's brief and intake paragraphs name the retry and the lock wait.
- [ ] **Step 3:** Run the changed suites; commit; open the PR (owner merges).
