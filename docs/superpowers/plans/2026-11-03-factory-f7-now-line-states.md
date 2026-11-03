# Factory F7, PR 1: the Now line's state machine (#478) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put every code change to a Now line's mark or stamp through one table, `vaultlib/now_states.py`. The publish gate refuses a brief that changes an existing line's state, a reopened expired line stays open, and an unknown mark is listed by `review`.

**Architecture:**
- `now_states.py` holds `STATE`, `ALLOWED` and `transition()`.
- `vaultlib/now.py` (the stamp and `check`) and the telemetry extension's `rca.py` (`filed`, `reopen`) call it.
- `publish.py`'s Now screen compares old and staged states for brief runs.
- The line format, the merge driver and the owner's hand edits stay as they are.

**Tech Stack:** Python 3 stdlib, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-11-03-factory-f7-now-line-states-design.md`

## Global Constraints

- The line format, `LINE`/`STAMP` regexes, merge ranking and every existing close wording stay as they are. The spec's §6 questions O1–O3 are not built here.
- A refused transition leaves the line unchanged and appends `{ts, writer, from, to, statement_hash}` to `system/logs/now-<YYYY-MM>.jsonl`, the file `check` already logs to. It never raises out of a unit.
- Core cap: there are 29 lines of headroom (16,451 of 16,480). Measure once at the end and raise in this PR with a comment naming this spec. The owner approves at merge.
- Bats ruling R1. Tests stub claude and `gh`.
- The template rule holds: fixtures use invented statements.
- One `changes/` file: `- Changed: the brief can only add Now lines, never tick or drop one; a reopened expired line stays open (#478)`.
- Delivery: one PR, branch `feat/factory-f7-now`. The owner merges it (publish gate and Now writers).

## Review Focus

1. Every mark or stamp written in code comes from `now_states.transition()`. A grep test enforces it (Task 6); check that the grep's exclusions are only fixtures and the table itself.
2. The brief refusal compares states by line key (the line without its mark and stamp, as `merge` pairs them). A brief that rewrites a statement and changes its mark must not slip through as one line removed plus one line added.
3. The table refuses T15 (`rca.reopen`) on an open line. Check that `rca_file.sh:96-99` never reaches reopen with an open line in a legitimate flow (test_rca.py:206-224).

## Task 1: the table

- [ ] Write failing `system/tests/python/test_now_states.py`.
  - Walk every (writer, from, to) triple from the spec §3 table. Assert the table's pairs return a new line and every other pair returns `None`.
  - Assert `STATE` maps `[ ]`, `[x]`, `[X]`, `[-]`, stamped and unstamped, plus `[/]` as unknown.
- [ ] Implement `system/scripts/vaultlib/now_states.py`. It uses the standard library and imports only `now.STAMP` and `now.CLOSED`.
- [ ] Run the tests and commit.

## Task 2: the stamp and the reopened-expired fix

- [ ] Failing tests in `test_now.py`:
  - An unstamped `[-]` and `[x]` get `ticked` through `transition()`, with output unchanged from today (test_now.py:227-235 stays green).
  - An open line with an `expired` stamp loses the stamp and its `[via::]`, then survives two `check` runs.
- [ ] Route `now.stamp` through `transition(writer="stamp")`. In the expired case, drop `[via::]` with the existing field helpers.
- [ ] Run `test_now.py` in full and commit.

## Task 3: `check` (T7, T8)

- [ ] Failing test: a check that would close a line already closed by hand keeps the hand mark. The table refuses done→done by `check`, and today's re-read already keeps the hand tick (test_now.py:294-305), so this pins it.
- [ ] Route the evidence close and the expiry through `transition(writer="check")`.
- [ ] Run and commit.

## Task 4: `rca.filed` and `rca.reopen` (T14, T15)

- [ ] Failing tests in the telemetry extension's `test_rca.py`:
  - `filed` on a done line stamps `filed <KEY>` as today.
  - `reopen` on an open line is refused and logged, with the page byte-for-byte unchanged.
  - `reopen` on a done line works as today (test_rca.py:206-224).
- [ ] Route both through `transition(writer="rca")`. Keep their `run.lock` waits.
- [ ] Run the telemetry suites and commit.

## Task 5: the brief's publish guard

- [ ] Failing test in `test_publish.py`, or the suite that holds the brief's Now screen: a brief run whose staged page ticks an existing open line is rejected with `now: the brief changed <statement>: open to done`.
  - A run that only adds open lines passes.
  - A run that rewrites an existing line's statement and also ticks it is rejected. Pair lines by their key, as in Review Focus 2.
- [ ] Implement in `publish.py`'s Now screen (`:380-393`), for runs whose command is `brief` only.
- [ ] Run `headless.bats` and the publish tests, then commit.

## Task 6: unknown marks, the grep guard, close

- [ ] Failing tests:
  - `now.py review` lists `- [/] owed: x (since 2026-11-01)` as unreadable with the fix text.
  - `held._mark` treats `[/]` as open (test_held.py).
- [ ] Implement both.
- [ ] Add the grep test: no file under `system/scripts` or `extensions/*/scripts` other than `now_states.py` contains `- [x] `, `- [-] ` or `_(closed: ` as a string it writes. Exclude comments and docstrings by a narrow pattern, and list any exception with its reason.
- [ ] Measure the core cap and raise it.
- [ ] Add the change file.
- [ ] Run lint, `pipeline.bats`, the full Python suite and `/foundry-review`.
- [ ] Open the PR, with spec §6 O1–O3 listed for the owner.
