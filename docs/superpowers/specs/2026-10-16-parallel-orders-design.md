# Parallel Work Orders: up to three orders at once

**Date:** 2026-10-16
**Status:** Draft, from the owner's grill answers on #229 (2026-10-16); awaiting approval.
**Issue:** #229.

## 1. Today

- `nightshift.py tick` takes `system/nightshift.lock`, picks one due item (`nightshift_sched.pick`) and runs it to the end inside the tick (`vaultlib/nightshift_run.py` `tick`, `run_item`).
- A 2-hour research order therefore holds every other order. On 2026-10-16, three orders queued together ran one after another.
- Each order already has its own clone or research folder, its own item directory and its own session process.

## 2. Decisions (owner, 2026-10-16)

1. Several orders are queued together most days, so this is worth building.
2. Research and plan orders both run side by side. Two plan orders with the same `repo` and `base` never run at once, because they would push competing branches from one plan.
3. Up to **3** at once: a constant `MAX_PARALLEL = 3` in the runner, with no config key (keep designs minimal). It becomes a key only if a vault needs another number.
4. Usage is protected by the existing 5-hour ceiling, checked before each new start. No per-batch budget.

## 3. Design: the tick becomes a small scheduler

The tick keeps the global lock for its whole life, as today. Its body becomes a loop:
- While fewer than 3 orders are running and a due item can start, start it on a worker thread: `run_item`, unchanged in what it does.
- When any worker finishes, re-screen the queue and fill the free slot.
- Exit when no worker is running and nothing can start.

This keeps everything that already works:
- **One process, one lock.** The systemd unit, its timer and the 15-minute cadence do not change. While a tick runs, the next timer firing finds the service still active and does nothing, as today. The running tick picks up orders queued meanwhile, because it re-screens after each finish.
- **Process control:** each session is still its own process group, and threads only send it signals. Cancel, budget and resume work per item as today.
- **Crash recovery:** a tick killed mid-run leaves its items `running`. The next tick resumes them through the existing path (`_stop_stale`, `session.pid`, `elapsed`), up to 3 at once.

**Choosing what starts:**
- **Running first:** items already `running`, or `delivering`, take slots first. Up to 3 resume, oldest first.
- **Then queued and waiting items:** `pick` order (waiting_reset first, then start rank, then queue time), skipping a plan whose `(repo, base)` matches a running plan.
- **Ceiling:** before each new start, read the health file afresh. A finished session records its usage reading, so a later start sees it. `five_hour_hold` with that reading decides; a held start leaves the slot empty and writes the Held line, as today.
- **Claim:** the `claim-<attempt>` directory stays the per-item guard against a double start.

**Shared writes go under one in-process lock.** These files are written by more than one worker:
- the day's report (`rep.write`), which `_atomic` writes through a fixed `.tmp` name;
- the health file (`rep.write_health`, `rep.record_usage`);
- the run ledger and alerts (`ctx.log`, `ctx.alert`);
- the Now and notify writes in `_finish` and delivery.

A `threading.Lock` around each of those calls keeps them whole. Item notes (`ni.update`) and item directories belong to one worker each and need no lock.

## 4. Tests

- **Two research items** queued together both start in one tick and both deliver.
- **A plan and a research item** run together.
- **Two plans on the same repo and base** run one after the other within the tick; plans on different repos run together.
- **Never more than 3 running**, with 4 queued.
- **Ceiling:** a reading at the ceiling holds a new start but lets a running item resume.
- **Shared writes:** concurrent finishes leave a whole report and health file, and every ledger line.
- **One at a time:** with `MAX_PARALLEL` patched to 1, today's behaviour and its existing tests stand. The selftest is unchanged.

## 5. Not in this version

- A config key for the number.
- Detached workers or a unit per order.
- A per-batch usage budget.
- Parallelism in `/order` readiness checks.

## 6. Manual

FOUNDRY.md's Work Orders section says up to 3 run at once and two plans on one repo and base never overlap. The brief's and debrief's Work Order report already lists every item, so it needs no change.
