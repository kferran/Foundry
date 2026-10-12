# Usage Ceiling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every unattended session except the brief and the debrief is held while the 5-hour usage reading is at or above `order_max_five_hour`, and the reading is refreshed by every headless run.

**Architecture:** `run_headless.sh` records usage into the Nightshift health file through a shared `vaultlib` function; `Intake.run` and `meetings_fetch.sh` call the existing `triage.hold` (`system/scripts/triage.py hold` from bash), which reads `five_hour_hold`, before starting sessions; a reserve window before `brief_time` halves the ceiling.

**Tech Stack:** bash, Python 3 (`vaultlib`), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-11-usage-ceiling-design.md` (assumes the grill keeps the reserve window and one ceiling; drop Task 3's reserve step if it does not)

## Global Constraints

- Work on branch `feat/usage-ceiling`. Commit there; do not push or open a pull request.
- Run the suites from the repository root through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, which sets the gate's environment, outside a sandbox (the headless tests need `bwrap`). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_intake.py`, `test_nightshift_report.py`, `test_nightshift_sched.py`), bats (`headless.bats`, `meetings.bats`, `nightshift.bats`), the gate.
- Commits use `git commit -F .scratch/<file>`.
- Edits are described by place and content; the implementer anchors them in the current file text.

## Review Focus

- The brief and debrief paths in `run_headless.sh` never consult the hold; only the writers of the reading change there.
- A held intake tick still runs meetings import, `now.py check` and briefing extraction, and leaves inputs untouched (no attempt counted, no poison).
- `five_hour_hold`'s staleness rule (under 5 hours old) is reused, never copied, and so is `triage.hold`'s config and health-file read.
- The health file write in `run_headless.sh` happens under the lock the script already holds, so a Work Order tick writing the same file cannot interleave.

---

### Task 1: `record_usage` and the reading from every run

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_report.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/run_headless.sh`
- Test: `system/tests/python/test_nightshift_report.py`, `system/tests/headless.bats`

**Interfaces:**
- Produces: `rep.record_usage(vault, date, usage: dict, at: str) -> None` writes `usage5`, `usage7`, `usage5_at`, `usage` into `health-<date>.json`, merging with existing keys; `nightshift_run` calls it; `run_headless.sh` calls `system/scripts/nightshift.py record-usage <date> <json>` (a thin subcommand) when the session's output carries a usage reading.

- [ ] **Step 0: Settle spec Grill Q3 first.** `run_headless.sh` runs `--output-format json`, whose single result object carries no `rate_limit_event` (the source `nightshift_session.parse_stream` reads). Confirm what the CLI emits and which source the grill chose before writing tests; if it is `stream-json`, this task also moves the reads of `.is_error`, `.result` and `.permission_denials` in `run_headless.sh` to the stream's `result` line.
- [ ] **Step 1: Write the tests:** pytest for `record_usage` (create, merge, no-op without usage); bats: `stub_claude` output with a usage reading leaves `health-<date>.json` with `usage5` after `run_headless.sh ingest`; output without one leaves no file.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement** the function, replace the inline block in `nightshift_run.run_item` with a call, add the `record-usage` subcommand, and the `run_headless.sh` step after the result is read (inside the existing lock, before the ledger line).
- [ ] **Step 4: Run the suites.** Expected: PASS.
- [ ] **Step 5: Commit.** `.scratch/msg-1.txt`:

```text
feat(usage): every headless run refreshes the 5-hour usage reading

record_usage in nightshift_report writes the health file for Work Order
runs and, through nightshift.py record-usage, for every run_headless.sh
session, so the ceiling reads a number at most one session old.
```

### Task 2: The hold in the intake and the meetings fetch

**Files:**
- Modify: `system/scripts/vaultlib/intake.py`, `system/scripts/meetings_fetch.sh`
- Test: `system/tests/python/test_intake.py`, `system/tests/meetings.bats`

**Interfaces:**
- Consumes: `triage.hold(vault, now) -> str` (empty to run) and `system/scripts/triage.py hold`, both on master.

- [ ] **Step 1: Write the tests** from spec §4 (held at 0.7: inbox and digests skipped, meetings and `now.py check` run, one log line, one alert, a second tick adds no alert; 0.5 runs; stale reading runs; `meetings_fetch.sh` logs `held` and starts no session).
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement.** `run()` calls `triage.hold` before `process_inbox`/`process_digests`; `meetings_fetch.sh` calls `system/scripts/triage.py hold` after its role and enabled gates, as `triage_fetch.sh` does.
- [ ] **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-2.txt`:

```text
feat(usage): the intake and the meetings fetch hold at the ceiling

Inbox and digest sessions skip a tick while the 5-hour reading is at or
above order_max_five_hour and under 5 hours old; meetings import,
now.py check and briefing extraction still run. Both reuse triage.hold,
the rule inbox triage already applies.
```

### Task 3: The reserve window and the documents

**Files:**
- Modify: `system/scripts/vaultlib/intake.py`, `system/scripts/vaultlib/triage.py` (an optional ceiling argument on `hold`), `FOUNDRY.md`, `.claude/skills/order/SKILL.md` (status names intake holds), `docs/superpowers/roadmap.md`
- Test: `system/tests/python/test_intake.py`, `system/tests/python/test_triage.py`, `system/tests/commands.bats`

- [ ] **Step 1: Write the tests:** in the 60 minutes before `brief_time`, 0.35 holds and 0.25 runs; `FOUNDRY.md` has "The usage ceiling" paragraph naming what is held and what is not.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement** the window in `intake.py`, passing half the ceiling to `triage.hold` (skip this step if the grill drops the reserve) and write the paragraph.
- [ ] **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-3.txt`: `feat(usage): a reserve before the brief, and the ceiling in the manual`.
