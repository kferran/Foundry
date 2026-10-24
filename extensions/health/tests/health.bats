#!/usr/bin/env bats
# The health extension as core sees it (health scorecard spec §3.1, §3.4): the manifest, its config keys, the
# section prompt and the brief prep.
# Runs from a vault checkout: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

setup() {
  make_vault
  use_extension health
  cd "$V"
}

@test "the manifest loads with a brief section, no unit and its script executable" {
  run system/scripts/extensions.py check
  [ "$status" -eq 0 ]
  run system/scripts/extensions.py brief
  [ "$output" = health ]
  run system/scripts/extensions.py debrief
  [ -z "$output" ]
  run system/scripts/extensions.py units server
  [ -z "$output" ]
  [ -x extensions/health/scripts/health.py ]
}

@test "the config keys validate, and a bad threshold or gate date is an error" {
  sed -i '$d' system/config.md
  printf '%s\n' 'health_thresholds: {tick_success_pct: "90", brief_by: "07:00", now_open: "80"}' \
    'health_defect_gates: {C3: "2026-10-24", C7: "2026-10-30"}' '---' >> system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -eq 0 ]
  sed -i 's/now_open: "80"/now_open: "many"/' system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -ne 0 ]
  [[ "$output" == *"expected an integer"* ]]
  sed -i 's/now_open: "many"/now_open: "80"/; s/C7: "2026-10-30"/C7: "soon"/' system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -ne 0 ]
  [[ "$output" == *"expected a date"* ]]
}

@test "the section prompt is at most 20 words" {
  [ "$(LC_ALL=C.UTF-8 wc -w < extensions/health/brief/section.md)" -le 20 ]
}

# prep_health <date>: source brief/prep.sh as brief_prep.sh does (extensions spec §3).
prep_health() {
  (
    VAULT_ROOT="$V"
    source system/scripts/lib_config.sh
    source system/scripts/lib_prep.sh
    PREP_NAME=brief_prep PREP_DATE="$1" PREP_DIR="system/logs/inputs/$1"
    mkdir -p "$PREP_DIR/sections"
    prep_sources_init
    # shellcheck disable=SC1091
    source extensions/health/brief/prep.sh
  )
}

@test "brief prep: the whole scorecard on a Monday, one line a metric, and the history appended" {
  run prep_health 2026-10-26
  [ "$status" -eq 0 ]
  f=system/logs/inputs/2026-10-26/sections/health.md
  [ "$(wc -l < "$f")" -ge 11 ]
  grep -qxF -- '- ✅ Sync blocked: 0 (healthy 0)' "$f"
  grep -qF -- '- ❔ Headless runs published: unavailable' "$f"
  [ "$(jq -s '[.[] | select(.metric)] | length' system/logs/health/2026-10.jsonl)" -ge 11 ]
}

@test "brief prep: only breaches on a Tuesday, and an empty section when all pass" {
  run prep_health 2026-10-27
  [ "$status" -eq 0 ]
  [ -e system/logs/inputs/2026-10-27/sections/health.md ]
  [ ! -s system/logs/inputs/2026-10-27/sections/health.md ]
  printf 'reason: x\n' > system/logs/sync-blocked
  run prep_health 2026-10-28
  [ "$(cat system/logs/inputs/2026-10-28/sections/health.md)" = '- ⚠️ health: Sync blocked 1 (blocked now) (healthy 0)' ]
}

@test "brief prep: a failed score is an unavailable input and an empty section" {
  printf '#!/bin/sh\nexit 1\n' > extensions/health/scripts/health.py
  run prep_health 2026-10-27
  [ "$status" -eq 0 ]
  [ ! -s system/logs/inputs/2026-10-27/sections/health.md ]
  grep -qF -- '- brief_prep: health: health.py score failed (exit 1' system/logs/inputs/2026-10-27/unavailable.md
}
