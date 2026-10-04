#!/bin/bash
# Sync the vault with its private origin: commit, fetch, merge, push (two-machine spec §5.1).
# Usage: vault_sync.sh [--pre | --post]. Exit 0 synced or nothing to do; 1 failure (alerted); 2 usage;
# 3 blocked; 4 run.lock busy. --pre exits 3 when blocked and 0 otherwise; --post always exits 0.
set -uo pipefail  # no -e: every step's failure is handled where it happens
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh
# shellcheck source=lib_git.sh
source system/scripts/lib_git.sh

mode=default
(( $# <= 1 )) || { echo "usage: vault_sync.sh [--pre | --post]" >&2; exit 2; }
case "${1:-}" in
  "") ;;
  --pre) mode=pre ;;
  --post) mode=post ;;
  *) echo "usage: vault_sync.sh [--pre | --post]" >&2; exit 2 ;;
esac

export GIT_TERMINAL_PROMPT=0
[[ -n "${GIT_SSH_COMMAND:-}" ]] || export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15"
TZ="$(config_get timezone UTC)"
export TZ
role="$(config_get machine_role standalone)"
LOGS=system/logs BLOCKED=system/logs/sync-blocked STATE=system/logs/sync-state.json
DEADLINE=$(( $(date +%s) + ${SYNC_DEADLINE:-300} ))
mkdir -p "$LOGS"

alert() { printf -- '- %s [sync] %s\n' "$(date +%H:%M:%S)" "$1" >> "$LOGS/alerts_$(date +%F).md"; }

# finish <code>: exit, mapped by mode (§5.1 Modes).
finish() {
  local rc="$1"
  if [[ "$mode" == pre ]] && (( rc != 3 )); then rc=0; fi
  [[ "$mode" != post ]] || rc=0
  exit "$rc"
}

# fail <kind> <reason>: alert once a day per failure kind while it persists (§5.3), then exit 1.
fail() {
  local first="" last=""
  if [[ -f "$STATE" ]]; then
    first="$(jq -r --arg k "$1" 'select(.kind == $k) | .first_seen // empty' "$STATE" 2>/dev/null)"
    last="$(jq -r --arg k "$1" 'select(.kind == $k) | .last_alerted // empty' "$STATE" 2>/dev/null)"
  fi
  [[ "$last" == "$(date +%F)" ]] || alert "sync failed ($1): $2"
  jq -cn --arg k "$1" --arg f "${first:-$(date -Iseconds)}" --arg l "$(date +%F)" \
    '{kind: $k, first_seen: $f, last_alerted: $l}' > "$STATE.tmp" && mv -f "$STATE.tmp" "$STATE"
  echo "vault_sync: $2" >&2
  finish 1
}

# net <git args…>: a network git call bounded by the smaller of 120 s and the time left.
net() {
  local left=$(( DEADLINE - $(date +%s) ))
  (( left > 0 )) || return 124
  (( left <= 120 )) || left=120
  timeout "$left" git "$@"
}

git_dir="$(git rev-parse --git-dir 2>/dev/null)" || { echo "vault_sync: not a git repository" >&2; finish 1; }

# in_progress: print why git is mid-operation (precondition 4), or return 1.
in_progress() {
  local p
  if [[ -e "$git_dir/MERGE_HEAD" || -d "$git_dir/rebase-merge" || -d "$git_dir/rebase-apply" \
        || -e "$git_dir/CHERRY_PICK_HEAD" || -n "$(git ls-files -u 2>/dev/null)" ]]; then
    echo "operation in progress"
    return 0
  fi
  if [[ -e "$git_dir/index.lock" && -n "$(find "$git_dir/index.lock" -mmin +10 2>/dev/null)" ]]; then
    # ponytail: a git started elsewhere with -C is not seen; the lock then reads as stale and blocks (safe).
    for p in $(pgrep -x git 2>/dev/null); do
      [[ "$(readlink "/proc/$p/cwd" 2>/dev/null)" == "$VAULT_ROOT"* ]] && return 1
    done
    echo "stale index.lock"
    return 0
  fi
  return 1
}

