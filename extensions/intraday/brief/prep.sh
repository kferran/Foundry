# Today so far (phase D spec §3.9): the today file's embed line and yesterday's watch items by kind. Sourced by
# brief_prep.sh in a subshell, from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions
# spec §3). Records the watch's last tick for the Sources line.
yesterday="$(date -d "$PREP_DATE -1 day" +%F)"
prep_write sections/intraday.md printf 'today: [[%s.today]]\nyesterday (%s): %s\n' "$PREP_DATE" "$yesterday" \
  "$(extensions/intraday/scripts/today_log.py summary "$yesterday")"
# The session and route lines of yesterday's month and this one's (the same file twice within a month). The last
# tick is judged whole: its first failing line, if any (#302). A line from before ticks were named is its own tick.
lines="$(cat "system/logs/watch_fetch-${yesterday:0:7}.jsonl" "system/logs/watch_fetch-${PREP_DATE:0:7}.jsonl" 2>/dev/null \
  | jq -cR 'fromjson? | select(.step != "tick")')" || true
last="$(tail -n 1 <<< "$lines")"
if [[ -z "$last" ]]; then
  prep_source watch off
else
  bad="$(jq -c --argjson l "$last" 'select(if $l.tick then .tick == $l.tick else . == $l end) | select(.exit != 0)' \
    <<< "$lines" | head -n 1)" || true
  if [[ -z "$bad" ]]; then prep_source watch ok; else prep_source watch failed "$(jq -r .reason <<< "$bad")"; fi
fi
exit 0
