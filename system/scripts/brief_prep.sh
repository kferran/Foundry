#!/bin/bash
# Calendar and yesterday's focus stats into system/logs/inputs/<date>/ (spec §6.5; calendar spec §5).
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
prep_init brief_prep "$@"

# The calendar comes from the Google Calendar connector through a narrow claude session
# (calendar_fetch.sh, calendar spec §4); its reason line on failure lands in prep_errors.log.
rc=0
prep_write calendar.tsv system/scripts/calendar_fetch.sh "$PREP_DATE" || rc=$?
case "$rc" in
  0) ;;
  3) prep_unavailable "calendar: no Google Calendar connector reachable (connect it at claude.ai with the account this machine's claude is logged in with, then re-run /setup phase 6)" ;;
  4) prep_unavailable "calendar: the connector timed out" ;;
  5) prep_unavailable "calendar: the connector returned an unreadable event list (see system/logs/calendar_fetch-${PREP_DATE:0:7}.jsonl)" ;;
  6) prep_unavailable "calendar: the connector returned an error: $(sed -n 's/^calendar_fetch: the connector returned an error: //p' "$PREP_DIR/prep_errors.log" | tail -n 1) (if it persists, reconnect Google Calendar at claude.ai)" ;;
  7) prep_unavailable "calendar: the fetch session used an unexpected tool; nothing was written (see system/logs/alerts_$(date +%F).md)" ;;
  8) prep_unavailable "calendar: more than 100 events that day; not listed" ;;
  127) prep_unavailable "calendar: claude is not on PATH" ;;
  *) prep_unavailable "calendar: calendar_fetch.sh failed (exit $rc; see $PREP_DIR/prep_errors.log)" ;;
esac

# Error telemetry (Plan 11 spec §6): a last fetch before the brief. Notes land in raw/telemetry/.
rc=0
system/scripts/telemetry_fetch.py > /dev/null 2>> "$PREP_DIR/prep_errors.log" || rc=$?
case "$rc" in
  0) ;;
  1) prep_unavailable "telemetry: a source failed (see system/logs/telemetry-${PREP_DATE:0:7}.jsonl)" ;;
  4) prep_unavailable "telemetry: a fetch was already running" ;;
  *) prep_unavailable "telemetry: telemetry_fetch.py failed (exit $rc; see $PREP_DIR/prep_errors.log)" ;;
esac

yesterday="$(date -d "$PREP_DATE -1 day" +%F)"
prep_write focus_yesterday.md system/scripts/focus_stats.sh "$yesterday" \
  || prep_unavailable "focus_yesterday: focus_stats.sh failed"
[[ -s "system/logs/obsidian_focus_$yesterday.log" ]] || prep_unavailable "focus_yesterday: no focus log for $yesterday"
exit 0
