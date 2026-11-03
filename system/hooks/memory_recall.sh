#!/bin/bash
# Memory SessionStart hook (spec §6.17): freeze the session's scope, then inject the recall block.
# Never fails the session: any problem is logged and the hook exits 0 with no output.
[[ "${FOUNDRY_HEADLESS:-}" == 1 ]] && exit 0
set -uo pipefail
# shellcheck source=lib_memory.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_memory.sh"

main() {
  local input sid cwd out frozen src
  input="$(cat)"
  mem_env_ok || return 0
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  sid="$(jq -r '.session_id // empty' <<< "$input")"
  mem_valid_sid "$sid" || { mem_log "SessionStart: invalid session_id"; return 0; }
  cwd="$(jq -r '.cwd // empty' <<< "$input")"
  [[ -n "$cwd" ]] || cwd="$PWD"
  mem_prune
  mem_freeze "$sid" "$cwd" || return 0
  # A re-entry (compact, resume) runs recall from the cwd frozen at first sight, never the current one.
  frozen="$(jq -r '.cwd // empty' "$MEM_SESSIONS/$sid.json" 2>/dev/null)"
  [[ -n "$frozen" && -d "$frozen" ]] && cwd="$frozen"
  src="$(jq -r '.source // empty' <<< "$input")"
  out="$(cd "$cwd" && timeout 3 "$MEM_VAULT/system/scripts/vault_index.py" recall --cwd "$cwd" --session-id "$sid" --source "$src")" || {
    mem_log "SessionStart: recall failed or timed out for ${sid:0:8}"
    # The push log's failure line (recall R0 spec §3.2); a Workcell session logs nothing.
    [[ "${FOUNDRY_WORKCELL_SESSION:-}" == 1 ]] || jq -cn --arg ts "$(date -Iseconds)" --arg s "$sid" \
      '{ts: $ts, kind: "push", session: $s, failed: true}' >> "$MEM_VAULT/system/logs/recall-$(date +%Y-%m).jsonl"
    return 0
  }
  [[ -n "$out" ]] || return 0
  jq -cn --arg c "$out" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $c}}'
}

main 2>> "$MEM_LOG"
exit 0
