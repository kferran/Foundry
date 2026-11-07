# Focus-first Brief Design

**Grill:** 2026-10-22, recorded in this spec's `## Grill` section.
**Builder check:** 2026-10-22, two questions: how "no activity" is measured (settled in §3.2: git changes to the project page or a note linking to it) and how a Work Order is tied to a focus project (settled in §3.4: the brief compares names, and lists each call under Decided for you).
**Blueprint:** none: a change to the brief's prep script, command text and template, plus one count in an existing Slack notice.

## 1. Problem

The owner starts the day from Slack, GitHub or the calendar, not the brief. The brief prints every open Now line (159 open, about 37 new a day at #333) in its Dataview **From Now** block, above 🎯 Active Projects, and adds 3–5 "New objectives" to the Now page each morning that nothing closes. The brief answers "what is open", not "what did I choose to work on".

## 2. Goal

The brief opens with the owner's chosen focus (at most 5 projects per partition) and today's objectives drawn from those projects. Open Now lines show as Overdue plus a count with a link. The Now page stops gaining the brief's own objectives.

## 3. Design

### 3.1 The focus list stays `ActiveProjects.md`

No new note type (#122 removed a separate focus tracker). The owner keeps editing `wiki/<partition>/ActiveProjects.md`. `active_projects.py` changes:
- `MAX_ACTIVE = 5` (was 10).
- Entries past the cap print as one line at the end of the partition: `Also active: [[X]], [[Y]]`, with no Next or Decisions. The "only the first N" notice goes.
- Both partitions, each capped separately; work first, as today.

### 3.2 Stale flag

A focus project with no activity in 7 days gets `Stale: no change since <date>` under its heading. Activity is a commit in the last 7 days (before the brief's date) that changed the project page, or changed a note in the same partition that links to it (session digests, meetings and summaries link to it once ingested). One `git log --since --name-only -- wiki/<partition>/` call per partition. When git cannot run, no stale line prints and a notice says so. Proposed swaps wait for the weekly review (#112).

### 3.3 Brief order and Now lines

- `## 🎯 Active Projects` moves above `## 🌅 Morning Alignment` in the template, and gains `### Today` first: 3–5 objectives drawn only from the focus projects' **Next** items, each linking its project page. They are not written to any Now page.
- **From Now** (the Dataview block of every open line) is replaced by one line: `Open Now lines: <n> of <N> not overdue; [[wiki/work/Now]] · [[wiki/personal/Now]]`, n counting open lines in `now.md` that are not in `overdue.md`. **Overdue** stays as it is.
- **Add to Now** loses the **New objectives** bullet. Work Order "Needs you" lines and extension lines still go to the Now page.

### 3.4 Work Orders off focus

In 🛠 Work Orders, the brief appends `(not on focus)` to the Notes cell of a row whose title names no focus project and no codebase a focus project page links. Each such call goes under 🤖 Decided for you. Reordering the queue by focus is a separate issue.

### 3.5 Slack

The brief notice adds counts only: `Brief <date>: <f> focus projects (<s> stale), <n> need you, <w> waiting, <a> alerts today <link>`, f and s read from `system/logs/inputs/<date>/projects.md`. No project name or objective text leaves the vault: FOUNDRY.md's "No note text from `wiki/` is sent" stands (#218 boundary).

## 4. Out of scope

Expiring machine Now lines (#333, revisit after two weeks), queue reordering, a project field on Now lines, proposed focus swaps (#112).

## Grill

2026-10-22, with the owner.

| # | Question | Decision |
|---|---|---|
| Q1 | Worth building? | Yes: the owner skips the brief and starts from Slack, GitHub or the calendar. |
| Q2 | For whom? | The owner and the Foreman: focus ranks Now lines, picks daily objectives, labels Work Orders. |
| Q3 | Without it? | A shorter Now page alone does not record chosen focus. The shrink is still wanted. |
| Q4 | Smallest version? | Reuse `ActiveProjects.md`, Active Projects at the top, Now as Overdue plus a count. No new note type. |
| Q5 | What it displaces | Runs now as an overnight Work Order, ahead of F1–F4. |
| Q6 | Cap | 5 per partition; the rest as one "Also active" line. |
| Q7 | Daily objectives | Drawn from focus projects' Next items, shown in the brief, not written to Now. |
| Q8 | Slack | A short block at brief time. Settled for the build as counts only, since project names are wiki text (§3.5). |
| Q9 | Keeping it current | Stale flag after 7 days; swaps go to #112. |
| Q10 | Work Orders | A "not on focus" label; reordering is a separate issue. |
| Q11 | Partitions | Both, 5 each, work first. |
| Q12 | Machine-line expiry | Stays in #333; revisit after two weeks. |
