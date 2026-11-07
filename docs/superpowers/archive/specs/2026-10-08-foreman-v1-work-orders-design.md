# Foreman v1: Work Orders

**Date:** 2026-10-08
**Status:** Draft for the owner's review. Scope settled by a grilling session and a design review with the owner the same day.
**Replaces:** the roadmap's "Sub-project 2 brainstorm" row as the next step. The large §16 build (parallel sessions in herdr or tmux, job state, scout reports, merge modes) becomes **Foreman v2**, unscheduled.

## 1. Problem and goal

The owner approves a spec and a plan so they no longer have to watch a session. After that approval, work still waits on them: someone must queue it, the runner only starts plans in a night window, and sessions hold for prompts. The owner also relays messages between sessions and has no single view of what is queued, running or done.

In order of the owner's priority, v1 fixes:
1. **Approved work waits on the owner.**
2. **Juggling sessions.**
3. **No view of what is in flight.**

**Success**, measured from the run ledger and pull-request timestamps two weeks after release:
- no approval is needed between plan approval and the pull request;
- an approved plan reaches a pull request the same day.

## 2. Decisions (owner, 2026-10-08)

- **No new execution engine.** The existing unattended runner (today "the Nightshift") already runs an approved plan at any time with `--now`, confined, and ends in a pull request. It is enough for v1.
- **The runner is renamed for the user: Work Orders, run by the watcher.** Only names the user sees change: the command, the skill, docs, settings keys and printed text. File paths, systemd unit names, the `nightshift_item` schema, `raw/<p>/nightshift/` and `nightshift.py` keep their names until the reorganization (#62) moves them anyway.
- **An approved plan is queued at once.** Approving a plan with no execution method queues it as a Work Order that starts now, unless the owner says "tonight" or "hold".
- **The vault session the owner talks to is the Foreman.** Design sessions (grill, brainstorm, spec, plan) stay separate, one per project, and hand approved plans to the Foreman by cross-session message. The Foreman runs only `/order add`; the readiness check refuses an unready plan.
- **The Foreman and the design sessions run in the same permission mode**, so a handoff is not held for approval. This is a settings choice for the owner, not part of the build; the README says so.
- **A 5-hour usage ceiling** keeps headroom for the owner's own sessions.
- **Status:** `/order status` at any time, and a Work Orders section in the brief and the debrief.

## 3. Changes

### 3.1 The rename

- **Command and skill:** `/nightshift` becomes `/order` with the same subcommands (`add`, `ask`, `list`, `cancel`, `status`). The skill moves from `.claude/skills/nightshift/` to `.claude/skills/order/`; it still calls `system/scripts/nightshift.py`.
- **Settings keys**, each read with the old key as a fallback so a vault keeps working before its owner edits it:

  | New | Old (still read) | Where |
  |---|---|---|
  | `run_window` | `nightshift_window` | `system/config.md` |
  | `order_workspace` | `nightshift_workspace` | `system/config.md` |
  | `order_max_five_hour` | (new) | `system/config.md` |
  | `order_pr` | `nightshift_pr` | `system/codebases/<name>.md` |
  | `order_hosts` | `nightshift_hosts` | `system/codebases/<name>.md` |
  | `order_plugins` | `nightshift_plugins` | `system/codebases/<name>.md` |

  The schemas (`system/schemas/config.md`, `codebase.md`) list the new keys and keep the old ones, marked as old names.
- **Printed text:**
  - the report heading `# Nightshift: <date>` becomes `# Work Orders: <date>`;
  - the pull-request body line becomes "Queued as Work Order `<id>`.";
  - the author of the protected-files commit becomes "Work Orders";
  - the alert tag `[nightshift]` becomes `[orders]`;
  - the readiness messages that name `nightshift_pr` name `order_pr`;
  - the systemd unit descriptions say "Work Orders tick". The unit names stay the same.
- **Branches:** new pull-request branches are `order/<id>`.
- **Docs:** README (the runner paragraph, the command table, the folder list), CLAUDE.md (the command line, and the directory map's wording for `raw/<partition>/nightshift/`) and the skill text say Work Orders.

### 3.2 When an order runs

- `run_window` defaults to always (empty, or `00:00-24:00`). A vault that sets a window keeps it: `start: window` items run only inside it, as today.
- `/order add` starts **now** by default. "tonight" in the skill maps to `--at 22:00`; "hold" means the skill does not queue.
- The 7-day check (no `start: window` item above 80%) stays.
- **The 5-hour ceiling:**
  - after each finished session, the runner stores the 5-hour utilization as a number (`usage5`) and its time (`usage5_at`), next to today's `usage7`;
  - a tick starts no new `now`, `at` or `window` item while `usage5` is at or above `order_max_five_hour` (default `0.6`) and `usage5_at` is less than 5 hours old (an older value is ignored: the window has reset);
  - an item already running, or waiting for a usage reset, is not affected;
  - the hold is reported as a reason in `/order status`.

### 3.3 Approval queues the order

`CLAUDE.md` gains a rule under Commands:
- When the owner approves a plan and names no execution method, the plan runs as a Work Order that starts now. "native" or "subagent" runs it in the session; "tonight" queues it for 22:00; "hold" leaves it unqueued.
- In the vault, the session runs `/order add` (the skill shows the readiness result).
- In any other repository, the session pushes the plan's branch and sends the exact `nightshift.py add` command to the Foreman session by cross-session message.

### 3.4 Status

- `/order status` shows the current report (`nightshift.py report`), including holds and their reasons.
- **Brief:** the "🌙 Overnight" section becomes **"🛠 Work Orders"**: the `## Items` table of the morning's report. Its Needs-you lines stay under Active Objectives, now headed **Work Orders**.
- **Debrief:** `debrief_prep.sh` copies the open report (the one that collects everything since this morning's brief) to `system/logs/inputs/<date>/orders.md`. `/debrief` shows a **Work Orders** section: its items and Needs-you lines, or "No Work Orders ran today."

### 3.5 The Foreman persona

`system/agents/foreman.md` adds that the Foreman owns the Work Order queue, takes approved plans handed over by design sessions, queues them with `/order add`, and reports them in the brief and the debrief.

## 4. Tests

Existing tests that assert old strings change with the rename: the report and its heading, the branch name, the PR body, the alert tag, the unit descriptions, the skill and command text, and `prep.bats`'s report copy. New tests:
- the old settings keys are read when the new ones are absent, and the new ones win when both are set;
- `/order add` with no start flag starts now; `run_window` empty means always;
- the 5-hour ceiling holds a new item at or above the limit, ignores a value older than 5 hours, and never stops a running item;
- `debrief_prep.sh` copies the open report;
- the `CLAUDE.md` approval rule and the Foreman persona text.

Every test fails before the change. Bound tools: pytest (`test_nightshift_*.py`), bats (`prep.bats`, `commands.bats`, `nightshift.bats`, `units.bats`, `remote.bats`, `vault_integrity.bats`) and the gate (`system/scripts/verify_setup.sh`).

## 5. Rollout

- Ships as a Work Order on a `template` branch; the owner merges.
- A vault picks it up with `update_template.sh`; its existing keys keep working. The README tells the owner to rename the keys when convenient and to run the Foreman and design sessions in the same permission mode.
- After two weeks, the owner checks the two success measures (§1) from the run ledger and the pull requests.

## 6. Out of scope (Foreman v2, unscheduled)

Parallel Work Orders; Workcell sessions in herdr or tmux; job state under `system/jobs/`; the scout report schema; per-project merge modes; renaming files, units, the schema and the queue folders (left to #62).
