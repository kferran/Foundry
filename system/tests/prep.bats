#!/usr/bin/env bats
# brief_prep.sh and debrief_prep.sh (spec §6.5).
load helpers

setup() {
  make_vault
  cd "$V"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  # The calendar comes from calendar_fetch.sh, whose claude is the calendar stub (never the real one).
  export HOME="$BATS_TEST_TMPDIR/home" CLAUDE_BIN="$REPO/system/tests/stub_claude_connector"
  # A temporary HOME hides ~/.gitconfig, so the test commits need an identity of their own.
  export GIT_AUTHOR_NAME=test GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
  export FOUNDRY_MANAGED_SETTINGS="$BATS_TEST_TMPDIR/managed.json" FOUNDRY_MANAGED_SETTINGS_DIR="$BATS_TEST_TMPDIR/managed.d"
  export STUB_STREAM="$BATS_TEST_TMPDIR/stream.jsonl"
  calendar_says '{"status":"ok","reason":"","events":[{"start_date":"2026-10-01","start_time":"09:00","end_date":"2026-10-01","end_time":"09:30","title":"Standup"}]}'
  export PATH="$STUBS:$PATH"
  BP="$V/system/scripts/brief_prep.sh"
  DP="$V/system/scripts/debrief_prep.sh"
  IN=system/logs/inputs/2026-10-01
  mkdir -p system/logs
}

# calendar_says <structured output json> [tool…]: what the stubbed calendar session returns (default tools: ToolSearch
# and list_events).
calendar_says() {
  local out="$1" t
  shift
  {
    printf '{"type":"system","subtype":"init","tools":[]}\n'
    (( $# )) || set -- ToolSearch mcp__claude_ai_Google_Calendar__list_events
    for t in "$@"; do
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

@test "brief_prep: the calendar is written" {
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/calendar.tsv")" = "$(printf '2026-10-01\t09:00\t2026-10-01\t09:30\tStandup')" ]
  [ ! -e "$IN/unavailable.md" ]
}

@test "brief_prep: a failed calendar fetch is recorded, leaves no partial file, and still exits 0" {
  : > "$STUB_STREAM"
  STUB_RC=1 run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/calendar.tsv" ]
  grep -q '^- brief_prep: calendar: calendar_fetch.sh failed (exit 1; see system/logs/inputs/2026-10-01/prep_errors.log)$' "$IN/unavailable.md"
  grep -q '^calendar_fetch: ' "$IN/prep_errors.log"
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

@test "brief_prep: sources.md lists every source with ok, off or failed and the since date from the smoke log (connector health spec §2)" {
  system/scripts/vault_index.py set system/config.md triage_enabled true > /dev/null
  printf '%s\n' '{"time":"2026-09-30T05:45:00-06:00","source":"calendar","exit":3,"reason":"auth: no Google Calendar connector reachable"}' \
    '{"time":"2026-10-01T05:45:00-06:00","source":"triage","exit":0,"reason":""}' > system/logs/smoke-2026-10.jsonl
  calendar_says '{"status":"no_tool","reason":"","events":[]}'
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF -- '- calendar: failed: auth: no Google Calendar connector reachable (since 2026-09-30); expired: Google connector; renew: reconnect it at claude.ai, Settings, Connectors' "$IN/sources.md"
  grep -qxF -- '- meetings: off' "$IN/sources.md"
  grep -qxF -- '- triage: ok' "$IN/sources.md"
  grep -qxF -- '- notify: off' "$IN/sources.md"
  calendar_says '{"status":"ok","reason":"","events":[]}'
  run "$BP" 2026-10-01
  grep -qxF -- '- calendar: ok' "$IN/sources.md"
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
  codebase gone /nonexistent
  : > "$STUB_STREAM"
  run "$DP" 2026-10-01
  STUB_RC=1 run "$BP" 2026-10-01
  STUB_RC=1 run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(grep -c -- '- debrief_prep: git: codebase gone has no git repository at /nonexistent' "$IN/unavailable.md")" -eq 1 ]
  [ "$(grep -c -- '- brief_prep: calendar: calendar_fetch.sh failed' "$IN/unavailable.md")" -eq 1 ]
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

@test "prep scripts: brief and debrief write the same quarantine.md, and an input poisoned days earlier is in both (quarantine spec §2)" {
  mkdir -p system/quarantine/poisoned
  printf 'x\n' > system/quarantine/poisoned/d1.md
  printf '{"origin":"raw/work/notes/d1.md","sha256":"ab","poisoned_at":"2026-09-26T05:00:00-06:00"}' \
    > system/quarantine/poisoned/d1.md.origin.json
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- poisoned raw/work/notes/d1.md, since 2026-09-26 (5 days). system/scripts/intake.py --retry-input d1.md' \
    "$IN/quarantine.md"
  [ "$(wc -l < "$IN/quarantine.md")" -eq 1 ]
  rm system/quarantine/poisoned/d1.md system/quarantine/poisoned/d1.md.origin.json
  run "$DP" 2026-10-01
  grep -qx 'none' "$IN/quarantine.md"
}

@test "debrief_prep: no digests are stated, not left blank" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx 'No session digests.' "$IN/digests.md"
}

@test "debrief_prep: a zero for today reads none by HH:MM (#166)" {
  run "$DP"
  [ "$status" -eq 0 ]
  d="$(ls system/logs/inputs)"  # today in the vault's timezone, never this machine's
  grep -qE '^No session digests by [0-9]{2}:[0-9]{2}\.$' "system/logs/inputs/$d/digests.md"
  grep -qE '^No commits by [0-9]{2}:[0-9]{2}\.$' "system/logs/inputs/$d/git.md"
}

@test "debrief_prep: heartbeat.md counts the day's commits, digests, pull requests, alerts and headless runs (#166)" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/heartbeat.md")" = 'signals: 0 (2026-10-01)' ]

  commit_at "$V" 2026-10-01T10:00:00-06:00 "one"
  commit_at "$V" 2026-10-01T11:00:00-06:00 "two"
  digest raw/work/notes/w1.md work 2026-10-01T09:00:00-06:00 "## Outcome
Done."
  printf -- '- 10:00:00 [sync] one\n- 11:00:00 [intake] two\n' > system/logs/alerts_2026-10-01.md
  # Runs are counted as run_headless.sh counts them for the daily cap: no retry, meeting or usage-error run, any
  # spacing, a bad line skipped (PR #253 review).
  {
    printf '{"run_id":"a","command":"ingest","started_at":"2026-10-01T09:00:00-06:00"}\n'
    printf '{"run_id":"b","command":"brief","started_at":"2026-09-30T06:00:00-06:00"}\n'
    printf '{"command":"retry","started_at":"2026-10-01T09:30:00-06:00"}\n'
    printf '{"command":"ingest","exit":3,"started_at":"2026-10-01T09:40:00-06:00"}\n'
    printf '{"command": "debrief", "started_at": "2026-10-01T17:00:00-06:00"}\n'
    printf 'not json\n'
  } > system/logs/runs-2026-10.jsonl
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/heartbeat.md")" = 'signals: 7 (2026-10-01)' ]
}

@test "debrief_prep: the heartbeat reads unknown when git or the digest query failed (PR #253 review)" {
  mv system/scripts/vault_index.py system/scripts/vault_index_real.py
  printf '#!/bin/bash\n[[ "$1" == query ]] && exit 3\nexec "$(dirname "$0")/vault_index_real.py" "$@"\n' > system/scripts/vault_index.py
  chmod +x system/scripts/vault_index.py
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/heartbeat.md")" = 'signals: unknown (2026-10-01)' ]
}

