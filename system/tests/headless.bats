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
}

@test "invalid settings exit 3 without calling claude" {
  echo '{' > system/headless.settings.json
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  [ ! -e "$STUB_ARGS" ]
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
  [ ! -e "$STUB_ARGS" ]
}

@test "malformed ledger line is ignored" {
  mkdir -p system/logs
  printf '{"run_id":"r1","command":"ingest","started_at":"%sT01:0' "$(TZ=America/Denver date +%F)" > "$LEDGER"
  printf '\n' >> "$LEDGER"
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
}

@test "brief gives up on a busy run.lock with exit 6" {
  mkdir -p system/logs
  flock system/run.lock sleep 4 &
  sleep 0.5
  HEADLESS_LOCK_WAIT=1 STUB_MODE=brief run "$RH" brief
  [ "$status" -eq 6 ]
  wait
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
