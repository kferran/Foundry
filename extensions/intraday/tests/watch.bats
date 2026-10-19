#!/usr/bin/env bats
# The watch tick (phase D spec §3.2 to §3.7; plan Task 8): watch_fetch.sh with a stubbed claude.
# Runs from a vault checkout: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

SLACK=mcp__claude_ai_Slack__slack_search_public_and_private
GMAIL=mcp__claude_ai_Gmail__search_threads

setup() {
  make_vault
  use_extension intraday
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/extensions/intraday/tests/stub_claude_watch"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude" system/logs/watch
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_SLACK_STREAM="$BATS_TEST_TMPDIR/slack.jsonl" STUB_CAL_STREAM="$BATS_TEST_TMPDIR/cal.jsonl"
  export STUB_ARGS_SLACK="$BATS_TEST_TMPDIR/slack.args" STUB_MCP_LIST="claude.ai Slack: https://slack.example/mcp - ok Connected"
  export WATCH_CLOCK="3 10"   # a Wednesday, 10:00
  sed -i '$d' system/config.md
  cat >> system/config.md <<'EOF'
watch_channels: [{id: "C0OPS", label: "ops"}]
watch_group_dms: "false"
watch_user_id: "U0OWNER"
watch_commitments_mail: "false"
watch_partition: "work"
capture_channel: "C0CAP"
capture_partition: "work"
---
EOF
  printf '{"watch": 1800000000, "own": 1800000000}\n' > system/logs/watch/cursors.json
  TODAY="$(TZ=America/Denver date +%F)"
  WF="$V/extensions/intraday/scripts/watch_fetch.sh"
  ALERTS="system/logs/alerts_$TODAY.md"
  cal_says '[]'
  slack_says '{"items": []}'
}

# result <channel line> <channel id> <ts> <text>: one search result block.
result() {
  printf '### Result 1 of 1\nChannel: %s\nFrom: Pat Sample <pat@example.com> (ID: U0PAT) \nTime: x\nMessage_ts: %s\nPermalink: [link](https://example.slack.com/archives/%s/p%s)\nText: \n%s\n\n---\n\n' \
    "$1" "$3" "$2" "${3/./}" "$4"
}

# slack_says <reply json>: one page per search this tick builds; a search's results come from page-<name>.md.
slack_says() {
  local inputs name n=1 res
  inputs="$(extensions/intraday/scripts/watch.py slack-input)"
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t0","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t0","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$SLACK"
    for name in $(jq -r 'keys_unsorted[]' <<< "$inputs"); do
      res="$(printf '## Messages (0 results)\n')"
      [[ ! -f "$BATS_TEST_TMPDIR/page-$name.md" ]] || res="$(printf '## Messages (1 results)\n%s' "$(cat "$BATS_TEST_TMPDIR/page-$name.md")")"
      jq -cn --arg t "${SLACK_TOOL_USED:-$SLACK}" --argjson i "$(jq -c --arg n "$name" '.[$n]' <<< "$inputs")" --arg id "t$n" \
        '{type: "assistant", message: {content: [{type: "tool_use", id: $id, name: $t, input: $i}]}}'
      jq -cn --arg id "t$n" --arg r "$res" --arg p "${SLACK_PAGINATION:-End of results}" \
        '{type: "user", message: {content: [{type: "tool_result", tool_use_id: $id, content: [{type: "text", text: ({results: $r, pagination_info: $p} | tojson)}]}]}}'
      n=$((n + 1))
    done
    jq -cn --arg r "$1" '{type: "result", subtype: "success", is_error: false, result: $r}'
  } > "$STUB_SLACK_STREAM"
}

# cal_says <events json>: the calendar session's structured output for today.
cal_says() {
  jq -cn --argjson e "$1" '{type: "result", subtype: "success", is_error: false, structured_output: {status: "ok", reason: "", events: $e}}' > "$STUB_CAL_STREAM"
}

