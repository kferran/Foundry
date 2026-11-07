# Delivered work and handoffs

**Date:** 2026-10-08; trimmed 2026-10-09 after a three-reviewer check for over-engineering.
**Status:** Draft for the owner's review.
**Issue:** #79 (merged with the delivered-work part of #28; #28's commitments ledger is cut).
**Order:** after Foreman v1 (Work Orders), before RCA-to-Jira phase 1, which reuses this spec's Jira fetch.

## 1. Problem and goal

The owner's role includes making sure the work they generate is tracked and completed. Today:
- **Handoffs disappear.** A ticket the owner files from a review and assigns to a teammate leaves their view until someone mentions it.
- **Deliverables go unrecorded.** The debrief's "Execution Logs & Results" is free text built from commits and digests; documents, analyses, messages and reviews done outside the vault show up only when a digest happens to mention them.

The owner wants a daily list of handoffs to chase and a daily list of what they delivered.

## 2. Decisions (owner, 2026-10-08 and 2026-10-09)

- **Keys only.** The vault stores no copies of ticket content; tickets are read live from Jira each morning.
- **Handoffs come from Jira itself:** tickets in the configured projects, reported by the owner and assigned to someone else. Nothing is recorded in the vault for a handoff.
- **Jira is read through the Atlassian connector,** confined the way the calendar and Drive fetches are. The connector's JQL tool returns no change history (probed 2026-10-09), so "last status change" is the status-category change date: a move inside one category (In Progress to In Review) does not count.
- **Stalled** means open with no status-category change for 7 days, cut in the JQL.
- **Deliverable types** (fixed): decision, doc, analysis, message, code, review, handoff.
- **Views:** the brief shows "Handoffs to chase"; the debrief shows "Delivered today".
- **Cut on 2026-10-09** (reviewers, owner): the weekly rollup, the manual `log:` tool and its log file, Jira source labels, a second Jira read in the debrief, and the settings for stall days and rollup weekday. Earlier cuts: the after-fix error count (RCA-to-Jira) and #28's commitments ledger.

## 3. Changes

### 3.1 Settings (`system/config.md`, schema `system/schemas/config.md`)

| Key | Meaning |
|---|---|
| `handoffs_site` | the Jira site's host name (the connector's `cloudId`), for example `example.atlassian.net` |
| `handoffs_projects` | Jira project keys to read; handoffs are off while this is empty |

### 3.2 The Jira fetch (`system/scripts/jira_fetch.sh`)

- Same pattern as `meetings_fetch.sh`: one confined `claude -p` session allowed only the connector's JQL search tool (`lib_confine.sh`: built-in tools and the server's other tools denied, other servers denied by name, `--strict`), a timeout, a JSONL run log, `alert_once`, and a `--check` mode for `/setup`.
- The query is built from settings, never from free text:
  `project in (<handoffs_projects>) AND reporter = currentUser() AND assignee != currentUser() AND statusCategory != Done AND statusCategoryChangedDate <= -7d ORDER BY statusCategoryChangedDate ASC`.
- A model-free parser (`system/scripts/jira_handoffs.py`) reads the tool result from the session stream, checks that only the expected tool ran with exactly those arguments (exit 7 otherwise), merges the pages, and prints one line per ticket for the brief: `- [ ] [<key>](<link>) <summary> (<assignee>, <status>, unchanged since <date>)`. The stream helpers it shares with `meetings_extract.py` move to `vaultlib/stream.py`.
- Exit codes follow the meetings fetch: 0 ok, 1 claude error, 2 usage or incomplete settings, 3 no connector, 4 timeout, 6 connector error, 7 unexpected tool.

### 3.3 Brief: handoffs to chase

- `brief_prep.sh` runs the fetch when `handoffs_projects` is set and writes `system/logs/inputs/<date>/handoffs.md`. A failed fetch adds an Unavailable Sources line, as the calendar does.
- `/brief` shows a **"🧾 Handoffs to chase"** section after Active Projects with those lines verbatim. The list is rebuilt every morning and never carries forward.

### 3.4 Debrief: delivered today

- **Digest section.** `system/hooks/digest_instructions.md` adds **Delivered**: one bullet per thing handed to someone else or published in the session, as `type — what — link` (types from §2; leave out if none). `/ingest` does not compile it.
- **By hand.** The owner (or the Foreman, asked to log something) writes a `delivered: <type> — <what> — <link>` line in the day's briefing 📝 Notes section.
- **Pull requests.** `debrief_prep.sh` writes `system/logs/inputs/<date>/prs.md` from `gh search prs` (opened or merged that day by the owner, and reviewed by the owner and updated that day), limited to the registered GitHub repositories (a codebase's `order_pr: github:<owner>/<repo>`, and `template_remote` when it is on GitHub). A missing `gh` or a failed search adds an Unavailable Sources line.
- `/debrief` shows a **"6. Delivered Today"** section, grouped by type, from the Delivered sections in `digests.md`, the briefing's `delivered:` lines and `prs.md`, or "Nothing recorded."

### 3.5 Setup

`/setup` gains a handoffs step (server or standalone): it asks for the Jira site and project keys, writes them, and runs `jira_fetch.sh --check`, mapping exits 1, 2, 3, 4, 6 and 7 to plain messages as the meetings step does.

## 4. Tests

- **pytest:** the parser (expected tool and arguments only; pages merged; malformed results fail closed; the brief line format), the query built from settings, and `vaultlib/stream.py` through the existing meetings tests.
- **bats:** `jira_fetch.sh` with a stub `claude` (each exit code, the confinement flags, the query built from settings, the run log, one alert a day), `brief_prep.sh` writing `handoffs.md` and its Unavailable line, `debrief_prep.sh` writing `prs.md` with a stub `gh` and its Unavailable line, the digest instructions' Delivered section, the brief, debrief and setup text.

Every test fails before the change. Bound tools: pytest, bats (`handoffs.bats`, `prep.bats`, `commands.bats`), the gate.

## 5. Rollout

- The plan edits `.claude/commands/`, so it runs in an attended session or as a Work Order through `.nightshift/protected/`; the owner merges.
- The owner sets `handoffs_site` and `handoffs_projects` in the vault (or runs the `/setup` step) and confirms the connector with `jira_fetch.sh --check`.

## 6. Out of scope

A weekly rollup (concatenate debriefs if wanted later); the after-fix error count (RCA-to-Jira); a commitments ledger (#28); writing to Jira; source labels (RCA-to-Jira); detecting deliverables from tool use.
