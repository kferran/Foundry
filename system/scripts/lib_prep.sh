# shellcheck shell=bash
# Shared setup for brief_prep.sh and debrief_prep.sh (spec §6.5). Source after lib_args.sh and
# lib_config.sh, from VAULT_ROOT. prep_init sets TZ, PREP_DATE and PREP_DIR.

prep_init() {  # <script name> [date]
  PREP_NAME="$1"
  shift
  TZ="$(config_get timezone UTC)"
  export TZ
  if (( $# > 1 )); then echo "usage: $PREP_NAME.sh [YYYY-MM-DD]" >&2; exit 2; fi
  PREP_DATE="${1:-$(date +%F)}"
  args_date "$PREP_DATE" || { echo "$PREP_NAME: invalid date: $PREP_DATE" >&2; exit 2; }
  PREP_DIR="system/logs/inputs/$PREP_DATE"
  mkdir -p "$PREP_DIR"
  # Each script owns the unavailable.md lines that carry its name, so re-running one script
  # replaces its own lines and never erases the other's.
  local u="$PREP_DIR/unavailable.md"
  if [[ -f "$u" ]]; then
    grep -v -F -- "- $PREP_NAME: " "$u" > "$u.tmp" || true
    mv -f -- "$u.tmp" "$u"
  fi
}

prep_unavailable() { printf -- '- %s: %s\n' "$PREP_NAME" "$1" >> "$PREP_DIR/unavailable.md"; }

# prep_source <source> <ok|off|failed> [reason]: what this run read itself, for sources.py report (connector health
# spec §2). The file is the run's own: prep_sources_init empties it.
prep_sources_init() { : > "$PREP_DIR/sources.given"; }
prep_source() { printf '%s\t%s\t%s\n' "$1" "$2" "${3:-}" >> "$PREP_DIR/sources.given"; }

# prep_reason <script name> <exit>: the script's last "<name>: …" line in prep_errors.log without that prefix (its
# class leads it), else the exit.
prep_reason() {
  local r
  r="$(sed -n "s/^$1: //p" "$PREP_DIR/prep_errors.log" 2>/dev/null | tail -n 1)"
  printf '%s\n' "${r:-other: $1 exited $2}"
}

# prep_meetings: an unavailable line when the last Google Drive search of the day (meetings_fetch.sh) failed; with
# a search today, its reading for the Sources line.
prep_meetings() {
  local log="system/logs/meetings_fetch-${PREP_DATE:0:7}.jsonl" last
  [[ -f "$log" ]] || return 0
  last="$(jq -cR --arg d "$PREP_DATE" 'fromjson? | select(.step == "search" and ((.time // "") | startswith($d)))' "$log" | tail -n 1)"
  [[ -n "$last" ]] || return 0
  if [[ "$(jq -r .exit <<< "$last")" == 0 ]]; then
    [[ "$PREP_NAME" != brief_prep ]] || prep_source meetings ok
    return 0
  fi
  [[ "$PREP_NAME" != brief_prep ]] || prep_source meetings failed "$(jq -r .reason <<< "$last")"
  prep_unavailable "meetings: the last Google Drive search today failed (exit $(jq -r '"\(.exit): \(.reason)"' <<< "$last"))"
}

# prep_write <file> <command…>: run the command into $PREP_DIR/<file>, replacing it only on success,
# so a failed source never leaves a partial file behind. Returns the command's status.
prep_write() {
  local f="$PREP_DIR/$1" rc=0
  shift
  "$@" > "$f.tmp" 2>> "$PREP_DIR/prep_errors.log" || rc=$?
  if (( rc == 0 )); then mv -f -- "$f.tmp" "$f"; else rm -f -- "$f.tmp"; fi
  return "$rc"
}
