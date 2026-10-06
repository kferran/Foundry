#!/usr/bin/env bats
load helpers

setup() {
  make_vault
  cd "$V"
  mkdir -p raw/work/notes raw/inbox/.staging
  printf -- '---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "s1"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\nDigest one.\n' > raw/work/notes/d1.md
  export CLAUDE_BIN="$REPO/system/tests/stub_claude" STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_STDIN="$BATS_TEST_TMPDIR/stdin"
  RH="$V/system/scripts/run_headless.sh"
  LEDGER="system/logs/runs-$(TZ=America/Denver date +%Y-%m).jsonl"
}

teardown() {
  pkill -f '^sleep 31\.4159$' 2>/dev/null || true
}

@test "usage errors exit 2" {
  run "$RH"; [ "$status" -eq 2 ]
  run "$RH" rm; [ "$status" -eq 2 ]
  run "$RH" ingest; [ "$status" -eq 2 ]
  run "$RH" brief extra; [ "$status" -eq 2 ]
  run "$RH" ingest wiki/work/concepts/Kafka.md; [ "$status" -eq 2 ]
  printf -- '---\ntype: session_digest\npartition: personal\ncodebase: "v"\nsession_id: "s"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\nx\n' > "$BATS_TEST_TMPDIR/p.md"
  mkdir -p raw/personal/notes
  cp "$BATS_TEST_TMPDIR/p.md" raw/personal/notes/p.md
  run "$RH" ingest raw/work/notes/d1.md raw/personal/notes/p.md; [ "$status" -eq 2 ]
  [ ! -e "$LEDGER" ]
}

@test "status 2 after validation is recorded and returned as 1" {
  STUB_MODE=fail2 run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  [ "$(wc -l < "$LEDGER")" -eq 1 ]
  [ "$(jq -r .exit "$LEDGER")" = "1" ]
}

