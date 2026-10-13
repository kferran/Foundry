#!/usr/bin/env bats
# install_units.sh and the unit templates (spec §6.10). systemctl is always a stub; systemd-analyze is real.
load helpers

UNITS=(foundry-intake.service foundry-intake.timer foundry-brief.service foundry-brief.timer
       foundry-debrief.service foundry-debrief.timer foundry-smoke.service foundry-smoke.timer)

setup() {
  make_vault
  cp -r "$REPO/system/systemd" "$V/system/systemd"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  ln -s "$REPO/system/tests/stub_claude" "$STUBS/claude"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n' > "$STUBS/systemctl"
  chmod +x "$STUBS/systemctl"
  export PATH="$STUBS:$PATH" SYSTEMCTL="$STUBS/systemctl" STUB_SYSTEMCTL_LOG="$BATS_TEST_TMPDIR/systemctl.log"
  export SYSTEMD_USER_DIR="$BATS_TEST_TMPDIR/units" HOME="$BATS_TEST_TMPDIR/home"
  UD="$SYSTEMD_USER_DIR"
  move_vault "$V"
}

move_vault() {  # <new path>: relocate the vault and re-derive the paths the tests compare against
  [ "$1" = "$V" ] || mv "$V" "$1"
  V="$1"
  VP="$(cd "$V" && pwd -P)"
  cd "$V"
  IU="$V/system/scripts/install_units.sh"
}

