# Run-time resilience (#436 S1, S3, S4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An outage holds intake without poisoning inputs, a unit script's crash exits 70 and alerts, and the brief and debrief leave the daily cap.

**Architecture:** S4 narrows the cap block in `run_headless.sh` to `ingest`. S1 adds a short `claude -p` check to `run_headless.sh` after exit 1 or 124 that turns an outage into exit 7, which intake treats like the cap. S3 adds a Python guard in `vaultlib/alerts.py` and a shell `crash_trap` in `lib_fetch.sh`; the four unit scripts use them.

**Tech Stack:** bash, jq, Python 3 stdlib, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-run-time-resilience-design.md`

## Global Constraints

- Exit 7 = outage (`run_headless.sh` only); exit 70 = a crash in a unit's script. Exit 1 keeps its meaning (handled, alerted).
- `SuccessExitStatus` stays `1 4` (nightshift, watch, telemetry) and `1` (smoke); `units.bats:273,484` unchanged.
- The cap stays `HEADLESS_MAX_RUNS_PER_DAY` (default 60) and applies to `ingest` only; failed ingest runs keep counting.
- `debrief_prep.sh:109` (the heartbeat's run count) is not changed.
- Alert text uses an existing tag: `[intake]` (outage), `[orders]` (nightshift), `[telemetry]`, `[intraday]` (watch), `[smoke]`.
- Crash alert text: `<unit> crashed: <type>; journalctl --user -u <unit>`, once a day per unit.
- Outage alert once a day, marker `system/logs/.outage-alerted-<date>`; no per-run "failed (exit N)" alert for 7.
- Bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Tests stub claude; no test calls the real claude. The probe (Task 2) and the live acceptance run real claude in a `.scratch/` clone with the sandbox off.
- Each PR adds one `changes/<date>-<slug>.md` line with its PR number. The owner merges each PR (headless runner, intake, units).
- Delivery: PR 1 = Task 1 and this plan (branch `feat/run-time-resilience`). PR 3 = Tasks 5-6 (branch `feat/crash-exit`, cut from master; it shares no file with PR 1). PR 2 = Tasks 2-4 (branch `feat/outage-hold`, cut from master after PR 1 merges, since Task 3 edits the cap line Task 1 rewrites). The spec's order (S4, S1, S3) is the merge order; PR 3 may open before PR 2.

## Review Focus

1. An outage check that hangs: the check's own timeout ends it and the run counts as an outage (Task 3 test `outage check that hangs`).
2. A usage-limit result (mapped to 4) or a publish rejection (5) never runs the check (Task 3 test `usage limit runs no outage check`).
3. A `set -e` stop inside `|| rc=$?` handling must not fire the ERR trap (Task 6 test `a failure inside || does not trip the trap`).
4. A crash whose alert write itself fails still exits 70 (Task 5 test `guard exits 70 when the alert cannot be written`).
5. A run of ticks that each crash writes one alert a day per unit (Tasks 5 and 6, the second call in each crash test).

---

## PR 1: S4

### Task 1: The cap applies to ingest only

**Files:**
- Modify: `system/scripts/run_headless.sh:136-144`
- Modify: `FOUNDRY.md:361` (Headless isolation: "a daily run cap")
- Create: `changes/2026-11-02-brief-outside-cap.md`
- Test: `system/tests/headless.bats` (after "meeting runs do not count toward the daily cap")

**Interfaces:**
- Produces: the cap count selects `.command == "ingest"` with exits outside `[2,3,4,6]`. Task 3 adds 7 to that list.

- [ ] **Step 1: Write the failing tests**

```bash
@test "the brief and debrief run when ingest has reached the daily cap (#436 S4)" {
  mkdir -p system/logs
  today="$(TZ=America/Denver date +%F)"
  for i in 1 2; do printf '{"run_id":"r%s","command":"ingest","started_at":"%sT01:00:00-06:00","exit":1}\n' "$i" "$today" >> "$LEDGER"; done
  HEADLESS_MAX_RUNS_PER_DAY=2 STUB_MODE=brief run "$RH" brief
  [ "$status" -eq 0 ]
  [ ! -e "system/logs/.cap-alerted-$today" ]
}

