# Plan 8e: Real-Use Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An ingest backlog no longer skips the day's brief or debrief, and `/debrief` reads the run ledger's publish fields where they are.

**Architecture:**
- `run_headless.sh`'s default `run.lock` wait for brief and debrief rises from 600 to 1400 seconds (one sync hold plus one ingest run). Each ingest is a new process that needs about 0.2 s to reach `flock`, so a waiting brief gets the lock before the next ingest.
- Unit limits rise to fit the longer wait: brief and debrief `TimeoutStartSec=45min`, and the server's sync drop-ins `60min`.
- `.claude/commands/debrief.md` names `exit` and `.publish.{status,published,rejected,conflicts}`, matching main spec §6.3.

**Tech Stack:** bash 5, flock, systemd user units, bats ≥ 1.8, Python 3.11+.

**Spec:** `docs/superpowers/specs/2026-10-03-two-machines-design.md` rev 4: §5.4 "Lock wait", §5.2 (drop-in limits), §8 (8e), §8.1 (8e), §10 (8e row); main spec `2026-09-30-vault-template-design.md` §6.3 (lock) and §6.6 (unit limits).

## Global Constraints

- **Lock wait (spec §5.4, main §6.3):** `HEADLESS_LOCK_WAIT` default 1400 s, for brief and debrief only; ingest still waits without a limit; the timeout alert and exit 6 are unchanged.
- **Unit limits (main §6.6, spec §5.2):** `jarvis-brief.service` and `jarvis-debrief.service` `TimeoutStartSec=45min`; server drop-ins brief and debrief `60min`; intake unchanged (90, drop-in 105).
- **Ledger fields (main §6.3):** `{run_id, command, started_at, finished_at, inputs[], input_sha256[], partition, exit, publish: {status, published[], rejected[], conflicts[]}, …}`.
- **Tool floor:** jq 1.6, bats 1.8 (no `run -N`), SQLite 3.40, Python 3.11. bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. `systemctl` is always a stub; tests use temp dirs.
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log` (16 suites). **Lint:** `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log` (0 errors). Read verdicts from exit codes, never through a pipe.
- **Patches:** every step is an exact patch tested in a scratch clone of `feat/plan-8e` at 72a4821. Save the block to a file and run `git apply --check <file> && git apply <file>`. A patch that does not apply means the tree differs from the plan's base: stop and compare.
- **Template rule:** no hostname, user path or remote URL is committed. American English. Commit trailers name the authoring model.
- **Never** install units, run `/setup`, `install_units.sh` or `install_hooks.sh` against the real user session; live acceptance uses a throwaway clone.

## Decisions made while planning

- **D1 Two tasks.** The `/debrief` wording and the lock wait share nothing, so a reviewer can accept one and reject the other.
- **D2 The backlog test is a guard.** It passes before Task 2, because the lock order it pins (a waiting brief beats the next ingest process) already holds. It protects the property the 1400-second figure depends on: a persistent ingest worker or an in-process relock would starve the brief (measured during the spec re-review: 0/100 wins against a same-process relock).
- **D3 The default is pinned by a grep.** A behavioral test of a 1400-second wait would take 23 minutes. The test pins the exact assignment line, so the comment goes on the line above it.
- **D4 `stub_claude` gains `STUB_SLEEP`** (default 0) so an ingest run lasts long enough for a brief to queue behind it.
- **D5 Intake's own 600-second wait** for briefing extraction (`vaultlib/intake.py`) is a separate lock use and stays (spec review ruling).
- **D6 Scratch result:** gate 16/16 and lint 0 errors on the Debian host with both tasks applied; each red step was checked against its own commit.

## Review Focus

1. **A brief waits behind one long ingest run (about 15 minutes).** Expected: it takes the lock when the run ends and publishes; no exit 6. Pinned by the backlog test (ordering) and live acceptance (an 11-minute hold).
2. **A sync tick takes the lock between two ingest runs while a brief waits.** Expected: the brief still gets the lock within 1400 s. Covered by the arithmetic in spec §5.4; no test (it needs a 5-minute hold).
3. **A unit hits its new `TimeoutStartSec` while waiting.** Expected: never with the default `HEADLESS_TIMEOUT` (the budgets have a margin of about 3 minutes or more). Pinned by `units.bats` values and `systemd-analyze verify` in the installer tests.
4. **The debrief on a day with a rejected run.** Expected: the debrief's runs section lists the rejection. Pinned by the `commands.bats` wording test.
5. **A user overrides `HEADLESS_LOCK_WAIT`.** Expected: the override still wins. Pinned by the existing exit-6 test (`HEADLESS_LOCK_WAIT=1`).

---

### Task 1: `/debrief` reads the ledger's publish fields

**Files:**
- Modify: `.claude/commands/debrief.md`
- Test: `system/tests/commands.bats`

- [ ] **Step 1: Write the failing test:**

```diff
diff --git a/system/tests/commands.bats b/system/tests/commands.bats
index 6367edc..4b8e716 100644
--- a/system/tests/commands.bats
+++ b/system/tests/commands.bats
@@ -398,3 +398,10 @@ self_edit_contract() {
   [[ "$sec" == *'whenever the mode is `private`'* ]]
   [[ "$sec" != *'On a server or a client, only `private` is allowed: the machines share the vault through the private `origin`. Then check'* ]]
 }
