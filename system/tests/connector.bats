#!/usr/bin/env bats
# lib_connector.sh (connector runner spec §2): the one confined claude invocation and the one outcome rule.
load helpers

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_calendar"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude"
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_CWD="$BATS_TEST_TMPDIR/cwd" STUB_ENV="$BATS_TEST_TMPDIR/env"
}

# prepare: source the libraries and set the runner's inputs for a calendar-shaped session.
# shellcheck disable=SC2034  # the CONNECTOR_* variables are the library's inputs
prepare() {
  source system/scripts/lib_confine.sh
  source system/scripts/lib_connector.sh
  CONNECTOR_SERVER="claude.ai Google Calendar" CONNECTOR_PREFIX=mcp__claude_ai_Google_Calendar
  CONNECTOR_TOOL=mcp__claude_ai_Google_Calendar__list_events CONNECTOR_OTHERS=(create_event get_event)
  CONNECTOR_TIMEOUT=30 CONNECTOR_TURNS=9
  work="$(mktemp -d -p "$BATS_TEST_TMPDIR")"
}

arg_after() { awk -v f="$1" 'p { print; exit } $0 == f { p = 1 }' "$STUB_ARGS"; }
deny_list() { awk '$0 == "--disallowedTools" { p = 1; next } p' "$STUB_ARGS"; }

