# Run-time resilience: outages, crashes and the brief's room (#436 S1, S3, S4)

**Grill:** not an owner idea: audit, the 2026-10-30 stability assessment as filed in https://github.com/kferran/Foundry/issues/436
**Builder check:** 2026-11-01, four questions. The smoke check would miss a crash followed by a clean tick and would re-alert units whose handled exits already fail them: F2 changed to an alert from the crashing script (§3.2). What the S1 build does if the probe disagrees, and whether the debrief heartbeat follows the cap: settled as Claude's calls (§6). Whether F1 and F2 are decided: the owner's (§5).
**Blueprint:** none: three fixes to the existing intake, runner and unit plumbing; no new shape.

## 1. Why

Three findings from the 2026-10-30 stability assessment can each cost a day without anyone noticing (#436, re-checked on master `00e4e37`). Their frequency is unknown: no live server logs were read.

- **S1.** A short outage or an expired `claude` login poisons the intake queue in bulk. `run_headless.sh` exits 1 (claude failed) or 124 (timeout). Intake counts both against the input (`vaultlib/intake.py:35`, `NOT_INPUT_FAULT`), runs up to 5 inputs a tick, and poisons an input after 3 failures. One bad hour moves good inputs to `system/quarantine/poisoned/`, which only a manual retry brings back.
- **S3.** A crash reads as success to systemd. The nightshift, watch and telemetry units set `SuccessExitStatus=1 4`, and smoke sets `SuccessExitStatus=1`. In all four scripts exit 1 already means a handled failure that has alerted (a Work Order ended failed or blocked, `nightshift_run.py:629`; a smoke source failed). A Python traceback or a `set -e` stop also exits 1, so a crash looks the same as a handled failure, and no alert names it.
- **S4.** The daily cap of 60 headless runs (`run_headless.sh:12,137-143`) counts the brief and the debrief. A day of failing or busy ingest runs reaches 60, and then the brief is refused ("daily cap reached"). The morning brief is the one run the owner reads every day.

## 2. Goals

1. An outage or expired login holds intake. Attempts do not advance, inputs stay where they are, and one alert a day says why.
2. A crash in a unit's script is told apart from a handled failure and reaches the owner as an alert.
3. The brief and the debrief always run, whatever ingest did that day.

**Non-goals:** the other #436 items (S2 update pin, S5 Now.md merge, S6 notify hold expiry, S7 retention, S8 calendar check), which come later through the audit track. Changing what counts against the cap for ingest.

**Anti-goals:** an input that really breaks claude must still poison after 3 failures. A fix must never turn a handled failure into a red unit, or add a prompt or install step on the owner's side beyond what §4 names.

## 3. Design

### 3.1 S1: hold intake during an outage

When a headless run ends 1 or 124, `run_headless.sh` checks whether claude itself works before it records the exit. If the check fails, the run's exit becomes **7 (outage)**:
- 7 is recorded in the ledger like any exit, and is left out of attempts (`run_headless.sh:78`, `intake.py` `NOT_INPUT_FAULT`) and out of the daily cap's count (`run_headless.sh:138`).
- Intake treats 7 like 4 and 6: the tick stops, the inputs stay, the next tick tries again.
- One alert a day (`system/logs/.outage-alerted-<date>`), naming the check's reason. The per-run "failed (exit N)" alert is not sent for 7.
- The brief and debrief units surface 7 as they surface any other non-zero exit today.

**The check (fork F1, §5).** Recommended: a minimal `claude -p` call with no tools, a 60 s timeout and the same `CLAUDE_BIN` and environment, whose success is exit 0 and a `result` line that is not `is_error`. It costs one short model call per failed run, only after a failure. The plan's first task confirms how claude behaves logged out (an empty config directory) and with no network (an unreachable proxy) before the code depends on it.

A real input failure passes the check (claude works), so it still exits 1 or 124 and still poisons after 3. An outage that clears between the failure and the check is counted as an input failure, the case today, at most once per failure.

### 3.2 S3: a crash has its own exit code

- `nightshift.py` and `telemetry_fetch.py` catch any exception that escapes `main`, print the traceback to stderr (the journal keeps it) and exit **70** (`EX_SOFTWARE`).
- `watch_fetch.sh` and `smoke_check.sh` get an `ERR` trap, so a `set -e` stop exits 70; their `|| rc=$?` handling is unchanged, since ERR does not fire inside `||` lists.
- `SuccessExitStatus` stays `1 4` and `1`. Exit 1 keeps its meaning (handled, alerted); 70 makes the unit fail, so `systemctl --user --failed` shows it until the next run.

**How a crash reaches the owner (fork F2, §5).** Recommended: the crashing script alerts on its own way out. The Python handler calls the alert writer (`<unit> crashed: <exception type>; journalctl --user -u <unit>`), and the shell trap calls `alert_once` with the same text, once a day per unit. The alert is written within the tick that crashed, needs no new unit or install step, and is not lost when the next tick succeeds. It does not see a process killed from outside (out of memory, `TimeoutStartSec`), which exits by signal without running the handler. The smoke check is not used for this: it sees only a unit still failed when it runs, and these units tick every 5 to 60 minutes, so a crash followed by a clean tick would never reach it (builder check, 2026-11-01).

### 3.3 S4: the brief and debrief are outside the cap

The cap check and the count at `run_headless.sh:137-143` apply to `ingest` only. A brief or debrief run neither checks the cap nor counts toward it. `debrief_prep.sh:109` is not changed: its count is one term of the heartbeat's `signals: N` (`debrief.md`), which tells a quiet day from a failed read and keeps counting every run. Failed ingest runs still count (the cap is the spend limit; S1 handles outages).

## 4. Constraints

- Every exit code, ledger field and alert stays as it is except where this spec names a change. The ledger's existing readers (the debrief, `count_attempts`, the health scorecard) read exit 7 as one more non-zero exit.
- The new alert text uses an existing tag from `vaultlib/alerts.py` (`scripts.bats` test 28 checks every tag a writer uses).
- `units.bats:273,484` pin the `SuccessExitStatus` values; they stay unchanged.
- Bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing.
- Tests stub claude (`system/tests/stub_claude*`); no test calls the real claude. The live acceptance (a throwaway clone in `.scratch/`, real claude, sandbox off) runs once after the build, logged out and with the network blocked.
- The core budget in `vault_integrity.bats` is a guide; a raise is measured and the owner's.
- The pull requests touch the headless runner and intake, so the owner merges them.

## 5. Forks for the owner

- **F1, the outage check.** Recommended: the `claude -p` check above. The alternative reads the failed run's own output: no `result` line means outage. It costs no extra call, but it rests on how claude reports each failure, and a timeout (124) never has a result line, so a hanging input would never poison.
- **F2, how a crash reaches the owner.** Recommended: the script alerts on its own crash (§3.2). The alternative is `OnFailure=` on each service, starting an alert unit within seconds. It also catches a kill or a start timeout, and it covers every `foundry-*` service, but it is one more unit file that every vault installs with `install_units.sh --update`, and it alerts again for the brief, debrief and intake units, which already fail (and alert) on their handled exits.

## 6. Calls made by Claude

- Exit 70 for a crash, keeping 1 for a handled failure. #436 proposed the reverse (a new code for "nothing to do"); keeping 1 changes no existing test or reader.
- Exit 7 for an outage (unused by `run_headless.sh` today; the plan confirms no caller reads 7).
- Failed ingest runs keep counting against the cap.
- The brief and debrief leave the cap entirely, the simpler of #436's two options ("exempt, or reserve room").

- If the plan's first probe shows an outage ending in another code (such as 137, after `timeout -k` kills a hung claude), the trigger list takes that code too, and the check's success test follows what the probe shows. If the check passes while claude is logged out or offline, it cannot tell an outage apart, and the build stops and comes back to the owner.
- `debrief_prep.sh` keeps counting every run in the heartbeat (above).
- The crash alert uses its own wording and leaves the smoke check's `units` drift line alone.

## 7. Delivery

One plan (superpowers:writing-plans) and one pull request per finding, failing test first, in this order: S4 (smallest), S1, S3. The owner merges each. On the last merge: tick S1, S3 and S4 on #436 and update the roadmap's audit track line.