@test "every template renders with all placeholders replaced and the ownership header" {
  run "$IU"
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    [ -f "$UD/$n" ]
    grep -qx "new $n" <<< "$output"
    [ "$(head -n 1 "$UD/$n")" = "# Managed by vault: $VP" ]
  done
  run grep -l '{{' "$UD"/*
  [ "$status" -eq 1 ]
}

@test "services carry TZ, PATH, an unresolved CLAUDE_BIN and their timeouts" {
  run "$IU"
  [ "$status" -eq 0 ]
  for s in intake brief debrief; do
    f="$UD/foundry-$s.service"
    grep -qxF 'Environment="TZ=America/Denver"' "$f"
    grep -qxF "Environment=\"PATH=$STUBS:%h/.local/bin:/usr/local/bin:/usr/bin:/bin\"" "$f"
    grep -qxF "Environment=\"CLAUDE_BIN=$STUBS/claude\"" "$f"
    grep -q '^TimeoutStartSec=' "$f"
  done
  run grep -l stub_claude "$UD"/*
  [ "$status" -eq 1 ]
  grep -qx 'TimeoutStartSec=90min' "$UD/foundry-intake.service"
  # The brief's worst case (prep fetches, the lock wait, a 15-minute session, publish) is about 47 minutes (audit C6).
  grep -qx 'TimeoutStartSec=60min' "$UD/foundry-brief.service"
  grep -qx 'TimeoutStartSec=45min' "$UD/foundry-debrief.service"
  grep -qxF "ExecStartPre=-\"$VP/system/scripts/brief_prep.sh\"" "$UD/foundry-brief.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/foundry-brief.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" debrief" "$UD/foundry-debrief.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/intake_daemon.sh\"" "$UD/foundry-intake.service"
}

@test "timers fire at the configured times in the configured timezone" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF 'OnCalendar=*-*-* 06:00:00 America/Denver' "$UD/foundry-brief.timer"
  grep -qxF 'OnCalendar=*-*-* 17:00:00 America/Denver' "$UD/foundry-debrief.timer"
  grep -qx 'Persistent=true' "$UD/foundry-brief.timer"
  grep -qx 'Persistent=true' "$UD/foundry-debrief.timer"
}

@test "installing reloads systemd and enables the timers" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx -- '--user daemon-reload' "$STUB_SYSTEMCTL_LOG"
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-smoke.timer foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "a second run reports every unit unchanged and rewrites nothing" {
  run "$IU"
  touch -d 2000-01-01 "$UD"/*
  run "$IU"
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    grep -qx "unchanged $n" <<< "$output"
    [ "$(stat -c %Y "$UD/$n")" = "$(date -d 2000-01-01 +%s)" ]
  done
}

@test "a config change rewrites only the units it affects" {
  run "$IU"
  system/scripts/vault_index.py set system/config.md brief_time 07:30
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'changed foundry-brief.timer' <<< "$output"
  grep -qx 'unchanged foundry-brief.service' <<< "$output"
  grep -qxF 'OnCalendar=*-*-* 07:30:00 America/Denver' "$UD/foundry-brief.timer"
}

@test "--dry-run prints the rendered units and touches nothing" {
  run "$IU" --dry-run
  [ "$status" -eq 0 ]
  grep -qx '===== foundry-brief.timer' <<< "$output"
  grep -qxF 'OnCalendar=*-*-* 06:00:00 America/Denver' <<< "$output"
  [ ! -e "$UD" ]
  [ ! -e "$STUB_SYSTEMCTL_LOG" ]
}

@test "--uninstall removes only this vault's units" {
  run "$IU"
  printf '[Unit]\nDescription=foreign\n' > "$UD/foreign.service"
  printf '# Managed by vault: /elsewhere\n[Unit]\n' > "$UD/other.timer"
  run "$IU" --uninstall
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    [ ! -e "$UD/$n" ]
    grep -qx "removed $n" <<< "$output"
  done
  [ -f "$UD/foreign.service" ]
  [ -f "$UD/other.timer" ]
  grep -q -- '^--user disable --now .*foundry-brief.timer' "$STUB_SYSTEMCTL_LOG"
  run grep -E 'foreign|other' "$STUB_SYSTEMCTL_LOG"
  [ "$status" -eq 1 ]
}

@test "moving the vault re-points its units" {
  run "$IU"
  move_vault "$BATS_TEST_TMPDIR/moved"
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'changed foundry-brief.service' <<< "$output"
  [ "$(head -n 1 "$UD/foundry-brief.service")" = "# Managed by vault: $VP" ]
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/foundry-brief.service"
}

@test "a vault path with spaces renders quoted paths that systemd accepts" {
  move_vault "$BATS_TEST_TMPDIR/my vault"
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/foundry-brief.service"
  grep -qxF "WorkingDirectory=$VP" "$UD/foundry-brief.service"
}

@test "a vault path a unit file cannot carry is refused before anything is written" {
  move_vault "$BATS_TEST_TMPDIR/100%vault"
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"contains characters a unit file cannot carry"* ]]
  [ ! -e "$UD" ]
}

@test "an invalid config is refused before anything is written" {
  sed -i 's/^brief_time: .*/brief_time: "6am"/' system/config.md
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"invalid"* ]]
  [ ! -e "$UD" ]
}

@test "a template systemd rejects fails the install before anything is written" {
  sed -i 's|intake_daemon.sh|missing.sh|' system/systemd/foundry-intake.service.in
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"systemd-analyze"* ]]
  [ ! -e "$UD" ]
}

@test "an unknown placeholder is refused" {
  printf 'Documentation={{NOPE}}\n' >> system/systemd/foundry-intake.timer.in
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"unreplaced placeholder {{NOPE}}"* ]]
  [ ! -e "$UD" ]
}

@test "a same-named unit that no vault manages is never overwritten" {
  mkdir -p "$UD"
  printf '[Unit]\nDescription=mine\n' > "$UD/foundry-brief.service"
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"is not managed by a vault"* ]]
  grep -qx 'Description=mine' "$UD/foundry-brief.service"
  [ ! -e "$UD/foundry-intake.service" ]
}

@test "a unit owned by another vault that still exists is never overwritten" {
  mkdir -p "$UD" "$BATS_TEST_TMPDIR/other/system/scripts"
  printf '# Managed by vault: %s\n[Unit]\n' "$BATS_TEST_TMPDIR/other" > "$UD/foundry-brief.service"
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"belongs to the vault at $BATS_TEST_TMPDIR/other"* ]]
  [ ! -e "$UD/foundry-intake.service" ]
}