@test "a non-mention cancellation in a watched channel is one today line and one [watch] alert, with the calendar cross-check" {
  result "#ops (ID: C0OPS)" C0OPS 1792430610.351069 "Heads up: the Weekly Huddle is cancelled today." > "$BATS_TEST_TMPDIR/page-watch.md"
  cal_says "[{\"start_date\": \"$TODAY\", \"start_time\": \"09:30\", \"end_date\": \"$TODAY\", \"end_time\": \"10:00\", \"title\": \"Weekly Huddle\"}]"
  slack_says '{"items": [{"query": "watch", "channel_id": "C0OPS", "ts": "1792430610.351069", "kind": "meeting_change", "who": "Pat", "what": "Weekly Huddle cancelled today", "by": "", "change": "cancelled", "meeting": false}]}'
  run "$WF"
  [ "$status" -eq 0 ]
  [ "$(grep -c '\[watch\]' "$ALERTS")" -eq 1 ]
  grep -qF '[watch] Weekly Huddle 09:30-10:00 cancelled per #ops (calendar still confirmed) https://example.slack.com/archives/C0OPS/p1792430610351069' "$ALERTS"
  run extensions/intraday/scripts/today_log.py tick
  [ "$status" -eq 0 ]
  [ "$(grep -c '\*\*meeting\*\*' "briefings/$TODAY.today.md")" -eq 1 ]
  grep -qF '**meeting** Weekly Huddle 09:30-10:00 cancelled per #ops (calendar still confirmed) https://example.slack.com/archives/C0OPS/p1792430610351069' "briefings/$TODAY.today.md"
  run system/scripts/vault_index.py validate "briefings/$TODAY.today.md"
  [ "$status" -eq 0 ]
  # The next tick reads the same message again through its overlap: nothing routes twice.
  slack_says '{"items": [{"query": "watch", "channel_id": "C0OPS", "ts": "1792430610.351069", "kind": "meeting_change", "who": "Pat", "what": "Weekly Huddle cancelled today", "by": "", "change": "cancelled", "meeting": false}]}'
  run "$WF"
  [ "$(grep -c '\[watch\]' "$ALERTS")" -eq 1 ]
}

@test "a commitment in a group DM becomes one owed line with the message link" {
  result "Group DM (ID: C0GDM)" C0GDM 1792434633.451019 "I'll get you added to the partner meeting" > "$BATS_TEST_TMPDIR/page-own.md"
  slack_says '{"items": [{"query": "own", "channel_id": "C0GDM", "ts": "1792434633.451019", "kind": "commitment", "who": "Sam Sample", "what": "Add Sam to the partner meeting", "by": "", "change": "other", "meeting": false}]}'
  run "$WF"
  [ "$status" -eq 0 ]
  grep -qF -- '- [ ] owed: Add Sam to the partner meeting (in group DM) [due:: ' wiki/work/Now.md
  grep -qF '(Sam Sample, since '"$TODAY"', https://example.slack.com/archives/C0GDM/p1792434633451019)' wiki/work/Now.md
  grep -qxF -- --allowedTools "$STUB_ARGS_SLACK"
  grep -qxF -- mcp__claude_ai_Slack__slack_send_message "$STUB_ARGS_SLACK"
}

@test "the capture channel's first tick only sets its cursor; the next one's messages become an inbox drop the intake compiles" {
  run "$WF"
  [ "$status" -eq 0 ]
  [ -z "$(ls raw/inbox 2>/dev/null)" ]
  [ "$(jq -r .capture system/logs/watch/cursors.json)" != null ]
  result "#notes (ID: C0CAP)" C0CAP 1792429200.000100 "idea: retry the export with the new key" > "$BATS_TEST_TMPDIR/page-capture.md"
  slack_says '{"items": []}'
  run "$WF"
  [ "$status" -eq 0 ]
  f="$(ls raw/inbox/slack-*.md)"
  grep -qxF 'partition: "work"' "$f"
  grep -qxF 'idea: retry the export with the new key' "$f"
  touch -d '10 minutes ago' "$f"
  CLAUDE_BIN="$REPO/system/tests/stub_claude" run system/scripts/intake_daemon.sh
  [ "$status" -eq 0 ]
  [ ! -e "$f" ]
  ls raw/archive | grep -q '^slack-'
  # The next tick reads the same message again through its overlap: it is not captured twice.
  slack_says '{"items": []}'
  run "$WF"
  [ "$status" -eq 0 ]
  [ -z "$(ls raw/inbox 2>/dev/null)" ]
}