@test "debrief_prep: orders.md copies the open Work Orders report, empty when there is none" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -e "$IN/orders.md" ]
  [ ! -s "$IN/orders.md" ]
  mkdir -p system/logs/nightshift
  # The morning's report closed at brief time; everything after it lands in the next day's report.
  printf '# Work Orders: 2026-10-01\n> Health: claude ok\n\nNothing ran.\n' > system/logs/nightshift/2026-10-01.md
  printf '# Work Orders: 2026-10-02\n> Health: claude ok\n\n## Items\n' > system/logs/nightshift/2026-10-02.md
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(head -n 1 "$IN/orders.md")" = '# Work Orders: 2026-10-02' ]
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

@test "brief_prep: actions.md lists open meeting actions, and a failed Drive search today is an unavailable source" {
  system/scripts/vault_index.py set system/config.md meetings_enabled true > /dev/null
  mkdir -p wiki/work/meetings
  printf -- '---\ntype: meeting\ntitle: "Sync"\ndate: "2026-09-30"\nstart: "2026-09-30T09:00:00-06:00"\npartition: work\nsource: "gdoc:FAKE-x"\ntranscript: "[[s.transcript]]"\n---\n# Sync\n\n## Action items\n- [ ] [Blake Sample] Slides: Prepare them.\n' > wiki/work/meetings/s.md
  printf '{"time":"2026-09-30T16:00:00-06:00","kind":"imported","source":"raw/meetings/FAKE-x.gdoc.md","note":"wiki/work/meetings/s.md","complete":true}\n' > system/logs/meetings-2026-09.jsonl
  printf '{"time":"2026-10-01T08:00:00-06:00","step":"search","doc":"search","exit":0,"reason":""}\n{"time":"2026-10-01T09:00:00-06:00","step":"search","doc":"search","exit":3,"reason":"no Google Drive connector reachable"}\n' > system/logs/meetings_fetch-2026-10.jsonl
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF -- '- Slides: Prepare them. ([[s]], 2026-09-30)' "$IN/actions.md"
  grep -qxF -- '- brief_prep: meetings: the last Google Drive search today failed (exit 3: no Google Drive connector reachable)' "$IN/unavailable.md"
  printf '{"time":"2026-10-01T10:00:00-06:00","step":"search","doc":"search","exit":0,"reason":""}\n' >> system/logs/meetings_fetch-2026-10.jsonl
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  run grep -c meetings "$IN/unavailable.md"
  [ "$output" = 1 ]
}

