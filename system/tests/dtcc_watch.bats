#!/usr/bin/env bats
# dtcc_watch.py exit codes (DTCC watcher spec §6).
load helpers

setup() {
  make_vault
  cd "$V"
}

@test "no map: exit 0 and no output" {
  run system/scripts/dtcc_watch.py
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "an invalid map: exit 2" {
  mkdir -p system/dtcc
  printf 'partition: nope\n' > system/dtcc/map.yaml
  run system/scripts/dtcc_watch.py
  [ "$status" -eq 2 ]
}

@test "--brief with no notes prints nothing; a bad date exits 2" {
  run system/scripts/dtcc_watch.py --brief 2026-10-06
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  run system/scripts/dtcc_watch.py --brief 2026-13-01
  [ "$status" -eq 2 ]
}
