# Smoke Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `system/scripts/smoke_check.sh` runs each configured fetch's check mode and the `claude` version check, alerts once a day per failure, and runs after every unattended template update and daily before the brief.

**Architecture:** One bash script on the `lib_config.sh` and `alert_once` pattern; `--check` added to `calendar_fetch.sh`; one `after_merge` step in `update_template.sh`; a service and timer pair rendered by `install_units.sh`.

**Tech Stack:** bash, systemd user units, bats.

**Spec:** `docs/superpowers/specs/2026-10-11-smoke-check-design.md`

## Global Constraints

- Work on branch `feat/smoke-check`. Commit there; do not push or open a pull request.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch`, outside a sandbox. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: bats (`smoke.bats`, `calendar.bats`, `units.bats`, the `update_template` suite in `scripts.bats`), the gate.
- Commits use `git commit -F .scratch/<file>`.
- Edits are described by place and content; the implementer anchors them in the current file text.

## Review Focus

- A disabled source is never executed (the stub's call log proves it), so the smoke check costs no connector session the owner did not turn on.
- `alert_once` keys are per source, so two failing sources give two lines and a repeat gives none.
- The `after_merge` step runs after `install_units.sh --update`, never before, so re-rendered units are what gets checked.
- The timer time is derived from `brief_time`; a `brief_time` change re-renders it (as `units.bats` checks for the brief timer).

---

### Task 1: `calendar_fetch.sh --check`

**Files:**
- Modify: `system/scripts/calendar_fetch.sh`
- Test: `system/tests/calendar.bats`

- [ ] **Step 1: Write the test:** with `stub_claude_calendar`, `calendar_fetch.sh --check` exits 0 and prints `calendar_fetch: the connector listed <n> events`; `--check extra` exits 2.
- [ ] **Step 2: Run it to verify it fails.** `bats system/tests/calendar.bats -f check`.
- [ ] **Step 3: Implement** the flag on the `meetings_fetch.sh --check` pattern: same session, today's date, count the extracted rows, print the line instead of the TSV.
- [ ] **Step 4: Run the suite.** Expected: PASS.
- [ ] **Step 5: Commit.** `.scratch/msg-1.txt`: `feat(calendar): calendar_fetch.sh --check reports the event count`.

### Task 2: `smoke_check.sh`

**Files:**
- Create: `system/scripts/smoke_check.sh`
- Test: `system/tests/smoke.bats`

**Interfaces:**
- Produces: one line per source (`<source>: ok|failed: <reason>|off`), exit 0 when every configured source passes, else 1; `system/logs/smoke-<YYYY-MM>.jsonl`; `system/logs/claude.version`; `[smoke]` alerts.

- [ ] **Step 1: Write the tests** from spec §4: all ok; one failing source alerts once; a disabled source is not called; version change alerts once and rewrites the file; a client runs no checks. Stubs for each fetch go on `PATH` in `$BATS_TEST_TMPDIR/bin` and record their arguments.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement.** Source `lib_config.sh`; role gate; the table from spec §3.1 as a list of `(name, enabled-test, command, timeout)`; `timeout` around each; `logline` and `alert_once` as `jira_fetch.sh` defines them.
- [ ] **Step 4: Run the suite and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-2.txt`:

```text
feat(smoke): smoke_check.sh runs every fetch's check mode and the version check

One line per source, one alert a day per failure, the claude version
recorded in system/logs/claude.version and a change reported once with
the acceptance steps to re-run.
```

### Task 3: Triggers

**Files:**
- Create: `system/systemd/foundry-smoke.service.in`, `system/systemd/foundry-smoke.timer.in`
- Modify: `system/scripts/install_units.sh`, `system/scripts/update_template.sh`, `system/tests/system_health.bats`
- Test: `system/tests/units.bats`, `system/tests/scripts.bats` (the update sequence)

- [ ] **Step 1: Write the tests:** the smoke timer renders `OnCalendar=*-*-* 05:30:00 America/Denver` for `brief_time` 06:00 and follows a `brief_time` change; it renders for server and standalone and never for a client; the unattended update's recorded step list ends with the smoke step after the units step; `system_health.bats`'s version test reads `system/logs/claude.version`.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement:** the two unit templates (a `{{SMOKE_TIME}}` placeholder computed in `install_units.sh` from `brief_time`), the `UNITS`/`ENABLE` additions for both roles, the `after_merge` line, and the health test change.
- [ ] **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-3.txt`:

```text
feat(smoke): run the smoke check daily before the brief and after each template update
```

### Task 4: Documents

**Files:**
- Modify: `FOUNDRY.md` (Daily use, Machine roles, Development), `docs/superpowers/roadmap.md`
- Test: `system/tests/commands.bats` (`FOUNDRY.md` names `smoke_check.sh`)

- [ ] **Step 1: Write the test.** **Step 2: Verify it fails.** **Step 3: Write the paragraphs.** **Step 4: Run the test and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-4.txt`: `docs(smoke): the smoke check in the manual and the roadmap`.
