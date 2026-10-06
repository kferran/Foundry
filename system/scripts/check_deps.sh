#!/bin/bash
# The single dependency list (spec §6.2): one "ok|missing|optional <item> [hint]" line per item.
# Which items are required depends on the machine role (two-machine spec §3.4). Exit 0 always;
# --strict exits 1 if a required item is missing. Optional items never fail --strict.
set -euo pipefail
# No dirname: this script must run with a PATH that lacks coreutils.
src="${BASH_SOURCE[0]}"
[[ "$src" == */* ]] || src="./$src"
VAULT_ROOT="$(cd "${src%/*}/../.." && pwd -P)"

usage() { echo "usage: check_deps.sh [--strict] [--role standalone|server|client]" >&2; exit 2; }
strict=0 role=""
while (( $# )); do
  case "$1" in
    --strict) strict=1; shift ;;
    --role) (( $# >= 2 )) || usage; role="$2"; shift 2 ;;
    *) usage ;;
  esac
done
if [[ -z "$role" ]]; then
  role="$(cd "$VAULT_ROOT" && system/scripts/vault_index.py field system/config.md machine_role 2>/dev/null || true)"
  role="${role:-standalone}"
fi
case "$role" in
  standalone) REQUIRED=(claude git jq bats systemctl hyprctl python3 flock timeout pyyaml pytest fts5 systemd-analyze) ;;
  server) REQUIRED=(claude git jq bats systemctl python3 flock timeout pyyaml pytest fts5 systemd-analyze) ;;
  client) REQUIRED=(claude git jq python3 pyyaml fts5) ;;
  *) usage ;;
esac

has() { command -v "$1" >/dev/null 2>&1 && echo 1 || echo 0; }
py() { command -v python3 >/dev/null 2>&1 && python3 "$@" >/dev/null 2>&1 && echo 1 || echo 0; }

if (( $(has pacman) )); then pm=pacman; elif (( $(has apt-get) )); then pm=apt; else pm=other; fi
# hint <item>: the install hint for this package manager.
hint() {
  local pkg_pacman pkg_apt
  case "$1" in
    claude) echo "install Claude Code: https://docs.claude.com/en/docs/claude-code/setup"; return ;;
    systemctl) echo "systemd is required (user services)"; return ;;
    systemd-analyze) echo "systemd is required (unit verification)"; return ;;
    herdr) echo "optional session backend for sub-project 2; see README"; return ;;
    fts5) pkg_pacman="sqlite python" pkg_apt="libsqlite3-0 python3"; printf "python's sqlite3 lacks FTS5: " ;;
    git|jq|tmux) pkg_pacman="$1" pkg_apt="$1" ;;
    bats) pkg_pacman=bash-bats pkg_apt=bats ;;
    bwrap) pkg_pacman=bubblewrap pkg_apt=bubblewrap ;;
    gh) pkg_pacman=github-cli pkg_apt=gh ;;
    hyprctl) pkg_pacman=hyprland pkg_apt=hyprland ;;
    python3) pkg_pacman=python pkg_apt=python3 ;;
    flock) pkg_pacman=util-linux pkg_apt=util-linux ;;
    timeout) pkg_pacman=coreutils pkg_apt=coreutils ;;
    pyyaml) pkg_pacman=python-yaml pkg_apt=python3-yaml ;;
    pytest) pkg_pacman=python-pytest pkg_apt=python3-pytest ;;
    az) pkg_pacman=azure-cli pkg_apt=azure-cli ;;
  esac
  case "$pm" in
    pacman) echo "sudo pacman -S $pkg_pacman" ;;
    apt) echo "sudo apt install $pkg_apt" ;;
    *) echo "install $1" ;;
  esac
}

missing=0
report() {  # <item> <present 0|1> [optional]
  if (( $2 )); then
    echo "ok $1"
  elif [[ "${3:-}" == optional ]]; then
    echo "optional $1 $(hint "$1")"
  else
    echo "missing $1 $(hint "$1")"
    missing=1
  fi
}
present() {  # <item>: 1 when the item is available
  case "$1" in
    pyyaml) py -c 'import yaml' ;;
    pytest) py -m pytest --version ;;
    fts5) py -c 'import sqlite3; sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")' ;;
    *) has "$1" ;;
  esac
}

for item in "${REQUIRED[@]}"; do report "$item" "$(present "$item")"; done
for c in herdr tmux; do report "$c" "$(has "$c")" optional; done
if [[ "$role" != client ]]; then report az "$(has az)" optional; fi
if [[ "$role" != client ]]; then report bwrap "$(has bwrap)" optional; report gh "$(has gh)" optional; fi

(( strict && missing )) && exit 1
exit 0
