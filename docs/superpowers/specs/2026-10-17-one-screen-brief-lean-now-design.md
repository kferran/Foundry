# One-screen brief and lean Now page (gap plan phase A)

**Date:** 2026-10-17
**Status:** Approved (owner, 2026-10-17), including the four review decisions: the interactive split of long lines, the Blockers defaults in §3.6, the core budget raise and the 8 KB risk with every project kept.
**Plan:** `docs/superpowers/2026-10-17-cto-gap-plan.md`, phase A. Follows `2026-10-11-brief-one-screen-design.md` (#115), whose sections stand; this spec limits what each section holds.

## 1. Measures (live vault, 2026-10-17 13:49)

| | Today | Target (gap plan) |
|---|---|---|
| Brief 2026-10-17 | 24.4 KB | 8 KB |
| Work Now page | 135 KB: 95 open lines, 207 closed lines | 25 KB |
| Open Now lines over 300 characters | 37 of 95 (longest 503) | 0 |
| Headless brief prompt | 2,991 words (`brief.md` 2,478, telemetry section 409, handoffs section 104) | 2,500 |

The brief's bytes by section: Active Projects 6.9 KB (8 projects), Blockers 5.8 KB (telemetry, then Pipeline's triage and meeting notices), Morning Alignment 4.5 KB (13 meeting actions and 5 new objectives), Handoffs to chase 4.3 KB (22 tickets, some unchanged since 2025), the rest 2.8 KB.

Two facts the gap plan did not have:
- `active_projects.py` already caps next actions at 3 per project (`MAX_NEXT`). The section is large because "Decisions waiting" has no cap and items carry their full text.
- Closed lines take two thirds of the Now page. `stamp_and_prune` drops them 7 days after their stamp, but only when `now.py` writes the page.

## 2. Decisions

Owner, 2026-10-17:
1. **Active Projects:** every project stays in the brief, with up to 3 next actions each.
2. **Waiting on and handoffs:** 5 people, then a count; handoffs over 90 days old collapse to one count line, and at most 10 are listed.
3. **Closed Now lines:** they leave the Now page at the next brief, into a monthly archive note that keeps their text and links.
4. **Line history:** a line keeps its statement short; each update is a dated note under it (`  - YYYY-MM-DD: …`), which the brief does not print.

Taken as the plan recommended, with no question asked:
5. **Caps live in the prep scripts,** so the model only sees capped input.
6. **Evidence closes lines.** The intake tick's `now.py check` already closes lines whose evidence is a merged or closed pull request or a finished Work Order, every 5 minutes. A GitHub issue URL becomes evidence too: closed issue, closed line. `now.py review` stays a read-only list for the Foreman.

## 3. Design

### 3.1 Active Projects (`active_projects.py`)
- Next actions: 3 per project, as today.
- Decisions waiting: at most 3 per project, then `- and N more decisions on the page`.
- Each printed item is cut to 160 characters at a word boundary, with `…`. The project link carries the rest.

### 3.2 Waiting on (`meeting_actions.py`)
- The Waiting on section lists at most 5 owners, those with the most open items first (ties by name), then one line: `and N more people (M actions)`.
- Your own actions (**Yours**) keep every item. Each is cut to 160 characters, as in 3.1.

### 3.3 Handoffs to chase (`extensions/handoffs/scripts/jira_handoffs.py extract`)
- Tickets unchanged for 90 days or less: at most 10, oldest change first, then `and N more`.
- Tickets unchanged for more than 90 days: one line, `N handoffs unchanged for more than 90 days (oldest: KEY, since DATE)`.