@test "brief and debrief runs do not count toward the ingest cap (#436 S4)" {
  mkdir -p system/logs
  today="$(TZ=America/Denver date +%F)"
  for c in brief debrief; do printf '{"run_id":"%s","command":"%s","started_at":"%sT01:00:00-06:00","exit":0}\n' "$c" "$c" "$today" >> "$LEDGER"; done
  HEADLESS_MAX_RUNS_PER_DAY=2 STUB_MODE=noop run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bats -f "#436 S4" system/tests/headless.bats`
Expected: both FAIL (status 4).

- [ ] **Step 3: Implement**

Wrap lines 136-144 in `if [[ "$cmd" == ingest ]]; then … fi`, and change the count's selector from `.command != "retry" and .command != "meeting"` to `.command == "ingest"`. FOUNDRY.md:361: "a daily run cap" becomes "a daily cap on ingest runs (the brief and debrief neither count toward it nor wait on it)". Change line: `- Changed: the daily headless cap (HEADLESS_MAX_RUNS_PER_DAY, 60) counts and stops ingest runs only, so a day of failing ingest no longer refuses the morning brief. (#N)`

- [ ] **Step 4: Run the suite**

Run: `bats system/tests/headless.bats`
Expected: all pass, the existing cap and meeting tests included.

- [ ] **Step 5: Commit** (with this plan): `fix(headless): the daily cap counts and stops ingest only (#436 S4)`

---

## PR 2: S1

### Task 2: Probe how claude fails logged out and offline

**Files:**
- Create: `docs/superpowers/spikes/2026-11-02-claude-outage-probe.md`

Live, sandbox off, in a throwaway folder under `.scratch/`, real `claude`. Run each of these and record exit code, the `result` object (or its absence) and the elapsed time:

| Case | Command |
|---|---|
| working | `timeout -k 10s 60s claude -p "Reply with the word ok." --tools "" --strict-mcp-config --no-session-persistence --output-format json </dev/null` |
| logged out | the same with `CLAUDE_CONFIG_DIR=<empty folder>` |
| offline | the same with `HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9` |
| offline, a real run's shape | `timeout -k 30s 120s claude -p "Reply with the word ok." --output-format stream-json --verbose` with the proxy set |

- [ ] **Step 1:** Run the four cases; write the table and a verdict to the spike note.
- [ ] **Step 2:** Apply spec §6. The working case must exit 0 with `is_error: false`, or the check's success test follows what the probe shows. The logged-out and offline cases must fail the check. If either passes it, stop and bring it to the owner. If the real-run case ends in a code other than 1 or 124 (such as 137), Task 3's trigger list takes that code too (ledger a ruling).
- [ ] **Step 3: Commit:** `docs(spike): how claude -p fails logged out and offline (#436 S1)`

### Task 3: run_headless.sh turns an outage into exit 7

**Files:**
- Modify: `system/scripts/run_headless.sh` (attempts filter line 78, cap count from Task 1, after the usage-limit mapping at line 192, the failure alert at line 222)
- Modify: `system/tests/stub_claude` (a check branch before the argv record)
- Test: `system/tests/headless.bats`

**Interfaces:**
- Consumes: Task 1's cap selector; Task 2's verdict.
- Produces: exit 7 from `run_headless.sh` = claude itself does not work. Ledger lines carry `exit: 7`. Env knob `HEADLESS_CHECK_TIMEOUT` (default `60s`).
- Stub: when its argv holds the line `Reply with the word ok.`, it writes its argv to `$STUB_CHECK_ARGS` and acts on `STUB_CHECK`: `ok` (default) prints `{"type":"result","is_error":false,"result":"ok"}` and exits 0; `fail` prints `Not logged in` to stderr and exits 1; `hang` sleeps 5. It never touches `$STUB_ARGS`.

- [ ] **Step 1: Write the failing tests**

```bash
@test "a failed run whose outage check fails exits 7, alerts once a day, and is no attempt (#436 S1)" {
  STUB_MODE=fail STUB_CHECK=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 7 ]
  STUB_MODE=fail STUB_CHECK=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 7 ]
  [ "$(grep -c 'claude is not working' system/logs/alerts_*.md)" -eq 1 ]
  run grep -c 'failed (exit' system/logs/alerts_*.md
  [ "$output" = "0" ]
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  [ "$(jq -s 'map(.exit) | join(",")' "$LEDGER")" = '"7,7,1"' ]
  [ "$(jq -s 'last | .attempt' "$LEDGER")" -eq 1 ]
}

@test "a timeout whose outage check fails exits 7 (#436 S1)" {
  HEADLESS_TIMEOUT=1 STUB_MODE=sleep STUB_CHECK=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 7 ]
}

@test "an outage check that hangs ends at its timeout and counts as an outage (#436 S1)" {
  HEADLESS_CHECK_TIMEOUT=1 STUB_MODE=fail STUB_CHECK=hang run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 7 ]
}

@test "the outage check runs only after exit 1 or 124, with no tools (#436 S1)" {
  export STUB_CHECK_ARGS="$BATS_TEST_TMPDIR/check"
  STUB_MODE=noop run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_CHECK_ARGS" ]
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  grep -qx 'Reply with the word ok.' "$STUB_CHECK_ARGS"
  [ "$(grep -A1 -x -- '--tools' "$STUB_CHECK_ARGS" | tail -n 1)" = "" ]
}

@test "a usage limit runs no outage check (#436 S1)" {
  export STUB_CHECK_ARGS="$BATS_TEST_TMPDIR/check"
  STUB_MODE=usage_limit run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  [ ! -e "$STUB_CHECK_ARGS" ]
}

@test "outage runs do not count toward the daily cap (#436 S1)" {
  mkdir -p system/logs
  today="$(TZ=America/Denver date +%F)"
  for i in 1 2; do printf '{"run_id":"r%s","command":"ingest","started_at":"%sT01:00:00-06:00","exit":7}\n' "$i" "$today" >> "$LEDGER"; done
  HEADLESS_MAX_RUNS_PER_DAY=2 STUB_MODE=noop run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bats -f "#436 S1" system/tests/headless.bats`
Expected: FAIL (exits 1 and 124, no check args file).

- [ ] **Step 3: Implement**

- `claude_works()` in `run_headless.sh`: runs `timeout -k 10s "${HEADLESS_CHECK_TIMEOUT:-60s}" "$CLAUDE_BIN" -p "Reply with the word ok." --tools "" --strict-mcp-config --no-session-persistence --output-format json < /dev/null 2>>"$LOG" 9>&-`. It returns 0 when that exits 0 and its output passes `jq -e '.is_error == false'`. Otherwise it sets `check_reason` to `exit <n>` plus the output's `.result` (first 160 characters, when present) and returns 1. Use the success test Task 2 recorded.
- After the usage-limit mapping: `if (( rc == 1 || rc == 124 )) && ! claude_works; then rc=7; fi`, plus any code Task 2 added.
- In the failure branch, before the generic alert: `rc == 7` alerts once a day through the marker `system/logs/.outage-alerted-$TODAY`, with the text `claude is not working ($check_reason); intake holds its inputs until it does`.
- Add 7 to the attempts list on line 78 and to the cap count's excluded exits.

- [ ] **Step 4: Run the suite**

Run: `bats system/tests/headless.bats`
Expected: all pass. "claude failure and timeout are recorded" still sees 1 and 124 (STUB_CHECK defaults to ok).

- [ ] **Step 5: Commit:** `fix(headless): an outage exits 7 after a short claude check (#436 S1)`

### Task 4: Intake holds on exit 7

**Files:**
- Modify: `system/scripts/vaultlib/intake.py:30-35, 402, 463`
- Modify: `FOUNDRY.md:155` (Quarantine)
- Create: `changes/2026-11-02-outage-hold.md`
- Test: `system/tests/python/test_intake.py`

**Interfaces:**
- Consumes: exit 7 from Task 3.
- Produces: `OUTAGE_EXIT = 7`, in `NOT_INPUT_FAULT`, and `STOP_TICK = (CAP_EXIT, SETTINGS_EXIT, BUSY_EXIT, OUTAGE_EXIT)`, which both stop checks use.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_outage_ends_the_tick_and_never_poisons(iv, monkeypatch):
    # #436 S1: exit 7 (claude itself fails) ends the tick like the cap; no attempt, no retry alert.
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/work/notes/d1.md", "---\ntype: session_digest\npartition: work\n---\none\n")
    monkeypatch.setenv("STUB_RC", "7")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert len(calls(iv)) == 3
    assert (iv / "raw/inbox/a.md").exists() and (iv / "raw/work/notes/d1.md").exists()
    assert not (iv / "system/quarantine/poisoned").exists()
    alerts = "".join(p.read_text() for p in (iv / "system/logs").glob("alerts_*.md"))
    assert "will retry" not in alerts and "one at a time" not in alerts
```

Add `7` to the first loop of `test_failures_since_retry_ignores_nonfault_exits`: `for rc in (3, 4, 6, 7, None, "x", 0)`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest system/tests/python/test_intake.py -k "outage or nonfault" -v`
Expected: FAIL.

- [ ] **Step 3: Implement** the constants above, and use `STOP_TICK` at lines 402 and 463.
  - FOUNDRY.md Quarantine, after its first sentence: "An ingest that fails because claude itself does not work (an outage or an expired login, found by a short `claude -p` check after exit 1 or a timeout) exits 7: it is no attempt, the tick stops, the inputs stay, and one `[intake]` alert a day says so."
  - Change line: `- Changed: an outage or an expired claude login no longer moves good inputs to quarantine: ingest exits 7, intake holds its inputs, and one alert a day says claude is not working. (#N)`

- [ ] **Step 4: Run the suite**

Run: `python3 -m pytest system/tests/python/test_intake.py system/tests/python/test_intake_digests.py -q`
Expected: all pass.

- [ ] **Step 5: Commit:** `fix(intake): exit 7 holds the tick and is no attempt (#436 S1)`

---

## PR 3: S3

### Task 5: Python unit scripts exit 70 on a crash and alert

**Files:**
- Modify: `system/scripts/vaultlib/alerts.py` (new function)
- Modify: `system/scripts/nightshift.py`, `extensions/telemetry/scripts/telemetry_fetch.py`
- Test: `system/tests/python/test_alerts.py`; `system/tests/scripts.bats` (a grep that both entry points use the guard)

**Interfaces:**
- Produces: `guard(fn, vault, unit: str, tag: str) -> int` in `vaultlib/alerts.py`. It returns `fn()`'s result. On any `Exception` it prints the traceback to stderr and writes `alert(vault, day, clock, tag, f"{unit} crashed: {type(exc).__name__}; journalctl --user -u {unit}", key=f"{unit} crashed:")`. The day and clock are the vault's timezone, read as `alert.py` reads them. It returns 70, also when the alert write raises `OSError`. `KeyboardInterrupt` and `SystemExit` pass through.
- Entry points: `sys.exit(alerts.guard(lambda: nightshift_run.main(sys.argv[1:], VAULT), VAULT, "foundry-nightshift", "orders"))`. Telemetry does the same with `"foundry-telemetry", "telemetry"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_guard_exits_70_and_alerts_once_a_day_per_unit(tmp_path, capsys):
    def boom():
        raise ValueError("bad")
    assert alerts.guard(boom, tmp_path, "foundry-x", "orders") == 70
    assert alerts.guard(boom, tmp_path, "foundry-x", "orders") == 70
    text = "".join(p.read_text() for p in (tmp_path / "system/logs").glob("alerts_*.md"))
    assert text.count("[orders] foundry-x crashed: ValueError; journalctl --user -u foundry-x") == 1
    assert "Traceback" in capsys.readouterr().err

def test_guard_returns_the_result_of_a_clean_run(tmp_path):
    assert alerts.guard(lambda: 1, tmp_path, "foundry-x", "orders") == 1

def test_guard_exits_70_when_the_alert_cannot_be_written(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "alert", lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    assert alerts.guard(lambda: 1 / 0, tmp_path, "foundry-x", "orders") == 70
```

scripts.bats: `grep -qF 'alerts.guard(' system/scripts/nightshift.py` and the same for `extensions/telemetry/scripts/telemetry_fetch.py`.

- [ ] **Step 2: Run them to verify they fail.** Run: `python3 -m pytest system/tests/python/test_alerts.py -k guard -v`. Expected: FAIL, no attribute `guard`.
- [ ] **Step 3: Implement** `guard` and the two entry points. Update each script's docstring exit list: `70 a crash (alerted)`.
- [ ] **Step 4: Run** `python3 -m pytest system/tests/python/test_alerts.py system/tests/python/test_nightshift_run.py -q` plus the telemetry extension's python tests. Expected: pass.
- [ ] **Step 5: Commit:** `fix(units): a Python unit script's crash exits 70 and alerts (#436 S3)`

### Task 6: Shell unit scripts exit 70 on a set -e stop and alert

**Files:**
- Modify: `system/scripts/lib_fetch.sh` (new function beside `alert_once`)
- Modify: `system/scripts/smoke_check.sh:9`, `extensions/intraday/scripts/watch_fetch.sh:15,45`
- Modify: `FOUNDRY.md` (Always-on extension units paragraph, line 256, or the Smoke check paragraph)
- Create: `changes/2026-11-02-crash-exit.md`
- Test: `system/tests/lib.bats`

**Interfaces:**
- Consumes: `alert_once` and `FETCH_TAG` from `lib_fetch.sh`.
- Produces: `crash_trap <unit>`. It runs `set -E` and sets an ERR trap that calls `alert_once "<unit> crashed:" "exit <rc> at line <n>; journalctl --user -u <unit>"`, then exits 70. Callers run it after `FETCH_TAG` is set. `smoke_check.sh` uses `crash_trap foundry-smoke` and `set -Eeuo pipefail`; `watch_fetch.sh` uses `crash_trap foundry-watch`.

- [ ] **Step 1: Write the failing tests** (lib.bats; each writes a small script to `$BATS_TEST_TMPDIR` that sources `lib_fetch.sh` from a vault made by `make_vault` and runs from the vault root)

```bash
@test "crash_trap: a set -e stop exits 70 and alerts once a day per unit (#436 S3)" {
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' 'crash_trap foundry-x' 'f() { false; }' 'f' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  [ "$(grep -c '\[smoke\] foundry-x crashed: exit 1 at line [0-9]*; journalctl --user -u foundry-x' system/logs/alerts_*.md)" -eq 1 ]
}

@test "crash_trap: a failure inside || does not trip the trap (#436 S3)" {
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' 'crash_trap foundry-x' 'rc=0' 'false || rc=$?' 'exit "$rc"' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 1 ]
  [ -z "$(ls system/logs/alerts_*.md 2>/dev/null)" ]
}
```

The first test calls `false` inside a function, which proves `set -E` reaches functions.

- [ ] **Step 2: Run them to verify they fail.** Run: `bats -f crash_trap system/tests/lib.bats`. Expected: FAIL (`crash_trap: command not found`, status 127).
- [ ] **Step 3: Implement** `crash_trap` and the two call sites.
  - FOUNDRY.md, one sentence: "A unit script that crashes (an uncaught Python exception, or a shell command that stops it under `set -e`) exits 70, which fails the unit (`systemctl --user --failed` shows it until the next run), and alerts once a day: `<unit> crashed: <type>; journalctl --user -u <unit>`. Exit 1 still means a handled failure that already alerted."
  - Change line: `- Changed: a crash in the Work Order runner, the telemetry fetch, the intraday watch or the smoke check now exits 70 and alerts once a day with the journalctl command, instead of passing as a handled failure. (#N)`
- [ ] **Step 4: Run** `bats system/tests/lib.bats system/tests/smoke.bats system/tests/units.bats` and the intraday extension's bats. Expected: pass, `units.bats` pins unchanged.
- [ ] **Step 5: Commit:** `fix(units): a shell unit script's set -e stop exits 70 and alerts (#436 S3)`

---

## After the last merge

- Live acceptance, once, in a `.scratch/` clone with real claude and the sandbox off. Run `run_headless.sh ingest` on one digest logged out (empty `CLAUDE_CONFIG_DIR`), then with the network blocked (the Task 2 proxy). Expect exit 7, one outage alert, the input still in place and no attempt in the ledger.
- Tick S1, S3 and S4 on #436. Update the roadmap's audit track line. Remove the worktrees and branches.
