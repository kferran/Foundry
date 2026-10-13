#!/bin/bash
# Smoke check (smoke check spec §3.1): every configured fetch's check mode and the claude version, one line per
# source (ok, failed: <reason>, off), one [smoke] alert a day per failure, logged to system/logs/smoke-<YYYY-MM>.jsonl.
# Runs daily from foundry-smoke.timer, 15 minutes before the brief, on a server or standalone machine.
# Exit: 0 every configured source passed, 1 a source failed, 2 usage.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh

(( $# == 0 )) || { echo "usage: smoke_check.sh" >&2; exit 2; }
case "$(config_get machine_role standalone)" in
  server|standalone) ;;
  *) echo "client: no checks"; exit 0 ;;
esac
TZ="$(config_get timezone UTC)"
export TZ
mkdir -p system/logs
log="system/logs/smoke-$(date +%Y-%m).jsonl"
failed=0

logline() {  # <source> <exit> <reason>
  jq -cn --arg time "$(date -Iseconds)" --arg source "$1" --argjson exit "$2" --arg reason "$3" \
    '{time: $time, source: $source, exit: $exit, reason: $reason}' >> "$log"
}
alert_once() {  # <key> <text>: at most one alert a day per key
  local f="system/logs/alerts_$(date +%F).md"
  grep -qF -- "[smoke] $1" "$f" 2>/dev/null || printf -- '- %s [smoke] %s %s\n' "$(date +%H:%M:%S)" "$1" "$2" >> "$f"
}
report() {  # <source> <exit> <reason>: print the line, log it, alert a failure
  logline "$1" "$2" "$3"
  if (( $2 == 0 )); then
    echo "$1: ok"
  else
    echo "$1: failed: $3"
    alert_once "$1" "failed: $3 (see $log)"
    failed=1
  fi
}
# check <source> <timeout> <command…>: run the command under timeout with both streams captured; the reason is the
# last non-empty line of its output without the script's own prefix.
check() {
  local source="$1" t="$2" rc=0 reason
  shift 2
  timeout "$t" "$@" > "$out" 2>&1 || rc=$?
  reason="$(last_line)"
  (( rc != 124 )) || reason="timed out after ${t}s"
  report "$source" "$rc" "$reason"
}
last_line() { awk 'NF { l = $0 } END { print l }' "$out" | sed -E 's/^[a-z_]+: //'; }
out="$(mktemp)"
trap 'rm -f -- "$out"' EXIT

# The claude version: reported, never blocked. The file is written when absent, so a first run is silent.
vfile=system/logs/claude.version
claude_bin="${CLAUDE_BIN:-claude}"
vrc=0
current="$(timeout "${SMOKE_VERSION_TIMEOUT:-30}" "$claude_bin" --version 2>&1 | head -n 1)" || vrc=$?
if (( vrc != 0 )) || [[ -z "$current" ]]; then
  report version 1 "claude --version failed (exit $vrc): ${current:-no output}"
else
  recorded="$(cat "$vfile" 2>/dev/null || true)"
  if [[ -n "$recorded" && "$recorded" != "$current" ]]; then
    logline version 1 "claude $recorded -> $current"
    echo "version: failed: claude $recorded -> $current"
    alert_once version "claude $recorded -> $current; re-run the acceptance steps (FOUNDRY.md Development)"
    failed=1
  else
    report version 0 ""
  fi
  printf '%s\n' "$current" > "$vfile"
fi

check calendar "${SMOKE_CALENDAR_TIMEOUT:-210}" system/scripts/calendar_fetch.sh --check
if [[ "$(config_get meetings_enabled false)" == true ]]; then
  check meetings "${SMOKE_MEETINGS_TIMEOUT:-210}" system/scripts/meetings_fetch.sh --check
else echo "meetings: off"; fi
if [[ -n "$(config_get handoffs_projects "")" ]]; then
  check handoffs "${SMOKE_HANDOFFS_TIMEOUT:-360}" system/scripts/jira_fetch.sh --check
else echo "handoffs: off"; fi
if [[ "$(config_get triage_enabled false)" == true ]]; then
  check triage "${SMOKE_TRIAGE_TIMEOUT:-360}" system/scripts/triage_fetch.sh --check
else echo "triage: off"; fi
# A source list that fails decides nothing (audit C5): it is a failed source, never "no source".
lrc=0
sources="$(timeout "${SMOKE_TELEMETRY_TIMEOUT:-120}" system/scripts/telemetry_fetch.py --list 2>&1)" || lrc=$?
if (( lrc != 0 )); then
  report telemetry "$lrc" "telemetry_fetch.py --list failed (exit $lrc): $(tail -n 1 <<< "$sources")"
elif [[ -z "$sources" ]]; then
  echo "telemetry: off"
else
  trc=0 treason=""
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    rc=0
    timeout "${SMOKE_TELEMETRY_TIMEOUT:-120}" system/scripts/telemetry_fetch.py --check "$name" > "$out" 2>&1 || rc=$?
    (( rc == 0 )) || { trc=$rc; treason="$(last_line)"; }
    (( rc != 124 )) || treason="$name: timed out after ${SMOKE_TELEMETRY_TIMEOUT:-120}s"
  done <<< "$sources"
  report telemetry "$trc" "$treason"
fi
if [[ -f system/dtcc/map.yaml ]]; then
  check dtcc "${SMOKE_DTCC_TIMEOUT:-60}" system/scripts/dtcc_watch.py --check
else echo "dtcc: off"; fi

exit "$failed"
