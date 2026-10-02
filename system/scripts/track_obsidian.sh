#!/bin/bash
# Sample the focused Obsidian note every 30 s into system/logs/obsidian_focus_<date>.log (spec §6.7).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh
TZ="$(config_get timezone UTC)"
export TZ
LOG_DIR="$VAULT_ROOT/system/logs"
mkdir -p "$LOG_DIR"

# Sets WIN to the active window's JSON object. Runs in the main shell (never in $(…)) so a recovered
# signature persists: a stale HYPRLAND_INSTANCE_SIGNATURE (it changes every login) is replaced by the
# newest instance under $XDG_RUNTIME_DIR/hypr/ and the call is retried once.
hypr_query() {
  WIN="$(hyprctl activewindow -j 2>/dev/null)" || return 1
  jq -e 'type == "object"' >/dev/null 2>&1 <<< "$WIN"
}
active_window() {
  local newest
  WIN=""
  hypr_query && return 0
  newest="$(ls -1td -- "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"/hypr/*/ 2>/dev/null | head -n 1)" || true
  [[ -n "$newest" ]] || return 1
  newest="${newest%/}"
  export HYPRLAND_INSTANCE_SIGNATURE="${newest##*/}"
  hypr_query
}

while true; do
  title=""
  if active_window; then
    title="$(jq -r '.title // empty' <<< "$WIN" 2>/dev/null)" || title=""
  fi
  # "Note Name - Vault Name - Obsidian v1.x.x": drop the last two " - " fields, so a note
  # whose own name contains " - " is kept whole.
  if [[ "$title" == *" - Obsidian"* && "$title" == *" - "*" - "* ]]; then
    note="${title% - *}"
    note="${note% - *}"
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$note" >> "$LOG_DIR/obsidian_focus_$(date +%F).log"
  fi
  sleep 30
done
