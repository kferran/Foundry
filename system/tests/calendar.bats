#!/usr/bin/env bats
# calendar_fetch.sh (calendar spec §4): confinement flags, deny list, exit codes and log.
load helpers

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_calendar"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude"
  export JARVIS_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" JARVIS_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_CWD="$BATS_TEST_TMPDIR/cwd" STUB_ENV="$BATS_TEST_TMPDIR/env"
  export STUB_STREAM="$BATS_TEST_TMPDIR/stream.jsonl"
  CF="$V/system/scripts/calendar_fetch.sh"
  DAY=2026-10-05
  stream_ok '[{"start_date":"2026-10-05","start_time":"09:00","end_date":"2026-10-05","end_time":"09:30","title":"Standup"}]'
}

# stream_ok <events json>: a successful session returning those events.
stream_ok() {
  stream "{\"status\":\"ok\",\"reason\":\"\",\"events\":$1}" ToolSearch mcp__claude_ai_Google_Calendar__list_events StructuredOutput
}

# stream <structured output json> <tool name…>: a session using those tools and returning that output.
stream() {
  local out="$1" t
  shift
  {
    printf '{"type":"system","subtype":"init","tools":["ToolSearch","Bash"]}\n'
    for t in "$@"; do
      printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"%s","input":{}}]}}\n' "$t"
    done
    printf '{"type":"result","subtype":"success","is_error":false,"num_turns":4,"total_cost_usd":0.2,"permission_denials":[],"structured_output":%s}\n' "$out"
  } > "$STUB_STREAM"
}

arg_after() { awk -v f="$1" 'p { print; exit } $0 == f { p = 1 }' "$STUB_ARGS"; }

@test "a day's events are written as TSV and logged" {
  run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf '2026-10-05\t09:00\t2026-10-05\t09:30\tStandup')" ]
  log="system/logs/calendar_fetch-2026-10.jsonl"
  [ "$(wc -l < "$log")" -eq 1 ]
  [ "$(jq -c '[.date, .exit, .events, .cost_usd, .turns, .denials]' "$log")" = '["2026-10-05",0,1,0.2,4,0]' ]
  [ "$(jq -c .tools "$log")" = '["ToolSearch","Bash"]' ]
}

