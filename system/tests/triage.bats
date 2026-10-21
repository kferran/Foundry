#!/usr/bin/env bats
# Inbox triage (inbox triage spec §3.1): triage_fetch.sh with a stubbed claude.
load helpers

G=mcp__claude_ai_Gmail__search_threads

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_connector"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude" system/logs
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_STREAM="$BATS_TEST_TMPDIR/stream.jsonl"
  export STUB_MCP_LIST="claude.ai Gmail: https://gmail.example/mcp - ok Connected
claude.ai Atlassian: https://atlassian.example/mcp - ok Connected"
  export TRIAGE_CLOCK="3 10"   # a Wednesday, 10:00
  sed -i '$d' system/config.md
  printf '%s\n' 'triage_enabled: "true"' 'triage_partition: "work"' '---' >> system/config.md
  # A known last tick fixes the query this tick builds.
  printf '{"kind": "tick", "epoch": 1000300}\n' > "system/logs/triage-$(TZ=America/Denver date +%Y-%m).jsonl"
  Q="in:inbox after:1000000 -category:promotions -category:social -category:forums -from:me"
  TF="$V/system/scripts/triage_fetch.sh"
  LOG="system/logs/triage_fetch-$(TZ=America/Denver date +%Y-%m).jsonl"
  ALERTS="system/logs/alerts_$(TZ=America/Denver date +%F).md"
}

# gmail_says <tool> <query> <reply json>: a session that loads the tool, searches once and replies.
gmail_says() {
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$G"
    jq -cn --arg t "$1" --arg q "$2" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t,
      input: {query: $q, pageSize: 50}}]}}'
    jq -cn '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2", content: "…"}]},
      tool_use_result: {structuredContent: {threads: [{id: "a1", viewUrl: "https://mail.google.com/mail/#all/a1",
        messages: [{id: "m1", date: "2026-10-09T20:24:00Z", sender: "Blake Sample <blake@example.com>"}]}]}}}'
    jq -cn --arg r "$3" '{type: "result", subtype: "success", is_error: false, result: $r}'
  } > "$STUB_STREAM"
}

ITEM='{"items": [{"thread_id": "a1", "who": "Blake", "ask": "asks how to proceed", "next_step": "reply today"}]}'

@test "a thread that needs you becomes one owed Now line and one alert; a rerun adds nothing" {
  gmail_says "$G" "$Q" "$ITEM"
  run "$TF"
  [ "$status" -eq 0 ]
  grep -qF -- '- [ ] owed: Blake: asks how to proceed. Next: reply today [due:: ' wiki/work/Now.md  # since + 3 with a sender (Now clock spec §4)
  grep -qF -- '] (blake@example.com, since ' wiki/work/Now.md
  grep -qF '[triage] 1 new: Blake: asks how to proceed' "$ALERTS"
  gmail_says "$G" "$(system/scripts/triage.py query)" "$ITEM"   # the next tick searches from this one
  run "$TF"
  [ "$status" -eq 0 ]
  [ "$(grep -c 'asks how to proceed' wiki/work/Now.md)" -eq 1 ]
  [ "$(grep -c '\[triage\] 1 new' "$ALERTS")" -eq 1 ]
}

@test "the session may search Gmail and nothing else, with the deny list and the built query" {
  gmail_says "$G" "$Q" "$ITEM"
  run "$TF"
  [ "$status" -eq 0 ]
  grep -qxF -- "$G" "$BATS_TEST_TMPDIR/args"
  grep -qxF -- mcp__claude_ai_Gmail__send_message "$BATS_TEST_TMPDIR/args"
  grep -qxF -- mcp__claude_ai_Gmail__create_draft "$BATS_TEST_TMPDIR/args"
  grep -qF -- "query \"$Q\"" "$BATS_TEST_TMPDIR/args"
}

