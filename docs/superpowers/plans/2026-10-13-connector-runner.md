# Connector Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `system/scripts/lib_connector.sh` runs every confined connector session, so the six connector scripts share one `claude` invocation and one outcome rule.

**Architecture:** Two bash functions over `lib_confine.sh`: `connector_run` (confine, fresh session directory, the `claude -p` call) and `connector_outcome` (the checker's exit plus the session's exit to one code and reason). Each caller keeps its checker call, log lines, alerts, locks and `--check` mode. A structure test pins that the flags appear in no other script.

**Tech Stack:** bash, bats.

**Spec:** `docs/superpowers/specs/2026-10-13-connector-runner-design.md`

## Global Constraints

- Work on branch `feat/connector-runner` in a worktree under `.scratch/`. Commit there; the PR says "Part of #122 (step 2)".
- Run one suite through `system/scripts/test.sh <suite.bats>` from the worktree root, outside a sandbox. The gate is `system/scripts/verify_setup.sh`; never two at once.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. New tests go beside related tests, never appended at the end of `commands.bats`.
- Template rule: no hostnames, user paths, account IDs or people, employer, client or codebase names.
- Commits use `git commit -F .scratch/<file>` and end with the session attribution line.
- Bound tools: bats (`connector.bats`, `scripts.bats`, `calendar.bats`, `meetings.bats`, `handoffs.bats`, `triage.bats`, `notify.bats`, `rca.bats`), the gate, one real `calendar_fetch.sh` run.

## Review Focus

