# Work Order confinement, PR C (stale claims wait for a tick) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A research order's Stale claims reach ingest only after the owner ticks their Now line; a crossed-out line archives them unread.

**Architecture:** One module, `system/scripts/vaultlib/held.py`, owns the held files under `raw/<p>/held/`. Research delivery writes there and adds the line. Intake's Now step (under `run.lock`) releases a file on `[x]`, archives it on `[-]` and re-adds a missing line. The publish gate refuses a headless run that changes any Now line naming a held file.

**Tech Stack:** Python (`vaultlib`), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-30-work-order-confinement-design.md` §3.7 and §6 item 3 (approved by the owner's merge of #427, 2026-10-30)

## Global Constraints

- The publish gate and the Work Order runner are safety surfaces: the owner merges the PR.
- Held files are never ingested, never indexed and never cited until released (spec §3.7: "text from the web edits the wiki ... without the owner seeing it").
- Runner Now lines carry no `via`, so they never expire (`now.py:513`); a held file waits until the owner acts.
- A `shared` research order's line goes on the `work` page (`now.validate` refuses `shared`); the line names only the file path.
- Local git and tests run inside the sandbox (memory `sandbox-off-only-for-network`).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Template rule: no hostname, user path, remote URL, distro, account ID, or employer, client, codebase or people names.

## Rulings against the spec

- **Ruling 1, the statement names the path once and leads with it closely:** `Review <n> stale claims from a research Work Order before they reach the wiki: raw/<p>/held/<id>.stale-claims.md`. The id is in the path, and `fit=True` cuts from the end, so the path is the reason the line must stay under the cap. With an id at the 80-character limit the line is still under 300. Cost if wrong: a cut path, which the release step would then not find; Task 1's test pins a long id.
- **Ruling 2, a held file is found through its line's text**, on the page and in the current and previous month's `now-archive/` (the `nowmod.read` + `nowmod.archived` pattern of `triage.py:276`). `[x]` releases and `[-]` archives; an open line waits; no line means the add failed, so it is retried. Cost if wrong: a line hand-edited to drop the path re-adds a second line.
- **Ruling 4 (final review), a crossed file goes to `raw/<p>/held/rejected/`**, not `raw/<p>/archive/` as §3.7 says: recall and the debrief read `archive/`, so the rejected web text would reach every session. Only the runner's own line (owed, no who, evidence or via, the exact statement) decides, and ingest may not write `now-archive/`, which intake also reads. Cost if wrong: none; a rejected file can still be read by hand.
- **Ruling 3, the index skips `raw/*/held/`** (`index.NOT_INDEXED`), and the `session_digest` schema covers `raw/<p>/held/` so lint checks the file. Spec §3.7 is silent on both, and the Global Constraint above requires the first.

## Review Focus

1. A brief run whose staged `Now.md` reorders lines but leaves a held line byte-for-byte: the gate passes it.
2. A held line the owner ticks while a brief is running: the gate refuses the brief (its page differs), and the next intake tick releases the file.
3. The same research order delivered twice: no second held file and no second line.
4. A held file whose line was archived by `now.py archive` before intake saw the tick: still released (the archive is read).
5. A held file for a `shared` order: its line is on `work`, and `[x]` releases it to `raw/shared/notes/`.

---

### Task 1: Deliver into `raw/<p>/held/` with one owed line

**Files:**
- Create: `system/scripts/vaultlib/held.py`
- Modify: `system/scripts/vaultlib/nightshift_deliver.py:265-299` (`publish_research`, `stale_claims_input`)
- Test: `system/tests/python/test_nightshift_deliver.py` (its stale-claims tests at :461-520), new `system/tests/python/test_held.py`

**Interfaces:**
- Produces: `held.statement(path_rel: str, n: int) -> str`; `held.page(partition: str) -> str` (`work` for `shared`); `held.add_line(vault, path: Path, today: str) -> None` (raises what `nowmod.add` raises); `stale_claims_input` now returns `(path, n)` or None and writes `raw/<p>/held/<id>.stale-claims.md`.

- [ ] **Step 1: Write the failing tests:** `test_research_stale_claims_wait_in_held_with_one_owed_line` (after `publish_research`: the file is under `raw/work/held/`, nothing under `raw/work/notes/`, and `wiki/work/Now.md` has one open `owed` line naming the path and the count); `test_a_shared_orders_line_goes_on_work`; `test_a_second_delivery_writes_no_second_held_file_or_line`; `test_a_long_id_keeps_the_whole_path_in_the_line`; `test_a_line_that_cannot_be_added_leaves_the_held_file` (busy `run.lock`: the file exists and the result names the hold). Update the three existing stale-claims tests to `held/`.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement:** `stale_claims_input` writes to `held/` and its second-delivery check also looks in `held/`; `publish_research` calls `held.add_line` under `run.lock` (timeout 60) and reports a failed add in its detail.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(orders): research stale claims wait in held/ with an owed Now line (#301 S9)`.

### Task 2: Intake releases, archives or re-adds (§3.7)

**Files:**
- Modify: `system/scripts/vaultlib/held.py` (`step`), `system/scripts/vaultlib/intake.py:288-294` (`check_now` runs `held.step` inside its `run.lock` block, after `nowmod.check`)
- Test: `system/tests/python/test_held.py`, `system/tests/python/test_intake.py`

**Interfaces:**
- Consumes: Task 1's `held.page`, `held.add_line`.
- Produces: `held.step(vault, today: str, alert) -> None`.

- [ ] **Step 1: Write the failing tests:** `test_a_ticked_line_releases_the_file_to_notes` (`[x]` → the file is in `raw/<p>/notes/`, and the next `process_digests` takes it); `test_a_crossed_line_archives_the_file_unread` (`[-]` → `raw/<p>/archive/`, no ingest call); `test_an_open_line_keeps_the_file`; `test_a_missing_line_is_added_again`; `test_a_line_moved_to_the_archive_still_counts` (run `now.archive` after the tick); `test_a_shared_files_line_on_work_releases_to_shared_notes`; in `test_intake.py`, `test_the_now_step_releases_a_ticked_held_file` through `Intake(iv).check_now()`.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement** `held.step` per Ruling 2, moving with `os.replace` and alerting once on a move that fails.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(intake): a ticked held line releases its stale claims; a crossed one archives them`.

### Task 3: The gate refuses a headless change to a held line

**Files:**
- Modify: `system/scripts/vaultlib/publish.py:375-384` (`_check`, the `NOW_PAGE` branch)
- Test: `system/tests/python/test_publish.py` (beside `brief_run`, :499-540)

**Interfaces:**
- Consumes: `held.HELD` (a regex for `raw/[^/ ]+/held/[^ )]+\.md`), from Task 1's module.

- [ ] **Step 1: Write the failing tests:** `test_the_gate_refuses_a_brief_that_ticks_a_held_line`, `…_that_removes_a_held_line`, `…_that_adds_a_held_line`, `…_that_rewords_a_held_line` (each: the reason is `a Now line naming raw/<p>/held/ changes only by hand`); `test_the_gate_passes_a_brief_that_keeps_held_lines_and_moves_others` (Review Focus 1).
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement:** in the `NOW_PAGE` branch, compare the multiset of old and new lines matching `held.HELD`; any difference is one `Problem`.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(publish): a headless run cannot change a held stale-claims line`.

### Task 4: Index, schema, docs, change file, core cap

**Files:**
- Modify: `system/scripts/vaultlib/index.py:20-22` (`NOT_INDEXED` gains `raw/*/held/`, in the form the list uses), `system/schemas/session_digest.md:4` (`folders` gains the three `raw/<p>/held/`), `CLAUDE.md` Directory Map (one clause on `raw/<partition>/held/`), `FOUNDRY.md` (the research Stale claims sentence and the Now section), `changes/2026-10-31-work-order-confinement-c.md`, `system/tests/vault_integrity.bats` (`CORE_CAP`)
- Test: `system/tests/python/test_index_rules.py` (a held file is not indexed), the docs and cap suites

- [ ] **Step 1: Write the failing test** `test_a_held_file_is_not_indexed`; run it → FAIL; add the entry → PASS.
- [ ] **Step 2:** Schema, CLAUDE.md, FOUNDRY.md and the change file; run `system/scripts/test.sh system/tests/vault_integrity.bats system/tests/conformance.bats system/tests/commands.bats`; raise `CORE_CAP` by the measured overrun with its reason line.
- [ ] **Step 3: Commit** `docs(orders): held stale claims in the manual, index and schema; core cap`.

### After the tasks

- Whole-branch review (fresh reviewer, most capable model).
- Live acceptance in a throwaway clone with the real `claude`: one research order whose findings carry a Stale claims section; the held file and the line appear; tick it by hand; one intake tick releases the file; a brief run in the clone publishes without touching the line. Delete the clone.
- The PR: "Part of #402"; closes the #301 S9 line; the owner merges.
