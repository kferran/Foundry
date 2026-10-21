#!/bin/bash
# Usage log (factory F0 spec §3.7): UserPromptSubmit appends {ts, command} when the prompt starts with /<name>;
# PreToolUse on the Skill tool appends {ts, skill}. Names only, never prompt text or arguments, to
# system/logs/usage-YYYY-MM.jsonl. Attended interactive CLI sessions whose cwd is the vault root only.
# Fails open: any problem exits 0 with no output (a UserPromptSubmit hook's output would reach the model).
# Fast path: pure bash until the cwd is known to be the vault root, since this runs on every prompt everywhere.
[[ "${FOUNDRY_HEADLESS:-}" != 1 && "${CLAUDE_CODE_ENTRYPOINT:-}" == cli && "${CLAUDE_CODE_SESSION_ATTENDED:-}" == 1 ]] || exit 0

main() {
  local input vault key name
  input="$(cat)"  # one bulk read
  [[ "$input" == *'"agent_id"'* ]] && return 0  # subagent
  # The live cwd: a mid-session cd moves the session in or out of the log (the vault rules forbid cd).
  [[ "$input" =~ \"cwd\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] || return 0
  vault="$(cd "${BASH_SOURCE[0]%/*}/../.." && pwd -P)" || return 0
  [[ "$(realpath -e -- "${BASH_REMATCH[1]}")" == "$vault" ]] || return 0
  case "$(jq -r '.hook_event_name // empty' <<< "$input")" in
    UserPromptSubmit)
      key=command
      [[ "$(jq -r '.prompt // empty' <<< "$input")" =~ ^/([A-Za-z0-9._:-]+)([[:space:]]|$) ]] || return 0
      name="${BASH_REMATCH[1]}"
      # A vault command or skill, or a plugin's plugin:name; a path such as /etc logs nothing.
      [[ "$name" == *:* || -f "$vault/.claude/commands/$name.md" || -d "$vault/.claude/skills/$name" ]] || return 0 ;;
    PreToolUse)
      key=skill
      name="$(jq -r 'select(.tool_name == "Skill") | .tool_input.skill // empty' <<< "$input")" ;;
    *) return 0 ;;
  esac
  [[ "$name" =~ ^[A-Za-z0-9._:/-]{1,100}$ ]] || return 0
  jq -cn --arg ts "$(date -Iseconds)" --arg k "$key" --arg n "$name" '{ts: $ts, ($k): $n}' \
    >> "$vault/system/logs/usage-$(date +%Y-%m).jsonl"
}

main > /dev/null 2>&1
exit 0
