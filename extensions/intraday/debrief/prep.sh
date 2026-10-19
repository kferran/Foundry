# Open from today (phase D spec §3.9, #94 B8): the day's watch items by kind and the Now lines the watch added today
# that are still open. Sourced by debrief_prep.sh in a subshell, from the vault root, with PREP_DATE, PREP_DIR,
# SECTIONS and the prep_* functions.
{
  printf 'logged: %s\n' "$(extensions/intraday/scripts/today_log.py summary "$PREP_DATE")"
  extensions/intraday/scripts/today_log.py open "$PREP_DATE"
} > "$SECTIONS/intraday.md"