@test "brief_prep: the first run seeds the default partition's Now page from the previous brief, and now.md lists it" {
  mkdir -p briefings
  printf -- '---\ntype: briefing\n---\n### 1. Active Objectives\n- [ ] **Open item**\n- [x] **Done item**\n### 2. Unavailable Sources\n' > briefings/2026-09-29.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/now.md")" = "$(printf '## personal\n- [ ] owed: **Open item** (since 2026-09-29)')" ]
  [ ! -e "$IN/carried.md" ]
  printf -- '- [ ] **Later item**\n' >> briefings/2026-09-29.md
  run "$BP" 2026-10-01
  run grep -c 'Later item' wiki/personal/Now.md
  [ "$output" = "0" ]
}

@test "brief_prep: no earlier briefing writes an empty now.md, no Now page and no unavailable line" {
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -f "$IN/now.md" ]
  [ ! -s "$IN/now.md" ]
  [ ! -e wiki/personal/Now.md ]  # the brief's publish creates it; a page written now trips the 60 s check
  run grep -c 'now' "$IN/unavailable.md"
  [ "$status" -ne 0 ]  # no now line, or no unavailable.md at all
}

@test "brief_prep: overdue.md lists the lines past their clock and clock.md holds the two dates (Now clock spec §6, §7)" {
  mkdir -p wiki/work
  printf -- '---\ntype: concept\ntags: [now]\ncompiled_at: "2026-09-01"\npartition: work\n---\n# Now\n\n## Needs you\n- [ ] owed: Pick it [due:: 2026-09-28] (since 2026-09-01)\n- [ ] owed: Later [due:: 2026-10-05] (since 2026-09-01)\n\n## Waiting\n' > wiki/work/Now.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/overdue.md")" = "$(printf '**1 to 7 days over**\n- owed: Pick it [due:: 2026-09-28] (since 2026-09-01)')" ]
  [ "$(cat "$IN/clock.md")" = "$(printf 'short: 2026-10-04\nlong: 2026-10-31')" ]
}

@test "brief_prep: alerts.md holds yesterday's and today's alerts with the new-message triage lines summed (phase A spec §3.6)" {
  mkdir -p system/logs
  printf -- '- 09:00:00 [triage] 2 new: Blake; Avery\n- 10:00:00 [sync] blocked\n' > system/logs/alerts_2026-09-30.md
  printf -- '- 05:00:00 [triage] 3 new: Cara\n- 05:10:00 [triage] no Gmail connector reachable\n' > system/logs/alerts_2026-10-01.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/alerts.md")" = "$(printf -- '- 10:00:00 [sync] blocked\n- 05:10:00 [triage] no Gmail connector reachable\n- [triage] 5 new (on the Now page)')" ]
}

@test "brief_prep: closed Now lines move to the month's archive note before now.md lists the page (phase A spec §3.4)" {
  mkdir -p wiki/work
  printf -- '---\ntype: concept\ntags: [now]\ncompiled_at: "2026-09-01"\npartition: work\n---\n# Now\n\n## Needs you\n- [x] owed: Shipped (since 2026-09-01) _(closed: ticked 2026-09-30)_\n  - 2026-09-15: asked Blake\n- [ ] owed: Open (since 2026-09-01)\n' > wiki/work/Now.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/now.md")" = "$(printf '## work\n- [ ] owed: Open (since 2026-09-01)')" ]
  run grep -c 'Shipped' wiki/work/Now.md
  [ "$output" = "0" ]
  [ "$(tail -n 2 wiki/work/now-archive/2026-09.md)" = "$(printf -- '- [x] owed: Shipped (since 2026-09-01) _(closed: ticked 2026-09-30)_\n  - 2026-09-15: asked Blake')" ]
}

