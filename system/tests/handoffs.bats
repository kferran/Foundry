#!/usr/bin/env bats
# Handoffs (delivered work spec §3.2, §4): the Jira fetch with a stubbed claude.
load helpers

J=mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_meetings"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude"
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_CWD="$BATS_TEST_TMPDIR/cwd" STUB_STREAMS="$BATS_TEST_TMPDIR/streams"
  export STUB_MCP_LIST="claude.ai Atlassian: https://atlassian.example/mcp - ok Connected
claude.ai Gmail: https://gmail.example/mcp - ok Connected"
  mkdir -p "$STUB_STREAMS" system/logs
  sed -i '$d' system/config.md
  printf '%s\n' 'handoffs_site: "example.atlassian.net"' 'handoffs_projects: ["EX"]' '---' >> system/config.md
  JF="$V/system/scripts/jira_fetch.sh"
  LOG="system/logs/jira_fetch-$(TZ=America/Denver date +%Y-%m).jsonl"
  JQL="$(system/scripts/jira_handoffs.py query | tail -n 1)"
}

# ticket <key>: one issue node as the search result carries it.
ticket() {
  jq -cn --arg k "$1" '{key: $k, fields: {summary: ("Fix " + $k), status: {name: "In Review"},
    assignee: {displayName: "Blake Sample"}, statuscategorychangedate: "2026-09-28T09:00:00.000-0600"}}'
}

# jira_says <tool> <jql> <ticket json…>: a session that loads the tool and searches once with <tool> and <jql>.
jira_says() {
  local tool="$1" jql="$2" nodes
  shift 2
  nodes="$(printf '%s\n' "$@" | jq -cs .)"
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$J"
    jq -cn --arg t "$tool" --arg q "$jql" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t,
      input: {cloudId: "example.atlassian.net", jql: $q, maxResults: 100}}]}}'
    jq -cn --argjson n "$nodes" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2", content: "<persisted-output>…"}]},
      tool_use_result: {structuredContent: {issues: {nodes: $n, pageInfo: {hasNextPage: false}}}}}'
    printf '{"type":"result","subtype":"success","is_error":false,"num_turns":3}\n'
  } > "$STUB_STREAMS/search.jsonl"
}

sessions() { grep -c -- '^--end--$' "$STUB_ARGS"; }
session_arg() { awk -v f="$1" 'p { print; exit } $0 == f { p = 1 }' "$STUB_ARGS"; }
session_deny() { awk '$0 == "--end--" { exit } p { print } $0 == "--disallowedTools" { p = 1 }' "$STUB_ARGS"; }

@test "fetch: one confined search built from the settings prints one brief line per ticket and logs it" {
  jira_says "$J" "$JQL" "$(ticket EX-1)" "$(ticket EX-2)"
  run "$JF"
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 1 ]
  [ "${#lines[@]}" -eq 2 ]
  [ "${lines[0]}" = '- [ ] [EX-1](https://example.atlassian.net/browse/EX-1) Fix EX-1 (Blake Sample, In Review, unchanged since 2026-09-28)' ]
  [ "$(session_arg --allowedTools)" = "$J" ]
  [ "$(session_arg --permission-mode)" = dontAsk ]
  prompt="$(sed -n '/^-p$/,/^--settings$/p' "$STUB_ARGS")"
  [[ "$prompt" == *"cloudId \"example.atlassian.net\""* ]]
  [[ "$prompt" == *"jql: $JQL"* ]]
  session_deny | grep -qx 'mcp__claude_ai_Atlassian__createJiraIssue'
  session_deny | grep -qx 'mcp__claude_ai_Atlassian__getAccessibleAtlassianResources'
  session_deny | grep -qx Bash
  [ "$(session_arg --settings | jq -c '.deniedMcpServers')" = '[{"serverName":"claude.ai Gmail"}]' ]
  [ "$(jq -c '[.exit, .lines]' "$LOG")" = '[0,2]' ]
}

@test "fetch --check prints how many stalled handoffs the search listed" {
  jira_says "$J" "$JQL" "$(ticket EX-1)"
  run "$JF" --check
  [ "$status" -eq 0 ]
  [ "$output" = 'jira_fetch: the search listed 1 stalled handoffs' ]
}

@test "fetch: incomplete settings exit 2 before any session" {
  system/scripts/vault_index.py set system/config.md handoffs_site "" > /dev/null
  run "$JF"
  [ "$status" -eq 2 ]
  [[ "$output" == *'handoffs_site is not set'* ]]
  [ ! -e "$STUB_ARGS" ]
  [ "$(jq -c .exit "$LOG")" = 2 ]
}

@test "fetch: a search with other arguments or another tool exits 7 with one alert a day" {
  jira_says "$J" 'project = EX' "$(ticket EX-1)"
  run "$JF"
  [ "$status" -eq 7 ]
  [ "$output" = 'jira_fetch: the session searched with other arguments than the ones built from the settings' ]
  jira_says mcp__claude_ai_Atlassian__createJiraIssue "$JQL" "$(ticket EX-1)"
  run "$JF"
  [ "$status" -eq 7 ]
  [ "$(grep -c '\[handoffs\] Jira fetch failed (exit 7):' "system/logs/alerts_$(TZ=America/Denver date +%F).md")" -eq 1 ]
}

@test "fetch: no connector exits 3; a timeout exits 4" {
  printf '{"type":"result","subtype":"success","is_error":false}\n' > "$STUB_STREAMS/search.jsonl"
  run "$JF"
  [ "$status" -eq 3 ]
  jira_says "$J" "$JQL" "$(ticket EX-1)"
  STUB_SLEEP=3 JIRA_TIMEOUT=1 run "$JF"
  [ "$status" -eq 4 ]
  [ "$output" = 'jira_fetch: timed out after 1s' ]
}

@test "fetch: an allow rule for the whole Atlassian server stops the fetch before claude runs" {
  printf '{"permissions":{"allow":["mcp__claude_ai_Atlassian"]}}\n' > "$HOME/.claude/settings.json"
  run "$JF"
  [ "$status" -eq 1 ]
  [[ "$output" == *"allows every tool on mcp__claude_ai_Atlassian"* ]]
  [ ! -e "$STUB_ARGS" ]
}

@test "settings: handoffs_site and handoffs_projects are config fields" {
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -eq 0 ]
  [[ "$output" != *'unknown field handoffs'* ]]
}
