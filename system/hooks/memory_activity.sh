#!/bin/bash
# Soundwave PostToolUse hook (spec §6.17): count work events for an eligible session.
# Fast path: pure bash, no jq or Python (spike item 15: one jq call alone costs ~44 ms).
[[ "${JARVIS_HEADLESS:-}" != 1 && "${CLAUDE_CODE_ENTRYPOINT:-}" == cli ]] || exit 0
[[ "${JARVIS_CREW:-}" == 1 || "${CLAUDE_CODE_SESSION_ATTENDED:-}" == 1 ]] || exit 0
input="$(cat)"  # one bulk read: `read -d ''` on a pipe goes byte by byte (1 MB ~ 900 ms)
[[ "$input" == *'"agent_id"'* ]] && exit 0  # subagent
[[ "$input" =~ \"session_id\"[[:space:]]*:[[:space:]]*\"([A-Za-z0-9-]+)\" ]] || exit 0
sid="${BASH_REMATCH[1]}"
d="${BASH_SOURCE[0]%/*}/../logs/memory/sessions"
if [[ ! -e "$d/$sid.eligible" ]]; then
  [[ -e "$d/$sid.out" ]] && exit 0
  # Hooks installed mid-session: no SessionStart ran, so freeze the scope once now (slow path).
  [[ "$input" =~ \"cwd\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] || exit 0
  cwd="${BASH_REMATCH[1]}"
  # shellcheck source=lib_memory.sh
  source "${BASH_SOURCE[0]%/*}/lib_memory.sh"
  mem_freeze "$sid" "$cwd" 2>> "$MEM_LOG" || exit 0
fi
n=0
[[ -f "$d/$sid.events" ]] && { read -r n < "$d/$sid.events" || n=0; }
[[ "$n" =~ ^[0-9]+$ ]] || n=0
printf '%d\n' $(( n + 1 )) > "$d/$sid.events"
exit 0
