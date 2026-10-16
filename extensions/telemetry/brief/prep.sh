# Telemetry in the brief (Plan 11 spec §6): a last fetch before the brief, then the error groups the brief lists.
# Sourced by brief_prep.sh in a subshell, from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions
# (extensions spec §3). Writes sections/telemetry.md: the active groups and those resolved in the last 24 hours as one
# table, then the sources' ranks; empty when there are no such groups.
: > "$PREP_DIR/sections/telemetry.md"
rc=0
extensions/telemetry/scripts/telemetry_fetch.py > /dev/null 2>> "$PREP_DIR/prep_errors.log" || rc=$?
case "$rc" in
  0) ;;
  1) prep_unavailable "telemetry: a source failed (see system/logs/telemetry-${PREP_DATE:0:7}.jsonl)" ;;
  4) prep_unavailable "telemetry: a fetch was already running" ;;
  *) prep_unavailable "telemetry: telemetry_fetch.py failed (exit $rc; see $PREP_DIR/prep_errors.log)" ;;
esac
# Notes store UTC timestamps with a +00:00 offset, so the cutoff is written the same way.
cutoff="$(date -u -d '-24 hours' +%Y-%m-%dT%H:%M:%S+00:00)"
rc=0
groups="$(system/scripts/vault_index.py query --limit 500 "SELECT path, environment, source, service, exception, count, detected_at, last_seen, resolved_at, substatus, regressed, sentry_issue, covered, mock, partition, escalate, escalated_at FROM v_production_error WHERE status = 'active' OR resolved_at >= '$cutoff' ORDER BY environment, count DESC" 2>> "$PREP_DIR/prep_errors.log")" || rc=$?
if (( rc != 0 )); then
  prep_unavailable "telemetry: the error groups could not be read (see $PREP_DIR/prep_errors.log)"
  exit 0
fi
# A table with no rows is its header and separator only.
(( $(wc -l <<< "$groups") > 2 )) || exit 0
rc=0
ranks="$(system/scripts/vault_index.py query "SELECT name, environment, rank FROM v_telemetry_source" 2>> "$PREP_DIR/prep_errors.log")" || rc=$?
(( rc == 0 )) || prep_unavailable "telemetry: the source ranks could not be read (see $PREP_DIR/prep_errors.log)"
printf '## Error groups (cutoff %s)\n\n%s\n\n## Sources\n\n%s\n' "$cutoff" "$groups" "$ranks" > "$PREP_DIR/sections/telemetry.md"
exit 0
