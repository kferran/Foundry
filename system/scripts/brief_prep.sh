#!/bin/bash
# Calendar and yesterday's focus stats into system/logs/inputs/<date>/ (spec §6.5).
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

# stdin from /dev/null and a timeout: an unauthenticated gcalcli prompts for input and would
# otherwise hang the unit's ExecStartPre until systemd kills it.
rc=0
prep_write calendar.tsv timeout 60 gcalcli agenda "${PREP_DATE}T00:00" "${PREP_DATE}T23:59" --tsv < /dev/null || rc=$?
case "$rc" in
  0) ;;
  127) prep_unavailable "calendar: gcalcli is not installed" ;;
  124) prep_unavailable "calendar: gcalcli timed out after 60s (run: gcalcli init)" ;;
  *) prep_unavailable "calendar: gcalcli agenda failed (exit $rc; see $PREP_DIR/prep_errors.log)" ;;
esac

yesterday="$(date -d "$PREP_DATE -1 day" +%F)"
prep_write focus_yesterday.md system/scripts/focus_stats.sh "$yesterday" \
  || prep_unavailable "focus_yesterday: focus_stats.sh failed"
[[ -s "system/logs/obsidian_focus_$yesterday.log" ]] || prep_unavailable "focus_yesterday: no focus log for $yesterday"
exit 0
