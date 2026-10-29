# A rejected brief retries once, and every unit's limit fits its worst case

**Date:** 2026-10-29
**Status:** draft, for the owner's review
**Grill:** not an owner idea: audit issue https://github.com/kferran/Foundry/issues/299 (the 2026-10-20 audit; in-flight plan `docs/superpowers/2026-10-28-in-flight-plan.md` phase 4)
**Builder check:** 2026-10-29, four questions and four wrong claims, all settled as my calls: systemd retries the brief, so prep reruns without lock juggling and each start keeps its own limit and ledger line (§3.1); the first rejection is logged, the second alerts (§3.1); an ingest that finds `run.lock` busy ends the intake tick (§3.2); the smoke unit passes its budget in `SMOKE_BUDGET` (§3.2); intake's sum is about 145 min, the watch's step budget was already right, and the drop-ins are absolute values (§3.2)
**Blueprint:** none: a retry in the brief's run and timeout values; no new feature shape.
**Lane:** feature, one pull request with a short plan. It changes unit templates and `run_headless.sh`'s brief path, so the owner merges it.

## 1. Why

#299 records a live vault with no morning brief on 2026-10-18 and a manual rerun on 2026-10-16. Its first item, one bad Now line rejecting the whole brief, is fixed by #366 and #412. Two items remain:

- **No retry.** A brief the publish gate rejects (`run_headless.sh` exit 5: rejected or empty, or "target changed during the run" when a client's sync lands mid-run, #107 limit 2) stays failed until someone reruns it by hand. `foundry-brief.service` has no `Restart=`, and `Persistent=` covers only a missed timer.
- **Limits below the worst case.** `conformance.bats` sums each unit's worst case from its steps and lists the units over their `TimeoutStartSec` (`TIMING_OVERRUNS`, which may only shrink):

| Unit | Worst case | Limit |
|---|---|---|
| intake | 7,270 s, and ingest's `run.lock` wait is unbounded (`flock 9`, no `-w`) | 90 min (5,400 s) |
| smoke | 3,000 s with one telemetry source, +120 s per further source | 35 min (2,100 s) |
| watch (intraday) | 1,815 s | 29 min (1,740 s) |
| smoke/calendar | 235 s | 210 s |
| smoke/watch | 1,225 s | 1,140 s |

A kill at the limit skips what a unit does last: the smoke check's timer and unit-drift rows, an intake tick's later runs. No kill has been seen since 2026-10-05, so the second item is low; the first cost two briefs.

## 2. Goals, non-goals, anti-goals

- **Goals:** a rejected brief gets one fresh run before anyone is told; every unit's limit holds its worst case, so `TIMING_OVERRUNS` is empty.
- **Non-goals:** retrying a debrief or an ingest (an ingest input already retries on the next tick); retrying a brief that failed for another reason (the usage limit, exit 4; claude's own failure, exit 1, which the alert already names); making units faster.
- **Anti-goals:** a retry loop; a retry that runs on stale inputs; a second brief published for one day.

## 3. Design

### 3.1 One retry for a rejected brief

systemd does the retry (my call after the builder check: a retry inside `run_headless.sh` would have to rerun `brief_prep.sh`, which takes `run.lock` itself, while holding it). `foundry-brief.service` gets `Restart=on-failure`, `RestartPreventExitStatus=1 2 3 4 6 7 SIGTERM SIGKILL`, `RestartSec=60`, and `StartLimitIntervalSec=1d` with `StartLimitBurst=2`, so exit 5 (publish rejected or empty) starts the unit once more. (systemd 252, Debian 12, refuses `RestartForceExitStatus=` on a `Type=oneshot` unit; `systemd-analyze verify` accepts this form, checked 2026-10-29.) A timeout kill also restarts once under the same start limit, which the spec accepts: a brief that timed out gets one more try. `ExecStartPre` reruns `brief_prep.sh`, so the inputs match the page the retry sees, and `run_headless.sh brief` runs as a fresh process with a new run id, a new snapshot and its own ledger line. Each start has its own `TimeoutStartSec`, so the brief's limit and the server drop-ins (`DROPIN_TIMEOUT`, absolute values) stay as they are. A first exit 5 is logged and raises no alert (my call: the retry runs before anyone is told). `run_headless.sh` raises one `[intake]` alert, which Slack carries at once, when a brief exits 5 and the day's ledger already holds a brief that exited 5: "the brief was rejected twice; see <both publish.json paths>". A debrief, an ingest, and a brief that exits 4 (usage limit) or 1 are never retried.

### 3.2 Limits that fit

Each unit's limit becomes its table sum rounded up to the next 5 minutes, with the step table as the source of truth, so `conformance.bats` checks the fit:

- **intake:** ingest's `flock 9` gets `-w "$HEADLESS_LOCK_WAIT"`, as the other commands have; a busy lock exits 6 with the "run.lock busy" alert, and `intake.py` ends the tick on exit 6 as it does on the run cap (no further input, no batch split, no second alert; the inputs stay for the next tick). The table sums `intake.lock`, the extension ticks, and `INTAKE_MAX_RUNS` × (`headless.lock` + `headless`) (about 145 min or more; the builder reads the exact sum from the table). `TimeoutStartSec` rises to fit it, and the server drop-in (`DROPIN_TIMEOUT` `foundry-intake`, an absolute value) rises by the same amount.
- **smoke:** the unit sets `Environment=SMOKE_BUDGET=<seconds>`, its `TimeoutStartSec` less the time the last rows (timers, units) need; `smoke_check.sh` skips a further telemetry row when the time left under `SMOKE_BUDGET` is under that row's limit, with a `smoke: time left too short for <row>; skipped` line. `TimeoutStartSec` rises to fit one telemetry source and the last rows. `conformance.bats` checks `SMOKE_BUDGET` against the unit's limit.
- **watch:** the manifest's `budget.steps` already counts the five server listings; `TimeoutStartSec`, the manifest's prose ("ends inside the unit's 29-minute limit") and the comment in `watch_fetch.sh` rise to fit.
- **smoke/calendar, smoke/watch:** each row's `--check` timeout counts its server listings, and the smoke unit's sum counts the raised rows.

`TIMING_OVERRUNS` ends empty, and its comment says a new overrun fails the gate.

## 4. Tests

- `units.bats`: the rendered brief unit carries the restart settings and the start limit, and `systemd-analyze verify` accepts them; the pinned limits (lines 55–58 and 282–284 today) move to the new values.
- `headless.bats`: a first brief exit 5 raises no alert; a second exit 5 the same day raises the "rejected twice" alert; a debrief exit 5 raises the alert it does today.
- `intake` tests: an ingest that exits 6 ends the tick with no batch split and no second alert.
- `conformance.bats`: `TIMING_OVERRUNS` is empty, the `TIMING_STEPS` comment no longer calls ingest's lock wait unbounded, and `SMOKE_BUDGET` fits the smoke unit's limit.
- the smoke suite: a run whose time left is short skips a further telemetry row with its line.

## 5. Done when

The gate is green with `TIMING_OVERRUNS` empty; #299's two remaining lines are ticked by the merged PR.

## 6. Left to the builder

The ledger query for "already rejected today", the rounding of each limit, the reserve inside `SMOKE_BUDGET`, and the test names. If a supported distribution's systemd rejects the restart settings on a `Type=oneshot` unit, the builder stops and reports it, since the retry then needs another design.
