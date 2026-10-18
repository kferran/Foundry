#!/bin/bash
# Ingest evals (ingest evals spec §3.2): each golden case runs through one real intake tick in a throwaway vault,
# N times, scored by eval_check.py. Not gating: the owner runs it after a change to ingest.md, run_headless.sh, the
# headless settings, the intake's staging or the claude version. Uses CLAUDE_BIN as the units do, never a stub.
# Usage: eval_ingest.sh [--case <name>]… [--runs N] [--max-usd D] [--local]
# Exit 0 when every case meets its min_pass_rate, 1 when one does not or was skipped (budget), 2 on usage.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

usage() { echo "usage: eval_ingest.sh [--case <name>]… [--runs N] [--max-usd D] [--local]" >&2; exit 2; }
runs=3 max_usd=5 local=0 cases=()
while (( $# )); do
  case "$1" in
    --case) [[ $# -ge 2 ]] || usage; cases+=("$2"); shift 2 ;;
    --runs) [[ "${2:-}" =~ ^[1-9][0-9]*$ ]] || usage; runs="$2"; shift 2 ;;
    --max-usd) [[ "${2:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || usage; max_usd="$2"; shift 2 ;;
    --local) local=1; shift ;;
    *) usage ;;
  esac
done

roots=(system/tests/golden/ingest)
(( local )) && roots+=(system/tests/golden/local)
dirs=()
for root in "${roots[@]}"; do
  for d in "$root"/*/; do
    [[ -d "$d" ]] || continue
    name="$(basename "$d")"
    if (( ${#cases[@]} )) && [[ " ${cases[*]} " != *" $name "* ]]; then continue; fi
    [[ -f "$d/expect.yaml" ]] || { echo "eval_ingest: case $name has no expect.yaml" >&2; exit 2; }
    dirs+=("${d%/}")
  done
done
(( ${#dirs[@]} )) || { echo "eval_ingest: no case to run" >&2; exit 2; }

log="system/logs/evals/ingest-$(date +%Y-%m).jsonl"
session="$(mktemp)"
mkdir -p system/logs/evals
spent=0

build_vault() {  # <dir>: a runnable vault, as system/tests/helpers.bash's make_vault builds one
  local v="$1"
  cp -r system/tests/fixtures/vault "$v"
  mkdir -p "$v/system/scripts" "$v/.claude"
  cp -r system/schemas system/templates "$v/system/"
  cp -r system/scripts/. "$v/system/scripts/"
  find "$v/system/scripts" -name __pycache__ -prune -exec rm -rf {} +
  cp CLAUDE.md "$v/CLAUDE.md"
  cp -r .claude/commands "$v/.claude/commands"
  [[ -f system/headless.settings.json ]] && cp system/headless.settings.json "$v/system/"
  [[ -f .claude/settings.json ]] && cp .claude/settings.json "$v/.claude/"
  printf -- '---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\nremote_mode: "none"\ndefault_partition: "work"\n---\n' > "$v/system/config.md"
  git -C "$v" init -q
  git -C "$v" config user.email eval@example.com
  git -C "$v" config user.name eval
}

record() {  # <json object>: one line to the month's log and to this session's summary
  printf '%s\n' "$1" | tee -a "$log" >> "$session"
}

for dir in "${dirs[@]}"; do
  name="$(basename "$dir")"
  rate="$(system/scripts/eval_check.py rate "$dir/expect.yaml")"
  for (( n = 1; n <= runs; n++ )); do
    if awk -v s="$spent" -v m="$max_usd" 'BEGIN { exit !(s >= m) }'; then
      record "$(jq -cn --arg c "$name" --argjson r "$n" --argjson rate "$rate" \
        '{time: (now | todate), case: $c, repeat: $r, min_pass_rate: $rate, skipped: true}')"
      continue
    fi
    tmp="$(mktemp -d)"
    v="$tmp/vault"
    build_vault "$v"
    [[ -d "$dir/vault" ]] && cp -r "$dir/vault/." "$v/"
    mkdir -p "$v/raw/inbox"
    [[ -d "$dir/inputs/inbox" ]] && cp -r "$dir/inputs/inbox/." "$v/raw/inbox/"
    if [[ -d "$dir/inputs/notes" ]]; then
      for p in "$dir"/inputs/notes/*/; do
        mkdir -p "$v/raw/$(basename "$p")/notes"
        cp -r "$p." "$v/raw/$(basename "$p")/notes/"
      done
    fi
    if [[ -f "$dir/make_input.py" ]]; then  # exit 3: this machine cannot run the case (its stdout says why)
      mrc=0
      reason="$(python3 -I "$dir/make_input.py" "$v/raw/inbox")" || mrc=$?
      if (( mrc == 3 )); then
        record "$(jq -cn --arg c "$name" --argjson r "$n" --argjson rate "$rate" --arg why "$reason" \
          '{time: (now | todate), case: $c, repeat: $r, min_pass_rate: $rate, skipped: true, reason: $why}')"
        rm -rf "$tmp"
        continue
      fi
      (( mrc == 0 )) || { echo "eval_ingest: case $name: make_input.py failed (exit $mrc)" >&2; rm -rf "$tmp"; exit 2; }
    fi
    find "$v/raw" -type f -exec touch -d '10 minutes ago' {} +   # past the intake's fresh-file wait
    (cd "$v" && system/scripts/vault_index.py rebuild >/dev/null)
    mkdir -p "$v/system/logs/runs"
    before="$(ls "$v/system/logs/runs")"
    rc=0
    (cd "$v" && system/scripts/intake.py) > "$tmp/intake.log" 2>&1 || rc=$?
    mapfile -t ids < <(comm -13 <(printf '%s\n' "$before" | sort) <(ls "$v/system/logs/runs" | sort) | grep -v '^$' || true)
    failed="$(system/scripts/eval_check.py check "$v" "$dir/expect.yaml" "$dir/vault" "${ids[@]}" || true)"
    if ls "$v"/system/logs/.intake-held-* >/dev/null 2>&1; then failed="held: the usage ceiling held the tick"$'\n'"$failed"; fi
    cost="$(system/scripts/eval_check.py cost "$v" "${ids[@]}")"
    spent="$(awk -v s="$spent" -v c="$cost" 'BEGIN { print s + c }')"
    publish="$(for id in "${ids[@]}"; do jq -r .status "$v/system/logs/runs/$id/publish.json" 2>/dev/null || echo missing; done)"
    record "$(jq -cn --arg c "$name" --argjson r "$n" --argjson rate "$rate" --argjson exit "$rc" --argjson cost "$cost" \
      --arg ids "${ids[*]:-}" --arg pub "$publish" --arg failed "$failed" \
      '{time: (now | todate), case: $c, repeat: $r, min_pass_rate: $rate, exit: $exit, cost: $cost,
        run_ids: ($ids | split(" ") | map(select(. != ""))), publish: ($pub | split("\n") | map(select(. != ""))),
        failed: ($failed | split("\n") | map(select(. != "")))}')"
    rm -rf "$tmp"
  done
done

rc=0
system/scripts/eval_check.py summary "$session" || rc=$?
rm -f "$session"
exit "$rc"
