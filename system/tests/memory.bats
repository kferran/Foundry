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

@test "capture: an out-of-scope session writes nothing" {
  mkdir -p "$BATS_TEST_TMPDIR/elsewhere"
  stop out-2 $'<vault-digest>\n## Outcome\nx\n</vault-digest>' "$BATS_TEST_TMPDIR/elsewhere"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ -z "$(digests)" ]
  [ ! -e "$S/out-2.json" ]
}

@test "capture: no request below the work-event threshold, a request at it" {
  thresholds 5 0
  start c-1
  tools c-1 4
  stop c-1 "Done with that."
  [ -z "$output" ]
  tool c-1
  stop c-1 "Done with that."
  [ "$(jq -r .decision <<< "$output")" = block ]
  [[ "$(jq -r .reason <<< "$output")" == "Jarvis memory (not an error): please reply with a short session digest."* ]]
  [ "$(jq -r .awaiting_digest "$S/c-1.json")" = true ]
}

@test "capture: no request before digest_min_minutes have passed" {
  thresholds 1 20
  start t-1
  tools t-1 5
  stop t-1 "Done."
  [ -z "$output" ]
  jq '.started_at -= 1300' "$S/t-1.json" > "$S/t-1.json.new"
  mv "$S/t-1.json.new" "$S/t-1.json"
  stop t-1 "Done."
  [ "$(jq -r .decision <<< "$output")" = block ]
}

@test "capture: no request when the last message asks the user a question" {
  thresholds 1 0
  start q-1
  tools q-1 3
  stop q-1 "Which option do you want?   "
  [ -z "$output" ]
}

@test "capture: a requested digest is redacted and written with the sid8 name and valid frontmatter" {
  thresholds 1 0
  start abcdef12-3456
  tools abcdef12-3456 2
  stop abcdef12-3456 "Done."
  msg=$'Here it is.\n<vault-digest>\n## Outcome\nShipped the export job.\n## Facts learned\n- password: hunter2\n</vault-digest>'
  stop abcdef12-3456 "$msg"
  [ -z "$output" ]
  f="$(digests)"
  [ "$(wc -l <<< "$f")" -eq 1 ]
  [[ "$f" =~ ^raw/personal/notes/[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}-abcdef12-shipped-the-export-job\.md$ ]]
  run grep -c hunter2 "$f"
  [ "$output" = 0 ]
  grep -q '\[REDACTED' "$f"
  grep -qx 'redactions: "1"' "$f"
  grep -qE '^created_at: "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}"$' "$f"
  grep -qx 'codebase: "vault"' "$f"
  system/scripts/vault_index.py validate "$f"
  [ "$(cat "$S/abcdef12-3456.events")" -eq 0 ]
  [ "$(jq -r .awaiting_digest "$S/abcdef12-3456.json")" = false ]
}

@test "capture: an on-demand digest (no request first) is captured" {
  start od-1
  stop od-1 $'<vault-digest>\n## Outcome\nOn demand.\n</vault-digest>'
  [ "$(digests | wc -l)" -eq 1 ]
}

@test "capture: no digest after a request raises an alert and never asks twice in a row" {
  thresholds 1 0
  start n-1
  tools n-1 3
  stop n-1 "Done."
  [ "$(jq -r .decision <<< "$output")" = block ]
  stop n-1 "I would rather not."
  [ -z "$output" ]
  grep -q 'session n-1 did not return the requested digest' system/logs/alerts_*.md
  [ "$(jq -r .awaiting_digest "$S/n-1.json")" = false ]
}

@test "capture: an invalid session_id writes nothing" {
  start "../evil"
  stop "../evil" $'<vault-digest>\nx\n</vault-digest>'
  [ -z "$(digests)" ]
  run ls "$S"
  [ -z "$output" ]
}

@test "capture: two sessions in the same minute produce distinct files" {
  start aaaaaaaa-1
  start bbbbbbbb-1
  stop aaaaaaaa-1 $'<vault-digest>\n## Outcome\nSame text.\n</vault-digest>'
  stop bbbbbbbb-1 $'<vault-digest>\n## Outcome\nSame text.\n</vault-digest>'
  [ "$(digests | wc -l)" -eq 2 ]
}

