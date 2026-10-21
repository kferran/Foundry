# Publish gate: refuse symlinked paths

**Date:** 2026-10-21
**Status:** draft for the owner
**Grill:** not an owner idea: audit finding #298 (high), 2026-10-20 audit
**Builder check:** 2026-10-21, two questions, both settled as the builder's calls: a faulted recovery is listed in `failed` so it alerts (P10), and hold-back moves only a file at its exact staging path. One wrong claim corrected (the meeting import's refusal path).
**Blueprint:** Compile run (the publish gate)
**Lane:** feature (a safety surface: the publish gate); the owner merges

## Intent and why

The publish gate (`system/scripts/vaultlib/publish.py`) is the only route by which model output reaches the vault (P2), and it is what keeps `private/` and the partition walls closed (P5). Today every check is lexical, on the declared path, while every write follows symlinks. A probe in a scratch vault published into `wiki/<p>/private/`, `system/agents/workcells/` and a folder outside the vault, each time through a symlinked folder under `wiki/<p>/`.

How the escape passes the gate today: `_target_files` walks with `os.walk` (no `followlinks`), so files behind the link are absent from `snap["files"]`. `_expected` returns `None`, `_conflict` passes when nothing exists at the destination, `_is_file_path` follows the link (`is_dir`), and `_apply` runs `mkdir(parents=True)` and `os.replace` through it as a fresh create.

The headless model cannot make a symlink (its tools are Edit inside its own staging folder and a fixed set of `vault_index.py` subcommands). Links reach the vault from a git sync, the owner, or another tool. The gate must hold whatever is already on disk.

## Goals

- No publish writes, renames or reads through a symlink on any path the gate handles: the target, the target's folders, the staged source, the staging folder, the journal and the journal's entries.
- A hit fails closed through today's refusal paths: same statuses, exit codes and alert lines.
- `recover()` refuses an uncommitted journal written before the fix if any of its entries crosses a link.

## Non-goals

- The model's read side. The headless `Read(wiki/*/private/**)` deny is lexical too; whether Claude Code resolves links before it matches is unverified. That needs its own probe and issue.
- The Work Order output path. A research run's allowlist is the queue note's own `output`, so the gate has no rule of its own requiring `wiki/<p>/`. Issue #298 item 1 (full re-screen at each tick) covers that.
- Undoing writes that already escaped through a journal committed before the fix.

## Anti-goals

- No realpath "containment" rule that lets a link stay as long as it lands inside `wiki/<p>/`. An in-tree link (`wiki/work/x` to `wiki/work/meetings`) would then pass the lexical meetings, Now-page, schema-location and partition checks on a path that is not where the file lands.
- No new alert text, exit code, config key or opt-out.

## Constraints

- Fail closed through today's statuses, exit codes and alert lines.
- Change `publish.py` and its tests only; callers (`run_headless.sh`, `intake.py` meeting import, `nightshift_deliver.py`) stay as they are.
- Every existing test passes unchanged.
- The gate guards against links already on disk; it cannot assume who made them.

## The rule (decided)

**A path the gate touches must resolve to itself.** For a vault-relative path `rel`, refuse if any component of `rel`, under the resolved vault root, is a symlink (in effect, `os.path.realpath(vault / rel)` must equal `os.path.join(os.path.realpath(vault), rel)`). This refuses a symlink anywhere below the vault root: leaf, folder, dangling, in-tree or escaping. The declared path is then the real path, so every existing lexical check holds as written. `safe_rel` already bans `..` and dot folders in targets. A vault root reached through a symlinked parent still works because the root itself is resolved.

This is the simplest rule that closes every route: one comparison, no allowlist of acceptable links. *Builder's call:* write it as an `os.path.islink` walk over each prefix below the resolved vault root. Realpath equality is shorter, but non-strict `realpath` leaves a symlink loop unresolved and passes it (the rename then fails with `ELOOP` and is held back, so nothing escapes); the walk refuses it outright. One private helper in `publish.py` (for example `_resolves(vault, rel) -> bool`) serves every call site below.

## Where it runs

| Path | Today | Change |
|---|---|---|
| Target, in `_check` | lexical only | early return `Problem(target, "symlink on the target path")` before `_is_file_path`, so no later step reads the old note or hashes through the link |
| Staged files, in `staged_targets` | leaf `is_symlink()` (and `rglob` yields a linked folder as one entry) | replace `path.is_symlink()` with the helper on each yielded path. That also catches a linked `wiki/.staging/` or `wiki/.staging/<run_id>/`. Reason stays "staged path is a symlink" |
| Source in `record_stage` | leaf `is_symlink()` | helper on `vault / target`; raise `PublishError("symlink on the target path: …")`. Closes copying a linked file into model-readable staging for exact targets such as `briefings/<date>.md` |
| Journal file, in `_read_journal` | follows links | raise `ValueError` if the journal path does not resolve to itself, so `recover()` records it as `recovery_failed` ("unreadable journal") |
| Journal entries, in `_apply`, before hashing or `mkdir` | strings only; `vault / "/abs"` and `..` pass | require `safe_rel(target)`, `staged == f"wiki/.staging/{run_id}/{target}"` (what `commit_run` writes), and the helper on both. A hit is a `failed` Problem "publish failed: unsafe journal entry", and nothing for that entry is moved |

