# shellcheck shell=bash
# Shared helpers for the connector fetch scripts (F1 spec §3.2). Source after lib_connector.sh (fetch_reason and fail
# call connector_classify). The script sets, before calling:
#   FETCH_NAME    the stderr prefix (triage_fetch)
#   FETCH_TAG     the alert tag (triage)
#   FETCH_LOG     the month's JSONL log
#   FETCH_FIELDS  a JSON object merged into every log line (default {})
#   FETCH_LABEL   the alert key's lead (Inbox triage)
#   FETCH_ALERTS  the exits that alert, space-separated (1 2 3 4 6 7)

# Each server's full tool list, the allowed tool included: fetch_others subtracts the one a session may call.
# shellcheck disable=SC2034  # read by the scripts that source this file
GMAIL_TOOLS=(apply_sensitive_message_label apply_sensitive_thread_label create_draft create_label delete_draft
  delete_label forward get_draft get_message get_thread label_message label_thread list_drafts list_labels
  mark_message_spam mark_thread_spam reply search_threads send_message trash_message trash_thread unlabel_message
  unlabel_thread unmark_message_spam unmark_thread_spam untrash_message untrash_thread update_draft update_label
  update_message_labels)
# shellcheck disable=SC2034
SLACK_TOOLS=(slack_send_message slack_send_message_draft slack_schedule_message slack_add_reaction
  slack_add_list_record slack_complete_file_upload slack_create_canvas slack_create_conversation slack_create_list
  slack_get_file_upload_url slack_get_reactions slack_list_channel_members slack_list_user_channels slack_read_canvas
  slack_read_channel slack_read_file slack_read_list slack_read_thread slack_read_user_profile slack_search_channels
  slack_search_emojis slack_search_public slack_search_public_and_private slack_search_users slack_update_canvas
  slack_update_list slack_update_list_record)
# shellcheck disable=SC2034
DRIVE_TOOLS=(search_files read_file_content create_file update_file copy_file share_file trash_file
  download_file_content get_file_permissions list_recent_files get_file_metadata)
# shellcheck disable=SC2034
CALENDAR_TOOLS=(list_events create_event update_event delete_event respond_to_event get_event search_events
  list_calendars suggest_time)

logline() {  # <exit> <reason> [<JSON object>]: {time, exit, reason} + FETCH_FIELDS + the object, one line to FETCH_LOG
  jq -cn --arg time "$(date -Iseconds)" --argjson exit "$1" --arg reason "$2" --argjson f "${FETCH_FIELDS:-"{}"}" \
    --argjson x "${3:-"{}"}" '{time: $time, exit: $exit, reason: $reason} + $f + $x' >> "$FETCH_LOG"
}
alert_once() {  # <key> <text>: "- HH:MM:SS [FETCH_TAG] <key> <text>", at most one alert a day per key
  local f="system/logs/alerts_$(date +%F).md"
  grep -qF -- "[$FETCH_TAG] $1" "$f" 2>/dev/null || printf -- '- %s [%s] %s %s\n' "$(date +%H:%M:%S)" "$FETCH_TAG" "$1" "$2" >> "$f"
}
fetch_reason() {  # <exit> <reason>: FETCH_REASON, led by its connector class (connector health spec §2)
  connector_classify "$1" "$2" "${work:-}"
  FETCH_REASON="${CONNECTOR_CLASS:+$CONNECTOR_CLASS: }$2"
}
fail() {  # <exit> <reason>: log, alert an exit in FETCH_ALERTS once a day, print and exit
  fetch_reason "$1" "$2"
  logline "$1" "$FETCH_REASON"
  [[ " ${FETCH_ALERTS:-} " != *" $1 "* ]] || alert_once "$FETCH_LABEL failed (exit $1):" "$FETCH_REASON"
  echo "$FETCH_NAME: $FETCH_REASON" >&2
  exit "$1"
}
skip() {  # <reason> [<JSON object>]: a run that does not happen, logged and not alerted
  logline 0 "skipped: $1" "${2:-"{}"}"
  exit 0
}
fetch_check_arg() {  # "$@": check=1 for --check, 0 for no argument; anything else is a usage error
  case "$#:${1:-}" in
    0:) check=0 ;;
    1:--check) check=1 ;;
    *) echo "usage: $FETCH_NAME.sh [--check]" >&2; exit 2 ;;
  esac
}
fetch_workdir() {  # work: a new directory under /tmp, removed on exit; a session's directory under it goes too (#40)
  work="$(mktemp -d -p /tmp)"
  trap 'rm -rf -- "$work"' EXIT
}
fetch_others() {  # <server tools...>: CONNECTOR_OTHERS, each tool but the one the session may call
  local t
  CONNECTOR_OTHERS=()
  for t in "$@"; do [[ "${CONNECTOR_PREFIX}__$t" == "$CONNECTOR_TOOL" ]] || CONNECTOR_OTHERS+=("$t"); done
}