# block <reason>: write the marker (one alert per blocked period) and exit 3.
block() {
  [[ -e "$BLOCKED" ]] || alert "sync blocked: $1; intake, brief and debrief are skipped until it is resolved"
  printf 'reason: %s\ntime: %s\n%s' "$1" "$(date -Iseconds)" "${2:-}" > "$BLOCKED"
  echo "vault_sync: blocked: $1" >&2
  finish 3
}

on_signal() {
  [[ ! -e "$git_dir/MERGE_HEAD" ]] || git merge --abort 2>/dev/null
  exit "$1"
}
trap 'on_signal 143' TERM
trap 'on_signal 130' INT

if [[ "$mode" == pre ]]; then
  [[ ! -e "$BLOCKED" ]] || exit 3
  in_progress > /dev/null && exit 3
fi

remote_mode="$(config_get remote_mode none)"
[[ "$remote_mode" == private ]] || fail config "remote_mode is $remote_mode, not private"
origin="$(git remote get-url origin 2>/dev/null)" || fail config "no origin remote; run /setup phase 4"
template="$(head -n 1 system/template_source 2>/dev/null || true)"
if [[ -n "$template" ]] && git_url_same "$origin" "$template"; then fail config "origin is the template repository"; fi
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" || fail config "no upstream; run /setup phase 4"
[[ "$upstream" == origin/* ]] || fail config "the upstream $upstream is not on origin"
branch="${upstream#origin/}"

exec 9> system/run.lock
if reason="$(in_progress)"; then
  # Unfinished before the lock: a sync holding the lock may be mid-merge, so only a free lock writes the marker.
  flock -n 9 && block "$reason"
  finish 3
fi
flock -n 9 || finish 4
reason="$(in_progress)" && block "$reason"

# sync_message: the scripted message for the staged changes (§4.1).
sync_message() {
  local a r p st n=0 body=""
  declare -A num=()
  while IFS=$'\t' read -r -d '' a r p; do
    if [[ "$a" == - ]]; then num[$p]="(binary)"; else num[$p]="+$a/-$r"; fi
  done < <(git diff --cached --numstat -z --no-renames)
  while IFS= read -r -d '' st && IFS= read -r -d '' p; do
    n=$(( n + 1 ))
    case "$st" in
      A) body+="${p//[$'\n\r\t']/ } (new)"$'\n' ;;
      D) body+="${p//[$'\n\r\t']/ } (deleted)"$'\n' ;;
      *) body+="${p//[$'\n\r\t']/ } ${num[$p]:-}"$'\n' ;;
    esac
  done < <(git diff --cached --name-status -z --no-renames)
  printf 'sync(%s): %d file(s)\n\n%s\nJarvis-Command: sync\nJarvis-Role: %s\n' "$role" "$n" "$body" "$role"
}

# Cycle (§5.1).
system/scripts/commit_runs.py > /dev/null || fail commit "commit_runs.py could not commit a run (see its alert)"
git add -A || fail commit "git add -A failed"
if ! git diff --cached --quiet; then
  if ! err="$(sync_message | git commit -q -F - 2>&1)"; then
    git reset -q
    fail commit "the sync commit was refused: $(head -n 1 <<< "$err")"
  fi
fi
for attempt in 1 2; do
  net fetch -q origin || fail fetch "git fetch origin failed"
  if ! git merge-base --is-ancestor "origin/$branch" HEAD; then
    if ! err="$(git merge -q --no-edit -m "sync($role): merge origin/$branch" \
                  -m "Jarvis-Command: sync"$'\n'"Jarvis-Role: $role" "origin/$branch" 2>&1)"; then
      if [[ -n "$(git ls-files -u)" ]]; then
        git merge --abort
        fail merge "merge conflict with origin/$branch"
      fi
      [[ ! -e "$git_dir/MERGE_HEAD" ]] || git merge --abort
      fail merge "git merge origin/$branch was refused: $(head -n 1 <<< "$err")"
    fi
  fi
  net push -q origin "HEAD:refs/heads/$branch" && break
  (( attempt == 1 )) || fail push "git push origin was rejected twice"
done
if [[ -f "$STATE" ]]; then
  alert "sync recovered (was failing: $(jq -r '.kind // "unknown"' "$STATE" 2>/dev/null))"
  rm -f "$STATE"
fi
finish 0
