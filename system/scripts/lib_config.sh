# shellcheck shell=bash
# Config and codebase helpers (spec §6.1). Source after VAULT_ROOT is set; all parsing via vault_index.py.

_vi() { (cd "$VAULT_ROOT" && system/scripts/vault_index.py "$@"); }

_expand_home() {
  local v="${1-}"
  if [[ "$v" == "~" || "$v" == "~/"* ]]; then v="$HOME${v:1}"; fi
  printf '%s\n' "$v"
}

config_get() {
  local v
  if v="$(_vi field system/config.md "$1" 2>/dev/null)" && [[ -n "$v" ]]; then
    _expand_home "$v"
  else
    printf '%s\n' "${2-}"
  fi
}

config_set() { _vi set system/config.md "$1" "$2"; }

codebases_list() {
  local f name
  for f in "$VAULT_ROOT"/system/codebases/*.md; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f" .md)"
    [[ "$name" == example ]] && continue
    printf '%s\n' "$name"
  done
}

codebase_get() {
  local name="$1" key="$2" v
  [[ "$name" =~ ^[A-Za-z0-9._-]+$ && "$name" != .* ]] || return 2
  if v="$(_vi field "system/codebases/$name.md" "$key" 2>/dev/null)" && [[ -n "$v" ]]; then
    _expand_home "$v"
  else
    printf '%s\n' "${3-}"
  fi
}

codebase_default() {
  local names=() n
  mapfile -t names < <(codebases_list)
  if (( ${#names[@]} == 1 )); then printf '%s\n' "${names[0]}"; return 0; fi
  for n in "${names[@]}"; do
    if [[ "$(codebase_get "$n" default false)" == "true" ]]; then printf '%s\n' "$n"; return 0; fi
  done
  return 1
}

config_validate() {
  local files=(system/config.md) f
  for f in "$VAULT_ROOT"/system/codebases/*.md; do [[ -f "$f" ]] && files+=("system/codebases/$(basename "$f")"); done
  _vi validate "${files[@]}"
}