+
+@test "/debrief reads the ledger fields where run_headless.sh writes them" {
+  f=.claude/commands/debrief.md
+  grep -qF '`exit`, `.publish.status`, `.publish.published`, `.publish.rejected`, `.publish.conflicts`' "$f"
+  run grep -F '(command, exit, published, rejected, conflicts)' "$f"
+  [ "$status" -eq 1 ]
+}
```

- [ ] **Step 2: Run and watch it fail.** `bats system/tests/commands.bats > system/logs/t1.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t1.log`. Expected: `exit=1`, only "/debrief reads the ledger fields where run_headless.sh writes them".

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/.claude/commands/debrief.md b/.claude/commands/debrief.md
index 405ac6e..0826b25 100644
--- a/.claude/commands/debrief.md
+++ b/.claude/commands/debrief.md
@@ -24,7 +24,7 @@ Read what exists. Every source that is missing or unreadable goes under **Unavai
 - `system/logs/inputs/<date>/focus.md`: top notes and Focus Fragmentation Warnings.
 - `system/logs/inputs/<date>/unavailable.md`: sources the prep script could not read.
 - `system/logs/alerts_<date>.md`: pipeline alerts.
-- Headless runs: the lines of `system/logs/runs-<YYYY-MM>.jsonl` whose `started_at` begins with the date (command, exit, published, rejected, conflicts).
+- Headless runs: the lines of `system/logs/runs-<YYYY-MM>.jsonl` whose `started_at` begins with the date: `command`, `exit`, `.publish.status`, `.publish.published`, `.publish.rejected`, `.publish.conflicts` (the publish lists sit under `publish`, not at the top level).
 - Agent metrics: Glob `system/logs/metrics/*.json`; each file has `agent`, `timestamp` and `verification_gates.test_suite_passed`.
 
 ## Write the debrief
```

- [ ] **Step 4: Run and watch it pass.** Same command, `exit=0`. Commit: `git add .claude/commands/debrief.md system/tests/commands.bats && git commit -m "fix(debrief): read the ledger's publish fields under .publish"`.

### Task 2: Brief and debrief wait 1400 s for `run.lock`

**Files:**
- Modify: `system/scripts/run_headless.sh`, `system/systemd/jarvis-brief.service.in`, `system/systemd/jarvis-debrief.service.in`, `system/scripts/install_units.sh`
- Test: `system/tests/headless.bats`, `system/tests/units.bats`, `system/tests/stub_claude`

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/headless.bats b/system/tests/headless.bats
index 54767c8..8a31ffa 100644
--- a/system/tests/headless.bats
+++ b/system/tests/headless.bats
@@ -199,6 +199,28 @@ teardown() {
   wait
 }
 
+@test "brief and debrief wait 1400 s for run.lock by default" {
+  grep -qxF 'LOCK_WAIT="${HEADLESS_LOCK_WAIT:-1400}"' "$RH"
+}
+
+@test "a brief waiting behind an ingest backlog runs before the next ingest" {
+  mkdir -p raw/inbox
+  printf 'first note\n' > raw/inbox/a.md
+  printf 'second note\n' > raw/inbox/b.md
+  touch -d '10 minutes ago' raw/inbox/a.md raw/inbox/b.md
+  STUB_MODE=noop STUB_SLEEP=2 system/scripts/intake.py &
+  ipid=$!
+  for _ in $(seq 50); do
+    [ -s "$STUB_ARGS" ] && break
+    sleep 0.1
+  done
+  [ -s "$STUB_ARGS" ]
+  HEADLESS_LOCK_WAIT=30 STUB_MODE=brief run "$RH" brief
+  wait "$ipid"
+  [ "$status" -eq 0 ]
+  [ "$(jq -r .command "$LEDGER" | tr '\n' ' ')" = "ingest brief ingest " ]
+}
+
 @test "permission denials are recorded as warnings" {
   STUB_DENIALS='[{"tool_name":"Write"}]' run "$RH" ingest raw/work/notes/d1.md
   [ "$status" -eq 0 ]
diff --git a/system/tests/stub_claude b/system/tests/stub_claude
index 80bef9e..aaed4ff 100755
--- a/system/tests/stub_claude
+++ b/system/tests/stub_claude
@@ -3,6 +3,7 @@
 printf '%s\n' "$@" > "${STUB_ARGS:-/dev/null}"
 readlink /proc/self/fd/0 > "${STUB_STDIN:-/dev/null}"
 run_id="$(ls wiki/.staging | head -1)"
+sleep "${STUB_SLEEP:-0}"  # a slow run, for lock-order tests
 s="wiki/.staging/$run_id"
 case "${STUB_MODE:-write}" in
   write|write_delete_input|leak)
diff --git a/system/tests/units.bats b/system/tests/units.bats
index f80756a..2430983 100644
--- a/system/tests/units.bats
+++ b/system/tests/units.bats
@@ -52,8 +52,8 @@ move_vault() {  # <new path>: relocate the vault and re-derive the paths the tes
   run grep -l stub_claude "$UD"/*
   [ "$status" -eq 1 ]
   grep -qx 'TimeoutStartSec=90min' "$UD/jarvis-intake.service"
-  grep -qx 'TimeoutStartSec=30min' "$UD/jarvis-brief.service"
-  grep -qx 'TimeoutStartSec=20min' "$UD/jarvis-debrief.service"
+  grep -qx 'TimeoutStartSec=45min' "$UD/jarvis-brief.service"
+  grep -qx 'TimeoutStartSec=45min' "$UD/jarvis-debrief.service"
   grep -qxF "ExecStartPre=-\"$VP/system/scripts/brief_prep.sh\"" "$UD/jarvis-brief.service"
   grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/jarvis-brief.service"
   grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" debrief" "$UD/jarvis-debrief.service"
@@ -270,8 +270,8 @@ set_role() { system/scripts/vault_index.py set system/config.md machine_role "$1
   grep -qxF "ExecStartPre=-\"$VP/system/scripts/debrief_prep.sh\"" "$UD/jarvis-debrief.service.d/jarvis-sync.conf"
   [ "$(grep -c '^ExecStartPre=' "$UD/jarvis-intake.service.d/jarvis-sync.conf")" -eq 2 ]
   grep -qx 'TimeoutStartSec=105min' "$UD/jarvis-intake.service.d/jarvis-sync.conf"
-  grep -qx 'TimeoutStartSec=45min' "$UD/jarvis-brief.service.d/jarvis-sync.conf"
-  grep -qx 'TimeoutStartSec=35min' "$UD/jarvis-debrief.service.d/jarvis-sync.conf"
+  grep -qx 'TimeoutStartSec=60min' "$UD/jarvis-brief.service.d/jarvis-sync.conf"
+  grep -qx 'TimeoutStartSec=60min' "$UD/jarvis-debrief.service.d/jarvis-sync.conf"
   run "$IU"
   grep -qx 'unchanged jarvis-brief.service.d/jarvis-sync.conf' <<< "$output"
 }
```

- [ ] **Step 2: Run and watch them fail.** `bats system/tests/headless.bats > system/logs/t2h.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t2h.log` (expected: `exit=1`, only "brief and debrief wait 1400 s for run.lock by default"; "a brief waiting behind an ingest backlog runs before the next ingest" passes already, see D2) and `bats system/tests/units.bats > system/logs/t2u.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t2u.log` (expected: `exit=1`, "services carry TZ, PATH, an unresolved CLAUDE_BIN and their timeouts" and "a server gets the sync timer and one drop-in per run service, sync around the run").

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/system/scripts/install_units.sh b/system/scripts/install_units.sh
index 19ed7f3..8bf6377 100755
--- a/system/scripts/install_units.sh
+++ b/system/scripts/install_units.sh
@@ -92,7 +92,7 @@ esac
 DROPINS=()
 [[ "$role" != server ]] || DROPINS=(jarvis-intake.service.d/jarvis-sync.conf jarvis-brief.service.d/jarvis-sync.conf
                                     jarvis-debrief.service.d/jarvis-sync.conf)
-declare -A DROPIN_TIMEOUT=([jarvis-intake]=105min [jarvis-brief]=45min [jarvis-debrief]=35min)
+declare -A DROPIN_TIMEOUT=([jarvis-intake]=105min [jarvis-brief]=60min [jarvis-debrief]=60min)
 declare -A DROPIN_PREP=([jarvis-intake]="" [jarvis-brief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/brief_prep.sh"'
                         [jarvis-debrief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"')
 
diff --git a/system/scripts/run_headless.sh b/system/scripts/run_headless.sh
index e746953..0987ea0 100755
--- a/system/scripts/run_headless.sh
+++ b/system/scripts/run_headless.sh
@@ -11,7 +11,8 @@ source system/scripts/lib_config.sh
 CLAUDE_BIN="${CLAUDE_BIN:-claude}"
 MAX_PER_DAY="${HEADLESS_MAX_RUNS_PER_DAY:-60}"
 TIMEOUT="${HEADLESS_TIMEOUT:-15m}"
-LOCK_WAIT="${HEADLESS_LOCK_WAIT:-600}"
+# brief/debrief wait for run.lock: one sync hold plus one ingest run (two-machines spec §5.4)
+LOCK_WAIT="${HEADLESS_LOCK_WAIT:-1400}"
 TZ="$(config_get timezone UTC)"
 export TZ JARVIS_HEADLESS=1
 TODAY="$(date +%F)"
diff --git a/system/systemd/jarvis-brief.service.in b/system/systemd/jarvis-brief.service.in
index 664e88c..116277c 100644
--- a/system/systemd/jarvis-brief.service.in
+++ b/system/systemd/jarvis-brief.service.in
@@ -7,6 +7,6 @@ WorkingDirectory={{VAULT_ROOT}}
 Environment="TZ={{TZ}}"
 Environment="PATH={{UNIT_PATH}}"
 Environment="CLAUDE_BIN={{CLAUDE_BIN}}"
-TimeoutStartSec=30min
+TimeoutStartSec=45min
 ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/brief_prep.sh"
 ExecStart="{{VAULT_ROOT}}/system/scripts/run_headless.sh" brief
diff --git a/system/systemd/jarvis-debrief.service.in b/system/systemd/jarvis-debrief.service.in
index 6092613..ef21f71 100644
--- a/system/systemd/jarvis-debrief.service.in
+++ b/system/systemd/jarvis-debrief.service.in
@@ -7,6 +7,6 @@ WorkingDirectory={{VAULT_ROOT}}
 Environment="TZ={{TZ}}"
 Environment="PATH={{UNIT_PATH}}"
 Environment="CLAUDE_BIN={{CLAUDE_BIN}}"
-TimeoutStartSec=20min
+TimeoutStartSec=45min
 ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"
 ExecStart="{{VAULT_ROOT}}/system/scripts/run_headless.sh" debrief
```

- [ ] **Step 4: Run and watch them pass.** Both commands, each `exit=0`. Then the gate (exit 0, 16 PASS) and lint (0 errors). Commit: `git add system/scripts/run_headless.sh system/systemd/jarvis-brief.service.in system/systemd/jarvis-debrief.service.in system/scripts/install_units.sh system/tests/headless.bats system/tests/units.bats system/tests/stub_claude && git commit -m "feat(headless): brief and debrief wait 1400 s for run.lock; 45-min units, 60 on a server"`.

### Task 3: Live acceptance and status

**Files:**
- Create: `docs/superpowers/spikes/<date>-plan-8e-acceptance.md`, `docs/superpowers/plans/<date>-plan-8e-outcomes.md`
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (Plan 8 row), `README.md` (Status table)

Spec §8.1 (8e), in a throwaway clone under `~/.cache/jarvis-accept/`, with `claude` on `PATH` (a login shell). One live brief, about $0.26; no calendar fetch (the prep step is not run).

- [ ] **Step 1: Clone and configure.**

```bash
A=${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-accept; rm -rf "$A" && mkdir -p "$A"
git clone -q -b feat/plan-8e "$(git rev-parse --show-toplevel)" "$A/v"
cp "$A/v/system/config.example.md" "$A/v/system/config.md"
git -C "$A/v" config core.hooksPath .githooks
```

- [ ] **Step 2: Hold the lock past the old wait.** `flock "$A/v/system/run.lock" sleep 660 &` (11 minutes), then `sleep 60; "$A/v/system/scripts/run_headless.sh" brief > "$A/brief.out" 2>&1; echo "brief=$?"` with a Bash timeout of at least 1500000 ms. Expected: `brief=0` about 10 minutes after the brief started (longer than the old 600-second wait); the ledger line has `exit` 0, a `started_at` about 10 minutes after the brief command started, and `publish.published` lists `briefings/<date>.md`; no `run.lock busy` alert.

- [ ] **Step 3: Record and status.**
  - **Acceptance record:** the exit, the wait observed, the cost, the gate, a verdict.
  - **Roadmap Plan 8 row:** 8e complete with links.
  - **README Status:** an 8e row, Complete with links.
  - **Outcomes doc** from the ledger.
  - `rm -rf "$A"`. Gate, lint, then commit: `docs: Plan 8e acceptance, status and outcomes`.
