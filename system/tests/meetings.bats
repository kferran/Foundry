#!/usr/bin/env bats
# Meetings (meetings spec §6): the Drive fetch with a stubbed claude, drops, the pre-commit hook and the units.
load helpers

D=mcp__claude_ai_Google_Drive
OLD=2026-10-01T09:00:00Z

setup() {
  make_vault
  cd "$V"
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_meetings"
  unset CLAUDE_CONFIG_DIR
  mkdir -p "$HOME/.claude"
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_CWD="$BATS_TEST_TMPDIR/cwd" STUB_STREAMS="$BATS_TEST_TMPDIR/streams"
  mkdir -p "$STUB_STREAMS" system/logs
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  system/scripts/vault_index.py set system/config.md meetings_enabled true > /dev/null
  MF="$V/system/scripts/meetings_fetch.sh"
  LOG="system/logs/meetings_fetch-$(TZ=America/Denver date +%Y-%m).jsonl"
}

# doc <id> [title] [modifiedTime] [createdTime]: one listed file, as the search result carries it.
doc() {
  jq -cn --arg id "$1" --arg t "${2:-Weekly sync - 2026/10/01 09:00 MDT - Notes by Gemini}" --arg m "${3:-$OLD}" \
    --arg c "${4:-$OLD}" '{id: $id, title: $t, createdTime: $c, modifiedTime: $m, mimeType: "application/vnd.google-apps.document"}'
}

# search_says <file json…>: a search session that lists those files.
search_says() {
  local files
  files="$(printf '%s\n' "$@" | jq -cs .)"
  {
    printf '{"type":"system","subtype":"init","tools":["ToolSearch"]}\n'
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    printf '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":[{"type":"tool_reference","tool_name":"%s__search_files"}]}]}}\n' "$D"
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2","name":"%s__search_files","input":{"query":"q"}}]}}\n' "$D"
    jq -cn --argjson f "$files" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2", content: "<persisted-output>…"}]}, tool_use_result: {structuredContent: {files: $f}}}'
    printf '{"type":"result","subtype":"success","is_error":false,"num_turns":3}\n'
  } > "$STUB_STREAMS/search.jsonl"
}

# read_says <id> [text] [id the session reads]: a read session for <id>.
read_says() {
  {
    printf '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}\n'
    jq -cn --arg id "${3:-$1}" --arg n "$D" '{type: "assistant", message: {content: [{type: "tool_use", id: "t2", name: ($n + "__read_file_content"), input: {fileId: $id}}]}}'
    jq -cn --arg text "${2:-## Notes for $1}" '{type: "user", message: {content: [{type: "tool_result", tool_use_id: "t2", content: "<persisted-output>…"}]}, tool_use_result: {structuredContent: {fileContent: $text, title: "x", viewUrl: "https://docs.example/x"}}}'
    printf '{"type":"result","subtype":"success","is_error":false,"num_turns":3}\n'
  } > "$STUB_STREAMS/read-$1.jsonl"
}

sessions() { grep -c -- '^--end--$' "$STUB_ARGS"; }

# session_arg <n> <flag>: the value after <flag> in the n-th session's argv.
session_arg() { awk -v n="$1" -v f="$2" '$0 == "--end--" { s++; next } s == n - 1 && p { print; exit } s == n - 1 && $0 == f { p = 1 }' "$STUB_ARGS"; }

# session_deny <n>: the n-th session's --disallowedTools list.
session_deny() { awk -v n="$1" '$0 == "--end--" { s++; p = 0; next } s == n - 1 && p { print } s == n - 1 && $0 == "--disallowedTools" { p = 1 }' "$STUB_ARGS"; }

