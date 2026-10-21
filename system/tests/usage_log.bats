#!/usr/bin/env bats
# Usage log hook (factory F0 spec §3.7): one line per slash command or Skill call, names only.
load helpers

setup() {
  make_vault
  cp -r "$REPO/system/hooks" "$V/system/hooks"
  VP="$(cd "$V" && pwd -P)"
  H="$VP/system/hooks/usage_log.sh"
  export CLAUDE_CODE_ENTRYPOINT=cli CLAUDE_CODE_SESSION_ATTENDED=1
  unset FOUNDRY_HEADLESS FOUNDRY_WORKCELL_SESSION FOUNDRY_WORK_ORDER
  cd "$VP"
}

hook() { run bash -c 'printf "%s" "$2" | "$1"' _ "$H" "$1"; }
prompt() { hook "$(jq -cn --arg p "$1" --arg c "${2:-$VP}" '{session_id: "s-1", cwd: $c, hook_event_name: "UserPromptSubmit", prompt: $p}')"; }
skill() { hook "$(jq -cn --arg s "$1" --arg c "${2:-$VP}" '{session_id: "s-1", cwd: $c, hook_event_name: "PreToolUse", tool_name: "Skill", tool_input: {skill: $s, args: "secret words"}}')"; }
lines() { cat system/logs/usage-*.jsonl 2>/dev/null; }

@test "a /query prompt writes one line with only ts and command" {
  prompt '/query what is in the inbox'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(lines | wc -l)" -eq 1 ]
  [ "$(lines | jq -c 'keys')" = '["command","ts"]' ]
  [ "$(lines | jq -r .command)" = query ]
  [ "$(lines | grep -c 'inbox')" -eq 0 ]
}

@test "a prompt without a leading slash command writes nothing" {
  prompt 'please run /query for me'
  [ "$status" -eq 0 ]
  prompt '/tmp/x is full'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ -z "$(lines)" ]
}

@test "a Skill PreToolUse writes one line with only ts and skill" {
  skill 'superpowers:brainstorming'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(lines | wc -l)" -eq 1 ]
  [ "$(lines | jq -c 'keys')" = '["skill","ts"]' ]
  [ "$(lines | jq -r .skill)" = superpowers:brainstorming ]
  [ "$(lines | grep -c 'secret')" -eq 0 ]
}

@test "headless, unattended, non-CLI and subagent sessions write nothing" {
  FOUNDRY_HEADLESS=1 prompt '/query x'
  [ "$status" -eq 0 ]
  CLAUDE_CODE_SESSION_ATTENDED=0 skill lint
  [ "$status" -eq 0 ]
  CLAUDE_CODE_ENTRYPOINT=sdk-cli prompt '/lint'
  [ "$status" -eq 0 ]
  hook "$(jq -cn --arg c "$VP" '{session_id: "s-1", cwd: $c, agent_id: "a1", hook_event_name: "PreToolUse", tool_name: "Skill", tool_input: {skill: "lint"}}')"
  [ "$status" -eq 0 ]
  [ -z "$(lines)" ]
}

@test "a cwd outside the vault root writes nothing" {
  mkdir -p "$BATS_TEST_TMPDIR/elsewhere" "$VP/wiki/sub"
  prompt '/query x' "$BATS_TEST_TMPDIR/elsewhere"
  [ "$status" -eq 0 ]
  skill lint "$VP/wiki/sub"
  [ "$status" -eq 0 ]
  [ -z "$(lines)" ]
}

@test "a broken log directory still exits 0 with no output" {
  rm -rf system/logs
  printf 'not a directory\n' > system/logs
  prompt '/query x'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  skill lint
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}
