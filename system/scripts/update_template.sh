#!/bin/bash
# Fetch and merge template updates; never auto-resolves (spec §6.12).
# --unattended (foundry-update.timer, #87): take run.lock, abort a conflicted merge, and report through the
# alerts file the brief reads: what merged, a conflict, a failure or a busy skip. Nothing new is silent.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

unattended=0
alert() { mkdir -p system/logs; printf -- '- %s [update] %s\n' "$(date +%H:%M:%S)" "$1" >> "system/logs/alerts_$(date +%F).md"; }
die() {
  (( ! unattended )) || alert "template update failed: $2"
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
[[ -z "$(g status --porcelain)" ]] || die 1 "working tree is not clean; commit or stash first"

g fetch --quiet template || die 1 "git fetch template failed"
# LC_ALL=C: "HEAD branch:" is translated in other locales.
branch="$(LC_ALL=C g remote show template 2>/dev/null | sed -n 's/^ *HEAD branch: //p')"
[[ -n "$branch" && "$branch" != "(unknown)" ]] || die 1 "cannot determine the template's default branch"
ref="template/$branch"
g merge-base HEAD "$ref" >/dev/null 2>&1 \
  || die 1 "$ref shares no history with this vault (created from a GitHub template?); merge it by hand: git merge --allow-unrelated-histories $ref"
(( ! unattended )) || ! g merge-base --is-ancestor "$ref" HEAD || exit 0

if ! g merge --no-ff --no-edit "$ref"; then
  conflicted="$(g diff --name-only --diff-filter=U)"
  [[ -n "$conflicted" ]] || die 1 "git merge $ref failed"
  if (( unattended )); then
    g merge --abort
    alert "template update stopped on a conflict in $(paste -sd ' ' <<< "$conflicted"); the vault is unchanged. Run system/scripts/update_template.sh by hand and resolve it."
    exit 1
  fi
  echo "update_template: merge stopped on conflicts in:" >&2
  sed 's/^/  /' <<< "$conflicted" >&2
  echo "Resolve each file, then 'git add' it and 'git commit'; or run 'git merge --abort' to undo." >&2
  exit 1
fi

# Runs from before this update are committed with the rest of the vault, never one by one (two-machines spec §4.2).
system/scripts/commit_runs.py --init-cutover 9>&-
system/scripts/vault_index.py rebuild 9>&-

# Re-render units only where this vault already installed them: an update must never install or
# enable units the user skipped (spec gate: no unit runs before Plan 4 rewrites the commands).
unit_dir="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
owned=0
for f in "$unit_dir"/*.service "$unit_dir"/*.timer "$unit_dir"/*.service.d/*.conf; do
  if [[ -f "$f" && "$(head -n 1 -- "$f")" == "# Managed by vault: $VAULT_ROOT" ]]; then owned=1; break; fi
done
if (( owned )); then
  system/scripts/install_units.sh --update 9>&-
else
  echo "update_template: units not installed; skipped (install them with system/scripts/install_units.sh)"
fi

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
  list="$(printf '%s; ' "${merged[@]:0:10}")"
  list="${list%; }"
  (( ${#merged[@]} <= 10 )) || list+="; and $(( ${#merged[@]} - 10 )) more"
  alert "template updated: merged ${#merged[@]} change(s): $list"
fi
