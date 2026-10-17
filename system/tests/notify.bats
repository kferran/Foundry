#!/usr/bin/env bats
# Slack notices (Slack notices spec §3.2): notify.sh with a stubbed claude.
load helpers

# The default connector is Slack connected at claude.ai, the one a headless session loads (#133).
T=mcp__claude_ai_Slack__slack_send_message

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_calendar"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude" system/logs
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_STREAM="$BATS_TEST_TMPDIR/stream.jsonl"
  export STUB_MCP_LIST="plugin:slack:slack: https://slack.example/mcp (HTTP) - ok Connected"
  sed -i '$d' system/config.md
  printf '%s\n' 'slack_notify_channel: "C0EXAMPLE"' '---' >> system/config.md
  N="$V/system/scripts/notify.sh"
  ALERTS="system/logs/alerts_$(TZ=America/Denver date +%F).md"
  run "$N"  # the first tick only sets the cursor
  [ "$status" -eq 0 ]
}

# slack_posts <message>: a session that loads the tool and posts <message> to the channel.
slack_posts() {
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$T"
    jq -cn --arg t "${2:-$T}" --arg m "$1" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t,
      input: {channel_id: "C0EXAMPLE", message: $m}}]}}'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","content":"ok"}]}}\n'
    printf '{"type":"result","subtype":"success","is_error":false}\n'
  } > "$STUB_STREAM"
}

@test "nothing new starts no session" {
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "a posted notice moves the cursor, so the next tick sends nothing" {
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  slack_posts "$(system/scripts/notify.py collect | jq -r .message)"
  run "$N"
  [ "$status" -eq 0 ]
  grep -qxF -- "$T" "$STUB_ARGS"
  grep -qxF -- mcp__claude_ai_Slack__slack_send_message_draft "$STUB_ARGS"
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "a post the checker confirms moves the cursor even when claude exits non-zero (#122)" {
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  slack_posts "$(system/scripts/notify.py collect | jq -r .message)"
  STUB_RC=1 run "$N"
  [ "$status" -eq 0 ]
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "a session that breaks its rules holds notices until the hold file goes, without feeding the same lines again" {
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  slack_posts "$(system/scripts/notify.py collect | jq -r .message)" mcp__claude_ai_Slack__slack_send_message_draft
  run "$N"
  [ "$status" -eq 7 ]
  [ -s system/logs/notify/hold ]
  printf -- '- 06:20:00 [intake] two\n' >> "$ALERTS"
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 5 ]
  [ ! -e "$STUB_ARGS" ]
  rm system/logs/notify/hold
  msg="$(system/scripts/notify.py collect | jq -r .message)"
  [ "$msg" = "• Alert 06:20:00 [intake] two" ]
}

@test "a post that drifted counts as sent and alerts once a day" {
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  printf -- '- 06:10:01 [intake] two\n' >> "$ALERTS"
  slack_posts "• Alert 06:10:00 [intake] one"
  run "$N"
  [ "$status" -eq 0 ]
  grep -qF '[notify] Notice posted with drift: 1 of 2 event lines missing from the post' "$ALERTS"
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "an empty channel starts no session, and --check then refuses" {
  sed -i 's/^slack_notify_channel: "C0EXAMPLE"$/slack_notify_channel: ""/' system/config.md
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
  run "$N" --check
  [ "$status" -eq 2 ]
}

@test "--check posts the test message" {
  slack_posts "Foundry notices are on for ${V##*/}."
  run "$N" --check
  [ "$status" -eq 0 ]
  grep -qF '"message":"Foundry notices are on for' "$STUB_ARGS"
}