@test "brief_prep: briefings and debriefs before yesterday move to briefings/archive/<YYYY-MM>/; a rerun changes nothing" {
  today="$(TZ=America/Denver date +%F)"
  yesterday="$(date -d "$today -1 day" +%F)"
  mkdir -p briefings
  for f in 2026-09-29.md 2026-09-29.debrief.md 2026-09-29.today.md 2026-10-01.md "$yesterday.md" "$yesterday.debrief.md" \
      "$today.md" "$today.debrief.md" "$today.today.md" notes.md; do
    printf 'x\n' > "briefings/$f"
  done
  run "$BP"
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
  [ "$status" -eq 0 ]
  [ -f briefings/archive/2026-09/2026-09-29.md ]
  [ -f briefings/archive/2026-09/2026-09-29.debrief.md ]
  [ -f briefings/archive/2026-09/2026-09-29.today.md ]   # phase D spec §3.6: the today file moves with its briefing
  [ -f "briefings/$today.today.md" ]
  [ -f briefings/archive/2026-10/2026-10-01.md ]
  [ ! -e briefings/2026-09-29.md ]
  [ -f "briefings/$yesterday.md" ]
  [ -f "briefings/$yesterday.debrief.md" ]
  [ -f "briefings/$today.md" ]
  [ -f "briefings/$today.debrief.md" ]
  [ -f briefings/notes.md ]
  before="$(find briefings | sort)"
  run "$BP"
  [ "$status" -eq 0 ]
  [ "$(find briefings | sort)" = "$before" ]
}

@test "brief_prep: a busy run.lock skips archiving and is recorded" {
  today="$(TZ=America/Denver date +%F)"
  mkdir -p briefings
  printf 'x\n' > briefings/2026-09-29.md
  # The holder keeps run.lock for the whole run, however long the prep steps take, and is released afterwards.
  flock system/run.lock sleep 60 &
  holder=$!
  sleep 0.5
  ARCHIVE_LOCK_WAIT=1 run "$BP"
  kill "$holder"
  wait "$holder" || true
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
  [ "$status" -eq 0 ]
  [ -f briefings/2026-09-29.md ]
  [ ! -e briefings/archive ]
  grep -qxF -- '- brief_prep: briefings: run.lock busy; nothing archived' \
    "system/logs/inputs/$(TZ=America/Denver date +%F)/unavailable.md"
}

@test "brief_prep: a run for a past date archives nothing" {
  mkdir -p briefings
  printf 'x\n' > briefings/2026-09-29.md
  printf 'x\n' > briefings/2026-10-01.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -f briefings/2026-09-29.md ]
  [ -f briefings/2026-10-01.md ]
  [ ! -e briefings/archive ]
}

@test "brief_prep: a briefing whose archive copy exists stays put and is recorded with what to do (#55)" {
  today="$(TZ=America/Denver date +%F)"
  mkdir -p briefings/archive/2026-09
  printf 'old\n' > briefings/archive/2026-09/2026-09-29.md
  printf 'new\n' > briefings/2026-09-29.md
  run "$BP"
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
  [ "$status" -eq 0 ]
  [ "$(cat briefings/archive/2026-09/2026-09-29.md)" = "old" ]
  [ "$(cat briefings/2026-09-29.md)" = "new" ]
  grep -qxF -- '- brief_prep: briefings: 2026-09-29.md not archived (briefings/archive/2026-09/2026-09-29.md exists; merge the two copies, then delete briefings/2026-09-29.md)' \
    "system/logs/inputs/$today/unavailable.md"
}

@test "brief_prep: a briefing that cannot be moved stays put and is recorded (#56)" {
  [ "$(id -u)" -ne 0 ] || skip "root can write to a read-only folder"
  today="$(TZ=America/Denver date +%F)"
  mkdir -p briefings/archive/2026-09
  printf 'x\n' > briefings/2026-09-29.md
  chmod a-w briefings/archive/2026-09
  run "$BP"
  chmod u+w briefings/archive/2026-09
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
  [ "$status" -eq 0 ]
  [ -f briefings/2026-09-29.md ]
  [ ! -e briefings/archive/2026-09/2026-09-29.md ]
  grep -qF -- '- brief_prep: briefings: 2026-09-29.md could not be archived (see ' "system/logs/inputs/$today/unavailable.md"
}

