#!/bin/bash
# Smoke check (smoke check spec §3.1): every configured fetch's check mode and the claude version, one line per
# source (ok, failed: <reason>, expired: <credential>; renew: <how>, unreachable: <host>, held: <reading>, off), one
# [smoke] alert a day per failure (per credential for an expired one), logged to
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
  local cred host since n
  logline "$1" "$2" "$3"
  if (( $2 == 0 )); then
    echo "$1: ok"
    return 0
  fi
  failed=1
  # Connector health spec §2: an expired credential is named with its renewal, one alert a day per credential; a
  # network failure names the host and alerts once it failed the same way at the previous check too.
  cred="$(system/scripts/sources.py credential "$1" "$3" 2>/dev/null || true)"
  if [[ -n "$cred" ]]; then
    echo "$1: expired: ${cred%%$'\t'*}; renew: ${cred#*$'\t'}"
    alert_once "expired ${cred%%$'\t'*}:" "renew: ${cred#*$'\t'} ($1: $3)"
  elif [[ "$3" == "network: "* ]]; then
    host="${3#network: }" host="${host%% *}"
    echo "$1: unreachable: $host"
    since="$(system/scripts/sources.py streak "$1" --class network 2>/dev/null || true)"
    n="${since%%$'\t'*}" since="${since#*$'\t'}"
    [[ "$n" =~ ^[0-9]+$ ]] || n=0
    (( n < 2 )) || alert_once "unreachable $host:" "since ${since%%$'\t'*}; check the VPN or network route to $host"
  else
    echo "$1: failed: $3"
    alert_once "$1" "failed: $3 (see $log)"
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
  # One line per source (connector health spec §2): each has its own credential and host.
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    rc=0
    timeout "$tt" system/scripts/telemetry_fetch.py --check "$name" > "$out" 2>&1 < /dev/null || rc=$?
    if (( rc == 0 )); then r=""
    elif (( rc == 124 )); then r="timeout: timed out after ${tt}s"
    else r="$(reason telemetry_fetch.py)" r="${r#"$name: "}"; fi
    report "telemetry/$name" "$rc" "$r"
  done <<< "$sources"
fi
if [[ -f system/dtcc/map.yaml ]]; then
  check dtcc "${SMOKE_DTCC_TIMEOUT:-60}" system/scripts/dtcc_watch.py --check
else echo "dtcc: off"; fi

# Timers (#166): each enabled timer this vault installed fired by its next tick after systemd's LastTrigger plus a
# grace of one interval, at most 2 hours (every template timer runs at most 15 minutes, hourly or daily apart, so
# this is one interval or 2 hours for the daily ones). A failed run is the run ledger's business, not this check's.
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
UNIT_DIR="${SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
shopt -s nullglob
for f in "$UNIT_DIR"/foundry-*.timer; do
  [[ "$(head -n 1 -- "$f")" == "# Managed by vault: $VAULT_ROOT" ]] || continue
  t="${f##*/}"
  if ! "$SYSTEMCTL" --user is-enabled --quiet "$t"; then echo "$t: off"; continue; fi
  props="$(TZ=UTC "$SYSTEMCTL" --user show -p LastTriggerUSec -p SubState "$t" 2>/dev/null || true)"
  last="$(sed -n 's/^LastTriggerUSec=//p' <<< "$props")"
  # A timer waiting on its own still-running service fired (a long intake run outlasts the 5-minute interval).
  if grep -qx SubState=running <<< "$props"; then logline "$t" 0 ""; echo "$t: ok"; continue; fi
  [[ -z "$last" ]] || last="$(date -d "$last" +%s 2>/dev/null || true)"
  cal="$(sed -n 's/^OnCalendar=//p' "$f" | head -n 1)" span="$(sed -n 's/^OnUnitActiveSec=//p' "$f" | head -n 1)"
  due="" step=""
  if [[ -z "$last" ]]; then :
  elif [[ -n "$cal" ]]; then
    mapfile -t next < <(TZ=UTC LC_ALL=C systemd-analyze calendar --iterations=2 --base-time="@$last" "$cal" 2>/dev/null \
                        | sed -n 's/^[^:]*: \([A-Z][a-z][a-z] [0-9-]* [0-9:]* UTC\)$/\1/p')
    # Only the timestamps, whatever the label: systemd 255 renamed "Iter. #2" to "Iteration #2".
    if (( ${#next[@]} == 2 )); then
      due="$(date -d "${next[0]}" +%s)" step=$(( $(date -d "${next[1]}" +%s) - due ))
    fi
  elif [[ -n "$span" ]]; then
    step="$(LC_ALL=C systemd-analyze timespan "$span" 2>/dev/null | awk '$1 == "us:" { print int($2 / 1000000) }')"
    [[ -z "$step" ]] || due=$(( last + step ))
  fi
  if [[ -z "$due" ]]; then
    logline "$t" 0 unknown
    echo "$t: unknown"
    continue
  fi
  (( step < 7200 )) || step=7200
  if (( $(date +%s) > due + step )); then
    r="stale: no run since $(date -d "@$last" '+%F %H:%M')"
    logline "$t" 1 "$r"
    echo "$t: $r"
    alert_once "$t stale:" "${r#stale: }"
    failed=1
  else
    logline "$t" 0 ""
    echo "$t: ok"
  fi
done

# Unit drift (#166): each unit and drop-in install_units.sh --dry-run renders against its installed copy. A unit not
# installed (one the owner never installed, or removed) is left out; with none installed the line reads off.
rdir="$(mktemp -d)"
trap 'rm -rf -- "$out" "$rdir"' EXIT
urc=0
timeout "${SMOKE_UNITS_TIMEOUT:-60}" system/scripts/install_units.sh --dry-run > "$rdir/all" 2> "$out" < /dev/null || urc=$?
if (( urc != 0 )); then
  report units "$urc" "install_units.sh --dry-run failed (exit $urc): $(reason install_units.sh)"
else
  # "===== <name>" opens each file; a drop-in's "/" is stored as "%".
  awk -v d="$rdir" '/^===== / { f = substr($0, 7); gsub("/", "%", f); f = d "/" f; next } { print > f }' "$rdir/all"
  installed=0 differs=0
  for r in "$rdir"/foundry-*; do
    n="${r##*/}" n="${n//%//}"
    [[ -f "$UNIT_DIR/$n" ]] || continue
    installed=1
    cmp -s -- "$r" "$UNIT_DIR/$n" && continue
    differs=1
    logline units 1 "differs: $n"
    echo "units: differs: $n"
    alert_once "$n differs:" "run system/scripts/install_units.sh --update"
  done
  if (( differs )); then failed=1
  elif (( installed )); then report units 0 ""
  else echo "units: off"; fi
fi

exit "$failed"
