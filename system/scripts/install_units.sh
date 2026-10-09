#!/bin/bash
# Render, verify, install and enable the systemd user units (spec §6.10).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh

SYSTEMCTL="${SYSTEMCTL:-systemctl}"
UNIT_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
HEADER_PREFIX="# Managed by vault: "
HEADER="$HEADER_PREFIX$VAULT_ROOT"

die() { echo "install_units: $2" >&2; exit "$1"; }
usage() { die 2 "usage: install_units.sh [--dry-run | --uninstall | --update]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  --update) mode=update ;;
  *) usage ;;
esac

shopt -s nullglob

# owned_units / owned_dropins: the unit files and drop-ins (<unit>.d/<name>.conf) in UNIT_DIR whose
# header names this vault.
owned_units() {
  local f
  for f in "$UNIT_DIR"/*.service "$UNIT_DIR"/*.timer; do
    if [[ "$(head -n 1 -- "$f")" == "$HEADER" ]]; then printf '%s\n' "${f##*/}"; fi
  done
}
owned_dropins() {
  local f
  for f in "$UNIT_DIR"/*.service.d/*.conf; do
    if [[ "$(head -n 1 -- "$f")" == "$HEADER" ]]; then printf '%s\n' "${f#"$UNIT_DIR"/}"; fi
  done
}

# remove_units <name…>: disable, delete and report units this vault owns.
remove_units() {
  (( $# )) || return 0
  "$SYSTEMCTL" --user disable --now "$@" || echo "install_units: warning: systemctl disable failed" >&2
  local n
  for n in "$@"; do
    rm -f -- "$UNIT_DIR/$n"
    echo "removed $n"
  done
}

# remove_dropins <unit.d/name.conf…>: delete and report owned drop-ins, and their directories once empty.
remove_dropins() {
  local n
  for n in "$@"; do
    rm -f -- "$UNIT_DIR/$n"
    rmdir -- "$UNIT_DIR/${n%/*}" 2>/dev/null || true
    echo "removed $n"
  done
}

if [[ "$mode" == uninstall ]]; then
  mapfile -t owned < <(owned_units)
  mapfile -t dropins < <(owned_dropins)
  if (( ${#owned[@]} + ${#dropins[@]} == 0 )); then
    echo "no units managed by $VAULT_ROOT"
    exit 0
  fi
  remove_units "${owned[@]}"
  remove_dropins "${dropins[@]}"
  "$SYSTEMCTL" --user daemon-reload
  exit 0
fi


# The units each machine role runs (two-machine spec §3.3), and the ones it enables.
role="$(config_get machine_role standalone)"
case "$role" in
  standalone)
    UNITS=(foundry-intake.service foundry-intake.timer foundry-brief.service foundry-brief.timer
           foundry-debrief.service foundry-debrief.timer foundry-focus.service)
    ENABLE=(foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service) ;;
  server)
    UNITS=(foundry-intake.service foundry-intake.timer foundry-brief.service foundry-brief.timer
           foundry-debrief.service foundry-debrief.timer foundry-sync.service foundry-sync.timer)
    ENABLE=(foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-sync.timer) ;;
  client) UNITS=() ENABLE=() ;;
  *) die 1 "unknown machine_role in system/config.md: $role" ;;
esac
# The meetings fetch (meetings spec §4) writes only gitignored files, so it gets no sync drop-in.
if [[ "$role" != client && "$(config_get meetings_enabled false)" == true ]]; then
  UNITS+=(foundry-meetings.service foundry-meetings.timer)
  ENABLE+=(foundry-meetings.timer)
fi
# Error telemetry (Plan 11): standalone and server, only when a source is enabled.
if [[ "$role" != client ]] && [[ -n "$(system/scripts/telemetry_fetch.py --list 2>/dev/null)" ]]; then
  UNITS+=(foundry-telemetry.service foundry-telemetry.timer)
  ENABLE+=(foundry-telemetry.timer)
fi
# Nightshift: standalone and server (Nightshift spec §2).
if [[ "$role" != client ]]; then
  UNITS+=(foundry-nightshift.service foundry-nightshift.timer)
  ENABLE+=(foundry-nightshift.timer)
fi
# Template update: standalone and server, every morning (#87); a client gets updates through sync.
if [[ "$role" != client ]]; then
  UNITS+=(foundry-update.service foundry-update.timer)
  ENABLE+=(foundry-update.timer)
fi
# DTCC watcher: standalone and server, only when the vault has a map (DTCC watcher spec §7).
if [[ "$role" != client ]] && [[ -f system/dtcc/map.yaml ]]; then
  UNITS+=(foundry-dtcc-watch.service foundry-dtcc-watch.timer)
  ENABLE+=(foundry-dtcc-watch.timer)
fi
# A server syncs around every run (two-machine spec §5.2): one drop-in per run service, with the
# service's own prep step and a timeout raised by two sync deadlines plus margin.
DROPINS=()
[[ "$role" != server ]] || DROPINS=(foundry-intake.service.d/foundry-sync.conf foundry-brief.service.d/foundry-sync.conf
                                    foundry-debrief.service.d/foundry-sync.conf foundry-update.service.d/foundry-sync.conf)
declare -A DROPIN_TIMEOUT=([foundry-intake]=105min [foundry-brief]=60min [foundry-debrief]=60min [foundry-update]=35min)
declare -A DROPIN_PREP=([foundry-intake]="" [foundry-brief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/brief_prep.sh"'
                        [foundry-debrief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"' [foundry-update]="")
# --update (update_template.sh) re-renders only what this vault installed: a unit a new template adds is
# reported, never installed or enabled, so /setup's ask-before-installing holds (#35). Drop-ins follow their
# service.
if [[ "$mode" == update ]]; then
  mapfile -t have < <(owned_units)
  keep=() keep_enable=() keep_dropins=()
  for n in "${UNITS[@]}"; do
    if [[ " ${have[*]} " == *" $n "* ]]; then keep+=("$n"); else echo "new unit available: $n (install it with system/scripts/install_units.sh)"; fi
  done
  # Only what is enabled now stays enabled: a timer the owner disabled stays off across updates (#87).
  for n in "${ENABLE[@]}"; do
    [[ " ${keep[*]} " != *" $n "* ]] || ! "$SYSTEMCTL" --user is-enabled --quiet "$n" || keep_enable+=("$n")
  done
  for d in "${DROPINS[@]}"; do [[ " ${keep[*]} " != *" ${d%%.d/*} "* ]] || keep_dropins+=("$d"); done
  UNITS=("${keep[@]}") ENABLE=("${keep_enable[@]}") DROPINS=("${keep_dropins[@]}")
fi

if [[ "$role" == client ]]; then
  echo "install_units: machine_role client: no units"
  if [[ "$mode" == install ]]; then
    mapfile -t stale < <(owned_units)
    mapfile -t stale_dropins < <(owned_dropins)
    if (( ${#stale[@]} + ${#stale_dropins[@]} )); then
      remove_units "${stale[@]}"
      remove_dropins "${stale_dropins[@]}"
      "$SYSTEMCTL" --user daemon-reload
    fi
  fi
  exit 0
fi

# Unit files split ExecStart on whitespace and expand % specifiers, so paths are quoted in the
# templates and restricted to characters that survive both.
SAFE='^/[A-Za-z0-9._/@+ -]+$'
[[ "$VAULT_ROOT" =~ $SAFE ]] \
  || die 1 "the vault path contains characters a unit file cannot carry (allowed: letters, digits, space and . _ / @ + -): $VAULT_ROOT"
claude_bin="$(command -v claude || true)"  # deliberately not symlink-resolved: version-manager shims dispatch on their own path
[[ "$claude_bin" == /* ]] || die 1 "claude is not on PATH"
[[ "$claude_bin" =~ $SAFE ]] || die 1 "the claude path contains characters a unit file cannot carry: $claude_bin"
if ! out="$(config_validate 2>&1)"; then
  printf '%s\n' "$out" >&2
  die 1 "system/config.md or a codebase file is invalid; fix it and re-run"
fi
tz="$(config_get timezone)" brief="$(config_get brief_time)" debrief="$(config_get debrief_time)"
IFS=: read -r bh bm <<< "$brief"
t=$(( (10#$bh * 60 + 10#$bm + 1410) % 1440 ))
dtcc_time="$(printf '%02d:%02d' $(( t / 60 )) $(( t % 60 )))"
sync_interval="$(config_get sync_interval_minutes 5)"
unit_path="$(dirname "$claude_bin"):%h/.local/bin:/usr/local/bin:/usr/bin:/bin"

esc() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
templates=()
for n in "${UNITS[@]}"; do
  [[ -f "system/systemd/$n.in" ]] || die 1 "missing unit template system/systemd/$n.in"
  templates+=("system/systemd/$n.in")
done
# render <template> <output> [sed args…]: header plus the template with every placeholder replaced.
render() {
  local t="$1" out="$2"
  shift 2
  mkdir -p -- "$(dirname -- "$out")"
  {
    printf '%s\n' "$HEADER"
    sed "$@" -e "s|{{VAULT_ROOT}}|$(esc "$VAULT_ROOT")|g" -e "s|{{TZ}}|$(esc "$tz")|g" \
        -e "s|{{BRIEF_TIME}}|$(esc "$brief")|g" -e "s|{{DTCC_TIME}}|$(esc "$dtcc_time")|g" -e "s|{{DEBRIEF_TIME}}|$(esc "$debrief")|g" \
        -e "s|{{SYNC_INTERVAL}}|$(esc "$sync_interval")|g" \
        -e "s|{{CLAUDE_BIN}}|$(esc "$claude_bin")|g" -e "s|{{UNIT_PATH}}|$(esc "$unit_path")|g" "$t"
  } > "$out"
  if grep -q '{{' "$out"; then
    die 1 "$t: unreplaced placeholder $(grep -o '{{[^}]*}*' "$out" | head -n 1)"
  fi
}
for t in "${templates[@]}"; do
  render "$t" "$work/$(basename "$t" .in)"
done
for d in "${DROPINS[@]}"; do
  svc="${d%.service.d/*}"
  render system/systemd/dropins/foundry-sync.conf.in "$work/$d" \
    -e "s|{{PREP_LINE}}|$(esc "${DROPIN_PREP[$svc]}")|" -e "s|{{TIMEOUT}}|${DROPIN_TIMEOUT[$svc]}|"
done
# Each unit is verified with its drop-ins beside it, as systemd will load them.
rendered=("$work"/*.service "$work"/*.timer)
out=""
if (( ${#rendered[@]} )) && ! out="$(systemd-analyze --user verify "${rendered[@]}" 2>&1)"; then
  printf '%s\n' "$out" >&2
  die 1 "systemd-analyze --user verify rejected the rendered units"
fi
[[ -z "$out" ]] || printf '%s\n' "$out" >&2
files=("${rendered[@]##*/}" "${DROPINS[@]}")

