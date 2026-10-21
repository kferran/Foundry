# Publish Gate Symlink Refusal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The publish gate refuses any path it touches that crosses a symlink below the vault root, so no publish writes, renames or reads through a link (#298).

**Architecture:** One private helper in `vaultlib/publish.py`, `_resolves(vault, rel)`, walks each prefix of a vault-relative path under the resolved vault root and returns False if any is a symlink. Each call site adds a reason through a refusal path that exists today; `_apply` also checks each journal entry before it builds a path from it, and `recover()` lists a run whose entries faulted in `failed` so it alerts.

**Tech Stack:** Python 3 stdlib (`os.path.realpath`, `Path.is_symlink`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-21-publish-symlink-escape-design.md`

## Global Constraints

- Change `system/scripts/vaultlib/publish.py` and its tests only; callers (`run_headless.sh`, `intake.py`, `nightshift_deliver.py`) stay as they are. One FOUNDRY.md line and one CHANGELOG line.
- Fail closed through today's statuses, exit codes and alert lines: no new alert text, exit code, config key or opt-out.
- No realpath containment rule: a link anywhere below the resolved vault root is refused, in-tree ones included. The vault root itself is resolved, so a vault reached through a linked parent works.
- Reason strings contain "symlink" or "unsafe journal entry": `symlink on the target path` (`_check`, and `record_stage` as `symlink on the target path: <target>`), `staged path is a symlink` (unchanged), `publish failed: unsafe journal entry` (`_apply`).
- Hold back an unsafe entry's staged file only when `staged == f"wiki/.staging/{run_id}/{target}"`, `safe_rel(target)` passes and the staged path has no symlink; otherwise move nothing.
- Every existing test passes unchanged. Core budget: `system/scripts` stays at or under 13,950 lines (13,916 at base).

## Review Focus

1. A linked `wiki/.staging/<run_id>/`: `read_decisions` and `commit_run`'s copy of `_decisions.jsonl` read through the link today (leaf `is_symlink()` only). Expect both to use `_resolves`; Task 1's staging test asserts no `_decisions.jsonl` lands in the run folder.
2. An owner who links `system/logs/` or `system/logs/runs/`: the journal check runs only on an uncommitted journal, after `_committed()`, so committed runs keep their `publish.json` and no alert repeats every tick. Task 2's journal-link test pins the uncommitted case.
3. A journal entry with an absolute or `..` target, or a dangling staged link: `_apply` today counts a missing staged file as "renamed before a crash" and reports it published. Expect the entry check before the existence branch; Task 2's entry tests assert the entry is in `problems`, not `published`.
4. A run whose `_apply` faults during `recover()` (today's `OSError` too): expect it in both `recovered` and `failed`, `publish.json` `recovery_failed`, staging removed. Task 2 pins it.
5. A vault reached through a linked parent folder publishes as before (Task 1, regression test; passes before and after).

---

### Task 1: Refuse symlinked targets and staging at validation and stage time

**Files:**
- Modify: `system/scripts/vaultlib/publish.py` (`record_stage`, `staged_targets`, `read_decisions`, `_check`, `commit_run`'s decisions copy; new `_resolves` after `safe_rel`)
- Test: `system/tests/python/test_publish.py`

**Interfaces:**
- Produces: `_resolves(vault, rel) -> bool`: True when `rel` is relative and no prefix of it, joined to `Path(os.path.realpath(vault))`, is a symlink (`is_symlink()` is True for dangling and looped links too). Task 2 uses it.

- [ ] **Step 1: Write the failing tests** (house style: `run`, `stage_new`, `decide`, `rec`, `reasons`, `LATER`, `os.symlink`, `tmp_path`; each staged note is a valid `concept("work", …, "[[Index]]")` with a `create` decision)
  - `test_a_note_staged_through_a_linked_folder_is_refused[private|workcells|outside]`: `wiki/work/concepts/linked` links to `wiki/work/private/`, `system/agents/workcells/` or `tmp_path/"outside"`; stage `…/linked/X.md`; `commit_run` → status `rejected`, `"symlink on the target path"` in the problem reasons, `not (dest / "X.md").exists()`.
  - `test_an_in_tree_link_into_meetings_is_refused`: `wiki/work/notes` → `wiki/work/meetings/`; stage `wiki/work/notes/X.md`; same assertions.
  - `test_a_leaf_link_target_is_refused[dangling|existing]`: `wiki/work/concepts/Leaf.md` links to `tmp_path/"gone.md"` (absent) or to `wiki/work/concepts/Kafka.md`; stage `Leaf.md`; reason present, `gone.md` absent, Kafka's text unchanged.
  - `test_a_linked_staging_folder_is_refused`: remove `wiki/.staging/<RID>/`, link it to `tmp_path/"st"` holding a valid `wiki/work/concepts/S.md` and `_decisions.jsonl`; `commit_run` → `rejected`, `"staged path is a symlink"`, `not (run / "wiki/work/concepts/S.md").exists()`, no `_decisions.jsonl` in `system/logs/runs/<RID>/`.
  - `test_record_stage_refuses_an_exact_target_under_a_linked_folder`: `wiki/work/concepts/linked` → `tmp_path/"out"` holding `X.md`; `snapshot(vault, RID, ["wiki/work/concepts/linked/X.md"])`; `record_stage` raises `PublishError` matching `symlink on the target path`; nothing at `wiki/.staging/<RID>/wiki/work/concepts/linked/X.md`.
  - `test_a_vault_reached_through_a_linked_parent_publishes`: `os.symlink(vault, tmp_path / "vlink")`, then snapshot, stage and `commit_run` a valid note through `tmp_path / "vlink"` → `published`. Regression: passes before and after.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `system/scripts/test.sh system/tests/python/test_publish.py -k "linked or leaf_link or in_tree"`
Expected: every new test but the regression FAILS (today the escapes publish, or reject with another reason).

- [ ] **Step 3: Implement**
  - `_resolves` as in Interfaces (prefix walk, not realpath equality, so a loop is refused).
  - `_check`: after the `.md` suffix check, before `_is_file_path`, return `[Problem(target, "symlink on the target path")]` when `not _resolves(vault, target)`.
  - `staged_targets(vault, run_id)`: replace `path.is_symlink()` with `not _resolves(vault, path.relative_to(vault))`.
  - `read_decisions` and `commit_run`: replace the `is_symlink()` leaf check on `_decisions.jsonl` with `_resolves` on its vault-relative path.
  - `record_stage`: before the `is_file()` check, raise `PublishError(f"symlink on the target path: {target}")` when `not _resolves(vault, target)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `system/scripts/test.sh system/tests/python/test_publish.py`
Expected: all pass.

- [ ] **Step 5: Commit** (`git commit -F <msg file>`)

### Task 2: Check journal entries and the journal; alert on a faulted recovery

**Files:**
- Modify: `system/scripts/vaultlib/publish.py` (`_apply`, `recover`)
- Test: `system/tests/python/test_publish_commit.py`

**Interfaces:**
- Consumes: `_resolves(vault, rel) -> bool` (Task 1), `safe_rel(rel) -> str` (raises `PublishError`).

- [ ] **Step 1: Write the failing tests** (each hand-writes `system/logs/runs/<RID>/publish.journal` with one uncommitted entry over the `run` fixture, then calls `publish.recover(run)`)
  - `test_recover_refuses_an_entry_target_through_a_linked_folder`: staged `wiki/.staging/<RID>/wiki/work/concepts/linked/X.md` is a real file, `wiki/work/concepts/linked` → `tmp_path/"out"`; result `RID in failed`; `publish.json` status `recovery_failed` with reason `publish failed: unsafe journal entry`; `not (tmp_path/"out"/"X.md").exists()`; the staged file is held back under `system/quarantine/<RID>/staged/`; the journal's last line is `{"committed": true}`.
  - `test_recover_never_moves_a_staged_symlink`: staged entry path is a link to `tmp_path/"evil.md"`; after recover, `not os.path.lexists(run / "wiki/work/concepts/L.md")`, `evil.md` still exists, reason present.
  - `test_recover_refuses_an_entry_commit_run_did_not_write[absolute|dotdot|unstaged]`: target `str(tmp_path / "abs.md")`; target `wiki/../../dotdot.md`; staged `wiki/work/concepts/Kafka.md` with target `wiki/work/concepts/Moved.md`. Reason present, entry not in `published`, nothing at the destination, and Kafka.md stays in place (no hold-back of a file the gate did not stage).
  - `test_recover_refuses_a_linked_journal`: the journal is a link to a file in `tmp_path` holding a valid entry for a staged note; `failed == [RID]`, `recovery_failed`, `"unreadable journal"` in the reason, the note not published.
  - `test_recover_lists_a_run_whose_entry_faulted_in_failed`: crash `commit_run` mid-rename (`KeyboardInterrupt`, as `test_recover_quarantines_conflicted_entries`), then `_rename` raises `OSError` during `recover`; `RID in result["failed"]` and `RID in result["recovered"]`, status `recovery_failed`, staging folder gone.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `system/scripts/test.sh system/tests/python/test_publish_commit.py -k "refuse or never_moves or faulted"`
Expected: all FAIL.

- [ ] **Step 3: Implement**
  - `_apply`: first thing for each entry with a `target`, before any path is built: `exact` is True when `safe_rel(entry["target"])` passes (catch `PublishError`), `entry["staged"] == f"wiki/.staging/{run_id}/{entry['target']}"` and `_resolves(vault, entry["staged"])`. If not `exact and _resolves(vault, entry["target"])`: append `Problem(entry["target"], "publish failed: unsafe journal entry")`, hold the staged file back only when `exact` (an `OSError` from the hold-back is ignored, as today), `continue`.
  - `recover()`: after `_committed(journal)` returns False, raise `ValueError("symlink on the journal path")` when `not _resolves(vault, journal.relative_to(vault))` (lands in the existing "unreadable journal" path). After `_report`, append `rd.name` to `failed` when `faults` (directly, not through `fail()`); keep `recovered.append`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `system/scripts/test.sh system/tests/python/test_publish_commit.py`
Expected: all pass.

- [ ] **Step 5: Docs, verify and commit**
  - FOUNDRY.md, the publish step of How it works: one sentence that the gate refuses a path with a symlink on it (target, its folders, staging, the journal).
  - CHANGELOG.md under `## 2026-10-21`: one Fixed line (a run that writes through a symlinked folder is refused; a recovery that could not apply an entry now alerts), ending `(#<PR>)`.
  - Run `test_publish.py`, `test_publish_commit.py`, `test_meetings.py`, `test_commit_runs.py`, `test_quarantine.py`, `test_stage_cli.py`, `test_nightshift_deliver.py`, `headless.bats`, `vault_integrity.bats`, `conformance.bats` through `system/scripts/test.sh`; all pass, core line count at or under 13,950.
  - Commit with `-F`.
