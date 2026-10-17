#!/bin/bash
# Git activity and session digests into system/logs/inputs/<date>/ (spec §6.5).
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
# A zero says when it was counted (#166): "No commits by 17:00." for today, plain for a past day.
by=""
[[ "$PREP_DATE" != "$(date +%F)" ]] || by=" by $(date +%H:%M)"

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
  printf '## %s\n\n%s\n\n' "$1" "${log:-No commits$by.}"
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
    echo "No session digests$by."
    return 0
  fi
  while IFS=$'\t' read -r path partition codebase created; do
    printf '## %s (%s, %s, %s)\n\n' "${path##*/}" "$partition" "$codebase" "$created"
    awk 'NR==1 && $0=="---" {fm=1; next} fm && $0=="---" {fm=0; next} !fm' "$path"
    echo
  done < <(jq -r '.rows[] | @tsv' <<< "$rows")
}
prep_write digests.md digests_md || prep_unavailable "digests: index query failed (see $PREP_DIR/prep_errors.log)"
# The same quarantine rows the brief reads, so the two never disagree (quarantine-in-brief spec §2).
prep_write quarantine.md system/scripts/intake.py --quarantine --date "$PREP_DATE" \
  || prep_unavailable "quarantine: intake.py --quarantine failed (see $PREP_DIR/prep_errors.log)"

# The open Work Orders report (Foreman v1 §3.4): everything after this morning's brief lands in the next day's
# report, so the debrief for a date reads the report dated one day later. Empty when nothing ran.
open_report="system/logs/nightshift/$(date -d "$PREP_DATE +1 day" +%F).md"
if [[ -f "$open_report" ]]; then
  prep_write orders.md cat "$open_report" || prep_unavailable "orders: report unreadable"
else
  : > "$PREP_DIR/orders.md"
fi

# Pull requests for Delivered Today (delivered work spec §3.4): opened or merged by you that day, or reviewed by
# you and updated that day, in the registered GitHub repositories (github_repos). Empty when none is registered.
prs_md() {
  local r
  local -a repos=() args=()
  mapfile -t repos < <(github_repos)
  (( ${#repos[@]} )) || return 0
  command -v gh > /dev/null 2>&1 || return 3
  for r in "${repos[@]}"; do args+=(--repo "$r"); done
  args+=(--json url,title --limit 100)
  # Each search is cut off after GH_TIMEOUT seconds, so a hung proxy cannot eat the debrief's budget (audit C11).
  local t="${GH_TIMEOUT:-60}"
  timeout "$t" gh search prs --author @me --created "$PREP_DATE" "${args[@]}" --jq '.[] | "- code — opened: \(.title) — \(.url)"' || return 1
  timeout "$t" gh search prs --author @me --merged-at "$PREP_DATE" "${args[@]}" --jq '.[] | "- code — merged: \(.title) — \(.url)"' || return 1
  timeout "$t" gh search prs --reviewed-by @me --updated "$PREP_DATE" "${args[@]}" --jq '.[] | "- review — reviewed: \(.title) — \(.url)"' || return 1
}
rc=0
prep_write prs.md prs_md || rc=$?
case "$rc" in
  0) ;;
  3) prep_unavailable "prs: gh is not installed; pull requests are not listed" ;;
  *) prep_unavailable "prs: gh search failed (see $PREP_DIR/prep_errors.log)" ;;
esac

prep_meetings
# The heartbeat (#166): the day's commits, digests, pull requests, alerts and headless runs (as run_headless.sh counts
# them for the daily cap); unknown when git or the digest query failed, so a quiet day and a dead read differ.
signals="$( { grep -h '^- ' "$PREP_DIR/git.md" "$PREP_DIR/prs.md" "system/logs/alerts_$PREP_DATE.md"
  grep -hE '^## [^ ]+\.md \(' "$PREP_DIR/digests.md"
  jq -R --arg d "$PREP_DATE" 'fromjson? | objects | (.exit // 0) as $e | select(.command != "retry" and .command != "meeting" and ([2,3,4,6] | index($e) | not) and (((.started_at | strings) // "") | startswith($d))) | 1' "system/logs/runs-${PREP_DATE:0:7}.jsonl"
  } 2>/dev/null | wc -l)" || true
[[ -f "$PREP_DIR/git.md" && -f "$PREP_DIR/digests.md" ]] && ! grep -qE '^- debrief_prep: (git|digests):' \
  "$PREP_DIR/unavailable.md" 2>/dev/null || signals=unknown
printf 'signals: %s (%s)\n' "$signals" "$PREP_DATE" > "$PREP_DIR/heartbeat.md"
exit 0
