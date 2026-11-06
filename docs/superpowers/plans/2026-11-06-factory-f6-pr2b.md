# Factory F6, PR 2b: lock order and cross-unit waits (#477) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Fail CI when two nodes take two locks in opposite orders (P9, G1).
- Fail CI when a node can wait on a lock for less time than another node can hold it, and has no `busy` edge that says what happens then (P10, G2, G7).

**Architecture:**
- `system/tests/pipeline_graph.py`: adds P9 and P10.
- `system/pipeline.yml`:
  - `locks` lists are outermost first.
  - An optional `waits: {<lock>: <TIMING_VALUES key>}` names a node's wait.
- `system/tests/pipeline.bats`: fixtures for each new problem line.

No runtime change.

**Tech Stack:** Python 3 stdlib, PyYAML, bats.

**Spec:** `docs/superpowers/specs/2026-11-04-factory-f6-pr2-design.md` (G1, G2, G7). Stacked on PR 2a (#520).

## Builder check (2026-11-06, `feat/f6-pr2a` at `70e8b0e`)

**Acquisition order in the code (outermost first):**

| Node | Order | Evidence |
|---|---|---|
| intake | `intake.lock` → `run.lock` → `stage.lock` | `vaultlib/intake.py:980`, then per run; `publish.py:163` inside a run |
| nightshift | `nightshift.lock` → `run.lock` | `nightshift_run.py:1092`, then `:651` and `nightshift_deliver.py:254` |
| brief, debrief | `run.lock` → `stage.lock` | `run_headless.sh:123-127`, then `publish.py:163` |
| sync | `run.lock`, then git's `index.lock` checked under it | `vault_sync.sh:122-129` |

**Other findings:**
- **There is no `archive.lock` file.** `ARCHIVE_LOCK_WAIT` is the brief prep's wait on `run.lock` (`brief_prep.sh:122-124`); `archive.lock` is only a `TIMING_VALUES` key.
- **Debrief's missing `busy` edge.** Debrief has a busy path its node does not declare: `run_headless.sh:127-129` alerts `[intake] … skipped: run.lock busy` and exits 6. The node gains `busy: alert:intake`.
- **Sync's lock order.** Sync's list reads `[index.lock, run.lock]`; it becomes `[run.lock, index.lock]`, the order the script uses.
- **G2's hold bound.** G2 measures a hold by the holder's `TIMING_STEPS` sum. P10 uses the holder's `TimeoutStartSec` instead. That limit bounds every hold, `conformance.bats` already proves the step sums fit under it, and it needs no second parser of the step table. It is the stricter of the two, so it can only ask for more `busy` edges.
- **G7.** A `flock -n` caller waits 0 s, so P10 covers it with no special case.

## Global Constraints

- No runtime change. The core cap and the schema count are unchanged.
- New problem lines:
  - `<a>, <b>: <node> takes <a> first, <node> takes <b> first` (P9).
  - `<node>: shares <lock> with <other> and has no busy edge` (P10).
  - `<node>: waits <w> s for <lock>, which <other> can hold for <h> s, and has no busy edge` (P10).
  - `<node>: waits names no TIMING_VALUES key <key>` (P10).
- **Bats ruling R1:** no mid-test `!`, no `&&` assertion chains, and no wall-clock assertions.
- **Change file:** none (no vault user sees a change).
- **Delivery:** branch `feat/f6-pr2b`, its PR based on `feat/f6-pr2a` until #520 merges; the owner merges.

## Review Focus

1. Each `locks` order matches the code (the table above).
2. Each `busy` edge names what the code does when the lock is busy.

## Task 1: P9 lock order

- [ ] For each node, every pair of locks in list order is a claim. Two claims in opposite orders print one line per pair.
- [ ] Reorder sync's list. Fixture: two nodes with `[run.lock, notify.lock]` and `[notify.lock, run.lock]`.

## Task 2: P10 cross-unit waits

- [ ] For each lock a node lists that another node also lists, the node needs a `busy` edge that is not `none`.
- [ ] The exception: its `waits` entry for that lock is a `TIMING_VALUES` key whose value is at least the other node's `TimeoutStartSec`.
- [ ] Add `busy: alert:intake` to debrief.
- [ ] Fixtures: a shared lock with no busy edge; a wait shorter than the hold; a wait at least as long as the hold (passes); an unknown key.

## Task 3: docs and the gate

- [ ] FOUNDRY.md factory line: one sentence on lock order and busy edges.
- [ ] Run `pipeline.bats`, `conformance.bats` and `vault_integrity.bats`, then `review_diff.py`, then open the PR.
