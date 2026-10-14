# shellcheck shell=bash
# Git remote helpers (spec §6.11).

# git@host:path ≡ ssh://git@host/path ≡ https://host/path: host lowercased; user, port, trailing "/"
# and ".git" dropped. Local paths and file:// URLs get only the trailing "/" and ".git" rules.
git_url_normalize() {
  local u="${1-}" host path
  while [[ "$u" == */ ]]; do u="${u%/}"; done
  u="${u%.git}"
  while [[ "$u" == */ ]]; do u="${u%/}"; done
  if [[ "$u" == file://* ]]; then
    printf '%s\n' "${u#file://}"
    return
  elif [[ "$u" =~ ^[A-Za-z][A-Za-z0-9+.-]*://([^/]*)(/.*)?$ ]]; then
    host="${BASH_REMATCH[1]##*@}"; host="${host%%:*}"; path="${BASH_REMATCH[2]#/}"
  elif [[ "$u" =~ ^([^/:]+):(.+)$ ]]; then
    host="${BASH_REMATCH[1]##*@}"; path="${BASH_REMATCH[2]#/}"
  else
    printf '%s\n' "$u"
    return
  fi
  printf '%s/%s\n' "${host,,}" "$path"
}

git_url_same() { [[ -n "${1-}" && -n "${2-}" && "$(git_url_normalize "$1")" == "$(git_url_normalize "$2")" ]]; }

# The sync's commit step (two-machines spec §4.1, §5.1), shared by vault_sync.sh and the unattended update.
# Every git child runs with run.lock's fd 9 closed: a daemon or a detached gc it starts must not keep the lock.

# git_sync_message <role>: the scripted message for the staged changes (§4.1).
git_sync_message() {
  local role="$1" a r p st n=0 body=""
  local -A num=()
  while IFS=$'\t' read -r -d '' a r p; do
    if [[ "$a" == - ]]; then num[$p]="(binary)"; else num[$p]="+$a/-$r"; fi
  done < <(command git diff --cached --numstat -z --no-renames 9>&-)
  while IFS= read -r -d '' st && IFS= read -r -d '' p; do
    n=$(( n + 1 ))
    case "$st" in
      A) body+="${p//[$'\n\r\t']/ } (new)"$'\n' ;;
      D) body+="${p//[$'\n\r\t']/ } (deleted)"$'\n' ;;
      *) body+="${p//[$'\n\r\t']/ } ${num[$p]:-}"$'\n' ;;
    esac
  done < <(command git diff --cached --name-status -z --no-renames 9>&-)
  printf 'sync(%s): %d file(s)\n\n%s\nFoundry-Command: sync\nFoundry-Role: %s\n' "$role" "$n" "$body" "$role"
}

# git_sync_commit <role>: commit_runs.py, then every remaining change as one sync(<role>) commit through the
# pre-commit hook. Returns 0 (nothing staged included); on a refusal unstages, sets GIT_SYNC_ERROR, returns 1.
# Runs from the vault root.
git_sync_commit() {
  local role="$1" err
  GIT_SYNC_ERROR=""
  if ! system/scripts/commit_runs.py > /dev/null 9>&-; then
    GIT_SYNC_ERROR="commit_runs.py could not commit a run (see its alert)"
    return 1
  fi
  if ! command git add -A 9>&-; then
    GIT_SYNC_ERROR="git add -A failed"
    return 1
  fi
  if ! command git diff --cached --quiet 9>&-; then
    if ! err="$(git_sync_message "$role" | command git commit -q -F - 2>&1 9>&-)"; then
      command git reset -q 9>&-
      GIT_SYNC_ERROR="the sync commit was refused: $(head -n 1 <<< "$err")"
      return 1
    fi
  fi
  return 0
}
