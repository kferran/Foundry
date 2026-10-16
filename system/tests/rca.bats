#!/usr/bin/env bats
# RCA-to-Jira (RCA spec §3.3): rca_file.sh with a stubbed claude.
load helpers

C=mcp__claude_ai_Atlassian__createJiraIssue
STEM=2026-10-11-orders

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_calendar"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude" system/logs wiki/work/rca
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_STREAM="$BATS_TEST_TMPDIR/stream.jsonl"
  export STUB_MCP_LIST="claude.ai Atlassian: https://atlassian.example/mcp - ok Connected"
  sed -i '$d' system/config.md
  printf '%s\n' 'handoffs_site: "example.atlassian.net"' 'rca_project: "EX"' '---' >> system/config.md
  printf -- '---\ntype: rca\ntitle: "Orders fail"\npartition: work\ncreated_at: "2026-10-11"\nsource: "raw/telemetry/a.md"\nrc_confidence: 4\nfix_confidence: 4\nstatus: draft\n---\n# Orders fail\n\n## Ticket draft\n\n**Summary:** Orders fail\n\n**Description:**\nRoot cause: `src/app/orders.py:42`.\n' \
    > "wiki/work/rca/$STEM.md"
  printf -- '---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-11"\npartition: work\n---\n# Now\n\n## Needs you\n- [x] owed: Review RCA draft: %s (since 2026-10-11, rca:%s)\n\n## Waiting\n' "$STEM" "$STEM" \
    > wiki/work/Now.md
  RF="$V/system/scripts/rca_file.sh"
  ALERTS="system/logs/alerts_$(TZ=America/Denver date +%F).md"
  ARGS="$(system/scripts/rca.py args work "$STEM")"
}

# jira_says <tool> <args json> [key]: a session that loads the tool and calls it once.
jira_says() {
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$C"
    jq -cn --arg t "$1" --argjson a "$2" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t, input: $a}]}}'
    jq -cn --arg k "${3:-EX-7}" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2", content: "…"}]},
      tool_use_result: {structuredContent: {key: $k, id: "1"}}}'
    printf '{"type":"result","subtype":"success","is_error":false}\n'
  } > "$STUB_STREAM"
}

# jira_errs <text>: a session whose one create call comes back as an error with that text.
jira_errs() {
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s"}]}]}}\n' "$C"
    jq -cn --arg t "$C" --argjson a "$ARGS" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: $t, input: $a}]}}'
    jq -cn --arg e "$1" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2", is_error: true,
      content: [{type: "text", text: $e}]}]}}'
    printf '{"type":"result","subtype":"success","is_error":false}\n'
  } > "$STUB_STREAM"
}

@test "a create Jira refuses for a required field clears the marker and hands the draft back; the field then files (#175)" {
  jira_errs 'Error: 400 Bad Request: {"errors":{"customfield_10042":"Team is required."}}'
  run "$RF" work "$STEM"
  [ "$status" -eq 6 ]
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
  grep -qx 'status: "draft"' "wiki/work/rca/$STEM.md"
  grep -q '^- \[ \] owed: Review RCA draft: '"$STEM"': not filed .*Team is required.* (since 2026-10-11, rca:' wiki/work/Now.md
  grep -qF 'Jira refused the ticket, nothing was created' "$ALERTS"
  sed -i '$d' system/config.md
  printf '%s\n' "rca_extra_fields: {customfield_10042: '{\"id\": \"10042\"}'}" '---' >> system/config.md
  ARGS="$(system/scripts/rca.py args work "$STEM")"
  [ "$(jq -c .additional_fields <<< "$ARGS")" = '{"customfield_10042":{"id":"10042"}}' ]
  jira_says "$C" "$ARGS"
  run "$RF" work "$STEM"
  [ "$status" -eq 0 ]
  [ "$output" = "EX-7" ]
}

@test "a create error that is not a client rejection keeps the marker, since a ticket may exist" {
  jira_errs '500 Internal Server Error'
  run "$RF" work "$STEM"
  [ "$status" -eq 6 ]
  [[ "$output" == 'rca_file: connector: the connector returned an error: '*'500 Internal Server Error'*'; the create tool was called, so check Jira before deleting '* ]]   # #106
  [ -e "system/logs/rca/work-$STEM.attempt" ]
  grep -q '^- \[x\] owed: Review RCA draft: '"$STEM"' (since' wiki/work/Now.md
}

@test "an approved draft is filed once, and the key reaches the note, its Now line and the alerts" {
  jira_says "$C" "$ARGS"
  run "$RF" work "$STEM"
  [ "$status" -eq 0 ]
  [ "$output" = "EX-7" ]
  grep -qx 'ticket: "EX-7"' "wiki/work/rca/$STEM.md"
  grep -qx 'status: "filed"' "wiki/work/rca/$STEM.md"
  grep -qF '_(closed: filed EX-7 ' wiki/work/Now.md
  grep -qF '[rca] filed EX-7 for' "$ALERTS"
  grep -qxF -- "$C" "$STUB_ARGS"
  grep -qxF -- mcp__claude_ai_Atlassian__editJiraIssue "$STUB_ARGS"
  [ ! -e "system/logs/rca/work-$STEM.key" ]   # #106
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
}