The `_apply` check is the one that matters for recovery and for a link that appears between validation and rename. It also stops a second route the audit did not name: `os.replace` on a symlinked *staged* file moves the link itself into `wiki/`, and `recover()` would replay that. *Builder's call:* on an unsafe entry, hold the staged file back with `_hold_back` (as today's `OSError` path does) only when the entry's `staged` is exactly `wiki/.staging/{run_id}/{target}`, `safe_rel(target)` passes and the staged path has no symlink in it; otherwise leave every file in place and only report the entry, so the gate never moves a file it did not stage. After `_apply`, both `commit_run` and `recover()` delete the staging folder with `rmtree`, so anything not held back is lost.

## What a hit does

All of these exist today; the fix adds reasons only.
- Ingest, brief and debrief: `validate_run` problem, then `_quarantine`, then `publish.json` status `rejected`, then `publish_staged.py` exit 5, then `run_headless.sh` rc 5 and its "publish rejected or empty" alert.
- Meeting import: `record_stage` raises `PublishError`, which leaves `_publish_run` (`intake.py:762-770`) before any ledger write and lands in `_meeting_failure`: a "will retry" alert, and the source is quarantined after 3 tries; the next `recover()` quarantines the open staging folder as aborted. Unchanged by this spec.
- Research delivery: `publish_research` returns `False, "publish gate: rejected: …"`.
- `_apply` hit at commit: status `rejected` (like today's `OSError`); at recovery, `recovery_failed`, then the existing "publish recovery failed for run(s)" alert. The journal still reaches `committed`, so a refused entry is never retried. *Builder's call (fail loud, P10):* today a run whose `_apply` returns faults at recovery gets `recovery_failed` in its `publish.json` but is listed in `recovered`, and both alert sites (`intake.py:513-515`, `run_headless.sh:130-132`) read only `failed`, so no alert fires. `recover()` also lists such a run in `failed` (directly, not through `fail()`, which would quarantine it and overwrite the report that `commit_runs.py` reads). This covers today's `OSError` faults too: a recovery that could not apply an entry was silent, and it now alerts. A test pins the list membership.

## Journals written before the fix

No migration. The guard sits in `_apply`, so the fixed `recover()` replays an uncommitted old journal through it and refuses any entry that crosses a link. Committed journals are never replayed.

## Tests (one failing test per route, written first)

House style of `system/tests/python/test_publish.py` and `test_publish_commit.py`: the `run`/`vault` fixtures, `stage_new`, `decide`, `rec`, `reasons`, `LATER`, `os.symlink`, `tmp_path`. Each staged note is otherwise valid (schema, decision, walls), so the test lands the file on today's code. Each runs `commit_run` (or `recover`), asserts the symlink or unsafe-entry reason through `reasons()` (not only a non-empty problem list), and asserts that nothing exists at the link's destination afterwards.
1. Folder `wiki/work/concepts/linked` → `wiki/work/private/`: staged `…/linked/X.md` is rejected.
2. Same folder link → `system/agents/workcells/`: rejected.
3. Same folder link → a `tmp_path` folder outside the vault: rejected.
4. In-tree folder link `wiki/work/notes` → `wiki/work/meetings/` on an ingest run: rejected (the lexical meetings check alone would pass it).
5. Leaf link, dangling and to an existing note: rejected.
6. `wiki/.staging/<RID>` replaced by a link to a `tmp_path` folder holding a valid note: rejected. (`test_staged_symlink_rejected` already covers a linked staged file.)
7. `record_stage` of an exact target whose folder is a link: `PublishError`, nothing copied into staging.
8. A hand-written uncommitted journal whose entry target crosses a linked folder: `recover()` reports `recovery_failed`, nothing at the destination, journal ends `committed`.
9. A journal whose staged entry is a symlink: `recover()` refuses it and the link is not moved into `wiki/`.
10. Journal entries with an absolute target, a `..` target, or a staged path outside `wiki/.staging/<run_id>/`: refused.
11. The journal file itself is a link: `recovery_failed`, "unreadable journal".
12. Regression: a vault reached through a symlinked parent folder publishes a valid note as before.

## What must not change

- Every legit publish (ingest, brief, debrief, meeting import, research delivery) and every existing test passes unchanged.
- Notes Obsidian or the owner create as real files and folders publish as before. The index already skips symlinks (`index.py`), and the only links the template makes are under `.claude/skills/` (`extensions.py`), which no publish targets.
- Cost: a few `stat` calls per staged file; no new walk of the vault.

## Risks

- An owner who links `wiki/`, `briefings/` or a folder under `wiki/<p>/` (for example into a synced folder) gets every run that touches it refused, with "symlink on the target path" in `publish.json` and the existing alert. That is the intended fail-closed outcome. *Builder's call:* one line in FOUNDRY.md where the publish gate is described, saying the gate refuses symlinked paths.
- Check-then-rename race: a link created between the `_apply` check and `os.replace` still lands. That needs a concurrent writer that makes links; the model cannot. Upgrade path if needed: `os.open` each folder with `O_NOFOLLOW` and rename with `dir_fd`.
- Quarantine and hold-back destinations under `system/quarantine/<run_id>/` still follow links. Only the gate writes there; left as a known gap.

## Left to the builder

- The helper's name and form (realpath equality or prefix walk).
- Exact reason strings, kept short and containing "symlink" or "unsafe journal entry" so the tests and `notify.py`'s first-problem line read well.
- The CHANGELOG line, per house style.

**Size:** one PR (`publish.py` plus tests; FOUNDRY.md line optional).
