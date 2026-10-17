# One-screen Brief and Lean Now Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The morning brief fits in 8 KB, the work Now page in 25 KB, and the headless brief prompt in 2,500 words (gap plan phase A).

**Architecture:** The prep scripts cap what they write (Active Projects, Waiting on, handoffs, Blockers inputs), so the model only sees capped input. `vaultlib/now.py` moves closed lines to a monthly archive note at each brief prep, keeps line history as dated notes under a line, and refuses lines over 300 characters. Size tests on a fixture vault at the live vault's size hold the targets.

**Tech Stack:** bash, Python 3 stdlib, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-17-one-screen-brief-lean-now-design.md`

## Global Constraints

- Item cut: 160 characters at a word boundary, ending `…`. One helper, `vaultlib/briefings.py` `cut(text, limit=160) -> str`, used by every prep script in this plan.
- Line cap: an open Now line written in full (statement, fields, parenthesis) is at most `MAX_LINE = 300` characters. Recall's `LONG_LINE = 240` cut stays.
- Notes under a line: `  - YYYY-MM-DD: <text>` (two spaces). Only lines starting `- [ ] ` count as open lines; no reader changes.
- Archive note: `wiki/<partition>/now-archive/YYYY-MM.md` from `system/templates/now_archive.md`, frontmatter `type: concept`, `tags: [now-archive]`, `compiled_at`, `partition`. No new schema: core stays at 14.
- Every Now page write stays under run.lock, as today.
- Core budget: `vault_integrity.bats` holds core scripts at 13,200 lines, and they are at 13,200 today. Remove `KEEP_DAYS` pruning and trim comment-only lines where they repeat the spec; raise the budget in Task 9 by the measured amount, with the reason in the test's comment.
- Template rule: no real names, ticket keys or sites in fixtures or docs. Use `Blake Sample`, `ABC-123`, `example.atlassian.net`.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- Words: `brief.md` plus every extension's `brief/section.md` at most 2,500 words. Each rule this plan adds to `brief.md` replaces one it removes.
- CHANGELOG line under `## 2026-10-17` (or the merge date) ending `(#PR)`.

## Review Focus

1. **Archiving loses nothing.** A closed line and its notes appear once in the archive and leave the page; an open line and its notes stay. Covered by Task 4's round-trip test and the run.lock test.
2. **A note never becomes an open line**, and a line's notes move with it through `set`, `archive` and evidence closing. Covered by Task 5.
3. **Caps keep counts honest.** Every "and N more" line names the true remainder. Covered by the count assertions in Tasks 1 to 3.
4. **The 300 cap fails closed** in `add`, `set` and the publish gate, and never breaks the 37 existing long lines on read. Covered by Task 5 and Task 6.
5. **Issue evidence closes only on a closed issue**, and a `gh` failure counts as a check failure, as for pull requests. Covered by Task 7.

---

### Task 1: Active Projects caps decisions and cuts items

**Files:**
- Modify: `system/scripts/active_projects.py`, `system/scripts/vaultlib/briefings.py`
- Test: `system/tests/python/test_active_projects.py`, `system/tests/python/test_briefings.py`

**Interfaces:**
- Produces: `briefings.cut(text: str, limit: int = 160) -> str`; `active_projects.MAX_DECISIONS = 3`.
- `project_block()` prints at most `MAX_NEXT` next actions and `MAX_DECISIONS` decisions, each through `cut()`, then `- and N more decisions on the page` when decisions remain. Next actions over the cap keep today's line.

- [ ] Step 1: failing tests: `test_cut_stops_at_a_word_and_marks_the_cut` (159-, 160- and 400-character inputs; a single 200-character word cuts mid-word); `test_decisions_cap_at_three_and_count_the_rest` (6 decisions: 3 printed, `and 3 more decisions`); `test_long_items_are_cut` (a 400-character next action prints at most 161 characters).
- [ ] Step 2: run them, see them fail. Implement. Run `pytest system/tests/python/test_active_projects.py system/tests/python/test_briefings.py`.
- [ ] Step 3: commit.

### Task 2: Waiting on lists 5 owners, Yours cuts items, notices since the last brief

**Files:**
- Modify: `system/scripts/meeting_actions.py`
- Test: `system/tests/python/test_meeting_actions.py`

**Interfaces:**
- `MAX_OWNERS = 5`. `waiting` keeps the owners with the most items first, ties by `str.casefold` name, then `and N more people (M actions)`.
- `mine` lines put `text` through `briefings.cut()`.
- `notices(day)` takes records since `window_start(VAULT, day)` instead of `NOTICE_DAYS`, so a notice prints in one brief only. `NOTICE_DAYS` goes.

