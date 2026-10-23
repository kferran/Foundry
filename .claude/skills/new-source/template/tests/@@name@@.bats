#!/usr/bin/env bats
# @@description@@: the fetch with a stubbed claude, the manifest and the brief section. Written by /new-source; the
# feature adds its own tests for its arguments, its parse and its lines.
# Runs from a vault checkout with this repository at extensions/: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

T=@@tool@@
@@server_tools@@

setup() {
  make_vault
  use_extension @@name@@
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_connector"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude"
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_CWD="$BATS_TEST_TMPDIR/cwd" STUB_STREAMS="$BATS_TEST_TMPDIR/streams"
  export STUB_MCP_LIST="@@server@@: https://server.example/mcp - ok Connected
claude.ai Other: https://other.example/mcp - ok Connected"
  mkdir -p "$STUB_STREAMS" system/logs
  F="$V/extensions/@@name@@/scripts/@@name@@_fetch.sh"
  LOG="system/logs/@@name@@_fetch-$(TZ=America/Denver date +%Y-%m).jsonl"
  ALERTS="system/logs/alerts_$(TZ=America/Denver date +%F).md"
}

# session <tool> <input JSON> <result fields JSON> <result message JSON>: a session that loads the tool, calls <tool>
# once with <input>, gets a result with the given fields and a structuredContent, then ends with the message.
session() {
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$T"
    jq -cn --arg t "$1" --argjson i "$2" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t, input: $i}]}}'
    jq -cn --argjson r "$3" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2"} + $r]},
      tool_use_result: {structuredContent: {items: []}}}'
    printf '%s\n' "$4"
  } > "$STUB_STREAMS/search.jsonl"
}
TEXT='{"content": "{\"items\": []}"}'   # a result as plain JSON text, which the model can read
DONE='{"type":"result","subtype":"success","is_error":false,"num_turns":3}'
good() { session "$T" '{}' "$TEXT" "$DONE"; }

sessions() { grep -c -- '^--end--$' "$STUB_ARGS"; }
session_arg() { awk -v f="$1" 'p { print; exit } $0 == f { p = 1 }' "$STUB_ARGS"; }
session_deny() { awk '$0 == "--end--" { exit } p { print } $0 == "--disallowedTools" { p = 1 }' "$STUB_ARGS"; }
# others: the server's tools the session may not call, as the deny list names them.
others() (
  source system/scripts/lib_fetch.sh
  for t in @@tools@@; do [[ "@@prefix@@__$t" == "$T" ]] || echo "@@prefix@@__$t"; done
)

@test "fetch: one confined call with the built input, logged" {
  good
  run "$F"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(sessions)" -eq 1 ]
  [ "$(session_arg --allowedTools)" = "$T" ]
  [ "$(session_arg --permission-mode)" = dontAsk ]
  prompt="$(sed -n '/^-p$/,/^--settings$/p' "$STUB_ARGS")"
  [[ "$prompt" == *"call $T once with exactly this input: {}"* ]]
  session_deny | grep -qx Bash
  [ "$(session_deny | grep -cx "$T")" -eq 0 ]
  [ "$(session_deny | grep "^@@prefix@@__")" = "$(others)" ]   # the server's table, less the one tool
  [ "$(session_arg --settings | jq -c '.deniedMcpServers')" = '[{"serverName":"claude.ai Other"}]' ]
  [ "$(jq -c '[.exit, .lines]' "$LOG")" = '[0,0]' ]
}

@test "fetch --check prints how many lines the session read" {
  good
  run "$F" --check
  [ "$status" -eq 0 ]
  [ "$output" = '@@name@@_fetch: the session read 0 lines' ]
}

@test "fetch: an error result message exits 1" {
  session "$T" '{}' "$TEXT" '{"type":"result","subtype":"error_during_execution","is_error":true}'
  run "$F"
  [ "$status" -eq 1 ]
  [[ "$output" == *'claude returned an error result (error_during_execution)' ]]
}

@test "fetch: no ToolSearch result naming the tool exits 3" {
  printf '%s\n' "$DONE" > "$STUB_STREAMS/search.jsonl"
  run "$F"
  [ "$status" -eq 3 ]
  [ "$output" = '@@name@@_fetch: auth: no @@server@@ connector reachable' ]
}

@test "fetch: an error tool result exits 6" {
  session "$T" '{}' '{"is_error": true, "content": "upstream failed"}' "$DONE"
  run "$F"
  [ "$status" -eq 6 ]
  [[ "$output" == *'the connector returned an error: "upstream failed"' ]]
}

@test "fetch: a result too large for the model exits 6" {
  session "$T" '{}' '{"content": "<persisted-output>…"}' "$DONE"
  run "$F"
  [ "$status" -eq 6 ]
  [[ "$output" == *'a call result was too large for the model to read' ]]
}

@test "fetch: other arguments or another tool exit 7 with one alert a day" {
  session "$T" '{"x": 1}' "$TEXT" "$DONE"
  run "$F"
  [ "$status" -eq 7 ]
  [ "$output" = "@@name@@_fetch: other: the session called $T with other arguments than the ones built for this run" ]
  session @@prefix@@__another_tool '{}' "$TEXT" "$DONE"
  run "$F"
  [ "$status" -eq 7 ]
  [ "$output" = '@@name@@_fetch: other: the session used an unexpected tool: @@prefix@@__another_tool' ]
  [ "$(grep -c '\[@@name@@\] @@name@@ fetch failed (exit 7):' "$ALERTS")" -eq 1 ]
}

@test "the manifest loads: listed, one smoke entry, one allow rule" {
  run system/scripts/extensions.py check
  [ "$status" -eq 0 ]
  [ "$(system/scripts/extensions.py list)" = @@name@@ ]
  [ "$(system/scripts/extensions.py smoke)" = "$(printf '@@name@@\t360\t1\textensions/@@name@@/scripts/@@name@@_fetch.sh --check')" ]
  [ "$(system/scripts/extensions.py allow)" = 'Bash(extensions/@@name@@/scripts/@@name@@_fetch.sh --check)' ]
}

# prep_src: source brief/prep.sh as brief_prep.sh does (extensions spec §3), for 2026-10-01.
IN=system/logs/inputs/2026-10-01
prep_src() {
  (
    VAULT_ROOT="$V"
    source system/scripts/lib_config.sh
    source system/scripts/lib_prep.sh
    PREP_NAME=brief_prep PREP_DATE=2026-10-01 PREP_DIR="$IN"
    mkdir -p "$PREP_DIR/sections"
    prep_sources_init
    # shellcheck disable=SC1091
    source extensions/@@name@@/brief/prep.sh
  )
}

@test "brief section: the fetch's lines (none until the feature parses them) and an ok reading" {
  good
  run prep_src
  [ "$status" -eq 0 ]
  [ -e "$IN/sections/@@name@@.md" ]
  [ ! -s "$IN/sections/@@name@@.md" ]
  grep -qx "$(printf '@@name@@\tok\t')" "$IN/sources.given"
  [ ! -e "$IN/unavailable.md" ]
}

@test "brief section: a failed fetch is an unavailable input, an empty section and a failed reading" {
  printf '#!/bin/bash\necho "@@name@@_fetch: auth: no connector" >&2\nexit 3\n' > "$F"
  run prep_src
  [ "$status" -eq 0 ]
  [ ! -s "$IN/sections/@@name@@.md" ]
  grep -qxF -- '- brief_prep: @@name@@: auth: no connector' "$IN/unavailable.md"
  grep -qx "$(printf '@@name@@\tfailed\tauth: no connector')" "$IN/sources.given"
}