@test "unsafe input filename exits 2 without calling claude" {
  cp raw/work/notes/d1.md 'raw/work/notes/bad&name.md'
  run "$RH" ingest 'raw/work/notes/bad&name.md'
  [ "$status" -eq 2 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "invalid settings exit 3 without calling claude" {
  echo '{' > system/headless.settings.json
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  [ ! -e "$STUB_ARGS" ]
  [ "$(wc -l < "$LEDGER")" -eq 1 ]
  [ "$(jq -r .exit "$LEDGER")" = "3" ]
  : > system/headless.settings.json
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  echo '[]' > system/headless.settings.json
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  printf '{}\n{}\n' > system/headless.settings.json
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "missing command file exits 3" {
  rm .claude/commands/ingest.md
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  [ ! -e "$STUB_ARGS" ]
  [ -z "$(ls -A wiki/.staging)" ]
  grep -q 'ingest.md' system/logs/alerts_*.md
}

@test "exact invocation flags, inlined prompt and /dev/null stdin" {
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  grep -qx -- '--restricted' "$STUB_ARGS"
  grep -qx -- 'system/headless.settings.json' "$STUB_ARGS"
  grep -qx -- '--strict-mcp-config' "$STUB_ARGS"
  grep -qx -- '--no-session-persistence' "$STUB_ARGS"
  grep -qx -- 'dontAsk' "$STUB_ARGS"
  grep -qx -- 'json' "$STUB_ARGS"
  grep -qx -- 'CLAUDE.md' "$STUB_ARGS"
  grep -qx -- 'Read,Glob,Grep,Edit,Write,Bash' "$STUB_ARGS"
  grep -qE -- '^Edit\(/wiki/\.staging/[0-9]{8}T[0-9]{6}-ingest-[0-9a-f]{4}/\*\*\)$' "$STUB_ARGS"
  grep -qxF -- 'Bash(system/scripts/vault_index.py stage:*)' "$STUB_ARGS"
  run grep -q -- '--setting-sources' "$STUB_ARGS"; [ "$status" -ne 0 ]
  run grep -q -- 'vault_index.py set' "$STUB_ARGS"; [ "$status" -ne 0 ]
  run grep -qF -- '$ARGUMENTS' "$STUB_ARGS"; [ "$status" -ne 0 ]
  grep -q -- 'raw/work/notes/d1.md' "$STUB_ARGS"
  [ "$(cat "$STUB_STDIN")" = "/dev/null" ]
}

@test "successful ingest publishes with provenance and writes a ledger line" {
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  grep -q 'provenance: \["headless"\]' wiki/work/concepts/New.md
  [ "$(jq -r .exit "$LEDGER")" = "0" ]
  [ "$(jq -r '.publish.published[0]' "$LEDGER")" = "wiki/work/concepts/New.md" ]
  [ "$(jq -r '.partition' "$LEDGER")" = "work" ]
  [ "$(jq -r '.input_sha256[0]' "$LEDGER")" = "$(sha256sum raw/work/notes/d1.md | cut -d' ' -f1)" ]
  [ -z "$(ls -A wiki/.staging)" ]
}

@test "noop ingest succeeds; brief that writes nothing exits 5" {
  STUB_MODE=noop run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  STUB_MODE=nothing run "$RH" brief
  [ "$status" -eq 5 ]
  STUB_MODE=brief run "$RH" brief
  [ "$status" -eq 0 ]
  [ -f "briefings/$(TZ=America/Denver date +%F).md" ]
}

@test "claude failure and timeout are recorded and staging is quarantined" {
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  HEADLESS_TIMEOUT=1 STUB_MODE=sleep run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 124 ]
  [ "$(jq -s 'map(.exit) | sort | join(",")' "$LEDGER")" = '"1,124"' ]
  [ -z "$(ls -A wiki/.staging)" ]
  grep -q 'failed (exit 1)' system/logs/alerts_*.md
}

@test "daily cap exits 4 and alerts once" {
  mkdir -p system/logs
  today="$(TZ=America/Denver date +%F)"
  for i in 1 2; do printf '{"run_id":"r%s","command":"ingest","started_at":"%sT01:00:00-06:00","exit":0}\n' "$i" "$today" >> "$LEDGER"; done
  HEADLESS_MAX_RUNS_PER_DAY=2 run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  HEADLESS_MAX_RUNS_PER_DAY=2 run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  [ "$(grep -c 'daily headless cap' system/logs/alerts_*.md)" -eq 1 ]
  [ "$(jq -s 'map(select(.exit == 4)) | length' "$LEDGER")" -eq 2 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "an account usage limit exits 4, alerts once, and is not reported as a failed input" {
  STUB_MODE=usage_limit run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  STUB_MODE=usage_limit run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  [ "$(grep -c 'account usage limit' system/logs/alerts_*.md)" -eq 1 ]
  [ "$(jq -s 'map(select(.exit == 4)) | length' "$LEDGER")" -eq 2 ]
  run grep -c 'failed (exit' system/logs/alerts_*.md
  [ "$output" = "0" ]
}

@test "an error result that is not a usage limit stays exit 1" {
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  run grep -c 'account usage limit' system/logs/alerts_*.md
  [ "$output" = "0" ]
}

@test "malformed ledger line is ignored" {
  mkdir -p system/logs
  printf '{"run_id":"r1","command":"ingest","started_at":"%sT01:0' "$(TZ=America/Denver date +%F)" > "$LEDGER"
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  run bash -c 'tail -n1 "$1" | jq -e .run_id' _ "$LEDGER"
  [ "$status" -eq 0 ]
}

@test "ledger with non-object and mistyped lines" {
  mkdir -p system/logs
  printf '%s\n' '{"command":"ingest","started_at":"x","input_sha256":[5,{"a":1}],"exit":1}' '5' '"str"' '{"started_at":123}' '[1]' > "$LEDGER"
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  run bash -c 'tail -n1 "$1" | jq -e .run_id' _ "$LEDGER"
  [ "$status" -eq 0 ]
}

@test "input vanishing during the run still records the pre-run hash" {
  sha="$(sha256sum raw/work/notes/d1.md | cut -d' ' -f1)"
  STUB_MODE=write_delete_input STUB_RM=raw/work/notes/d1.md run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ ! -e raw/work/notes/d1.md ]
  [ "$(jq -r '.input_sha256[0]' "$LEDGER")" = "$sha" ]
  [ -f wiki/work/concepts/New.md ]
}

@test "attempt counts consecutive failures of the same input" {
  for i in 1 2 3; do
    STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
    [ "$status" -eq 1 ]
  done
  [ "$(jq -s 'map(.attempt) | join(",")' "$LEDGER")" = '"1,2,3"' ]
}

@test "FOUNDRY_ORIGINAL_SHA256 overrides recorded hashes and must match input count" {
  h="$(printf 'a%.0s' $(seq 64))"
  FOUNDRY_ORIGINAL_SHA256="$h" run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ "$(jq -r '.input_sha256[0]' "$LEDGER")" = "$h" ]
  FOUNDRY_ORIGINAL_SHA256="$h $h" run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 2 ]
}

@test "attempt looks back into the previous month's ledger" {
  sha="$(sha256sum raw/work/notes/d1.md | cut -d' ' -f1)"
  prev="system/logs/runs-$(TZ=America/Denver date -d "$(TZ=America/Denver date +%Y-%m-01) -1 day" +%Y-%m).jsonl"
  mkdir -p system/logs
  printf '{"run_id":"p","command":"ingest","started_at":"x","exit":1,"input_sha256":["%s"]}\n' "$sha" > "$prev"
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  [ "$(jq -r .attempt "$LEDGER")" = "2" ]
}

@test "brief gives up on a busy run.lock with exit 6" {
  mkdir -p system/logs
  flock system/run.lock sleep 4 &
  sleep 0.5
  HEADLESS_LOCK_WAIT=1 STUB_MODE=brief run "$RH" brief
  [ "$status" -eq 6 ]
  [ "$(wc -l < "$LEDGER")" -eq 1 ]
  [ "$(jq -r .exit "$LEDGER")" = "6" ]
  wait
}

@test "brief and debrief wait 1400 s for run.lock by default" {
  grep -qxF 'LOCK_WAIT="${HEADLESS_LOCK_WAIT:-1400}"' "$RH"
}

@test "a brief waiting behind an ingest backlog runs before the next ingest" {
  mkdir -p raw/inbox
  printf 'first note\n' > raw/inbox/a.md
  printf 'second note\n' > raw/inbox/b.md
  touch -d '10 minutes ago' raw/inbox/a.md raw/inbox/b.md
  STUB_MODE=noop STUB_SLEEP=2 system/scripts/intake.py &
  ipid=$!
  for _ in $(seq 50); do
    [ -s "$STUB_ARGS" ] && break
    sleep 0.1
  done
  [ -s "$STUB_ARGS" ]
  HEADLESS_LOCK_WAIT=30 STUB_MODE=brief run "$RH" brief
  wait "$ipid"
  [ "$status" -eq 0 ]
  [ "$(jq -r .command "$LEDGER" | tr '\n' ' ')" = "ingest brief ingest " ]
}

@test "a brief that gets run.lock after midnight keeps the date it started on" {
  mkdir -p "$BATS_TEST_TMPDIR/bin" system/logs
  real="$(command -v date)"
  printf '#!/bin/bash\nfor a in "$@"; do case "$a" in -d|--date*) exec %s "$@" ;; esac; done\nif [[ -e "$BATS_TEST_TMPDIR/tomorrow" ]]; then t="2026-01-02 00:10:00"; else t="2026-01-01 23:59:00"; fi\nexec %s -d "$t" "$@"\n' "$real" "$real" > "$BATS_TEST_TMPDIR/bin/date"
  chmod +x "$BATS_TEST_TMPDIR/bin/date"
  ( flock 9; sleep 2; touch "$BATS_TEST_TMPDIR/tomorrow" ) 9> system/run.lock &
  sleep 0.5
  PATH="$BATS_TEST_TMPDIR/bin:$PATH" HEADLESS_LOCK_WAIT=30 STUB_MODE=brief run "$RH" brief
  wait
  [ "$(jq -r .run_id system/logs/runs-2026-01.jsonl | cut -c1-8)" = 20260101 ]
}

@test "permission denials are recorded as warnings" {
  STUB_DENIALS='[{"tool_name":"Write"}]' run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ "$(jq -r '.warnings.permission_denials' "$LEDGER")" = "1" ]
}

