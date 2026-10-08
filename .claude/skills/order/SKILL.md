---
name: order
description: |
  Queue refined work as a Work Order for unattended execution: an approved implementation plan (or a task range of one)
  that ends in a pull request, or a written research brief that ends in a findings note. Use for
  /order add|ask|list|cancel|status, or when the user wants work run in the background, later today or overnight.
---
# Work Orders

Specs: `docs/superpowers/specs/2026-10-06-nightshift-design.md` (the runner) and `docs/superpowers/specs/2026-10-08-foreman-v1-work-orders-design.md` (Work Orders). Everything runs through `system/scripts/nightshift.py` from the vault root.

**`/order add <plan> [--tasks N-M] [--at HH:MM | --now] [--budget 4h] [--model opus]`**
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear. For `template`, the branch that holds the plan must be pushed to the template remote first: the check and the run read it from there, never from the vault, and `--base` is that branch's name.
2. Read the plan (for `template`: `git fetch -q template <branch>`, then `git show FETCH_HEAD:<plan path>`). Propose `--verify` commands from its test lines (its Global Constraints or the last task's suite run) and a `--tasks` range that leaves out any task on the vault's `master`, a deploy, or a step needing the user. Show both and get the user's yes.
3. Run `system/scripts/nightshift.py add --kind plan --title "<plan title>" --partition <partition> --repo <repo> --base <branch holding the plan> --pr-base <target branch> --plan <path> --tasks <range> --verify "<cmd>" … [--now | --at HH:MM] [--budget] [--model]`. Exit 2 lists what is not ready: report it and stop.

**`/order ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a new path under `wiki/<partition>/`; research creates new notes only). When the question is about code, ask which repository (a registered codebase or `template`) and which branch or commit (a branch for `template`); the session reads a pinned copy under `code/`, at the remote's default branch when no base is named. Save the brief to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--repo <name> [--base <branch or commit>]] [--now | --at]`.

**`/order list`**, **`cancel <id>`**, **`status`** (`nightshift.py report` for the open report: everything since this morning's brief).

Queuing is the user's approval for that Work Order to push a branch and open a pull request. Never queue on the user's behalf without an explicit yes in this conversation. Exit codes: 0 ok, 1 an item failed, 2 not ready or bad arguments, 4 a run is in progress.
