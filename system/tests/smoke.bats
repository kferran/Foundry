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
  stub triage_fetch.sh 0 "triage_fetch: 0 threads need you" 1
  # Units (#166): an empty unit directory, and a systemctl that answers from $STUB_TIMERS lines
  # "<timer>|<LastTriggerUSec>|<SubState>"; a timer with no line is not enabled. Other verbs succeed silently.
  cp -r "$REPO/system/systemd" system/systemd
  export SYSTEMD_USER_DIR="$BATS_TEST_TMPDIR/units" SYSTEMCTL="$BATS_TEST_TMPDIR/bin/systemctl"
  export STUB_TIMERS="$BATS_TEST_TMPDIR/timers"
  UD="$SYSTEMD_USER_DIR"
  mkdir -p "$UD"
  touch "$STUB_TIMERS"
  cat > "$SYSTEMCTL" <<'EOF'
#!/bin/bash
[[ "$2" == is-enabled || "$2" == show ]] || exit 0
line="$(grep -F "${*: -1}|" "$STUB_TIMERS")" || exit 1
[[ "$2" != show ]] || { IFS='|' read -r _ last sub <<< "$line"; printf 'LastTriggerUSec=%s\nSubState=%s\n' "$last" "$sub"; }
EOF
  chmod +x "$SYSTEMCTL"
}

# timer <name> <schedule line> <seconds ago or ""> [substate]: an installed timer of this vault, enabled, last
# triggered that long ago ("" for never), as systemctl prints it under TZ=UTC.
timer() {
  printf '# Managed by vault: %s\n[Timer]\n%s\n' "$(pwd -P)" "$2" > "$UD/$1"
  local last=""
  [[ -z "$3" ]] || last="$(TZ=UTC date -d "@$(( $(date +%s) - $3 ))" '+%a %F %T %Z')"
  printf '%s|%s|%s\n' "$1" "$last" "${4:-waiting}" >> "$STUB_TIMERS"
}

# stub <script> <exit> <message> [stream]: the vault's copy of a fetch records its call, prints the message to stderr
# (or the stream given) and exits with the code.
stub() {
  local f="system/scripts/$1" fd="${4:-2}"
  cat > "$f" <<EOF
#!/bin/bash
echo "$1 \$*" >> "\$CALLS"
[[ -z "$3" ]] || echo "$3" >&$fd
exit $2
EOF
  chmod +x "$f"
}

set_key() { sed -i "s/^$1:.*/$1: $2/;t;\$i $1: $2" system/config.md; }
alerts() { cat system/logs/alerts_*.md 2>/dev/null || true; }
# items <row…>: the fixture extension checked per item, on, listing these "item<tab>credential<tab>renewal" rows.
items() {
  use_extension items
  mkdir -p system/logs
  printf '%s\n' "$@" > system/logs/items.list
}

@test "every configured source reads ok and the rest off; the version is recorded, nothing is alerted" {
  need_user_systemd
  run "$SC"
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "version: ok" ]
  [ "${lines[1]}" = "calendar: ok" ]
  [ "${lines[2]}" = "meetings: off" ]
  [ "${lines[3]}" = "triage: off" ]
  [ "$(cat system/logs/claude.version)" = "1.0.0 (Claude Code)" ]
  [ -z "$(alerts)" ]
  [ "$(jq -r 'select(.source == "calendar") | .exit' "$LOG")" = 0 ]
  grep -qx 'calendar_fetch.sh --check' "$CALLS"
  run grep -c -e meetings_fetch -e triage_fetch "$CALLS"
  [ "$output" = 0 ]
}

