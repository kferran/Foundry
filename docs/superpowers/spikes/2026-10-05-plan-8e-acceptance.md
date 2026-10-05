# Plan 8e acceptance

**Date:** 2026-10-04 (config timezone; 2026-10-05 UTC) · **Branch:** `feat/plan-8e` · **Commit:** b6a2a53 (Tasks 1–2 plus the final-review fix) · **Debian host:** Debian 12.15 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2, Claude Code 2.1.289. Executed natively on the Debian host. The host name is kept out of this record (template rule).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Debian host | e725a36 (Task 2) | 0 | 16/16 PASS | lint 0 errors |
| Debian host | cdc6e33 (final-review fix) | 0 | 16/16 PASS | lint 0 errors, 4 warnings (older than this plan) |

## Live run (spec §8.1, 8e; Plan 4a steps re-run where this branch changed them)

A throwaway clone under `~/.cache/jarvis-accept/`, removed afterwards: `system/config.md` from the example (`machine_role: standalone`), `core.hooksPath .githooks`, `commit_runs.py --init-cutover`. `claude` on `PATH`. No units were installed.

| Step | Result |
|---|---|
| Ingest of one inbox note (`intake.py`) | exit 0; published `wiki/personal/concepts/NightlyExportJob.md` |
| `run.lock` held 11 minutes by `flock … sleep 660`; `run_headless.sh brief` started 60 s in | exit 0 after waiting **628 s** (longer than the old 600-second limit, which would have given exit 6); published `briefings/2026-10-04.md`; no `run.lock busy` alert |
| `debrief_prep.sh`, then `run_headless.sh debrief` | exit 0; published `briefings/2026-10-04.debrief.md`; its runs table lists each run's `exit`, `publish.status`, published, rejected and conflicts |

Ledger, in order:

```
20261004T213223-ingest-087a  started 21:32:23  exit 0  published
20261004T213348-brief-47a1   started 21:43:48  exit 0  published
20261004T214417-debrief-b16a started 21:44:17  exit 0  published
```

The brief's run id carries the time it was queued (21:33:48) and its `started_at` the time it took the lock (21:43:48): one clock reading names the run (final-review fix), so a run that waits past midnight keeps its day.

## Cost

Three live runs: $0.20, $0.21 and $0.23 (the session logs were read by file, not matched to runs), **$0.65** in total. No calendar fetch: the brief's prep step was not run.

## Verdict

**PASS.** A brief waiting longer than the old 600-second limit takes the lock and publishes, and the debrief reports the ledger's publish fields. The gate passes 16/16 on the tool floor.
