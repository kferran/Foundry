#!/bin/bash
# Wheeljack's harness: the only way automation invokes claude (spec §6.3).
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
LOCK_WAIT="${HEADLESS_LOCK_WAIT:-600}"
TZ="$(config_get timezone UTC)"
export TZ JARVIS_HEADLESS=1
TODAY="$(date +%F)"
LEDGER="system/logs/runs-$(date +%Y-%m).jsonl"
mkdir -p system/logs/headless system/logs/runs

die() { echo "run_headless: $2" >&2; exit "$1"; }
alert() { printf -- '- %s [wheeljack] %s\n' "$(date +%H:%M:%S)" "$1" >> "system/logs/alerts_${TODAY}.md"; }
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

inputs=() partition=""
if [[ "$cmd" == ingest ]]; then
  (( $# >= 1 && $# <= 5 )) || die 2 "ingest takes 1-5 raw paths"
  for arg in "$@"; do
    relpath="$(args_vault_path "$arg")" || die 2 "not a file inside the vault: $arg"
    case "$relpath" in
      raw/inbox/.staging/*) p="$(input_partition "$relpath")" ;;
      raw/work/notes/*|raw/personal/notes/*|raw/shared/notes/*) p="${relpath#raw/}"; p="${p%%/*}" ;;
      *) die 2 "not an ingestible raw path: $relpath" ;;
    esac
    [[ -z "$partition" || "$partition" == "$p" ]] || die 2 "inputs span partitions ($partition, $p)"
    partition="$p"
    inputs+=("$relpath")
  done
else
  (( $# == 0 )) || die 2 "$cmd takes no arguments"
fi

if ! jq empty system/headless.settings.json 2>/dev/null; then
  alert "system/headless.settings.json is missing or invalid; $cmd not run"
  die 3 "invalid system/headless.settings.json"
fi

exec 9>system/run.lock
if [[ "$cmd" == ingest ]]; then
  flock 9
elif ! flock -w "$LOCK_WAIT" 9; then
  alert "$cmd skipped: run.lock busy for ${LOCK_WAIT}s"
  die 6 "run.lock busy"
fi

system/scripts/publish_staged.py recover >> "$LOG" 2>&1 || true

runs_today=0
if [[ -f "$LEDGER" ]]; then
  runs_today="$(jq -R --arg d "$TODAY" 'fromjson? | select(.command != "retry" and ((.started_at // "") | startswith($d))) | 1' "$LEDGER" | wc -l)"
fi
if (( runs_today >= MAX_PER_DAY )); then
  marker="system/logs/.cap-alerted-$TODAY"
  [[ -e "$marker" ]] || { alert "daily headless cap ($MAX_PER_DAY) reached; inputs left in place"; : > "$marker"; }
  die 4 "daily cap reached"
fi

run_id="$(date +%Y%m%dT%H%M%S)-$cmd-$(od -An -N2 -tx1 /dev/urandom | tr -d ' \n')"
case "$cmd" in
  ingest) if [[ "$partition" == shared ]]; then targets=("wiki/shared/**"); else targets=("wiki/$partition/**" "wiki/shared/**"); fi ;;
  brief) targets=("briefings/$TODAY.md") ;;
  debrief) targets=("briefings/$TODAY.debrief.md") ;;
esac
started="$(date -Iseconds)"
system/scripts/publish_staged.py snapshot "$run_id" --targets "${targets[@]}" >/dev/null

cmdfile=".claude/commands/$cmd.md"
[[ -f "$cmdfile" ]] || die 2 "missing $cmdfile"
body="$(awk 'NR==1 && $0=="---" {fm=1; next} fm && $0=="---" {fm=0; next} !fm' "$cmdfile")"
argstr="$run_id"
(( ${#inputs[@]} )) && argstr="$run_id ${inputs[*]}"
prompt="${body//\$ARGUMENTS/$argstr}"

vi="system/scripts/vault_index.py"
allow=("Edit(/wiki/.staging/$run_id/**)")
for sub in query related show backlinks orphans issues validate field stage; do allow+=("Bash($vi $sub:*)"); done

out="system/logs/runs/$run_id/claude.json"
printf '\n===== %s %s %s\n' "$(date -Iseconds)" "$run_id" "${inputs[*]:-}" >> "$LOG"
set +e
timeout "$TIMEOUT" "$CLAUDE_BIN" -p "$prompt" --append-system-prompt-file CLAUDE.md \
  --restricted --settings system/headless.settings.json --strict-mcp-config --no-session-persistence \
  --permission-mode dontAsk --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" \
  --allowedTools "${allow[@]}" < /dev/null > "$out" 2>> "$LOG"
rc=$?
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

shas=()
if [[ -n "${JARVIS_ORIGINAL_SHA256:-}" ]]; then
  read -r -a shas <<< "$JARVIS_ORIGINAL_SHA256"
else
  for f in "${inputs[@]}"; do shas+=("$(sha256sum -- "$f" | cut -d' ' -f1)"); done
fi
attempt=1
if (( ${#shas[@]} )); then
  prev="system/logs/runs-$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m).jsonl"
  failures="$( { cat "$prev" "$LEDGER" 2>/dev/null || true; } | jq -R --argjson s "$(json_list "${shas[@]}")" \
    'fromjson? | select(.command != "retry" and (.exit // 0) != 0 and (.exit // 0) != 4 and ([.input_sha256[]?] | any(. as $x | $s | index($x)))) | 1' | wc -l)"
  attempt=$(( failures + 1 ))
fi
pubsum="$(jq -c '{status, published: (.published // []), rejected: ([(.problems // [])[].path] | unique), conflicts: (.conflicts // [])}' \
  "system/logs/runs/$run_id/publish.json" 2>/dev/null || echo '{}')"
jq -cn --arg run_id "$run_id" --arg command "$cmd" --arg started "$started" --arg finished "$(date -Iseconds)" \
  --argjson inputs "$(json_list "${inputs[@]}")" --argjson shas "$(json_list "${shas[@]}")" \
  --arg partition "$partition" --argjson exit "$rc" --argjson publish "$pubsum" \
  --argjson attempt "$attempt" --argjson denials "$denials" \
  '{run_id:$run_id, command:$command, started_at:$started, finished_at:$finished, inputs:$inputs,
    input_sha256:$shas, partition:(if $partition == "" then null else $partition end), exit:$exit,
    publish:$publish, attempt:$attempt, warnings:{permission_denials:$denials}}' >> "$LEDGER"
exit "$rc"