@test "brief_prep: nightshift.md copies that morning's report, empty when there is none" {
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -e "$IN/nightshift.md" ] && [ ! -s "$IN/nightshift.md" ]
  mkdir -p system/logs/nightshift
  printf '# Work Orders: 2026-10-01\n> Health: claude ok\n\nNothing ran.\n' > system/logs/nightshift/2026-10-01.md
  run "$BP" 2026-10-01
  grep -qx '# Work Orders: 2026-10-01' "$IN/nightshift.md"
}

@test "brief_prep: yesterday.md copies the newest debrief of the 7 days before, frontmatter dropped (#179)" {
  mkdir -p briefings/archive/2026-09
  printf -- '---\ntype: debrief\ndate: "2026-09-26"\n---\n# Old\n' > briefings/archive/2026-09/2026-09-26.debrief.md
  printf -- '---\ntype: debrief\ndate: "2026-09-28"\n---\n\n# Evening Debrief: 2026-09-28\nClosed X.\n' \
    > briefings/archive/2026-09/2026-09-28.debrief.md
  printf -- '---\ntype: debrief\ndate: "2026-10-01"\n---\n# Today\n' > briefings/2026-10-01.debrief.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/yesterday.md")" = "$(printf 'debrief: [[2026-09-28.debrief]]\n\n# Evening Debrief: 2026-09-28\nClosed X.')" ]
}

@test "brief_prep: yesterday.md takes a debrief exactly 7 days back whole when it has no frontmatter (#179)" {
  mkdir -p briefings
  printf -- '# Evening Debrief\nClosed X.\n---\nMore.\n' > briefings/2026-09-24.debrief.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/yesterday.md")" = "$(printf 'debrief: [[2026-09-24.debrief]]\n\n# Evening Debrief\nClosed X.\n---\nMore.')" ]
}

@test "brief_prep: an unreadable debrief is an unavailable input and the prep still exits 0 (#179)" {
  mkdir -p briefings
  printf -- '---\ntype: debrief\n---\n# Evening Debrief\n' > briefings/2026-09-30.debrief.md
  chmod 000 briefings/2026-09-30.debrief.md
  run "$BP" 2026-10-01
  chmod 644 briefings/2026-09-30.debrief.md
  [ "$status" -eq 0 ]
  [ ! -e "$IN/yesterday.md" ]
  grep -qF 'yesterday: the debrief briefings/2026-09-30.debrief.md is unreadable' "$IN/unavailable.md"
}

@test "brief_prep: no debrief in the 7 days before writes the none line (#179)" {
  mkdir -p briefings/archive/2026-09
  printf -- '---\ntype: debrief\n---\n# Old\n' > briefings/archive/2026-09/2026-09-23.debrief.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/yesterday.md")" = 'none: no debrief found from 2026-09-24 to 2026-09-30' ]
}

@test "brief_prep: projects.md lists active projects with their next actions" {
  mkdir -p wiki/work/concepts
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-10-01\npartition: work\n---\n# Active Projects\n## Active\n- [[Alpha]]: focus\n' > wiki/work/ActiveProjects.md
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-10-01\npartition: work\n---\n# Alpha\n- [ ] first step\n' > wiki/work/concepts/Alpha.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '### \[\[Alpha\]\]: focus' "$IN/projects.md"
  grep -qx -- '- first step' "$IN/projects.md"
  run grep -c 'projects' "$IN/unavailable.md"
  [ "$status" -ne 0 ]  # no projects line, or no unavailable.md at all
}

@test "brief_prep: a failing active_projects.py is recorded and leaves no projects.md" {
  printf '#!/bin/bash\necho boom >&2\nexit 1\n' > "$V/system/scripts/active_projects.py"
  chmod +x "$V/system/scripts/active_projects.py"
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/projects.md" ]
  grep -qxF -- '- brief_prep: projects: active_projects.py failed (see system/logs/inputs/2026-10-01/prep_errors.log)' "$IN/unavailable.md"
}

@test "brief_prep: core writes no handoffs.md; the handoffs section is an extension's (extensions spec §2)" {
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/handoffs.md" ]
}

