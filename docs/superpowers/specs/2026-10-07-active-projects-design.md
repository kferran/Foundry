# Active Projects in the Brief

**Date:** 2026-10-07
**Status:** Approved in brainstorming (2026-10-07), awaiting written-spec review
**Issue:** #65
**Extends:** brief prep (`brief_prep.sh`, spec §6.5); brief carry-forward (PR #36); meeting actions (meetings spec §2.5)

## 1. Problem and decisions

A user working on a few long-running projects keeps one working page per project in the wiki: status, next actions as checkboxes, decisions waiting on them. The morning brief shows none of it, so the user opens each page to remember where things stand, and nothing in the brief points at the project they said is their main focus. This feature lists the active projects in the brief, each with its next few open actions and the decisions waiting on the user, read from the project's own page.

| Topic | Decision |
|---|---|
| What the brief shows | A "today's slice" per active project: a link, the next 3 open actions and every open decision waiting on the user. |
| Where items are ticked | On the project page only. The brief lists project items as plain bullets, never checkboxes, so nothing is tracked in two places. |
| Project pages | Ordinary `concept` notes. No new note type, schema or folder. A page needs only checkboxes and, optionally, a "Decisions…" heading (§3). |
| Which projects are active | A hand-maintained list note per partition, `wiki/<partition>/ActiveProjects.md`, in priority order. The user (or the Foreman when asked) moves lines between `## Active`, `## Paused` and `## Done` as work moves. |
| Extraction | Deterministic: a new script, `system/scripts/active_projects.py`, run from `brief_prep.sh`. No model reads project pages to decide what is next. |
| Packaging | Ships in this repository. The list notes and project pages are the user's vault content; this repository ships neither. |

Rejected:
- **A `project` note type in a top-level `projects/` folder** (schema, index view, status field). It needs a schema, an index view, lint rules and a migration for existing pages, and the user preferred maintaining a list by hand.
- **Mirroring project actions into the brief as checkboxes that carry forward.** That makes two copies of every action and two places to tick it.
- **A tag- or frontmatter-driven list.** The user wants to order projects by priority and move them between Active, Paused and Done by editing one list.

## 2. The list note

`wiki/work/ActiveProjects.md` and `wiki/personal/ActiveProjects.md` are optional. `wiki/shared/` has none, because shared notes hold partition-neutral knowledge, not work.

The list note is a `concept` note at the partition root (the concept schema's `folders` is `wiki/<partition>/`, which admits it):

```markdown
---
type: concept
tags: ["active-projects"]
compiled_at: 2026-10-07
partition: work
status: canonical
provenance: ["interactive"]
---

# Active Projects

## Active
- [[MigrationProject]]: main focus through April
- [[SomeOtherProject]]

## Paused
- [[ParkedProject]]: waiting on vendor

## Done
- [[FinishedProject]]: closed 2026-09-30
```

Rules:
- Only `## Active` is read. Its order is the priority order.
- An entry is a line `- [[Target]]` with an optional `: focus` text after the link. The target resolves the way Obsidian resolves it (`vaultlib.links.Resolver`).
- A target outside the list's own partition is rejected and reported (§4.3), to keep the partition walls.
- Lines that are not entries (prose, blank lines, nested bullets) are ignored.
- At most 10 active entries are read. More produce a notice line (§4.2).

## 3. Reading a project page

For each active entry, the script reads the target's body (frontmatter stripped with `vaultlib.frontmatter`) and collects two lists.

**Next actions.** The first 3 open checkboxes in page order, outside any "Decisions" section.
- An open checkbox is a line matching `^\s*- \[ \] (.+)$`. Nested checkboxes count, and their indentation is dropped.
- `- [x]` (done) and `- [-]` (dropped) lines never count.
- Checkboxes inside fenced code blocks never count (`vaultlib.links.code_free_lines`).

**Decisions waiting.** Every open checkbox under a heading whose text, after the `#` marks and one space, starts with "Decisions" (case-insensitive, at any heading level). The section ends at the next heading of the same or a higher level.

Each item keeps its text verbatim, including wiki links and bold. An item that is only a parent line with nested children is still one item; children are separate items.

## 4. Data flow

### 4.1 Run

`brief_prep.sh` gains one step after `actions.md`:

```bash
prep_write projects.md system/scripts/active_projects.py "$PREP_DATE" \
  || prep_unavailable "projects: active_projects.py failed (see $PREP_DIR/prep_errors.log)"
```

`active_projects.py YYYY-MM-DD`:
1. For each partition in `work`, `personal`, read `wiki/<partition>/ActiveProjects.md`. A missing file means no projects in that partition, with no notice.
2. For each active entry, resolve the target against the vault's `wiki/` files and read it (§3).
3. Print `projects.md` (§4.2) and exit 0. A bad date exits 2. Any other failure exits 1, and `prep_write` keeps no partial file.

The date argument is used only in the header line. The output reflects the pages as they are when prep runs.

### 4.2 Output: `system/logs/inputs/<date>/projects.md`

```markdown
# Active projects for 2026-10-07

## work

### [[MigrationProject]]: main focus through April
Next:
- Get the vendor's answer on API access.
- Confirm which account holds the production data.
- Book the kickoff with the platform team.
Decisions waiting:
- Add a second vendor now or after launch.

### [[SomeOtherProject]]
Next:
- None open.

## Notices
- work: [[MissingPage]] in ActiveProjects does not resolve to a note.
```

- A partition with no list or no active entries is omitted.
- `Decisions waiting:` is omitted when the page has none.
- `## Notices` is omitted when empty.
- When no partition has an active entry, the file holds only the header line and `None.`

### 4.3 Notices

| Case | Notice line |
|---|---|
| Target does not resolve | `- <partition>: [[X]] in ActiveProjects does not resolve to a note.` |
| Target is ambiguous (several notes share the name) | `- <partition>: [[X]] in ActiveProjects matches more than one note; use a path link.` |
| Target is in another partition | `- <partition>: [[X]] is in <other partition>; list it in that partition's ActiveProjects.` |
| Target unreadable | `- <partition>: [[X]] could not be read.` |
| More than 10 active entries | `- <partition>: only the first 10 active projects are shown.` |

Notices never fail the script. The brief puts them under Systemic Blockers (§5).

## 5. The brief

`system/templates/daily-briefing.md` gains a section between Morning Alignment and the Friction Matrix:

```markdown
## 🎯 Active Projects
```

It sits after `### 2. Unavailable Sources`, so `carry_forward.py` (which reads `### 1.` up to `### 2.`) never sees it. The two headings `### 1.` and `### 2.` are unchanged (`commands.bats` checks the second).

`.claude/commands/brief.md` changes:
- **Inputs:** add `system/logs/inputs/<date>/projects.md`: active projects with their next actions and decisions waiting.
- **Write the briefing:** add a **🎯 Active Projects** bullet:
  - Copy each project block from `projects.md` in its order: the link heading, `Next:` items and `Decisions waiting:` items, as plain `- ` bullets, never `- [ ] `.
  - Write "None." when `projects.md` says None.
  - Put `## Notices` lines under Systemic Blockers.
  - When an existing briefing lacks the section, add it before the Friction Matrix.
- **New objectives:** an objective may name a project action and link the project page. It must not repeat the action's text as its own checkbox.
- **Headless runs** read `projects.md` like every other prep input and never open project pages.

## 6. Tests

`system/tests/python/test_active_projects.py` (pytest, fixture vault in `tmp_path`, following `test_carry_forward.py` and `test_meeting_actions.py`):

- Active order is kept; Paused and Done are ignored; the focus text is kept.
- The 3-item cap; nested checkboxes count; `[x]` and `[-]` are skipped; checkboxes in fenced code are skipped.
- The Decisions split: items under a "Decisions…" heading go to decisions, never to next; the section ends at the next same-or-higher heading.
- A page with no open items prints `None open.`
- Each row of the §4.3 notice table.
- Work and personal lists are separate partitions; a missing list is silent.
- A bad date exits 2.
- More than 10 active entries.

`system/tests/prep.bats`:
- `brief_prep.sh` writes `projects.md`.
- A failing `active_projects.py` adds the `projects:` unavailable line and leaves no partial file.

`system/tests/commands.bats`:
- The template has `## 🎯 Active Projects` after `### 2. Unavailable Sources` and before the Friction Matrix.
- `brief.md` names `projects.md`.

`system/tests/python/test_carry_forward.py`:
- A briefing with checkboxes under `## 🎯 Active Projects` carries none of them.

Each test fails before its code exists (red before green).

## 7. Out of scope

- Debrief changes.
- Project health scoring and staleness flags.
- Automatic moves between Active, Paused and Done.
- A `project` note type.
- Reading project pages anywhere but the brief prep.
