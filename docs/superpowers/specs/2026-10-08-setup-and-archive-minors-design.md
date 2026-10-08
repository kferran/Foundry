# Setup consent and briefing-archive minors

**Date:** 2026-10-08
**Status:** Scope approved by the owner (2026-10-08, from the issue triage), awaiting written-spec review
**Closes:** #59, #55, #56, #54, #57

## 1. Problem and decisions

Five small issues from live use and the PR #53 review, in two files and their tests:

| Issue | Problem | Decision |
|---|---|---|
| #59 | `/setup` phase 6b re-runs `install_units.sh` with no dry run and no yes, so re-running setup can install telemetry, Nightshift or DTCC units the user never approved. | Phase 6b follows phase 6a: `install_units.sh --dry-run`, show the units that would change, install on an explicit yes, report the `new`/`changed`/`unchanged`/`removed` lines. |
| #55 | When `briefings/archive/<YYYY-MM>/<name>` already exists, the brief says only `<name> not archived (<dest> exists)`, every day, with no way out. | The line says what to do: `briefings: <name> not archived (<dest> exists; merge the two copies, then delete briefings/<name>)`. Editing the archived copy from `/brief` (the issue's alternative) is out of scope. |
| #56 | The archive's failure path (a move that fails) has no test, and the archive tests can fail when they straddle local midnight. | A test for the failure path; the date-sensitive tests skip when the date changes during the run. |
| #54 | The first brief after an update that adds the archive moves every past briefing, and the next sync lints them all; nothing warns the user. | One README bullet under "Updating and uninstalling": run `system/scripts/lint_vault.sh` before such an update. |
| #57 | A client with yesterday's briefing open in Obsidian may write it back to `briefings/<date>.md` after the server archives it (unverified). | Precaution (owner, 2026-10-08): the archive moves only briefings and debriefs dated **two or more days** before today. Yesterday's files stay in `briefings/` for one more day. |

## 2. Changes

- `.claude/commands/setup.md`, phase 6b: the sentence "If phase 5 installed the units, run `system/scripts/install_units.sh` again so the meetings timer follows `meetings_enabled`, and report its lines." becomes "If phase 5 installed the units, run `system/scripts/install_units.sh --dry-run`, show the units that would change, and install on an explicit yes (as in phase 5), then report its lines."
- `system/scripts/brief_prep.sh`, the archive step:
  - a file is moved only when its date is before yesterday (yesterday computed from `$today` with `date -d`, in the vault's time zone like `$today`);
  - the `dest exists` line gains the hint above.
- `README.md`:
  - the `/brief` row in Daily use and any line that says "earlier days" move to `briefings/archive/` says "days before yesterday";
  - one bullet under "Updating and uninstalling" for #54.
- `CLAUDE.md` Directory Map: "Each brief moves earlier days to `briefings/archive/<YYYY-MM>/`" becomes "Each brief moves days before yesterday to `briefings/archive/<YYYY-MM>/`".
- `.claude/commands/brief.md`: any text that says earlier days are archived follows the same wording.

## 3. Tests (bats)

- `system/tests/commands.bats`: phase 6b of `setup.md` holds `install_units.sh --dry-run` and "explicit yes".
- `system/tests/prep.bats`:
  - yesterday's briefing and debrief stay in `briefings/`; a briefing from two days ago moves to `briefings/archive/<YYYY-MM>/`;
  - an existing archived copy gives the hint line from #55;
  - a move that fails (the archive month folder is read-only) leaves the file in place, exits 0 and writes `briefings: <name> could not be archived (see …/prep_errors.log)`; skipped when run as root;
  - each test that computes today's date before running brief prep skips when the date changed during the run.
- `system/tests/vault_integrity.bats` or `commands.bats`: the README holds the #54 bullet; `CLAUDE.md` says "days before yesterday".

Each new or changed test fails before its change.

Bound tools: bats (`commands.bats`, `prep.bats`, `vault_integrity.bats`), the gate.

## 4. Out of scope

- Editing the archived copy from `/brief` or `/debrief` (#55's alternative).
- The end-of-day ingest of the Notes section (#61, waiting for a decision).
- Verifying #57 by hand; the precaution makes it moot.