@test "fetch: a search, then one confined read per listed Doc, written with a header" {
  search_says "$(doc FAKE-doc-0001)" "$(doc FAKE-doc-0002 'Retro - 2026/10/01 11:00 MDT - Notes by Gemini' "$OLD" 2026-10-01T10:00:00Z)"
  read_says FAKE-doc-0001 '## Weekly sync - Transcript'
  read_says FAKE-doc-0002
  run "$MF"
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 3 ]
  [ "$(session_arg 1 --allowedTools)" = "${D}__search_files" ]
  [ "$(session_arg 2 --allowedTools)" = "${D}__read_file_content" ]
  [ "$(session_arg 3 --allowedTools)" = "${D}__read_file_content" ]
  [ "$(system/scripts/vault_index.py field raw/meetings/FAKE-doc-0001.gdoc.md title)" = 'Weekly sync - 2026/10/01 09:00 MDT - Notes by Gemini' ]
  [ "$(system/scripts/vault_index.py field raw/meetings/FAKE-doc-0001.gdoc.md modified_time)" = "$OLD" ]
  [ "$(tail -n 1 raw/meetings/FAKE-doc-0001.gdoc.md)" = '## Weekly sync - Transcript' ]
  [ "$(jq -c '[.step, .doc, .exit]' "$LOG" | tr '\n' ' ')" = '["search","search",0] ["read","FAKE-doc-0001",0] ["read","FAKE-doc-0002",0] ' ]
  [ -s system/logs/meetings_fetch.since ]
}

@test "fetch: a Doc listed twice (two search calls or pages) is read once" {
  search_says "$(doc FAKE-doc-0001)" "$(doc FAKE-doc-0001)" "$(doc FAKE-doc-0002)"
  read_says FAKE-doc-0001
  read_says FAKE-doc-0002
  run "$MF"
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 3 ]
  [ "$(jq -c 'select(.step == "read") | .doc' "$LOG" | tr '\n' ' ')" = '"FAKE-doc-0001" "FAKE-doc-0002" ' ]
}

@test "fetch: a search result in another shape fails closed with exit 1 and keeps .since; an empty files list is fine" {
  search_says "$(doc FAKE-doc-0001)"
  cp "$STUB_STREAMS/search.jsonl" "$BATS_TEST_TMPDIR/good.jsonl"
  for f in '.tool_use_result = [{"type": "text", "text": "x"}]' '.tool_use_result = {"structuredContent": {"items": []}}' \
           '.tool_use_result.structuredContent.files[0] |= del(.createdTime)' 'empty'; do
    jq -c "if .tool_use_result then $f else . end" "$BATS_TEST_TMPDIR/good.jsonl" > "$STUB_STREAMS/search.jsonl"
    run "$MF"
    [ "$status" -eq 1 ]
    [ ! -e system/logs/meetings_fetch.since ]
  done
  [ "$(jq -c 'select(.step == "search") | .exit' "$LOG" | tr '\n' ' ')" = '1 1 1 1 ' ]
  search_says
  run "$MF"
  [ "$status" -eq 0 ]
  [ -s system/logs/meetings_fetch.since ]
}

@test "fetch: a filter that fails stops the fetch with exit 1, logged, and keeps .since" {
  search_says "$(doc FAKE-doc-0001)"
  read_says FAKE-doc-0001
  printf 'keep\n' > system/logs/meetings_fetch.since
  rm -f system/index.db
  mkdir system/index.db
  run "$MF"
  [ "$status" -eq 1 ]
  [ "$(sessions)" -eq 1 ]
  [ "$(cat system/logs/meetings_fetch.since)" = keep ]
  [ "$(jq -c 'select(.step == "search") | [.exit, (.reason | startswith("filter: "))]' "$LOG" | tail -n 1)" = '[1,true]' ]
}

@test "fetch: a second read call for another Doc fails the session even without a result" {
  search_says "$(doc FAKE-doc-0001)"
  read_says FAKE-doc-0001
  sed -i '$i {"type":"assistant","message":{"content":[{"type":"tool_use","id":"t3","name":"mcp__claude_ai_Google_Drive__read_file_content","input":{"fileId":"FAKE-other"}}]}}' "$STUB_STREAMS/read-FAKE-doc-0001.jsonl"
  run "$MF"
  [ "$status" -eq 0 ]
  [ ! -e raw/meetings/FAKE-doc-0001.gdoc.md ]
  [ "$(jq -c 'select(.step == "read") | .exit' "$LOG")" = 7 ]
}

