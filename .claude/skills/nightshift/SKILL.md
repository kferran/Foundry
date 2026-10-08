---
name: nightshift
description: |
  Queue refined work for unattended execution: an approved implementation plan (or a task range of one) that ends in
  a pull request, or a written research brief that ends in a findings note. Use for /nightshift add|ask|list|cancel|status,
  or when the user wants work run overnight, later today or in the background.
---
# Nightshift

Spec: `docs/superpowers/specs/2026-10-06-nightshift-design.md`. Everything runs through `system/scripts/nightshift.py` from the vault root.

**`/nightshift add <plan> [--tasks N-M] [--at HH:MM | --now] [--budget 4h] [--model opus]`**
1. Find the plan's repository: a registered codebase (`system/codebases/*.md`) or `template` (this repository's template remote). Ask if unclear. For `template`, the branch that holds the plan must be pushed to the template remote first: the check and the run read it from there, never from the vault, and `--base` is that branch's name.
2. Read the plan (for `template`: `git fetch -q template <branch>`, then `git show FETCH_HEAD:<plan path>`). Propose `--verify` commands from its test lines (its Global Constraints or the last task's suite run) and a `--tasks` range that leaves out any task on the vault's `master`, a deploy, or a step needing the user. Show both and get the user's yes.
3. Run `system/scripts/nightshift.py add --kind plan --title "<plan title>" --partition <partition> --repo <repo> --base <branch holding the plan> --pr-base <target branch> --plan <path> --tasks <range> --verify "<cmd>" … [--now | --at HH:MM] [--budget] [--model]`. Exit 2 lists what is not ready: report it and stop.

**`/nightshift ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a path under `wiki/<partition>/`). Save it to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--now | --at]`.

**`/nightshift list`**, **`cancel <id>`**, **`status`** (`nightshift.py report` for the coming morning's report).

Queuing is the user's approval for that item to push a branch and open a pull request. Never queue on the user's behalf without an explicit yes in this conversation. Exit codes: 0 ok, 1 an item failed, 2 not ready or bad arguments, 4 a run is in progress.