- [ ] Step 1: failing tests: `test_waiting_on_lists_five_owners_then_a_count` (7 owners with 1 to 7 items: the 5 largest print; the count line says `2 more people (3 actions)`); `test_owner_ties_sort_by_name`; `test_yours_cuts_long_items`; `test_notices_print_once` (a record before the previous brief's window does not print).
- [ ] Step 2: implement. Run `pytest system/tests/python/test_meeting_actions.py` and `bats system/tests/prep.bats`.
- [ ] Step 3: commit.

### Task 3: Handoffs to chase caps the list

**Files:**
- Modify: `extensions/handoffs/scripts/jira_handoffs.py`
- Test: `extensions/handoffs/tests/python/test_handoffs_jira.py`

**Interfaces:**
- `MAX_LISTED = 10`, `OLD_DAYS = 90`. `extract(stream, cfg, today: str)` sorts tickets by `statuscategorychangedate` (oldest first), lists at most 10 unchanged for `OLD_DAYS` days or less, then `- and N more`, then one line `- N handoffs unchanged for more than 90 days (oldest: KEY, since DATE)` when any are older. The ticket line keeps today's shape with the summary through `cut()`.
- `main` passes today's date (`--date`, default today in the vault's zone); `brief/prep.sh` passes `$PREP_DATE`.

- [ ] Step 1: failing tests: 25 tickets (8 old, 17 recent) give 10 listed, `and 7 more`, and `8 handoffs unchanged for more than 90 days (oldest: ABC-1, since 2025-03-02)`; a ticket exactly 90 days old is recent; every existing fail-closed test still passes.
- [ ] Step 2: implement. Run the handoffs pytest and `bats extensions/handoffs/tests/handoffs.bats`.
- [ ] Step 3: commit.

### Task 4: `now.py archive` and the monthly archive note

**Files:**
- Create: `system/templates/now_archive.md`
- Modify: `system/scripts/vaultlib/now.py`, `system/scripts/now.py`, `system/scripts/brief_prep.sh`, `system/scripts/vaultlib/index.py` (orphan lint skips `now-archive/`)
- Test: `system/tests/python/test_now.py`, `system/tests/prep.bats`, `system/tests/python/test_index_rules.py`

**Interfaces:**
- `vaultlib.now.blocks(text) -> list[tuple[str, list[str]]]`: each line with the note lines directly under it.
- `vaultlib.now.archive(vault, partition, today) -> int`: under run.lock, stamps unstamped closed lines (as `stamp_and_prune` does), moves every closed line and its notes to the month's archive note (made from the template when missing), appending in page order; returns the count moved. Writes the archive before the page, so a crash between them repeats a line in the archive and loses none; a line already in the archive is not written twice.
- `stamp_and_prune` becomes `stamp(text, today)`: stamps and clears stamps, drops nothing. `KEEP_DAYS` goes.
- CLI: `now.py archive --partition <p> --date <day>` prints `archived N`.
- `brief_prep.sh`: `now.py archive` for both partitions after `seed`, before `list`; a failure is `prep_unavailable`, and `list` still runs.

- [ ] Step 1: failing tests: `test_archive_moves_closed_lines_with_their_notes`; `test_archive_keeps_open_lines_and_their_notes`; `test_archive_appends_to_the_month_note_and_skips_repeats` (run twice: one copy); `test_archive_month_follows_the_stamp_date`; `test_stamp_drops_nothing`; prep.bats `brief prep archives closed lines before listing`; index rule `now-archive notes are not orphans`.
- [ ] Step 2: implement. Run `pytest system/tests/python/test_now.py system/tests/python/test_index_rules.py`, `bats system/tests/prep.bats system/tests/commands.bats`.
- [ ] Step 3: commit.

### Task 5: `now.py note` and the 300-character cap

**Files:**
- Modify: `system/scripts/vaultlib/now.py`, `system/scripts/now.py`, `.claude/skills/` and `system/agents/foreman.md` text that tells writers to append updates to a line
- Test: `system/tests/python/test_now.py`

**Interfaces:**
- `MAX_LINE = 300`. `validate()` takes the rendered line and raises `ValueError("the line is N characters; the limit is 300: move history to now.py note")` above it. `add` and `set_statement` call it on the line they would write. A repeat `add` of an existing long line ("exists") still succeeds.
- `note(vault, partition, match, text, today) -> str`: under run.lock, appends `  - <today>: <text>` after the last note of the one open line whose statement contains `match`; same match errors as `set_statement`; `text` is one line without `[rec::`/`[due::`.
- `set_statement` and `check`'s closing keep a line's notes under it.
- `review` gains a `long` group: open lines over `MAX_LINE`.
- CLI: `now.py note --partition <p> --match <text> --text <update>`.

- [ ] Step 1: failing tests: `test_add_and_set_refuse_a_line_over_300`; `test_note_lands_under_the_one_matching_line`; `test_notes_follow_set_and_check`; `test_a_note_is_never_an_open_line` (`open_lines`, recall and `overdue` ignore it); `test_review_lists_long_lines`.
- [ ] Step 2: implement. Replace "append" wording in CLAUDE.md's **Now** rule and the Foreman persona with `now.py note`. Run `pytest system/tests/python/test_now.py system/tests/python/test_recall.py`.
- [ ] Step 3: commit.

### Task 6: The publish gate refuses a new long Now line