# gh_says [rc]: a GitHub codebase, and a gh on PATH that lists one pull request per search, or fails with rc.
gh_says() {
  printf '%s\n' '#!/bin/bash' "(( ${1:-0} == 0 )) || { echo 'HTTP 401: Bad credentials' >&2; exit ${1:-0}; }" \
    'echo "$*" >> "$(dirname "$0")/gh.args"' \
    'case "$*" in' \
    '  *--created*) echo "- code — opened: Add export — https://github.com/acme/shop/pull/1" ;;' \
    '  *--reviewed-by*) echo "- review — reviewed: Fix login — https://github.com/acme/shop/pull/2" ;;' \
    'esac' > "$STUBS/gh"
  chmod +x "$STUBS/gh"
  mkdir -p system/codebases
  printf -- '---\ntype: codebase\nname: "shop"\npath: "%s"\npartition: "work"\nsearch_globs: ["*.md"]\norder_pr: "github:acme/shop"\n---\n' "$V" > system/codebases/shop.md
}

@test "debrief_prep: prs.md lists the day's pull requests in the registered GitHub repositories" {
  gh_says
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/prs.md")" = "- code — opened: Add export — https://github.com/acme/shop/pull/1
- review — reviewed: Fix login — https://github.com/acme/shop/pull/2" ]
  grep -qF -- 'search prs --author @me --created 2026-10-01 --repo acme/shop --json url,title --limit 100' "$STUBS/gh.args"
  grep -qF -- 'search prs --author @me --merged-at 2026-10-01 --repo acme/shop' "$STUBS/gh.args"
  grep -qF -- 'search prs --reviewed-by @me --updated 2026-10-01 --repo acme/shop' "$STUBS/gh.args"
  run grep -c prs "$IN/unavailable.md"
  [ "$status" -ne 0 ]  # no prs line, or no unavailable.md at all
}

@test "debrief_prep: a gh search that hangs is cut off and listed as unavailable (audit C11)" {
  gh_says
  printf '%s\n' '#!/bin/bash' 'sleep 30' > "$STUBS/gh"
  GH_TIMEOUT=1 run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF -- '- debrief_prep: prs: gh search failed (see system/logs/inputs/2026-10-01/prep_errors.log)' "$IN/unavailable.md"
}

@test "debrief_prep: no GitHub repository writes an empty prs.md; a failing gh is an unavailable source" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -e "$IN/prs.md" ]
  [ ! -s "$IN/prs.md" ]
  gh_says 1
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF -- '- debrief_prep: prs: gh search failed (see system/logs/inputs/2026-10-01/prep_errors.log)' "$IN/unavailable.md"
}

@test "brief_prep: friction.md lists the flagged notes no earlier brief named, then the count" {
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-09-30\npartition: work\nis_friction: "true"\n---\n# Stuck\n' > wiki/work/concepts/Stuck.md
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-09-29\npartition: work\nis_friction: "true"\n---\n# Known\n' > wiki/work/concepts/Known.md
  mkdir -p briefings
  printf -- '---\ntype: briefing\ndate: "2026-09-30"\nstatus: active\n---\n## 🛑 Blockers\n- **Friction**:\n  - [[Known]]\n  1 open friction note\n' > briefings/2026-09-30.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- \[\[Stuck\]\]' "$IN/friction.md"
  run grep -c 'Known' "$IN/friction.md"
  [ "$status" -eq 1 ]
  grep -qx '2 open friction notes' "$IN/friction.md"
}

@test "brief_prep: people.md holds the Before today's meetings blocks, empty when no event names an entity" {
  mkdir -p wiki/personal/entities
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-09-30\npartition: personal\n---\n# Standup Team\n' > wiki/personal/entities/StandupTeam.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -f "$IN/people.md" ]
  [ ! -s "$IN/people.md" ]
  calendar_says '{"status":"ok","reason":"","events":[{"start_date":"2026-10-01","start_time":"09:00","end_date":"2026-10-01","end_time":"09:30","title":"Standup Team sync"}]}'
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '### \[\[StandupTeam|Standup Team\]\] (09:00 Standup Team sync)' "$IN/people.md"
}

@test "prep scripts: no role writes a focus file or a focus line (the tracker is gone, #122)" {
  printf '[09:00:00] Kafka\n' > system/logs/obsidian_focus_2026-09-30.log
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/focus_yesterday.md" ]
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/focus.md" ]
  run grep -c 'focus' "$IN/unavailable.md"
  [ "$status" -ne 0 ]  # no focus line, or no unavailable.md at all
}

@test "brief_prep: an enabled extension writes its section and prompt into sections/" {
  use_extension demo
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/sections/demo.md")" = '- [ ] demo line' ]
  grep -q 'Demo' "$IN/sections/demo.prompt.md"
  grep -q '^demo	ok' "$IN/sources.given"
}

