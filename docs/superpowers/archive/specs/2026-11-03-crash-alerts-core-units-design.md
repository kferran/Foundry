# Crash alerts for the other eight core units (#436, the F6 gaps)

**Grill:** 2026-11-03, https://github.com/kferran/Foundry/issues/436 (owner-approved run-time resilience track; the eight gaps are F6's seeded `PIPELINE_GAPS` lines, listed on #436 on 2026-11-03).
**Builder check:** 2026-11-03, from master `aa0b058`. Four findings:
- **Why these eight were left out:** S3 (#461, spec `2026-11-01-run-time-resilience-design.md` §3.2) covered only the units whose `SuccessExitStatus` hid a crash. These eight have no `SuccessExitStatus` masking, so a crash already fails the unit in systemd. Nothing alerts on it, so it is seen only by someone running `systemctl --user --failed`.
- **The trap catches more than crashes:** `crash_trap` (`lib_fetch.sh:40-48`) traps ERR with `set -E`, so any failing simple command outside an `||` list or an `if` becomes exit 70. In a `set -e` script that matches the existing stop. In a script without `-e`, it turns every failure the script handles on a later line into a crash.
- **Two scripts run without `-e` on purpose:** `brief_run.sh:6` and `vault_sync.sh:5` ("no -e: every step's failure is handled where it happens"). They cannot take the ERR trap as it is.
- **`run_headless.sh` is shared:** it runs the debrief unit, and also every ingest from intake and both brief attempts from `brief_run.sh`. A trap there must name the unit that is running it.

**Blueprint:** none: exit and alert handling in existing scripts, no new part.

## 1. Why

F6's `pipeline.bats` (#495) lists 8 of 10 core units whose entry script installs no crash handler: brief, debrief, intake, meetings, notify, sync, triage and update. In each, an unexpected failure (an unset variable, a `jq` on bad input, a Python exception that escapes `run()`) fails the unit and raises no alert. The brief reports a failed unit only when the run ledger has a line for it. The smoke check sees a timer that stopped triggering, never a run that failed (S3's builder check). Each gap closed deletes its `PIPELINE_GAPS` line, which `pipeline.bats` enforces.

## 2. Goals

1. An unexpected failure in each of the eight units exits 70 and raises one alert a day naming the unit and `journalctl --user -u <unit>`, with the existing tag of each unit.
2. Every exit code, handled failure and alert that exists today stays as it is.
3. Each fixed unit's `PIPELINE_GAPS` line is deleted in the same PR.

**Non-goals:** units that already have a crash handler (smoke, nightshift, the watch and telemetry); a process killed from outside (out of memory, `TimeoutStartSec`), which no in-process handler sees (S3 §3.2); and S6's notify hold (a separate #436 item).

**Anti-goals:** a handled failure that turns into exit 70; a `--check` run or a call from another script that alerts as if it were the unit (the `alerting=` rule in `alerts.guard`); and any change to `SuccessExitStatus`, which `units.bats` pins.

## 3. Design, in three groups by risk

### 3.1 Group A: fetch scripts that already use `lib_fetch.sh` and `set -e`, plus `intake.py`

- `meetings_fetch.sh`, `triage_fetch.sh` and `notify.sh` copy `watch_fetch.sh:47`: `(( check )) || crash_trap foundry-<unit>` after `FETCH_TAG` is set. Their `fail` and `|| rc=$?` paths are unchanged, since ERR does not fire inside `||` lists.
  - `notify.sh` has no `--check` that skips the post (it posts by design), so it traps on every run.
- `intake.py` wraps its run in `alerts.guard(..., VAULT, "foundry-intake", "intake", alerting=<the unit's own run>)`. The unit's own run is the call with no arguments, which `intake_daemon.sh` makes. The `--retry*` and `--quarantine` calls from people and the brief prep do not alert.
- Each script's `set -e` already stops on these failures today, so the risk is the alert text only.

### 3.2 Group B: `set -e` scripts without `lib_fetch.sh`

- **`update_template.sh`:**
  - Source `lib_fetch.sh` for `crash_trap`, set `FETCH_TAG=update`, and trap only under `--unattended`, which is the unit's run.
  - Its `die` path exits 1 with an `[update]` alert, and stays.
  - The plan's first task lists every command whose non-zero exit is expected and confirms it sits in an `||` or an `if`.
- **`run_headless.sh`:**
  - It traps with the unit named by the command it runs: `foundry-debrief` for `debrief`, `foundry-brief` for `brief`, `foundry-intake` for `ingest`, under the existing `[intake]` tag.
  - Its `set +e` windows (`:76` and `:230` inside functions, `:132-135` and `:190-205` at top level) stay outside the trap: the plan sets `trap - ERR` for each window and restores it after.

### 3.3 Group C: scripts without `-e`, `brief_run.sh` and `vault_sync.sh`

- **The trap is EXIT-only:** a new `crash_trap --exit-only <unit>` keeps `on_exit` (the crashes ERR never sees: an unset variable, a bad `$(( ))`) and installs no ERR trap. This adds about 6 core lines in `lib_fetch.sh`. A handled failure never becomes exit 70: under `set -u`, an unset variable stops the script through the EXIT path, and every failure the script handles still runs its own handling.
- **`vault_sync.sh`:** `--pre` and `--post` keep their exit mapping (`:36-41`), because the explicit `exit` command is left alone by `on_exit` (`lib_fetch.sh:53`).
- **`brief_run.sh`:** keeps its pass-through of `run_headless.sh`'s exit (`:11`), which is also an explicit `exit`.

## 4. Testing

Per script, one bats test in its existing suite injects an unexpected failure and asserts exit 70 and one alert line `<unit> crashed:`:
- **Shell scripts:** a stub `jq` on `PATH` that exits 5, or an unset variable for the Group C scripts.
- **`intake.py`:** an exception raised from a monkeypatched step.

A second test runs the script's usual failure path and asserts its exit and alert are unchanged. `pipeline.bats` then passes with that script's gap line deleted. The full gate runs in CI.

## 5. Delivery

Three PRs in the order A, B, C, each deleting its units' gap lines. The owner merges each: B touches the headless runner and C touches sync.

## 6. Open questions

- **O1:** whether `run_headless.sh`'s trap should also write a ledger line, so the debrief counts a crashed run. Deferred: the alert reaches Slack (`[intake]` has severity `now`).
