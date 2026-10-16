# Parallel Work Orders: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** One tick runs up to 3 Work Orders at once, refilling a slot when an order finishes.

**Architecture:** `tick()` keeps the global lock and becomes a loop. It starts `run_item` on worker threads (at most `MAX_PARALLEL = 3`), waits for any to finish, re-screens the queue and starts more. Shared files are written under one `threading.RLock`, and the report's atomic write gets a per-writer temp file.

**Tech stack:** Python 3.11 (threading), pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-parallel-orders-design.md` (approved 2026-10-16).

## Global Constraints

- No new config key, unit, timer or dependency. The global lock and the 15-minute timer stay as they are.
- Two plan items with the same `(repo, base)` never run at once.
- The 5-hour ceiling is read afresh before each new start. Running, waiting_reset and delivering items are never held by it.
- With `MAX_PARALLEL = 1`, every existing runner test passes unchanged.

## Review Focus

1. **A worker raises:** the others finish, the tick returns 1, and one `[orders]` alert names the item. Pinned in task 3.
2. **Two plans on one repo and base queued with a research item:** the research item runs beside the first plan, and the second plan starts only after the first finishes. Pinned in task 3.
3. **A claim directory left from a crashed tick** keeps that attempt from starting twice. The existing claim guard is unchanged.
4. **Health and report writes from two workers at once:** both stay whole JSON and Markdown. Pinned in task 1.
5. **The ceiling reached mid-tick by a finished session's reading:** the next queued item is held, and running ones go on. Pinned in task 3.

---

### Task 1: shared writes are safe from threads

**Files:** `system/scripts/vaultlib/nightshift_report.py` (`_atomic`), `system/scripts/vaultlib/nightshift_run.py` (`SHARED` lock: `Ctx.alert`, `Ctx.log`, `_finish`, `record_usage` in `run_item`, and the tick's own health and report writes), `system/tests/python/test_nightshift_report.py`.

- [ ] **Failing test:** eight threads each call `rep.write_health(vault, d, {"n": i})` 50 times. Expected: no exception (today two writers rename the same `.tmp` file, and one fails with FileNotFoundError), and the file is valid JSON.
- [ ] **Implement:** `_atomic` writes through `tempfile.NamedTemporaryFile(dir=path.parent, delete=False)`, then `os.replace`. `nightshift_run.SHARED = threading.RLock()`, held around the shared writes listed above.
- [ ] **Green:** `test_nightshift_report.py` and `test_nightshift_run.py`. **Commit:** `fix(orders): shared report and health writes are safe from parallel workers (#229)`

### Task 2: the tick runs up to three orders

**Files:** `system/scripts/vaultlib/nightshift_run.py` (`tick`, a `_startable` chooser, `MAX_PARALLEL`), `system/tests/python/test_nightshift_parallel.py` (new).

The tests replace `nr.run_item` with a fake. The fake records the moment each item starts and ends, how many run at once, and each plan's `(repo, base)`, sleeps briefly, then sets the item `done`.

- [ ] **Failing tests:**
  - four research items queued: never more than 3 at once, and all 4 finish in one tick;
  - two plans on one repo and base plus one research item: the research item overlaps the first plan, and the second plan starts after the first ends;
  - two plans on different bases run together;
  - with `health` at the ceiling, no queued item starts, and a `running` item still resumes;
  - a fake that raises for one item: the other two finish, the tick returns 1, and one alert names the item;
  - `MAX_PARALLEL = 1`: at most 1 runs at once.
- [ ] **Implement.** The tick body after the sandbox check becomes a loop:
  - start what can start now: `delivering`, then `running`, then queued items in `pick` order (re-picking after each start, skipping started ids and any plan whose `(repo, base)` is running), until `MAX_PARALLEL` run;
  - check the ceiling against a fresh health read before each queued start;
  - create the claim directory per start, as today;
  - each worker runs `run_item` in a thread and sets an `Event` in `finally`. A raised exception becomes rc 1 and an `[orders]` alert;
  - wait on the event, then reap finished threads and loop;
  - exit when nothing runs and nothing can start, returning the largest worker rc.
  - The Held line logic stays: it is written when a start is held.
- [ ] **Green:** the new file, the whole `test_nightshift_run.py` and `nightshift.bats`. **Commit:** `feat(orders): one tick runs up to three Work Orders at once (#229)`

### Task 3: the manual

- [ ] **Failing pin** in `commands.bats`, in the Work Orders tests: `grep -qF 'Up to 3 Work Orders run at once' FOUNDRY.md` and `grep -qF 'same repo and base' FOUNDRY.md`.
- [ ] **FOUNDRY.md, Work Orders:** "Up to 3 Work Orders run at once; the tick starts another as one finishes. Two plan orders on the same repo and base run one after the other. The 5-hour ceiling is checked before each start."
- [ ] **CHANGELOG.md** (after #239 merges; otherwise in the PR body): "- Up to three Work Orders run at the same time. (#<n>)"
- [ ] **Green:** `commands.bats`, then the full gate. **Commit:** `docs(orders): the manual says up to 3 run at once (#229)`

### Final review and acceptance

- **Fresh reviewer** on the whole branch.
- **Live acceptance:** in a `.scratch` clone, queue three research orders with a stubbed `claude` (the runner tests' stub) and run one real tick. All three start within seconds of each other, all deliver, and the report lists each once.