### 3.4 The Now archive
- The archive is one note per month, `wiki/<partition>/now-archive/YYYY-MM.md`, made from a new template `system/templates/now_archive.md`. It is `type: concept` with `tags: [now-archive]`, as the Now page is `type: concept` with `tags: [now]`, so core keeps its 14 schemas (the budget test in `vault_integrity.bats`). The body is the closed lines in the order they closed, each with its notes. Nothing ingests it, and the orphan lint skips it.
- `now.py archive --partition <p> --date <day>` moves every closed line (`[x]` or `[-]`, stamped or not) and its notes from the Now page to the month's archive note, under run.lock. An unstamped closed line gets its stamp first, as today.
- `brief_prep.sh` runs it for both partitions before `now.py list`. `stamp_and_prune` keeps stamping and stops dropping lines; `KEEP_DAYS` goes.

### 3.5 Notes under a line
- Form: a line's notes are the lines directly under it indented by two spaces, `  - YYYY-MM-DD: text`. Every reader of Now lines already reads only lines that start `- [ ] `.
- `now.py note --partition <p> --match <text> --text <update>` appends one note under the one open line that matches, dated today.
- `now.py add` and `set` refuse a line over 300 characters, written in full (statement, fields and the parenthesis). Recall still cuts at 240.
- The publish gate refuses a staged Now page that adds an open line over 300 characters. The headless brief writes Now lines by editing the page.
- Moving, archiving and `set` keep a line's notes with it.
- **Existing long lines.** A script cannot tell a statement from its history, so the 37 lines are split in one interactive Foreman session: `now.py review` lists them (`long`), and each is rewritten with `set` and `note`. The owner reads the page diff before the sync commit. This replaces the "migration" in the grill's option text.
- **Open:** Dataview's TASK view in the brief's From Now block may show a line's notes as its children. The live acceptance checks this. If it does, the From Now block shows the notes, and the brief's own text still prints none.

### 3.6 Blockers (defaults, for the owner's review)
These follow from the target and were not grilled:
- Pipeline: a `[triage]` alert already became a Now line, so the brief prints `[triage] N new (on the Now page)` once. Today it prints every line.
- Pipeline: meeting notices print only for meetings imported since the previous brief.
- Telemetry: Recurring stays one line per environment, and an environment with no groups is left out.

### 3.7 Size tests
- A fixture vault at the live vault's size (`system/tests/fixtures/brief_size.py`: 8 projects with 5 next actions and 6 decisions each, 12 waiting owners, 95 open and 200 closed Now lines, every third item past the 160-character cut). A bats test runs the brief prep on it and fails when the inputs the brief prints add up to more than 8 KB. `now.md` is left out: the brief reads it only to skip repeats. Handoffs are left out: the extension's own tests hold its cap. On 2026-10-17 the fixture measured 7.4 KB (projects 4.3, actions 1.8, overdue 1.2); with every item long, projects alone are 8.8 KB.
- A bats test counts the words of `brief.md` plus every extension's `brief/section.md`, and fails above 2,500.
- A bats test fails when the fixture's Now page is over 25 KB after `now.py archive`.

## 4. Validation

- pytest: `test_active_projects.py`, `test_meeting_actions.py`, `test_now*.py` (archive, note, the 300 cap, issue evidence), the handoffs extension's `test_handoffs_jira.py`.
- bats: `prep.bats`, `commands.bats` and the new size tests; the handoffs extension suite.
- Live acceptance of the brief: the caps in the live brief, the Now page after one archive, and the From Now block with notes.

**Done when** (gap plan): for 5 weekdays the live brief is under 8 KB, the Now page under 25 KB, and the headless brief prompt under 2,500 words.

## 5. Risks

- **Every project stays.** With 8 projects, Active Projects alone is about 4 KB after the caps in 3.1. The 8 KB brief target may need fewer active projects in `ActiveProjects.md`. The size test reports the bytes per section, so the owner sees where the brief stands.
- **Core budget.** Core scripts are at 13,200 lines, the budget's limit. This phase removes `KEEP_DAYS` pruning and trims where it can; the rest raises the budget in this phase's pull request, with the measured count and the reason in the test's comment.
- **Prompt words.** Getting `brief.md` from 2,478 words to about 2,000 means cutting rules, not adding them. Each rule this phase adds replaces one it removes.
