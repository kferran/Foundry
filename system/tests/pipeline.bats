#!/usr/bin/env bats
# The pipeline graph (factory F6, #477; spec docs/superpowers/specs/2026-11-03-factory-f6-pipeline-graph-design.md):
# system/pipeline.yml declares one node per core unit, and pipeline_graph.py checks it against the code (P1 to P8).
# PIPELINE_GAPS lists what the code lacks today, one line per node and rule with the issue that closes it; the list
# only shrinks: a gap that passes prints "gap closed, delete its line", as TIMING_OVERRUNS does in conformance.bats.

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  CHECK="$VAULT_ROOT/system/tests/pipeline_graph.py"
}

# <node> <rule> <issue>  # what is missing
PIPELINE_GAPS='
brief P3 #436  # brief_run.sh: no crash_trap; a failure before run_headless.sh alerts nothing
sync P3 #436  # vault_sync.sh: no crash_trap; "not a git repository" exits 1 silently
'

gaps_file() { printf '%s\n' "$PIPELINE_GAPS" > "$BATS_TEST_TMPDIR/gaps"; echo "$BATS_TEST_TMPDIR/gaps"; }

@test "the pipeline graph matches the code, outside the known gaps (factory F6, #477)" {
  if [ -e "$VAULT_ROOT/system/config.md" ]; then skip "this checkout is a vault; the rule guards the template"; fi
  run python3 "$CHECK" "$VAULT_ROOT" "$(gaps_file)"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

# fixture: a tree with one unit foundry-a (and its timer), the real alert tags, one script and the given manifest.
fixture() {
  R="$BATS_TEST_TMPDIR/r"
  mkdir -p "$R/system/systemd" "$R/system/scripts/vaultlib"
  cp "$VAULT_ROOT/system/scripts/vaultlib/alerts.py" "$R/system/scripts/vaultlib/"
  : > "$R/system/systemd/foundry-a.service.in"
  : > "$R/system/systemd/foundry-a.timer.in"
  printf '#!/bin/bash\ncrash_trap foundry-a\nflock 9 system/run.lock\n' > "$R/system/scripts/a.sh"
  printf '%s\n' "$1" > "$R/system/pipeline.yml"
}

GOOD='nodes:
  a:
    unit: foundry-a
    scripts: [system/scripts/a.sh]
    locks: [run.lock]
    failure: {busy: retry-next-tick, other: alert:intake}'

@test "a complete node passes" {
  fixture "$GOOD"
  run python3 "$CHECK" "$R"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "P1: a unit with no node, and a node with no unit, each fail" {
  fixture "${GOOD/foundry-a/foundry-b}"
  run python3 "$CHECK" "$R"
  [ "$output" = "$(printf '%s\n' 'a: no unit foundry-b' 'foundry-a: no node')" ]
}

@test "P2: declared locks that differ from the lock files the scripts name fail; the intake.lock() helper is no lock" {
  fixture "${GOOD/locks: \[run.lock\]/locks: [intake.lock]}"
  printf 'with intake.lock("run.lock", timeout=0): pass\n' >> "$R/system/scripts/a.sh"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: locks [intake.lock] but its scripts name [run.lock]' ]
}

@test "P3: an alert catch-all with no crash handler fails, as does a missing catch-all and an unlisted none" {
  fixture "$GOOD"
  printf '#!/bin/bash\nflock 9 system/run.lock\n' > "$R/system/scripts/a.sh"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: other is alert:intake but system/scripts/a.sh installs no crash handler' ]
  fixture "${GOOD/, other: alert:intake/}"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: no other edge' ]
  fixture "${GOOD/other: alert:intake/other: none}"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: other is none with no PIPELINE_GAPS line' ]
}

@test "P3: a Python entry passes with alerts.guard and fails without it" {
  fixture "${GOOD/system\/scripts\/a.sh]/system/scripts/a.py]}"
  printf 'alerts.guard(main, "intake")\nLOCK = "run.lock"\n' > "$R/system/scripts/a.py"
  run python3 "$CHECK" "$R"
  [ -z "$output" ]
  printf 'LOCK = "run.lock"\n' > "$R/system/scripts/a.py"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: other is alert:intake but system/scripts/a.py installs no crash handler' ]
}

@test "P4: an unknown tag, an unknown edge and a caller that names no node each fail" {
  fixture "${GOOD/busy: retry-next-tick/busy: alert:nosuch, x: pager, y: caller:zz}"
  run python3 "$CHECK" "$R"
  [ "$output" = "$(printf '%s\n' 'a: alert:nosuch is not a known tag' 'a: x has unknown edge pager' 'a: y names no node zz')" ]
}

@test "P3: a ledger catch-all passes with the entry's write_ledger trap and fails without it (#436, PR B)" {
  fixture "${GOOD/other: alert:intake/other: ledger}"
  printf '#!/bin/bash\ntrap write_ledger EXIT\nflock 9 system/run.lock\n' > "$R/system/scripts/a.sh"
  run python3 "$CHECK" "$R"
  [ -z "$output" ]
  printf '#!/bin/bash\nflock 9 system/run.lock\n' > "$R/system/scripts/a.sh"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: other is ledger but system/scripts/a.sh writes no ledger line on exit' ]
}

@test "P5: retry-next-tick on a unit with no timer fails" {
  fixture "$GOOD"
  rm "$R/system/systemd/foundry-a.timer.in"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: retry-next-tick on a unit with no timer' ]
}

@test "P6 and P7: a path written with no reader, and read with no writer, fail; a source, a sink and * pass" {
  fixture "$GOOD
    writes: [x/, raw/work/notes/, wiki/a.md]
    reads: [y/, raw/*/notes/, raw/inbox/]
sources:
  - {path: raw/inbox/, by: owner}
sinks:
  - {path: wiki/, by: owner}"
  run python3 "$CHECK" "$R"
  [ "$output" = "$(printf '%s\n' 'x/: written by a, read by no node and not a sink' 'y/: read by a, written by no node and not a source')" ]
}

@test "P8: a listed gap silences its rule, and a gap that now passes must be deleted" {
  fixture "${GOOD/other: alert:intake/other: none}"
  printf 'a P3 #1  # none yet\n' > "$BATS_TEST_TMPDIR/g"
  run python3 "$CHECK" "$R" "$BATS_TEST_TMPDIR/g"
  [ -z "$output" ]
  fixture "$GOOD"
  run python3 "$CHECK" "$R" "$BATS_TEST_TMPDIR/g"
  [ "$output" = 'a P3: gap closed, delete its line' ]
}