if [[ "$mode" == dry ]]; then
  for n in "${files[@]}"; do
    printf '===== %s\n' "$n"
    cat -- "$work/$n"
  done
  exit 0
fi

# Never overwrite a unit this vault does not own: a foreign unit, or one owned by another vault that
# still exists. A unit whose owning vault is gone was left by a move and is re-pointed here.
for n in "${files[@]}"; do
  dst="$UNIT_DIR/$n"
  [[ -e "$dst" ]] || continue
  first="$(head -n 1 -- "$dst")"
  [[ "$first" == "$HEADER" ]] && continue
  if [[ "$first" != "$HEADER_PREFIX"* ]]; then
    die 1 "$dst exists and is not managed by a vault; move it aside and re-run"
  fi
  other="${first#"$HEADER_PREFIX"}"
  if [[ -d "$other/system/scripts" ]]; then
    die 1 "$dst belongs to the vault at $other; run its install_units.sh --uninstall first"
  fi
done

for n in "${files[@]}"; do
  u="$work/$n" dst="$UNIT_DIR/$n"
  mkdir -p -- "$(dirname -- "$dst")"
  if [[ -f "$dst" ]] && cmp -s -- "$u" "$dst"; then
    echo "unchanged $n"
    continue
  fi
  if [[ -e "$dst" ]]; then status=changed; else status=new; fi
  cp -- "$u" "$dst.tmp"
  mv -f -- "$dst.tmp" "$dst"
  echo "$status $n"
done
# A role change leaves owned units and drop-ins the new role does not use: remove them.
stale=() stale_dropins=()
while IFS= read -r n; do
  [[ " ${UNITS[*]} " == *" $n "* ]] || stale+=("$n")
done < <(owned_units)
while IFS= read -r n; do
  [[ " ${DROPINS[*]} " == *" $n "* ]] || stale_dropins+=("$n")
done < <(owned_dropins)
remove_units "${stale[@]}"
remove_dropins "${stale_dropins[@]}"
"$SYSTEMCTL" --user daemon-reload
(( ${#ENABLE[@]} == 0 )) || "$SYSTEMCTL" --user enable --now "${ENABLE[@]}"
