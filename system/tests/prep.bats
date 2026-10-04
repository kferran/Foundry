#!/usr/bin/env bats
# brief_prep.sh and debrief_prep.sh (spec §6.5).
load helpers

setup() {
  make_vault
  cd "$V"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  # The calendar comes from calendar_fetch.sh, whose claude is the calendar stub (never the real one).
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_calendar"
  # A temporary HOME hides ~/.gitconfig, so the test commits need an identity of their own.
  export GIT_AUTHOR_NAME=test GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
  export JARVIS_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" JARVIS_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_STREAM="$BATS_TEST_TMPDIR/stream.jsonl"
  calendar_says '{"status":"ok","reason":"","events":[{"start_date":"2026-10-01","start_time":"09:00","end_date":"2026-10-01","end_time":"09:30","title":"Standup"}]}'
  export PATH="$STUBS:$PATH"
  BP="$V/system/scripts/brief_prep.sh"
  DP="$V/system/scripts/debrief_prep.sh"
  IN=system/logs/inputs/2026-10-01
  mkdir -p system/logs
}

# calendar_says <structured output json> [tool…]: what the stubbed calendar session returns.
calendar_says() {
  local out="$1" t
  shift
  {
    printf '{"type":"system","subtype":"init","tools":[]}\n'
    for t in "${@:-ToolSearch}"; do
      printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"%s","input":{}}]}}\n' "$t"
    done
    printf '{"type":"result","subtype":"success","is_error":false,"num_turns":4,"total_cost_usd":0.2,"permission_denials":[],"structured_output":%s}\n' "$out"
  } > "$STUB_STREAM"
}

commit_at() {  # <repo> <iso date> <message> [author email]
  GIT_AUTHOR_DATE="$2" GIT_COMMITTER_DATE="$2" GIT_AUTHOR_EMAIL="${4:-test@example.com}" \
    git -C "$1" commit -q --allow-empty -m "$3"
}

digest() {  # <path> <partition> <created_at> <body>
  mkdir -p "$(dirname "$1")"
  printf -- '---\ntype: session_digest\npartition: %s\ncodebase: "vault"\nsession_id: "s"\ncreated_at: "%s"\n---\n%s\n' "$2" "$3" "$4" > "$1"
}

codebase() {  # <name> <path>
  mkdir -p system/codebases
  printf -- '---\ntype: codebase\nname: "%s"\npath: "%s"\npartition: "work"\nsearch_globs: ["*.md"]\n---\n' "$1" "$2" > "system/codebases/$1.md"
}

@test "brief_prep: calendar and yesterday's focus are written" {
  printf '[09:00:00] Kafka\n' > system/logs/obsidian_focus_2026-09-30.log
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/calendar.tsv")" = "$(printf '2026-10-01\t09:00\t2026-10-01\t09:30\tStandup')" ]
  grep -qx '# Focus: 2026-09-30' "$IN/focus_yesterday.md"
  grep -qx '| Kafka | 1 | 0.5 |' "$IN/focus_yesterday.md"
  [ ! -e "$IN/unavailable.md" ]
}

@test "brief_prep: a failed calendar fetch is recorded, leaves no partial file, and still exits 0" {
  : > "$STUB_STREAM"
  STUB_RC=1 run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/calendar.tsv" ]
  grep -q '^- brief_prep: calendar: calendar_fetch.sh failed (exit 1; see system/logs/inputs/2026-10-01/prep_errors.log)$' "$IN/unavailable.md"
  grep -q '^calendar_fetch: ' "$IN/prep_errors.log"
  grep -qx -- '- brief_prep: focus_yesterday: no focus log for 2026-09-30' "$IN/unavailable.md"
}

@test "brief_prep: each calendar failure gets its own Unavailable Sources line" {
  check() {  # <expected line>
    run "$BP" 2026-10-01
    [ "$status" -eq 0 ]
    grep -qxF -- "- brief_prep: calendar: $1" "$IN/unavailable.md"
  }
  calendar_says '{"status":"no_tool","reason":"","events":[]}'
  check 'no Google Calendar connector reachable (connect it at claude.ai with the account this machine'"'"'s claude is logged in with, then re-run /setup phase 6)'
  calendar_says '{"status":"tool_error","reason":"rate limited","events":[]}'
  check 'the connector returned an error: rate limited (if it persists, reconnect Google Calendar at claude.ai)'
  calendar_says '{"status":"ok","reason":"","events":[{"start_date":"2026-10-02","start_time":"","end_date":"2026-10-02","end_time":"","title":"x"}]}'
  check 'the connector returned an unreadable event list (see system/logs/calendar_fetch-2026-10.jsonl)'
  calendar_says '{"status":"too_many","reason":"140","events":[]}'
  check 'more than 100 events that day; not listed'
  calendar_says '{"status":"ok","reason":"","events":[]}' ToolSearch mcp__claude_ai_Gmail__send_message
  check 'the fetch session used an unexpected tool; nothing was written (see system/logs/alerts_'"$(TZ=America/Denver date +%F)"'.md)'
  STUB_SLEEP=5 CALENDAR_TIMEOUT=1 check 'the connector timed out'
  CLAUDE_BIN="$BATS_TEST_TMPDIR/no-such-claude" check 'claude is not on PATH'
}

@test "brief_prep: the default date is today in the configured timezone" {
  run "$BP"
  [ "$status" -eq 0 ]
  [ -d "system/logs/inputs/$(TZ=America/Denver date +%F)" ]
}

