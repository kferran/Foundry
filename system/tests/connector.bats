#!/usr/bin/env bats
# lib_connector.sh (connector runner spec §2): the one confined claude invocation and the one outcome rule.
load helpers

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_connector"
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

# --- lib_fetch.sh (F1 spec §3.2) and the connector stub (§3.4) ---

# fetch_lib: lib_fetch.sh after lib_connector.sh, with a triage-shaped script's settings.
# shellcheck disable=SC2034  # the FETCH_* variables are the library's inputs
fetch_lib() {
  source system/scripts/lib_confine.sh
  source system/scripts/lib_connector.sh
  source system/scripts/lib_fetch.sh
  mkdir -p system/logs
  FETCH_NAME=triage_fetch FETCH_TAG=triage FETCH_LOG=system/logs/f.jsonl FETCH_LABEL="Inbox triage" FETCH_ALERTS="1 3"
  FETCH_FIELDS='{"items": 0, "source": "mail"}'
  ALERTS="system/logs/alerts_$(date +%F).md"
}

@test "logline writes {time, exit, reason} with FETCH_FIELDS and the object merged in, the object last" {
  fetch_lib
  logline 0 "" '{"items": 3}'
  [ "$(jq -c 'keys_unsorted' system/logs/f.jsonl)" = '["time","exit","reason","items","source"]' ]
  [ "$(jq -c '[.exit, .reason, .items, .source]' system/logs/f.jsonl)" = '[0,"",3,"mail"]' ]
}

@test "alert_once writes its [FETCH_TAG] key once a day" {
  fetch_lib
  alert_once "Inbox triage failed (exit 3):" first
  alert_once "Inbox triage failed (exit 3):" second
  [ "$(wc -l < "$ALERTS")" -eq 1 ]
  grep -qE '^- [0-9]{2}:[0-9]{2}:[0-9]{2} \[triage\] Inbox triage failed \(exit 3\): first$' "$ALERTS"
}

@test "fail leads the reason with its class, logs it, alerts an exit in FETCH_ALERTS, prints it and exits" {
  fetch_lib
  run fail 3 "no Gmail connector reachable"
  [ "$status" -eq 3 ]
  [ "$output" = "triage_fetch: auth: no Gmail connector reachable" ]
  [ "$(jq -c '[.exit, .reason, .items]' system/logs/f.jsonl)" = '[3,"auth: no Gmail connector reachable",0]' ]
  grep -qF '[triage] Inbox triage failed (exit 3): auth: no Gmail connector reachable' "$ALERTS"
  run fail 2 x
  [ "$status" -eq 2 ]
  [ "$output" = "triage_fetch: x" ]
  [ "$(tail -n 1 system/logs/f.jsonl | jq -r .reason)" = x ]
  [ "$(wc -l < "$ALERTS")" -eq 1 ]
}

@test "skip logs the skipped reason with exit 0 and exits 0" {
  fetch_lib
  run skip "outside hours"
  [ "$status" -eq 0 ]
  [ "$(jq -c '[.exit, .reason, .items]' system/logs/f.jsonl)" = '[0,"skipped: outside hours",0]' ]
  [ ! -e "$ALERTS" ]
}

@test "fetch_check_arg sets check, or exits 2 with the usage line" {
  fetch_lib
  fetch_check_arg
  [ "$check" = 0 ]
  fetch_check_arg --check
  [ "$check" = 1 ]
  run fetch_check_arg --bogus
  [ "$status" -eq 2 ]
  [ "$output" = "usage: triage_fetch.sh [--check]" ]
  run fetch_check_arg --check --check
  [ "$status" -eq 2 ]
}

@test "fetch_reason leads a reason with its class once: a reason that already has one keeps it (#302)" {
  fetch_lib
  fetch_reason 1 "calendar_fetch failed"
  [ "$FETCH_REASON" = "other: calendar_fetch failed" ]
  fetch_reason 1 "other: calendar_fetch failed"
  [ "$FETCH_REASON" = "other: calendar_fetch failed" ]
  fetch_reason 1 "auth: Google login expired"
  [ "$FETCH_REASON" = "auth: Google login expired" ]
}

@test "fetch_workdir leaves no directory once its shell exits" {
  run bash -c 'source system/scripts/lib_fetch.sh; fetch_workdir; [[ -d "$work" ]] || exit 1; echo "$work"'
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  [ ! -e "$output" ]
}

