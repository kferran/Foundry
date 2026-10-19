# Phase C: Step 4 Budgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Meetings move to `extensions/meetings/` (core to 11 schemas), `CLAUDE.md` drops to 50 lines or fewer, and the core line budget resets to the measured count.

**Architecture:** Four generic hooks first (`importer`, `owns`, `index_ignore`, `run_kinds`), each proven with the loader's fixture extension; then the meetings code, schemas, units, brief section and tests move behind them, as phase 4 moved telemetry; then the `CLAUDE.md` prune; then the budgets.

**Tech Stack:** bash, Python 3 (`vaultlib`), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-19-phase-c-budgets-design.md`

## Global Constraints

- The gate runs twice before the PR: every extension off, every extension on (`gate` and `gate-all-extensions` in CI).
- Moves use `git mv` so history follows the files.
- No behaviour change for a vault with meetings on: the same notes, runs, commit titles, alerts and brief lines. `meetings.bats` and the meetings pytest files move unchanged except for paths.
- A core file may keep a meetings path or type name only where spec §3.3 says so.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- CHANGELOG line with an `Action:` line (the vault's update enables the extension by migration; nothing to run by hand unless `extensions.py migrate` reports otherwise).

## Review Focus

1. **A vault with meetings on behaves the same after the update**: migration enables the extension before the first tick; the import runs at the same point in the tick, under run.lock.
2. **The publish gate still refuses an ingest run that stages a meeting note**, now through `owns`.
3. **Core with every extension off has no meeting schema, unit, prep file or brief text**, and its suites pass.
4. **The routing lines and the approved-plans rule still reach the model**: `foreman.md` is named from `CLAUDE.md`; the `order` skill's description names plan approval.

---

### Task 1: The four hooks

**Files:** `system/scripts/vaultlib/extensions.py`, `vaultlib/intake.py`, `vaultlib/publish.py`, `vaultlib/index.py`, `commit_runs.py`; the loader fixture under `system/tests/fixtures/extensions/`; `test_extensions.py`, `test_intake.py`, `test_publish.py`, `test_index.py`, `test_commit_runs.py`.

- `importer: {run, timeout}`: `Intake.extension_importers()` runs each enabled extension's command after `extension_ticks()` and before `process_inbox()`, under run.lock (no wait), one alert line on a non-zero exit.
- `owns: [glob…]`: `publish._check` refuses an `ingest` target matching an enabled extension's glob with "written only by the <name> extension's importer".
- `index_ignore: [path…]`: `index.IGNORED` gains the enabled extensions' paths.
- `run_kinds: [name…]`, `commit_title: <script>`: `publish.check_run_id` and `commit_runs.RUN_ID` accept them; `commit_runs` asks the extension's script for the commit title of its kind.
- Tests: each hook with the fixture extension on and off.

### Task 2: Move meetings into `extensions/meetings/`

**Files:** the table in spec §3.1, by `git mv`; `extensions/meetings/extension.md` (contract, `config_keys` fragment with `meetings_enabled`, `meetings_partition` and the rest, `sources`, `smoke`, `units`, `alert_tags`, `importer`, `owns: [wiki/*/meetings/]`, `index_ignore: [raw/meetings/, meetings/drop/]`, `run_kinds: [meeting]`, `brief`, `deps`); `extensions/meetings/scripts/meetings_tick.py` (the import, from `intake.py`, using `vaultlib.intake.Intake` for logs, alerts and publish); `extensions/meetings/brief/{prep.sh,section.md}`; `vaultlib/extensions.py` `MIGRATIONS`.

- Core loses: `meeting_actions.py` from `brief_prep.sh`, `prep_meetings` from `lib_prep.sh`, the meetings lines in `smoke_check.sh`, `install_units.sh`, `sources.py`, `alerts.py`, the meetings block in `brief.md` (to `section.md`), the meetings phase body in `setup.md` (to the extension's enable steps).
- `meeting_prep.py` stays (spec §3.3) and reads meeting actions only when `v_meeting` exists.
- Tests: the moved suites under `extensions/meetings/tests/`; core's `prep.bats`, `commands.bats`, `smoke.bats`, `units.bats` updated; the migration test (a vault with `meetings_enabled: true` or a meeting note gets the extension).

### Task 3: `CLAUDE.md` to 50 lines

**Files:** `CLAUDE.md`, `system/agents/foreman.md`, `.claude/skills/order/SKILL.md`, `commands.bats`.

- As spec §4. The `order` skill's description gains "when the user approves a plan". `foreman.md` gains the Agents block and the two routing lines, worded as today.
- Tests: the line count (≤ 50); the routing phrases in `foreman.md`; the approved-plans sentence in `order/SKILL.md`; Scannable Layouts and Blocked Actions in Writing; the CLAUDE.md asserts that named moved text follow it.

### Task 4: Budgets and documents

**Files:** `vault_integrity.bats` (schemas ≤ 11; lines ≤ measured + 50, with the reason), `FOUNDRY.md` (meetings as an extension; the Agents text), the extensions spec §7 note, the roadmap row, `CHANGELOG.md`.

- [ ] Run the gate with every extension off and every extension on.

### Task 5: Live acceptance (owner)

- [ ] After the vault's update: `system/scripts/extensions.py list` shows meetings on; the next brief has Waiting on; a transcript dropped in `meetings/drop/work/` imports within one tick.
