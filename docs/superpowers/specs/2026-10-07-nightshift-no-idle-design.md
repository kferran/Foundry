# Nightshift: remove the inactivity gate

**Date:** 2026-10-07
**Status:** Approved by the owner in chat (2026-10-07: "yes, remove it"), awaiting written-spec review
**Changes:** `2026-10-06-nightshift-design.md` §1 (When) and §3.2 step 3

## 1. Problem and decision

A window item starts only after the user has been inactive for 20 minutes: no tmux client activity and no memory session event on the host (`IDLE = 1200` in `vaultlib/nightshift_sched.py`). The owner asked to remove it ("We need to remove the inactivity clause, that's dumb"). The window already says when unattended work may run; the gate only delays items while the owner works, and on a server where the owner keeps a tmux client attached it can hold the queue all night.

**Decision:** a window item is due when the time is inside the window, its budget fits before the window ends, and the 7-day usage is under 80%. Nothing reads user activity.

Kept unchanged: the window (`nightshift_window`), the budget-fits check, the 7-day usage gate, `now` and `at` items, `waiting_reset` handling and the pick order.

## 2. Changes

- `system/scripts/vaultlib/nightshift_sched.py`:
  - remove `IDLE` and `idle_seconds()`, and the `subprocess` and `Path` imports they alone use;
  - `due(fm, now_local, window, usage7)` and `pick(entries, now_local, window, usage7)` lose their `idle` parameter;
  - `due()` loses its `"user active"` branch;
  - the module docstring drops "idle".
- `system/scripts/vaultlib/nightshift_run.py` (`tick`): the `ns.idle_seconds` call goes; the two calls to `ns.due` and `ns.pick` drop their idle argument.
- The memory hooks keep writing `system/logs/memory/sessions/*.events`; memory capture uses them (`memory_activity.sh`), so they are not "fed only" to the gate.
- `README.md` (the Nightshift paragraph): "(`nightshift_window`, default `22:00-05:00`, waiting while you are active)" becomes "(`nightshift_window`, default `22:00-05:00`)".
- `docs/superpowers/specs/2026-10-06-nightshift-design.md`: §1's When row drops "waits while the user is active"; §3.2 step 3 drops the inactivity condition. A line under its Status records the change and points here.

## 3. Tests

`system/tests/python/test_nightshift_sched.py`:
- every `due` and `pick` call drops the idle argument;
- `test_window_item_rules` loses the `"user active"` assertion;
- a new test: a window item inside the window is due whatever the time since the last activity, which now means `due()` takes no activity input at all. It asserts `ns.due(item(), at(23), W, 0.4) == (True, "")`, and that `nightshift_sched` has no `idle_seconds` or `IDLE` (so no caller can bring the gate back by accident).

Each changed test fails before the code change (wrong argument count or the attribute still present) and passes after.

Bound tools: pytest (`system/tests/python/test_nightshift_sched.py`, `test_nightshift_run.py`), the gate.

## 4. Out of scope

- Any other Nightshift change (the source fix is a separate plan).
- Changing the vault's `nightshift_window`.
