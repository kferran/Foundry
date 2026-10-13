#!/usr/bin/env bats
# smoke_check.sh (smoke check spec §3.1): one line per source, one alert a day per failure, the claude version.
load helpers

setup() {
  make_vault
  cd "$V"
  mkdir -p "$BATS_TEST_TMPDIR/bin"
  printf '#!/bin/bash\n[[ "$1" == --version ]] || exit 2\necho "1.0.0 (Claude Code)"\n' > "$BATS_TEST_TMPDIR/bin/claude"
  chmod +x "$BATS_TEST_TMPDIR/bin/claude"
  export PATH="$BATS_TEST_TMPDIR/bin:$PATH" CALLS="$BATS_TEST_TMPDIR/calls"
  unset CLAUDE_BIN
  SC="system/scripts/smoke_check.sh"
  LOG="system/logs/smoke-$(TZ=America/Denver date +%Y-%m).jsonl"
  # Every real check prints a line on success; a stub that says nothing stands for a check that did not run.
  stub calendar_fetch.sh 0 "calendar_fetch: the connector listed 1 events" 1
  stub meetings_fetch.sh 0 "meetings_fetch: the search listed 0 Docs" 1
  stub jira_fetch.sh 0 "jira_fetch: the search listed 0 stalled handoffs" 1
  stub triage_fetch.sh 0 "triage_fetch: 0 threads need you" 1
  stub dtcc_watch.py 0 "map ok" 1
  stub telemetry_fetch.py 0 "telemetry_fetch: prod-sentry: ok" 1
}

# stub <script> <exit> <message> [stream]: the vault's copy of a fetch records its call, prints the message to stderr
# (or the stream given) and exits with the code. telemetry_fetch.py --list prints the sources in STUB_SOURCES.
stub() {
  local f="system/scripts/$1" fd="${4:-2}"
  cat > "$f" <<EOF
#!/bin/bash
echo "$1 \$*" >> "\$CALLS"
if [[ "$1" == telemetry_fetch.py ]] && [[ "\$1" == --list ]]; then
  [[ -z "\${STUB_SOURCES:-}" ]] || printf '%s\n' "\$STUB_SOURCES"
  exit "\${STUB_LIST_RC:-0}"
fi
[[ -z "$3" ]] || echo "$3" >&$fd
exit $2
EOF
  chmod +x "$f"
}

set_key() { sed -i "s/^$1:.*/$1: $2/;t;\$i $1: $2" system/config.md; }
alerts() { cat system/logs/alerts_*.md 2>/dev/null || true; }

@test "every configured source reads ok and the rest off; the version is recorded, nothing is alerted" {
  run "$SC"
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "version: ok" ]
  [ "${lines[1]}" = "calendar: ok" ]
  [ "${lines[2]}" = "meetings: off" ]
  [ "${lines[3]}" = "handoffs: off" ]
  [ "${lines[4]}" = "triage: off" ]
  [ "${lines[5]}" = "telemetry: off" ]
  [ "${lines[6]}" = "dtcc: off" ]
  [ "$(cat system/logs/claude.version)" = "1.0.0 (Claude Code)" ]
  [ -z "$(alerts)" ]
  [ "$(jq -r 'select(.source == "calendar") | .exit' "$LOG")" = 0 ]
  grep -qx 'calendar_fetch.sh --check' "$CALLS"
  grep -qx 'telemetry_fetch.py --list' "$CALLS"
  run grep -c -e meetings_fetch -e jira_fetch -e triage_fetch -e dtcc_watch -e 'telemetry_fetch.py --check' "$CALLS"
  [ "$output" = 0 ]
}

@test "a failing source reads failed with the script's reason, exits 1 and alerts once a day" {
  stub calendar_fetch.sh 6 "calendar_fetch: no Google Calendar connector"
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'calendar: failed: no Google Calendar connector' <<< "$output"
  [ "$(jq -r 'select(.source == "calendar") | .reason' "$LOG")" = "no Google Calendar connector" ]
  alerts | grep -qF "[smoke] calendar failed: no Google Calendar connector (see $LOG)"
  run "$SC"
  [ "$status" -eq 1 ]
  [ "$(alerts | grep -c '\[smoke\]')" -eq 1 ]
}

@test "a check that exits 0 without a word is a failure: no check passes silently" {
  stub calendar_fetch.sh 0 ""
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'calendar: failed: no output' <<< "$output"
}

@test "a reason keeps the Python checks' own first word and drops only the script's prefix" {
  mkdir -p system/dtcc
  printf 'partition: work\n' > system/dtcc/map.yaml
  stub dtcc_watch.py 1 "stale: shop: src/x is missing at main" 1
  stub calendar_fetch.sh 6 $'claude: some noise\nmore noise\ncalendar_fetch: no Google Calendar connector'
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'dtcc: failed: stale: shop: src/x is missing at main' <<< "$output"
  grep -qx 'calendar: failed: no Google Calendar connector' <<< "$output"
}

@test "at the usage ceiling the connector checks are held, not failed, with one alert a day; the local checks still run" {
  printf '#!/bin/bash\n[[ "$1" == hold ]] || exit 2\necho "five-hour usage 0.7 is at or above 0.6"\n' > system/scripts/triage.py
  chmod +x system/scripts/triage.py
  set_key meetings_enabled '"true"'
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'version: ok' <<< "$output"
  grep -qx 'calendar: held: five-hour usage 0.7 is at or above 0.6' <<< "$output"
  grep -qx 'meetings: held: five-hour usage 0.7 is at or above 0.6' <<< "$output"
  grep -qx 'telemetry: off' <<< "$output"
  run grep -c -e calendar_fetch -e meetings_fetch "$CALLS"
  [ "$output" = 0 ]
  alerts | grep -qF '[smoke] held: five-hour usage 0.7 is at or above 0.6; the connector checks did not run'
  run "$SC"
  [ "$(alerts | grep -c '\[smoke\]')" -eq 1 ]
}