- A checker pass is success whatever `claude`'s exit: notify must still commit its cursor and rca must still write back its key when the session exited non-zero after the tool call succeeded (Task 2's `(0, 2) → 0` case; Tasks 7 and 8 keep the commit and write-back after `connector_outcome`).
- `rca_file.sh` touches `.attempt` before the session; when `connector_run` returns 127 or 1 nothing ran, so the caller removes `.attempt` before failing, or the next tick wrongly reports exit 5 (Task 8).
- `meetings_fetch.sh` runs up to eleven sessions in one process; `confine_settings` (a 30 s `claude mcp list`) must run once, and each session must get its own directory (Task 4; `meetings.bats` already counts distinct cwds).
- A unit stopped mid-session must leave no `/tmp` directory: the session directory is under the caller's `work`, which its trap removes (`meetings.bats` #40 test stays green in Task 4).
- Calendar turns strict: a settings rule allowing the whole Calendar server is refused with exit 1 and the rule named (Task 3's new case).

---

### Task 1: `lib_connector.sh` and `connector_run`

**Files:**
- Create: `system/scripts/lib_connector.sh`
- Test: `system/tests/connector.bats`

**Interfaces:**
- Produces: `connector_run <prompt> <work dir>`; inputs `CONNECTOR_SERVER`, `CONNECTOR_PREFIX`, `CONNECTOR_TOOL`, `CONNECTOR_OTHERS` (array of bare tool names), `CONNECTOR_TIMEOUT`, `CONNECTOR_TURNS`, optional `CONNECTOR_SCHEMA` (a file); outputs `<work>/out.jsonl`, `<work>/claude.err`, `CONNECTOR_RC` (the session's exit), `CONNECTOR_REASON`; returns 0 (a session ran), 1 (refused rule, nothing ran) or 127 (no `claude`, nothing ran).

- [ ] **Step 1: Write the failing tests.** `system/tests/connector.bats`, on `calendar.bats`'s setup (same `HOME`, `CLAUDE_BIN`, managed-settings and `STUB_*` exports; `load helpers`; `make_vault`; `cd "$V"`), with a helper that sources the two libraries and sets the inputs:

```bash
# shellcheck disable=SC2034  # the CONNECTOR_* variables are the library's inputs
prepare() {
  source system/scripts/lib_confine.sh
  source system/scripts/lib_connector.sh
  CONNECTOR_SERVER="claude.ai Google Calendar" CONNECTOR_PREFIX=mcp__claude_ai_Google_Calendar
  CONNECTOR_TOOL=mcp__claude_ai_Google_Calendar__list_events CONNECTOR_OTHERS=(create_event get_event)
  CONNECTOR_TIMEOUT=30 CONNECTOR_TURNS=9
  work="$(mktemp -d -p /tmp)"
}
```

Tests (each runs in the bats process, no `run`, so the variables the function sets are visible):
1. "connector_run passes the prompt first, the flags, and the tool lists last": `prepare`; `connector_run "say hi" "$work"`; `[ "$CONNECTOR_RC" -eq 0 ]`; `[ "$(sed -n 1p "$STUB_ARGS")" = -p ]`; `[ "$(sed -n 2p "$STUB_ARGS")" = "say hi" ]`; `grep -qx -- --permission-mode "$STUB_ARGS"`; `[ "$(awk -v f=--permission-mode 'p { print; exit } $0 == f { p = 1 }' "$STUB_ARGS")" = dontAsk ]`; the same for `--output-format` → `stream-json`, `--max-turns` → `9`, `--allowedTools` → the tool, `--max-budget-usd` → `1`; `grep -qx -- --disable-slash-commands`, `--no-session-persistence`, `--verbose`; `run grep -qx -- --json-schema "$STUB_ARGS"` then `[ "$status" -eq 1 ]`; the lines after `--disallowedTools` hold `Bash`, `mcp__claude_ai_Google_Calendar__create_event` and `mcp__claude_ai_Google_Calendar__get_event` and not the allowed tool; `[ "$(cat "$STUB_ENV")" = 1 ]`; `[[ "$(cat "$STUB_CWD")" == "$work"/* ]]`; `[ ! -e "$(cat "$STUB_CWD")" ]`; `[ -e "$work/out.jsonl" ]`; `[ -e "$work/claude.err" ]`.
2. "connector_run passes --json-schema only when CONNECTOR_SCHEMA is set": `prepare`; `printf '{"type":"object"}' > "$work/schema.json"`; `CONNECTOR_SCHEMA="$work/schema.json" connector_run p "$work"`; `[ "$(awk -v f=--json-schema 'p { print; exit } $0 == f { p = 1 }' "$STUB_ARGS")" = '{"type":"object"}' ]`.
3. "connector_run records the session's exit and the timeout's": `prepare`; `STUB_RC=6 connector_run p "$work"`; `[ "$CONNECTOR_RC" -eq 6 ]`; then `CONNECTOR_TIMEOUT=1 STUB_SLEEP=5 connector_run p "$work"`; `[ "$CONNECTOR_RC" -eq 124 ]`.
4. "connector_run returns 127 without claude and 1 on a refused rule, running nothing": `prepare`; `run_rc=0`; `CLAUDE_BIN="$BATS_TEST_TMPDIR/none" connector_run p "$work" || run_rc=$?`; `[ "$run_rc" -eq 127 ]`; `[[ "$CONNECTOR_REASON" == "claude not found"* ]]`; `[ ! -e "$STUB_ARGS" ]`; then write `$HOME/.claude/settings.json` with `{"permissions":{"allow":["mcp__claude_ai_Google_Calendar"]}}`; `run_rc=0`; `connector_run p "$work" || run_rc=$?`; `[ "$run_rc" -eq 1 ]`; `[[ "$CONNECTOR_REASON" == *"allows every tool on mcp__claude_ai_Google_Calendar"* ]]`; `[ ! -e "$STUB_ARGS" ]`.
5. "two sessions in one process list the servers once and get two directories": `prepare`; `STUB_MCP_LIST=$'claude.ai Google Calendar: x - ok\nclaude.ai Gmail: y - ok' connector_run p "$work"`; `first="$CONFINE_SETTINGS"`; `[[ "$first" == *'"claude.ai Gmail"'* ]]`; `cwd1="$(cat "$STUB_CWD")"`; `STUB_MCP_FAIL=1 connector_run p "$work"` (a second `mcp list` would now fail and empty `deniedMcpServers`); `[ "$CONFINE_SETTINGS" = "$first" ]`; `[ "$(cat "$STUB_CWD")" != "$cwd1" ]`.

- [ ] **Step 2: Run to verify they fail.** `system/scripts/test.sh system/tests/connector.bats`. Expected: every test fails on `lib_connector.sh: No such file`.

- [ ] **Step 3: Implement.** `system/scripts/lib_connector.sh`:

```bash
# shellcheck shell=bash
# One confined connector session (connector runner spec §2). Source from VAULT_ROOT after lib_confine.sh.
# Every `claude` flag a connector session gets is in this file. Set before calling:
#   CONNECTOR_SERVER   the connector's name in `claude mcp list`; the other listed servers are denied by name
#   CONNECTOR_PREFIX   the server's tool prefix, e.g. mcp__claude_ai_Gmail
#   CONNECTOR_TOOL     the one allowed tool
#   CONNECTOR_OTHERS   the server's other tools, bare names (an array)
#   CONNECTOR_TIMEOUT  seconds for the session
#   CONNECTOR_TURNS    --max-turns
#   CONNECTOR_SCHEMA   optional: a file whose JSON schema the reply must match (--json-schema)

# connector_run <prompt> <work dir>: run one session in a fresh directory under <work dir>, leaving <work dir>/out.jsonl
# and <work dir>/claude.err. Returns 127 (no claude) or 1 (a refused allow rule) with CONNECTOR_REASON set and nothing
# run; otherwise returns 0 with CONNECTOR_RC the session's exit (124 or 137 after the timeout). The server list is
# read once per process; a caller running several sessions pays for `claude mcp list` once.
connector_run() {
  local prompt="$1" work="$2" claude_bin="${CLAUDE_BIN:-claude}" sdir t
  local -a others=() schema=()
  CONNECTOR_REASON="" CONNECTOR_RC=0
  if ! command -v "$claude_bin" > /dev/null 2>&1; then
    CONNECTOR_REASON="claude not found ($claude_bin)"
    return 127
  fi
  [[ -n "${CONFINE_SETTINGS:-}" ]] || confine_settings "$CONNECTOR_SERVER" "$work"
  for t in "${CONNECTOR_OTHERS[@]}"; do others+=("${CONNECTOR_PREFIX}__$t"); done
  if ! confine_deny --strict "$CONNECTOR_PREFIX" "$CONNECTOR_TOOL" "${others[@]}"; then
    CONNECTOR_REASON="$CONFINE_ERROR"
    return 1
  fi
  [[ -z "${CONNECTOR_SCHEMA:-}" ]] || schema=(--json-schema "$(cat "$CONNECTOR_SCHEMA")")
  # A fresh working directory per session, under the caller's work directory so its trap removes a session a stopped
  # unit leaves behind (#40). The prompt comes first: --allowedTools and --disallowedTools take variable-length lists
  # and stay last.
  sdir="$(mktemp -d -p "$work" session.XXXXXX)"
  (cd "$sdir" && FOUNDRY_HEADLESS=1 timeout -k 10 "$CONNECTOR_TIMEOUT" "$claude_bin" -p "$prompt" \
    --settings "$CONFINE_SETTINGS" --disable-slash-commands --no-session-persistence --permission-mode dontAsk \
    --output-format stream-json --verbose "${schema[@]}" --max-turns "$CONNECTOR_TURNS" --max-budget-usd 1 \
    --allowedTools "$CONNECTOR_TOOL" --disallowedTools "${CONFINE_DENY[@]}" \
    < /dev/null > "$work/out.jsonl" 2> "$work/claude.err") || CONNECTOR_RC=$?
  rm -rf -- "$sdir"
  return 0
}
```

- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/connector.bats`. Expected: PASS. Also `shellcheck -x system/scripts/lib_connector.sh` clean (the gate lints first).

- [ ] **Step 5: Commit.** `.scratch/msg-1.txt`: `feat(connector): lib_connector.sh runs one confined connector session`.

### Task 2: `connector_outcome`

**Files:**
- Modify: `system/scripts/lib_connector.sh`
- Test: `system/tests/connector.bats`

**Interfaces:**
- Produces: `connector_outcome <checker exit> <work dir>`; reads `CONNECTOR_RC`, `CONNECTOR_TIMEOUT`, `<work>/check.err` (the checker's stderr) and `<work>/claude.err`; sets `CONNECTOR_EXIT` and `CONNECTOR_REASON`.

- [ ] **Step 1: Write the failing test** below the Task 1 tests: "connector_outcome: the checker's verdict wins, a timeout is 4, claude's stderr is appended". With `prepare`, `printf 'triage: no Gmail connector\n' > "$work/check.err"`, `printf 'unknown option --foo\n' > "$work/claude.err"`, then a table of cases, each as `CONNECTOR_RC=<rc> connector_outcome <prc> "$work"` followed by `[ "$CONNECTOR_EXIT" -eq <exit> ]` and a reason check:
  - `(0, 0)` → 0; `(0, 2)` → 0; `(0, 124)` → 0.
  - `(7, 124)` → 7, reason `no Gmail connector`.
  - `(6, 124)` → 4, reason `timed out after 30s`; `(6, 137)` → 4.
  - `(3, 0)` → 3, reason `no Gmail connector` (prefix stripped).
  - `(3, 2)` → 3, reason `no Gmail connector; claude exited 2: unknown option --foo`.
  - An empty `check.err` with `(1, 0)` → 1, reason empty.

- [ ] **Step 2: Run to verify it fails.** Expected: `connector_outcome: command not found`.

- [ ] **Step 3: Implement**, appended to `lib_connector.sh`:

```bash
# connector_outcome <checker exit> <work dir>: set CONNECTOR_EXIT and CONNECTOR_REASON from the checker's verdict and
# the session's exit. The checker's verdict wins: 0 is success whatever claude's exit (the checker saw the whole result,
# or the post or ticket it confirms exists), and 7 (an unexpected tool) stands. Another failure after a timed-out session
# is 4; after any other failed session it keeps the checker's code and names claude's exit and stderr, so a refused
# flag does not read as a missing connector. The checker's stderr is <work dir>/check.err, its first line prefixed
# "<name>: ".
connector_outcome() {
  local prc="$1" work="$2"
  CONNECTOR_EXIT="$prc" CONNECTOR_REASON="$(sed -E 's/^[a-z_]+: //' "$work/check.err" 2>/dev/null | head -n 1)"
  (( prc != 0 && prc != 7 )) || return 0
  if (( CONNECTOR_RC == 124 || CONNECTOR_RC == 137 )); then
    CONNECTOR_EXIT=4 CONNECTOR_REASON="timed out after ${CONNECTOR_TIMEOUT}s"
  elif (( CONNECTOR_RC != 0 )); then
    CONNECTOR_REASON="$CONNECTOR_REASON; claude exited $CONNECTOR_RC: $(head -c 200 "$work/claude.err" 2>/dev/null)"
  fi
}
```

- [ ] **Step 4: Run the suite.** Expected: PASS.

- [ ] **Step 5: Commit.** `.scratch/msg-2.txt`: `feat(connector): connector_outcome maps the checker's and the session's exits to one code`.

### Task 3: `calendar_fetch.sh` on the runner, strict

**Files:**
- Modify: `system/scripts/calendar_fetch.sh:44-60`, `system/scripts/calendar_fetch.sh:62-71`
- Test: `system/tests/calendar.bats`

- [ ] **Step 1: Write the failing test** beside the deny-list test: "a rule allowing the whole Calendar server is refused (strict)": write `$HOME/.claude/settings.json` with `{"permissions":{"allow":["mcp__claude_ai_Google_Calendar"]}}`; `run "$CF" "$DAY"`; `[ "$status" -eq 1 ]`; `[[ "$output" == *"allows every tool on mcp__claude_ai_Google_Calendar"* ]]`; `[ ! -e "$STUB_ARGS" ]`.

- [ ] **Step 2: Run to verify it fails.** `system/scripts/test.sh system/tests/calendar.bats -f strict`. Expected: FAIL (today the fetch runs; a whole-server rule is skipped, not refused).

- [ ] **Step 3: Implement.** Source `lib_connector.sh` after `lib_confine.sh`. Replace the `claude_bin` check, `confine_deny`, `confine_settings`, the `(cd "$work" && … claude …)` block and the outcome lines with:

```bash
CONNECTOR_SERVER="$SERVER_NAME" CONNECTOR_PREFIX="$SERVER_PREFIX" CONNECTOR_TOOL="$TOOL" CONNECTOR_OTHERS=("${CALENDAR_OTHERS[@]}")
CONNECTOR_TIMEOUT="${CALENDAR_TIMEOUT:-150}" CONNECTOR_TURNS=15 CONNECTOR_SCHEMA="$VAULT_ROOT/system/scripts/calendar_schema.json"
# (the prompt stays as it is)
connector_run "$prompt" "$work" || finish $? "$CONNECTOR_REASON"
# The tool-use check runs on every session, a timed-out one included.
prc=0
system/scripts/calendar_tsv.py "$day" --summary "$summary" < "$work/out.jsonl" > "$work/events.tsv" 2> "$work/check.err" || prc=$?
connector_outcome "$prc" "$work"
if (( prc == 7 )); then
  printf -- '- %s [calendar] calendar fetch for %s: %s\n' "$(date +%H:%M:%S)" "$day" "$CONNECTOR_REASON" >> "system/logs/alerts_$(date +%F).md"
fi
(( CONNECTOR_EXIT == 0 )) || finish "$CONNECTOR_EXIT" "$CONNECTOR_REASON"
cat "$work/events.tsv"
finish 0 ""
```

Delete the now-unused `claude_bin` and the "prompt comes first" comment (it lives in the library). The header comment's "confined by lib_confine.sh" becomes "run by lib_connector.sh".

- [ ] **Step 4: Run the suites.** `system/scripts/test.sh system/tests/calendar.bats`; `system/scripts/test.sh system/tests/connector.bats`. Expected: PASS. The existing "no claude" test (exit 127) and the cwd tests pass unchanged: the session directory is under `$work`, under `/tmp`.

- [ ] **Step 5: Commit.** `.scratch/msg-3.txt`: `refactor(calendar): the fetch runs on lib_connector.sh and confines strictly`.

### Task 4: `meetings_fetch.sh`

**Files:**
- Modify: `system/scripts/meetings_fetch.sh:39-41`, `system/scripts/meetings_fetch.sh:62-104`
- Test: `system/tests/meetings.bats` (unchanged; it already checks two distinct cwds, the #40 cleanup and exit 127)

- [ ] **Step 1: Run the suite first** to record it green: `system/scripts/test.sh system/tests/meetings.bats`.

- [ ] **Step 2: Implement.** Source `lib_connector.sh`. Set once after the `--check` parsing: `CONNECTOR_SERVER="$SERVER_NAME" CONNECTOR_PREFIX="$PREFIX" CONNECTOR_TIMEOUT="${MEETINGS_TIMEOUT:-150}" CONNECTOR_TURNS=10`. Delete the `claude_bin` block (lines 62-67), the `confine_settings` call and the `sdir` variable and its trap part (`trap 'rm -rf -- "$work"' EXIT`). In `session()`, set `CONNECTOR_TOOL="$tool"` and `CONNECTOR_OTHERS=()` filled with the bare names of `DRIVE_TOOLS` other than the step's tool (`[[ "$t" == "${tool#"${PREFIX}__"}" ]] || CONNECTOR_OTHERS+=("$t")`), then:

```bash
  local rrc=0
  connector_run "$prompt" "$work" || rrc=$?
  if (( rrc != 0 )); then
    logline "$step" "${id:-search}" "$rrc" "$CONNECTOR_REASON"
    echo "meetings_fetch: $CONNECTOR_REASON" >&2
    return "$rrc"
  fi
  # The tool-use check runs on every session, a timed-out one included.
  system/scripts/meetings_extract.py "${args[@]}" < "$work/out.jsonl" > "$work/$step.out" 2> "$work/check.err" || prc=$?
  connector_outcome "$prc" "$work"
  prc="$CONNECTOR_EXIT" reason="$CONNECTOR_REASON"
  logline "$step" "${id:-search}" "$prc" "$reason"
```

The `case "$prc"` alert block and `return "$prc"` stay. A search that returns 127 now exits through the existing `rc != 0` branch after `session search` (it reads the reason from the log line), so the top-level 127 message is the same text.

- [ ] **Step 3: Run the suite.** Expected: PASS, including "a fetch stopped mid-session removes that session's /tmp directory (#40)" and "exit 127" cases.

- [ ] **Step 4: Commit.** `.scratch/msg-4.txt`: `refactor(meetings): the Drive sessions run on lib_connector.sh`.

### Task 5: `jira_fetch.sh`

**Files:**
- Modify: `system/scripts/jira_fetch.sh:60-89`
- Test: `system/tests/handoffs.bats` (unchanged)

- [ ] **Step 1: Run the suite first:** `system/scripts/test.sh system/tests/handoffs.bats`.
- [ ] **Step 2: Implement.** Source `lib_connector.sh`; `CONNECTOR_SERVER="claude.ai Atlassian" CONNECTOR_PREFIX="$PREFIX" CONNECTOR_TOOL="$TOOL" CONNECTOR_OTHERS=("${OTHER_TOOLS[@]}") CONNECTOR_TIMEOUT="${JIRA_TIMEOUT:-300}" CONNECTOR_TURNS=12`; `trap 'rm -rf -- "$work"' EXIT`; then after the prompt:

```bash
connector_run "$prompt" "$work" || fail $? "$CONNECTOR_REASON"
# The tool-use check runs on every session, a timed-out one included.
prc=0
system/scripts/jira_handoffs.py extract < "$work/out.jsonl" > "$work/lines.md" 2> "$work/check.err" || prc=$?
connector_outcome "$prc" "$work"
(( CONNECTOR_EXIT == 0 )) || fail "$CONNECTOR_EXIT" "$CONNECTOR_REASON"
```

Delete `claude_bin`, `others`, `sdir`, `confine_settings`, `confine_deny` and the inline block.
- [ ] **Step 3: Run the suite.** Expected: PASS.
- [ ] **Step 4: Commit.** `.scratch/msg-5.txt`: `refactor(handoffs): the Jira fetch runs on lib_connector.sh`.

### Task 6: `triage_fetch.sh`

**Files:**
- Modify: `system/scripts/triage_fetch.sh:69-99`
- Test: `system/tests/triage.bats` (unchanged)

- [ ] **Step 1: Run the suite first:** `system/scripts/test.sh system/tests/triage.bats`.
- [ ] **Step 2: Implement** as Task 5, with `CONNECTOR_SERVER="claude.ai Gmail"`, `CONNECTOR_TIMEOUT="${TRIAGE_TIMEOUT:-300}"`, `CONNECTOR_TURNS=12`, the checker `system/scripts/triage.py extract "$q" < "$work/out.jsonl" > "$work/found.json" 2> "$work/check.err"`, and `(( CONNECTOR_EXIT == 0 )) || fail "$CONNECTOR_EXIT" "$CONNECTOR_REASON"`. The `connector_run` call goes where the `claude_bin` check was, after `q` and `owners` are built.
- [ ] **Step 3: Run the suite.** Expected: PASS.
- [ ] **Step 4: Commit.** `.scratch/msg-6.txt`: `refactor(triage): the inbox search runs on lib_connector.sh`.

### Task 7: `notify.sh`

**Files:**
- Modify: `system/scripts/notify.sh:78-109`
- Test: `system/tests/notify.bats` (unchanged)

- [ ] **Step 1: Run the suite first:** `system/scripts/test.sh system/tests/notify.bats`.
- [ ] **Step 2: Implement.** `CONNECTOR_SERVER="$connector" CONNECTOR_PREFIX="$PREFIX" CONNECTOR_TOOL="$TOOL" CONNECTOR_OTHERS=("${OTHER_TOOLS[@]}") CONNECTOR_TIMEOUT="${NOTIFY_TIMEOUT:-120}" CONNECTOR_TURNS=6` (after `TOOL` and `PREFIX` are read from `notify.py tool`); `connector_run "$prompt" "$work" || fail $? "$CONNECTOR_REASON"`; the checker `system/scripts/notify.py check "$work/collected.json" < "$work/out.jsonl" > "$work/drift.txt" 2> "$work/check.err" || prc=$?`; `connector_outcome "$prc" "$work"`; then the existing `if (( prc == 7 ))` hold block, `(( CONNECTOR_EXIT == 0 )) || fail "$CONNECTOR_EXIT" "$CONNECTOR_REASON"`, and the commit and drift lines unchanged.
- [ ] **Step 3: Run the suite.** Expected: PASS (a checker pass still commits the cursor whatever the session's exit).
- [ ] **Step 4: Commit.** `.scratch/msg-7.txt`: `refactor(notify): the Slack post runs on lib_connector.sh`.

### Task 8: `rca_file.sh`

**Files:**
- Modify: `system/scripts/rca_file.sh:81-113`
- Test: `system/tests/rca.bats`

- [ ] **Step 1: Write the failing test** beside the exit-127 or refused-rule test: "a refused allow rule leaves no .attempt file": write `$HOME/.claude/settings.json` with `{"permissions":{"allow":["mcp__claude_ai_Atlassian"]}}`; `run "$RF" work <stem>` (the fixture the suite's other tests use); `[ "$status" -eq 1 ]`; `[ ! -e system/logs/rca/work-<stem>.attempt ]`.
- [ ] **Step 2: Run to verify it fails.** Expected: today `confine_deny` runs before `touch "$attempt"`, so this passes already; keep it as the pin and move on (it fails if Step 3 forgets the removal).
- [ ] **Step 3: Implement.** `CONNECTOR_SERVER="claude.ai Atlassian" CONNECTOR_PREFIX="$PREFIX" CONNECTOR_TOOL="$TOOL" CONNECTOR_OTHERS=("${OTHER_TOOLS[@]}") CONNECTOR_TIMEOUT="${RCA_TIMEOUT:-300}" CONNECTOR_TURNS=8`; keep `mkdir -p "${attempt%/*}"; touch "$attempt"` before the session, then:

```bash
rrc=0
connector_run "$prompt" "$work" || rrc=$?
if (( rrc != 0 )); then
  rm -f -- "$attempt"  # nothing ran
  fail "$rrc" "$CONNECTOR_REASON"
fi
# The tool-use check runs on every session, a timed-out one included: a ticket may exist even when claude failed.
prc=0
key="$(system/scripts/rca.py extract "$partition" "$stem" < "$work/out.jsonl" 2> "$work/check.err")" || prc=$?
connector_outcome "$prc" "$work"
if (( CONNECTOR_EXIT != 0 )); then
  reason="$CONNECTOR_REASON"
  if system/scripts/rca.py called < "$work/out.jsonl"; then
    reason="$reason; the create tool was called, so check Jira before deleting $attempt"
  else
    rm -f -- "$attempt"
  fi
  fail "$CONNECTOR_EXIT" "$reason"
fi
```

- [ ] **Step 4: Run the suite.** `system/scripts/test.sh system/tests/rca.bats`. Expected: PASS.
- [ ] **Step 5: Commit.** `.scratch/msg-8.txt`: `refactor(rca): the filing session runs on lib_connector.sh`.

### Task 9: The one-file rule and the manual

**Files:**
- Modify: `FOUNDRY.md` (Headless isolation paragraph, line 303; Development acceptance paragraph, line 351)
- Test: `system/tests/scripts.bats` (beside the `test.sh` test), `system/tests/commands.bats` (beside the FOUNDRY.md structure checks)

- [ ] **Step 1: Write the failing tests.** `scripts.bats`: "every claude flag for a connector session lives in lib_connector.sh": `run grep -l -e '--permission-mode' -e '--disallowedTools' system/scripts/*.sh`; `[ "$output" = "$(printf 'system/scripts/lib_connector.sh\nsystem/scripts/run_headless.sh')" ]`. `commands.bats`: `grep -qF 'lib_connector.sh' FOUNDRY.md`.
- [ ] **Step 2: Run to verify they fail.** The `scripts.bats` test passes once Tasks 3 to 8 are done and fails on any earlier state; the `commands.bats` grep fails.
- [ ] **Step 3: Write the paragraphs.** Line 303: replace "`run_headless.sh` is the only way automation calls `claude`" with "`run_headless.sh` runs the vault's own commands and `system/scripts/lib_connector.sh` runs every connector session (one connector tool allowed, every other tool denied, `dontAsk`, a fresh directory, a timeout); no other script calls `claude`". Line 351, after the live-acceptance sentence: "After a `claude` version change, one `system/scripts/calendar_fetch.sh` run from a throwaway clone proves the connector flags; `lib_connector.sh` is the one place they live."
- [ ] **Step 4: Run the suites and the gate.** `system/scripts/test.sh system/tests/scripts.bats`; `system/scripts/test.sh system/tests/commands.bats`; then `system/scripts/verify_setup.sh`. Expected: PASS, no `FAIL` line.
- [ ] **Step 5: Commit.** `.scratch/msg-9.txt`: `docs(connector): one file holds the connector flags; the manual says so`.

### Task 10: The real-claude check

- [ ] **Step 1:** From a throwaway clone of the branch under `.scratch/` with `system/config.md` copied from `config.example.md` (timezone set), run `system/scripts/calendar_fetch.sh "$(date +%F)"` outside the sandbox. Expected: exit 0 and TSV rows (or an empty result with exit 0), with `system/logs/calendar_fetch-<month>.jsonl` showing `exit: 0` and the tool list `["ToolSearch", "mcp__claude_ai_Google_Calendar__list_events", …]`. Exit 3 means the clone's `claude` has no Calendar connector, which still proves the flag list was accepted (the session ran); exit 1 with "claude exited 1: unknown option" means a flag `claude` refuses: fix the library and re-run.
- [ ] **Step 2:** Delete the clone. Record the exit and the log line in the PR body under Checks.