@test "unknown arguments exit 2" {
  run "$IU" --bogus
  [ "$status" -eq 2 ]
  run "$IU" --dry-run --uninstall
  [ "$status" -eq 2 ]
}

set_role() { system/scripts/vault_index.py set system/config.md machine_role "$1" > /dev/null; }

@test "machine_role server installs the run units and the sync timer" {
  set_role server
  run "$IU"
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    [ -f "$UD/$n" ]
  done
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-smoke.timer foundry-sync.timer foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "machine_role client installs nothing and says so" {
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'install_units: machine_role client: no units' <<< "$output"
  [ ! -e "$UD" ]
  [ ! -e "$STUB_SYSTEMCTL_LOG" ]
  run "$IU" --dry-run
  [ "$status" -eq 0 ]
  grep -qx 'install_units: machine_role client: no units' <<< "$output"
}

@test "a role change removes the owned units the new role does not use" {
  set_role server
  run "$IU"
  [ -f "$UD/foundry-sync.timer" ]
  set_role standalone
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-sync.timer' <<< "$output"
  [ ! -e "$UD/foundry-sync.timer" ]
  grep -q -- '^--user disable --now .*foundry-sync.timer' "$STUB_SYSTEMCTL_LOG"
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    [ ! -e "$UD/$n" ]
  done
  grep -qx 'removed foundry-brief.timer' <<< "$output"
}

@test "a role change never removes units this vault does not own" {
  run "$IU"
  printf '[Unit]\nDescription=foreign\n' > "$UD/foreign.service"
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  [ -f "$UD/foreign.service" ]
}

@test "a server gets the sync timer and one drop-in per run service, sync around the run" {
  set_role server
  sed -i '/^machine_role:/a sync_interval_minutes: "7"' system/config.md
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'OnUnitActiveSec=7min' "$UD/foundry-sync.timer"
  grep -qx 'TimeoutStartSec=10min' "$UD/foundry-sync.service"
  grep -qx 'SuccessExitStatus=4' "$UD/foundry-sync.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/vault_sync.sh\"" "$UD/foundry-sync.service"
  for s in intake brief debrief; do
    d="$UD/foundry-$s.service.d/foundry-sync.conf"
    [ "$(head -n 1 "$d")" = "# Managed by vault: $VP" ]
    grep -qx "new foundry-$s.service.d/foundry-sync.conf" <<< "$output"
  done
  [ "$(grep '^Exec' "$UD/foundry-brief.service.d/foundry-sync.conf")" = "$(printf 'ExecStartPre=\nExecStartPre="%s/system/scripts/vault_sync.sh" --pre\nExecStartPre=-"%s/system/scripts/brief_prep.sh"\nExecStartPost="%s/system/scripts/vault_sync.sh" --post' "$VP" "$VP" "$VP")" ]
  grep -qxF "ExecStartPre=-\"$VP/system/scripts/debrief_prep.sh\"" "$UD/foundry-debrief.service.d/foundry-sync.conf"
  [ "$(grep -c '^ExecStartPre=' "$UD/foundry-intake.service.d/foundry-sync.conf")" -eq 2 ]
  grep -qx 'TimeoutStartSec=105min' "$UD/foundry-intake.service.d/foundry-sync.conf"
  grep -qx 'TimeoutStartSec=75min' "$UD/foundry-brief.service.d/foundry-sync.conf"
  grep -qx 'TimeoutStartSec=60min' "$UD/foundry-debrief.service.d/foundry-sync.conf"
  run "$IU"
  grep -qx 'unchanged foundry-brief.service.d/foundry-sync.conf' <<< "$output"
}

@test "a standalone machine gets no sync units or drop-ins" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-sync.timer" ]
  run ls -d "$UD"/*.service.d
  [ "$status" -ne 0 ]
}

@test "leaving the server role removes the sync units and the owned drop-ins, never a foreign one" {
  set_role server
  run "$IU"
  printf '[Service]\nNice=5\n' > "$UD/foundry-brief.service.d/local.conf"
  set_role standalone
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-sync.timer' <<< "$output"
  grep -qx 'removed foundry-intake.service.d/foundry-sync.conf' <<< "$output"
  [ ! -e "$UD/foundry-sync.service" ]
  [ ! -e "$UD/foundry-intake.service.d" ]
  [ ! -e "$UD/foundry-brief.service.d/foundry-sync.conf" ]
  [ -f "$UD/foundry-brief.service.d/local.conf" ]
}

@test "--uninstall removes the owned drop-ins too" {
  set_role server
  run "$IU"
  run "$IU" --uninstall
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-debrief.service.d/foundry-sync.conf' <<< "$output"
  run ls -A "$UD"
  [ -z "$output" ]
}

@test "the meetings fetch is installed only with meetings_enabled, on a server or standalone, hourly on workdays" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-meetings.timer" ]
  system/scripts/vault_index.py set system/config.md meetings_enabled true > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'new foundry-meetings.service' <<< "$output"
  grep -qxF 'OnCalendar=Mon..Fri *-*-* 08..18:00:00 America/Denver' "$UD/foundry-meetings.timer"
  grep -qx 'Persistent=false' "$UD/foundry-meetings.timer"
  grep -qxF "ExecStart=\"$VP/system/scripts/meetings_fetch.sh\"" "$UD/foundry-meetings.service"
  grep -qx 'TimeoutStartSec=35min' "$UD/foundry-meetings.service"
  grep -qxF "Environment=\"CLAUDE_BIN=$STUBS/claude\"" "$UD/foundry-meetings.service"
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-smoke.timer foundry-meetings.timer foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
  set_role server
  run "$IU"
  [ "$status" -eq 0 ]
  [ -f "$UD/foundry-meetings.timer" ]
  [ ! -e "$UD/foundry-meetings.service.d" ]
  system/scripts/vault_index.py set system/config.md meetings_enabled false > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-meetings.timer' <<< "$output"
  [ ! -e "$UD/foundry-meetings.service" ]
  system/scripts/vault_index.py set system/config.md meetings_enabled true > /dev/null
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-meetings.timer" ]
}

@test "inbox triage is installed only with triage_enabled, on a server or standalone, every 30 minutes on workdays" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-triage.timer" ]
  system/scripts/vault_index.py set system/config.md triage_enabled true > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'new foundry-triage.service' <<< "$output"
  grep -qxF 'OnCalendar=Mon..Fri *-*-* 08..17:00,30:00 America/Denver' "$UD/foundry-triage.timer"
  grep -qx 'Persistent=false' "$UD/foundry-triage.timer"
  grep -qxF "ExecStart=\"$VP/system/scripts/triage_fetch.sh\"" "$UD/foundry-triage.service"
  grep -qxF "Environment=\"CLAUDE_BIN=$STUBS/claude\"" "$UD/foundry-triage.service"
  grep -q -- 'foundry-triage.timer' "$STUB_SYSTEMCTL_LOG"
  set_role server
  run "$IU"
  [ "$status" -eq 0 ]
  [ -f "$UD/foundry-triage.timer" ]
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-triage.timer" ]
}

@test "Slack notices are installed only with a channel, on a server or standalone, every 5 minutes" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-notify.timer" ]
  system/scripts/vault_index.py set system/config.md slack_notify_channel C0EXAMPLE > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'new foundry-notify.service' <<< "$output"
  grep -qx 'OnCalendar=\*:0/5' "$UD/foundry-notify.timer"
  grep -qx 'Persistent=false' "$UD/foundry-notify.timer"
  grep -qxF "ExecStart=\"$VP/system/scripts/notify.sh\"" "$UD/foundry-notify.service"
  grep -q -- 'foundry-notify.timer' "$STUB_SYSTEMCTL_LOG"
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-notify.timer" ]
}

@test "a vault with an enabled telemetry source gets the telemetry timer; one without does not" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-telemetry.timer" ]
  mkdir -p "$V/system/telemetry" "$V/system/codebases"
  printf -- '---\ntype: codebase\nname: "x"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n' > "$V/system/codebases/x.md"
  printf -- '---\ntype: telemetry_source\nname: "p"\ncodebase: "x"\nenvironment: "prod"\nkind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n' > "$V/system/telemetry/p.md"
  run "$IU"
  [ "$status" -eq 0 ]
  grep -q '^OnUnitActiveSec=1h$' "$UD/foundry-telemetry.timer"
  grep -q 'telemetry_fetch.py' "$UD/foundry-telemetry.service"
  grep -q 'enable --now .*foundry-telemetry.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "a telemetry source list that fails stops the install and keeps the telemetry units (audit C5)" {
  mkdir -p "$V/system/telemetry" "$V/system/codebases"
  printf -- '---\ntype: codebase\nname: "x"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n' > "$V/system/codebases/x.md"
  printf -- '---\ntype: telemetry_source\nname: "p"\ncodebase: "x"\nenvironment: "prod"\nkind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n' > "$V/system/telemetry/p.md"
  run "$IU"
  [ -e "$UD/foundry-telemetry.timer" ]
  printf '#!/bin/bash\necho "telemetry_fetch: index locked" >&2\nexit 1\n' > "$V/system/scripts/telemetry_fetch.py"
  run "$IU" --update
  [ "$status" -eq 1 ]
  [[ "$output" == *"telemetry_fetch.py --list failed"* ]]
  [ -e "$UD/foundry-telemetry.timer" ]
}

@test "a server gets no sync drop-in for the telemetry service" {
  "$V/system/scripts/vault_index.py" set "$V/system/config.md" machine_role server
  mkdir -p "$V/system/telemetry" "$V/system/codebases"
  printf -- '---\ntype: codebase\nname: "x"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n' > "$V/system/codebases/x.md"
  printf -- '---\ntype: telemetry_source\nname: "p"\ncodebase: "x"\nenvironment: "prod"\nkind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n' > "$V/system/telemetry/p.md"
  run "$IU"
  [ "$status" -eq 0 ]
  [ -e "$UD/foundry-telemetry.timer" ]
  [ ! -e "$UD/foundry-telemetry.service.d" ]
}

@test "standalone and server get the nightshift timer every 15 minutes" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -q '^OnCalendar=\*:0/15$' "$UD/foundry-nightshift.timer"
  grep -q 'nightshift.py' "$UD/foundry-nightshift.service"
  grep -qx 'Description=The Foundry: Work Orders tick' "$UD/foundry-nightshift.service"
  grep -qx 'Description=The Foundry: Work Orders tick every 15 minutes' "$UD/foundry-nightshift.timer"
  grep -q 'enable --now .*foundry-nightshift.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "Work Orders and the update are installed when their keys are absent, so existing vaults keep them (#122)" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ -e "$UD/foundry-nightshift.timer" ]
  [ -e "$UD/foundry-update.timer" ]
  : > "$STUB_SYSTEMCTL_LOG"
  run "$IU" --update
  [ "$status" -eq 0 ]
  [ -e "$UD/foundry-nightshift.timer" ]
  [ -e "$UD/foundry-update.timer" ]
  grep -q 'enable --now .*foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "orders_enabled and update_enabled false install neither, and remove them when they were installed (#122)" {
  run "$IU"
  system/scripts/vault_index.py set system/config.md orders_enabled false > /dev/null
  system/scripts/vault_index.py set system/config.md update_enabled false > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-nightshift.timer' <<< "$output"
  grep -qx 'removed foundry-update.timer' <<< "$output"
  [ ! -e "$UD/foundry-nightshift.timer" ]
  [ ! -e "$UD/foundry-update.timer" ]
  system/scripts/vault_index.py set system/config.md orders_enabled true > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  [ -e "$UD/foundry-nightshift.timer" ]
  [ ! -e "$UD/foundry-update.timer" ]
}

@test "the committed example starts a new vault with Work Orders and the update off (#122)" {
  grep -q '^orders_enabled: "false" ' "$REPO/system/config.example.md"
  grep -q '^update_enabled: "false" ' "$REPO/system/config.example.md"
}

@test "a vault with a DTCC map gets the watch timer 30 minutes before the brief; one without does not" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-dtcc-watch.timer" ]
  mkdir -p "$V/system/dtcc"
  printf 'partition: work\n' > "$V/system/dtcc/map.yaml"
  run "$IU"
  [ "$status" -eq 0 ]
  grep -q '^OnCalendar=\*-\*-\* 05:30:00 ' "$UD/foundry-dtcc-watch.timer"
  grep -q 'dtcc_watch.py' "$UD/foundry-dtcc-watch.service"
  grep -q 'enable --now .*foundry-dtcc-watch.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "the update time follows brief_time and wraps past midnight (#117)" {
  system/scripts/vault_index.py set system/config.md brief_time 08:00 > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'OnCalendar=\*-\*-\* 07:15:00 America/Denver' "$UD/foundry-update.timer"
  system/scripts/vault_index.py set system/config.md brief_time 00:30 > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'OnCalendar=\*-\*-\* 23:45:00 America/Denver' "$UD/foundry-update.timer"
}

@test "standalone and server get the template update 45 minutes before the brief, a server with its sync drop-in (#87, #117)" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF "ExecStart=\"$VP/system/scripts/update_template.sh\" --unattended" "$UD/foundry-update.service"
  grep -qx 'OnCalendar=\*-\*-\* 05:15:00 America/Denver' "$UD/foundry-update.timer"
  grep -qx 'Persistent=true' "$UD/foundry-update.timer"
  [ ! -e "$UD/foundry-update.service.d" ]
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'TimeoutStartSec=35min' "$UD/foundry-update.service.d/foundry-sync.conf"
  grep -qxF "ExecStartPost=\"$VP/system/scripts/vault_sync.sh\" --post" "$UD/foundry-update.service.d/foundry-sync.conf"
  system/scripts/vault_index.py set system/config.md machine_role client > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-update.timer" ]
}

@test "standalone and server get the smoke check 15 minutes before the brief, never a client (smoke check spec §3.2)" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF "ExecStart=\"$VP/system/scripts/smoke_check.sh\"" "$UD/foundry-smoke.service"
  grep -qxF "Environment=\"CLAUDE_BIN=$STUBS/claude\"" "$UD/foundry-smoke.service"
  grep -qx 'SuccessExitStatus=1' "$UD/foundry-smoke.service"
  grep -qx 'TimeoutStartSec=25min' "$UD/foundry-smoke.service"
  grep -qxF 'OnCalendar=*-*-* 05:45:00 America/Denver' "$UD/foundry-smoke.timer"
  grep -qx 'Persistent=true' "$UD/foundry-smoke.timer"
  system/scripts/vault_index.py set system/config.md brief_time 00:10 > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF 'OnCalendar=*-*-* 23:55:00 America/Denver' "$UD/foundry-smoke.timer"
  set_role server
  run "$IU"
  [ "$status" -eq 0 ]
  [ -f "$UD/foundry-smoke.timer" ]
  [ ! -e "$UD/foundry-smoke.service.d" ]
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/foundry-smoke.timer" ]
}

@test "--update keeps a timer the owner disabled disabled, and re-enables only enabled ones (#87)" {
  "$IU" > /dev/null
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n[[ "$*" != *"is-enabled --quiet foundry-nightshift.timer"* ]]\n' > "$STUBS/systemctl"
  : > "$STUB_SYSTEMCTL_LOG"
  run "$IU" --update
  [ "$status" -eq 0 ]
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-smoke.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "--update removes a focus tracker an older template installed" {
  "$IU" > /dev/null
  printf '# Managed by vault: %s\n[Service]\nExecStart=/bin/true\n' "$VP" > "$UD/foundry-focus.service"
  : > "$STUB_SYSTEMCTL_LOG"
  run "$IU" --update
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-focus.service' <<< "$output"
  [ ! -e "$UD/foundry-focus.service" ]
  grep -qx -- '--user disable --now foundry-focus.service' "$STUB_SYSTEMCTL_LOG"
}
