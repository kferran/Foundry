#!/usr/bin/env bats
# Handoffs (delivered work spec §3.2, §4): the Jira fetch with a stubbed claude.
# Runs from a vault checkout with this repository at extensions/: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

J=mcp__claude_ai_Atlassian__searchJiraIssuesUsingJql

setup() {
  make_vault
  use_extension handoffs
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
  JF="$V/extensions/handoffs/scripts/jira_fetch.sh"
  LOG="system/logs/jira_fetch-$(TZ=America/Denver date +%Y-%m).jsonl"
  JQL="$(extensions/handoffs/scripts/jira_handoffs.py query | tail -n 1)"
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
  [ "$output" = 'jira_fetch: other: the session searched with other arguments than the ones built from the settings' ]
  jira_says mcp__claude_ai_Atlassian__createJiraIssue "$JQL" "$(ticket EX-1)"
  run "$JF"
  [ "$status" -eq 7 ]
  [ "$(grep -c '\[handoffs\] Jira fetch failed (exit 7):' "system/logs/alerts_$(TZ=America/Denver date +%F).md")" -eq 1 ]
}

@test "fetch: no connector exits 3; a timeout exits 4" {
  printf '{"type":"result","subtype":"success","is_error":false}\n' > "$STUB_STREAMS/search.jsonl"
  run "$JF"
  [ "$status" -eq 3 ]
  [[ "$output" == 'jira_fetch: auth: '* ]]   # no connector reachable is a credential to renew (connector health spec)
  jira_says "$J" "$JQL" "$(ticket EX-1)"
  STUB_SLEEP=3 JIRA_TIMEOUT=1 run "$JF"
  [ "$status" -eq 4 ]
  [ "$output" = 'jira_fetch: timeout: timed out after 1s' ]
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

@test "the manifest loads: listed, one smoke entry, one Sources row, one allow rule" {
  run system/scripts/extensions.py check
  [ "$status" -eq 0 ]
  [ "$(system/scripts/extensions.py list)" = handoffs ]
  [ "$(system/scripts/extensions.py smoke)" = "$(printf 'handoffs\t360\t1\textensions/handoffs/scripts/jira_fetch.sh --check')" ]
  [ "$(system/scripts/extensions.py allow)" = 'Bash(extensions/handoffs/scripts/jira_fetch.sh --check)' ]
}

# fetch_stub <rc> [line…]: replace jira_fetch.sh with a stub that prints the lines and exits rc (with a
# jira_fetch reason line on stderr when rc is not 0), and records each call.
fetch_stub() {
  local rc="$1"
  shift
  printf '%s\n' "$@" > "$BATS_TEST_TMPDIR/lines.md"
  printf '#!/bin/bash\necho "jira_fetch.sh $*" >> "%s/calls"\ncat "%s"\n(( %s == 0 )) || echo "jira_fetch: handoffs_site is not set" >&2\nexit %s\n' \
    "$BATS_TEST_TMPDIR" "$BATS_TEST_TMPDIR/lines.md" "$rc" "$rc" > "$JF"
}

# prep_handoffs: source brief/prep.sh as brief_prep.sh does (extensions spec §3), for 2026-10-01.
IN=system/logs/inputs/2026-10-01
prep_handoffs() {
  (
    VAULT_ROOT="$V"
    source system/scripts/lib_config.sh
    source system/scripts/lib_prep.sh
    PREP_NAME=brief_prep PREP_DATE=2026-10-01 PREP_DIR="$IN"
    mkdir -p "$PREP_DIR/sections"
    prep_sources_init
    # shellcheck disable=SC1091
    source extensions/handoffs/brief/prep.sh
  )
}

@test "brief section: the fetch's lines, and an ok reading for the Sources line (delivered work §3.3)" {
  fetch_stub 0 '- [ ] [EX-1](https://example.atlassian.net/browse/EX-1) Fix EX-1 (Blake Sample, In Review, unchanged since 2026-09-21)'
  run prep_handoffs
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/sections/handoffs.md")" = '- [ ] [EX-1](https://example.atlassian.net/browse/EX-1) Fix EX-1 (Blake Sample, In Review, unchanged since 2026-09-21)' ]
  grep -qx "$(printf 'handoffs\tok\t')" "$IN/sources.given"
  [ ! -e "$IN/unavailable.md" ]
}

@test "brief section: empty and unread while handoffs_projects is empty, and off on the Sources line" {
  sed -i 's/^handoffs_projects:.*/handoffs_projects: []/' system/config.md
  fetch_stub 0 'never'
  run prep_handoffs
  [ "$status" -eq 0 ]
  [ -e "$IN/sections/handoffs.md" ]
  [ ! -s "$IN/sections/handoffs.md" ]
  [ ! -e "$BATS_TEST_TMPDIR/calls" ]
  grep -qx "$(printf 'handoffs\toff\t')" "$IN/sources.given"
}

@test "brief section: a failed fetch is an unavailable input, an empty section and a failed reading" {
  fetch_stub 2
  run prep_handoffs
  [ "$status" -eq 0 ]
  [ ! -s "$IN/sections/handoffs.md" ]
  grep -qxF -- '- brief_prep: handoffs: handoffs_site is not set (set it with /setup)' "$IN/unavailable.md"
  grep -q "^$(printf 'handoffs\tfailed\t')" "$IN/sources.given"
  fetch_stub 3
  run prep_handoffs
  grep -qF -- '- brief_prep: handoffs: no Atlassian connector reachable' "$IN/unavailable.md"
}

@test "brief_prep runs the section and copies its prompt beside it (extensions spec §3)" {
  fetch_stub 0 '- [ ] [EX-2](https://example.atlassian.net/browse/EX-2) Fix EX-2 (Blake Sample, In Review, unchanged since 2026-09-21)'
  export CLAUDE_BIN="$BATS_TEST_TMPDIR/no-claude"   # the calendar is unavailable; the prep still runs
  run system/scripts/brief_prep.sh 2026-10-01
  [ "$status" -eq 0 ]
  grep -qF 'EX-2' "$IN/sections/handoffs.md"
  cmp -s extensions/handoffs/brief/section.md "$IN/sections/handoffs.prompt.md"
  grep -qx -- '- handoffs: ok' "$IN/sources.md"
}

@test "the smoke check runs the extension's check and names the Atlassian connector when it expired" {
  printf '#!/bin/bash\necho "jira_fetch: auth: token expired" >&2\nexit 6\n' > "$JF"
  mkdir -p "$BATS_TEST_TMPDIR/bin"
  printf '#!/bin/bash\n[[ "$1" == --version ]] || exit 2\necho "1.0.0 (Claude Code)"\n' > "$BATS_TEST_TMPDIR/bin/claude"
  chmod +x "$BATS_TEST_TMPDIR/bin/claude"
  PATH="$BATS_TEST_TMPDIR/bin:$PATH" CLAUDE_BIN=claude SYSTEMD_USER_DIR="$BATS_TEST_TMPDIR/units" \
    run system/scripts/smoke_check.sh
  grep -qx 'handoffs: expired: Atlassian connector; renew: reconnect it at claude.ai, Settings, Connectors' <<< "$output"
  grep -qF '[smoke] expired Atlassian connector:' "system/logs/alerts_$(TZ=America/Denver date +%F).md"
}
