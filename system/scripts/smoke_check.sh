#!/bin/bash
# Smoke check (smoke check spec §3.1): every configured fetch's check mode and the claude version, one line per
# source (ok, failed: <reason>, held: <reading>, off), one [smoke] alert a day per failure, logged to
# system/logs/smoke-<YYYY-MM>.jsonl. Runs daily from foundry-smoke.timer, 15 minutes before the brief, on a server
# or standalone machine. At the usage ceiling the connector checks are held; the local checks still run.
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
out="$(mktemp)"
trap 'rm -f -- "$out"' EXIT

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
# reason <script>: the script's own last "<name>: …" line from $out without that prefix, else the last non-empty
# line (the Python checks print "stale: …" or "<source>: …" and keep that word).
reason() {
  local p
  p="$(basename "$1")" p="${p%.*}"
  awk -v p="$p: " 'index($0, p) == 1 { own = substr($0, length(p) + 1) } NF { last = $0 } END { print (own != "" ? own : last) }' "$out"
}
# check <source> <timeout> <command…>: run the command under timeout with both streams captured. A check that says
# nothing did not run (a lost lock, a wrong gate), so exit 0 with no output is a failure.
check() {
  local source="$1" t="$2" rc=0 r
  shift 2
  timeout "$t" "$@" > "$out" 2>&1 < /dev/null || rc=$?
  r="$(reason "$1")"
  if (( rc == 124 )); then r="timed out after ${t}s"
  elif (( rc == 0 )) && [[ -z "$r" ]]; then rc=1 r="no output"; fi
  report "$source" "$rc" "$r"
}

# The claude version: reported, never blocked. The file is written when absent, so a first run is silent; an older
# vault's claude_version (the health suite's old name) is taken over first.
vfile=system/logs/claude.version
[[ -e "$vfile" || ! -e system/logs/claude_version ]] || mv -- system/logs/claude_version "$vfile"
claude_bin="${CLAUDE_BIN:-claude}"
vrc=0
# stdout only, first line: the reading system_health.bats records, so the two writers never flip the file.
vout="$(timeout "${SMOKE_VERSION_TIMEOUT:-30}" "$claude_bin" --version 2> "$out" < /dev/null)" || vrc=$?
current="${vout%%$'\n'*}"
if (( vrc != 0 )) || [[ -z "$current" ]]; then
  r="$(reason "$claude_bin")"
  report version 1 "claude --version failed (exit $vrc): ${r:-no output}"
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

# The usage ceiling (usage ceiling spec): no connector session starts while the 5-hour reading is at or above
# order_max_five_hour. The checks that start no model session still run.
held="$(system/scripts/triage.py hold 2>/dev/null || true)"
[[ -z "$held" ]] || alert_once held: "$held; the connector checks did not run"
# connector <source> <timeout> <command…>: a connector check, or its held line.
connector() {
  if [[ -n "$held" ]]; then
    logline "$1" 0 "held: $held"
    echo "$1: held: $held"
  else
    check "$@"
  fi
}

connector calendar "${SMOKE_CALENDAR_TIMEOUT:-210}" system/scripts/calendar_fetch.sh --check
if [[ "$(config_get meetings_enabled false)" == true ]]; then
  connector meetings "${SMOKE_MEETINGS_TIMEOUT:-210}" system/scripts/meetings_fetch.sh --check
else echo "meetings: off"; fi
if [[ -n "$(config_get handoffs_projects "")" ]]; then
  connector handoffs "${SMOKE_HANDOFFS_TIMEOUT:-360}" system/scripts/jira_fetch.sh --check
else echo "handoffs: off"; fi
if [[ "$(config_get triage_enabled false)" == true ]]; then
  connector triage "${SMOKE_TRIAGE_TIMEOUT:-360}" system/scripts/triage_fetch.sh --check
else echo "triage: off"; fi
# A source list that fails decides nothing (audit C5): it is a failed source, never "no source".
lrc=0 tt="${SMOKE_TELEMETRY_TIMEOUT:-120}"
sources="$(timeout "$tt" system/scripts/telemetry_fetch.py --list 2> "$out" < /dev/null)" || lrc=$?
if (( lrc != 0 )); then
  report telemetry "$lrc" "telemetry_fetch.py --list failed (exit $lrc): $(reason telemetry_fetch.py)"
elif [[ -z "$sources" ]]; then
  echo "telemetry: off"
else
  trc=0 treason=""
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    rc=0
    timeout "$tt" system/scripts/telemetry_fetch.py --check "$name" > "$out" 2>&1 < /dev/null || rc=$?
    (( rc != 0 )) || continue
    trc=$rc
    if (( rc == 124 )); then r="$name: timed out after ${tt}s"; else r="$(reason telemetry_fetch.py)"; fi
    treason="${treason:+$treason; }$r"
  done <<< "$sources"
  report telemetry "$trc" "$treason"
fi
if [[ -f system/dtcc/map.yaml ]]; then
  check dtcc "${SMOKE_DTCC_TIMEOUT:-60}" system/scripts/dtcc_watch.py --check
else echo "dtcc: off"; fi

exit "$failed"