**Files:**
- Modify: `system/scripts/vaultlib/publish.py`
- Test: `system/tests/python/test_publish.py`

**Interfaces:**
- In `_check`, for a `NOW_PAGE` target: compare the staged page's open lines with the live page's; an open line that is new or changed and longer than `now.MAX_LINE` gives `Problem(target, "a Now line over 300 characters: move history to a note under it")`. Unchanged long lines pass.

- [ ] Step 1: failing tests: a staged brief run adding a 301-character line is refused; one keeping an existing 400-character line unchanged passes; a 300-character line passes.
- [ ] Step 2: implement. Run `pytest system/tests/python/test_publish.py system/tests/python/test_publish_commit.py`.
- [ ] Step 3: commit.

### Task 7: A GitHub issue URL is evidence

**Files:**
- Modify: `system/scripts/vaultlib/now.py`
- Test: `system/tests/python/test_now.py`

**Interfaces:**
- `ISSUE_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/\d+$")`. `evidence_state` runs `gh issue view <url> --json state,stateReason` with `GH_TIMEOUT`: `CLOSED` gives `"issue closed"` (or `"issue closed as not planned"`), `OPEN` gives None, anything else `CheckFailed`.
- CLAUDE.md's **Now** rule lists the issue URL among evidence kinds.

- [ ] Step 1: failing tests with the stub `gh` the PR tests use: closed issue closes the line; open issue leaves it; a `gh` error counts toward `FAILURE_ALERT`.
- [ ] Step 2: implement. Run `pytest system/tests/python/test_now.py system/tests/python/test_intake.py`.
- [ ] Step 3: commit.

### Task 8: Blockers trims and the prompt under 2,500 words

**Files:**
- Modify: `.claude/commands/brief.md`, `system/scripts/brief_prep.sh` (pipeline alerts input), `extensions/telemetry/brief/section.md`, `extensions/handoffs/brief/section.md`
- Test: `system/tests/prep.bats`, the telemetry and handoffs `docs.bats`/`extension.bats`

**Interfaces:**
- Today the brief reads `system/logs/alerts_<date>.md` and the previous day's file directly. Prep writes `alerts.md` instead: every alert line except `[triage]` ones, which become one line, `[triage] N new (on the Now page)`. `brief.md` reads `alerts.md` and prints the triage line as is.
- Telemetry Recurring: one line per environment with groups; environments with none are left out (prep output, then the section text).
- `brief.md`: cut rules the capped prep now enforces (per-section length advice, repeat-avoidance the caps make moot) and merge overlapping Blockers rules, until the word test in Task 9 passes. Record in the PR body each rule removed and why.

- [ ] Step 1: failing tests for the triage line and the telemetry environments.
- [ ] Step 2: implement and cut text. Run `bats system/tests/prep.bats system/tests/headless.bats` and both extension suites.
- [ ] Step 3: commit.

### Task 9: Size tests and the core budget

**Files:**
- Create: `system/tests/fixtures/brief_size/` (fixture vault parts), `system/tests/brief_size.bats`
- Modify: `system/tests/vault_integrity.bats` (budget), `CHANGELOG.md`

**Interfaces:**
- Fixture: 8 projects with 6 decisions and 5 next actions each, 25 handoffs (8 older than 90 days), 12 waiting owners, a work Now page with 95 open lines (none over 300) and 200 closed lines with notes.
- Tests: `brief prep input stays under 8 KB` (sum of the prep files the brief reads; on failure it prints bytes per file); `the brief prompt stays under 2,500 words`; `the Now page is under 25 KB after archive`.
- Budget: measure `git ls-files -z system/scripts | xargs -0 cat | wc -l` and set the limit to that count, with a comment line naming this PR and the reason.

- [ ] Step 1: write the tests and fixture; run `bats system/tests/brief_size.bats`. Fix any cap the fixture shows over target in the task that owns it.
- [ ] Step 2: run the full suites: `bats system/tests/` and `pytest system/tests/python extensions/*/tests/python`.
- [ ] Step 3: commit.

### Task 10: Split the existing long lines (interactive, owner present)

Not a Work Order step: it runs in a Foreman session with the owner, after Tasks 1 to 9 merge.

- [ ] `now.py review --partition work` lists the `long` group (37 lines on 2026-10-17).
- [ ] For each: `now.py set` with the current statement, then `now.py note` for each dated update, oldest first.
- [ ] The owner reads `git diff wiki/work/Now.md` before the sync commit.

### Task 11: Live acceptance

- [ ] The next brief after merge: Active Projects, Waiting on and Handoffs show their caps and counts; the brief is under 8 KB (`wc -c briefings/<date>.md`).
- [ ] The work Now page after one archive is under 25 KB; `wiki/work/now-archive/<YYYY-MM>.md` holds the closed lines.
- [ ] The From Now block in Obsidian: check whether Dataview shows notes as children of a line, and record the result in the spec's §3.5.
- [ ] Five weekdays in a row under the targets closes phase A in the gap plan.