@test "two failing sources give two alert lines" {
  set_key meetings_enabled '"true"'
  stub calendar_fetch.sh 6 "calendar_fetch: no Google Calendar connector"
  stub meetings_fetch.sh 3 "meetings_fetch: no Google Drive connector"
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'meetings: failed: no Google Drive connector' <<< "$output"
  [ "$(alerts | grep -c '\[smoke\]')" -eq 2 ]
}

@test "enabled features are each checked once; the telemetry sources come from --list" {
  set_key meetings_enabled '"true"'
  set_key triage_enabled '"true"'
  set_key handoffs_projects '["AB"]'
  mkdir -p system/dtcc
  printf 'partition: work\n' > system/dtcc/map.yaml
  STUB_SOURCES=$'prod-sentry\nprod-adx' run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'telemetry: ok' <<< "$output"
  grep -qx 'dtcc: ok' <<< "$output"
  [ "$(grep -c -x 'meetings_fetch.sh --check' "$CALLS")" -eq 1 ]
  [ "$(grep -c -x 'jira_fetch.sh --check' "$CALLS")" -eq 1 ]
  [ "$(grep -c -x 'triage_fetch.sh --check' "$CALLS")" -eq 1 ]
  [ "$(grep -c -x 'dtcc_watch.py --check' "$CALLS")" -eq 1 ]
  grep -qx 'telemetry_fetch.py --check prod-sentry' "$CALLS"
  grep -qx 'telemetry_fetch.py --check prod-adx' "$CALLS"
}

@test "a telemetry source list that fails is a failed source, never no source (audit C5)" {
  STUB_LIST_RC=1 run "$SC"
  [ "$status" -eq 1 ]
  grep -q '^telemetry: failed: ' <<< "$output"
  run grep -c 'telemetry_fetch.py --check' "$CALLS"
  [ "$output" = 0 ]
}

@test "failing telemetry sources are each named; the Python scripts' reasons come from stdout" {
  printf '#!/bin/bash\necho "telemetry_fetch.py $*" >> "$CALLS"\n[[ "$1" == --list ]] && { printf "prod-sentry\\nprod-adx\\n"; exit 0; }\necho "telemetry_fetch: $2: HTTP 401"\nexit 1\n' > system/scripts/telemetry_fetch.py
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'telemetry: failed: prod-sentry: HTTP 401; prod-adx: HTTP 401' <<< "$output"
}

@test "a check that hits its timeout reads timed out, and the run goes on to the next source" {
  printf '#!/bin/bash\necho "calendar_fetch.sh $*" >> "$CALLS"\nsleep 5\n' > system/scripts/calendar_fetch.sh
  SMOKE_CALENDAR_TIMEOUT=1 run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'calendar: failed: timed out after 1s' <<< "$output"
  grep -qx 'dtcc: off' <<< "$output"
  [ "$(jq -r 'select(.source == "calendar") | .exit' "$LOG")" = 124 ]
}

@test "a claude version change is reported once with the acceptance steps, and the file follows" {
  mkdir -p system/logs
  printf '0.9.0 (Claude Code)\n' > system/logs/claude.version
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'version: failed: claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code)' <<< "$output"
  alerts | grep -qF '[smoke] version claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code); re-run the acceptance steps (FOUNDRY.md Development)'
  [ "$(cat system/logs/claude.version)" = "1.0.0 (Claude Code)" ]
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'version: ok' <<< "$output"
  [ "$(alerts | grep -c '\[smoke\]')" -eq 1 ]
}

@test "an older vault's claude_version file is taken over, so a change since its last health check is reported" {
  mkdir -p system/logs
  printf '0.9.0 (Claude Code)\n' > system/logs/claude_version
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'version: failed: claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code)' <<< "$output"
  [ "$(cat system/logs/claude.version)" = "1.0.0 (Claude Code)" ]
  [ ! -e system/logs/claude_version ]
}

@test "a missing claude is a failed version check and the other sources still run" {
  rm "$BATS_TEST_TMPDIR/bin/claude"
  CLAUDE_BIN=/nonexistent/claude run "$SC"
  [ "$status" -eq 1 ]
  grep -q '^version: failed: ' <<< "$output"
  grep -qx 'calendar: ok' <<< "$output"
  [ ! -e system/logs/claude.version ]
}

@test "the version is the first stdout line only, so a stderr notice never changes the recorded reading" {
  printf '#!/bin/bash\necho "update available" >&2\necho "1.0.0 (Claude Code)"\necho "more"\n' > "$BATS_TEST_TMPDIR/bin/claude"
  run "$SC"
  [ "$status" -eq 0 ]
  [ "$(cat system/logs/claude.version)" = "1.0.0 (Claude Code)" ]
}

@test "a client runs no checks" {
  set_key machine_role '"client"'
  run "$SC"
  [ "$status" -eq 0 ]
  [ "$output" = "client: no checks" ]
  [ ! -e "$CALLS" ]
}

@test "an argument is a usage error" {
  run "$SC" --quiet
  [ "$status" -eq 2 ]
  [ ! -e "$CALLS" ]
}