@test "scope: frozen at SessionStart, so a later cd never moves the session" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  register code "$C" work
  start fz-1
  stop fz-1 $'<vault-digest>\n## Outcome\nFrozen.\n</vault-digest>' "$C"
  f="$(digests)"
  [[ "$f" == raw/personal/notes/* ]]
  grep -qx 'codebase: "vault"' "$f"
}

@test "capture: a worktree session's digest lands in its codebase's partition" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  git -C "$C" worktree add -q "$BATS_TEST_TMPDIR/code-feature" -b feature
  register code "$C" work
  start wt-2 "$BATS_TEST_TMPDIR/code-feature"
  stop wt-2 $'<vault-digest>\n## Outcome\nFrom a worktree.\n</vault-digest>' "$BATS_TEST_TMPDIR/code-feature"
  [[ "$(digests)" == raw/work/notes/* ]]
  grep -qx 'codebase: "code"' "$(digests)"
}

@test "capture: secrets in the first line don't land in the filename" {
  start secret-1
  msg=$'<vault-digest>\npassword: hunter2\n## Outcome\nWork done.\n</vault-digest>'
  stop secret-1 "$msg"
  f="$(digests)"
  [[ "$f" != *"hunter2"* ]]
  grep -q '\[REDACTED' "$f"
  [ -z "$(find "$VP/raw/personal/notes" -maxdepth 1 -name '.*' -type f)" ]
}

@test "crew sessions skip the attended check and the periodic request; marked digests carry task_id" {
  export JARVIS_CREW=1 JARVIS_TASK_ID=task-42 CLAUDE_CODE_SESSION_ATTENDED=0
  thresholds 1 0
  start crew-1
  tools crew-1 5
  stop crew-1 "Done."
  [ -z "$output" ]
  stop crew-1 $'<vault-digest>\n## Outcome\nTask done.\n</vault-digest>'
  grep -qx 'task_id: "task-42"' "$(digests)"
}

seed_digests() {
  mkdir -p raw/personal/notes raw/work/notes
  printf -- '---\ntype: session_digest\npartition: "personal"\ncodebase: "vault"\nsession_id: "x"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\n## Outcome\nPersonal outcome.\n' > raw/personal/notes/d1.md
  printf -- '---\ntype: session_digest\npartition: "work"\ncodebase: "code"\nsession_id: "y"\ncreated_at: "2026-10-01T10:00:00-06:00"\n---\n## Outcome\nWork outcome.\n' > raw/work/notes/d2.md
}

@test "recall: a re-entry (compact) from the vault keeps a codebase session's frozen scope" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  register code "$C" work
  seed_digests
  start wall-1 "$C"
  [[ "$(jq -r .hookSpecificOutput.additionalContext <<< "$output")" == *"Work outcome."* ]]
  start wall-1 "$VP"
  ctx="$(jq -r '.hookSpecificOutput.additionalContext // ""' <<< "$output")"
  [[ "$ctx" == *"Work outcome."* ]]
  [[ "$ctx" != *"Personal outcome."* ]]
  [[ "$ctx" != *"Scope: vault (personal)"* ]]
}

@test "recall: a re-entry from a codebase keeps the vault session's frozen scope" {
  C="$BATS_TEST_TMPDIR/code"
  repo "$C"
  register code "$C" work
  seed_digests
  start wall-2 "$VP"
  start wall-2 "$C"
  ctx="$(jq -r '.hookSpecificOutput.additionalContext // ""' <<< "$output")"
  [[ "$ctx" == *"Personal outcome."* ]]
  [[ "$ctx" != *"Work outcome."* ]]
}

@test "capture: a declined request is not re-asked until digest_min_minutes after the request" {
  thresholds 5 20
  start dc-1
  jq '.started_at -= 1300' "$S/dc-1.json" > "$S/dc-1.json.new"
  mv "$S/dc-1.json.new" "$S/dc-1.json"
  tools dc-1 5
  stop dc-1 "Done."
  [ "$(jq -r .decision <<< "$output")" = block ]
  stop dc-1 "I would rather not."
  [ -z "$output" ]
  tools dc-1 5
  stop dc-1 "Done again."
  [ -z "$output" ]
  [ "$(jq -r .awaiting_digest "$S/dc-1.json")" = false ]
  [ "$(cat system/logs/alerts_*.md | grep -c 'dc-1')" -eq 1 ]
  jq '.last_request_at -= 1300' "$S/dc-1.json" > "$S/dc-1.json.new"
  mv "$S/dc-1.json.new" "$S/dc-1.json"
  stop dc-1 "Done once more."
  [ "$(jq -r .decision <<< "$output")" = block ]
}

@test "capture: a message that only mentions the tags is not a digest" {
  thresholds 1 0
  start mt-1
  tools mt-1 3
  stop mt-1 'Reply with anything between `<vault-digest>` and `</vault-digest>` markers and I will save it.'
  [ -z "$(digests)" ]
  [ "$(cat "$S/mt-1.events")" -eq 3 ]
  [ "$(jq -r .last_digest_at "$S/mt-1.json")" -eq 0 ]
}

@test "capture: an empty digest block writes nothing" {
  start em-1
  tools em-1 2
  stop em-1 '<vault-digest></vault-digest>'
  [ -z "$(digests)" ]
  stop em-1 $'<vault-digest>\n  \n</vault-digest>'
  [ -z "$(digests)" ]
  [ "$(cat "$S/em-1.events")" -eq 2 ]
}

@test "capture: a block with the tags on their own lines is captured" {
  start ol-1
  stop ol-1 $'Here you go.\n<vault-digest>\n## Outcome\nOwn lines.\n</vault-digest>\nThanks.'
  [ "$(digests | wc -l)" -eq 1 ]
}
