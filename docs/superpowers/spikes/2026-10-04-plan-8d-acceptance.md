# Plan 8d acceptance

**Date:** 2026-10-04 · **Branch:** `feat/plan-8d` · **Commit:** 18f5499 (Tasks 1–4 plus the final-review fixes) · **Debian host:** Debian 12.15 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2, Claude Code 2.1.289. Work ran natively on the Debian host, so its gate is the native gate. The host name is kept out of this record (template rule).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Debian host | 9e23922 (before Task 1) | 0 | 14/14 PASS | |
| Debian host | b1dc3c8 (Task 4) | 0 | 15/15 PASS | lint 0 errors |
| Debian host | 18f5499 (final-review fixes) | 0 | 15/15 PASS | lint 0 errors |

## Live runs (spec §7.1)

Every run used a throwaway copy (a `git archive` in a `mktemp -d -p /tmp` directory, or a clone under `~/.cache/jarvis-accept/`), removed afterwards. Event titles are kept out of this record.

| Run | Day | Exit | Events | Cost | Turns | Denials | Unexpected tools |
|---|---|---|---|---|---|---|---|
| 1. `calendar_fetch.sh`, Debian host | 2026-10-05 | 0 | 11 | $0.23 | 4 | 0 | none |
| 2. `brief_prep.sh` fetch, Debian host | 2026-10-04 | 0 | 0 | $0.06 | 4 | 0 | none |
| 2. headless brief, Debian host | 2026-10-04 | 0 | n/a | n/a | n/a | 0 | n/a |
| 1. `calendar_fetch.sh`, laptop | | pending | | | | | |

- **Run 1** matches the calendar: the connector, read directly, lists the same 11 events for 2026-10-05 (one all-day, ten timed, same start and end times).
- **Run 2**: 2026-10-04 is a Sunday with no events (confirmed against the connector). `calendar.tsv` is empty, Unavailable Sources has no calendar line, and Active Objectives reports no fixed commitments. The brief published `briefings/2026-10-04.md` with 0 permission denials.
- **Phase 6 path (§7.1 item 3)**: run 1 ran from this interactive Claude Code session through the Bash tool with a 300000 ms timeout, so the nested `claude -p` path is proven by the same run.
- **Init tool list** (run 1's log line): `CronList DesignSync ListAgents LSP ReportFindings ScheduleWakeup ShareOnboardingGuide StructuredOutput TaskStop ToolSearch`. No file, shell, network or connector tool loaded up front; `list_events` came through `ToolSearch`.
- The user's settings hold no allow rule broader than the calendar server: the fail-closed check added in the fix wave did not trip.

## Verdict

**PASS on the Debian host**: the fetch returns the day's events correctly, the brief consumes them and stays connector-free, and the gate passes 15/15 on the tool floor. The laptop fetch is pending (this session reaches only the server).
