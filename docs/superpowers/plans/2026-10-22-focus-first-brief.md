# Focus-first Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The brief opens with at most 5 focus projects per partition and today's objectives drawn from them; open Now lines show as Overdue plus a count; the brief stops adding objectives to the Now page.

**Architecture:** `active_projects.py` caps the list at 5, prints the overflow as one line and flags stale projects from git. The brief's command text and template move 🎯 Active Projects to the top, add `### Today`, replace the From Now Dataview block with a count line, drop New objectives from Add to Now, and label off-focus Work Orders. The Slack brief notice gains two counts.

**Tech Stack:** Python 3 stdlib, git, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-22-focus-first-brief-design.md`

## Global Constraints

- No new note type, schema, config key or exit code. `ActiveProjects.md` keeps its format.
- Template rule: no real names, ticket keys or sites in fixtures or docs. Use `Alpha`, `Beta`, `Blake Sample`.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions. Docs tests check names, not exact wording, except where an existing test already pins a phrase.
- `brief.md` plus every extension's `brief/section.md` stays at or under 2,500 words; each rule added replaces one removed.
- Slack sends no text from `wiki/`: counts only (spec §3.5).
- Core budget: `system/scripts` stays within the `vault_integrity.bats` cap; if it must rise, raise it by the measured amount with the reason in the test's comment.
- Per-task suites: `system/scripts/test.sh system/tests/python/test_active_projects.py`, `system/scripts/test.sh system/tests/python/test_notify.py`, `system/scripts/test.sh system/tests/commands.bats`, `system/scripts/test.sh system/tests/prep.bats`.
- The brief's command text changes, so the PR body lists the live acceptance re-run for `/brief` as owed by the owner after merge.
- CHANGELOG line under `## 2026-10-22` (or the merge date) ending `(#PR)`. FOUNDRY.md's `/brief` row (line 67) and the Slack notices paragraph updated.

## Review Focus

1. **Overflow and caps count honestly.** 7 active entries print 5 blocks and `Also active:` with exactly the other 2; a notice-producing entry (unresolved link) does not consume a slot silently. Task 1.
2. **Stale is measured, never guessed.** A project changed 3 days ago is not stale; one changed 10 days ago is; a linking note changed 2 days ago clears it; a git failure prints no stale line and one notice. Task 2.
3. **The brief no longer writes objectives to Now**, and still writes Work Order "Needs you" lines and extension lines. Task 3's docs tests.
4. **No wiki text reaches Slack.** The notice adds numbers only; a project name in `projects.md` never appears in the message. Task 4.

---

### Task 1: Cap active projects at 5 with an "Also active" line

**Files:**
- Modify: `system/scripts/active_projects.py`
- Test: `system/tests/python/test_active_projects.py`

**Interfaces:**
- `MAX_ACTIVE = 5`. `partition_blocks()` renders the first 5 resolvable entries; the remaining resolvable entries print after the blocks as `Also active: [[X]], [[Y]]`. Entries with a notice (unresolved, ambiguous, other partition, unreadable) keep their notices and take no slot. The `only the first N active projects are shown` notice is removed.

- [ ] Step 1: failing tests: `test_seven_entries_show_five_blocks_and_also_active_names_the_other_two`; `test_an_unresolved_entry_takes_no_slot`; update the test at line 136 that pins the old notice to assert it is gone.
- [ ] Step 2: run them, see them fail. Implement. Run `system/scripts/test.sh system/tests/python/test_active_projects.py`.
- [ ] Step 3: commit.

### Task 2: Stale flag from git

**Files:**
- Modify: `system/scripts/active_projects.py`
- Test: `system/tests/python/test_active_projects.py`, `system/tests/prep.bats` (only if its ActiveProjects fixture needs a git repo)

**Interfaces:**
- `STALE_DAYS = 7`. `changed_since(part, day) -> set[str] | None`: paths from `git log --since=<day - 7> --until=<day> --name-only --format= -- wiki/<part>/`, run from the vault root; None when git fails.
- A block gains `Stale: no change since <day - 7>` after its heading when neither the project page nor any changed note in the partition that links to it (via `vaultlib.links`) is in the set. When `changed_since` returns None, no stale lines print and Notices gains `- <part>: could not read git history; no stale check.`

