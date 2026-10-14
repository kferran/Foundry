# Shrink Guard Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The publish gate's shrink guard accepts a heading renamed in place when its section keeps every line, and `/ingest` retires a state-encoding heading by renaming it (#160).

**Architecture:** One helper in `system/scripts/vaultlib/publish.py` splits a body into (heading, section lines) in order, reusing `linkmod.code_free_lines` and `HEADING` as `_headings` does. `_shrink` subtracts the headings it finds renamed in place from the removed set. The reason wording stays `shrink guard: headings removed: …`.

**Tech Stack:** Python (pytest), bats.

**Spec:** `docs/superpowers/specs/2026-10-14-shrink-guard-rename-design.md`

## Global Constraints

- Work on branch `feat/shrink-guard-rename` in worktree `.scratch/rename`. Commit there; do not push or open a pull request.
- Run suites through `system/scripts/test.sh <suite.bats | pytest path> [args…]` outside a sandbox. Never run the gate (`verify_setup.sh`); the main session runs it.
- Bound tools: pytest (`test_publish.py`, `test_publish_commit.py`, `test_stage_cli.py`, `test_commit_runs.py`, `test_meetings.py`, `test_nightshift_item.py`, `test_intake.py`), bats (`commands.bats`).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- A heading removed with its section stays refused even when the body keeps 60% of its length (the new test separates the heading verdict from the ratio check).
- Position is the ordinal among same-level headings; the candidate's title must be absent from the old note, so a moved heading never pairs with an existing one.
- Section lines come from the raw body, so a fenced block under a renamed heading is guarded too; heading detection ignores fences, as before.
- `deprecate` and `supersede` stay exempt; the frontmatter and 60% checks are unchanged.

---

### Task 1: The guard accepts a rename in place

**Files:**
- Modify: `system/scripts/vaultlib/publish.py`
- Test: `system/tests/python/test_publish.py` (after `test_shrink_guard`)

**Interfaces:**
- Produces: `_sections(body) -> list[(heading, set[str])]`; `_shrink` no longer reports a heading renamed in place.

- [ ] **Step 1: Write the tests.** A `sectioned` fixture writes `wiki/work/concepts/Deploys.md` with three `##` sections (the middle one titled `## Release train (merged, not yet in the vault)`), then snapshots the run and stages the note. Tests, each citing `(#160)`:
  - `test_shrink_guard_accepts_a_heading_renamed_in_place`: the middle heading renamed to `## Release train`, one line added to its section: no problems.
  - `test_shrink_guard_refuses_a_rename_that_drops_section_lines`: renamed, one of its two lines removed (body still above 60%): `headings removed` reported.
  - `test_shrink_guard_refuses_a_heading_removed_with_its_section`: the middle heading and its two lines removed (body above 60%): `headings removed` reported, no `below 60%`.
  - `test_shrink_guard_refuses_a_renamed_heading_moved_elsewhere`: the middle section moved to the end under a new title, body kept: `headings removed` reported.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/python/test_publish.py -k shrink`. Expected: the accept test FAILs (`headings removed`); the three refuse tests pass (they pin today's behaviour).
- [ ] **Step 3: Implement** `_sections` and the rename subtraction in `_shrink` (spec rules 1-3).
- [ ] **Step 4: Run the suite** and every pytest file that imports `publish`.
- [ ] **Step 5: Commit.** `fix(publish): the shrink guard accepts a heading renamed in place (#160)`.

### Task 2: Ingest retires a state heading by renaming it; documents match

**Files:**
- Modify: `.claude/commands/ingest.md` (step 5, patch bullet), `FOUNDRY.md` (publish step and the Staged publish line), `docs/superpowers/specs/2026-09-30-vault-template-design.md` (§6.20 item 4)
- Test: `system/tests/commands.bats` (new test after "ingest: headless contract, allowlisted index calls, decisions file")

- [ ] **Step 1: Write the test:** `@test "ingest: retire a state heading by renaming it in place (#160)"` greps the ingest sentence and the FOUNDRY.md sentence.
- [ ] **Step 2: Run it to verify it fails.** `system/scripts/test.sh system/tests/commands.bats -f '#160'`. Expected: FAIL.
- [ ] **Step 3: Implement:** the ingest sentence; FOUNDRY.md says a heading renamed in place with its section kept passes; the design spec's item 4 says the same.
- [ ] **Step 4: Run** `commands.bats` and `test_intake.py`.
- [ ] **Step 5: Commit.** `docs(ingest): retire a state heading by renaming it in place (#160)`.
