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
  for s in calendar_fetch.sh meetings_fetch.sh jira_fetch.sh triage_fetch.sh dtcc_watch.py; do stub "$s" 0 ""; done
  stub telemetry_fetch.py 0 ""
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

@test "a failing telemetry source names it; the Python scripts' reasons come from stdout" {
  printf '#!/bin/bash\necho "telemetry_fetch.py $*" >> "$CALLS"\n[[ "$1" == --list ]] && { echo prod-sentry; exit 0; }\necho "telemetry_fetch: prod-sentry: HTTP 401"\nexit 1\n' > system/scripts/telemetry_fetch.py
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'telemetry: failed: prod-sentry: HTTP 401' <<< "$output"
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

@test "a missing claude is a failed version check and the other sources still run" {
  rm "$BATS_TEST_TMPDIR/bin/claude"
  CLAUDE_BIN=/nonexistent/claude run "$SC"
  [ "$status" -eq 1 ]
  grep -q '^version: failed: ' <<< "$output"
  grep -qx 'calendar: ok' <<< "$output"
  [ ! -e system/logs/claude.version ]
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