- [ ] Step 1: failing tests (each in a `tmp_path` git repo with dated commits via `GIT_COMMITTER_DATE`/`GIT_AUTHOR_DATE`): `test_a_page_changed_three_days_ago_is_not_stale`; `test_a_page_changed_ten_days_ago_is_stale`; `test_a_linking_note_changed_recently_clears_stale`; `test_no_git_prints_no_stale_line_and_one_notice`.
- [ ] Step 2: run them, see them fail. Implement. Run `system/scripts/test.sh system/tests/python/test_active_projects.py` and `system/scripts/test.sh system/tests/prep.bats`.
- [ ] Step 3: commit.

### Task 3: Brief command and template

**Files:**
- Modify: `.claude/commands/brief.md`, `system/templates/daily-briefing.md`, `FOUNDRY.md` (the `/brief` row), `CHANGELOG.md`
- Test: `system/tests/commands.bats`

**Interfaces:**
- Template: `## 🎯 Active Projects` (with `### Today` first) moves above `## 🌅 Morning Alignment`. The From Now comment in Active Objectives is replaced by one naming the count line.
- `brief.md`:
  - **🎯 Active Projects:** first `### Today`, 3–5 `- ` lines drawn only from the projects' **Next** items in `projects.md`, each linking its project page; "None." when `projects.md` says None. Then the blocks as today, then any `Also active:` line verbatim, and each `Stale:` line verbatim under its heading.
  - **Active Objectives:** **From Now** and its Dataview block are replaced by `Open Now lines: <n> of <N> not overdue; [[wiki/work/Now]] · [[wiki/personal/Now]]`, n and N counted from `now.md` and `overdue.md`.
  - **Add to Now:** the **New objectives** bullet goes; the Work Order and extension bullets stay.
  - **🛠 Work Orders:** append `(not on focus)` to the Notes cell of a row whose Item names no focus project and no codebase a project block names; list each such call under 🤖 Decided for you.
  - **When an existing briefing** has the old order, move 🎯 Active Projects above 🌅 Morning Alignment once.
- `commands.bats`: replace the From Now test (line 759) with one checking the count line and that `New objectives` is gone; update the template order test (line 85) so Active Projects comes before Morning Alignment; update the Now-clock test (line 790) so Overdue is followed by the count line; add a check for `### Today`, `Also active`, `Stale:` and `(not on focus)`.

- [ ] Step 1: update the bats tests first; run `system/scripts/test.sh system/tests/commands.bats` and see them fail.
- [ ] Step 2: edit `brief.md`, the template, the FOUNDRY.md `/brief` row and CHANGELOG. Check the 2,500-word cap. Run `system/scripts/test.sh system/tests/commands.bats` and `system/scripts/test.sh system/tests/conformance.bats`.
- [ ] Step 3: commit.

### Task 4: Slack brief notice adds focus counts

**Files:**
- Modify: `system/scripts/vaultlib/notify.py` (`_run_event` / `_counts`), `FOUNDRY.md` (Slack notices paragraph)
- Test: `system/tests/python/test_notify.py`

**Interfaces:**
- The brief notice reads `Brief <day>: <f> focus projects (<s> stale), <n> need you, <w> waiting, <a> alerts today <link>`. f counts `### [[` headings and s counts `Stale:` lines in `system/logs/inputs/<day>/projects.md`; when the file is missing, the focus part is left out. No text from `projects.md` is copied.

- [ ] Step 1: failing tests: `test_brief_notice_counts_focus_and_stale`; `test_brief_notice_without_projects_input_leaves_focus_out`; `test_brief_notice_never_carries_a_project_name` (fixture project `Alpha`; assert `Alpha` not in the message).
- [ ] Step 2: run them, see them fail. Implement. Run `system/scripts/test.sh system/tests/python/test_notify.py` and `system/scripts/test.sh system/tests/notify.bats`.
- [ ] Step 3: commit.
