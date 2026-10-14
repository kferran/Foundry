# Sync: a run the hook refuses stays behind, the cycle goes on

**Date:** 2026-10-13
**Status:** Draft for the owner's review.
**Issue:** #136 (C7). From the 2026-10-13 audit (`docs/superpowers/2026-10-13-audit.md` on the audit branch).

## 1. Problem

`vault_sync.sh` runs `commit_runs.py` first. On the first run whose commit the pre-commit hook refuses, `commit_runs.py` alerts, unstages the run's paths and returns 1 (`test_a_hook_failure_alerts_leaves_the_run_pending_and_stops`), and `vault_sync.sh` maps that to `fail commit`: no fetch, merge or push until a human fixes the note. The `[sync]` alert comes once a day; the `[commit_runs]` alert comes every cycle, since `commit_runs.alert()` has no dedupe (the audit's "one alert a day" undercounts). Skipping the run inside `commit_runs.py` alone does not help: `git add -A` stages the same paths for the sync commit and the hook refuses that one too. The refused note passed the publish gate; what the hook refuses beyond the gate is a disagreement between `lint_vault.sh --staged` and the gate's schema check, or conflict markers, which the gate never writes.

## 2. Decisions

- **`commit_runs.py` carries on past a refused run.** It alerts, leaves the run pending, prints `refused <run_id> <path>` per path on stdout, commits the later runs and exits 3 at the end when any run was refused (a code of its own, so a crash's exit 1 is never read as a refusal; built 2026-10-14). The alert is written once a day per run: `<run dir>/refused` holds the day and the hook's first line, and a later successful commit removes it.
- **`vault_sync.sh` leaves the refused paths out of the sync commit** (`git add -A -- . ':(exclude,literal)<path>'` per path, literal so a bracket in a name is no glob) and goes on to fetch, merge and push. Exit 3 with `refused` lines is that case; exit 3 with none, exit 1 or exit 2 stays `fail commit`. The refused notes stay modified in the working tree and the next cycle tries them again. Should `origin` bring a change to one of them, `git merge` refuses before it starts ("local changes would be overwritten") and the cycle ends in `fail merge`, alerted once a day with the file named.
- Two fixes rejected: `--no-verify` for run commits, because the hook is the last check before the private remote; restoring the pre-run version of a refused note, because the owner may have edited it since.

## 3. Changes

- `system/scripts/commit_runs.py`: the loop continues on `error`; the `refused` lines; the marker and its dedupe.
- `system/scripts/vault_sync.sh`: captures `commit_runs.py`'s stdout, the exclusion pathspec, the exit mapping.
- `.claude/commands/backup.md` step 3: "If it exits 1, stop" becomes "If it prints `refused` lines, report them; the other runs are committed", and step 5's hook still stops the manual commit as now.
- `FOUNDRY.md`, the sync paragraph: one sentence on a refused run.
- Cross-reference: the C4 spec's pre-update commit runs the same step, so a refused run also blocks the daily update until it is fixed. As built (2026-10-14): the other runs and the sync commit land, the update stops before fetching, and its `[update]` line lists the commits made, names the refused paths and points at the `[commit_runs]` alert in the same day's alerts file, which carries the hook's line.

**Existing vault:** no config or unit change. A vault stuck on a refused run today syncs again on the next cycle, with the refused note still waiting.

## 4. Tests

pytest `test_commit_runs.py`: the hook-failure case flips: the refused run stays pending and alerted, the later run is committed, exit 1, stdout has `refused <run> <path>`; a second call the same day adds no alert and a call on a new day adds one; a run committed after a refusal has no marker. bats `sync.bats`: a published run the hook refuses plus an ordinary edit: the edit is in the sync commit and pushed, the refused note is left modified and unstaged, exit 0, one `[commit_runs]` alert and no `[sync]` alert; `origin` changing that note makes the next cycle exit 1 with `sync failed (merge)`; a `commit_runs.py` that exits 1 with no `refused` line still gives `sync failed (commit)`. Each fails before the change. Bound tools: pytest, bats and the gate.

## 5. Out of scope

- The sync commit itself refused for an owner's own note (`sync.bats` "a commit the hook refuses"): still `fail commit`; the audit did not raise it.
- Why lint and the gate can disagree on a published note.