@test "connector_run passes the prompt first, the flags, and the tool lists last" {
  prepare
  STUB_STDIN="$BATS_TEST_TMPDIR/stdin" connector_run "say hi" "$work"
  [ "$CONNECTOR_RC" -eq 0 ]
  [ "$(cat "$BATS_TEST_TMPDIR/stdin")" = /dev/null ]
  [ "$(sed -n 1p "$STUB_ARGS")" = -p ]
  [ "$(sed -n 2p "$STUB_ARGS")" = "say hi" ]
  [ "$(arg_after --permission-mode)" = dontAsk ]
  [ "$(arg_after --output-format)" = stream-json ]
  [ "$(arg_after --max-turns)" = 9 ]
  [ "$(arg_after --max-budget-usd)" = 1 ]
  [ "$(arg_after --allowedTools)" = mcp__claude_ai_Google_Calendar__list_events ]
  [ "$(arg_after --settings | jq -c .disableAllHooks)" = true ]
  grep -qx -- --disable-slash-commands "$STUB_ARGS"
  grep -qx -- --no-session-persistence "$STUB_ARGS"
  grep -qx -- --verbose "$STUB_ARGS"
  run grep -qx -- --json-schema "$STUB_ARGS"
  [ "$status" -eq 1 ]
  grep -qx Bash <<< "$(deny_list)"
  grep -qx mcp__claude_ai_Google_Calendar__create_event <<< "$(deny_list)"
  grep -qx mcp__claude_ai_Google_Calendar__get_event <<< "$(deny_list)"
  run grep -qx mcp__claude_ai_Google_Calendar__list_events <<< "$(deny_list)"
  [ "$status" -eq 1 ]
  [ "$(cat "$STUB_ENV")" = 1 ]
  [[ "$(cat "$STUB_CWD")" == "$work"/* ]]
  [ ! -e "$(cat "$STUB_CWD")" ]
  [ -e "$work/out.jsonl" ]
  [ -e "$work/claude.err" ]
}

@test "connector_run passes --json-schema only when CONNECTOR_SCHEMA is set" {
  prepare
  printf '{"type":"object"}' > "$work/schema.json"
  CONNECTOR_SCHEMA="$work/schema.json" connector_run p "$work"
  [ "$(arg_after --json-schema)" = '{"type":"object"}' ]
}

@test "connector_run records the session's exit and the timeout's" {
  prepare
  STUB_RC=6 connector_run p "$work"
  [ "$CONNECTOR_RC" -eq 6 ]
  CONNECTOR_TIMEOUT=1 STUB_SLEEP=5 connector_run p "$work"
  [ "$CONNECTOR_RC" -eq 124 ]
}

@test "connector_run returns 127 without claude and 1 on a refused rule, running nothing" {
  prepare
  run_rc=0
  CLAUDE_BIN="$BATS_TEST_TMPDIR/none" connector_run p "$work" || run_rc=$?
  [ "$run_rc" -eq 127 ]
  [[ "$CONNECTOR_REASON" == "claude not found"* ]]
  [ ! -e "$STUB_ARGS" ]
  printf '{"permissions":{"allow":["mcp__claude_ai_Google_Calendar"]}}' > "$HOME/.claude/settings.json"
  run_rc=0
  connector_run p "$work" || run_rc=$?
  [ "$run_rc" -eq 1 ]
  [[ "$CONNECTOR_REASON" == *"allows every tool on mcp__claude_ai_Google_Calendar"* ]]
  [ ! -e "$STUB_ARGS" ]
}

@test "connector_run runs nothing when no session directory can be made" {
  need_non_root
  prepare
  chmod a-w "$work"
  run_rc=0
  connector_run p "$work" || run_rc=$?
  chmod u+w "$work"
  [ "$run_rc" -eq 1 ]
  [[ "$CONNECTOR_REASON" == *"session directory"* ]]
  [ ! -e "$STUB_ARGS" ]
}

@test "connector_run runs nothing when the session settings cannot be built (#122)" {
  prepare
  mkdir "$BATS_TEST_TMPDIR/bin"
  printf '#!/bin/sh\nexit 5\n' > "$BATS_TEST_TMPDIR/bin/jq"
  chmod +x "$BATS_TEST_TMPDIR/bin/jq"
  run_rc=0
  PATH="$BATS_TEST_TMPDIR/bin:$PATH" connector_run p "$work" || run_rc=$?
  [ "$run_rc" -eq 1 ]
  [[ "$CONNECTOR_REASON" == *"session settings"* ]]
  [ -z "$CONFINE_SETTINGS" ]
  [ ! -e "$STUB_ARGS" ]
}

@test "two sessions in one process list the servers once and get two directories" {
  prepare
  STUB_MCP_LIST=$'claude.ai Google Calendar: x - ok\nclaude.ai Gmail: y - ok' connector_run p "$work"
  first="$CONFINE_SETTINGS"
  [[ "$first" == *'"claude.ai Gmail"'* ]]
  cwd1="$(cat "$STUB_CWD")"
  STUB_MCP_FAIL=1 connector_run p "$work"
  [ "$CONFINE_SETTINGS" = "$first" ]
  [ "$(cat "$STUB_CWD")" != "$cwd1" ]
}

# outcome <checker exit> <session exit> <expected exit> <expected reason>
outcome() {
  CONNECTOR_RC="$2" connector_outcome "$1" "$work"
  [ "$CONNECTOR_EXIT" -eq "$3" ]
  [ "$CONNECTOR_REASON" = "$4" ]
}

@test "connector_outcome: the checker's verdict wins, a timeout is 4, claude's stderr is appended" {
  prepare
  printf 'triage: no Gmail connector\n' > "$work/check.err"
  printf 'unknown option --foo\n' > "$work/claude.err"
  outcome 0 0 0 "no Gmail connector"
  outcome 0 2 0 "no Gmail connector"
  outcome 0 124 0 "no Gmail connector"
  outcome 7 124 7 "no Gmail connector"
  outcome 6 124 4 "timed out after 30s"
  outcome 6 137 4 "timed out after 30s"
  outcome 3 0 3 "no Gmail connector"
  outcome 3 2 3 "no Gmail connector; claude exited 2: unknown option --foo"
  printf 'Error: one\nError: two\n' > "$work/claude.err"
  outcome 3 2 3 "no Gmail connector; claude exited 2: Error: one Error: two"   # one line for the alert (#122)
  : > "$work/check.err"
  outcome 1 0 1 ""
}

@test "connector_outcome reads the first line of a long checker stderr (a traceback) without dying" {
  prepare
  printf 'triage: boom\n' > "$work/check.err"
  head -c 70000 /dev/zero | tr '\0' x >> "$work/check.err"
  # Under the connector scripts' set -euo pipefail, a SIGPIPE inside the library would kill the script silently.
  run bash -euo pipefail -c 'source system/scripts/lib_confine.sh; source system/scripts/lib_connector.sh
    CONNECTOR_RC=0 CONNECTOR_TIMEOUT=30 connector_outcome 3 "$1"; printf "%s %s" "$CONNECTOR_EXIT" "$CONNECTOR_REASON"' _ "$work"
  [ "$status" -eq 0 ]
  [ "$output" = "3 boom" ]
}

@test "connector_classify gives every failure one class (connector health spec §2)" {
  prepare
  : > "$work/claude.err"
  cls() { CONNECTOR_RC="${3:-0}"; connector_classify "$1" "$2" "$work"; [ "$CONNECTOR_CLASS" = "$4" ]; }
  cls 0 "" 0 ""
  cls 3 "no Atlassian connector reachable" 0 auth
  cls 6 'the connector returned an error: "401 Unauthorized"' 0 auth
  cls 6 "the connector returned an error: token expired, reconnect" 0 auth
  cls 6 "the connector returned an error: 500 Internal Server Error" 0 connector
  cls 4 "timed out after 30s" 124 timeout
  cls 127 "claude not found (claude)" 0 claude
  cls 7 "the session used an unexpected tool: Bash" 0 other
  cls 1 "claude returned an error result" 1 other
  printf 'Invalid API key · Please run /login\n' > "$work/claude.err"
  cls 1 "claude returned an error result" 1 claude
}
