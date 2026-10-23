#!/usr/bin/env bats
# Slack notices (Slack notices spec §3.2): notify.sh with a stubbed claude.
load helpers

# The default connector is Slack connected at claude.ai, the one a headless session loads (#133).
T=mcp__claude_ai_Slack__slack_send_message

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_connector"
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
  grep -qF '[notify] Notice posted with drift: 1 of 2 event lines missing from the post (kept in system/logs/notify/drift/)' "$ALERTS"
  [ "$(jq '.lines | length' system/logs/notify/drift/collected.json)" -eq 2 ]
  grep -qF '"message":"• Alert 06:10:00 [intake] one"' system/logs/notify/drift/out.jsonl
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
  [ "$(tail -n 1 system/logs/notify-*.jsonl | jq -c 'del(.time)')" = '{"exit":0,"reason":"check","events":1}' ]
}

@test "an argument other than --check is a usage error, an empty one too (F1: fetch_check_arg)" {
  run "$N" ""
  [ "$status" -eq 2 ]
  [ "$output" = "usage: notify.sh [--check]" ]
  run "$N" --check extra
  [ "$status" -eq 2 ]
}

@test "a failure logs and alerts as before (F1: lib_fetch.sh)" {
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  slack_posts "$(system/scripts/notify.py collect | jq -r .message)" mcp__claude_ai_Slack__slack_send_message_draft
  run "$N"
  [ "$status" -eq 7 ]
  [ "$(tail -n 1 system/logs/notify-*.jsonl | jq -c 'del(.time)')" = '{"exit":7,"reason":"other: the session used an unexpected tool: mcp__claude_ai_Slack__slack_send_message_draft","events":0}' ]
  grep -qF '[notify] Notices failed (exit 7): other: the session used an unexpected tool' "$ALERTS"
  [ "${lines[-1]}" = "notify: other: the session used an unexpected tool: mcp__claude_ai_Slack__slack_send_message_draft" ]
}

# thread_posts <file> <message> <posted ts> [thread_ts]: a session that posts <message>, in a thread when given, and
# whose send result names the posted message's link.
thread_posts() {
  local url="https://example.slack.com/archives/C0EXAMPLE/p${3/./}${4:+?thread_ts=$4&cid=C0EXAMPLE}"
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$T"
    jq -cn --arg t "$T" --arg m "$2" --arg th "${4:-}" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2",
      name: $t, input: ({channel_id: "C0EXAMPLE", message: $m} + if $th == "" then {} else {thread_ts: $th} end)}]}}'
    jq -cn --arg u "Message sent: $url" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2",
      content: [{type: "text", text: $u}]}]}}'
    printf '{"type":"result","subtype":"success","is_error":false}\n'
  } > "$1"
}

@test "with slack_notify_thread daily, the day's first notice posts the parent, then every notice replies under it (#293)" {
  sed -i '$d' system/config.md
  printf '%s\n' 'slack_notify_thread: "daily"' '---' >> system/config.md
  day="$(TZ=America/Denver date +%F)"
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  thread_posts "$STUB_STREAM" "Foundry updates $day" 1792430610.351069
  thread_posts "$STUB_STREAM.next" "$(system/scripts/notify.py collect | jq -r .message)" 1792430700.000200 1792430610.351069
  run "$N"
  [ "$status" -eq 0 ]
  grep -qF '"thread_ts":"1792430610.351069"' "$STUB_ARGS"
  [ "$(system/scripts/notify.py parent)" = 1792430610.351069 ]
  [ "$(jq -r '.posts["1792430700.000200"].thread' system/logs/notify/thread.json)" = 1792430610.351069 ]
  # The same day: one session, a reply under the same parent.
  printf -- '- 06:20:00 [intake] two\n' >> "$ALERTS"
  thread_posts "$STUB_STREAM" "$(system/scripts/notify.py collect | jq -r .message)" 1792431300.000300 1792430610.351069
  run "$N"
  [ "$status" -eq 0 ]
  grep -qF '"thread_ts":"1792430610.351069"' "$STUB_ARGS"
  [ "$(jq '.posts | length' system/logs/notify/thread.json)" -eq 3 ]
}

@test "a parent post whose result names no link holds notices and sends no notice top-level (#293)" {
  sed -i '$d' system/config.md
  printf '%s\n' 'slack_notify_thread: "daily"' '---' >> system/config.md
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  slack_posts "Foundry updates $(TZ=America/Denver date +%F)"
  run "$N"
  [ "$status" -eq 7 ]
  [ -s system/logs/notify/hold ]
  [ ! -e system/logs/notify/thread.json ]
  rm system/logs/notify/hold
  msg="$(system/scripts/notify.py collect | jq -r .message)"
  [ "$msg" = "• Alert 06:10:00 [intake] one" ]
}

@test "slack_notify_thread daily with a user ID for a DM is refused before any session (#293)" {
  sed -i 's/^slack_notify_channel: "C0EXAMPLE"$/slack_notify_channel: "U0OWNER"/; $d' system/config.md
  printf '%s\n' 'slack_notify_thread: "daily"' '---' >> system/config.md
  printf -- '- 06:10:00 [intake] one\n' >> "$ALERTS"
  rm -f "$STUB_ARGS"
  run "$N"
  [ "$status" -eq 2 ]
  [ ! -e "$STUB_ARGS" ]
}
