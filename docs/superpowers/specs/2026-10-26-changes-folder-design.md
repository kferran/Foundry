# One file per change: `changes/` replaces the root CHANGELOG.md

**Date:** 2026-10-26
**Status:** draft, for the owner's review
**Grill:** 2026-10-26, two rounds and a revised Q10, every recommendation taken, recorded on https://github.com/kferran/Foundry/issues/395
**Builder check:** 2026-10-26, three questions and eight missed consumers, all settled as my calls: the line's number is the issue's from the first commit (§3.1); the frozen history keeps the name `CHANGELOG.md` inside `changes/`, so the `[[CHANGELOG]]` link in every past brief still resolves (§3.2, a change to the grill's `HISTORY.md`); a checksum freezes it, which also catches a stale branch's CHANGELOG edit that git's rename detection carries into it (§3.2); this PR updates the open plans that still say "CHANGELOG line" (§3.4); the vendor scan skips only the frozen history (§3.4).
**Blueprint:** none: a file layout and the update step that reads it; no new feature shape.
**Lane:** feature, one pull request with a short plan. No safety surface: `update_template.sh` is the update path, not the publish gate, and no settings, sandbox, redaction or hook changes.

## 1. Why

Every pull request that a vault user would notice adds a line to `CHANGELOG.md` under today's date. Two open PRs that both add a line conflict on GitHub as soon as one merges: the `merge=union` driver in `.gitattributes` runs only in a local git. Each conflict costs a merge of master, a push and a CI run, and it recurs on every merge (defect class `C13-changelog`). On 2026-10-26 it hit #393 twice in one hour.

## 2. Goals, non-goals, anti-goals

- **Goals:** no two pull requests edit the same file to record their change; a vault's brief shows **What changed** exactly as it does today.
- **Non-goals:** a compiled or rolled-up changelog; generating notes from PR bodies, commit trailers or GitHub; a bot that writes to master.
- **Anti-goals:** any network or GitHub access during a vault's update; a vault's brief flooded with old history; lint warnings in every past brief.

## 3. Design

### 3.1 The change file

A pull request that changes something a vault user would notice adds one file, `changes/<YYYY-MM-DD>-<slug>.md`. The date is the day the file is written; the slug is the branch name with `/` turned into `-` (for example `changes/2026-10-26-feat-changes-folder.md`), or any slug no other file uses. The file holds today's line format and nothing else:

```
- Changed: <what changed, in plain words> (#<n>)
  - Action: <what a vault runs>
```

One or more `- ` lines, each ending with `(#<n>)`, each optionally followed by one indented `  - Action: ` line. `<n>` is the issue the work is part of, written in the first commit, so the branch's first push passes CI (CI runs on every push, before a PR exists); the PR number may replace it once the PR is open. Docs, test and CI changes add no file. A Work Order's plan adds the file in its last task.

### 3.2 History

`CHANGELOG.md` moves to `changes/CHANGELOG.md` with `git mv` and is frozen: nothing adds to it again. It keeps its name so the `[[CHANGELOG]]` link in every past brief's What changed still resolves by name (the index resolves links against every walked file; `changes/` is left out of `NAME_EXCLUDED`). Its `## What's next` section is dropped in the move: both of its items (#310, #331) have shipped, and plans live in `docs/superpowers/roadmap.md`. A test pins its SHA-256: an edit, including one that a branch cut before the move carries in through git's rename detection, fails the gate. The `CHANGELOG.md merge=union` line and its comment leave `.gitattributes`.

### 3.3 The update reads the folder

`update_template.sh`'s `changelog_added` becomes `changes_added`: when `HEAD^1` has a `changes/` folder, it prints, in file-name order, the `- ` and `  - Action: ` lines of each `changes/*.md` file the merge added (`git diff --name-only --diff-filter=A HEAD^1 HEAD -- changes/`), skipping `changes/CHANGELOG.md`. When `HEAD^1` has no `changes/` folder, it prints nothing, so a vault's first update never floods the brief. Everything after it (appending to today's `updates.md`, the alert's "notes in today's brief") is unchanged.

**Switch day (owner, Q10 revised):** `update_template.sh` does not re-run itself after its merge, so the update that brings this change runs the old step. The old step sees the root `CHANGELOG.md` deleted, prints nothing, and that morning's What changed is empty in each vault: this PR's line and the line of every change file merged in the same update are missing from the brief. Nothing in this change needs an `Action:`, and the lines stay readable in `changes/`. From the next update on, the new step runs. The PR body says so.

### 3.4 What else changes with it

- **The brief** (`.claude/commands/brief.md`, What changed, and its line 38 mention): the closing line becomes `Full list: [changes/](changes/)`. A Markdown link to a folder resolves (`links.py`).
- **FOUNDRY.md:** the Release notes rule names the change file, its path and format (§3.1). The C13 row of the gate table names the new gates (the format test and the history checksum) in place of the union driver and the date test; the defect-class list and the update section (around lines 97, 468 and 486) say "change files" for "the changelog lines" and "CHANGELOG conflicts". Defect class `C13-changelog` keeps its label.
- **The index** (`vaultlib/index.py`): `changes/` joins `NOT_INDEXED` (never a note), not `NAME_EXCLUDED`; `CHANGELOG.md` leaves `ROOT_DOCS`.
- **`/new-source`** (`new_source.py`, its SKILL.md): in the template it writes `changes/<date>-source-<name>.md` with its `- Added: <description>. (#<issue>)` line, in place of editing CHANGELOG.md.
- **`foundry-review`** (`review_diff.py` `changelog_label`, its SKILL.md table row): a vault-visible path changed with no added `changes/*.md` file holding a `- … (#N)` line is the finding.
- **The console extension's manifest:** "the CHANGELOG line says so" becomes "its change file says so".
- **Open plans:** `docs/superpowers/plans/2026-10-24-console-today.md`'s unchecked steps that add a CHANGELOG line add a change file. Branches open when this merges convert their own line when they next merge master (the freeze test fails them until they do).
- **The vendor scan** (`vault_integrity.bats`, "core names no vendor or customer"): it skips `changes/CHANGELOG.md` where it skipped `CHANGELOG.md`; new change files are scanned.

### 3.5 Tests

- `commands.bats`: the CHANGELOG format test and the duplicate-date test go. In their place: every `changes/*.md` but `changes/CHANGELOG.md` holds only `- … (#n)` lines and `  - Action: ` lines, and a seeded bad file is found; `changes/CHANGELOG.md`'s SHA-256 is the pinned one. The release-notes test (brief's Full list line, FOUNDRY.md's rule sentence) follows §3.4, and the stale union-merge comment goes.
- `vault_integrity.bats`: "CHANGELOG.md merges with the union driver" goes; the vendor scan follows §3.4.
- `remote.bats`: the release-notes update tests write change files: a merge that adds two files appends both files' lines in name order; a later merge the same day appends only its own; an edit to `changes/CHANGELOG.md` prints nothing; a vault whose `HEAD^1` has no `changes/` prints nothing.
- `test_index_rules.py`: a past brief linking `[[CHANGELOG]]` has no dead-link warning when the file is `changes/CHANGELOG.md`; `CHANGELOG.md` at the root is a root note.
- `test_links.py`, `test_new_source.py` and `test_foundry_review.py` follow §3.4.

## 4. Done when

- The root has no `CHANGELOG.md`, `changes/CHANGELOG.md` holds its history, and this PR's own line is in `changes/2026-10-26-feat-changes-folder.md`.
- The gate is green, and two branches that each add a change file merge into master in either order with no conflict.

## 5. Left to the builder

The exact awk or loop in `changes_added`, the test names, and the wording of the FOUNDRY.md rule within §3.1.
