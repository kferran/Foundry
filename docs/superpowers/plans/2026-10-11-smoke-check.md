# Smoke Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `system/scripts/smoke_check.sh` runs each configured fetch's check mode and the `claude` version check, alerts once a day per failure, and runs daily at `brief_time` minus 15 minutes.

**Architecture:** One bash script on the `lib_config.sh` and `alert_once` pattern; `--check` added to `calendar_fetch.sh`; a service and timer pair rendered by `install_units.sh` through a `{{SMOKE_TIME}}` placeholder. No change to `update_template.sh` (spec §2 cut the post-update run).

**Tech Stack:** bash, systemd user units, bats.

**Spec:** `docs/superpowers/specs/2026-10-11-smoke-check-design.md` (revised 2026-10-13)

## Global Constraints

- Work on branch `feat/smoke-check` in worktree `.scratch/smoke`. Commit there; do not push or open a pull request.
- Run the suites from the repository root through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, which sets the gate's environment, outside a sandbox. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: bats (`smoke.bats`, `calendar.bats`, `units.bats`, `commands.bats`), the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- `smoke_check.sh` never contains the text `--permission-mode` or `--disallowedTools` (the one-file rule in `scripts.bats`).
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- A disabled source is never executed (the stub's call log proves it), so the smoke check costs no connector session the owner did not turn on.
- `alert_once` keys are per source, so two failing sources give two lines and a repeat gives none.
- A `telemetry_fetch.py --list` that fails reads as a failed `telemetry` source, never as "no source" (audit C5).
- A check that hits its `timeout` reads `failed: timed out after <n>s`, with the run going on to the next source.
- The timer minute is derived from `brief_time` and wraps past midnight; a `brief_time` change re-renders it (as `units.bats` checks for the update timer).

---

### Task 1: `calendar_fetch.sh --check`

**Files:**
- Modify: `system/scripts/calendar_fetch.sh`
- Test: `system/tests/calendar.bats` (after "the date defaults to today in the configured timezone")

**Interfaces:**
- Produces: `calendar_fetch.sh --check` → stdout `calendar_fetch: the connector listed <n> events`, exit as a fetch, one log line; `calendar_fetch.sh --check 2026-10-05` → exit 2.

- [ ] **Step 1: Write the test:** with `stub_claude_calendar` (one event in `stream_ok`), `run "$CF" --check` exits 0, `$output` is `calendar_fetch: the connector listed 1 events`, and the month's log has one line with `.exit == 0`; `run "$CF" --check "$DAY"` exits 2.
- [ ] **Step 2: Run it to verify it fails.** `system/scripts/test.sh system/tests/calendar.bats -f 'check'`. Expected: FAIL (today `--check` is an invalid date, exit 2, and the date form prints TSV).
- [ ] **Step 3: Implement:** a `check=0` flag parsed before the date (`--check` sets it and shifts; a remaining argument with `--check` is usage, exit 2); after the outcome, `if (( check ))` print the count line (`wc -l < "$work/events.tsv"`) instead of `cat`.
- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/calendar.bats`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(calendar): calendar_fetch.sh --check reports the event count`.

### Task 2: `smoke_check.sh`

**Files:**
- Create: `system/scripts/smoke_check.sh`
- Test: `system/tests/smoke.bats`

**Interfaces:**
- Consumes: `calendar_fetch.sh --check`, `meetings_fetch.sh --check`, `jira_fetch.sh --check`, `triage_fetch.sh --check`, `telemetry_fetch.py --list` / `--check <name>`, `dtcc_watch.py --check`, `"$CLAUDE_BIN" --version`.
- Produces: one line per source (`<source>: ok|failed: <reason>|off`), exit 0 when every configured source passes, else 1, 2 on any argument; `system/logs/smoke-<YYYY-MM>.jsonl`; `system/logs/claude.version`; `[smoke]` alerts.

- [ ] **Step 1: Write the tests** (spec §4). `setup`: `make_vault`, `cd "$V"`, a `claude` stub on `PATH` printing `1.0.0 (Claude Code)` for `--version`, and a `stub <script> <exit> [message]` helper that overwrites `$V/system/scripts/<script>` with a script appending `<script> $*` to `$BATS_TEST_TMPDIR/calls`, printing the message to stderr (or stdout for the Python scripts) and exiting with the code; `telemetry_fetch.py` stub prints `prod-sentry` for `--list` and the message otherwise. Tests:
  - all ok: calendar and the version stub only (the fixture config has no features): `calendar: ok`, `version: ok`, `meetings: off`, `handoffs: off`, `triage: off`, `telemetry: off`, `dtcc: off`; exit 0; no alerts file; `claude.version` holds `1.0.0 (Claude Code)`; the log has one `calendar` line with exit 0.
  - one failing source: calendar stub exits 6 with `calendar_fetch: no Google Calendar connector`: `calendar: failed: no Google Calendar connector`, exit 1, one alert line `[smoke] calendar failed: no Google Calendar connector (see system/logs/smoke-<month>.jsonl)`; a second run adds no line (`grep -c '\[smoke\]'` stays 1).
  - two failing sources give two alert lines (calendar 6, and `meetings_enabled: true` with a meetings stub exiting 3).
  - a disabled source is not run: `calls` has no `meetings_fetch.sh`, `jira_fetch.sh`, `triage_fetch.sh`, `dtcc_watch.py` entry and no `telemetry_fetch.py --check` entry (only `--list`).
  - enabled features run: `meetings_enabled: true`, `triage_enabled: true`, `handoffs_projects: ["AB"]`, a `system/dtcc/map.yaml`, telemetry `--list` printing `prod-sentry`: `calls` holds each `--check` once, and `telemetry_fetch.py --check prod-sentry`.
  - a failing telemetry list: the `telemetry_fetch.py` stub exits 1 on `--list`: `telemetry: failed: …`, exit 1.
  - a timeout: a calendar stub that sleeps 5 with `SMOKE_TIMEOUT_SCALE` unset but the per-source timeout env `SMOKE_CALENDAR_TIMEOUT=1`: `calendar: failed: timed out after 1s`.
  - version change: `claude.version` holds `0.9.0 (Claude Code)`: `version: failed: claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code)`, exit 1, one alert `[smoke] version claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code); re-run the acceptance steps (FOUNDRY.md Development)`, the file now holds the new version; a second run reads `version: ok`.
  - a client: `machine_role: client`: output `client: no checks`, exit 0, `calls` absent.
  - an argument: `run system/scripts/smoke_check.sh --quiet` exits 2.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/smoke.bats`. Expected: every test FAILs (no such file).
- [ ] **Step 3: Implement.** Source `lib_config.sh`; `(( $# == 0 )) || usage 2`; role gate; `TZ` from config; `log`, `logline <source> <exit> <reason>` (jq) and `alert_once <key> <text>` on the `jira_fetch.sh` pattern with the `[smoke]` tag; `check <source> <timeout> <command…>`: `timeout "$t" "$@" > "$out" 2>&1 || rc=$?`, reason = last non-empty line of `$out` with `^[a-z_]+: ` stripped, 124 → `timed out after ${t}s`, print the line, log, alert on failure, set `failed=1`. Per-source timeouts read `${SMOKE_<SOURCE>_TIMEOUT:-<default>}` from spec §3.1. Sources in the spec's order: version, calendar, meetings (`meetings_enabled`), handoffs (`handoffs_projects` non-empty: `config_get handoffs_projects ""` not `[]`/empty), triage (`triage_enabled`), telemetry (`--list` under timeout; a non-zero list is `failed`; else one check per name; `off` on an empty list), dtcc (`-f system/dtcc/map.yaml`). The version check is inline: `cur="$(timeout 30 "$claude_bin" --version 2>&1 | head -n 1)"`, compare with the file, write the file.
- [ ] **Step 4: Run the suite, shellcheck and the gate.**
- [ ] **Step 5: Commit.** `feat(smoke): smoke_check.sh runs every configured fetch's check mode and the version check`.

### Task 3: The unit

**Files:**
- Create: `system/systemd/foundry-smoke.service.in`, `system/systemd/foundry-smoke.timer.in`
- Modify: `system/scripts/install_units.sh`, `system/tests/system_health.bats`
- Test: `system/tests/units.bats` (after "standalone and server get the template update 45 minutes before the brief")

**Interfaces:**
- Consumes: `system/scripts/smoke_check.sh` (Task 2).
- Produces: `foundry-smoke.timer` at `{{SMOKE_TIME}}` = `brief_time` minus 15 for server and standalone, in the base `UNITS` and `ENABLE` lists after the debrief units.

- [ ] **Step 1: Write the test:** `run "$IU"` → `foundry-smoke.service` has `ExecStart="$VP/system/scripts/smoke_check.sh"`, `SuccessExitStatus=1`, `TimeoutStartSec=25min`; the timer has `OnCalendar=*-*-* 05:45:00 America/Denver` and `Persistent=true`; `brief_time` `00:10` → `23:55:00`; `machine_role server` keeps it; `client` removes it. Add `foundry-smoke.service foundry-smoke.timer` to `units.bats`'s `UNITS` list, and `foundry-smoke.timer` after `foundry-debrief.timer` in the exact enable lines at `units.bats` (the three/enable test, the server test, the meetings test, the `--update` test) and `remote.bats` (the `install_units.sh` enable pin).
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/units.bats`.
- [ ] **Step 3: Implement:** the two templates on the `foundry-dtcc-watch` pattern; `smoke_time` from `+1425` beside the `+1410`/`+1395` lines, `{{SMOKE_TIME}}` in `render`; the units in the standalone and server `UNITS`/`ENABLE` arrays after the debrief units; `system_health.bats` reads and writes `system/logs/claude.version`.
- [ ] **Step 4: Run `units.bats`, `remote.bats` and the gate.**
- [ ] **Step 5: Commit.** `feat(smoke): foundry-smoke.timer runs the smoke check 15 minutes before the brief`.

### Task 4: Documents

**Files:**
- Modify: `FOUNDRY.md` (Daily use, Machine roles, Updating and uninstalling, Development), `docs/superpowers/roadmap.md`
- Test: `system/tests/commands.bats` (after "the manual names lib_connector.sh as the second way automation calls claude")

- [ ] **Step 1: Write the test:** `FOUNDRY.md` contains `` `foundry-smoke.timer` runs `smoke_check.sh` 15 minutes before the brief ``, `` `system/logs/claude.version` `` and `re-run the acceptance steps`-adjacent text: `a ``[smoke] version`` alert is the trigger`.
- [ ] **Step 2: Verify it fails.** **Step 3: Write the paragraphs** (Daily use "Smoke check" paragraph after "The usage ceiling"; the Machine roles "Runs" cells; the Updating bullet's "ahead of the DTCC watcher 30 minutes before it" sentence gains the smoke check at 15; Development's last paragraph names the version alert; the roadmap row's status). **Step 4: Run `commands.bats` and the gate.**
- [ ] **Step 5: Commit.** `docs(smoke): the smoke check in the manual and the roadmap`.
