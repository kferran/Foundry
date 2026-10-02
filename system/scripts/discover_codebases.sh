#!/bin/bash
# Find git repos under a directory; one JSON object per repo (spec §6.13).
set -euo pipefail

(( $# == 1 )) || { echo "usage: discover_codebases.sh <dir>" >&2; exit 2; }
root="$(realpath -e -- "$1" 2>/dev/null)" || root=""
[[ -n "$root" && -d "$root" ]] || { echo "discover_codebases: not a directory: $1" >&2; exit 2; }

json_list() { if (( $# )); then printf '%s\n' "$@" | jq -R . | jq -cs .; else echo '[]'; fi; }

# One object for the repo owning worktree $1. path = the main worktree; for a bare repo, the worktree
# on the repo's HEAD branch, else the first by name. worktrees = every existing non-bare worktree, sorted.
emit() {
  local line wt="" br="" first=1 main="" onhead="" common head path remote
  local -a wts=() sorted=()
  common="$(git -C "$1" rev-parse --path-format=absolute --git-common-dir)"
  head="$(git --git-dir="$common" symbolic-ref -q HEAD 2>/dev/null || true)"
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) wt="${line#worktree }" ;;
      "branch "*) br="${line#branch }" ;;
      bare) wt="" ;;
      "")
        if [[ -n "$wt" && -d "$wt" ]]; then
          wt="$(realpath -- "$wt")"
          (( first )) && main="$wt"
          [[ -n "$onhead" || "$br" != "$head" ]] || onhead="$wt"
          wts+=("$wt")
        fi
        first=0 wt="" br="" ;;
    esac
  done < <(git -C "$1" worktree list --porcelain; echo)
  (( ${#wts[@]} )) || return 0
  mapfile -t sorted < <(printf '%s\n' "${wts[@]}" | LC_ALL=C sort -u)
  path="${main:-${onhead:-${sorted[0]}}}"
  remote="$(git -C "$path" remote get-url origin 2>/dev/null || true)"
  jq -cn --arg path "$path" --argjson wts "$(json_list "${sorted[@]}")" --arg remote "$remote" \
    '{path: $path, worktrees: $wts, remote: (if $remote == "" then null else $remote end)}'
}

top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$top" && "$(realpath -- "$top")" == "$root" ]]; then
  emit "$root"
  exit 0
fi

declare -A seen=()
while IFS= read -r -d '' dotgit; do
  repo="${dotgit%/.git}"
  common="$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || continue
  common="$(realpath -- "$common")"
  [[ -z "${seen[$common]:-}" ]] || continue
  seen[$common]=1
  emit "$repo"
done < <(find "$root" -maxdepth 3 \( -name node_modules -o -name vendor -o -name .venv -o -name bin \
           -o -name obj -o -name dist -o -name target \) -prune -o -name .git -print0 | LC_ALL=C sort -z)
