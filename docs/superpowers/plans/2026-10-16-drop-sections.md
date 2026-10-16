# Drop Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A meeting note first imported from a dropped transcript gets its empty sections filled when the Gemini Doc for the same meeting arrives later (#215), and a note with no summary says `No summary from the source.` so it does not read like an empty meeting.

**Architecture:** `vaultlib/meetings.py` renders the new Summary wording, owns `EMPTY_SECTION` (moved from `intake.py`, extended to the new wording) and gains `fill_sections(note_text, m)`, a text-level merge that fills only blank `## ` sections. `vaultlib/intake.py` `_import_meeting` tries the fill where it would otherwise archive a later source as a duplicate (after the #142 retire test), publishes the merged note through the same snapshot, `record_stage` and `commit_run` steps the retire path uses, and then archives the Doc with the fetch log's `skipped` line.

**Tech Stack:** Python, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-meetings-design.md` §2.3 steps 1 and 5, issues #215 and #216.

## Global Constraints

- Work on branch `fix/drop-sections` in worktree `.scratch/drop-sections`. Do not push or open a pull request.
- Run suites through `system/scripts/test.sh <suite | pytest path>`, outside a sandbox. Never run the gate.
- Template rule: synthetic meeting titles and people only (the existing `NOTES` and `long_cues` fixtures).
- The meeting input (`render_input`) keeps `None.`: `/ingest` step 10 and `commands.bats` read that wording to know a drop has no notes.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- A section that holds text is never overwritten; the fill runs only when Summary, Decisions and Action items are all blank (the #188 guard holds).
- The #142 retire path still runs first: an empty drop note with a short transcript is retired for the Doc, not filled.
- The fill stays inside one partition, leaves the note's frontmatter (`source`, `transcript`, `status`, `provenance`) untouched, and records the Doc ID as skipped so the fetch does not read it again.

---

### Task 1: `No summary from the source.`

**Files:**
- Modify: `system/scripts/vaultlib/meetings.py`, `system/scripts/vaultlib/intake.py`, `FOUNDRY.md`, the meetings spec, `system/schemas/meeting.md`
- Test: `system/tests/python/test_meetings.py` (`test_empty_sections_say_none`)

- [ ] **Step 1: Change the test:** a note rendered from an `.srt` drop reads `## Summary\nNo summary from the source.` and `None.` under Decisions, Action items and Details.
- [ ] **Step 2: Run it red.** `system/scripts/test.sh system/tests/python/test_meetings.py -k summary_from_the_source`.
- [ ] **Step 3: Implement:** `NO_SUMMARY` in `render_meeting`; `EMPTY_SECTION` moves to `meetings.py` and matches the new wording, so `_empty` (#142) still treats such a note as empty.
- [ ] **Step 4: Run green**, then the whole file.
- [ ] **Step 5: Commit** `fix(meetings): a note with no summary says so (#215)`.

### Task 2: fill a drop note's empty sections from a later Gemini Doc

**Files:**
- Modify: `system/scripts/vaultlib/meetings.py` (`fill_sections`), `system/scripts/vaultlib/intake.py` (`_import_meeting`, `_publish_meeting`, `_archive_duplicate`), spec §2.3 step 5, `system/schemas/meeting.md`, `FOUNDRY.md`
- Test: `system/tests/python/test_meetings.py`, beside the #188 tests

**Interfaces:**
- `meetings.fill_sections(note_text, m) -> str | None`: the note with each blank section filled from `m`, or `None` when Summary, Decisions or Action items hold text or `m` has nothing for a blank section.

- [ ] **Step 1: Write the tests:** (a) a drop with 30 cues, `aged`, then the Doc: one new meeting run publishes only the drop note; Summary, Decisions and Action items come from the Doc; `source` and `transcript` are unchanged; the Doc is in `raw/archive/` and the fetch log has it as skipped; no `-2` note. This replaces `test_first_source_wins_a_doc_after_a_drop_is_archived_and_skipped_by_the_fetch`, whose behaviour changes. (b) the same with a Summary typed into the drop note: the Doc is archived, the note is unchanged.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement** as in Architecture.
- [ ] **Step 4: Run green**, then `test_meetings.py`, `test_meeting_actions.py`, `test_meeting_prep.py`, `meetings.bats`, `commands.bats`.
- [ ] **Step 5: Commit** `fix(meetings): a later Gemini Doc fills a drop note's empty sections (#215)`.

### Not built: the twin link (#216)

Linking a later drop's transcript from a populated note needs a second transcript per meeting (`transcript` is one required link and the transcript file is named after its note), a two-target publish of a new transcript plus a note edit, and a dedup by the drop's sha so a re-drop does not link twice. That is more than a small change; it stays on #216.