@test "the session is confined: one allowed tool, the deny list, hooks and skills off, no isolation flags that hide connectors" {
  run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  [ "$(arg_after --allowedTools)" = mcp__claude_ai_Google_Calendar__list_events ]
  [ "$(arg_after --permission-mode)" = dontAsk ]
  [ "$(arg_after --output-format)" = stream-json ]
  [ "$(arg_after --max-budget-usd)" = 1 ]
  [ "$(arg_after --max-turns)" = 15 ]
  deny="$(awk '$0 == "--disallowedTools" { p = 1; next } p' "$STUB_ARGS")"
  for t in Bash PowerShell Monitor Read Write Edit Glob Grep WebFetch WebSearch Skill Agent Workflow SendMessage \
      Artifact CronCreate RemoteTrigger ListMcpResourcesTool ReadMcpResourceTool \
      mcp__claude_ai_Google_Calendar__create_event mcp__claude_ai_Google_Calendar__update_event \
      mcp__claude_ai_Google_Calendar__delete_event mcp__claude_ai_Google_Calendar__respond_to_event \
      mcp__claude_ai_Google_Calendar__get_event mcp__claude_ai_Google_Calendar__search_events \
      mcp__claude_ai_Google_Calendar__list_calendars mcp__claude_ai_Google_Calendar__suggest_time; do
    grep -qx -- "$t" <<< "$deny"
  done
  run grep -qx -- mcp__claude_ai_Google_Calendar__list_events <<< "$deny"
  [ "$status" -eq 1 ]
  grep -qx -- --disable-slash-commands "$STUB_ARGS"
  grep -qx -- --verbose "$STUB_ARGS"
  grep -qx -- --json-schema "$STUB_ARGS"
  [ "$(arg_after --settings | jq -c .disableAllHooks)" = true ]
  run grep -qxE -- '--restricted|--tools|--setting-sources|--safe-mode' "$STUB_ARGS"
  [ "$status" -eq 1 ]
  [ "$(cat "$STUB_ENV")" = 1 ]
  [[ "$(cat "$STUB_CWD")" == /tmp/* ]]
  [ ! -e "$(cat "$STUB_CWD")" ]
}

@test "the prompt names the day, the next day and the configured timezone" {
  run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  grep -qF 'startTime "2026-10-05T00:00:00", endTime "2026-10-06T00:00:00", timeZone "America/Denver"' "$STUB_ARGS"
}

@test "every tool the user's settings allow is denied, except list_events and rules that would match it" {
  printf '%s\n' '{"permissions":{"allow":["mcp__claude_ai_Gmail__send_message","Bash(ls:*)","mcp__claude_ai_Google_Calendar","mcp__claude_ai_Google_Calendar__*","mcp__*","mcp__claude_ai_Google_Calendar__list_events"]}}' > "$HOME/.claude/settings.json"
  printf '%s\n' '{"permissions":{"allow":["mcp__claude_ai_Slack__slack_send_message"]}}' > "$HOME/.claude/settings.local.json"
  printf '%s\n' '{"permissions":{"allow":["WebFetch(domain:x)"]}}' > "$JARVIS_MANAGED_SETTINGS"
  mkdir -p "$JARVIS_MANAGED_SETTINGS_DIR"
  printf '%s\n' '{"permissions":{"allow":["mcp__claude_ai_Asana__create_task"]}}' > "$JARVIS_MANAGED_SETTINGS_DIR/10-team.json"
  run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  deny="$(awk '$0 == "--disallowedTools" { p = 1; next } p' "$STUB_ARGS")"
  for t in mcp__claude_ai_Gmail__send_message Bash mcp__claude_ai_Slack__slack_send_message WebFetch mcp__claude_ai_Asana__create_task; do
    grep -qx -- "$t" <<< "$deny"
  done
  for t in mcp__claude_ai_Google_Calendar__list_events mcp__claude_ai_Google_Calendar 'mcp__claude_ai_Google_Calendar__*' 'mcp__*'; do
    run grep -qxF -- "$t" <<< "$deny"
    [ "$status" -eq 1 ]
  done
}

@test "CLAUDE_CONFIG_DIR replaces ~/.claude for the allow rules" {
  export CLAUDE_CONFIG_DIR="$BATS_TEST_TMPDIR/cfg"
  mkdir -p "$CLAUDE_CONFIG_DIR"
  printf '%s\n' '{"permissions":{"allow":["mcp__claude_ai_Gmail__send_message"]}}' > "$CLAUDE_CONFIG_DIR/settings.json"
  run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  awk '$0 == "--disallowedTools" { p = 1; next } p' "$STUB_ARGS" | grep -qx mcp__claude_ai_Gmail__send_message
}

@test "a settings file that does not parse stops the fetch before claude runs" {
  printf 'not json\n' > "$HOME/.claude/settings.json"
  run "$CF" "$DAY"
  [ "$status" -eq 1 ]
  [[ "$output" == *"calendar_fetch: "*"settings.json"* ]]
  [ ! -e "$STUB_ARGS" ]
}

@test "every other listed server is denied by name; a failing listing still fetches" {
  export STUB_MCP_LIST="$(printf '%s\n' 'claude.ai Google Calendar: https://c/mcp - ok Connected' 'claude.ai Atlassian Rovo (2): https://a/mcp - ok Connected' 'plugin:slack:slack: https://s/mcp (HTTP) - ok Connected')"
  run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  [ "$(arg_after --settings | jq -c '[.deniedMcpServers[].serverName]')" = '["claude.ai Atlassian Rovo (2)","plugin:slack:slack"]' ]
  STUB_MCP_FAIL=1 run "$CF" "$DAY"
  [ "$status" -eq 0 ]
  [ "$(arg_after --settings | jq -c .deniedMcpServers)" = '[]' ]
}

@test "exit codes: no connector 3, connector error 6, too many 8, invalid 5, error result 1" {
  stream '{"status":"no_tool","reason":"","events":[]}' ToolSearch
  run "$CF" "$DAY"
  [ "$status" -eq 3 ]
  stream '{"status":"tool_error","reason":"rate limited","events":[]}' ToolSearch mcp__claude_ai_Google_Calendar__list_events
  run "$CF" "$DAY"
  [ "$status" -eq 6 ]
  [[ "$output" == *"rate limited"* ]]
  stream '{"status":"too_many","reason":"140","events":[]}' ToolSearch
  run "$CF" "$DAY"
  [ "$status" -eq 8 ]
  stream_ok '[{"start_date":"2026-10-06","start_time":"","end_date":"2026-10-06","end_time":"","title":"Tomorrow"}]'
  run "$CF" "$DAY"
  [ "$status" -eq 5 ]
  printf '{"type":"result","subtype":"error_max_turns","is_error":false,"errors":["Reached maximum number of turns (15)"]}\n' > "$STUB_STREAM"
  run "$CF" "$DAY"
  [ "$status" -eq 1 ]
  [ "$(wc -l < system/logs/calendar_fetch-2026-10.jsonl)" -eq 5 ]
}

@test "a tool outside the three expected ones fails the fetch, writes nothing and alerts" {
  stream '{"status":"ok","reason":"","events":[]}' ToolSearch mcp__claude_ai_Gmail__send_message
  run "$CF" "$DAY"
  [ "$status" -eq 7 ]
  [[ "$output" != *$'\t'* ]]
  grep -q 'calendar.*mcp__claude_ai_Gmail__send_message' system/logs/alerts_*.md
  [ "$(jq -c .unexpected_tools system/logs/calendar_fetch-2026-10.jsonl)" = '["mcp__claude_ai_Gmail__send_message"]' ]
}

@test "a timeout exits 4, a missing claude 127, a bad date 2, a failing claude 1" {
  STUB_SLEEP=5 CALENDAR_TIMEOUT=1 run "$CF" "$DAY"
  [ "$status" -eq 4 ]
  CLAUDE_BIN="$BATS_TEST_TMPDIR/no-such-claude" run "$CF" "$DAY"
  [ "$status" -eq 127 ]
  run "$CF" 2026-02-30
  [ "$status" -eq 2 ]
  : > "$STUB_STREAM"
  STUB_RC=1 run "$CF" "$DAY"
  [ "$status" -eq 1 ]
}

@test "the date defaults to today in the configured timezone" {
  stream_ok '[]'
  run "$CF"
  [ "$status" -eq 0 ]
  grep -qF "startTime \"$(TZ=America/Denver date +%F)T00:00:00\"" "$STUB_ARGS"
}
