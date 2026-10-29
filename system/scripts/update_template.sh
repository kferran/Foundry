#!/bin/bash
# Fetch and merge template updates; never auto-resolves (spec §6.12).
# --unattended (foundry-update.timer, #87): take run.lock, commit a dirty tree as the sync does (audit C4), abort a
# conflicted merge, and report through the alerts file the brief reads: what was committed and merged, a conflict,
# a failure or a busy skip. Nothing new is silent.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh
# shellcheck source=lib_git.sh
source system/scripts/lib_git.sh
# The vault's own day names the alerts file the brief reads, whatever the host's timezone.
TZ="$(config_get timezone UTC)"
export TZ GIT_TERMINAL_PROMPT=0
[[ -n "${GIT_SSH_COMMAND:-}" || -n "$(git config core.sshCommand 2>/dev/null)" ]] || export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15"

unattended=0
alert() { mkdir -p system/logs; printf -- '- %s [update] %s\n' "$(date +%H:%M:%S)" "$1" >> "system/logs/alerts_$(date +%F).md"; }
committed=""
die() {
  (( ! unattended )) || alert "template update failed: $committed$2"
  echo "update_template: $2" >&2
  exit "$1"
}
case "${1:-}" in
  "") ;;
  --unattended) unattended=1 ;;
  *) die 2 "usage: update_template.sh [--unattended]" ;;
