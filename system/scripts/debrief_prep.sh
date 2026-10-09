#!/bin/bash
# Git activity, session digests and focus stats into system/logs/inputs/<date>/ (spec §6.5).
# Exits 0 whenever the date is valid; every source that could not be read gets a line in unavailable.md.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_args.sh
source system/scripts/lib_args.sh
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh
# shellcheck source=lib_prep.sh
source system/scripts/lib_prep.sh
prep_init debrief_prep "$@"

# These functions run inside prep_write's `||` context, where bash disables errexit, so every
# failure must return explicitly.

# One "## <name>" section per repo. In a codebase with user.email configured, only that author's
# commits are listed, so a shared work repo shows your day rather than the whole team's. The vault
# lists every author: its commits come from scripts and other machines (two-machines spec §4.4).
# Local branches only: remote-tracking refs (the template remote included) are other people's history.
repo_log() {  # <name> <path> [all]
  local email log
  local -a author=()
  email="$(git -C "$2" config user.email 2>/dev/null || true)"
  [[ -z "$email" || "${3:-}" == all ]] || author=(--author="$email")
  log="$(git -C "$2" log --branches --no-merges "${author[@]}" \
    --since="${PREP_DATE}T00:00:00" --until="${PREP_DATE}T23:59:59" \
    --date=format-local:%H:%M --format='- %ad %h %s')" || return 1
  printf '## %s\n\n%s\n\n' "$1" "${log:-No commits.}"
}

git_md() {
  local name path
  repo_log vault "$VAULT_ROOT" all || prep_unavailable "git: git log failed for the vault"
  while IFS= read -r name; do
    path="$(codebase_get "$name" path)"
    if [[ -z "$path" ]] || ! git -C "$path" rev-parse --git-dir >/dev/null 2>&1; then
      prep_unavailable "git: codebase $name has no git repository at ${path:-<no path>}"
      continue
    fi
    repo_log "$name" "$path" || prep_unavailable "git: git log failed for codebase $name"
  done < <(codebases_list)
}
prep_write git.md git_md || prep_unavailable "git: git.md could not be written"

digests_md() {
  local rows path partition codebase created
  rows="$(system/scripts/vault_index.py query --json \
    "SELECT path, partition, codebase, created_at FROM v_session_digest WHERE substr(created_at, 1, 10) = '$PREP_DATE' ORDER BY created_at, path")" || return 1
  jq -e '.rows | type == "array"' >/dev/null 2>&1 <<< "$rows" || return 1
  if [[ "$(jq '.rows | length' <<< "$rows")" == 0 ]]; then
    echo "No session digests."
    return 0
  fi
  while IFS=$'\t' read -r path partition codebase created; do
    printf '## %s (%s, %s, %s)\n\n' "${path##*/}" "$partition" "$codebase" "$created"
    awk 'NR==1 && $0=="---" {fm=1; next} fm && $0=="---" {fm=0; next} !fm' "$path"
    echo
  done < <(jq -r '.rows[] | @tsv' <<< "$rows")
}
prep_write digests.md digests_md || prep_unavailable "digests: index query failed (see $PREP_DIR/prep_errors.log)"

# The open Work Orders report (Foreman v1 §3.4): everything after this morning's brief lands in the next day's
# report, so the debrief for a date reads the report dated one day later. Empty when nothing ran.
open_report="system/logs/nightshift/$(date -d "$PREP_DATE +1 day" +%F).md"
if [[ -f "$open_report" ]]; then
  prep_write orders.md cat "$open_report" || prep_unavailable "orders: report unreadable"
else
  : > "$PREP_DIR/orders.md"
fi

# Pull requests for Delivered Today (delivered work spec §3.4): opened or merged by you that day, or reviewed by
# you and updated that day, in the registered GitHub repositories. Empty when none is registered.
github_repos() {  # owner/repo, one per line: each codebase's order_pr (or nightshift_pr), and a GitHub template_remote
  local name pr
  while IFS= read -r name; do
    pr="$(codebase_get "$name" order_pr)"
    [[ -n "$pr" ]] || pr="$(codebase_get "$name" nightshift_pr)"
    [[ "$pr" != github:* ]] || printf '%s\n' "${pr#github:}"
  done < <(codebases_list)
  config_get template_remote | sed -nE 's#^.*github\.com[:/]([^/]+/[^/]+)$#\1#p' | sed 's/\.git$//'
}
prs_md() {
  local r
  local -a repos=() args=()
  mapfile -t repos < <(github_repos)
  (( ${#repos[@]} )) || return 0
  command -v gh > /dev/null 2>&1 || return 3
  for r in "${repos[@]}"; do args+=(--repo "$r"); done
  args+=(--json url,title --limit 100)
  gh search prs --author @me --created "$PREP_DATE" "${args[@]}" --jq '.[] | "- code — opened: \(.title) — \(.url)"' || return 1
  gh search prs --author @me --merged-at "$PREP_DATE" "${args[@]}" --jq '.[] | "- code — merged: \(.title) — \(.url)"' || return 1
  gh search prs --reviewed-by @me --updated "$PREP_DATE" "${args[@]}" --jq '.[] | "- review — reviewed: \(.title) — \(.url)"' || return 1
}
rc=0
prep_write prs.md prs_md || rc=$?
case "$rc" in
  0) ;;
  3) prep_unavailable "prs: gh is not installed; pull requests are not listed" ;;
  *) prep_unavailable "prs: gh search failed (see $PREP_DIR/prep_errors.log)" ;;
esac

prep_meetings
prep_write focus.md system/scripts/focus_stats.sh "$PREP_DATE" || prep_unavailable "focus: focus_stats.sh failed"
[[ -s "system/logs/obsidian_focus_$PREP_DATE.log" ]] || prep_unavailable "focus: no focus log for $PREP_DATE"
exit 0
