#!/usr/bin/env bats
# Structural checks that run anywhere (spec §12). Live service checks live in system_health.bats.

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  cd "$VAULT_ROOT"
}

@test "partition folders exist" {
  for p in work personal shared; do
    [ -d "wiki/$p/concepts" ]
  done
  [ -d raw/inbox ] && [ -d raw/archive ] && [ -d raw/telemetry ]
}

@test "Index note exists" {
  [ -f wiki/Index.md ]
}

@test "vault scripts and hook are executable" {
  [ -x system/scripts/vault_index.py ]
  [ -x system/scripts/lint_vault.sh ]
  [ -x .githooks/pre-commit ]
}

@test "a schema note exists for every template type" {
  for t in wiki-concept:concept daily-briefing:briefing daily-debrief:debrief intent-shaper:plan_gate; do
    file="system/templates/${t%%:*}.md"
    type="${t##*:}"
    grep -q "^type: $type\$" "$file"
    grep -q "^schema_for: $type\$" "system/schemas/$type.md"
  done
}

@test "generated and per-user files are not tracked" {
  ! git ls-files --error-unmatch system/index.db 2>/dev/null
  ! git ls-files --error-unmatch system/config.md 2>/dev/null
}

@test "generated paths are gitignored" {
  git check-ignore -q system/index.db
  git check-ignore -q wiki/.staging/run/x.md
  git check-ignore -q system/fleet/tasks/x/status.json
  git check-ignore -q raw/inbox/note.md
  git check-ignore -q system/quarantine/x.md
}
