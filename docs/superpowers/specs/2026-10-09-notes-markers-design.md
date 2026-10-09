# Notes markers: the Notes block goes to the wiki once, after midnight

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #61. The owner chose option A on the issue and approved this scope in the 2026-10-09 grill.

## 1. Problem

The briefing's `## 📝 Notes` section ships empty. To send notes to the wiki, the owner types `#wiki-ingest-start` and `#wiki-ingest-end` by hand. Pre-placing the markers is unsafe today. `Intake._extract_locked` sends a block once the briefing has been unchanged for 60 s, and it treats each new text hash as a new block. With the markers already in place, a sync while the owner is mid-note sends half a note, and every later edit sends another copy.

## 2. Decisions

- The template puts both markers inside `## 📝 Notes`.
- **Every `#wiki-ingest` block inside the Notes section waits for the end of the day.** A block anywhere else in the briefing still goes out as it does now.
- **The end of the day is just after midnight (option A).** On each intake tick after midnight, the daemon sends the Notes-section blocks of every earlier-day briefing still in `briefings/` (not the archive), once per briefing. The 06:00 brief archives the file after that.
- **Known gap, accepted:** notes that reach the server after the 06:00 archive are not sent.

## 3. Changes

### 3.1 The template

`system/templates/daily-briefing.md`, under `## 📝 Notes`, keeps its comment, reworded to say the block is sent once after midnight, and adds:

```
#wiki-ingest-start

#wiki-ingest-end
```

An empty block is skipped, as it already is.

### 3.2 Extraction (`vaultlib/intake.py`)

- `_extract_locked(path)` takes the blocks of today's briefing as now, but skips a block whose start marker sits inside the Notes section: after the `## 📝 Notes` heading and before the next `## ` heading.
- A new step in `extract_briefing()`, under the same `run.lock`: for each `briefings/<date>.md` dated before today in the configured timezone, unchanged for 60 s and with no `{"kind": "notes", "briefing": <rel>}` record in `extracted_blocks.jsonl`:
  - sends each non-empty Notes-section block whose hash is not already recorded as a drop in `raw/inbox/` (the same writer and record format as other blocks);
  - then records `{"kind": "notes", "briefing": <rel>, "time": …}`, so the briefing is never read for Notes again.
- A nested or unterminated block in the Notes section raises the existing once-a-day alert, and nothing in that briefing's Notes is sent until it is fixed.

### 3.3 Wording

The Notes wording in the README (client section), the `/setup` client notes and `CLAUDE.md`'s directory map: notes go between the pre-placed markers in 📝 Notes and reach the wiki once, after midnight. A block written elsewhere in the briefing goes out within a few minutes.

## 4. Tests

- **pytest (`test_intake.py`):**
  - a Notes block edited several times today produces no drop today;
  - after midnight it produces exactly one drop, and later edits produce no more;
  - an empty Notes block produces none;
  - a block outside Notes still goes out right away;
  - a briefing already archived is not read;
  - the hash of a Notes block already sent (for example by today's behavior before the update) is not sent again.
- **bats (`commands.bats`):** the template's Notes section holds both markers, in order. `/brief` still never edits the section.

Bound tools: pytest, bats and the gate.
