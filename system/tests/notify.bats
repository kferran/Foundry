#!/usr/bin/env bats
# Slack notices (Slack notices spec §3.2): notify.sh with a stubbed claude.
load helpers

T=mcp__plugin_slack_slack__slack_send_message

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
  grep -qxF -- mcp__plugin_slack_slack__slack_send_message_draft "$STUB_ARGS"
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "a refused post keeps the cursor and alerts once a day, and the next tick sends it again" {
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  msg="$(system/scripts/notify.py collect | jq -r .message)"
  slack_posts "$msg" mcp__plugin_slack_slack__slack_send_message_draft
  run "$N"
  [ "$status" -eq 7 ]
  run "$N"
  [ "$status" -eq 7 ]
  [ "$(grep -c '\[notify\] Notices failed (exit 7)' "$ALERTS")" -eq 1 ]
  slack_posts "$msg"
  run "$N"
  [ "$status" -eq 0 ]
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
