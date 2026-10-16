#!/usr/bin/env bats
# dtcc_watch.py exit codes (DTCC watcher spec §6).
# Runs from a vault checkout with the extension at extensions/dtcc/: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

setup() {
  make_vault
  use_extension dtcc
  cd "$V"
}

@test "no map: exit 0 and no output" {
  run extensions/dtcc/scripts/dtcc_watch.py
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "an invalid map: exit 2" {
  mkdir -p system/dtcc
  printf 'partition: nope\n' > system/dtcc/map.yaml
  run extensions/dtcc/scripts/dtcc_watch.py
  [ "$status" -eq 2 ]
}

@test "--brief with no notes prints nothing; a bad date exits 2" {
  run extensions/dtcc/scripts/dtcc_watch.py --brief 2026-10-06
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  run extensions/dtcc/scripts/dtcc_watch.py --brief 2026-13-01
  [ "$status" -eq 2 ]
}

@test "the brief section adds each DTCC line to the Now page of its note's partition (extensions spec §3)" {
  grep -qF 'wiki/<partition>/changes/' "$V/extensions/dtcc/brief/section.md"
  grep -qF 'Now page' "$V/extensions/dtcc/brief/section.md"
}

# prep_dtcc: source brief/prep.sh as brief_prep.sh does (extensions spec §3), for 2026-10-01.
IN=system/logs/inputs/2026-10-01
prep_dtcc() {
  (
    VAULT_ROOT="$V"
    source system/scripts/lib_config.sh
    source system/scripts/lib_prep.sh
    PREP_NAME=brief_prep PREP_DATE=2026-10-01 PREP_DIR="$IN"
    mkdir -p "$PREP_DIR/sections"
    prep_sources_init
    # shellcheck disable=SC1091
    source extensions/dtcc/brief/prep.sh
  )
}

@test "brief section: empty without a map, and off on the Sources line (DTCC watcher spec §7)" {
  run prep_dtcc
  [ "$status" -eq 0 ]
  [ -e "$IN/sections/dtcc.md" ]
  [ ! -s "$IN/sections/dtcc.md" ]
  grep -qx "$(printf 'dtcc\toff\t')" "$IN/sources.given"
}

@test "brief section: with a map and no new notes, empty and ok (DTCC watcher spec §7)" {
  mkdir -p system/dtcc
  cp "$V/extensions/dtcc/map.example.yaml" system/dtcc/map.yaml
  run prep_dtcc
  [ "$status" -eq 0 ]
  [ ! -s "$IN/sections/dtcc.md" ]
  grep -qx "$(printf 'dtcc\tok\t')" "$IN/sources.given"
}
