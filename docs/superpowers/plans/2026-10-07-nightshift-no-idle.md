# Nightshift Without the Inactivity Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Nightshift window item is due inside the window when its budget fits and the 7-day usage is under 80%, whatever the user is doing.

**Architecture:** `vaultlib/nightshift_sched.py` loses `IDLE`, `idle_seconds()` and the `idle` parameter of `due()` and `pick()`; `nightshift_run.tick` stops computing idle time. The README and the Nightshift spec drop the inactivity wording.

**Tech Stack:** Python 3.11, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-nightshift-no-idle-design.md`

## Global Constraints

- Work on branch `fix/nightshift-no-idle` of `kferran/Foundry`. Commit there; do not push or open a pull request.
- Keep the window, the budget-fits check, the 7-day usage gate, `now`/`at` items, `waiting_reset` handling and the pick order unchanged.
- The memory session event files (`system/logs/memory/sessions/*.events`) stay; memory capture uses them.
- Run the two suites as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch python3 -m pytest system/tests/python/test_nightshift_sched.py system/tests/python/test_nightshift_run.py -q` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`.
- Bound tools: pytest (`test_nightshift_sched.py`, `test_nightshift_run.py`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- A window item while the user is active is due: pinned by `test_a_window_item_needs_no_inactivity`.
- Nothing can call the removed gate by accident: the same test asserts `IDLE` and `idle_seconds` are gone.
- The tick's candidate filter (`ns.due(..., 0)`) still treats every non-terminal item the same way; `test_nightshift_run.py` runs the tick end to end.

---

### Task 1: Remove the gate

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_sched.py`, `system/scripts/vaultlib/nightshift_run.py`, `README.md`, `docs/superpowers/specs/2026-10-06-nightshift-design.md`
- Test: `system/tests/python/test_nightshift_sched.py`

**Interfaces:**
- Produces: `due(fm, now_local, window, usage7) -> (bool, str)` and `pick(entries, now_local, window, usage7)`.

- [ ] **Step 1: Update the tests**

Edit 1 in `system/tests/python/test_nightshift_sched.py`. Find:

````text
    assert ns.due(item(), at(23), W, idle=3600, usage7=0.4)[0]
    assert ns.due(item(), at(12), W, 3600, 0.4) == (False, "outside the window")
    assert ns.due(item(), at(23), W, 60, 0.4) == (False, "user active")
    assert ns.due(item(budget="8h"), at(23), W, 3600, 0.4) == (False, "budget does not fit before the window ends")
    assert ns.due(item(), at(23), W, 3600, 0.9) == (False, "7-day usage above 80%")
    assert not ns.due(item(state="done"), at(23), W, 3600, 0.4)[0]


def test_now_and_at_skip_window_and_idle():
    assert ns.due(item(start="now"), at(12), W, 0, 0.4)[0]
    assert ns.due(item(start="at", start_at="2026-10-06T15:00:00-06:00"), at(15, 5), W, 0, 0.4)[0]
    assert not ns.due(item(start="at", start_at="2026-10-06T15:00:00-06:00"), at(14), W, 0, 0.4)[0]
````

Replace with:

````text
    assert ns.due(item(), at(23), W, usage7=0.4)[0]
    assert ns.due(item(), at(12), W, 0.4) == (False, "outside the window")
    assert ns.due(item(budget="8h"), at(23), W, 0.4) == (False, "budget does not fit before the window ends")
    assert ns.due(item(), at(23), W, 0.9) == (False, "7-day usage above 80%")
    assert not ns.due(item(state="done"), at(23), W, 0.4)[0]


def test_now_and_at_skip_the_window():
    assert ns.due(item(start="now"), at(12), W, 0.4)[0]
    assert ns.due(item(start="at", start_at="2026-10-06T15:00:00-06:00"), at(15, 5), W, 0.4)[0]
    assert not ns.due(item(start="at", start_at="2026-10-06T15:00:00-06:00"), at(14), W, 0.4)[0]
````

Edit 2 in `system/tests/python/test_nightshift_sched.py`. Find:

````text
    assert not ns.due(fm, at(12), W, 0, 0.4)[0]
    assert ns.due(fm, at(13, 1), W, 0, 0.4)[0]
````

Replace with:

````text
    assert not ns.due(fm, at(12), W, 0.4)[0]
    assert ns.due(fm, at(13, 1), W, 0.4)[0]
````

Edit 3 in `system/tests/python/test_nightshift_sched.py`. Find:

````text
    assert ns.pick(entries, at(23), W, 3600, 0.4)[0] == "n"
    assert ns.pick(entries[:2], at(23), W, 3600, 0.4)[0] == "a"
````

Replace with:

````text
    assert ns.pick(entries, at(23), W, 0.4)[0] == "n"
    assert ns.pick(entries[:2], at(23), W, 0.4)[0] == "a"
````

Edit 4 in `system/tests/python/test_nightshift_sched.py`. Find:

````text
    assert not ns.due(fm, at(12), W, 3600, 0.4)[0]
    assert ns.due(fm, at(23), W, 3600, 0.4)[0]
````

Replace with:

````text
    assert not ns.due(fm, at(12), W, 0.4)[0]
    assert ns.due(fm, at(23), W, 0.4)[0]


def test_a_window_item_needs_no_inactivity():
    assert ns.due(item(), at(23), W, 0.4) == (True, "")
    assert not hasattr(ns, "IDLE")
    assert not hasattr(ns, "idle_seconds")
````


- [ ] **Step 2: Run them to verify they fail**

Run: the suite command from Global Constraints.
Expected: FAIL, `6 failed, 24 passed`: every changed scheduler test fails with `TypeError: due() missing 1 required positional argument` (or `pick()`), because the code still takes `idle`.

- [ ] **Step 3: Remove the gate from the scheduler**

Edit 1 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
"""Window, idle, due and pick rules (Nightshift spec §3.2)."""
import subprocess
from datetime import datetime, time, timedelta
from pathlib import Path
````

Replace with:

````text
"""Window, due and pick rules (Nightshift spec §3.2)."""
from datetime import datetime, time, timedelta
````

Edit 2 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
IDLE = 1200        # seconds of inactivity before a window item starts
````

Replace with:

````text
````

Edit 3 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
def idle_seconds(vault, now: datetime) -> float:
    stamps = [p.stat().st_mtime for p in Path(vault).glob("system/logs/memory/sessions/*.events")]
    try:
        out = subprocess.run(["tmux", "list-clients", "-F", "#{client_activity}"], capture_output=True, text=True, timeout=5)
        stamps += [float(x) for x in out.stdout.split() if x.strip().isdigit()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return now.timestamp() - max(stamps) if stamps else float("inf")


````

Replace with:

````text
````

Edit 4 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
def due(fm: dict, now_local: datetime, window: tuple, idle: float, usage7: float) -> tuple:
````

Replace with:

````text
def due(fm: dict, now_local: datetime, window: tuple, usage7: float) -> tuple:
````

Edit 5 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
    if idle < IDLE:
        return False, "user active"
````

Replace with:

````text
````

Edit 6 in `system/scripts/vaultlib/nightshift_sched.py`. Find:

````text
def pick(entries, now_local: datetime, window: tuple, idle: float, usage7: float):
    rank = {"now": 0, "at": 1, "window": 2}
    ready = [e for e in entries if due(e[1], now_local, window, idle, usage7)[0]]
````

Replace with:

````text
def pick(entries, now_local: datetime, window: tuple, usage7: float):
    rank = {"now": 0, "at": 1, "window": 2}
    ready = [e for e in entries if due(e[1], now_local, window, usage7)[0]]
````


- [ ] **Step 4: Stop computing idle time in the tick**

Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    candidates = [e for e in entries if ns.due(e[1], ctx.local, ctx.window, float("inf"), 0)[0]
````

Replace with:

````text
    candidates = [e for e in entries if ns.due(e[1], ctx.local, ctx.window, 0)[0]
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    idle = ns.idle_seconds(ctx.vault, ctx.now)
    running = [e for e in entries if e[1].get("state") == "running"]
    chosen = running[0] if running else ns.pick(entries, ctx.local, ctx.window, idle, usage7)
````

Replace with:

````text
    running = [e for e in entries if e[1].get("state") == "running"]
    chosen = running[0] if running else ns.pick(entries, ctx.local, ctx.window, usage7)
````


- [ ] **Step 5: Run the tests to verify they pass**

Run: the suite command from Global Constraints.
Expected: PASS, `30 passed`.

- [ ] **Step 6: Update the README and the Nightshift spec**

Edit 1 in `README.md`. Find:

````text
**The Nightshift.** `/nightshift` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the nightly window (`nightshift_window`, default `22:00-05:00`, waiting while you are active), at a set time, or now. A plan item runs in a private clone under `nightshift_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report, `system/logs/nightshift/<date>.md`, starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server.
````

Replace with:

````text
**The Nightshift.** `/nightshift` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the nightly window (`nightshift_window`, default `22:00-05:00`), at a set time, or now. A plan item runs in a private clone under `nightshift_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report, `system/logs/nightshift/<date>.md`, starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server.
````


Edit 1 in `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Find:

````text
**Status:** Approved in brainstorming (2026-10-06), awaiting written-spec review
````

Replace with:

````text
**Status:** Approved in brainstorming (2026-10-06), awaiting written-spec review
**Changed:** 2026-10-07, the inactivity gate is removed (`2026-10-07-nightshift-no-idle-design.md`)
````

Edit 2 in `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Find:

````text
| When | Per item: the nightly window (config `nightshift_window`, default `22:00-05:00` local; waits while the user is active), `--at HH:MM`, or `--now`. A 15-minute timer runs one due item at a time. No count cap; per-item time budgets. |
````

Replace with:

````text
| When | Per item: the nightly window (config `nightshift_window`, default `22:00-05:00` local), `--at HH:MM`, or `--now`. A 15-minute timer runs one due item at a time. No count cap; per-item time budgets. |
````

Edit 3 in `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Find:

````text
3. **Pick** one due item: `now` items by queue time, then `at` items whose time has passed, then `window` items by queue time. A window item starts only when the time is inside the window, the user has been inactive for 20 minutes (newest tmux client activity and newest `system/logs/memory/sessions/*.events` modification on this host), `now + budget` is at or before the window's end, and the 7-day usage window is under 80%. Otherwise it waits for a later tick or night.
````

Replace with:

````text
3. **Pick** one due item: `now` items by queue time, then `at` items whose time has passed, then `window` items by queue time. A window item starts only when the time is inside the window, `now + budget` is at or before the window's end, and the 7-day usage window is under 80%. Otherwise it waits for a later tick or night.
````


- [ ] **Step 7: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 8: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(nightshift): a window item no longer waits for user inactivity

The scheduler drops the 20-minute inactivity gate (IDLE, idle_seconds,
and the idle argument of due and pick). A window item is due inside the
window when its budget fits and the 7-day usage is under 80%. The README
and the Nightshift spec drop "waits while the user is active".

Claude-Session: https://claude.ai/code/session_01647fUGoWRjf3w7UNpdzKpF
```

Run: `git add system/scripts/vaultlib/nightshift_sched.py system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_sched.py README.md docs/superpowers/specs/2026-10-06-nightshift-design.md && git commit -q -F .scratch/msg-1.txt`
