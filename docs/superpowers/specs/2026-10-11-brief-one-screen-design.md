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

The Friction Matrix heading goes: its three bullets become the Telemetry, Friction and Communication Debt lines in the order above, under one `## 🛑 Blockers` heading. Communication Debt stays one line until #98 phase 2 (my call).

### 3.2 Waiting on: yesterday's meetings, printed once (owner)

- `meeting_actions.py` lists under **Waiting on** the open action items of other people from meetings dated after the previous briefing's date and up to today: on a Tuesday, Monday's meetings; on a Monday, Friday's and the weekend's; on a Saturday, nothing. The previous briefing's date is the newest `briefings/<date>.md` or archived briefing older than today (the rule `now.py seed` already uses).
- An item prints once, the morning after its meeting, and lives on the meeting note after that. There is no rolling window and no cap.
- **Yours** (the owner's own open actions) keeps its current rule: every open item, any age, with days open.
- Grouping stays by owner, as today. My call: within one day, an owner written as a bare first name ("Gavin") joins the group of the owner whose full name starts with it ("Gavin Monson") when exactly one such owner appears that day; otherwise it stays as written. No entity lookup: two spellings on the same day are the only duplicate left once the window is one day.

### 3.3 Friction: new since the last brief, plus a count (owner)

- `brief_prep.sh` writes `system/logs/inputs/<date>/friction.md`: the active concept notes with `is_friction` true that no earlier brief has listed, one `- [[Name]]` per line, newest `compiled_at` first, and a final line `N open friction notes` counting every active one.
- "Listed before" is a ledger, `system/logs/friction_shown.jsonl`, one record per note path with the date it was first printed; a note that loses the flag and gains it again prints again. The first brief after the update prints only the count, so the backlog does not become a 118-line wall once more (my call).
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

- For each calendar event in `calendar.tsv`, in start order, find the entity notes (`wiki/<p>/entities/`, `<p>` the default partition and `shared`) whose title or an `aliases` entry occurs in the event title as whole words, case-folded. An event with no match contributes nothing; a person appears once even when in several events.
- For each matched entity, at most **five lines**, in this order and stopping at five:
  1. the entity link and the event time;
  2. open Now lines of the partition whose `who` is that person or whose statement names them (`owed` lines first, then `waiting`, then `draft`);
  3. that person's open action items from meeting notes, any age, newest first.
- At most five people. A day with no match writes an empty file, and `/brief` prints nothing.
- `/brief` prints the file verbatim as **Before today's meetings**, after the fixed commitments.
- No model reads entity notes for this; the script reads titles and aliases through the index and the Now page through `vaultlib.now`.

### 3.7 Size (my call)

On a weekday with ten meetings, the brief above the 📝 Notes section is under 8 KB. The debrief's size is unchanged by this spec.

## 4. Changes

- `system/scripts/meeting_actions.py`: the Waiting on window (§3.2), the previous-briefing lookup (shared with `now.py seed`, moved to `vaultlib`), the same-day first-name merge.
- `system/scripts/vaultlib/friction.py` (new) and the `brief_prep.sh` step that writes `friction.md` and updates `system/logs/friction_shown.jsonl` under `run.lock`.
- `system/scripts/meeting_prep.py` and `system/scripts/vaultlib/meeting_prep.py` (new): `people.md` (§3.6).
- `system/scripts/brief_prep.sh`, `debrief_prep.sh`: the role-aware focus step; the two new prep files.
- `.claude/commands/brief.md`: the section order; the Before today's meetings block; Friction and Recurring as the prep files give them; the Blockers heading; Focus Drift conditional.
- `.claude/commands/debrief.md`: Focus and Agent Health conditional.
- `system/templates/daily-briefing.md`: the Blockers heading in place of the Friction Matrix.
- `FOUNDRY.md`, `CLAUDE.md` (directory map, if it names the matrix): the new sections and the two prep files.

## 5. Tests

- **pytest (`test_meeting_actions.py`):** a Tuesday brief lists Monday's others' items and not Sunday's; a Monday brief lists Friday's and Saturday's; a Saturday brief lists none; Yours still lists an item 20 days old; "Gavin" and "Gavin Monson" on one day are one group; two full names starting with "Gavin" leave the bare name as written.
- **pytest (`test_friction.py`, new):** a flagged note prints once and is counted after; a note flagged, unflagged and flagged again prints twice; the first run with an empty ledger prints the count only; an inactive flagged note is neither printed nor counted.
- **pytest (`test_meeting_prep.py`, new):** an event title holding an entity title matches; an alias matches; a partial word does not; a person in two events appears once; lines stop at five in the stated order; a day with no match writes an empty file; a personal-partition entity never appears in a work brief.
- **bats (`prep.bats`):** `brief_prep.sh` on a server writes no focus file and no focus line; on a standalone machine it does as today; `friction.md` and `people.md` are written and listed in `unavailable.md` when their script fails.
- **bats (`commands.bats`):** `brief.md` carries the order, the Before today's meetings block, the Friction and Recurring rules and the Blockers heading; `debrief.md` carries the two conditionals; the template carries the heading.
- The gate: `system/scripts/verify_setup.sh`.

Bound tools: pytest, bats and the gate.

## 6. Left to the builder

The exact wording of each heading and count line; where in `vaultlib` the previous-briefing lookup lives; the ledger's record shape; how `people.md` renders a person with no open lines (the link line alone, or skipped).

## 7. Next grill

Friction to Work Orders: the system queues a research Work Order per new friction note and the brief shows only the decision each one needs.
