#!/bin/bash
# Usage log (factory F0 spec §3.7): UserPromptSubmit appends {ts, command} when the prompt starts with /<name>;
# PreToolUse on the Skill tool appends {ts, skill}. Names only, never prompt text or arguments, to
# system/logs/usage-YYYY-MM.jsonl. Attended CLI sessions whose cwd is the vault root only (the memory gates).
# Fails open: any problem exits 0 with no output (a UserPromptSubmit hook's output would reach the model).
[[ "${FOUNDRY_HEADLESS:-}" == 1 ]] && exit 0

main() {
  local input cwd key name
  input="$(cat)"
  # shellcheck source=lib_memory.sh
  source "${BASH_SOURCE[0]%/*}/lib_memory.sh"
  mem_env_ok || return 0
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  cwd="$(jq -r '.cwd // empty' <<< "$input")"
  [[ "$(realpath -e -- "$cwd")" == "$MEM_VAULT" ]] || return 0
  case "$(jq -r '.hook_event_name // empty' <<< "$input")" in
    UserPromptSubmit)
      key=command
      [[ "$(jq -r '.prompt // empty' <<< "$input")" =~ ^/([A-Za-z0-9._:-]+)([[:space:]]|$) ]] || return 0
      name="${BASH_REMATCH[1]}" ;;
    PreToolUse)
      key=skill
      name="$(jq -r 'select(.tool_name == "Skill") | .tool_input.skill // empty' <<< "$input")" ;;
    *) return 0 ;;
  esac
  [[ "$name" =~ ^[A-Za-z0-9._:/-]{1,100}$ ]] || return 0
  jq -cn --arg ts "$(date -Iseconds)" --arg k "$key" --arg n "$name" '{ts: $ts, ($k): $n}' \
    >> "$MEM_VAULT/system/logs/usage-$(date +%Y-%m).jsonl"
}

main > /dev/null 2>&1
exit 0
