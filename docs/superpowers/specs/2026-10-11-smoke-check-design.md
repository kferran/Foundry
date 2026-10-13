# Smoke check: every fetch proves itself before the brief

**Date:** 2026-10-11, revised 2026-10-13 (the timer's minute decided by the owner; the post-update step cut).
**Status:** Decided. Part of #122 (simplify the template, step 2).
**Issue:** #122. From the 2026-10-11 review ("fragile coupling to Claude Code CLI flags").

## 1. Problem

Calendar, meetings, handoffs, inbox triage and the Work Order sessions all drive `claude -p` with `--settings`, `--disallowedTools`, `--permission-mode dontAsk` and stream-json output, and name connector tools like `mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql`. Telemetry and the DTCC watcher depend on outside APIs. `foundry-update.timer` merges the template 45 minutes before the brief and re-renders units, and `claude` updates itself. After either, the first sign of a break is a brief that says "calendar: the fetch session used an unexpected tool", or nothing at all when the break is in a fetch the brief does not run that day.

`system_health.bats` already checks that the `claude` version is unchanged "since the last health check" and tells the owner to re-run spike item 12. It runs only when someone runs `verify_setup.sh --health`.

## 2. Decisions

- **One script, `system/scripts/smoke_check.sh`, runs every configured fetch's check mode and the version check.** It prints one line per source (`<source>: ok`, `<source>: failed: <reason>`, `<source>: off`) and exits 0 when every configured source passes, else 1. It takes no arguments.
- **It runs once a day, from `foundry-smoke.timer` at `brief_time` minus 15 minutes** (owner, 2026-10-13), through its own `{{SMOKE_TIME}}` placeholder in `install_units.sh`. A run costs one connector session per enabled connector, so once a day is the ceiling.
- **The post-update run is cut** (the resolution of the 2026-10-11 open question). The update runs at `brief_time` minus 45 and the smoke check at minus 15, both before the brief, and the brief is the only reader of the alerts: on an update day the minus-15 run checks the merged scripts, and a run straight after the update would reach the same reader 30 minutes earlier for one more session per connector. The update unit's 20-minute timeout (35 on a server) could not hold four connector checks either. On a server the update, with its sync drop-in, may still be running at minus 15; the checks read no units and take no lock, so the overlap is harmless. A vault that has not installed `foundry-smoke.timer` runs no check until its owner runs `system/scripts/install_units.sh` (`install_units.sh --update` never installs a new unit; the update alert names it).
- **A slow morning may overrun the brief.** The checks run one after another; the connector checks' own timeouts add to 900 s (calendar 150, meetings 150, Jira 300, triage 300) before telemetry and the DTCC map. The checks and the brief share no lock, so an overlap costs usage only, and a late alert reaches the next day's brief, which reads the previous day's alerts too. The service's `TimeoutStartSec` is 35 minutes, above the sum of the script's own timeouts in §3.1.
- **The usage ceiling applies** (usage ceiling spec: every unattended session that is not the brief, the debrief or a notice). While `triage.py hold` prints a reading, the connector checks print `<source>: held: <reading>` with no alert of their own and one `[smoke] held:` alert a day; the version, telemetry and DTCC checks start no model session and still run.
- **No check passes silently.** A check that exits 0 with no output did not run (a lost lock, a wrong gate) and reads `failed: no output`. `meetings_fetch.sh --check` reports a busy `meetings.lock` as a reason with exit 4 instead of the fetch's silent exit 0.
- **A failure is one alert a day per source**, `[smoke]`-tagged, and the brief lists it under Systemic Blockers as alerts already are. No new brief section.
- **A `claude` version change is reported, not blocked.** The script records the version in `system/logs/claude.version`; a change raises one alert naming both versions and the acceptance steps to re-run. Pinning or rolling back `claude` is the owner's call. `system_health.bats` reads the same file (today `claude_version`, renamed).
- **`calendar_fetch.sh` gains `--check`** (the others have it): one confined session that lists today's events and reports the count, as `meetings_fetch.sh --check` does.
- **Slack notices are never smoke-checked:** `notify.sh --check` posts a real message, an outward action the owner runs by hand.

## 3. Changes

### 3.1 `system/scripts/smoke_check.sh`

For a server or standalone machine (a client prints `client: no checks` and exits 0):

| Source | Check | Timeout | Off when |
|---|---|---|---|
| `version` | `"$CLAUDE_BIN" --version` against `system/logs/claude.version`; write the file when absent | 30 s | never |
| `calendar` | `calendar_fetch.sh --check` | 210 s | never (the brief always reads it) |
| `meetings` | `meetings_fetch.sh --check` | 210 s | `meetings_enabled` not `true` |
| `handoffs` | `jira_fetch.sh --check` | 360 s | `handoffs_projects` empty |
| `triage` | `triage_fetch.sh --check` | 360 s | `triage_enabled` not `true` (`--check` skips that gate itself, so the smoke check applies it) |
| `telemetry` | `telemetry_fetch.py --check <name>` per source in `--list`; a `--list` that fails is a failed source, never "no source" (audit C5) | 120 s each | `--list` prints nothing |
| `dtcc` | `dtcc_watch.py --check`: the map's validity and its codebase paths (exit 1 stale, 2 invalid). It does not reach the DTCC site | 60 s | no `system/dtcc/map.yaml` |

The gate for an off source lives in `smoke_check.sh`, so an off source's script is never run. Each check runs under `timeout` with both streams captured and stdin closed; its reason is the script's own last `<script name>: …` line without that prefix (the Python checks' `stale:` and `<source>:` words stay), else the last non-empty line; a `timeout` exit (124) reads `timed out after <n>s`; several failing telemetry sources are joined with `; `. An existing vault's `system/logs/claude_version` (the health suite's old name) is renamed to `claude.version` on the first run, so a `claude` change since its last health check is reported. Each source's exit and reason are logged to `system/logs/smoke-<YYYY-MM>.jsonl` (`{time, source, exit, reason}`). A failure raises `alert_once "<source>"`: `- HH:MM:SS [smoke] <source> failed: <reason> (see <log>)`. The version change raises `alert_once version`: `claude <old> -> <new>; re-run the acceptance steps (FOUNDRY.md Development)` and updates the file.

### 3.2 Trigger

`foundry-smoke.service.in` (`Type=oneshot`, `TimeoutStartSec=35min`, `SuccessExitStatus=1`: a failed source is reported by its alert, not as a failed unit) and `foundry-smoke.timer.in` (`OnCalendar` at `{{SMOKE_TIME}}` in `{{TZ}}`, `Persistent=true`). `install_units.sh` computes `{{SMOKE_TIME}}` as `brief_time` minus 15 minutes, wrapping past midnight as the update time does, and installs both for server and standalone. An existing vault gets "new unit available: foundry-smoke.service, foundry-smoke.timer" in its update alert and the owner installs them by running `system/scripts/install_units.sh`.

### 3.3 `calendar_fetch.sh --check`

Same confined session as a fetch, for today, printing `calendar_fetch: the connector listed <n> events` instead of the TSV, with the fetch's exit codes and log line. `--check` with another argument is a usage error (exit 2).

### 3.4 `system_health.bats`

The version test reads and writes `system/logs/claude.version` instead of `claude_version`, the first line of `claude --version` only, and skips instead of writing `unknown` when `claude` is missing, so the two writers agree.

### 3.5 Documents

`FOUNDRY.md`: a Smoke check paragraph in Daily use; the unit in the Machine roles table; the Updating bullet's ordering sentence (update at minus 45, DTCC watcher at minus 30, smoke check at minus 15); the Development paragraph on acceptance re-runs names the version alert as its trigger. `docs/superpowers/roadmap.md`: the Smoke check row.

## 4. Tests

bats (`smoke.bats`), with stub fetches written over the vault's copies (`make_vault` copies `system/scripts/`) that record their calls: every configured line reads `ok`, the exit is 0 and nothing is alerted; a stub that exits 6 gives `failed: <its reason>` for that source, exit 1, one alert line, and a second run the same day adds no second alert while two failing sources give two lines; a disabled source reads `off` and its stub records no call; a changed version alerts once and rewrites the file, an absent file is written silently, an old `claude_version` file is taken over; a check that exits 0 with no output reads `failed: no output`; the Python checks' first word survives the prefix strip; at the usage ceiling the connector checks read `held:` and their scripts are not called, with one alert; two failing telemetry sources are both named; a client exits 0 with `client: no checks`; an argument exits 2. `meetings.bats`: `--check` against a busy lock exits 4 with a reason. `units.bats`: the smoke timer renders at `brief_time` minus 15 minutes (`05:45:00` for `06:00`, `23:55:00` for `00:10`) for server and standalone, never for a client. `calendar.bats`: `--check` prints the count line with the calendar stub and writes the log line; `--check` with a date exits 2. `commands.bats`: `FOUNDRY.md` names `smoke_check.sh`, the timer's minute and the version alert.

Each fails before the change. Bound tools: bats and the gate.

## 5. Out of scope

- A run straight after the template update (cut, §2).
- Fixing a failing fetch automatically, or rolling `claude` back.
- A check for the headless `ingest`, `brief` and `debrief` commands (those are the acceptance steps, which cost real runs).
- Health in the brief as its own section.
- Dedupe between the smoke check and the brief's own calendar fetch at `brief_time`.
