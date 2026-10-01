# shellcheck shell=bash
# Shared argument validators (spec §6). Source after VAULT_ROOT is set (physical path) and cd "$VAULT_ROOT".

args_date() {
  [[ "${1-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || return 1
  [[ "$(date -d "$1" +%F 2>/dev/null)" == "$1" ]]
}

args_vault_path() {
  local abs
  abs="$(realpath -e -- "${1-}" 2>/dev/null)" || return 1
  [[ -f "$abs" ]] || return 1
  case "$abs" in
    "$VAULT_ROOT"/*) printf '%s\n' "${abs#"$VAULT_ROOT"/}" ;;
    *) return 1 ;;
  esac
}

args_raw_filename() {
  (
    LC_ALL=C
    [[ "${1-}" =~ ^[A-Za-z0-9._\ \-]+$ && "${1-}" != .* ]]
  )
}

args_sanitize_filename() {
  local s
  s="$(printf '%s' "${1-}" | LC_ALL=C sed 's/[^A-Za-z0-9._ -]/_/g')"
  while [[ "$s" == .* ]]; do s="${s#.}"; done
  printf '%s\n' "${s:-file}"
}