@test "brief_prep: a failing extension prep is one unavailable line and the rest of the prep still runs" {
  use_extension demo
  DEMO_PREP_FAIL=1 run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/sections/demo.md" ]
  grep -qxF -- '- brief_prep: demo: brief section failed (see system/logs/inputs/2026-10-01/prep_errors.log)' "$IN/unavailable.md"
  [ -e "$IN/actions.md" ]
  [ -e "$IN/sources.md" ]
}

@test "debrief_prep: an enabled extension writes its debrief section into debrief_sections/ (phase D spec §2)" {
  use_extension demo
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/debrief_sections/demo.md")" = '- demo evening line' ]
  grep -q 'Demo (debrief)' "$IN/debrief_sections/demo.prompt.md"
  DEMO_PREP_FAIL=1 run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/debrief_sections/demo.md" ]
  grep -qxF -- '- debrief_prep: demo: debrief section failed (see system/logs/inputs/2026-10-01/prep_errors.log)' "$IN/unavailable.md"
}

@test "brief_prep: no extensions writes no sections/ folder" {
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/sections" ]
  run grep -c extensions "$IN/unavailable.md"
  [ "$status" -ne 0 ]
}

# away_vault: a session digest on 2026-10-06 and a Work Order's on 2026-10-08, so 2026-10-07 to 2026-10-09 have no
# session before the 2026-10-10 brief; gh merged 2 and has 1 open.
away_vault() {
  digest raw/work/notes/s.md work 2026-10-06T09:00:00-06:00 "Done."
  printf -- '---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "order-x"\ncreated_at: "2026-10-08T09:00:00-06:00"\nwork_order: "2026-10-01-a"\n---\nStale.\n' > raw/work/notes/o.md
  gh_says
  # The merged range is the away days in the vault's timezone (America/Denver, -06:00 in October), never UTC days.
  printf '%s\n' '#!/bin/bash' 'case "$*" in *"--merged-at 2026-10-07T00:00:00-06:00..2026-10-09T23:59:59-06:00 --repo acme/shop"*) echo 2 ;; *"--state open --repo acme/shop"*) echo 1 ;; *) exit 1 ;; esac' > "$STUBS/gh"
}

@test "brief_prep: away.md counts what happened on 3 days with no session digest (#166)" {
  away_vault
  mkdir -p raw/work/nightshift briefings/archive/2026-10 wiki/work
  wo() { printf -- '---\ntype: nightshift_item\nid: "%s"\npartition: work\nkind: plan\nstate: %s\nqueued_at: "2026-10-01T09:00:00-06:00"\nfinished_at: "%s"\n---\n' "$1" "$2" "$3" > "raw/work/nightshift/$1.md"; }
  # finished_at in UTC, as nightshift_run.py writes it. a ends 22:30 on 10-09 local (in the gap, though its UTC day is
  # 10-10); d ends 22:30 on 10-06 local (before the gap, though its UTC day is 10-07).
  wo 2026-10-01-a done 2026-10-10T04:30:00+00:00
  wo 2026-10-01-b failed 2026-10-08T05:00:00+00:00
  wo 2026-10-01-c blocked 2026-10-09T12:00:00+00:00
  wo 2026-10-01-d failed 2026-10-07T04:30:00+00:00
  printf '%s\n' '- [ ] owed: Ship it (since 2026-10-08)' '- [ ] owed: Old one (since 2026-10-01)' \
    '- [x] owed: Reply (since 2026-10-02) _(closed: ticked 2026-10-09)_' \
    '- [x] owed: Earlier (since 2026-10-02) _(closed: ticked 2026-10-05)_' > wiki/work/Now.md
  # Held for the brief: brief-severity lines only (smoke), never a now line (sync) or a never line (notify).
  printf -- '- 10:00:00 [sync] blocked\n- 11:00:00 [smoke] slow\n- 12:00:00 [notify] down\n' > system/logs/alerts_2026-10-08.md
  printf -- '- 05:00:00 [smoke] today\n' > system/logs/alerts_2026-10-10.md
  printf '## 🤖 Decided for you\n\n- a: took b\n- c: took d\n\n## 📝 Notes\n- mine\n' > briefings/archive/2026-10/2026-10-08.md
  printf '## 🤖 Decided for you\n\nNone.\n' > briefings/2026-10-09.md
  printf '### 6. Delivered Today\n\n- shipped\n\n### 7. Decided for you\n\n- e: took f\n' > briefings/archive/2026-10/2026-10-07.debrief.md
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ "$(cat system/logs/inputs/2026-10-10/away.md)" = "### While you were away (2026-10-07 to 2026-10-09)

- Pull requests: 2 of 3 merged, 1 of 3 still open
- Work Orders: 1 of 3 done, 1 of 3 failed
- Now lines: 1 of 4 added, 1 of 4 closed
- Alerts: 1 of 3 held for the brief
- Decided for you: 3 lines, from 2 of 3 briefings and 1 of 3 debriefs" ]
}