esac
(( $# <= 1 )) || die 2 "usage: update_template.sh [--unattended]"
# git children run with run.lock's fd 9 closed: a detached gc must not keep the lock.
g() { git "$@" 9>&-; }

if (( unattended )); then
  exec 9> system/run.lock
  if ! flock -w "${UPDATE_LOCK_WAIT:-300}" 9; then
    alert "template update skipped: another run held run.lock; it runs again tomorrow"
    exit 0
  fi
fi

g remote get-url template >/dev/null 2>&1 || die 1 "no template remote; run system/scripts/setup_remote.sh first"
# update_extensions: extensions/ is tracked and arrives with the merge (extensions spec §3). The skill links are
# re-made, and each listed extension that cannot load (or a field the loader ignores) is alerted once a day as
# "[extensions] <reason>".
update_extensions() {
  local reason moved
  # A feature that moved out of core is listed once when its old switch is set (extensions spec §4).
  moved="$( [[ ! -f system/scripts/extensions.py ]] || system/scripts/extensions.py migrate 2>/dev/null 9>&- || true)"
  [[ -z "$moved" ]] || echo "update_template: extensions: $(paste -sd ',' <<< "$moved" | sed 's/,/, /g')"
  [[ ! -f system/scripts/extensions.py ]] || system/scripts/extensions.py link > /dev/null 2>&1 9>&- || true
  [[ ! -f system/scripts/extensions.py ]] || while IFS= read -r reason; do
    [[ -n "$reason" ]] || continue
    mkdir -p system/logs
    grep -qF -- "[extensions] $reason" "system/logs/alerts_$(date +%F).md" 2>/dev/null \
      || printf -- '- %s [extensions] %s\n' "$(date +%H:%M:%S)" "$reason" >> "system/logs/alerts_$(date +%F).md"
  done < <(system/scripts/extensions.py check 2>/dev/null 9>&- || true)
}
# list10 <item…>: the alert's list form, at most 10 items then "and N more".
list10() {
  local s
  s="$(printf '%s; ' "${@:1:10}")"
  s="${s%; }"
  (( $# <= 10 )) || s+="; and $(( $# - 10 )) more"
  printf '%s' "$s"
}
if (( unattended )); then
  # A dirty tree is committed the way the sync does it (audit C4): on a server the --pre sync already did; on a
  # standalone machine nothing else commits between /backup runs. Every outcome names the commits made first.
  before="$(g rev-parse HEAD)"
  rc=0
  git_sync_commit "$(config_get machine_role standalone)" || rc=$?
  mapfile -t subjects < <(g log --reverse --format=%s "$before..HEAD")
  (( ${#subjects[@]} == 0 )) || committed="committed first: $(list10 "${subjects[@]}"); "
  # A run the hook refused (audit C7 §3) and a file left out for a secret shape (#166) stay uncommitted and the
  # update goes on (owner, #136 2026-10-15); every later alert names them, a secret by path, line and shape only.
  [[ -z "$GIT_SYNC_REFUSED" ]] || committed+="a published run was refused by the pre-commit hook and left uncommitted: $(paste -sd ' ' <<< "${GIT_SYNC_REFUSED%$'\n'}") (the hook's line is in today's [commit_runs] alert); "
  [[ -z "$GIT_SYNC_SECRETS" ]] || committed+="a file adds a secret shape and was left out of the commit: $(paste -sd ' ' <<< "${GIT_SYNC_SECRETS%$'\n'}"); "
  (( rc == 0 )) || die 1 "$GIT_SYNC_ERROR"
else
  [[ -z "$(g status --porcelain)" ]] || die 1 "working tree is not clean; commit or stash first"
fi

timeout "${UPDATE_FETCH_TIMEOUT:-300}" git fetch --quiet template 9>&- || die 1 "git fetch template failed"
# LC_ALL=C: "HEAD branch:" is translated in other locales.
branch="$(LC_ALL=C g remote show template 2>/dev/null | sed -n 's/^ *HEAD branch: //p')"
[[ -n "$branch" && "$branch" != "(unknown)" ]] || die 1 "cannot determine the template's default branch"
ref="template/$branch"
g merge-base HEAD "$ref" >/dev/null 2>&1 \
  || die 1 "$ref shares no history with this vault (created from a GitHub template?); merge it by hand: git merge --allow-unrelated-histories $ref"
if (( unattended )) && g merge-base --is-ancestor "$ref" HEAD; then
  [[ -z "$committed" ]] || alert "template update: ${committed}nothing new to merge"
  exit 0
fi

# The vault owns README.md (#90): for this merge only, an attributes file marks it merge=ours and the driver keeps
# the vault's version, the first update included. Sync merges between machines define neither and merge it normally.
attrs="$(mktemp)"
trap 'rm -f -- "$attrs"' EXIT
printf 'README.md merge=ours\n' > "$attrs"
pre_merge="$(g rev-parse HEAD)"
if ! out="$(g -c core.attributesFile="$attrs" -c merge.ours.driver=true merge --no-ff --no-edit "$ref" 2>&1)"; then
  printf '%s\n' "$out" >&2
  conflicted="$(g diff --name-only --diff-filter=U)"
  # Git refuses before it starts when the merge would overwrite a file left uncommitted, and names the files on
  # tab-indented lines after its first line (audit C7 §2).
  [[ -n "$conflicted" ]] || die 1 "git merge $ref was refused: $(head -n 1 <<< "$out") $(grep -P '^\t' <<< "$out" | sed 's/^\t//' | paste -sd ' ')"
  if (( unattended )); then
    g merge --abort || die 1 "merge stopped on a conflict and git merge --abort failed; resolve it by hand"
    alert "template update stopped on a conflict in $(paste -sd ' ' <<< "$conflicted"); the vault is unchanged${committed:+ apart from: ${committed%; }}. Run system/scripts/update_template.sh by hand and resolve it."
    exit 1
  fi
  echo "update_template: merge stopped on conflicts in:" >&2
  sed 's/^/  /' <<< "$conflicted" >&2
  echo "Resolve each file, then 'git add' it and 'git commit'; or run 'git merge --abort' to undo." >&2
  exit 1
fi
printf '%s\n' "$out"

list=""
if (( unattended )); then
  # The template's own history since the vault's last merge of it: one entry per pull request merged there.
  merged=()
  while IFS=$'\x1f' read -r -d $'\x1e' subject title; do
    subject="${subject#$'\n'}" title="${title%%$'\n'*}"
    if [[ "$subject" =~ ^Merge\ pull\ request\ (#[0-9]+) && -n "$title" ]]; then
      merged+=("${BASH_REMATCH[1]} $title")
    else
      merged+=("$subject")
    fi
  done < <(g log --first-parent --format='%s%x1f%b%x1e' HEAD^1..HEAD^2)
  list="$(list10 "${merged[@]}")"
fi
# after_merge <step> <command…>: the merge has landed, so an unattended run names it when a later step fails.
after_merge() {
  local rc=0
  "${@:2}" 9>&- || rc=$?
  (( rc == 0 )) || (( ! unattended )) || die 1 "merged $list, then $1 failed"
  return "$rc"
}

update_extensions

# What changed (changes folder spec §3.3): the change and Action lines of each changes/ file this merge added, in
# name order, appended to today's updates.md for the next brief. changes/CHANGELOG.md is frozen history, and a
# vault's first changes/ folder is history too, so neither floods a brief.
changes_added() {
  g cat-file -e HEAD^1:changes 2>/dev/null || return 0
  local f
  while IFS= read -r f; do
    [[ "$f" == changes/*.md && "$f" != changes/CHANGELOG.md ]] || continue
    g show "HEAD:$f" | grep -E '^(- |  - Action: )' || true
  done < <(g diff --name-only --diff-filter=A HEAD^1 HEAD -- changes/ | sort)
}
notes="system/logs/inputs/$(date +%F)/updates.md"
notes_suffix=""
if [[ "$(g rev-parse HEAD)" != "$pre_merge" ]]; then
  added="$(changes_added || true)"
  mkdir -p "$(dirname "$notes")" || true
  touch "$notes" || true
  if [[ -n "$added" ]] && printf '%s\n' "$added" >> "$notes"; then notes_suffix="; notes in today's brief"; fi
fi

# Runs from before this update are committed with the rest of the vault, never one by one (two-machines spec §4.2).
after_merge "commit_runs.py --init-cutover" system/scripts/commit_runs.py --init-cutover
after_merge "the index rebuild" system/scripts/vault_index.py rebuild

# Re-render units only where this vault already installed them: an update must never install or
# enable units the user skipped (spec gate: no unit runs before Plan 4 rewrites the commands).
unit_dir="${SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
owned=0
for f in "$unit_dir"/*.service "$unit_dir"/*.timer "$unit_dir"/*.service.d/*.conf; do
  if [[ -f "$f" && "$(head -n 1 -- "$f")" == "# Managed by vault: $VAULT_ROOT" ]]; then owned=1; break; fi
done
new_units=""
if (( owned )); then
  units_out="$(after_merge "install_units.sh --update" system/scripts/install_units.sh --update)"
  printf '%s\n' "$units_out"
  new_units="$(sed -n 's/^new unit available: \([^ ]*\).*/\1/p' <<< "$units_out" | paste -sd ',' | sed 's/,/, /g')"
else
  echo "update_template: units not installed; skipped (install them with system/scripts/install_units.sh)"
fi

if (( unattended )); then
  alert "template updated: ${committed}merged ${#merged[@]} change(s): $list${new_units:+; new unit available: $new_units (install with system/scripts/install_units.sh)}${notes_suffix}"
fi
