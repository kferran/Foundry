# The usage ceiling: the brief comes first

**Date:** 2026-10-11
**Status:** Approved for build. Grilled 2026-10-13: no reserve before the brief (Q1), one ceiling (Q2), the reading comes from `stream-json` (Q3, checked against the CLI).
**Issue:** Part of #122 (ahead of step 2, owner 2026-10-13). From the 2026-10-11 review ("everything shares one Claude account's usage window").

## 1. Problem

Brief, debrief, intake ingests, Work Orders, and the calendar, meetings and Jira fetches are all `claude -p` sessions on one account. Only Work Orders and inbox triage respect a ceiling: no new Work Order starts, and a triage tick is skipped, while the last 5-hour reading is at or above `order_max_five_hour` (default 0.6). Triage applies it through `vaultlib/triage.py`'s `hold(vault, now)` (`system/scripts/triage.py hold` from bash), which calls `nightshift_sched.five_hour_hold`. The reading itself is taken only from a Work Order session's `stream-json` output (its `rate_limit_event` lines, which `nightshift_session.parse_stream` reads) and written to `system/logs/nightshift/health-<date>.json`, so on a day without Work Orders it is stale, and the ceiling is read from a stale number.

The intake has no ceiling. A morning with ten inbox drops and a batch of digests runs ten or more ingest sessions before 06:00. When the account limit is reached, the brief fails with exit 4 and the only record is a line in `alerts_<date>.md` that the failed brief would have shown. #99's grill (2026-10-10) settled that triage ticks skip at the ceiling; this spec applies the same rule to every unattended session that is not the brief or the debrief.

## 2. Decisions

- **The brief, the debrief and the Slack notices are never held.** The first two are what the owner reads; the notices (`2026-10-11-slack-notices-design.md`) are how the owner learns a run failed.
- **Every other unattended session is held at the ceiling:** intake ingests, the connector fetches that run on their own timers (meetings; triage already holds), and Work Orders as today. A held tick logs one line and raises one alert a day ("intake held: 5-hour usage at <n>%"); inputs stay where they are and the next tick re-reads.
- **A fresh reading from every session.** `run_headless.sh` writes `usage5`, `usage7` and `usage5_at` to the health file after every run, so the number the ceiling reads is at most one session old. The readers are unchanged: `nightshift_sched.five_hour_hold` keeps its "under 5 hours old" rule.
- **The reading comes from `stream-json`** (Q3, checked 2026-10-13). A `claude -p --output-format json` result carries no utilization; with `--output-format stream-json --verbose` every session emits a `rate_limit_event` line whose `rate_limit_info.unifiedWindows` holds `five_hour` and `seven_day` utilization. `run_headless.sh` writes the stream to `system/logs/runs/<run_id>/stream.jsonl` and keeps its last `result` line as `claude.json`, so the usage-limit check, the denial count and the alert text read the same fields as before.
- **One setting** (owner, 2026-10-13). `order_max_five_hour` keeps its name and applies to all held sessions. A vault that wants intake to run harder than Work Orders does not exist yet; a second key waits for that vault.
- **No reserve before the brief** (owner, 2026-10-13). One rule for every held session; a reserve is added only if a brief actually fails at the limit.

## 3. Changes

- `run_headless.sh`: run the session with `--output-format stream-json --verbose` into `stream.jsonl`, keep its last `result` line as `claude.json`, then read the 5-hour and 7-day utilization with `nightshift_session.parse_stream` and update `system/logs/nightshift/health-<date>.json` under `run.lock`'s existing hold, through a small `vaultlib` function shared with `nightshift_run` (`rep.record_usage(vault, date, usage, at)`, called from bash as `system/scripts/nightshift.py record-usage <stream>`). A stream without usage leaves the file alone, and a failed record never fails the run. The stream is kept only for a failed run. Because a recorded reading can create the day's health file before the first Work Order tick, the tick runs its claude, gh and sandbox checks while the file lacks a `sandbox` key, not only when the file is missing.
- `vaultlib/intake.py`: the existing `triage.hold(vault, now)` is checked right before each ingest session (an inbox file, a digest batch), so a tick that crosses the ceiling stops there. A held inbox file stays where it is while later duplicates and `production_error` notes still route; held digests wait. Briefing extraction, the Now check, RCA filing and the meeting import run as before (an approved RCA filing is one short session per ticked line and is not held). One alert a day.
- `meetings_fetch.sh` and later fetch timers: the same hold through the existing `system/scripts/triage.py hold` (prints the reason, empty to run), called the way `triage_fetch.sh` calls it, so bash callers share the Python rule.
- `FOUNDRY.md`: the Work Orders paragraph's ceiling sentence becomes a paragraph of its own, "The usage ceiling", listing what is held and what is not.

## 4. Tests

pytest: `record_usage` writes and merges the three fields and leaves the file alone without usage; `Intake.run` with a health file at 0.7 starts no session, leaves the inputs and alerts once, while a `production_error` note in the inbox still routes; at 0.5 everything runs; a reading older than 5 hours does not hold; a Work Order tick on a health file that holds only a usage reading still runs its checks. bats: `run_headless.sh` with the stub claude's output carrying a usage reading writes the health fields and passes `--output-format stream-json --verbose`, and the usage-limit result line still maps to exit 4; `meetings_fetch.sh` exits 0 and logs `held` without a session at 0.7.

Each fails before the change. Bound tools: pytest (`test_intake.py`, `test_nightshift_report.py`, `test_nightshift_run.py`), bats (`headless.bats`, `meetings.bats`, `commands.bats`), the gate, and the live acceptance steps for `run_headless.sh` (brief, debrief, ingest).

## 5. Out of scope

- Reading usage from an API outside a session. A session's `rate_limit_event` stream lines are the only source today.
- Per-partition or per-command budgets.
- Changing how the brief and debrief behave at the limit (they fail with exit 4 and, with the Slack bridge, say so).