@test "a search that reads its full page limit resumes next tick from the last message it read" {
  result "#ops (ID: C0OPS)" C0OPS 1792430610.351069 "Status as usual." > "$BATS_TEST_TMPDIR/page-watch.md"
  SLACK_PAGINATION='For the next page of results use cursor `Q1`' slack_says '{"items": []}'
  run "$WF"
  [ "$status" -eq 0 ]
  [ "$(jq -r .watch system/logs/watch/cursors.json)" = 1792430610 ]
  [ "$(jq -r .own system/logs/watch/cursors.json)" -ne 1800000000 ]   # no message read: the tick's start
  grep -qF '[intraday] the watch search read its full page limit: the next tick reads on from the last message read' "$ALERTS"
}

@test "with only a capture channel set, the first tick still sets its cursor" {
  sed -i '/^watch_channels:/d; /^watch_user_id:/d' system/config.md
  [ "$(extensions/intraday/scripts/watch.py slack-input)" = "{}" ]
  run "$WF"
  [ "$status" -eq 0 ]
  [ "$(jq -r .capture system/logs/watch/cursors.json)" != null ]
}

@test "a Slack session outside the rules writes nothing, keeps its cursors and alerts once a day; the calendar still runs" {
  SLACK_TOOL_USED=mcp__claude_ai_Slack__slack_read_channel slack_says '{"items": []}'
  run "$WF"
  [ "$status" -eq 7 ]
  [ "$(jq -r .watch system/logs/watch/cursors.json)" = 1800000000 ]
  [ -f "system/logs/watch/calendar-$TODAY.json" ]
  run "$WF"
  [ "$(grep -c '\[intraday\] The slack watch failed (exit 7):' "$ALERTS")" -eq 1 ]
}

@test "--check runs the sessions and writes nothing; a client and a tick outside workdays 08:00-18:00 run nothing" {
  run "$WF" --check
  [ "$status" -eq 0 ]
  [[ "$output" == "watch_fetch: 0 from Slack, - from mail, 0 events today" ]]
  [ ! -e "system/logs/watch/calendar-$TODAY.json" ]
  [ "$(jq -r .watch system/logs/watch/cursors.json)" = 1800000000 ]
  rm -f "$STUB_ARGS_SLACK"
  WATCH_CLOCK="6 10" run "$WF"
  [ "$status" -eq 0 ]
  WATCH_CLOCK="3 18" run "$WF"
  [ "$status" -eq 0 ]
  system/scripts/vault_index.py set system/config.md machine_role client > /dev/null
  run "$WF"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS_SLACK" ]
}

@test "sent mail is searched with the built query and its commitments become owed lines" {
  system/scripts/vault_index.py set system/config.md watch_commitments_mail true > /dev/null
  export STUB_MAIL_STREAM="$BATS_TEST_TMPDIR/mail.jsonl"
  printf '{"watch": 1800000000, "own": 1800000000, "mail": 1800000000}\n' > system/logs/watch/cursors.json
  q="$(extensions/intraday/scripts/watch.py mail-query)"
  [ "$q" = "in:sent after:1799999700" ]
  {
    jq -cn --arg t "$GMAIL" --arg q "$q" '{type: "assistant", message: {content: [{type: "tool_use", id: "m1", name: $t, input: {query: $q, pageSize: 50, view: "THREAD_VIEW_MINIMAL"}}]}}'
    jq -cn '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "m1", content: "…"}]},
      tool_use_result: {structuredContent: {threads: [{id: "th1", viewUrl: "https://mail.google.com/mail/#all/thread-a:1",
        messages: [{labelIds: ["SENT"], internalDate: "1800000100000", subject: "Deck", snippet: "I will send the deck Friday"}]}]}}}'
    jq -cn '{type: "result", subtype: "success", is_error: false, result: ({items: [{thread_id: "th1", kind: "commitment", who: "Pat Sample", what: "Send Pat the deck", by: "", meeting: false}]} | tojson)}'
  } > "$STUB_MAIL_STREAM"
  run "$WF"
  [ "$status" -eq 0 ]
  grep -qF -- '- [ ] owed: Send Pat the deck [due:: ' wiki/work/Now.md
  grep -qF 'https://mail.google.com/mail/#all/thread-a:1)' wiki/work/Now.md
}