@test "recovery quarantines leftover staging before the run" {
  mkdir -p wiki/.staging/20260930T010101-ingest-0000/wiki/work/concepts
  echo x > wiki/.staging/20260930T010101-ingest-0000/wiki/work/concepts/Old.md
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ -f system/quarantine/20260930T010101-ingest-0000/staged/wiki/work/concepts/Old.md ]
}

@test "SIGTERM during the claude run is recorded as exit 143" {
  STUB_MODE=sleep "$RH" ingest raw/work/notes/d1.md &
  pid=$!
  for _ in $(seq 50); do
    [ -s "$STUB_ARGS" ] && break
    sleep 0.1
  done
  [ -s "$STUB_ARGS" ]
  kill -TERM "$pid"
  rc=0
  wait "$pid" || rc=$?
  [ "$rc" -eq 143 ]
  [ "$(tail -n1 "$LEDGER" | jq -r .exit)" = "143" ]
}

@test "failed publish recovery alerts with the run id and the run continues" {
  bad=20260930T010101-ingest-0001
  mkdir -p "system/logs/runs/$bad"
  printf '{"staged": "wiki/.st' > "system/logs/runs/$bad/publish.journal"
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ -f wiki/work/concepts/New.md ]
  run grep -c "recovery.*$bad" system/logs/alerts_*.md
  [ "$status" -eq 0 ]
  [ "$output" -eq 1 ]
}

