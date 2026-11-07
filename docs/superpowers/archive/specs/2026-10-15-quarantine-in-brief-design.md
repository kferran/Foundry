# Quarantine you can recover from: one reader for the brief and the debrief, one retry per input

**Date:** 2026-10-15
**Status:** Built (2026-10-15): PR #206.
**Plan:** phase 1 item 10 of `docs/superpowers/2026-10-15-next-phase-plan.md` (live finding L6).

## 1. Problem

Live use, 10-08 to 10-14:

- The 10-11 debrief said "Quarantine: empty" while two inputs poisoned on 10-08 sat in `system/quarantine/poisoned/`; the 10-12 debrief listed them.
- A digest poisoned on 10-14 after three shrink-guard rejections was patched by hand inside `poisoned/` and never requeued. Editing a file there never requeues it; only `intake.py --retry` does.

The causes, on master at 50dea02:

1. **No prep script reads quarantine.** The brief's model globs `system/quarantine/**/*` itself (`brief.md:35`) and lists file names only, so it also lists `.origin.json` sidecars, held-back run staging trees (`<run_id>/staged/`) and telemetry state backups, with no origin, date or way out.
2. **The debrief has no quarantine input at all.** `debrief.md:39` asks for "alerts and quarantined inputs", but its only input is today's alerts file (`:28`). An input poisoned on an earlier day reads as empty unless the model happens to glob the folder.
3. **The retry needs a run id that only Slack shows.** `intake.py --retry <run_id>` matches ledger records of the current and previous month; the alerts line and the brief never print the run id. `--retry-all` restores every poisoned input at once, including ones the owner wants left alone.

## 2. Decisions

- **One reader.** `vaultlib/quarantine.py` `items(vault)` returns one row per thing in quarantine, oldest first:

  | kind | what | since | way out |
  |---|---|---|---|
  | `poisoned` | an inbox file or digest in `poisoned/`, its origin from the `.origin.json` sidecar | the sidecar's `poisoned_at` | `system/scripts/intake.py --retry-input <name>` |
  | `meeting` | a meeting source in `meetings/`, its reason from `.reason.txt` | the file's mtime | fix the source; the next fetch or drop imports it (meetings spec) |
  | `run` | a held-back run's staging, `<run_id>/` | the run id's timestamp | none needed: the input is retried or poisoned on its own; listed so the owner can delete it |
  | `telemetry_state` | a corrupt telemetry state backup at the root | the file's mtime | none needed: the store was rebuilt; listed so the owner can delete it |

  Sidecars are never rows. A row carries kind, path, origin (or empty), since (a date), age in days, reason (the sidecar's or the last alert's, one line, at most 160 characters) and the way-out command.
- **One retry per input.** `intake.py --retry-input <name>` restores the one poisoned file named `<name>` (its basename in `poisoned/`) to its origin, as `--retry` does for a run's inputs: the same origin check, unique name, sidecar removal, solo-list update and `retry` ledger record. `--retry <run_id>` and `--retry-all` stay.
- **The prep scripts write the rows.** `brief_prep.sh` and `debrief_prep.sh` each run `system/scripts/intake.py --quarantine` and write `system/logs/inputs/<date>/quarantine.md`: one line per row, `- <kind> <origin or path>, since <date> (<n> days): <reason>. <way out>`, or `none` when empty. The brief and the debrief read that file and nothing else for quarantine, so they agree by construction.
- **The brief's Blockers.** Under **Pipeline**, each `poisoned` row is one line with its retry command, oldest first, at most 5 and a count of the rest; `run` and `telemetry_state` rows collapse to one line ("<n> held-back staging folders, <n> telemetry backups: safe to delete"). `meeting` rows stay with the `actions.md` Notices, as today.
- **The debrief's System State Deltas** lists what entered and left quarantine today (rows whose `since` is today, and inputs the ledger's `retry` records restored today), plus the total still held.
- **The Slack notice keeps its line** (#183) and switches its way out to `--retry-input <name>`, which needs no run lookup.

## 3. Changes

- `system/scripts/vaultlib/quarantine.py` (new): `items(vault)` and `render(items, today)`.
- `system/scripts/vaultlib/intake.py`: `retry_input(name)`, sharing the restore step with `retry`.
- `system/scripts/intake.py`: `--retry-input <name>` and `--quarantine` (prints the rendered rows).
- `system/scripts/brief_prep.sh`, `debrief_prep.sh`: write `quarantine.md`.
- `.claude/commands/brief.md`: the quarantine input line (`:35`) reads `quarantine.md`; the **Pipeline** sentence in Blockers (`:62-67`) says how to render the rows. `.claude/commands/debrief.md`: `quarantine.md` joins the inputs (`:28`), and System State Deltas (`:39`) says what to list.
- `system/scripts/vaultlib/notify.py`: the poisoned line's way out becomes `--retry-input <name>`.
- `FOUNDRY.md`: the quarantine and retry paragraph.

## 4. Tests

- pytest (`test_quarantine.py`, new): each kind becomes one row with its since date and way out; sidecars are never rows; an empty folder renders `none`; rows are oldest first.
- pytest (`test_intake_digests.py`): `retry_input` restores exactly the named file, leaves another poisoned file alone, writes the ledger record, and refuses a name not in `poisoned/` (exit 2).
- pytest (`test_notify.py`): the poisoned notice names `--retry-input <name>`.
- bats (`prep.bats`): both prep scripts write the same `quarantine.md` for the same folder; an input poisoned on an earlier day appears in the debrief's input (the 10-11 case).
- bats (`commands.bats`): `brief.md` and `debrief.md` read `quarantine.md` and no longer glob `system/quarantine/`.

Each fails before the change. Bound tools: pytest, bats, the gate, and the live acceptance steps (the brief and debrief command text changes).

## 5. Out of scope

- Ageing out or deleting quarantine automatically. The rows say what is safe to delete; the owner deletes it.
- Retrying a meeting source. The meetings spec owns that path.
- A Now line per poisoned input. The Blockers line repeats daily until the input is retried or deleted, which is the same reminder without a second store.
