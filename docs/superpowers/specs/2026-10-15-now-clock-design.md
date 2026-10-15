# The Now clock: a recommendation and a decide-by date on Now lines, and an Overdue block in the brief

**Date:** 2026-10-15
**Status:** Draft for the owner's review.
**Issue:** #166, line "`due` and `rec` on Now lines, and an Overdue block in the brief" (accepted as the first #166 spec on 2026-10-15). Related: #98 (session continuity), #107 (Now page known limits), #145 (`now.py review`, merged).

## 1. Problem

A Now line says what is open and since when, and nothing else. It does not say what the writer recommends, so the owner re-derives every decision, and it has no date by which it should be settled, so a line can sit open for weeks without the brief treating it differently from one added this morning. On 2026-10-13 one work Now page held 72 open lines, many already moot (#145). `now.py review` finds lines open more than 14 days with no evidence, but only when the Foreman runs it in a lull; the brief shows every open line the same way. The owner's earlier system put two things on every item that needed the owner: the writer's recommendation, and a decide-by clock (landing plus 3 days when a named person waits or the text names a date, else plus 30). Past its clock an item was listed under "Overdue" in the brief, uncapped and grouped by age. Nothing dropped on its own, and an update could tighten a clock or add evidence, never loosen it.

## 2. Decisions

- **Two optional parts, no new required field.** `rec` (the writer's recommendation) and `due` (the decide-by date) are Dataview inline fields inside the statement. A line without them stays valid and is never overdue.
- **One rule for all three kinds.** `owed`, `draft` and `waiting` take the same default clock; on a `waiting` line it is the date to chase. No per-kind branch. **Owner decision 1.**
- **The clock is written once, by the writer, and only tightened.** `now.py add` computes it from what it is given; a repeat add can move it earlier, add evidence or set the recommendation, and is refused when it would move the clock later.
- **Overdue is derived at read time and never stored.** A script lists the lines past their clock; the brief prints that list verbatim. No timer writes the page for the clock.
- **No backfill.** Existing lines keep no clock until a writer tightens one.
- **"Decided for you" is deferred** (§8).

## 3. The line

Each line becomes `- [ ] <kind>: <statement>[ [rec:: <option>: <why>]][ [due:: YYYY-MM-DD]] (<who>, since <date>[, <evidence>])`. Before and after:

```
- [ ] owed: Pick the export format (Blake Sample, since 2026-10-15)
- [ ] owed: Pick the export format [rec:: CSV: the vendor's loader reads it] [due:: 2026-10-18] (Blake Sample, since 2026-10-15)
```

The fields sit before the parenthesis because the current `LINE` pattern ends at `(<who>, since <date>[, <evidence>])` plus an optional close stamp: anything after or inside that parenthesis stops the line from parsing. Inside the statement they parse today: on the second line above `LINE` gives the statement `Pick the export format [rec:: …] [due:: 2026-10-18]`, who `Blake Sample`, since `2026-10-15` (checked against the current regex on 2026-10-15). Dataview's `[key:: value]` form is its documented inline-field syntax, so the brief's `TASK` query should list the line as before and show the two fields; the manual check in §11 confirms it. A tick, a drop, the close stamp and the 7-day prune are unchanged.

`LINE` stays as it is. A new helper reads each field once, anywhere in the statement (`\[rec:: ([^\[\]\n]+)\]`, `\[due:: (\d{4}-\d{2}-\d{2})\]`), and returns the **bare statement**: the statement with both fields removed and whitespace collapsed. `rec` holds no `[`, `]` or newline; `due` is an ISO date. `add` refuses a `--statement` that already holds `[rec::` or `[due::`.

## 4. Writing the clock: `now.py add`

- New flags: `--rec "<option>: <why>"` and `--due YYYY-MM-DD`. Both optional.
- **Default clock**, when `--due` is absent, in calendar days from `since`: **3** when `--who` is not empty, or when the bare statement holds an ISO date that is not part of a longer token (`(?<![\w-])\d{4}-\d{2}-\d{2}(?![\w-])`, so a Work Order id such as `2026-10-08-export-fix` does not count); otherwise **30**. The test reads only the arguments, so `now.py` makes no judgement. Triage passes the sender as `who`, so every inbox line gets 3 days.
- `--due` replaces the default on a new line. It may be any valid date; a writer that knows a deadline names it.
- `add` always writes `[due:: …]` on a new line, so the page shows the clock and every reader reads one value.

## 5. Repeat adds: tighten, never loosen

`add` finds an open line with the same kind and the same **bare** statement (the dedupe key changes from the raw statement to the bare one; without that, `add --due` on an existing line would add a second line).
- No `--due`, `--rec` or `--evidence`, or values equal to the line's: `exists`, nothing written. Triage, the brief and sessions re-add lines this way every day, so this path must stay write-free.
- `--due` earlier than the line's, or the line has no `due`: the field is set, `tightened: <line>`.
- `--due` later than the line's: refused, exit 2, `would loosen the clock (due <date>)`, nothing written.
- `--rec`: set or replaced. `--evidence`: set when the line has none; a different value on a line that has one is ignored (triage re-adds with a new link must not fail).

Hand edits in Obsidian are not checked: the owner may move a clock. A writer that wants a later clock asks the owner. Every write is under `run.lock`, as today. `review`'s duplicate group and `meeting_prep.py`'s entity match also use the bare statement (a `rec` naming a person must not match that person's entity). `check`, `rca.py`, `notify.py`, `triage.py` and `recall.py` need no change: they read `LINE` groups or whole lines, and `check` rewrites a line by prefix, so the fields survive a close.

## 6. Writing the clock: the brief

Interactive, the brief already runs `now.py add` per line, which applies §4. Headless, the brief Edits the staged `Now.md` itself, so `brief_prep.sh` writes one more prep file, `clock.md`, with two lines from `date -d`: `short: <date+3>` and `long: <date+30>`. `brief.md` tells the run to end each line it adds (new objectives, DTCC changes, Work Order decisions) with `[due:: <long>]`, or `<short>` when the statement holds an ISO date, before `(since <date>)`. The run copies a date; it does no arithmetic. A line written without it is only clockless. The brief's "none repeating an open line in `now.md`" compares bare statements: it ignores the two fields, as `add` does.

## 7. The Overdue block

- `now.py overdue [--date YYYY-MM-DD]`, read-only and without `run.lock` like `list` and `review`, reads both Now pages. A line is overdue when it is open (`[ ]`) and its `due` is before the date (today by default). Output, uncapped, groups in this order, each omitted when empty, lines oldest `due` first:

  ```
  **1 to 7 days over**
  - owed: Pick the export format [rec:: CSV: the vendor's loader reads it] [due:: 2026-10-18] (Blake Sample, since 2026-10-15)
  **8 to 30 days over**
  **More than 30 days over**
  ```
  then one line `N open lines carry no clock.` when N > 0. Nothing at all when no line is overdue and every line has a clock.
- `brief_prep.sh` writes `overdue.md` with `now.py overdue --date "$PREP_DATE"`, after `now.md`. `brief.md` prints it verbatim under the bold label **Overdue**, immediately before **From Now**, or nothing when it is empty. The lines are plain `- ` bullets: the owner ticks in From Now, which still lists every open line (the Dataview block is unchanged). **Owner decision 3.**
- A line never leaves Overdue on its own: only a tick, a drop or checked evidence closes it.

## 8. Deferred: "Decided for you"

The #166 line asks headless brief and debrief runs to record each decision they took that the owner could have been asked (the question, the option taken, the alternatives, how to reverse it). It does not fit this mechanism: those decisions are already taken, so a Now line would add one more open item to tick and would later turn overdue; the record is prose the model writes in `brief.md` and `debrief.md`, and its acceptance is a headless re-run. It stays its own S line on #166, which satisfies the rule that deferrals go to the issue.

## 9. Two machines (#107)

The clock adds no server write. `check`, `stamp_and_prune` and the evidence closer are unchanged; `overdue` and the brief only read; a repeat add with nothing new writes nothing. The new writes are an explicit `--due`, `--rec` or `--evidence` on a repeat add, on the machine where the writer runs, exactly as `add` writes today. The headless brief's lines go through the publish gate as today, so #107's second limit is unchanged too.

## 10. Out of scope

A backfill of existing lines; working-day clocks; the clock in SessionStart recall, Slack notice counts or the debrief; filtering overdue lines out of From Now; drafting chase messages for overdue `waiting` lines (#145's comment, item 3); auto-drop of any kind; "Decided for you" (§8).

## 11. Tests the plan must include

- **pytest (`test_now.py`):** the current `LINE` parses the after line of §3; the bare statement and both fields come out in either field order; default 3 with `who`, 3 with an ISO date, 30 with a Work Order id only, 30 otherwise; `--due` overrides; a statement holding `[due::` and a `rec` holding `]` are refused; a repeat add with no new value leaves the file byte-identical; an earlier `--due` tightens; a later one exits 2 and writes nothing; `--evidence` is set once and a different value is ignored; `review` duplicates and `meeting_prep` matches use the bare statement; `check` closing a line and the 7-day prune keep both fields; `overdue` groups, order, the no-clock count, both partitions, closed and dropped lines excluded, 40 overdue lines all printed, nothing written.
- **bats:** `prep.bats`: `brief_prep.sh` writes `overdue.md` and `clock.md`; `commands.bats`: `brief.md` carries the Overdue block, the headless `[due::]` rule and the bare-statement repeat rule, `CLAUDE.md`'s Now rule names `--rec` and `--due`, and `FOUNDRY.md`'s Now paragraph describes the clock.

Every test fails before the change. Bound tools: pytest, bats (`prep.bats`, `commands.bats`) and the gate. **Manual check before merge:** the owner opens a scratch brief whose From Now lists a line with both fields, confirms Dataview shows it, ticks it and confirms the tick lands on `Now.md`.

## 12. Rollout

After merge and the next template update, existing lines carry no clock and Overdue shows only the no-clock count. New lines from sessions, triage and the brief carry a clock; the first can lapse 3 days later. `FOUNDRY.md`'s Now paragraph and the `/brief` row, and `CLAUDE.md`'s Now rule, change in the same pull request.

## 13. Owner decisions

1. **`waiting` lines take the clock too.** Recommendation: yes, under the same rule; it is the chase date #145's comment asks for, and one rule is less code than two.
2. **A date named in the text gives 3 days (the earlier system's rule) or the date itself.** Recommendation: 3 days; the statement still shows the date, and a writer that wants the date passes `--due`.
3. **Overdue from the script, or a second Dataview block filtered on `due`.** Recommendation: the script; it is testable, works in the headless brief and needs no Obsidian check beyond §11's.
4. **No backfill of existing lines.** Recommendation: none; a backfill would put most of a 72-line page into Overdue on day one, and `now.py review` already covers old lines. The alternative is a one-time `[due:: <today+30>]` on every clockless open line.
5. **"Decided for you" stays a separate #166 item.** Recommendation: yes (§8).
