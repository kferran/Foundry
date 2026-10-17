#!/bin/bash
# Transcript keep (#166): on PreCompact and SessionEnd, copy the session's transcript outside the vault, so a digest
# the Stop hook missed can be recovered from it later. A copy never shrinks. Never fails or blocks the session.
[[ "${FOUNDRY_HEADLESS:-}" == 1 ]] && exit 0
set -uo pipefail
# shellcheck source=lib_memory.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_memory.sh"

MARKER=.foundry-keep  # written when the hook creates the keep directory; the prune runs only where it is
tmp=""
trap 'rm -f -- "$tmp"' EXIT TERM HUP

refuse() { mem_log "keep: $1"; return 1; }

keep_dir() {  # print the resolved keep directory, creating it (700, with the marker) when absent
  local dir home
  dir="$(_mem_vi field system/config.md transcript_keep_dir 2>/dev/null)" || dir=""
  [[ -n "$dir" ]] || dir="${XDG_STATE_HOME:-$HOME/.local/state}/foundry/transcripts"
  [[ "$dir" == "~" || "$dir" == "~/"* ]] && dir="$HOME${dir#\~}"
  [[ "$dir" == /* ]] || { refuse "transcript_keep_dir is not an absolute path: $dir"; return 1; }
  dir="$(realpath -m -- "$dir")" || return 1
  home="$(realpath -m -- "$HOME")" || return 1
  # A copy inside the vault could be committed and pushed; / or $HOME would put the prune among the owner's files.
  if [[ "$dir" == / || "$dir" == "$home" || "$dir" == "$MEM_VAULT" || "$dir" == "$MEM_VAULT"/* ]]; then
    refuse "transcript_keep_dir $dir is refused (/, the home directory or inside the vault)"
    return 1
  fi
  if [[ ! -e "$dir" ]]; then
    ( umask 077; mkdir -p -- "$dir" ) || return 1
    chmod 700 -- "$dir"
    : > "$dir/$MARKER"
  fi
  [[ -d "$dir" && -O "$dir" ]] || { refuse "transcript_keep_dir $dir is not a directory you own"; return 1; }
  (( (8#$(stat -c %a -- "$dir")) & 8#022 )) && { refuse "transcript_keep_dir $dir is writable by others"; return 1; }
  printf '%s\n' "$dir"
}

prune() {  # prune <dir>: session copies not refreshed for transcript_keep_days days (default 90; 0 keeps them all)
  local days
  [[ -f "$1/$MARKER" ]] || return 0
  days="$(_mem_vi field system/config.md transcript_keep_days 2>/dev/null)" || days=90
  [[ "$days" =~ ^[0-9]+$ ]] || days=90
  (( days > 0 )) || return 0
  # Only session-id names, only at the top: no recursion, and -type f never matches a symlink (find does not follow them).
  timeout 5 find "$1" -maxdepth 1 -type f -name '????????-????-????-????-????????????.jsonl' -mtime "+$days" -delete 2>/dev/null
}

main() {
  local input sid src projects dir dst
  input="$(timeout 2 cat)"  # Claude Code closes stdin; a stdin left open never holds the session
  sid="$(jq -r '.session_id // empty' <<< "$input" 2>/dev/null)"
  mem_valid_sid "$sid" || return 0
  # A subagent's event carries the parent's session_id beside its own transcript, which must not take the copy's name.
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  [[ -e "$MEM_SESSIONS/$sid.json" ]] || return 0  # only sessions the memory hooks froze in scope
  projects="$(realpath -m -- "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects")" || return 0
  src="$(jq -r '.transcript_path // empty' <<< "$input")"
  src="$(realpath -e -- "$src" 2>/dev/null)" || { mem_log "keep: no transcript for $sid"; return 0; }
  [[ "$src" == "$projects"/* && -f "$src" ]] || { mem_log "keep: transcript for $sid is outside $projects"; return 0; }
  dir="$(keep_dir)" || return 0
  dst="$dir/$sid.jsonl"
  if [[ -f "$dst" ]] && (( $(stat -c %s -- "$dst") > $(stat -c %s -- "$src") )); then
    :  # a larger copy is kept as it is
  elif ! { tmp="$(mktemp -- "$dir/.$sid.XXXXXX")" && timeout 20 cp -- "$src" "$tmp" && mv -f -- "$tmp" "$dst"; }; then
    mem_log "keep: could not copy the transcript for $sid"
  fi
  prune "$dir"
}

main
exit 0
