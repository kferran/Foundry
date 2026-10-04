#!/usr/bin/env bats
# install_units.sh and the unit templates (spec §6.10). systemctl is always a stub; systemd-analyze is real.
load helpers

UNITS=(jarvis-intake.service jarvis-intake.timer jarvis-brief.service jarvis-brief.timer
       jarvis-debrief.service jarvis-debrief.timer jarvis-focus.service)

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
  for s in intake brief debrief focus; do
    f="$UD/jarvis-$s.service"
    grep -qxF 'Environment="TZ=America/Denver"' "$f"
    grep -qxF "Environment=\"PATH=$STUBS:%h/.local/bin:/usr/local/bin:/usr/bin:/bin\"" "$f"
    grep -qxF "Environment=\"CLAUDE_BIN=$STUBS/claude\"" "$f"
    grep -q '^TimeoutStartSec=' "$f"
  done
  run grep -l stub_claude "$UD"/*
  [ "$status" -eq 1 ]
  grep -qx 'TimeoutStartSec=90min' "$UD/jarvis-intake.service"
  grep -qx 'TimeoutStartSec=30min' "$UD/jarvis-brief.service"
  grep -qx 'TimeoutStartSec=20min' "$UD/jarvis-debrief.service"
  grep -qxF "ExecStartPre=-\"$VP/system/scripts/brief_prep.sh\"" "$UD/jarvis-brief.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/jarvis-brief.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" debrief" "$UD/jarvis-debrief.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/intake_daemon.sh\"" "$UD/jarvis-intake.service"
}

@test "timers fire at the configured times in the configured timezone" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF 'OnCalendar=*-*-* 06:00:00 America/Denver' "$UD/jarvis-brief.timer"
  grep -qxF 'OnCalendar=*-*-* 17:00:00 America/Denver' "$UD/jarvis-debrief.timer"
  grep -qx 'Persistent=true' "$UD/jarvis-brief.timer"
  grep -qx 'Persistent=true' "$UD/jarvis-debrief.timer"
}

@test "installing reloads systemd and enables the three timers and the focus tracker" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx -- '--user daemon-reload' "$STUB_SYSTEMCTL_LOG"
  grep -qx -- '--user enable --now jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer jarvis-focus.service' "$STUB_SYSTEMCTL_LOG"
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
  grep -qx 'changed jarvis-brief.timer' <<< "$output"
  grep -qx 'unchanged jarvis-brief.service' <<< "$output"
  grep -qxF 'OnCalendar=*-*-* 07:30:00 America/Denver' "$UD/jarvis-brief.timer"
}

@test "--dry-run prints the rendered units and touches nothing" {
  run "$IU" --dry-run
  [ "$status" -eq 0 ]
  grep -qx '===== jarvis-brief.timer' <<< "$output"
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
  grep -q -- '^--user disable --now .*jarvis-brief.timer' "$STUB_SYSTEMCTL_LOG"
  run grep -E 'foreign|other' "$STUB_SYSTEMCTL_LOG"
  [ "$status" -eq 1 ]
}

@test "moving the vault re-points its units" {
  run "$IU"
  move_vault "$BATS_TEST_TMPDIR/moved"
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'changed jarvis-brief.service' <<< "$output"
  [ "$(head -n 1 "$UD/jarvis-brief.service")" = "# Managed by vault: $VP" ]
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/jarvis-brief.service"
}

@test "a vault path with spaces renders quoted paths that systemd accepts" {
  move_vault "$BATS_TEST_TMPDIR/my vault"
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF "ExecStart=\"$VP/system/scripts/run_headless.sh\" brief" "$UD/jarvis-brief.service"
  grep -qxF "WorkingDirectory=$VP" "$UD/jarvis-brief.service"
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
  sed -i 's|intake_daemon.sh|missing.sh|' system/systemd/jarvis-intake.service.in
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"systemd-analyze"* ]]
  [ ! -e "$UD" ]
}

@test "an unknown placeholder is refused" {
  printf 'Documentation={{NOPE}}\n' >> system/systemd/jarvis-intake.timer.in
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"unreplaced placeholder {{NOPE}}"* ]]
  [ ! -e "$UD" ]
}

@test "a same-named unit that no vault manages is never overwritten" {
  mkdir -p "$UD"
  printf '[Unit]\nDescription=mine\n' > "$UD/jarvis-brief.service"
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"is not managed by a vault"* ]]
  grep -qx 'Description=mine' "$UD/jarvis-brief.service"
  [ ! -e "$UD/jarvis-intake.service" ]
}

@test "a unit owned by another vault that still exists is never overwritten" {
  mkdir -p "$UD" "$BATS_TEST_TMPDIR/other/system/scripts"
  printf '# Managed by vault: %s\n[Unit]\n' "$BATS_TEST_TMPDIR/other" > "$UD/jarvis-brief.service"
  run "$IU"
  [ "$status" -eq 1 ]
  [[ "$output" == *"belongs to the vault at $BATS_TEST_TMPDIR/other"* ]]
  [ ! -e "$UD/jarvis-intake.service" ]
}

@test "unknown arguments exit 2" {
  run "$IU" --bogus
  [ "$status" -eq 2 ]
  run "$IU" --dry-run --uninstall
  [ "$status" -eq 2 ]
}

set_role() { system/scripts/vault_index.py set system/config.md machine_role "$1" > /dev/null; }

@test "machine_role server installs the run units without the focus tracker" {
  set_role server
  run "$IU"
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    [ "$n" = jarvis-focus.service ] && continue
    [ -f "$UD/$n" ]
  done
  [ ! -e "$UD/jarvis-focus.service" ]
  grep -qx -- '--user enable --now jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer jarvis-sync.timer' "$STUB_SYSTEMCTL_LOG"
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
  run "$IU"
  [ -f "$UD/jarvis-focus.service" ]
  set_role server
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed jarvis-focus.service' <<< "$output"
  [ ! -e "$UD/jarvis-focus.service" ]
  grep -qx -- '--user disable --now jarvis-focus.service' "$STUB_SYSTEMCTL_LOG"
  set_role client
  run "$IU"
  [ "$status" -eq 0 ]
  for n in "${UNITS[@]}"; do
    [ ! -e "$UD/$n" ]
  done
  grep -qx 'removed jarvis-brief.timer' <<< "$output"
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
  grep -qx 'OnUnitActiveSec=7min' "$UD/jarvis-sync.timer"
  grep -qx 'TimeoutStartSec=10min' "$UD/jarvis-sync.service"
  grep -qx 'SuccessExitStatus=4' "$UD/jarvis-sync.service"
  grep -qxF "ExecStart=\"$VP/system/scripts/vault_sync.sh\"" "$UD/jarvis-sync.service"
  for s in intake brief debrief; do
    d="$UD/jarvis-$s.service.d/jarvis-sync.conf"
    [ "$(head -n 1 "$d")" = "# Managed by vault: $VP" ]
    grep -qx "new jarvis-$s.service.d/jarvis-sync.conf" <<< "$output"
  done
  [ "$(grep '^Exec' "$UD/jarvis-brief.service.d/jarvis-sync.conf")" = "$(printf 'ExecStartPre=\nExecStartPre="%s/system/scripts/vault_sync.sh" --pre\nExecStartPre=-"%s/system/scripts/brief_prep.sh"\nExecStartPost="%s/system/scripts/vault_sync.sh" --post' "$VP" "$VP" "$VP")" ]
  grep -qxF "ExecStartPre=-\"$VP/system/scripts/debrief_prep.sh\"" "$UD/jarvis-debrief.service.d/jarvis-sync.conf"
  [ "$(grep -c '^ExecStartPre=' "$UD/jarvis-intake.service.d/jarvis-sync.conf")" -eq 2 ]
  grep -qx 'TimeoutStartSec=105min' "$UD/jarvis-intake.service.d/jarvis-sync.conf"
  grep -qx 'TimeoutStartSec=45min' "$UD/jarvis-brief.service.d/jarvis-sync.conf"
  grep -qx 'TimeoutStartSec=35min' "$UD/jarvis-debrief.service.d/jarvis-sync.conf"
  run "$IU"
  grep -qx 'unchanged jarvis-brief.service.d/jarvis-sync.conf' <<< "$output"
}

@test "a standalone machine gets no sync units or drop-ins" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ ! -e "$UD/jarvis-sync.timer" ]
  run ls -d "$UD"/*.service.d
  [ "$status" -ne 0 ]
}

@test "leaving the server role removes the sync units and the owned drop-ins, never a foreign one" {
  set_role server
  run "$IU"
  printf '[Service]\nNice=5\n' > "$UD/jarvis-brief.service.d/local.conf"
  set_role standalone
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed jarvis-sync.timer' <<< "$output"
  grep -qx 'removed jarvis-intake.service.d/jarvis-sync.conf' <<< "$output"
  [ ! -e "$UD/jarvis-sync.service" ]
  [ ! -e "$UD/jarvis-intake.service.d" ]
  [ ! -e "$UD/jarvis-brief.service.d/jarvis-sync.conf" ]
  [ -f "$UD/jarvis-brief.service.d/local.conf" ]
}

@test "--uninstall removes the owned drop-ins too" {
  set_role server
  run "$IU"
  run "$IU" --uninstall
  [ "$status" -eq 0 ]
  grep -qx 'removed jarvis-debrief.service.d/jarvis-sync.conf' <<< "$output"
  run ls -A "$UD"
  [ -z "$output" ]
}
