# Smoke check: every fetch proves itself after an update

**Date:** 2026-10-11
**Status:** Draft for the owner's review.
**Issue:** none yet. From the 2026-10-11 review ("fragile coupling to Claude Code CLI flags").

## 1. Problem

Calendar, meetings, handoffs and the Work Order sessions all drive `claude -p` with `--settings`, `--disallowedTools`, `--permission-mode dontAsk` and stream-json output, and name connector tools like `mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql`. Telemetry and the DTCC watcher depend on outside APIs. `foundry-update.timer` merges the template at 05:30 and re-renders units, and `claude` updates itself. After either, the first sign of a break is a brief that says "calendar: the fetch session used an unexpected tool", or nothing at all when the break is in a fetch the brief does not run that day.

`system_health.bats` already checks that the `claude` version is unchanged "since the last health check" and tells the owner to re-run spike item 12. It runs only when someone runs `verify_setup.sh --health`.

## 2. Decisions (proposed)

- **One script, `system/scripts/smoke_check.sh`, runs every fetch's check mode and the version check.** It prints one line per source (`ok`, `failed: <reason>`, `off`) and exits 0 when all configured sources pass.
- **It runs after each unattended template update and once a day**, from `update_template.sh --unattended` as an `after_merge` step and from a new `foundry-smoke.timer` at `brief_time` minus 30 minutes (so a failure is in the alerts file before the brief reads it). A run costs one connector session per enabled connector, so a daily run is the ceiling.
- **A failure is one alert a day per source**, `[smoke]`-tagged, and the brief lists it under Systemic Blockers as alerts already are. No new brief section.
- **A `claude` version change is reported, not blocked.** The script records the version in `system/logs/claude.version`; a change raises one alert naming both versions and the acceptance steps to re-run. Pinning or rolling back `claude` is the owner's call.
- **`calendar_fetch.sh` gains `--check`** (the others have it): one confined session that lists today's events and reports the count, as `meetings_fetch.sh --check` does.

## 3. Changes

### 3.1 `system/scripts/smoke_check.sh [--quiet]`

For a server or standalone machine (a client exits 0 with `client: no checks`):

| Source | Check | Off when |
|---|---|---|
| `claude` version | `"$CLAUDE_BIN" --version` against `system/logs/claude.version`; write the file when absent | never |
| calendar | `calendar_fetch.sh --check` | never (the brief always reads it) |
| meetings | `meetings_fetch.sh --check` | `meetings_enabled` false |
| handoffs | `jira_fetch.sh --check` | `handoffs_projects` empty |
| telemetry | `telemetry_fetch.py --check <name>` per source in `--list` | no source |
| dtcc | `dtcc_watch.py --check` | no `system/dtcc/map.yaml` |
| slack | `slack_bridge.py --check` | neither Slack channel set (when the Slack bridge ships) |

Each check runs under `timeout` (the fetch's own timeout plus a margin) and its exit and first stderr line are logged to `system/logs/smoke-<YYYY-MM>.jsonl`. A failure raises `alert_once "<source>"` with the reason and the fetch's own log path. The version change raises `alert_once version "claude <old> -> <new>; re-run the acceptance steps (FOUNDRY.md Development)"` and updates the file.

### 3.2 Triggers

- `update_template.sh`: after `install_units.sh --update`, `after_merge "smoke check" system/scripts/smoke_check.sh --quiet`. A failed check does not undo the merge; `after_merge` already names the merge in its message.
- `foundry-smoke.service.in` and `foundry-smoke.timer.in` (`OnCalendar` at `brief_time` minus 30 minutes in `TZ`, `Persistent=true`); `install_units.sh` adds them for server and standalone.

### 3.3 `calendar_fetch.sh --check`

Same confined session as a fetch, for today, printing `calendar_fetch: the connector listed <n> events` and the fetch's exit codes. `calendar.bats` gains the case.

### 3.4 `system_health.bats`

The version test reads `system/logs/claude.version` instead of its own record, so the two agree.

### 3.5 Documents

`FOUNDRY.md`: a Smoke check paragraph in Daily use and the unit in Machine roles; the Development paragraph on acceptance re-runs names the version alert as its trigger.

## 4. Tests

bats (`smoke.bats`): with stub fetches on `PATH` that exit 0, every configured line reads `ok` and nothing is alerted; a stub that exits 6 gives `failed:` for that source, one alert line, and a second run the same day adds no second alert; a disabled source reads `off` and is not run (the stub records calls); a changed version alerts once and rewrites the file; a client exits 0 with no checks; `units.bats`: the smoke timer renders at `brief_time` minus 30 minutes and only for server and standalone; `calendar.bats`: `--check` prints the count line with the calendar stub. `update_template.sh`'s test adds the smoke step to the unattended sequence.

Each fails before the change. Bound tools: bats and the gate.

## 5. Out of scope

- Fixing a failing fetch automatically, or rolling `claude` back.
- A check for the headless `ingest`, `brief` and `debrief` commands (those are the acceptance steps, which cost real runs).
- Health in the brief as its own section.
