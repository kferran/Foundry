# Today so far (phase D spec §3.9): the today file's embed line and yesterday's watch items by kind. Sourced by
# brief_prep.sh in a subshell, from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions
# spec §3). Records the watch's last tick for the Sources line.
yesterday="$(date -d "$PREP_DATE -1 day" +%F)"
prep_write sections/intraday.md printf 'today: [[%s.today]]\nyesterday (%s): %s\n' "$PREP_DATE" "$yesterday" \
  "$(extensions/intraday/scripts/today_log.py summary "$yesterday")"
# The last session or route line of yesterday's month and this one's (the same file twice within a month).
last="$(cat "system/logs/watch_fetch-${yesterday:0:7}.jsonl" "system/logs/watch_fetch-${PREP_DATE:0:7}.jsonl" 2>/dev/null \
  | jq -cR 'fromjson? | select(.step != "tick")' | tail -n 1)" || true
if [[ -z "$last" ]]; then
  prep_source watch off
elif [[ "$(jq -r .exit <<< "$last")" == 0 ]]; then
  prep_source watch ok
else
  prep_source watch failed "$(jq -r .reason <<< "$last")"
fi
exit 0