@test "prep scripts: a bad date or extra arguments exit 2 and write nothing" {
  for s in "$BP" "$DP"; do
    run "$s" 2026-13-01
    [ "$status" -eq 2 ]
    run "$s" 2026-10-01 extra
    [ "$status" -eq 2 ]
  done
  [ ! -e system/logs/inputs ]
}

@test "prep scripts: re-running one keeps the other's unavailable lines and never duplicates its own" {
  run "$DP" 2026-10-01
  run "$BP" 2026-10-01
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(grep -c -- '- debrief_prep: focus: no focus log for 2026-10-01' "$IN/unavailable.md")" -eq 1 ]
  [ "$(grep -c -- '- brief_prep: focus_yesterday: no focus log for 2026-09-30' "$IN/unavailable.md")" -eq 1 ]
}

@test "debrief_prep: git.md lists the vault's commits of that day in the configured timezone" {
  commit_at "$V" 2026-09-30T23:59:00-06:00 "day before"
  commit_at "$V" 2026-10-01T23:30:00-06:00 "late on the day"
  commit_at "$V" 2026-10-02T00:30:00-06:00 "day after"
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '## vault' "$IN/git.md"
  grep -qE '^- 23:30 [0-9a-f]+ late on the day$' "$IN/git.md"
  run grep -E 'day before|day after' "$IN/git.md"
  [ "$status" -eq 1 ]
}

@test "debrief_prep: the vault section lists commits from every author" {
  commit_at "$V" 2026-10-01T09:00:00-06:00 "mine"
  commit_at "$V" 2026-10-01T10:00:00-06:00 "from the other machine" other@example.com
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qE '^- 09:00 [0-9a-f]+ mine$' "$IN/git.md"
  grep -qE '^- 10:00 [0-9a-f]+ from the other machine$' "$IN/git.md"
}

@test "debrief_prep: codebase sections list only your commits on local branches" {
  C="$BATS_TEST_TMPDIR/app"
  git init -q "$C"
  git -C "$C" config user.email me@example.com
  git -C "$C" config user.name me
  commit_at "$C" 2026-10-01T10:00:00-06:00 "mine" me@example.com
  commit_at "$C" 2026-10-01T11:00:00-06:00 "a teammate's" other@example.com
  git -C "$C" checkout -q -b tmp
  commit_at "$C" 2026-10-01T12:00:00-06:00 "only on a remote" me@example.com
  git -C "$C" update-ref refs/remotes/origin/elsewhere HEAD
  git -C "$C" checkout -q -
  git -C "$C" branch -q -D tmp
  codebase app "$C"
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '## app' "$IN/git.md"
  grep -qE '^- 10:00 [0-9a-f]+ mine$' "$IN/git.md"
  run grep -E "teammate|only on a remote" "$IN/git.md"
  [ "$status" -eq 1 ]
}

@test "debrief_prep: a codebase without a repository is recorded, the rest still runs" {
  codebase gone /nonexistent
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- debrief_prep: git: codebase gone has no git repository at /nonexistent' "$IN/unavailable.md"
  grep -qx '## vault' "$IN/git.md"
  [ -f "$IN/digests.md" ]
  [ -f "$IN/focus.md" ]
}

@test "debrief_prep: digests.md holds that day's digests from every partition, oldest first" {
  digest raw/work/notes/w1.md work 2026-10-01T09:00:00-06:00 "Work digest."
  digest raw/personal/archive/p1.md personal 2026-10-01T08:00:00-06:00 "Personal digest."
  digest raw/work/notes/old.md work 2026-09-30T09:00:00-06:00 "Old digest."
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '## p1.md (personal, vault, 2026-10-01T08:00:00-06:00)' "$IN/digests.md"
  grep -qx '## w1.md (work, vault, 2026-10-01T09:00:00-06:00)' "$IN/digests.md"
  grep -qx 'Work digest.' "$IN/digests.md"
  run grep -E 'Old digest|type: session_digest' "$IN/digests.md"
  [ "$status" -eq 1 ]
  [ "$(grep -n 'p1.md' "$IN/digests.md" | cut -d: -f1)" -lt "$(grep -n 'w1.md' "$IN/digests.md" | cut -d: -f1)" ]
}

@test "debrief_prep: no digests and no focus data are stated, not left blank" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx 'No session digests.' "$IN/digests.md"
  grep -qx 'no focus data' "$IN/focus.md"
  grep -qx -- '- debrief_prep: focus: no focus log for 2026-10-01' "$IN/unavailable.md"
}

@test "debrief_prep: a failing index query is recorded and writes no digests.md" {
  mv system/scripts/vault_index.py system/scripts/vault_index_real.py
  printf '#!/bin/bash\n[[ "$1" == query ]] && exit 3\nexec "$(dirname "$0")/vault_index_real.py" "$@"\n' > system/scripts/vault_index.py
  chmod +x system/scripts/vault_index.py
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/digests.md" ]
  grep -q -- '^- debrief_prep: digests: index query failed' "$IN/unavailable.md"
}

@test "debrief_prep: a codebase whose git log fails is recorded, not reported as idle" {
  C="$BATS_TEST_TMPDIR/app"
  git init -q "$C"
  commit_at "$C" 2026-10-01T10:00:00-06:00 "mine"
  printf '1234567890123456789012345678901234567890\n' > "$C/.git/refs/heads/$(git -C "$C" branch --show-current)"
  codebase app "$C"
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- debrief_prep: git: git log failed for codebase app' "$IN/unavailable.md"
  run grep -x '## app' "$IN/git.md"
  [ "$status" -eq 1 ]
  grep -qx '## vault' "$IN/git.md"
}
