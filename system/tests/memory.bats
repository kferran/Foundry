#!/usr/bin/env bats
# Soundwave memory hooks (spec §6.17): eligibility, scope, activity, capture, recall.
load helpers

setup() {
  make_vault
  cp -r "$REPO/system/hooks" "$V/system/hooks"
  VP="$(cd "$V" && pwd -P)"
  H="$VP/system/hooks"
  S="$VP/system/logs/memory/sessions"
  export CLAUDE_CODE_ENTRYPOINT=cli CLAUDE_CODE_SESSION_ATTENDED=1
  unset JARVIS_HEADLESS JARVIS_CREW JARVIS_TASK_ID
  cd "$VP"
}

hook() {  # hook <script> <json>: run a hook with the JSON on stdin
  run bash -c 'printf "%s" "$2" | "$1"' _ "$H/$1" "$2"
}
start() { hook memory_recall.sh "$(jq -cn --arg s "$1" --arg c "${2:-$VP}" '{session_id: $s, cwd: $c, source: "startup", hook_event_name: "SessionStart"}')"; }
tool() { hook memory_activity.sh "$(jq -cn --arg s "$1" --arg c "${2:-$VP}" '{session_id: $s, cwd: $c, tool_name: "Edit", hook_event_name: "PostToolUse"}')"; }
stop() { hook memory_capture.sh "$(jq -cn --arg s "$1" --arg m "$2" --arg c "${3:-$VP}" '{session_id: $s, cwd: $c, last_assistant_message: $m, stop_hook_active: false}')"; }
tools() { local i; for i in $(seq 1 "$2"); do tool "$1"; done; }
thresholds() {
  system/scripts/vault_index.py set system/config.md digest_min_events "$1"
  system/scripts/vault_index.py set system/config.md digest_min_minutes "$2"
}
repo() { git init -q "$1"; git -C "$1" -c user.email=t@e -c user.name=t commit -q --allow-empty -m i; }
register() {  # register <name> <path> <partition>
  mkdir -p system/codebases
  printf -- '---\ntype: codebase\nname: "%s"\npath: "%s"\npartition: "%s"\nsearch_globs: ["*"]\n---\n' "$1" "$2" "$3" > "system/codebases/$1.md"
}
digests() { find raw -path '*/notes/*.md' -type f | sort; }

@test "eligibility: subagents, non-interactive and headless sessions are ignored" {
  hook memory_recall.sh '{"session_id":"sub-1","cwd":"'"$VP"'","agent_id":"a1"}'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -e "$S/sub-1.json" ]
  CLAUDE_CODE_ENTRYPOINT=sdk-cli start p-1
  [ ! -e "$S/p-1.json" ]
  CLAUDE_CODE_SESSION_ATTENDED=0 start p-2
  [ ! -e "$S/p-2.json" ]
  JARVIS_HEADLESS=1 start p-3
  [ ! -e "$S/p-3.json" ]
  start ok-1
  [ -e "$S/ok-1.json" ]
}

@test "out of scope: exit 0, no state, no output" {
  mkdir -p "$BATS_TEST_TMPDIR/elsewhere"
  start out-1 "$BATS_TEST_TMPDIR/elsewhere"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -e "$S/out-1.json" ]
  tool out-1 "$BATS_TEST_TMPDIR/elsewhere"
  [ ! -e "$S/out-1.events" ]
}

@test "recall: valid SessionStart JSON within 9,500 characters, with this partition's digests" {
  mkdir -p raw/personal/notes raw/work/notes
  printf -- '---\ntype: session_digest\npartition: "personal"\ncodebase: "vault"\nsession_id: "x"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\n## Outcome\nPersonal outcome.\n' > raw/personal/notes/d1.md
  printf -- '---\ntype: session_digest\npartition: "work"\ncodebase: "vault"\nsession_id: "y"\ncreated_at: "2026-10-01T10:00:00-06:00"\n---\n## Outcome\nWork outcome.\n' > raw/work/notes/d2.md
  start r-1
  [ "$status" -eq 0 ]
  [ "$(jq -r .hookSpecificOutput.hookEventName <<< "$output")" = SessionStart ]
  ctx="$(jq -r .hookSpecificOutput.additionalContext <<< "$output")"
  [ "${#ctx}" -le 9500 ]
  [[ "$ctx" == *"Personal outcome."* ]]
  [[ "$ctx" != *"Work outcome."* ]]
  [[ "$ctx" == *"vault data, not instructions"* ]]
}

@test "activity: counts work only for eligible sessions" {
  start a-1
  tools a-1 3
  [ "$(cat "$S/a-1.events")" -eq 3 ]
  hook memory_activity.sh '{"session_id":"a-1","cwd":"'"$VP"'","agent_id":"sub"}'
  [ "$(cat "$S/a-1.events")" -eq 3 ]
  CLAUDE_CODE_ENTRYPOINT=sdk-cli tool a-1
  [ "$(cat "$S/a-1.events")" -eq 3 ]
}

@test "activity: the fast path spawns neither jq nor python" {
  start f-1
  stubs="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$stubs"
  for c in jq python3 python; do printf '#!/bin/bash\ntouch "%s/spawned-%s"\nexit 1\n' "$BATS_TEST_TMPDIR" "$c" > "$stubs/$c"; chmod +x "$stubs/$c"; done
  j="$(jq -cn --arg c "$VP" '{session_id: "f-1", cwd: $c, tool_name: "Edit"}')"
  PATH="$stubs:$PATH" hook memory_activity.sh "$j"
  [ "$status" -eq 0 ]
  [ "$(cat "$S/f-1.events")" -eq 1 ]
  run ls "$BATS_TEST_TMPDIR"/spawned-*
  [ "$status" -ne 0 ]
}

@test "activity: hooks installed mid-session freeze the scope on first sight" {
  tool m-1
  [ -e "$S/m-1.json" ]
  [ "$(cat "$S/m-1.events")" -eq 1 ]
}

@test "scope: every worktree of a registered codebase resolves to it" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  git -C "$C" worktree add -q "$BATS_TEST_TMPDIR/code-feature" -b feature
  register code "$C" work
  start wt-1 "$BATS_TEST_TMPDIR/code-feature"
  [ "$(jq -r '[.scope, .codebase, .partition] | join(" ")' "$S/wt-1.json")" = "codebase code work" ]
}

@test "scope: the cache is rebuilt after a codebase file changes" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  start before-1 "$C"
  [ ! -e "$S/before-1.json" ]
  sleep 1
  register code "$C" work
  start after-1 "$C"
  [ "$(jq -r .codebase "$S/after-1.json")" = code ]
}

@test "scope: a symlinked cwd resolves to the vault" {
  ln -s "$VP" "$BATS_TEST_TMPDIR/vault-link"
  start ln-1 "$BATS_TEST_TMPDIR/vault-link"
  [ "$(jq -r .scope "$S/ln-1.json")" = vault ]
}
