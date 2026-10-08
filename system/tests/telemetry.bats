#!/usr/bin/env bats
# telemetry_fetch.py end to end with a stub az and canned HTTP (Plan 11 spec §8).
load helpers

setup() {
  make_vault
  mkdir -p "$V/system/telemetry" "$V/system/codebases" "$BATS_TEST_TMPDIR/bin"
  cat > "$V/system/codebases/shop.md" <<'EOF'
---
type: codebase
name: "shop"
path: "~"
partition: "work"
search_globs: ["*"]
---
EOF
  cat > "$V/system/telemetry/prod-adx.md" <<'EOF'
---
type: telemetry_source
name: "prod-adx"
codebase: "shop"
environment: "prod"
kind: "adx"
adx_cluster: "https://example.kusto.windows.net"
adx_database: "prod"
adx_signals: ["logs"]
---
EOF
  printf '#!/bin/bash\necho tok\n' > "$BATS_TEST_TMPDIR/bin/az"
  chmod +x "$BATS_TEST_TMPDIR/bin/az"
  export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  export FOUNDRY_TELEMETRY_STUB="$BATS_TEST_TMPDIR/stub"
  cp -r "$REPO/system/tests/fixtures/telemetry" "$FOUNDRY_TELEMETRY_STUB"
  mkdir -p "$V/system/templates"
  cp "$REPO/system/templates/production-error.md" "$V/system/templates/"
}

@test "a run writes one note, a jsonl line and state" {
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 0 ]
  [ "$(find "$V/raw/telemetry" -name 'prod-adx-a-*.md' | wc -l)" -eq 1 ]
  grep -q '"source": "prod-adx"' "$V"/system/logs/telemetry-*.jsonl
  [ -f "$V/system/logs/telemetry_state.json" ]
}

@test "a log note keeps the ticket GUID in its message and masks the email and password" {
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 0 ]
  note=$(find "$V/raw/telemetry" -name 'prod-adx-a-*.md')
  grep -qF 'message: "Ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b failed for <email> password=[REDACTED:assignment]"' "$note"
  run grep -rlE 'bob@example.com|hunter2' "$V/raw/telemetry" "$V/system/logs"
  [ "$status" -ne 0 ]
}

@test "the lock is held: a second run exits 4" {
  exec 9> "$V/system/telemetry.lock"
  flock 9
  run env TELEMETRY_LOCK_WAIT=1 "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 4 ]
}

@test "az not logged in: exit 1 and one alert naming az login" {
  printf '#!/bin/bash\nexit 1\n' > "$BATS_TEST_TMPDIR/bin/az"
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 1 ]
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$(grep -c 'run az login' "$V"/system/logs/alerts_*.md)" -eq 1 ]
}

@test "--check and --dry-run write no notes and no state" {
  run "$V/system/scripts/telemetry_fetch.py" --check prod-adx
  [ "$status" -eq 0 ]
  run "$V/system/scripts/telemetry_fetch.py" --dry-run
  [ "$status" -eq 0 ]
  [ ! -e "$V/system/logs/telemetry_state.json" ]
  [ "$(find "$V/raw" -path '*telemetry*' -name '*.md' 2>/dev/null | wc -l)" -eq 0 ]
}

@test "a Sentry token file readable by others is refused" {
  cat > "$V/system/telemetry/prod-sentry.md" <<'EOF'
---
type: telemetry_source
name: "prod-sentry"
codebase: "shop"
environment: "prod"
kind: "sentry"
sentry_url: "https://sentry.example.com"
sentry_org: "acme"
sentry_projects: ["api"]
---
EOF
  printf 'tok\n' > "$BATS_TEST_TMPDIR/sentry.token"
  chmod 0644 "$BATS_TEST_TMPDIR/sentry.token"
  run env FOUNDRY_SENTRY_TOKEN_FILE="$BATS_TEST_TMPDIR/sentry.token" "$V/system/scripts/telemetry_fetch.py" --check prod-sentry
  [ "$status" -eq 1 ]
  [[ "$output" == *"chmod 0600"* ]]
}
