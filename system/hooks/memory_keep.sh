#!/bin/bash
# Transcript keep (#166): on PreCompact and SessionEnd, copy the session's transcript outside the vault, so a digest
# the Stop hook missed can be recovered from it later. A copy never shrinks. Never fails or blocks the session.
[[ "${FOUNDRY_HEADLESS:-}" == 1 ]] && exit 0
set -uo pipefail
# shellcheck source=lib_memory.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_memory.sh"

main() {
  local input sid src dir dst tmp
  input="$(timeout 2 cat)"  # Claude Code closes stdin; a stdin left open never holds the session
  sid="$(jq -r '.session_id // empty' <<< "$input" 2>/dev/null)"
  mem_valid_sid "$sid" || return 0
  # A subagent's event carries the parent's session_id beside its own transcript, which must not take the copy's name.
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  [[ -e "$MEM_SESSIONS/$sid.json" ]] || return 0  # only sessions the memory hooks froze in scope
  src="$(jq -r '.transcript_path // empty' <<< "$input")"
  [[ -f "$src" && ! -L "$src" ]] || { mem_log "keep: no transcript for $sid"; return 0; }
  dir="$(_mem_vi field system/config.md transcript_keep_dir 2>/dev/null)" || dir=""
  [[ -n "$dir" ]] || dir="${XDG_STATE_HOME:-$HOME/.local/state}/foundry/transcripts"
  [[ "$dir" == "~/"* ]] && dir="$HOME/${dir#\~/}"
  [[ "$dir" == /* ]] || { mem_log "keep: transcript_keep_dir is not an absolute path: $dir"; return 0; }
  ( umask 077; mkdir -p -- "$dir" ) && dir="$(realpath -e -- "$dir")" || return 0
  # A copy inside the vault could be committed and pushed with whatever secrets the session saw.
  [[ "$dir" != "$MEM_VAULT" && "$dir" != "$MEM_VAULT"/* ]] \
    || { mem_log "keep: transcript_keep_dir is inside the vault; nothing copied"; return 0; }
  dst="$dir/$sid.jsonl" tmp="$dir/.$sid.jsonl.tmp.$$"
  [[ -f "$dst" ]] && (( $(stat -c %s -- "$dst") > $(stat -c %s -- "$src") )) && return 0
  if ( umask 077; timeout 20 cp -- "$src" "$tmp" ) && mv -f -- "$tmp" "$dst"; then return 0; fi
  rm -f -- "$tmp"
  mem_log "keep: could not copy the transcript for $sid"
}

main
exit 0