@test "another tool or another query is refused, writes nothing and alerts once a day" {
  gmail_says mcp__claude_ai_Gmail__get_thread "$Q" "$ITEM"
  run "$TF"
  [ "$status" -eq 7 ]
  [ ! -e wiki/work/Now.md ]
  gmail_says "$G" "in:inbox" "$ITEM"
  run "$TF"
  [ "$status" -eq 7 ]
  [ "$(grep -c '\[triage\] Inbox triage failed (exit 7):' "$ALERTS")" -eq 1 ]
}

@test "no connector exits 3 and alerts as an auth problem" {
  printf '{"type":"result","subtype":"success","is_error":false,"result":"{}"}\n' > "$STUB_STREAM"
  run "$TF"
  [ "$status" -eq 3 ]
  grep -qF '[triage] Inbox triage failed (exit 3): auth: no Gmail connector reachable' "$ALERTS"
}

@test "a tick outside workdays 08:00-18:00, while off, or over the usage ceiling is skipped and logged" {
  gmail_says "$G" "$Q" "$ITEM"
  TRIAGE_CLOCK="6 10" run "$TF"
  [ "$status" -eq 0 ]
  TRIAGE_CLOCK="3 18" run "$TF"
  [ "$status" -eq 0 ]
  mkdir -p system/logs/nightshift
  printf '{"usage5": 0.9, "usage5_at": "%s"}\n' "$(date -Iseconds)" > "system/logs/nightshift/health-$(date +%F).json"
  run "$TF"
  [ "$status" -eq 0 ]
  [ ! -e "$BATS_TEST_TMPDIR/args" ]
  [ ! -e wiki/work/Now.md ]
  [ "$(jq -r '.reason' "$LOG" | grep -c '^skipped: ')" -eq 3 ]
  grep -qF '5-hour usage 90%' "$LOG"
}

@test "--check prints the count and writes nothing; usage errors exit 2" {
  gmail_says "$G" "$Q" "$ITEM"
  run "$TF" --check
  [ "$status" -eq 0 ]
  [ "$output" = "triage_fetch: 1 threads need the owner" ]
  [ ! -e wiki/work/Now.md ]
  run "$TF" --bogus
  [ "$status" -eq 2 ]
}

# Chat triage (chat triage spec §3.2): a second session that may only search Slack.
S=mcp__claude_ai_Slack__slack_search_public_and_private

chat_on() {
  sed -i '$d' system/config.md
  printf '%s\n' 'triage_chat_enabled: "true"' '---' >> system/config.md
  printf '{"kind": "tick", "epoch": 1000300, "source": "chat"}\n' >> "system/logs/triage-$(TZ=America/Denver date +%Y-%m).jsonl"
  export STUB_SLACK_ARGS="$BATS_TEST_TMPDIR/slack_args" STUB_SLACK_STREAM="$BATS_TEST_TMPDIR/slack.jsonl"
  export STUB_MCP_LIST="$STUB_MCP_LIST
claude.ai Slack: https://slack.example/mcp - ok Connected"
}

# slack_says <tool> <reply json>: a session that loads the tool, searches once with this tick's input and replies.
slack_says() {
  local md
  md="### Result 1 of 1
Channel: #ops (ID: C0000000001)
From: Blake Sample <blake@example.com> (ID: U0000000001)
Message_ts: 1792170000.000100
Permalink: [link](https://example.slack.com/archives/C0000000001/p1792170000000100)
Text:
prod checkout is down
---
"
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$S"
    jq -cn --arg t "$1" --argjson i "$(system/scripts/triage.py query --source chat)" \
      '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t, input: $i}]}}'
    jq -cn --arg md "$md" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2",
      content: [{type: "text", text: ({results: $md, pagination_info: ""} | tojson)}]}]}}'
    jq -cn --arg r "$2" '{type: "result", subtype: "success", is_error: false, result: $r}'
  } > "$STUB_SLACK_STREAM"
}

CHAT='{"items": [{"channel_id": "C0000000001", "ts": "1792170000.000100", "who": "Blake", "ask": "prod checkout is down", "next_step": "look now"}]}'

