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
'

gaps_file() { printf '%s\n' "$PIPELINE_GAPS" > "$BATS_TEST_TMPDIR/gaps"; echo "$BATS_TEST_TMPDIR/gaps"; }

@test "the pipeline graph matches the code, outside the known gaps (factory F6, #477)" {
  if [ -e "$VAULT_ROOT/system/config.md" ]; then skip "this checkout is a vault; the rule guards the template"; fi
  run python3 "$CHECK" "$VAULT_ROOT" "$(gaps_file)"
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "with every extension's pipeline.yml, the graph still matches the code (F6 PR 2a)" {
  if [ -e "$VAULT_ROOT/system/config.md" ]; then skip "this checkout is a vault; the rule guards the template"; fi
  run python3 "$CHECK" "$VAULT_ROOT" "$(gaps_file)" --extensions
  printf '%s\n' "$output"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "FOUNDRY.md's diagram is the generator's output (F6 PR 2a)" {
  want="$(python3 "$CHECK" "$VAULT_ROOT" --mermaid --extensions)"
  have="$(sed -n '/^<!-- pipeline:begin -->$/,/^<!-- pipeline:end -->$/p' "$VAULT_ROOT/FOUNDRY.md" | sed '1,2d;$d' | sed '$d')"
  if [ "$have" != "$want" ]; then
    echo "FOUNDRY.md's pipeline block is stale: replace it with python3 system/tests/pipeline_graph.py . --mermaid --extensions"
  fi
  [ "$have" = "$want" ]
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

# ext <name> <pipeline.yml text>: an extension in the fixture, with one unit foundry-<name> and its timer.
ext() {
  mkdir -p "$R/extensions/$1/units"
  printf -- '---\nname: %s\nalert_tags: [{tag: %s, severity: now}]\n---\n' "$1" "$1" > "$R/extensions/$1/extension.md"
  printf '[Service]\nRestart=on-failure\n' > "$R/extensions/$1/units/foundry-$1.service.in"
  : > "$R/extensions/$1/units/foundry-$1.timer.in"
  printf '%s\n' "$2" > "$R/extensions/$1/pipeline.yml"
}

@test "--extensions: an extension unit needs a node; its own tag passes; extends must name a node" {
  fixture "$GOOD"
  ext e 'extends:
  zz: {scripts: [system/scripts/a.sh]}'
  run python3 "$CHECK" "$R"
  [ -z "$output" ]
  run python3 "$CHECK" "$R" --extensions
  [ "$output" = "$(printf '%s\n' 'e: extends no node zz' 'foundry-e: no node')" ]
  ext e 'nodes:
  e: {unit: foundry-e, scripts: [system/scripts/a.sh], locks: [run.lock], failure: {busy: retry-next-tick, other: alert:e}}'
  run python3 "$CHECK" "$R" --extensions
  [ -z "$output" ]
}

@test "--extensions: extends adds the step's locks, so a lock the step's script names must be declared" {
  fixture "$GOOD"
  printf 'flock 9 system/notify.lock\n' > "$R/system/scripts/b.sh"
  ext e 'nodes:
  e: {unit: foundry-e, scripts: [system/scripts/a.sh], locks: [run.lock], failure: {busy: retry-next-tick, other: alert:e}}
extends:
  a: {scripts: [system/scripts/b.sh]}'
  run python3 "$CHECK" "$R" --extensions
  [ "$output" = 'a: locks [run.lock] but its scripts name [notify.lock, run.lock]' ]
}

@test "P5: restart needs Restart= in the unit file" {
  fixture "${GOOD/busy: retry-next-tick, other: alert:intake/other: restart}"
  run python3 "$CHECK" "$R"
  [ "$output" = 'a: restart on a unit with no Restart=' ]
  printf '[Service]\nRestart=always\n' > "$R/system/systemd/foundry-a.service.in"
  run python3 "$CHECK" "$R"
  [ -z "$output" ]
}

@test "--mermaid: nodes, folders between writers and readers, and outside at the sources and sinks" {
  fixture "$GOOD
    writes: [x/]
sources:
  - {path: x/, by: owner}"
  run python3 "$CHECK" "$R" --mermaid
  [ "$output" = "$(printf '%s\n' 'flowchart LR' '  outside([outside])' '  a[a]' '  p0[("x/")]' '  a --> p0' '  outside --> p0')" ]
}

# two <a's locks> <b's failure>: the fixture with a second unit foundry-b whose node b takes run.lock and notify.lock.
two() {
  fixture "${GOOD/locks: \[run.lock\]/locks: [$1]}
  b:
    unit: foundry-b
    scripts: [system/scripts/b.sh]
    locks: [run.lock, notify.lock]
    failure: {$2other: alert:intake}"
  printf '#!/bin/bash\ncrash_trap foundry-b\nflock 9 system/run.lock\nflock 8 system/logs/notify.lock\n' > "$R/system/scripts/b.sh"
  printf 'flock 8 system/logs/notify.lock\n' >> "$R/system/scripts/a.sh"
  printf '[Service]\nTimeoutStartSec=20min\n' > "$R/system/systemd/foundry-b.service.in"
  : > "$R/system/systemd/foundry-b.timer.in"
}

@test "P9: two nodes that take two locks in opposite orders fail; the same order passes" {
  two "notify.lock, run.lock" "busy: retry-next-tick, "
  run python3 "$CHECK" "$R"
  [ "$output" = 'notify.lock, run.lock: a takes notify.lock first, b takes run.lock first' ]
  two "run.lock, notify.lock" "busy: retry-next-tick, "
  run python3 "$CHECK" "$R"
  [ -z "$output" ]
}

@test "P10: a shared lock needs a busy edge, unless a named wait outlasts the other unit's limit" {
  two "run.lock, notify.lock" ""
  run python3 "$CHECK" "$R"
  [ "$output" = "$(printf '%s\n' 'b: shares notify.lock with a and has no busy edge' 'b: shares run.lock with a and has no busy edge')" ]
  mkdir -p "$R/system/tests"
  printf "TIMING_VALUES='\nshort system/scripts/b.sh ^SHORT=([0-9]+)\$\nlong system/scripts/b.sh ^LONG=([0-9]+h)\$\n'\n" > "$R/system/tests/conformance.bats"
  printf 'SHORT=60\nLONG=2h\n' >> "$R/system/scripts/b.sh"
  printf '[Service]\nTimeoutStartSec=1h\n' > "$R/system/systemd/foundry-a.service.in"
  printf '    waits: {run.lock: short, notify.lock: nosuch}\n' >> "$R/system/pipeline.yml"
  run python3 "$CHECK" "$R"
  [ "$output" = "$(printf '%s\n' 'b: waits 60 s for run.lock, which a can hold for 3600 s, and has no busy edge' 'b: waits names no TIMING_VALUES key nosuch')" ]
  sed -i 's/waits: {run.lock: short, notify.lock: nosuch}/waits: {run.lock: long, notify.lock: long}/' "$R/system/pipeline.yml"
  run python3 "$CHECK" "$R"
  [ -z "$output" ]
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
