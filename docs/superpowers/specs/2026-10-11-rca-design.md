# RCA-to-Jira, phase 1: an attended root-cause analysis that files an approved ticket

**Date:** 2026-10-11
**Status:** Draft for the owner's review.
**Issue:** #106. Grilled with the owner on 2026-10-11. The grill's deferrals are checklist lines on #106: two more entries, live log queries, and phase 2 (unattended runs).

## 1. Problem

Production errors reach the brief as error-group notes in `raw/telemetry/`. Root-cause analysis then happens outside the Foundry, in a separate assistant system that is being decommissioned, and the owner files each ticket by hand. The Foundry needs its own RCA: a repeatable procedure, a durable record of each finding, and a ticket filed only after the owner approves it.

## 2. Decisions (owner, 2026-10-07 and 2026-10-11)

- **One entry in phase 1:** `/rca <error-group note>`, run in an interactive session.
- **The diagnosis procedure** (ported from the decommissioned system's RCA skill), in six steps:
  1. Read the input.
  2. Map the symptom to code areas through the vault index (`vault_index.py related`).
  3. Take the environment from the input.
  4. Use the logs stored in the error-group note: its counts, sample message, links and reopen query. The session runs no live log queries.
  5. Trace read-only to `file:line` in the registered codebase.
  6. Record the finding with **root-cause confidence** and **fix confidence**.
- **The two scales, 1–5.**
  - **Root-cause confidence:** 5 = pinned to `file:line` with a repro and a clean trace; 4 = located with a clear trace, but the repro is partial or one inference is unconfirmed; 3 = a plausible leading candidate; 2 = symptom clear, cause not localized; 1 = cannot localize, or it needs a product decision.
  - **Fix confidence:** derived from root-cause confidence, fix scope and blast radius. 5 = a mechanical fix in 1–3 files with a repro; 3 = an open design call; 1 = a human decision.
- **One note type, `rca`,** in `wiki/<partition>/rca/`, with a Ticket draft section. There is no separate draft type.
- **Approval is a tick.** `/rca` adds an `owed` line, "Review RCA draft: <title>", with evidence `rca:<note stem>`. Ticking it approves filing; dropping it (`[-]`) rejects the draft.
- **The filer is the only Jira writer:** a confined connector session allowed only `createJiraIssue` (the `jira_fetch.sh` pattern, no API token). The intake tick starts it when an approved line's note has no ticket yet. It writes the new key back into the note.
- **`/rca` sessions write nothing outward.** Jira create and edit, error-tracker updates, and mail and chat sends are denied.
- **The draft carries a masked "Not verified" section** into Jira.
- **Hotfix candidate:** a draft can set `hotfix_candidate: true`. It then raises an urgent alert line instead of waiting quietly in the Now page. No step anywhere notifies product owners.
- **Outward text:** the Ticket draft passes the humanizer skill before it is shown to the owner. Proposed code never carries a teammate's initials marker (`// TODO(AB)`); a marker is quoted only as evidence.
- **Unknown terms:** a term the vault index cannot resolve is flagged in the note as unconfirmed, never guessed.
- **Vault-specific values are settings.** The template ships no names or account IDs.

## 3. Changes

### 3.1 `system/schemas/rca.md` and `system/templates/rca.md`

`type: rca` in `wiki/work/`, `wiki/personal/` (not `shared`). Fields:
- `title`, `partition`, `created_at` (date), `source` (link to the error-group note), `codebase`, `environment`;
- `rc_confidence`, `fix_confidence` (int 1–5);
- `hotfix_candidate` (bool, default false);
- `ticket` (set only by the filer), `status` (draft, approved, filed, rejected).

Body sections, in this order:
1. Symptom
2. Environment
3. Evidence
4. Root cause (with `file:line`)
5. Confidence
6. Fix (a fix brief when fix confidence is 4–5, or the open design call)
7. Not verified
8. Unknown terms
9. Ticket draft (summary line, then the description in Markdown)

### 3.2 `.claude/commands/rca.md`

`/rca <raw/telemetry/... .md>`, interactive only.
- Runs the six steps against the error-group note and the codebase named in its `codebase` field (`system/codebases/<name>.md`, path read-only).
- Writes `wiki/<partition>/rca/<date>-<slug>.md` from the template, runs the humanizer pass on the Ticket draft, then runs `now.py add --partition <p> --kind owed --statement "Review RCA draft: <title>" --evidence rca:<stem>`.
- With `hotfix_candidate: true`, it also appends one `[rca] HOTFIX candidate: <title>` alert line.
- When fix confidence is 4–5, it ends by suggesting `/order` with a plan; it starts nothing itself.

### 3.3 `system/scripts/rca_file.sh` and `vaultlib/rca.py`

- The intake tick (`Intake.run`, after `check_now`) runs `rca.pending(vault)`: ticked Now lines with `rca:<stem>` evidence whose note has no `ticket` and status `draft`.
- For each one, `rca_file.sh <partition> <note stem>` runs one confined session allowed only `mcp__claude_ai_Atlassian__createJiraIssue`.
  - The arguments are built from the settings and the note's Ticket draft, never from free text: `cloudId` (`handoffs_site`), `projectKey` (`rca_project`), `issueTypeName` (`rca_issue_type`, default `Bug`), `summary`, `description` (Markdown), `labels` (`rca_labels`) and `assignee_account_id` (`rca_assignee`, optional).
  - `rca.py` checks that the session called only that tool, once, with exactly those arguments, and reads the key from the tool result.
- Under `run.lock`, it writes `ticket: <KEY>` and `status: filed` into the note, and closes the Now line's stamp as `_(closed: filed <KEY> <date>)_`.
- A dropped line sets `status: rejected`.
- A failure leaves the note as it is and alerts once a day. The next tick retries.
- Exits follow `jira_fetch.sh`.

### 3.4 Settings and setup

- `config.example.md` and the config schema gain:
  - `rca_project` (a Jira project key; empty turns filing off);
  - `rca_issue_type` (default `Bug`);
  - `rca_labels` (list);
  - `rca_assignee` (an Atlassian account ID, optional).
- `/setup` phase 6c (Handoffs, which already sets `handoffs_site`) asks for them.

### 3.5 Docs

FOUNDRY.md gets an "RCA" paragraph, plus the new command in the commands table.

## 4. Tests

- **pytest (`test_rca.py`):**
  - `pending()` finds only ticked, unfiled, rca-evidence lines;
  - the argument builder takes values from the settings and the note only;
  - the session check rejects another tool, a second call or other arguments;
  - the key write-back and the status changes; a dropped line becomes `rejected`;
  - the schema validates the template.
- **bats:**
  - `rca_file.sh` with a stubbed `claude`: success, exits, once-a-day alerts (`rca.bats`);
  - the intake hook (via pytest on `Intake.run`);
  - the command, setup and docs text (`commands.bats`).

Bound tools: pytest, bats and the gate.

## 5. Later (tracked on #106)

- Entries: an existing Jira key (comment mode) and a described symptom.
- Live log queries from a session.
- Phase 2: the unattended selector, dedupe, cost guard and after-fix watch.
- A Work Order plan suggested at fix confidence 4–5.