@test "the session is checked against the arguments sent, so a note edited during it still files (#106)" {
  printf '#!/bin/bash\n[[ "$1" == mcp ]] || sed -i "s/^\\*\\*Summary:\\*\\* Orders fail$/**Summary:** Orders fail, edited/" "%s"\nexec "%s" "$@"\n' \
    "$V/wiki/work/rca/$STEM.md" "$REPO/system/tests/stub_claude_calendar" > "$BATS_TEST_TMPDIR/claude"
  chmod +x "$BATS_TEST_TMPDIR/claude"
  jira_says "$C" "$ARGS"
  CLAUDE_BIN="$BATS_TEST_TMPDIR/claude" run "$RF" work "$STEM"
  [ "$status" -eq 0 ]
  [ "$output" = "EX-7" ]
  grep -qx '\*\*Summary:\*\* Orders fail, edited' "wiki/work/rca/$STEM.md"
}

@test "writing back a key by hand clears the markers, as the exit 5 message says (#106)" {
  mkdir -p system/logs/rca
  touch "system/logs/rca/work-$STEM.attempt"
  run system/scripts/rca.py filed work "$STEM" EX-5
  [ "$status" -eq 0 ]
  grep -qx 'ticket: "EX-5"' "wiki/work/rca/$STEM.md"
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
}

@test "another tool or other arguments are refused, write nothing and alert once a day" {
  jira_says mcp__claude_ai_Atlassian__editJiraIssue "$ARGS"
  run "$RF" work "$STEM"
  [ "$status" -eq 7 ]
  jira_says "$C" "$(jq -c '.summary = "something else"' <<< "$ARGS")"
  run "$RF" work "$STEM"
  [ "$status" -eq 7 ]
  grep -qx 'status: draft' "wiki/work/rca/$STEM.md"
  [ "$(grep -c '\[rca\] Filing' "$ALERTS")" -eq 1 ]
}

@test "a create call that saved no key blocks the next session until the marker goes" {
  jira_says "$C" "$(jq -c '.summary = "something else"' <<< "$ARGS")"
  run "$RF" work "$STEM"
  [ "$status" -eq 7 ]
  [ -e "system/logs/rca/work-$STEM.attempt" ]
  rm -f "$STUB_ARGS"
  run "$RF" work "$STEM"
  [ "$status" -eq 5 ]
  [ ! -e "$STUB_ARGS" ]
  grep -qx 'status: draft' "wiki/work/rca/$STEM.md"
  rm "system/logs/rca/work-$STEM.attempt"
  run "$RF" work "$STEM"
  [ "$status" -eq 7 ]
}

@test "a session that never called the create tool leaves no marker" {
  jira_says mcp__claude_ai_Atlassian__editJiraIssue "$ARGS"
  run "$RF" work "$STEM"
  [ "$status" -eq 7 ]
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
}

@test "no connector exits 3, a timeout 4, a missing claude 127; none leaves a marker or files (#106)" {
  printf '{"type":"result","subtype":"success","is_error":false}\n' > "$STUB_STREAM"
  run "$RF" work "$STEM"
  [ "$status" -eq 3 ]
  [ "$output" = 'rca_file: auth: no Atlassian connector reachable' ]
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
  jira_says "$C" "$ARGS"
  STUB_SLEEP=3 RCA_TIMEOUT=1 run "$RF" work "$STEM"
  [ "$status" -eq 4 ]
  [ "$output" = 'rca_file: timeout: timed out after 1s' ]
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
  rm -f "$STUB_ARGS"
  CLAUDE_BIN="$BATS_TEST_TMPDIR/no-such-claude" run "$RF" work "$STEM"
  [ "$status" -eq 127 ]
  [ ! -e "$STUB_ARGS" ]
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
  grep -qx 'status: draft' "wiki/work/rca/$STEM.md"
}

@test "a refused allow rule runs no session and leaves no marker (connector runner spec §2)" {
  printf '{"permissions":{"allow":["mcp__claude_ai_Atlassian"]}}' > "$HOME/.claude/settings.json"
  run "$RF" work "$STEM"
  [ "$status" -eq 1 ]
  [[ "$output" == *"allows every tool on mcp__claude_ai_Atlassian"* ]]
  [ ! -e "$STUB_ARGS" ]
  [ ! -e "system/logs/rca/work-$STEM.attempt" ]
}

@test "a ticket already created is only written back, never filed twice" {
  mkdir -p system/logs/rca
  printf 'EX-5\n' > "system/logs/rca/work-$STEM.key"
  run "$RF" work "$STEM"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
  grep -qx 'ticket: "EX-5"' "wiki/work/rca/$STEM.md"
  [ ! -e "system/logs/rca/work-$STEM.key" ]
}

@test "incomplete settings or a bad target exit 2 before any session" {
  sed -i 's/^rca_project: "EX"$/rca_project: ""/' system/config.md
  run "$RF" work "$STEM"
  [ "$status" -eq 2 ]
  [ ! -e "$STUB_ARGS" ]
  run "$RF" work ../escape
  [ "$status" -eq 2 ]
  run "$RF" work
  [ "$status" -eq 2 ]
}
