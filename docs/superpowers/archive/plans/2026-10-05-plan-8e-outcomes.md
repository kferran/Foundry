# Plan 8e outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-05 (plan: `2026-10-05-plan-8e-real-use-fixes.md`, commits 1cbf016..b6a2a53 plus this status commit). Executed natively on the Debian host: each task applied the plan's tested patches red-then-green, then one whole-branch review on Opus and one test-first fix. Acceptance: `docs/superpowers/spikes/2026-10-05-plan-8e-acceptance.md`.

Final verification at b6a2a53: `verify_setup.sh` exit 0 (16/16) on the Debian host (Debian 12.15, jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2); lint 0 errors. Live acceptance PASS, $0.65.

**How this plan was scoped:** a triage of 34 deferred minors from Plans 1–8d against the code at ed2bc00 (real server-plus-client use only) found 7 fixed, 2 moot and 24 cosmetic or without a real trigger. One stayed: `/debrief` read the ledger's publish fields at the top level. A second, found during triage, was added: brief and debrief gave up on `run.lock` after 600 s behind an ingest backlog and nothing retried them.

**Next on the roadmap:** set up the real vault (one server, one client).

## Rulings

- Spec: Ruling: the first rev 4 draft retried skipped runs from every server sync cycle; an independent review found it fired on days with no run at all, depended on `origin`, and needed `is-active` handling, so the user chose a longer lock wait instead (2026-10-05) — cost if wrong: a lock held longer than one sync plus one ingest still skips the run.
- Spec: Ruling: 1400 s, not the draft's 1100 s, to cover a sync tick taking the lock between two ingest runs (found by the re-review's `flock` experiments) — cost if wrong: a stuck holder delays the brief's exit-6 alert by about 5 minutes.
- Spec: Ruling: debrief 45 minutes, not 40, because 40 left 70 s for its prep — cost if wrong: none.
- Spec: Ruling: intake's own 600-second wait for briefing extraction stays (a separate lock use) — cost if wrong: an alert when a holder runs over 10 minutes.
- Task 3: Ruling: `run_headless.sh` and `debrief.md` changed, so the Plan 4a acceptance re-run is scoped to what changed: the lock-wait brief, one ingest and one debrief; the second-brief and `related` steps were skipped — cost if wrong: an untested path through the other commands, about $0.50 to cover.
- Final: Ruling: the reviewer's Minor 1 was re-graded to Important: with a `debrief_time` after about 23:36, the longer wait could move a debrief past midnight, stamp it with the next day and lose it at publish. Fixed (below) — cost if wrong: run ids of queued runs sort by queue time, not lock time.
- Final: Ruling: the spec's 8e test items, spliced into the 8c bullet, now have their own bullet — cost if wrong: none.

## Final-review fixes

- fixed a late debrief crossing midnight: `run_id`, `TODAY` and the ledger month now come from one clock reading taken before the lock. `headless.bats` "a brief that gets run.lock after midnight keeps the date it started on" RED (run id `20260102…`, exit 5) → GREEN; gate 16/16.

## Deferred minors

- The roughly 170 s left after one sync hold plus one ingest run is not measured on a large wiki (publish and snapshot time while the lock is held).
- `debrief.md`'s "(the publish lists sit under `publish`, not at the top level)" is redundant and a not-X contrast.
- The roadmap's Plan 9 row says "after every other plan" while Plan 10 runs after Plan 9 (older than this plan).
- Calendar spec line 155 still says the brief unit's limit is 30 minutes (Plan 8d history; 45 since Plan 8e).
- The 24 triaged items that stayed out are listed with their reasons in the triage; none had a real trigger.