@test "brief_prep: away.md is empty before any session digest (#166)" {
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ -e system/logs/inputs/2026-10-10/away.md ]
  [ ! -s system/logs/inputs/2026-10-10/away.md ]
}

@test "brief_prep: a 2-day gap shows the away block, a 1-day gap does not (#166)" {
  digest raw/work/notes/s.md work 2026-10-07T09:00:00-06:00 "Done."
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ "$(head -n 1 system/logs/inputs/2026-10-10/away.md)" = '### While you were away (2026-10-08 to 2026-10-09)' ]
  digest raw/work/notes/t.md work 2026-10-08T09:00:00-06:00 "Done."
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ -e system/logs/inputs/2026-10-10/away.md ]
  [ ! -s system/logs/inputs/2026-10-10/away.md ]
}

@test "brief_prep: a failed away.py leaves no earlier away.md for the same date (#166)" {
  mkdir -p system/logs/inputs/2026-10-10
  printf '### While you were away (2026-10-01 to 2026-10-09)\n' > system/logs/inputs/2026-10-10/away.md
  printf '%s\n' '#!/bin/bash' 'exit 1' > system/scripts/away.py
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ -e system/logs/inputs/2026-10-10/away.md ]
  [ ! -s system/logs/inputs/2026-10-10/away.md ]
  grep -qF -- '- brief_prep: away: away.py failed' system/logs/inputs/2026-10-10/unavailable.md
}

@test "brief_prep: a compiled digest in raw/<partition>/archive/ counts as a session (#166)" {
  digest raw/work/notes/s.md work 2026-10-05T09:00:00-06:00 "Done."
  digest raw/personal/archive/a.md personal 2026-10-09T09:00:00-06:00 "Done."
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ -e system/logs/inputs/2026-10-10/away.md ]
  [ ! -s system/logs/inputs/2026-10-10/away.md ]
}

@test "brief_prep: a source that cannot be read says unknown, the others still count (#166)" {
  away_vault
  printf '%s\n' '#!/bin/bash' 'exit 1' > "$STUBS/gh"
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  grep -qxF -- '- Pull requests: unknown' system/logs/inputs/2026-10-10/away.md
  grep -qxF -- '- Work Orders: none' system/logs/inputs/2026-10-10/away.md
  grep -q '^away.py: Pull requests: ' system/logs/inputs/2026-10-10/prep_errors.log
}

@test "brief_prep: away.md covers at most the 14 days before (#166)" {
  digest raw/work/notes/s.md work 2026-09-01T09:00:00-06:00 "Done."
  run "$BP" 2026-10-10
  [ "$status" -eq 0 ]
  [ "$(head -n 1 system/logs/inputs/2026-10-10/away.md)" = '### While you were away (2026-09-26 to 2026-10-09)' ]
  grep -qxF -- '- Now lines: none' system/logs/inputs/2026-10-10/away.md
}

# --- phase A size targets (phase A spec §3.7) ---

@test "brief size: the inputs the brief prints stay under 8 KB on a vault at the live size" {
  python3 "$REPO/system/tests/fixtures/brief_size.py" "$V"
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  printed=(projects.md actions.md people.md friction.md overdue.md alerts.md quarantine.md away.md updates.md)
  total=0
  for f in "${printed[@]}" $(cd "$IN" && ls sections/*.md 2>/dev/null | grep -v '\.prompt\.md$'); do
    [[ -f "$IN/$f" ]] || continue
    echo "$f $(wc -c < "$IN/$f")"
    total=$(( total + $(wc -c < "$IN/$f") ))
  done
  echo "total $total"
  [ "$total" -le 8192 ]
}

@test "brief size: the Now page is under 25 KB after the brief prep archives it" {
  python3 "$REPO/system/tests/fixtures/brief_size.py" "$V"
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  echo "Now.md $(wc -c < wiki/work/Now.md)"
  [ "$(wc -c < wiki/work/Now.md)" -le 25600 ]
  [ "$(grep -c '^- \[x\] ' wiki/work/now-archive/2026-09.md)" -eq 200 ]
}

@test "brief size: the brief prompt is at most 2,500 words with every extension's section" {
  words="$(cat "$REPO/.claude/commands/brief.md" "$REPO"/extensions/*/brief/section.md | wc -w)"
  echo "words $words"
  [ "$words" -le 2500 ]
}
