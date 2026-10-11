# The brief fits one screen

**Date:** 2026-10-11
**Status:** Draft for the owner's review. Scope settled in a grill with the owner on 2026-10-11; the decisions below are the owner's unless marked "my call".
**Lineage:** `2026-10-09-now-page-design.md` (#102: the Now page replaced the carried-forward list), `2026-10-07-active-projects-design.md`, `2026-10-05-meetings-design.md` §2.5 (meeting actions in the brief), `2026-10-03-calendar-connector-design.md` (calendar.tsv), `2026-10-05-error-monitoring-design.md` (the telemetry tables). Findings: the live-vault review of 2026-10-11 (PorchOS `docs/reviews/2026-10-11-vault-review.md`, §2.4 and §3.1).

## 1. Intent

The weekday brief is a dispatch list. The owner reads it at a desk in Obsidian and turns it into queued work: Work Orders for carried items and research, sessions for projects. A section earns its place only when it changes what gets queued that morning. In the live vault the brief grew from 3.6 KB to 55 KB in five days (about 8,000 words), mostly from sections that never changed a decision: closed carried items printed in full (fixed by #102), two weeks of everyone's action items, 118 friction note names, repeated telemetry rows, and daily lines for sources the server never has.

What the owner used on a weekday: the carried items, Active Projects and the telemetry New tables ("which of these gets an RCA"). What the owner skipped: Waiting on and friction. On review, both stay, in a form that can be read and queued from.

## 2. Goals, non-goals, anti-goals

**Goals.** A weekday brief the owner reads top to bottom and queues from. Everything that decides something is on the page; everything else is a count with a link.

**Non-goals.** Automating the fixes for friction notes (the system queuing a research Work Order per friction note) is its own project, grilled next. Reading mail and chat (#98 phase 2, the intraday brief) is separate. Nothing in the sections the owner ticks (From Now) changes.

**Anti-goals.** A brief that hides a new production error group, a new friction note or yesterday's action items to stay short. Short comes from printing each thing once and counting the rest, never from dropping new information.

## 3. Decisions

### 3.1 Order of the brief (owner)

1. **Fixed commitments** (calendar), as today.
2. **Before today's meetings** (new, §3.6).
3. **From Now**: the Dataview block over the Now pages, as #102 shipped it.
4. **Your meeting actions** (owner's own open actions, as today).
5. **🎯 Active Projects**, as today.
6. **Telemetry**: New tables, then one Recurring line and a Resolved count per environment (§3.4).
7. **Friction**: new since the last brief, plus a count (§3.3).
8. **Waiting on**: yesterday's meetings only (§3.2).
9. **🧾 Handoffs to chase** and **🛠 Work Orders**, as today (my call: neither was discussed; both are already short and rebuilt daily).
10. **Unavailable Sources**, only for sources this role runs (§3.5).
11. **📝 Notes** and the debrief embed, as today.

The Friction Matrix heading goes: its bullets become four parts under one `## 🛑 Blockers` heading, in this order: **Telemetry**, **Friction**, **Pipeline** (pipeline alerts, quarantined inputs, the Notices from `actions.md` and `projects.md`, and a FAILED Work Orders health line, each as today), **Communication Debt** (one line until #98 phase 2). The Pipeline part is my call, from the reviewer's fourth question: those lines are the only place a broken night shows up, so they keep their place.

### 3.2 Waiting on: yesterday's meetings, printed once (owner)

- `meeting_actions.py` lists under **Waiting on** the open action items of other people from the meeting notes **imported since the previous weekday brief**: the `imported` records in `system/logs/meetings-<YYYY-MM>.jsonl` whose time is after the previous Monday-to-Friday briefing's run (the newest weekday `briefings/<date>.md` or archived briefing before today, at that day's `brief_time`; with no earlier briefing, the last 7 days). Import time, not meeting date, so a Friday 17:30 meeting imported Monday morning still prints on Tuesday (my call, from the reviewer's second question).
- The owner does not read weekend briefs. A Saturday or Sunday brief prints no Waiting on, and Monday's covers everything imported since Friday's brief. On a Tuesday that is Monday's meetings.
- An item prints once and lives on the meeting note after that. There is no rolling window and no cap.
- **Yours** (the owner's own open actions) keeps its current rule: every open item, any age, with days open.
- Grouping stays by owner, as today. My call: within one brief, an owner written as a bare first name ("Gavin") joins the group of the owner whose full name starts with it ("Gavin Monson") when exactly one such owner appears in that brief; otherwise it stays as written. No entity lookup.

### 3.3 Friction: new since the last brief, plus a count (owner)

- `brief_prep.sh` writes `system/logs/inputs/<date>/friction.md`: the active concept notes with `is_friction` true that no earlier brief has listed, one `- [[Name]]` per line, newest `compiled_at` first, and a final line `N open friction notes` counting every active one.
- "Listed before" is read from the briefings themselves, never from a ledger (my call, from the reviewer's fifth question: `system/logs/` is per machine, briefings sync): a note was listed when its `[[Name]]` link appears under the Friction heading, or under the old "Friction notes" bullet, of any briefing in `briefings/` or `briefings/archive/`. The first brief after the update therefore prints only the notes flagged since the last old-style brief, and the 118-name backlog is already "listed". A note that loses the flag and gains it again prints again only if no briefing named it in the meantime, which is the right reading of "new".
- `/brief` prints the lines verbatim under **Friction**, then the count. Note names only: the owner opens the note to queue from it.

### 3.4 Telemetry: New in full, Recurring as a line (owner for New; my call for the rest)

Per environment, in the source's `rank` order:
- **New**: the table as today (at most 10 rows, then "and N more").
- **Recurring**: one line, `Recurring: N groups`, followed by the three largest by `count` as `service exception (count)`.
- **Resolved**: the count, as today.

### 3.5 A source that is off by role is not unavailable (my call)

- `brief_prep.sh` and `debrief_prep.sh` run the focus step only when `machine_role` is `standalone`; on a server or client they write no `focus*.md` and no focus line in `unavailable.md`.
- `/brief` omits the Focus Drift line, and `/debrief` omits the Focus paragraph, when the focus input file does not exist.
- `/debrief` prints **3. Agent Health** only when `system/logs/metrics/` holds a file; otherwise the section is omitted.
- The "Mail and chat skipped" line stays until #98 phase 2.

### 3.6 Before today's meetings (owner: add it, keep it short)

A new deterministic prep step, `meeting_prep.py`, writes `system/logs/inputs/<date>/people.md`:

- For each calendar event in `calendar.tsv`, in start order, find the entity notes (every active note under `wiki/<p>/entities/`, `<p>` the default partition and `shared`; there is no person field, so a partner or a system matches as a person does, my call from the reviewer's third question) whose title or an `aliases` entry occurs in the event title as whole words, case-folded. An event with no match contributes nothing; an entity appears once even when in several events.
- For each matched entity, at most **five lines**, in this order and stopping at five:
  1. the entity link and the event time;
  2. open Now lines of the partition whose `who` is that entity or whose statement names it (`owed` lines first, then `waiting`, then `draft`);
  3. for a person, their open action items from meeting notes, any age, newest first.
- At most five entities. A day with no match writes an empty file, and `/brief` prints nothing.
- `/brief` prints the file verbatim as **Before today's meetings**, after the fixed commitments.
- No model reads entity notes for this; the script reads titles and aliases through the index and the Now page through `vaultlib.now`.

### 3.7 Size (my call)

On a weekday with ten meetings, the brief above the 📝 Notes section is under 8 KB. The debrief's size is unchanged by this spec.

## 4. Changes

- `system/scripts/meeting_actions.py`: the Waiting on window by import time (§3.2), the previous-weekday-briefing lookup (shared with `now.py seed`, moved to `vaultlib`), the first-name merge within a brief.
- `system/scripts/vaultlib/friction.py` (new) and the `brief_prep.sh` step that writes `friction.md` from the index and the earlier briefings (§3.3). No ledger and no lock: it reads tracked files and writes only under `system/logs/inputs/`.
- `system/scripts/meeting_prep.py` and `system/scripts/vaultlib/meeting_prep.py` (new): `people.md` (§3.6).
- `system/scripts/brief_prep.sh`, `debrief_prep.sh`: the role-aware focus step; the two new prep files.
- `.claude/commands/brief.md`: the section order; the Before today's meetings block; Friction and Recurring as the prep files give them; the Blockers heading; Focus Drift conditional.
- `.claude/commands/debrief.md`: Focus and Agent Health conditional.
- `system/templates/daily-briefing.md`: the Blockers heading in place of the Friction Matrix.
- `FOUNDRY.md`, `CLAUDE.md` (directory map, if it names the matrix): the new sections and the two prep files.

## 5. Tests

- **pytest (`test_meeting_actions.py`):** a Tuesday brief lists the items imported after Monday's brief and not those imported before it; a Friday meeting imported Monday 08:00 prints on Tuesday; a Monday brief lists everything imported since Friday's brief; a Saturday brief lists none; with no earlier briefing the window is 7 days; Yours still lists an item 20 days old; "Gavin" and "Gavin Monson" in one brief are one group; two full names starting with "Gavin" leave the bare name as written.
- **pytest (`test_friction.py`, new):** a flagged note prints once and is counted after; a note named under the old "Friction notes" bullet of an archived briefing is not new; a note flagged, unflagged and flagged again prints again only when no briefing named it in between; an inactive flagged note is neither printed nor counted.
- **pytest (`test_meeting_prep.py`, new):** an event title holding an entity title matches; an alias matches; a partial word does not; a person in two events appears once; lines stop at five in the stated order; a day with no match writes an empty file; a personal-partition entity never appears in a work brief.
- **bats (`prep.bats`):** `brief_prep.sh` on a server writes no focus file and no focus line; on a standalone machine it does as today; `friction.md` and `people.md` are written and listed in `unavailable.md` when their script fails.
- **bats (`commands.bats`):** `brief.md` carries the order, the Before today's meetings block, the Friction and Recurring rules and the Blockers heading; `debrief.md` carries the two conditionals; the template carries the heading.
- The gate: `system/scripts/verify_setup.sh`.

Bound tools: pytest, bats and the gate.

## 6. Left to the builder

The exact wording of each heading and count line; where in `vaultlib` the previous-weekday-briefing lookup lives; how `people.md` renders an entity with no open lines (the link line alone, or skipped); how an existing briefing with the old matrix heading is handled when `/brief` edits it.

## 7. Next grill

Friction to Work Orders: the system queues a research Work Order per new friction note and the brief shows only the decision each one needs.
