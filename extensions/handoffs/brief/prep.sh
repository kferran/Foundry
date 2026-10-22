# Handoffs to chase (delivered work spec §3.3): stalled Jira handoffs, read live every brief. Sourced by
# brief_prep.sh in a subshell, from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions
# spec §3). Writes sections/handoffs.md: the fetch's lines, or an empty file while handoffs_projects is empty or
# the fetch failed.
: > "$PREP_DIR/sections/handoffs.md"
if [[ -z "$(config_get handoffs_projects)" ]]; then
  prep_source handoffs off
  exit 0
fi
rc=0
prep_write sections/handoffs.md extensions/handoffs/scripts/jira_fetch.sh || rc=$?
if (( rc == 0 )); then prep_source handoffs ok; else prep_source handoffs failed "$(prep_reason jira_fetch "$rc")"; fi
case "$rc" in
  0) ;;
  2) prep_unavailable "handoffs: $(sed -n 's/^jira_fetch: //p' "$PREP_DIR/prep_errors.log" | tail -n 1) (set it with /setup)" ;;
  3) prep_unavailable "handoffs: no Atlassian connector reachable (connect it at claude.ai with the account this machine's claude is logged in with, then re-run /setup)" ;;
  4) prep_unavailable "handoffs: the Jira connector timed out" ;;
  6) if [[ "$(sed -n 's/^jira_fetch: //p' "$PREP_DIR/prep_errors.log" | tail -n 1)" == *"too large"* ]]; then
       prep_unavailable "handoffs: a Jira search page was too large for the model to read; nothing was listed"
     else
       prep_unavailable "handoffs: the Jira connector returned an error (if it persists, reconnect Atlassian at claude.ai)"
     fi ;;
  7) prep_unavailable "handoffs: the fetch session used an unexpected tool; nothing was read (see system/logs/alerts_$(date +%F).md)" ;;
  127) prep_unavailable "handoffs: claude is not on PATH" ;;
  *) prep_unavailable "handoffs: jira_fetch.sh failed (exit $rc; see system/logs/jira_fetch-$(date +%Y-%m).jsonl)" ;;
esac
# A fetch failure is recorded above; the section stays empty and the brief still runs.
exit 0
