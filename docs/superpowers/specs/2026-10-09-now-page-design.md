# The Now page: session continuity, phase 1

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #98. Trimmed after a three-reviewer check the same day; the owner chose each cut below.

## 1. Problem

A new session does not know where things stand. Open loops live in the brief's carried objectives, project pages, unsent drafts and chat. SessionStart recall loads only the Outcome and Follow-ups of the last three digests, so a session never sees the brief's carried objectives. Records also drift: on 2026-10-09 the vault said two messages were "unsent" a day after both were sent.

#98 proposed a ledger of one note per item, with six kinds, a generator, a watch timer and a dashboard. The reviewers sized its phase 1 at about 2,000 to 2,600 lines and found the order inverted: phase 1 created records, and the evidence checks that fix drift came only in phase 2. On 2026-10-08 the owner cut #28's commitments ledger from #79. This phase brings back a smaller one because a new session must see open loops, and the brief alone does not reach sessions.

## 2. Decisions (owner, 2026-10-09)

- **One `Now.md` checklist per partition** (`work`, `personal`), at `wiki/<partition>/Now.md`, not one note per item. It moves to per-item notes only if parallel edits ever conflict.
- **Three kinds:** `owed` (you owe it), `waiting` (someone owes you), `draft` (a message not yet sent).
- **Now replaces the brief's carried objectives.** There is one list: the brief shows Now's open items, and new objectives go into Now.
- **You tick in the brief.** The brief shows Now through a Dataview `TASK` query, so a tick in the brief changes `Now.md`. You never have to open the Now page. If the tick does not reach `Now.md`, the fallback is one Obsidian embed per partition and section.
- **Closing:** your tick, or checked evidence. In phase 1 the evidence is a pull request (merged or closed, read with `gh`) or a Work Order (done, failed or cancelled). A model never closes an item on its own judgement.
- **Later phases:**
  - **Phase 2 starts with inbox triage (#99)**, the first watch, built right after phase 1. A confined fetch every 30 minutes on workdays, in working hours, on the meetings and Jira pattern, sweeps inbox mail, chat DMs and mentions, and tickets assigned to or naming the owner. It skips bot mail unless the mail names the owner or a production case. Each item that needs the owner becomes an `owed` line in `Now.md`, with the message link as evidence and a proposed next step, and raises an alert once. Two inbound items that sat unseen on 2026-10-09 are the reason;
  - further watches on a timer, one connector at a time;
  - a "draft was sent" check and other connector checks;
  - a dashboard.
- **Cut:**
  - the `inflight` and `decision` kinds;
  - per-item notes and the generator;
  - the digest State section and intake reconcile;
  - the seed import;
  - debrief Opened and Closed sections;
  - snooze.

## 3. Changes

### 3.1 The page

`wiki/<p>/Now.md` is a `concept` note with two sections:

```
## Needs you
- [ ] owed: Review the export PR (Blake Sample, since 2026-10-08, https://github.com/acme/shop/pull/7)
- [ ] draft: Reply to the vendor about the delay (vendor, since 2026-10-09)
## Waiting
- [ ] waiting: Access to the staging logs (Blake Sample, since 2026-10-07, EX-12)
```

Each line is `- [ ] <kind>: <statement> (<who>, since <date>[, <evidence>])`. `owed` and `draft` go under Needs you, and `waiting` goes under Waiting. You close a line by ticking it (`[x]`), or drop it with `[-]`, as with brief objectives. A checked close appends `_(closed: <how> <date>)_`. A tick by hand carries no date, so each `now.py` write first stamps every ticked or dropped line that has no stamp with `_(closed: ticked <date>)_`. A line stays 7 days after its stamp, then the next write removes it.

### 3.2 The writer: `system/scripts/now.py`

- `now.py add --partition <p> --kind <owed|waiting|draft> --statement "<text>" [--who <name>] [--evidence <url or key>]` appends a line under the right section and creates the page when it is missing.
- `now.py list [--partition <p>]` prints the open lines.
- `now.py check` is the evidence closer (§3.4).
- It takes `system/run.lock`. It refuses `shared` and any statement that holds a newline, and it is idempotent: the same open statement is not added twice.
- It is allowlisted for interactive sessions. Headless runs edit the page through the publish gate like any wiki note.

### 3.3 Where the page is read and written

- **Sessions (CLAUDE.md rule):** when something becomes owed, waiting or an unsent draft, record it with `now.py add`. Before calling anything unsent or still waiting, check its evidence.
- **SessionStart recall:** loads the open lines of the session partition's `Now.md` first, before digests, untruncated. When the budget is short, digests are cut first.
- **The brief:**
  - The "Carried forward" block and the **New objectives** checkboxes become one **From Now** block: a Dataview `TASK` query over both partitions' `Now.md`, open lines only, grouped by section:
    ````
    ```dataview
    TASK
    FROM "wiki/work/Now" OR "wiki/personal/Now"
    WHERE !completed AND status != "-"
    GROUP BY section
    ```
    ````
    You tick lines in the brief, and Dataview writes the tick to `Now.md`. The list is live, so a line the evidence check closes at 10:00 leaves the brief at 10:00. The brief no longer shows an age in days or a "stale" marker; each line keeps its `since <date>`. Without Dataview, the block shows as a code block, as `wiki/Index.md` does.
  - The 3–5 new objectives are written into `Now.md` as `owed` items, none repeating an open line, so they appear in the query. Headless, this goes through the publish gate. `brief_prep.sh` writes `now.md` (the open lines of both partitions) so the brief can check for repeats.
  - DTCC changes and the Work Orders report's "Needs you" lines carried forward with the objectives. They now go into `Now.md` as `owed` lines too, on the page of the partition that holds the change note or the Work Order. A Work Order id stays in the statement and never becomes evidence, because the order is already finished and the check would close the line at once.
  - `carry_forward.py` and `carried.md` are retired.
  - Once, when the default partition has no `Now.md`, `brief_prep.sh` creates it from the previous brief's open objectives. Objectives carry no partition, so they all go to the default partition. A new page comes from `system/templates/now.md`.
- **Owner:** ticks lines in Obsidian, or adds lines by hand in the same format.

### 3.4 The evidence closer

`now.py check` runs from the intake timer every 5 minutes, on a standalone machine or server. For each open line whose evidence is:
- a GitHub pull request URL: `gh pr view --json state`; merged or closed ticks it with `_(closed: PR merged|closed <date>)_`;
- a Work Order id: its queue note's `state`; done, failed or cancelled ticks it with that state.

A failed check (no `gh`, a network error) leaves the line open and is logged. Three failures of the same line on one day raise one alert. A check never closes a line on any other evidence.

## 4. Tests

- **pytest (`now.py`):**
  - add: section, format, idempotency, `shared` refused, page created;
  - list;
  - stamp a hand tick or drop with no date; prune 7 days after the stamp;
  - check: PR merged, closed or open, Work Order done or running, `gh` missing; the lock.
- **pytest (recall):** Now's open lines come first and untruncated, and the digests are cut first.
- **bats:**
  - `brief_prep.sh` writes `now.md` (open lines of both partitions) in place of `carried.md`;
  - the brief text carries the From Now query, and CLAUDE.md and setup text;
  - the intake path calls `now.py check`.

Every test fails before the change. Bound tools: pytest, bats (`prep.bats`, `commands.bats`, `memory.bats`) and the gate.

**Manual check before merge:** no test can drive Obsidian, so the owner opens a scratch brief with the From Now query, ticks one line, and confirms `Now.md` changed. If it did not, the plan switches the block to embeds before the PR.

## 5. Rollout

After merge and the next template update, the first brief creates each partition's `Now.md` from the previous brief's open objectives. Sessions start recording items, and recall shows them.
