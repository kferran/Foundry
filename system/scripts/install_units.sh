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
usage() { die 2 "usage: install_units.sh [--dry-run | --uninstall]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  *) usage ;;
esac

shopt -s nullglob

if [[ "$mode" == uninstall ]]; then
  owned=()
  for f in "$UNIT_DIR"/*.service "$UNIT_DIR"/*.timer; do
    if [[ "$(head -n 1 -- "$f")" == "$HEADER" ]]; then owned+=("${f##*/}"); fi
  done
  if (( ${#owned[@]} == 0 )); then
    echo "no units managed by $VAULT_ROOT"
    exit 0
  fi
  "$SYSTEMCTL" --user disable --now "${owned[@]}" || echo "install_units: warning: systemctl disable failed" >&2
  for n in "${owned[@]}"; do
    rm -f -- "$UNIT_DIR/$n"
    echo "removed $n"
  done
  "$SYSTEMCTL" --user daemon-reload
  exit 0
fi


# The units each machine role runs (two-machine spec §3.3), and the ones it enables.
role="$(config_get machine_role standalone)"
case "$role" in
  standalone)
    UNITS=(jarvis-intake.service jarvis-intake.timer jarvis-brief.service jarvis-brief.timer
           jarvis-debrief.service jarvis-debrief.timer jarvis-focus.service)
    ENABLE=(jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer jarvis-focus.service) ;;
  server)
    UNITS=(jarvis-intake.service jarvis-intake.timer jarvis-brief.service jarvis-brief.timer
           jarvis-debrief.service jarvis-debrief.timer)
    ENABLE=(jarvis-intake.timer jarvis-brief.timer jarvis-debrief.timer) ;;
  client) UNITS=() ENABLE=() ;;
  *) die 1 "unknown machine_role in system/config.md: $role" ;;
esac

# owned_units: the unit files in UNIT_DIR whose header names this vault.
owned_units() {
  local f
  for f in "$UNIT_DIR"/*.service "$UNIT_DIR"/*.timer; do
    if [[ "$(head -n 1 -- "$f")" == "$HEADER" ]]; then printf '%s\n' "${f##*/}"; fi
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

if [[ "$role" == client ]]; then
  echo "install_units: machine_role client: no units"
  if [[ "$mode" == install ]]; then
    mapfile -t stale < <(owned_units)
    if (( ${#stale[@]} )); then
      remove_units "${stale[@]}"
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
unit_path="$(dirname "$claude_bin"):%h/.local/bin:/usr/local/bin:/usr/bin:/bin"

esc() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
templates=()
for n in "${UNITS[@]}"; do
  [[ -f "system/systemd/$n.in" ]] || die 1 "missing unit template system/systemd/$n.in"
  templates+=("system/systemd/$n.in")
done
for t in "${templates[@]}"; do
  name="$(basename "$t" .in)"
  {
    printf '%s\n' "$HEADER"
    sed -e "s|{{VAULT_ROOT}}|$(esc "$VAULT_ROOT")|g" -e "s|{{TZ}}|$(esc "$tz")|g" \
        -e "s|{{BRIEF_TIME}}|$(esc "$brief")|g" -e "s|{{DEBRIEF_TIME}}|$(esc "$debrief")|g" \
        -e "s|{{CLAUDE_BIN}}|$(esc "$claude_bin")|g" -e "s|{{UNIT_PATH}}|$(esc "$unit_path")|g" "$t"
  } > "$work/$name"
  if grep -q '{{' "$work/$name"; then
    die 1 "$t: unreplaced placeholder $(grep -o '{{[^}]*}*' "$work/$name" | head -n 1)"
  fi
done
rendered=("$work"/*)
if ! out="$(systemd-analyze --user verify "${rendered[@]}" 2>&1)"; then
  printf '%s\n' "$out" >&2
  die 1 "systemd-analyze --user verify rejected the rendered units"
fi
[[ -z "$out" ]] || printf '%s\n' "$out" >&2

if [[ "$mode" == dry ]]; then
  for u in "${rendered[@]}"; do
    printf '===== %s\n' "${u##*/}"
    cat -- "$u"
  done
  exit 0
fi

# Never overwrite a unit this vault does not own: a foreign unit, or one owned by another vault that
# still exists. A unit whose owning vault is gone was left by a move and is re-pointed here.
for u in "${rendered[@]}"; do
  dst="$UNIT_DIR/${u##*/}"
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

mkdir -p -- "$UNIT_DIR"
for u in "${rendered[@]}"; do
  n="${u##*/}" dst="$UNIT_DIR/${u##*/}"
  if [[ -f "$dst" ]] && cmp -s -- "$u" "$dst"; then
    echo "unchanged $n"
    continue
  fi
  if [[ -e "$dst" ]]; then status=changed; else status=new; fi
  cp -- "$u" "$dst.tmp"
  mv -f -- "$dst.tmp" "$dst"
  echo "$status $n"
done
# A role change leaves owned units the new role does not use: remove them.
stale=()
while IFS= read -r n; do
  [[ " ${UNITS[*]} " == *" $n "* ]] || stale+=("$n")
done < <(owned_units)
remove_units "${stale[@]}"
"$SYSTEMCTL" --user daemon-reload
"$SYSTEMCTL" --user enable --now "${ENABLE[@]}"
