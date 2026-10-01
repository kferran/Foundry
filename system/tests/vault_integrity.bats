#!/usr/bin/env bats

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  cd "$VAULT_ROOT" || exit 1
}

@test "Verify required directory structural enclosures exist" {
  [ -d "raw/archive" ]
  [ -d "wiki" ]
  [ -d "briefings" ]
  [ -d "system/agents" ]
}

@test "Verify mandatory configuration manual blueprints are present" {
  [ -f "CLAUDE.md" ]
  [ -f "system/templates/wiki-concept.md" ]
  [ -f "system/templates/daily-briefing.md" ]
}

@test "Verify context-driven telemetry engine scripts are flagged as executable" {
  [ -x "system/scripts/telemetry_enricher.sh" ]
}

@test "Verify telemetry enricher runs cleanly and produces output files" {
  rm -f raw/kusto_enriched_*.md
  run system/scripts/telemetry_enricher.sh
  [ "$status" -eq 0 ]
  run bash -c "ls raw/kusto_enriched_*.md"
  [ "$status" -eq 0 ]
  rm -f raw/kusto_enriched_*.md
}

@test "Verify active 15-minute systemd telemetry unit timer state" {
  run systemctl --user is-active ultron-telemetry.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify underlying systemd telemetry background service unit loads cleanly" {
  run systemctl --user list-units --type=service --all
  [[ "$output" == *"ultron-telemetry.service"* ]]
}

@test "Verify 6am MT morning briefing systemd user timer is active" {
  run systemctl --user is-active brain-brief.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify 5pm MT evening debriefing systemd user timer is active" {
  run systemctl --user is-active brain-debrief.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify raw/ intake systemd user timer is active" {
  run systemctl --user is-active brain-intake.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify Obsidian focus tracker service is running" {
  run systemctl --user is-active brain-focus-tracker.service
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify /setup onboarding config exists" {
  [ -f "system/config.md" ]
}