@test "fetch_others lists a server's tools less the allowed one; each table holds its tool" {
  fetch_lib
  CONNECTOR_PREFIX=mcp__claude_ai_Slack CONNECTOR_TOOL=mcp__claude_ai_Slack__slack_send_message
  fetch_others "${SLACK_TOOLS[@]}"
  [ "${#CONNECTOR_OTHERS[@]}" -eq $(( ${#SLACK_TOOLS[@]} - 1 )) ]
  [[ " ${CONNECTOR_OTHERS[*]} " != *" slack_send_message "* ]]
  [[ " ${CONNECTOR_OTHERS[*]} " == *" slack_search_public_and_private "* ]]
  [[ " ${GMAIL_TOOLS[*]} " == *" search_threads "* ]]
  [[ " ${DRIVE_TOOLS[*]} " == *" search_files read_file_content "* ]]
  [[ " ${CALENDAR_TOOLS[*]} " == *" list_events "* ]]
}

@test "the connector stub prints a Slack, a Gmail or a Calendar session's own stream, else STUB_STREAM" {
  S="$REPO/system/tests/stub_claude_connector"
  for k in SLACK MAIL CAL; do printf '{"kind":"%s"}\n' "$k" > "$BATS_TEST_TMPDIR/$k.jsonl"; done
  export STUB_SLACK_STREAM="$BATS_TEST_TMPDIR/SLACK.jsonl" STUB_MAIL_STREAM="$BATS_TEST_TMPDIR/MAIL.jsonl"
  export STUB_CAL_STREAM="$BATS_TEST_TMPDIR/CAL.jsonl" STUB_SLACK_ARGS="$BATS_TEST_TMPDIR/slack.args"
  run "$S" -p hi --allowedTools mcp__claude_ai_Slack__slack_search_public_and_private
  [ "$output" = '{"kind":"SLACK"}' ]
  [ "$(sed -n 2p "$STUB_SLACK_ARGS")" = hi ]
  run "$S" -p hi --allowedTools mcp__claude_ai_Gmail__search_threads
  [ "$output" = '{"kind":"MAIL"}' ]
  run "$S" -p hi --allowedTools mcp__claude_ai_Google_Calendar__list_events
  [ "$output" = '{"kind":"CAL"}' ]
  [ ! -e "$STUB_ARGS" ]
  printf '{"calendar":1}\n' > "$BATS_TEST_TMPDIR/s.jsonl"
  STUB_MAIL_STREAM="" STUB_STREAM="$BATS_TEST_TMPDIR/s.jsonl" STUB_RC=5 run "$S" -p hi --allowedTools mcp__claude_ai_Gmail__search_threads
  [ "$status" -eq 5 ]
  [ "$output" = '{"calendar":1}' ]
  [ "$(sed -n 2p "$STUB_ARGS")" = hi ]
}

@test "the connector stub's meetings mode prints read-<id>.jsonl for the prompt's fileId, else search.jsonl" {
  S="$REPO/system/tests/stub_claude_connector"
  export STUB_STREAMS="$BATS_TEST_TMPDIR/streams"
  mkdir -p "$STUB_STREAMS"
  echo search > "$STUB_STREAMS/search.jsonl"
  echo read > "$STUB_STREAMS/read-FAKE-1.jsonl"
  run "$S" -p 'Then call the read tool with fileId "FAKE-1".'
  [ "$output" = read ]
  run "$S" -p 'Then search.'
  [ "$output" = search ]
  [ "$(grep -c -- '^--end--$' "$STUB_ARGS")" -eq 2 ]
  [ "$(wc -l < "$STUB_CWD")" -eq 2 ]
}

@test "the connector stub moves STUB_STREAM.next over STUB_STREAM after one session" {
  S="$REPO/system/tests/stub_claude_connector"
  export STUB_STREAM="$BATS_TEST_TMPDIR/s.jsonl"
  echo first > "$STUB_STREAM"
  echo second > "$STUB_STREAM.next"
  run "$S" -p one
  [ "$output" = first ]
  run "$S" -p two
  [ "$output" = second ]
  [ ! -e "$STUB_STREAM.next" ]
}

@test "the connector stub's mcp list prints the Calendar line by default, STUB_MCP_LIST when set, and fails on STUB_MCP_FAIL" {
  S="$REPO/system/tests/stub_claude_connector"
  run "$S" mcp list
  [ "$status" -eq 0 ]
  [ "${lines[1]}" = "claude.ai Google Calendar: https://calendar.example/mcp - ok Connected" ]
  STUB_MCP_LIST="claude.ai Google Drive: https://drive.example/mcp - ok Connected" run "$S" mcp list
  [ "${lines[1]}" = "claude.ai Google Drive: https://drive.example/mcp - ok Connected" ]
  STUB_MCP_PROBE="$BATS_TEST_TMPDIR/probe" STUB_MCP_FAIL=1 run "$S" mcp list
  [ "$status" -eq 1 ]
  [ -e "$BATS_TEST_TMPDIR/probe" ]
}
