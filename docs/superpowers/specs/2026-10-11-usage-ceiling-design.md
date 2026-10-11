# The usage ceiling: the brief comes first

**Date:** 2026-10-11
**Status:** Draft for the grill.
**Issue:** none yet. From the 2026-10-11 review ("everything shares one Claude account's usage window").

## 1. Problem

Brief, debrief, intake ingests, Work Orders, and the calendar, meetings and Jira fetches are all `claude -p` sessions on one account. Only Work Orders respect a ceiling: no new one starts while the last 5-hour reading is at or above `order_max_five_hour` (default 0.6). The reading itself is taken only from a Work Order session's result and written to `system/logs/nightshift/health-<date>.json`, so on a day without Work Orders it is stale, and the ceiling is read from a stale number.

The intake has no ceiling. A morning with ten inbox drops and a batch of digests runs ten or more ingest sessions before 06:00. When the account limit is reached, the brief fails with exit 4 and the only record is a line in `alerts_<date>.md` that the failed brief would have shown. #99's grill (2026-10-10) settled that triage ticks skip at the ceiling; this spec applies the same rule to every unattended session that is not the brief or the debrief.

## 2. Decisions (proposed)

- **The brief and the debrief are never held.** They are what the owner reads.
- **Every other unattended session is held at the ceiling:** intake ingests, the connector fetches that run on their own timers (meetings, and triage when it ships), and Work Orders as today. A held tick logs one line and raises one alert a day ("intake held: 5-hour usage at <n>%"); inputs stay where they are and the next tick re-reads.
- **A fresh reading from every session.** `run_headless.sh` writes `usage5`, `usage7` and `usage5_at` to the health file after every run, from the result line the same way `nightshift_run` does, so the number the ceiling reads is at most one session old. The readers are unchanged: `nightshift_sched.five_hour_hold` keeps its "under 5 hours old" rule.
- **One setting.** `order_max_five_hour` keeps its name and applies to all held sessions. A vault that wants intake to run harder than Work Orders does not exist yet; a second key waits for that vault.
- **A reserve before the brief.** From `brief_time` minus 60 minutes to `brief_time`, the intake holds at half the ceiling, so a busy early morning leaves room for the brief. **Grill Q1:** is the reserve worth its rule, or is the ceiling alone enough? **Q2:** 0.6 for everything, or a lower ceiling for intake?

## 3. Changes

- `run_headless.sh`: after the session, parse the result line's usage block (the fields `nightshift_session` reads) and update `system/logs/nightshift/health-<date>.json` under `run.lock`'s existing hold, through a small `vaultlib` function shared with `nightshift_run` (`rep.record_usage(vault, date, usage, at)`). A result without usage leaves the file alone.
- `vaultlib/intake.py`: `run()` reads the health file and `five_hour_hold`; when held, it skips `process_inbox` and `process_digests` for this tick (meetings import, `now.py check` and briefing extraction still run: none starts a session), logs `{"held": "<reason>"}` to the intake log and alerts once a day. The reserve window uses `brief_time` from the config and halves the ceiling.
- `meetings_fetch.sh` and later fetch timers: the same hold through `nightshift.py hold-check` (a new read-only subcommand that exits 0 to run, 5 to hold, printing the reason) so bash callers share the Python rule.
- `/order status`: the Held line already exists; the report names intake holds too, from the intake log.
- `FOUNDRY.md`: the Work Orders paragraph's ceiling sentence becomes a paragraph of its own, "The usage ceiling", listing what is held and what is not.

## 4. Tests

pytest: `record_usage` writes and merges the three fields and leaves the file alone without usage; `Intake.run` with a health file at 0.7 skips inbox and digests, logs the hold and alerts once, and runs meetings and `now.py check`; at 0.5 everything runs; in the reserve window 0.35 holds and 0.25 runs; a reading older than 5 hours does not hold. bats: `run_headless.sh` with the stub claude's result carrying usage writes the health fields; `nightshift.py hold-check` exits 5 with a reason at 0.7 and 0 at 0.5; `meetings_fetch.sh` exits 0 and logs `held` without a session at 0.7.

Each fails before the change. Bound tools: pytest (`test_intake.py`, `test_nightshift_report.py`, `test_nightshift_sched.py`), bats (`headless.bats`, `meetings.bats`, `nightshift.bats`), the gate.

## 5. Out of scope

- Reading usage from an API outside a session. The result line is the only source today.
- Per-partition or per-command budgets.
- Changing how the brief and debrief behave at the limit (they fail with exit 4 and, with the Slack bridge, say so).