@test "fetch: an allow rule for every Drive tool stops the fetch before claude runs" {
  for r in mcp__claude_ai_Google_Drive 'mcp__claude_ai_Google_Drive__*'; do
    jq -cn --arg r "$r" '{permissions: {allow: [$r]}}' > "$HOME/.claude/settings.json"
    rm -f "$STUB_ARGS"
    run "$MF"
    [ "$status" -eq 1 ]
    [[ "$output" == *"allow rule '$r'"* ]]
    [ ! -e "$STUB_ARGS" ]
  done
}

@test "fetch: --check runs the search only and reports the count" {
  search_says "$(doc FAKE-doc-0001)" "$(doc FAKE-doc-0002)"
  run "$MF" --check
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 1 ]
  [[ "$output" == *"the search listed 2 Docs"* ]]
  [ ! -e system/logs/meetings_fetch.since ]
  run "$MF" --bogus
  [ "$status" -eq 2 ]
}

@test "fetch: every session is confined: dontAsk, the other Drive tools and the user's allow rules denied, hooks off, a fresh /tmp directory" {
  printf '%s\n' '{"permissions":{"allow":["mcp__claude_ai_Gmail__send_message","mcp__claude_ai_Google_Drive__read_file_content"]}}' > "$HOME/.claude/settings.json"
  export STUB_MCP_LIST="$(printf '%s\n' 'claude.ai Google Drive: https://d/mcp - ok Connected' 'claude.ai Gmail: https://g/mcp - ok Connected')"
  search_says "$(doc FAKE-doc-0001)"
  read_says FAKE-doc-0001
  run "$MF"
  [ "$status" -eq 0 ]
  for n in 1 2; do
    [ "$(session_arg "$n" --permission-mode)" = dontAsk ]
    [ "$(session_arg "$n" --output-format)" = stream-json ]
    [ "$(session_arg "$n" --settings | jq -c '[.disableAllHooks, [.deniedMcpServers[].serverName]]')" = '[true,["claude.ai Gmail"]]' ]
    deny="$(session_deny "$n")"
    for t in Bash Read Write Edit WebFetch mcp__claude_ai_Gmail__send_message "${D}__create_file" "${D}__update_file" \
        "${D}__copy_file" "${D}__share_file" "${D}__trash_file" "${D}__download_file_content" \
        "${D}__get_file_permissions" "${D}__list_recent_files" "${D}__get_file_metadata"; do
      grep -qx -- "$t" <<< "$deny"
    done
  done
  grep -qx -- "${D}__read_file_content" <<< "$(session_deny 1)"
  grep -qx -- "${D}__search_files" <<< "$(session_deny 2)"
  run grep -qx -- "${D}__read_file_content" <<< "$(session_deny 2)"
  [ "$status" -eq 1 ]
  [ "$(sort -u "$STUB_CWD" | wc -l)" -eq 2 ]
  while IFS= read -r d; do
    [[ "$d" == /tmp/* ]]
    [ ! -e "$d" ]
  done < "$STUB_CWD"
}

@test "fetch: the search window starts 24 hours before .since, or 24 hours ago" {
  search_says
  printf '2026-10-05T12:00:00-06:00\n' > system/logs/meetings_fetch.since
  run "$MF"
  [ "$status" -eq 0 ]
  grep -qF "createdTime > '2026-10-04T18:00:00Z'" "$STUB_ARGS"
  grep -qF "mimeType = 'application/vnd.google-apps.document'" "$STUB_ARGS"
  [ "$(cat system/logs/meetings_fetch.since)" != '2026-10-05T12:00:00-06:00' ]
  rm system/logs/meetings_fetch.since "$STUB_ARGS"
  run "$MF"
  [ "$status" -eq 0 ]
  grep -qE "createdTime > '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'" "$STUB_ARGS"
  [ ! -e system/logs/meetings_fetch.since.tmp ]
}

@test "fetch: the filter keeps only new, settled Gemini Docs, the 10 oldest first" {
  docs=()
  for i in $(seq -w 1 12); do docs+=("$(doc "FAKE-new-$i" '' "$OLD" "2026-10-01T09:$i:00Z")"); read_says "FAKE-new-$i"; done
  docs+=("$(doc FAKE-title 'Weekly sync notes')" "$(doc FAKE-fresh '' "$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%SZ)")")
  docs+=("$(doc FAKE-known)" "$(doc FAKE-pending)" "$(doc FAKE-quarantined)" "$(doc FAKE-failing)" "$(doc FAKE-dup)" "$(doc 'FAKE/../x')")
  mkdir -p wiki/work/meetings raw/meetings system/quarantine/meetings
  printf -- '---\ntype: meeting\ntitle: "W"\ndate: "2026-10-01"\nstart: "2026-10-01T09:00:00-06:00"\npartition: work\nsource: "gdoc:FAKE-known"\ntranscript: "[[w.transcript]]"\nstatus: deprecated\n---\n# W\n' > wiki/work/meetings/w.md
  : > raw/meetings/FAKE-pending.gdoc.md
  : > system/quarantine/meetings/FAKE-quarantined.gdoc.md
  for i in 1 2 3; do printf '{"step":"read","doc":"FAKE-failing","exit":6}\n' >> "$LOG"; done
  printf '{"step":"import","doc":"FAKE-dup","exit":0,"skipped":true}\n' >> "$LOG"
  search_says "${docs[@]}"
  run "$MF"
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 11 ]
  [ "$(grep -o 'fileId "[^"]*"' "$STUB_ARGS" | cut -d'"' -f2 | tr '\n' ' ')" = "$(printf 'FAKE-new-%02d ' $(seq 1 10))" ]
  [ ! -e system/logs/meetings_fetch.since ]
}

@test "fetch: a read of a Doc that was not requested fails that session with exit 7, writes nothing and alerts" {
  search_says "$(doc FAKE-doc-0001)"
  read_says FAKE-doc-0001 'text' FAKE-other
  run "$MF"
  [ "$status" -eq 0 ]
  [ ! -e raw/meetings/FAKE-doc-0001.gdoc.md ]
  [ ! -e raw/meetings/FAKE-other.gdoc.md ]
  [ "$(jq -c 'select(.step == "read") | .exit' "$LOG")" = 7 ]
  grep -q '\[meetings\].*FAKE-other' system/logs/alerts_*.md
}

@test "fetch: an unexpected tool exits 7 with an alert and keeps .since" {
  search_says "$(doc FAKE-doc-0001)"
  sed -i "s/\"name\":\"${D}__search_files\"/\"name\":\"mcp__claude_ai_Gmail__send_message\"/" "$STUB_STREAMS/search.jsonl"
  printf 'keep\n' > system/logs/meetings_fetch.since
  run "$MF"
  [ "$status" -eq 7 ]
  [ "$(sessions)" -eq 1 ]
  [ "$(cat system/logs/meetings_fetch.since)" = keep ]
  grep -q '\[meetings\].*mcp__claude_ai_Gmail__send_message' system/logs/alerts_*.md
}

@test "fetch: no connector exits 3 and a connector error 6, each alerted once a day" {
  printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{}}]}}' \
    '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"No matching deferred tools found"}]}}' \
    '{"type":"result","subtype":"success","is_error":false,"num_turns":4}' > "$STUB_STREAMS/search.jsonl"
  run "$MF"
  [ "$status" -eq 3 ]
  run "$MF"
  [ "$status" -eq 3 ]
  [ "$(grep -c '\[meetings\].*exit 3' system/logs/alerts_*.md)" -eq 1 ]
  search_says
  sed -i 's/"tool_use_id":"t2","content":"<persisted-output>…"/"tool_use_id":"t2","is_error":true,"content":"rate limited"/' "$STUB_STREAMS/search.jsonl"
  run "$MF"
  [ "$status" -eq 6 ]
  [[ "$output" == *"rate limited"* ]]
  [ "$(jq -c 'select(.step == "search") | .exit' "$LOG" | tr '\n' ' ')" = '3 3 6 ' ]
}

@test "fetch: a ToolSearch reply that only repeats the Drive tool's name in its text is no connector, exit 3 (#38)" {
  printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{"query":"select:mcp__claude_ai_Google_Drive__search_files"}}]}}' \
    '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"No matching deferred tools found for select:mcp__claude_ai_Google_Drive__search_files"}]}}' \
    '{"type":"result","subtype":"success","is_error":false,"num_turns":4}' > "$STUB_STREAMS/search.jsonl"
  run "$MF"
  [ "$status" -eq 3 ]
}

@test "fetch: a search that fails with exit 1 is alerted once a day, and so is a failed filter (#39)" {
  search_says "$(doc FAKE-doc-0001)"
  jq -c 'if .tool_use_result then .tool_use_result = {"structuredContent": {"items": []}} else . end' \
    "$STUB_STREAMS/search.jsonl" > "$BATS_TEST_TMPDIR/odd.jsonl"
  cp "$BATS_TEST_TMPDIR/odd.jsonl" "$STUB_STREAMS/search.jsonl"
  run "$MF"
  [ "$status" -eq 1 ]
  run "$MF"
  [ "$status" -eq 1 ]
  [ "$(grep -c '\[meetings\] Drive fetch failed (exit 1):.*files list' system/logs/alerts_*.md)" -eq 1 ]
  rm system/logs/alerts_*.md
  search_says "$(doc FAKE-doc-0001)"
  rm -f system/index.db
  mkdir system/index.db
  run "$MF"
  [ "$status" -eq 1 ]
  grep -q '\[meetings\] Drive fetch failed (exit 1): filter: ' system/logs/alerts_*.md
}

@test "fetch: a fetch stopped mid-session removes that session's /tmp directory (#40)" {
  search_says
  STUB_SLEEP=30 setsid "$MF" > /dev/null 2>&1 &
  pid=$!
  for i in $(seq 1 100); do [ -s "$STUB_CWD" ] && break; sleep 0.1; done
  [ -s "$STUB_CWD" ]
  d="$(head -n 1 "$STUB_CWD")"
  [ -d "$d" ]
  kill -TERM -- "-$pid"
  wait "$pid" || true
  [ ! -e "$d" ]
}

@test "fetch: the third failed read of a Doc is alerted once and the Doc is skipped from then on" {
  search_says "$(doc FAKE-doc-0001)"
  read_says FAKE-doc-0001 'x' FAKE-other
  for i in 1 2 3 4; do
    run "$MF"
    [ "$status" -eq 0 ]
  done
  [ "$(sessions)" -eq 7 ]
  [ "$(grep -c '\[meetings\] FAKE-doc-0001 failed 3 reads' system/logs/alerts_*.md)" -eq 1 ]
}

@test "fetch: a timeout exits 4, a missing claude 127, a failing claude 1" {
  search_says
  STUB_SLEEP=5 MEETINGS_TIMEOUT=1 run "$MF"
  [ "$status" -eq 4 ]
  CLAUDE_BIN="$BATS_TEST_TMPDIR/no-such-claude" run "$MF"
  [ "$status" -eq 127 ]
  : > "$STUB_STREAMS/search.jsonl"
  STUB_RC=1 run "$MF"
  [ "$status" -eq 1 ]
}

@test "fetch: a busy lock, a disabled config or a client does nothing" {
  search_says
  flock system/meetings.lock -c "\"$MF\""
  [ ! -e "$STUB_ARGS" ]
  system/scripts/vault_index.py set system/config.md meetings_enabled false > /dev/null
  run "$MF"
  [ "$status" -eq 0 ]
  system/scripts/vault_index.py set system/config.md meetings_enabled true > /dev/null
  system/scripts/vault_index.py set system/config.md machine_role client > /dev/null
  run "$MF"
  [ "$status" -eq 0 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "drops: the template carries the drop folders, and intake imports a settled drop and deletes it" {
  [ -f "$REPO/meetings/drop/work/.gitkeep" ]
  [ -f "$REPO/meetings/drop/personal/.gitkeep" ]
  [ -z "$(git -C "$REPO" check-ignore meetings/drop/work/call.vtt)" ]
  mkdir -p meetings/drop/work
  f="meetings/drop/work/2026-10-05 1500 Vendor call.vtt"
  printf 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v Avery Sample>Hello.</v>\n' > "$f"
  touch -d '10 minutes ago' "$f"
  CLAUDE_BIN="$REPO/system/tests/stub_claude" run system/scripts/intake_daemon.sh
  [ "$status" -eq 0 ]
  [ "$(system/scripts/vault_index.py field wiki/work/meetings/2026-10-05-1500-vendor-call.md attendees)" = 'Avery Sample' ]
  [ -f wiki/work/meetings/2026-10-05-1500-vendor-call.transcript.md ]
  [ -f raw/work/notes/2026-10-05-1500-vendor-call.meeting-input.md ]
  [ ! -e "$f" ]
}

@test "drops: Finder and Explorer system files in a drop folder are gitignored, transcripts and .gitkeep are not" {
  for f in .DS_Store ._call.vtt Thumbs.db desktop.ini; do
    git -C "$REPO" check-ignore -q "meetings/drop/work/$f"
  done
  for f in .gitkeep call.vtt; do
    run git -C "$REPO" check-ignore -q --no-index "meetings/drop/personal/$f"
    [ "$status" -eq 1 ]
  done
}

# hook_commit <path> <content>: stage one file under the pre-commit hook and try to commit it.
hook_commit() {
  mkdir -p "$(dirname "$1")"
  printf '%b' "$2" > "$1"
  git add -- "$1"
  run git commit -qm "drop"
}

@test "pre-commit: a drop with another file type or a named secret is refused" {
  cp -r "$REPO/.githooks" .githooks
  git config core.hooksPath .githooks
  hook_commit meetings/drop/work/slides.pdf 'x'
  [ "$status" -eq 1 ]
  [[ "$output" == *"meetings/drop/work/slides.pdf is not a transcript"* ]]
  git rm -q --cached meetings/drop/work/slides.pdf
  hook_commit meetings/drop/personal/call.txt 'Avery Sample: the key is AKIAIOSFODNN7EXAMPLE\ntoken = hunter2\n'
  [ "$status" -eq 1 ]
  [[ "$output" == *"meetings/drop/personal/call.txt holds a secret (assignment,aws_key)"* ]]
  [ -z "$(git log --oneline 2>/dev/null)" ]
}

@test "pre-commit: a Teams-style VTT whose cue IDs look high-entropy is accepted, and so is .gitkeep" {
  cp -r "$REPO/.githooks" .githooks
  git config core.hooksPath .githooks
  hook_commit meetings/drop/work/.gitkeep ''
  [ "$status" -eq 0 ]
  hook_commit meetings/drop/work/Standup.vtt 'WEBVTT\n\n9f8Qz2LmX4vB7nR1tY6wK3pJ5sD0hG8cE2aZ/17-1\n00:00:01.000 --> 00:00:04.000\n<v Avery Sample>Hello.</v>\n'
  [ "$status" -eq 0 ]
  [ "$(git log --format=%s | wc -l)" -eq 2 ]
}

@test "pre-commit: a spoken 'password: …' is accepted, an api_key = … assignment is refused" {
  cp -r "$REPO/.githooks" .githooks
  git config core.hooksPath .githooks
  hook_commit meetings/drop/work/call.txt 'Avery: reset your password: it expired\n'
  [ "$status" -eq 0 ]
  hook_commit meetings/drop/work/env.txt 'api_key = example-value-1234\n'
  [ "$status" -eq 1 ]
  [[ "$output" == *"meetings/drop/work/env.txt holds a secret (assignment)"* ]]
}
