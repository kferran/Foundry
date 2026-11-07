# Where yesterday landed: the morning brief links the last debrief

**Date:** 2026-10-15
**Issue:** #179. Owner (2026-10-14): "I'd like to start linking the previous days debrief to the morning briefing so I can see where things landed."

## 1. Problem

The briefing embeds only its own day's debrief (`![[<date>.debrief]]` under 🌌 Evening Debriefing), which is empty at 06:00. Yesterday's debrief sits in yesterday's briefing, and after a weekend in the archive.

## 2. Decisions

- **Prep finds it; the brief summarizes it.** `brief_prep.sh` writes `yesterday.md`: the newest debrief dated before the brief's date and at most 7 days back, searched in `briefings/` and `briefings/archive/*/`. That reaches Friday from Monday and skips days with no debrief. The headless brief reads only prep inputs, so the file carries the debrief's text.
- **`yesterday.md` form.** First line `debrief: [[<date>.debrief]]`, a blank line, then the debrief's body without its frontmatter. With no debrief in the window: one line `none: no debrief found from <date-7> to <date-1>`.
- **The briefing.** A `### Where yesterday landed` section opens 🌅 Morning Alignment, before Active Objectives: the link, then three to five `- ` lines drawn from the debrief (what closed, what it left open, decisions still waiting on the user, anything it flagged: failed runs, alerts, quarantine). Lines Blockers or From Now already print are left out, so an alert or decision shows once. Facts are copied, never re-derived, and no line becomes a Now line. A debrief whose every section says None or Nothing recorded prints the link and `Nothing recorded.` With `none:`, the section prints `No debrief found from <a> to <b>.`; with no `yesterday.md` (an interactive re-run whose prep predates this change), `No debrief input.` An unreadable debrief is an Unavailable Sources line; the prep still exits 0.
- **The link resolves.** `[[<date>.debrief]]` resolves by name in Obsidian and in the index, archived or not.
- **Unchanged.** The day's own debrief stays embedded at the bottom of its briefing.

## 3. Changes

- `system/scripts/brief_prep.sh`: the `yesterday.md` step, before the archive step.
- `system/templates/daily-briefing.md`: the `### Where yesterday landed` heading first under 🌅 Morning Alignment.
- `.claude/commands/brief.md`: the input line and the section rule; an existing briefing without the section gets it before Active Objectives.
- `FOUNDRY.md` Daily use: one sentence.

## 4. Tests

`prep.bats`: the newest debrief in the window wins over an older one, found in the archive, its frontmatter dropped; one 8 days back is out of the window and gives the `none:` line; a debrief dated the brief's own day is ignored. `commands.bats`: `brief.md` names `yesterday.md` and the section rules; the template has the heading before Active Objectives; `FOUNDRY.md` has the sentence. Live acceptance: a real headless brief with a debrief for the day before.

## 5. Out of scope

- Holiday calendars: the 7-day window covers them.
- A summary written by the debrief itself for the next morning.