@test "a chat message that needs you becomes one owed Now line; mail still runs" {
  chat_on
  gmail_says "$G" "$Q" "$ITEM"
  slack_says "$S" "$CHAT"
  run "$TF"
  [ "$status" -eq 0 ]
  grep -qF -- '- [ ] owed: Blake: asks how to proceed.' wiki/work/Now.md
  grep -qF -- '- [ ] owed: Blake in #ops: prod checkout is down. Next: look now' wiki/work/Now.md
  grep -qF 'https://example.slack.com/archives/C0000000001/p1792170000000100' wiki/work/Now.md
  [ "$(grep -c '\[triage\] 1 new: ' "$ALERTS")" -eq 2 ]
}

@test "the chat session may only search Slack, with the built input" {
  chat_on
  gmail_says "$G" "$Q" "$ITEM"
  slack_says "$S" "$CHAT"
  run "$TF"
  [ "$status" -eq 0 ]
  grep -qxF -- "$S" "$STUB_SLACK_ARGS"
  grep -qxF -- mcp__claude_ai_Slack__slack_send_message "$STUB_SLACK_ARGS"
  grep -qxF -- mcp__claude_ai_Slack__slack_read_channel "$STUB_SLACK_ARGS"
  grep -qF -- '"only_my_channels": true' "$STUB_SLACK_ARGS"
}

@test "a failed chat session still writes the mail line and alerts once a day" {
  chat_on
  gmail_says "$G" "$Q" "$ITEM"
  slack_says mcp__claude_ai_Slack__slack_read_channel "$CHAT"
  run "$TF"
  [ "$status" -eq 7 ]
  grep -qF -- '- [ ] owed: Blake: asks how to proceed.' wiki/work/Now.md
  run grep -c 'in #ops' wiki/work/Now.md
  [ "$output" = 0 ]
  run "$TF"
  [ "$(grep -c '\[triage\] Chat triage failed (exit 7):' "$ALERTS")" -eq 1 ]
}

@test "a failed mail session still writes the chat line" {
  chat_on
  gmail_says mcp__claude_ai_Gmail__get_thread "$Q" "$ITEM"
  slack_says "$S" "$CHAT"
  run "$TF"
  [ "$status" -eq 7 ]
  grep -qF -- '- [ ] owed: Blake in #ops: prod checkout is down.' wiki/work/Now.md
  grep -qF '[triage] Inbox triage failed (exit 7):' "$ALERTS"
}

@test "with chat off, one session runs" {
  export STUB_SLACK_ARGS="$BATS_TEST_TMPDIR/slack_args" STUB_SLACK_STREAM="$BATS_TEST_TMPDIR/slack.jsonl"
  gmail_says "$G" "$Q" "$ITEM"
  slack_says "$S" "$CHAT"
  run "$TF"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_SLACK_ARGS" ]
}

@test "--check prints both counts and --source picks one" {
  chat_on
  gmail_says "$G" "$Q" "$ITEM"
  slack_says "$S" "$CHAT"
  run "$TF" --check
  [ "$status" -eq 0 ]
  [ "$output" = "triage_fetch: 1 threads need the owner
triage_fetch: 1 chat messages need the owner" ]
  run "$TF" --check --source chat
  [ "$status" -eq 0 ]
  [ "$output" = "triage_fetch: 1 chat messages need the owner" ]
  [ ! -e wiki/work/Now.md ]
  sed -i '/^triage_chat_enabled/d' system/config.md
  run "$TF" --check --source chat
  [ "$status" -eq 2 ]
}

@test "a bad triage_partition stops before any session and alerts once a day" {
  sed -i 's/^triage_partition: "work"$/triage_partition: "shared"/' system/config.md
  gmail_says "$G" "$Q" "$ITEM"
  run "$TF"
  [ "$status" -eq 2 ]
  [ ! -e "$BATS_TEST_TMPDIR/args" ]
  grep -qF '[triage] Inbox triage failed (exit 2): triage_partition must be one of work, personal' "$ALERTS"
}
