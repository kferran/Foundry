#!/bin/bash
# Calendar, meeting actions, active projects, handoffs and yesterday's focus stats into system/logs/inputs/<date>/ (spec §6.5;
# calendar spec §5; meetings spec §2.5; delivered work spec §3.3).
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

prep_write actions.md system/scripts/meeting_actions.py "$PREP_DATE" \
  || prep_unavailable "actions: meeting_actions.py failed (see $PREP_DIR/prep_errors.log)"
# Active projects with their next actions and decisions waiting (active projects spec §4, issue #65).
prep_write projects.md system/scripts/active_projects.py "$PREP_DATE" \
  || prep_unavailable "projects: active_projects.py failed (see $PREP_DIR/prep_errors.log)"
prep_meetings
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

# The Now page (Now page spec §3.3): once, a missing default-partition page takes the latest earlier briefing's
# open objectives; then now.md lists the open lines of both pages, so the brief adds no repeat.
NOW_LOCK_WAIT="${ARCHIVE_LOCK_WAIT:-60}" system/scripts/now.py seed "$PREP_DATE" > /dev/null 2>> "$PREP_DIR/prep_errors.log" \
  || prep_unavailable "now: the first Now page was not seeded (see $PREP_DIR/prep_errors.log)"
prep_write now.md system/scripts/now.py list \
  || prep_unavailable "now: now.py list failed (see $PREP_DIR/prep_errors.log)"
# Friction notes no earlier brief has listed, plus the count (one-screen brief spec §3.3).
prep_write friction.md system/scripts/friction_notes.py "$PREP_DATE" \
  || prep_unavailable "friction: friction_notes.py failed (see $PREP_DIR/prep_errors.log)"
# The Work Orders report for this morning (Nightshift spec §6); empty when nothing ran.
if [[ -f "system/logs/nightshift/$PREP_DATE.md" ]]; then
  prep_write nightshift.md cat "system/logs/nightshift/$PREP_DATE.md" || prep_unavailable "nightshift: report unreadable"
else
  : > "$PREP_DIR/nightshift.md"
fi
# Handoffs to chase (delivered work spec §3.3): stalled Jira handoffs, read live every brief; empty while
# handoffs_projects is empty or when the fetch failed.
: > "$PREP_DIR/handoffs.md"
if [[ -n "$(config_get handoffs_projects)" ]]; then
  rc=0
  prep_write handoffs.md system/scripts/jira_fetch.sh || rc=$?
  case "$rc" in
    0) ;;
    2) prep_unavailable "handoffs: $(sed -n 's/^jira_fetch: //p' "$PREP_DIR/prep_errors.log" | tail -n 1) (set it with /setup)" ;;
    3) prep_unavailable "handoffs: no Atlassian connector reachable (connect it at claude.ai with the account this machine's claude is logged in with, then re-run /setup)" ;;
    4) prep_unavailable "handoffs: the Jira connector timed out" ;;
    6) prep_unavailable "handoffs: the Jira connector returned an error (if it persists, reconnect Atlassian at claude.ai)" ;;
    7) prep_unavailable "handoffs: the fetch session used an unexpected tool; nothing was read (see system/logs/alerts_$(date +%F).md)" ;;
    127) prep_unavailable "handoffs: claude is not on PATH" ;;
    *) prep_unavailable "handoffs: jira_fetch.sh failed (exit $rc; see system/logs/jira_fetch-$(date +%Y-%m).jsonl)" ;;
  esac
fi
# New DTCC changes since the latest earlier briefing (DTCC watcher spec §7); empty without a map.
prep_write dtcc.md system/scripts/dtcc_watch.py --brief "$PREP_DATE" \
  || prep_unavailable "dtcc: dtcc_watch.py --brief failed (see $PREP_DIR/prep_errors.log)"

# Briefings and debriefs dated before today move to briefings/archive/<YYYY-MM>/, after the Now seed and
# dtcc.md are written (now.py seed and dtcc_watch.py read the archive too). The sync commit records
# the moves. Only a run for today archives: /brief <past date> must find that day's briefing where it is.
today="$(date +%F)"
if [[ "$PREP_DATE" == "$today" ]]; then
  # run.lock, like every other writer of tracked files: a sync's git add -A must not see half the moves.
  exec 9>system/run.lock
  if flock -w "${ARCHIVE_LOCK_WAIT:-60}" 9; then
    # Yesterday stays one more day: a client may still have it open in Obsidian (#57).
    yesterday="$(date -d "$today -1 day" +%F)"
    for f in briefings/*.md; do
      name="${f#briefings/}"
      [[ "$name" =~ ^(([0-9]{4}-[0-9]{2})-[0-9]{2})(\.debrief)?\.md$ ]] || continue
      [[ "${BASH_REMATCH[1]}" < "$yesterday" ]] || continue
      dest="briefings/archive/${BASH_REMATCH[2]}/$name"
      if [[ -e "$dest" ]]; then
        prep_unavailable "briefings: $name not archived ($dest exists; merge the two copies, then delete briefings/$name)"
      else
        { mkdir -p "${dest%/*}" && mv "$f" "$dest"; } 2>> "$PREP_DIR/prep_errors.log" \
          || prep_unavailable "briefings: $name could not be archived (see $PREP_DIR/prep_errors.log)"
      fi
    done
  else
    prep_unavailable "briefings: run.lock busy; nothing archived"
  fi
  exec 9>&-
fi
exit 0
