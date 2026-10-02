#!/bin/bash
# The single dependency list (spec §6.2): one "ok|missing|optional <item> [hint]" line per item.
# Exit 0 always; --strict exits 1 if a required item is missing. Optional items never fail --strict.
set -euo pipefail

strict=0
case "${1:-}" in
  "") ;;
  --strict) strict=1 ;;
  *) echo "usage: check_deps.sh [--strict]" >&2; exit 2 ;;
esac

declare -A HINT=(
  [claude]="install Claude Code: https://docs.claude.com/en/docs/claude-code/setup"
  [git]="sudo pacman -S git"
  [jq]="sudo pacman -S jq"
  [bats]="sudo pacman -S bash-bats"
  [gcalcli]="pipx install gcalcli"
  [systemctl]="systemd is required (user services)"
  [hyprctl]="sudo pacman -S hyprland"
  [python3]="sudo pacman -S python"
  [flock]="sudo pacman -S util-linux"
  [timeout]="sudo pacman -S coreutils"
  [pyyaml]="sudo pacman -S python-yaml"
  [pytest]="sudo pacman -S python-pytest"
  [fts5]="python's sqlite3 lacks FTS5: sudo pacman -S sqlite python"
  [systemd-analyze]="systemd is required (unit verification)"
  [herdr]="optional session backend for sub-project 2; see README"
  [tmux]="optional session backend for sub-project 2: sudo pacman -S tmux"
)
missing=0
report() {  # <item> <present 0|1> [optional]
  if (( $2 )); then
    echo "ok $1"
  elif [[ "${3:-}" == optional ]]; then
    echo "optional $1 ${HINT[$1]}"
  else
    echo "missing $1 ${HINT[$1]}"
    missing=1
  fi
}
has() { command -v "$1" >/dev/null 2>&1 && echo 1 || echo 0; }
py() { command -v python3 >/dev/null 2>&1 && python3 "$@" >/dev/null 2>&1 && echo 1 || echo 0; }

for c in claude git jq bats gcalcli systemctl hyprctl python3 flock timeout; do report "$c" "$(has "$c")"; done
report pyyaml "$(py -c 'import yaml')"
report pytest "$(py -m pytest --version)"
report fts5 "$(py -c 'import sqlite3; sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")')"
report systemd-analyze "$(has systemd-analyze)"
for c in herdr tmux; do report "$c" "$(has "$c")" optional; done

(( strict && missing )) && exit 1
exit 0