@test "a process claude leaves behind does not hold run.lock" {
  STUB_MODE=leak run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  run pgrep -f '^sleep 31\.4159$'
  [ "$status" -eq 0 ]
  run flock -n system/run.lock true
  [ "$status" -eq 0 ]
}

@test "unreadable note fails the snapshot with exit 3 and claude is not called" {
  [ "$(id -u)" -ne 0 ] || skip "root can read mode-000 files"
  chmod 000 wiki/work/concepts/Kafka.md
  run "$RH" ingest raw/work/notes/d1.md
  chmod 644 wiki/work/concepts/Kafka.md
  [ "$status" -eq 3 ]
  [ ! -e "$STUB_ARGS" ]
  run grep -c 'snapshot failed' system/logs/alerts_*.md
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$LEDGER")" -eq 1 ]
  [ "$(jq -r .exit "$LEDGER")" = "3" ]
}

@test "signal exits do not count as attempts" {
  sha="$(sha256sum raw/work/notes/d1.md | cut -d' ' -f1)"
  mkdir -p system/logs
  for rc in 129 130 143; do
    printf '{"run_id":"s%s","command":"ingest","started_at":"x","exit":%s,"input_sha256":["%s"]}\n' "$rc" "$rc" "$sha" >> "$LEDGER"
  done
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  [ "$(tail -n1 "$LEDGER" | jq -r .attempt)" = "1" ]
}

@test "ingest inputs reach the prompt one per line, after the run id" {
  cp raw/work/notes/d1.md "raw/work/notes/two words.md"
  run "$RH" ingest raw/work/notes/d1.md "raw/work/notes/two words.md"
  [ "$status" -eq 0 ]
  grep -qx 'raw/work/notes/d1.md' "$STUB_ARGS"
  grep -qx 'raw/work/notes/two words.md' "$STUB_ARGS"
  grep -qE '[0-9]{8}T[0-9]{6}-ingest-[0-9a-f]{4}$' "$STUB_ARGS"
}