@test "a failing source reads failed with the script's reason, exits 1 and alerts once a day" {
  need_user_systemd
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

@test "a reason drops only the script's prefix" {
  stub calendar_fetch.sh 6 $'claude: some noise\nmore noise\ncalendar_fetch: no Google Calendar connector'
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'calendar: failed: no Google Calendar connector' <<< "$output"
}

@test "at the usage ceiling the connector checks are held, not failed, with one alert a day; the local checks still run" {
  need_user_systemd
  printf '#!/bin/bash\n[[ "$1" == hold ]] || exit 2\necho "five-hour usage 0.7 is at or above 0.6"\n' > system/scripts/triage.py
  chmod +x system/scripts/triage.py
  set_key meetings_enabled '"true"'
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'version: ok' <<< "$output"
  grep -qx 'calendar: held: five-hour usage 0.7 is at or above 0.6' <<< "$output"
  grep -qx 'meetings: held: five-hour usage 0.7 is at or above 0.6' <<< "$output"
  grep -qx 'triage: off' <<< "$output"
  # No check ran, so no call was logged (the log may not exist at all).
  run grep -c -e calendar_fetch -e meetings_fetch <<< "$(cat "$CALLS" 2>/dev/null)"
  [ "$output" = 0 ]
  alerts | grep -qF '[smoke] held: five-hour usage 0.7 is at or above 0.6; the connector checks did not run'
  run "$SC"
  [ "$(alerts | grep -c '\[smoke\]')" -eq 1 ]
}

@test "two failing sources give two alert lines" {
  need_user_systemd
  set_key meetings_enabled '"true"'
  stub calendar_fetch.sh 6 "calendar_fetch: no Google Calendar connector"
  stub meetings_fetch.sh 3 "meetings_fetch: no Google Drive connector"
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'meetings: failed: no Google Drive connector' <<< "$output"
  [ "$(alerts | grep -c '\[smoke\]')" -eq 2 ]
}

@test "enabled features are each checked once; an extension's per-item source checks each listed item" {
  need_user_systemd
  set_key meetings_enabled '"true"'
  set_key triage_enabled '"true"'
  items prod-a prod-b
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'items/prod-a: ok' <<< "$output"
  grep -qx 'items/prod-b: ok' <<< "$output"
  [ "$(grep -c -x 'meetings_fetch.sh --check' "$CALLS")" -eq 1 ]
  [ "$(grep -c -x 'triage_fetch.sh --check --source mail' "$CALLS")" -eq 1 ]
  grep -qx 'triage_chat: off' <<< "$output"
}

@test "chat triage is its own line: an expired Slack login names the Slack connector, mail still reads ok" {
  need_user_systemd
  set_key triage_enabled '"true"'
  set_key triage_chat_enabled '"true"'
  cat > system/scripts/triage_fetch.sh <<'EOF'
#!/bin/bash
echo "triage_fetch.sh $*" >> "$CALLS"
if [[ "$*" == *chat* ]]; then echo "triage_fetch: auth: no Slack connector reachable" >&2; exit 3; fi
echo "triage_fetch: 0 threads need the owner"
EOF
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'triage: ok' <<< "$output"
  grep -qx 'triage_chat: expired: Slack connector; renew: reconnect it at claude.ai, Settings, Connectors' <<< "$output"
  grep -qx 'triage_fetch.sh --check --source chat' "$CALLS"
}

@test "a per-item list that fails is a failed source, never no item; an empty list is off (audit C5)" {
  items prod-a
  touch system/logs/items.fail
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'items: failed: items_list.sh failed (exit 1): other: the list broke' <<< "$output"
  run grep -c '^items/' <<< "$output"
  [ "$output" = 0 ]
  rm system/logs/items.fail
  : > system/logs/items.list
  run "$SC"
  grep -qx 'items: off' <<< "$output"
}

@test "failing items each get their own line, the reason without the item's name; the others still read ok" {
  items prod-a prod-b prod-c
  printf 'prod-a\tconnector: HTTP 503\nprod-b\tconnector: HTTP 503\n' > system/logs/items.bad
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'items/prod-a: failed: connector: HTTP 503' <<< "$output"
  grep -qx 'items/prod-b: failed: connector: HTTP 503' <<< "$output"
  grep -qx 'items/prod-c: ok' <<< "$output"
}

@test "an auth failure names the credential and its renewal, one alert a day per credential (connector health spec §2)" {
  set_key meetings_enabled '"true"'
  use_extension demo   # an extension's credential comes from its manifest (extensions spec §3)
  stub calendar_fetch.sh 3 "calendar_fetch: auth: no Google Calendar connector reachable"
  stub meetings_fetch.sh 6 "meetings_fetch: auth: HTTP 401 from Drive"
  export DEMO_CHECK_MODE=expired
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'calendar: expired: Google connector; renew: reconnect it at claude.ai, Settings, Connectors' <<< "$output"
  grep -qx 'demo: expired: Demo connector; renew: reconnect it at example.invalid' <<< "$output"
  [ "$(jq -r 'select(.source == "calendar") | .reason' "$LOG")" = "auth: no Google Calendar connector reachable" ]
  # calendar and meetings share the Google connector: one alert for it, one for the demo connector
  [ "$(alerts | grep -c '\[smoke\] expired Google connector:')" -eq 1 ]
  [ "$(alerts | grep -c '\[smoke\] expired Demo connector:')" -eq 1 ]
  [ "$(alerts | grep -c '\[smoke\] expired')" -eq 2 ]
  run grep -c -e '\[smoke\] calendar' -e '\[smoke\] meetings' -e '\[smoke\] demo' <<< "$(alerts)"
  [ "$output" = 0 ]
  run "$SC"
  [ "$(alerts | grep -c '\[smoke\] expired')" -eq 2 ]
}

@test "an item's auth failure names the credential its list gives" {
  items $'prod-a\tItem token\twrite a new token'
  printf 'prod-a\tauth: HTTP 401\n' > system/logs/items.bad
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'items/prod-a: expired: Item token; renew: write a new token' <<< "$output"
  alerts | grep -qF '[smoke] expired Item token: renew: write a new token (items/prod-a: auth: HTTP 401)'
}

@test "a network failure reads unreachable and alerts only when the previous check failed the same way" {
  items prod-a
  printf 'prod-a\tnetwork: example.invalid (URLError)\n' > system/logs/items.bad
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'items/prod-a: unreachable: example.invalid' <<< "$output"
  run grep -c 'unreachable' <<< "$(alerts)"
  [ "$output" = 0 ]
  run "$SC"
  [ "$(alerts | grep -c '\[smoke\] unreachable example.invalid:')" -eq 1 ]
  alerts | grep -qF "since $(TZ=America/Denver date +%F); check the VPN or network route to example.invalid"
  run "$SC"
  [ "$(alerts | grep -c 'unreachable')" -eq 1 ]
}

@test "a check that hits its timeout reads timed out, and the run goes on to the next source" {
  printf '#!/bin/bash\necho "calendar_fetch.sh $*" >> "$CALLS"\nsleep 5\n' > system/scripts/calendar_fetch.sh
  SMOKE_CALENDAR_TIMEOUT=1 run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'calendar: failed: timed out after 1s' <<< "$output"
  grep -qx 'meetings: off' <<< "$output"
  [ "$(jq -r 'select(.source == "calendar") | .exit' "$LOG")" = 124 ]
}

@test "a claude version change is reported once with the acceptance steps, not as a failure, and the file follows" {
  need_user_systemd
  mkdir -p system/logs
  printf '0.9.0 (Claude Code)\n' > system/logs/claude.version
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'version: changed: claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code)' <<< "$output"
  [ "$(jq -r 'select(.source == "version") | .exit' "$LOG")" = 0 ]
  alerts | grep -qF '[smoke] version claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code); re-run the acceptance steps (FOUNDRY.md Development)'
  run grep -c failed <<< "$(alerts)"
  [ "$output" = 0 ]
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
  [ "$status" -eq 0 ]
  grep -qx 'version: changed: claude 0.9.0 (Claude Code) -> 1.0.0 (Claude Code)' <<< "$output"
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
  need_user_systemd
  printf '#!/bin/bash\necho "update available" >&2\necho "1.0.0 (Claude Code)"\necho "more"\n' > "$BATS_TEST_TMPDIR/bin/claude"
  run "$SC"
  [ "$status" -eq 0 ]
  [ "$(cat system/logs/claude.version)" = "1.0.0 (Claude Code)" ]
}

@test "an enabled timer past its next tick plus the grace reads stale and alerts once a day; on time reads ok (#166)" {
  timer foundry-brief.timer 'OnCalendar=*-*-* 06:00:00 America/Denver' $(( 3 * 86400 ))
  timer foundry-debrief.timer 'OnCalendar=*-*-* 17:00:00 America/Denver' 3600
  timer foundry-intake.timer 'OnUnitActiveSec=5min' 120
  timer foundry-telemetry.timer 'OnUnitActiveSec=1h' $(( 3 * 3600 ))
  since="$(TZ=America/Denver date -d "@$(( $(date +%s) - 3 * 86400 ))" '+%F %H:%M')"
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx "foundry-brief.timer: stale: no run since $since" <<< "$output"
  grep -qx 'foundry-debrief.timer: ok' <<< "$output"
  grep -qx 'foundry-intake.timer: ok' <<< "$output"
  grep -q '^foundry-telemetry.timer: stale: no run since ' <<< "$output"
  alerts | grep -qF "[smoke] foundry-brief.timer stale: no run since $since"
  [ "$(jq -r 'select(.source == "foundry-brief.timer") | .exit' "$LOG")" = 1 ]
  run "$SC"
  [ "$(alerts | grep -c 'stale:')" -eq 2 ]
}

@test "a 15-minute timer that fired 10 minutes ago reads ok in a timezone east of UTC (#166)" {
  sed -i 's|^timezone:.*|timezone: "Asia/Tokyo"|' system/config.md
  timer foundry-nightshift.timer 'OnCalendar=*:0/15' 600
  run "$SC"
  grep -qx 'foundry-nightshift.timer: ok' <<< "$output"
}

@test "the next tick is read under either label systemd gives the second iteration (Iter. #2 to 254, Iteration #2 from 255) (#166)" {
  # A systemd-analyze whose calendar verb prints ticks 15 and 30 minutes after --base-time under $STUB_LABEL; every
  # other verb is the real one.
  real="$(command -v systemd-analyze)"
  cat > "$BATS_TEST_TMPDIR/bin/systemd-analyze" <<EOF
#!/bin/bash
[[ "\$1" == calendar ]] || exec "$real" "\$@"
b="\$(sed -n 's/^--base-time=@//p' <<< "\$3")"
printf '  Original form: %s\n    Next elapse: %s\n       From now: soon\n   %s: %s\n       From now: later\n' "\${*: -1}" \\
  "\$(date -u -d "@\$(( b + 900 ))" '+%a %F %T UTC')" "\$STUB_LABEL" "\$(date -u -d "@\$(( b + 1800 ))" '+%a %F %T UTC')"
EOF
  chmod +x "$BATS_TEST_TMPDIR/bin/systemd-analyze"
  timer foundry-nightshift.timer 'OnCalendar=*:0/15' 600
  STUB_LABEL='Iter. #2' run "$SC"
  grep -qx 'foundry-nightshift.timer: ok' <<< "$output"
  STUB_LABEL='Iteration #2' run "$SC"
  grep -qx 'foundry-nightshift.timer: ok' <<< "$output"
}

@test "a timer never triggered reads unknown, one running its service reads ok, a disabled one reads off (#166)" {
  timer foundry-brief.timer 'OnCalendar=*-*-* 06:00:00 America/Denver' ""
  timer foundry-intake.timer 'OnUnitActiveSec=5min' $(( 2 * 3600 )) running
  printf '# Managed by vault: %s\n[Timer]\nOnCalendar=*:0/15\n' "$(pwd -P)" > "$UD/foundry-nightshift.timer"
  printf '# Managed by vault: /elsewhere\n[Timer]\nOnCalendar=*:0/15\n' > "$UD/foundry-notify.timer"
  run "$SC"
  grep -qx 'foundry-brief.timer: unknown' <<< "$output"
  grep -qx 'foundry-intake.timer: ok' <<< "$output"
  grep -qx 'foundry-nightshift.timer: off' <<< "$output"
  run grep -c foundry-notify <<< "$output"
  [ "$output" = 0 ]
  # The hand-written timers differ from the render (the drift line's business); no timer line alerts.
  run grep -c 'stale:' <<< "$(alerts)"
  [ "$output" = 0 ]
}

@test "installed units that match the render read ok; a unit never installed is left out, never differs (#166)" {
  need_user_systemd
  run "$SC"
  grep -qx 'units: off' <<< "$output"
  run system/scripts/install_units.sh
  [ "$status" -eq 0 ]
  rm "$UD/foundry-smoke.timer"
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'units: ok' <<< "$output"
  run grep -c differs <<< "$output"
  [ "$output" = 0 ]
}

@test "an edited unit and an edited drop-in each read differs and alert once a day, naming the fix (#166)" {
  need_user_systemd
  set_key machine_role '"server"'
  run system/scripts/install_units.sh
  [ "$status" -eq 0 ]
  echo '# edited' >> "$UD/foundry-intake.service"
  echo '# edited' >> "$UD/foundry-intake.service.d/foundry-sync.conf"
  run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'units: differs: foundry-intake.service' <<< "$output"
  grep -qx 'units: differs: foundry-intake.service.d/foundry-sync.conf' <<< "$output"
  run grep -c '^units: ' <<< "$output"
  [ "$output" = 2 ]
  alerts | grep -qF '[smoke] foundry-intake.service differs: run system/scripts/install_units.sh --update'
  alerts | grep -qF '[smoke] foundry-intake.service.d/foundry-sync.conf differs: run system/scripts/install_units.sh --update'
  run "$SC"
  [ "$(alerts | grep -c '\[smoke\]')" -eq 2 ]
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

@test "an enabled extension's smoke entry runs and reads ok or failed like a core source" {
  need_user_systemd
  use_extension demo
  run "$SC"
  [ "$status" -eq 0 ]
  grep -qx 'demo: ok' <<< "$output"
  [ "$(jq -r 'select(.source == "demo") | .exit' "$LOG")" = "0" ]
}

@test "an expired credential from a manifest names it and its renewal" {
  need_user_systemd
  use_extension demo
  DEMO_CHECK_MODE=expired run "$SC"
  [ "$status" -eq 1 ]
  grep -qx 'demo: expired: Demo connector; renew: reconnect it at example.invalid' <<< "$output"
  [ "$(alerts | grep -c '\[smoke\] expired Demo connector:')" -eq 1 ]
}

@test "without extensions the smoke check prints no extension line" {
  need_user_systemd
  run "$SC"
  [ "$status" -eq 0 ]
  run grep -c '^demo' <<< "$output"
  [ "$status" -ne 0 ]
}
