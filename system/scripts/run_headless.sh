#!/bin/bash
# Headless harness: the only way automation invokes claude (spec §6.3).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_args.sh
source system/scripts/lib_args.sh
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
MAX_PER_DAY="${HEADLESS_MAX_RUNS_PER_DAY:-60}"
TIMEOUT="${HEADLESS_TIMEOUT:-15m}"
# brief/debrief wait for run.lock: one sync hold plus one ingest run (two-machines spec §5.4)
LOCK_WAIT="${HEADLESS_LOCK_WAIT:-1400}"
TZ="$(config_get timezone UTC)"
export TZ FOUNDRY_HEADLESS=1
# One clock reading names the run: a brief that waits past midnight for run.lock keeps its day (the run id, targets and logs agree).
RUN_TS="$(date +%Y%m%dT%H%M%S)"
TODAY="${RUN_TS:0:4}-${RUN_TS:4:2}-${RUN_TS:6:2}"
LEDGER="system/logs/runs-${RUN_TS:0:4}-${RUN_TS:4:2}.jsonl"
mkdir -p system/logs/headless system/logs/runs

die() { echo "run_headless: $2" >&2; exit "$1"; }
alert() { printf -- '- %s [intake] %s\n' "$(date +%H:%M:%S)" "$1" >> "system/logs/alerts_${TODAY}.md"; }
json_list() { if (( $# )); then printf '%s\n' "$@" | jq -R . | jq -cs .; else echo '[]'; fi; }

input_partition() {
  local p
  p="$(system/scripts/vault_index.py field "$1" partition 2>/dev/null || true)"
  case "$p" in work|personal|shared) ;; *) p="$(config_get default_partition personal)" ;; esac
  printf '%s\n' "$p"
}

cmd="${1:-}"
(( $# )) && shift
case "$cmd" in ingest|brief|debrief) ;; *) die 2 "unknown command: ${cmd:-<none>}" ;; esac
LOG="system/logs/headless/${cmd}_${TODAY}.log"

inputs=() shas=() partition=""
if [[ "$cmd" == ingest ]]; then
  (( $# >= 1 && $# <= 5 )) || die 2 "ingest takes 1-5 raw paths"
  for arg in "$@"; do
    relpath="$(args_vault_path "$arg")" || die 2 "not a file inside the vault: $arg"
    args_raw_filename "${relpath##*/}" || die 2 "unsafe input filename: $relpath"
    case "$relpath" in
      raw/inbox/.staging/*) p="$(input_partition "$relpath")" ;;
      raw/work/notes/*|raw/personal/notes/*|raw/shared/notes/*) p="${relpath#raw/}"; p="${p%%/*}" ;;
      *) die 2 "not an ingestible raw path: $relpath" ;;
    esac
    [[ -z "$partition" || "$partition" == "$p" ]] || die 2 "inputs span partitions ($partition, $p)"
    partition="$p"
    inputs+=("$relpath")
    shas+=("$(sha256sum -- "$relpath" | cut -d' ' -f1)")
  done
  if [[ -n "${FOUNDRY_ORIGINAL_SHA256:-}" ]]; then
    read -r -a shas <<< "$FOUNDRY_ORIGINAL_SHA256"
    (( ${#shas[@]} == ${#inputs[@]} )) || die 2 "FOUNDRY_ORIGINAL_SHA256 has ${#shas[@]} entries for ${#inputs[@]} inputs"
  fi
else
  (( $# == 0 )) || die 2 "$cmd takes no arguments"
fi

run_id="" started="" denials=0 ledger_written=0
write_ledger() {
  local rc=$? failures attempt=1 prevname pubsum='{}'
  set +e
  trap - EXIT
  (( ledger_written )) && return 0
  ledger_written=1
  # Exit 2 means "usage error, no ledger line" and the daemon poisons on it at once. This trap is
  # armed only after validation, so a 2 here (claude, or a set -e failure in jq/awk) is a run failure.
  (( rc == 2 )) && rc=1
  [[ -n "$started" ]] || started="$(date -Iseconds)"
  if (( ${#shas[@]} )); then
    prevname="system/logs/runs-$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m).jsonl"
    failures="$( { cat "$prevname" "$LEDGER" 2>/dev/null || true; } | jq -R --argjson s "$(json_list "${shas[@]}")" \
      'fromjson? | objects | (.exit // 0) as $e | select(.command != "retry" and ([0,3,4,6,129,130,143] | index($e) | not) and ([.input_sha256[]? | strings] | any(. as $x | $s | index($x)))) | 1' | wc -l)"
    attempt=$(( failures + 1 ))
  fi
  if [[ -n "$run_id" ]]; then
    pubsum="$(jq -c '{status, published: (.published // []), rejected: ([(.problems // [])[].path] | unique), conflicts: (.conflicts // [])}' \
      "system/logs/runs/$run_id/publish.json" 2>/dev/null)"
    [[ -n "$pubsum" ]] || pubsum='{}'
  fi
  if [[ -s "$LEDGER" && -n "$(tail -c1 "$LEDGER")" ]]; then echo >> "$LEDGER"; fi
  jq -cn --arg run_id "$run_id" --arg command "$cmd" --arg started "$started" --arg finished "$(date -Iseconds)" \
    --argjson inputs "$(json_list "${inputs[@]}")" --argjson shas "$(json_list "${shas[@]}")" \
    --arg partition "$partition" --argjson exit "$rc" --argjson publish "$pubsum" \
    --argjson attempt "$attempt" --argjson denials "$denials" \
    '{run_id:(if $run_id == "" then null else $run_id end), command:$command, started_at:$started, finished_at:$finished, inputs:$inputs,
      input_sha256:$shas, partition:(if $partition == "" then null else $partition end), exit:$exit,
      publish:$publish, attempt:$attempt, warnings:{permission_denials:$denials}}' >> "$LEDGER"
  exit "$rc"
}
cpid=""
stop_child() { [[ -z "$cpid" ]] || kill -TERM "$cpid" 2>/dev/null || true; }
trap 'stop_child; exit 129' HUP
trap 'stop_child; exit 130' INT
trap 'stop_child; exit 143' TERM
trap write_ledger EXIT

if ! jq -se 'length == 1 and (.[0] | type) == "object"' system/headless.settings.json >/dev/null 2>&1; then
  alert "system/headless.settings.json is missing or invalid; $cmd not run"
  die 3 "invalid system/headless.settings.json"
fi

cmdfile=".claude/commands/$cmd.md"
if [[ ! -f "$cmdfile" ]]; then
  alert "missing $cmdfile; $cmd not run"
  die 3 "missing $cmdfile"
fi

exec 9>system/run.lock
if [[ "$cmd" == ingest ]]; then
  flock 9
elif ! flock -w "$LOCK_WAIT" 9; then
  alert "$cmd skipped: run.lock busy for ${LOCK_WAIT}s"
  die 6 "run.lock busy"
fi

set +e
recovery="$(system/scripts/publish_staged.py recover 2>> "$LOG")"
recovery_rc=$?
set -e
printf '%s\n' "$recovery" >> "$LOG"
if (( recovery_rc != 0 )); then
  alert "publish recovery failed (exit $recovery_rc); see $LOG"
else
  recovery_failed="$(jq -er '(.failed // []) | map(strings) | join(" ")' <<< "$recovery" 2>/dev/null)" \
    || recovery_failed="(unreadable recover output)"
  [[ -z "$recovery_failed" ]] || alert "publish recovery failed for run(s): $recovery_failed (see system/logs/runs/<run_id>/publish.json)"
fi

runs_today=0
if [[ -f "$LEDGER" ]]; then
  runs_today="$(jq -R --arg d "$TODAY" 'fromjson? | objects | (.exit // 0) as $e | select(.command != "retry" and ([2,3,4,6] | index($e) | not) and (((.started_at | strings) // "") | startswith($d))) | 1' "$LEDGER" | wc -l)"
fi
if (( runs_today >= MAX_PER_DAY )); then
  marker="system/logs/.cap-alerted-$TODAY"
  [[ -e "$marker" ]] || { alert "daily headless cap ($MAX_PER_DAY) reached; inputs left in place"; : > "$marker"; }
  die 4 "daily cap reached"
fi

run_id="$RUN_TS-$cmd-$(od -An -N2 -tx1 /dev/urandom | tr -d ' \n')"
case "$cmd" in
  ingest) if [[ "$partition" == shared ]]; then targets=("wiki/shared/**"); else targets=("wiki/$partition/**" "wiki/shared/**"); fi ;;
  brief) targets=("briefings/$TODAY.md") ;;
  debrief) targets=("briefings/$TODAY.debrief.md") ;;
esac
started="$(date -Iseconds)"
if ! system/scripts/publish_staged.py snapshot "$run_id" --targets "${targets[@]}" >/dev/null 2>> "$LOG"; then
  alert "$cmd $run_id: snapshot failed; claude not run (see $LOG)"
  exit 3  # vault environment error: excluded from attempts and the cap, and stops the daemon
fi

body="$(awk 'NR==1 && $0=="---" {fm=1; next} fm && $0=="---" {fm=0; next} !fm' "$cmdfile")"
# $ARGUMENTS: the run id on the first line, then one input per line (a raw filename may contain spaces).
argstr="$run_id"
(( ${#inputs[@]} )) && argstr="$run_id"$'\n'"$(printf '%s\n' "${inputs[@]}")"
shopt -u patsub_replacement 2>/dev/null || true
prompt="${body//\$ARGUMENTS/$argstr}"

vi="system/scripts/vault_index.py"
allow=("Edit(/wiki/.staging/$run_id/**)")
for sub in query related show backlinks orphans issues validate field stage; do allow+=("Bash($vi $sub:*)"); done

out="system/logs/runs/$run_id/claude.json"
printf '\n===== %s %s %s\n' "$(date -Iseconds)" "$run_id" "${inputs[*]:-}" >> "$LOG"
set +e
# 9>&-: claude's process tree must not inherit run.lock, or a leaked child holds it forever
timeout -k 30s "$TIMEOUT" "$CLAUDE_BIN" -p "$prompt" --append-system-prompt-file CLAUDE.md \
  --restricted --settings system/headless.settings.json --strict-mcp-config --no-session-persistence \
  --permission-mode dontAsk --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" \
  --allowedTools "${allow[@]}" < /dev/null > "$out" 2>> "$LOG" 9>&- &
cpid=$!
wait "$cpid"
rc=$?
cpid=""
set -e
denials="$(jq -r '(.permission_denials // []) | length' "$out" 2>/dev/null || true)"
[[ "$denials" =~ ^[0-9]+$ ]] || denials=0

if (( rc == 0 )); then
  set +e
  system/scripts/publish_staged.py commit "$run_id" >> "$LOG" 2>&1
  prc=$?
  set -e
  if (( prc != 0 )); then
    rc=5
    alert "$cmd $run_id: publish rejected or empty (system/logs/runs/$run_id/publish.json)"
  fi
else
  system/scripts/publish_staged.py abort "$run_id" >> "$LOG" 2>&1 || true
  alert "$cmd $run_id failed (exit $rc)"
fi

exit "$rc"
