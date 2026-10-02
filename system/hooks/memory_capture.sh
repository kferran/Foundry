#!/bin/bash
# Soundwave Stop hook (spec §6.17): capture a marked digest, or ask for one after substantive work.
# Never fails the session and never blocks twice in a row.
[[ "${JARVIS_HEADLESS:-}" == 1 ]] && exit 0
set -uo pipefail
# shellcheck source=lib_memory.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib_memory.sh"

slugify() {
  local s
  s="$(printf '%s' "$1" | sed -E 's/^[#* ]+//; s/[^A-Za-z0-9]+/-/g; s/^-+//; s/-+$//' | tr '[:upper:]' '[:lower:]')"
  s="${s:0:40}"
  s="${s%-}"
  printf '%s\n' "${s:-digest}"
}

write_digest() {  # write_digest <sid> <digest text>
  local sid="$1" text="$2" st part codebase tz stamp created first slug dir name n redacted count task=""
  st="$MEM_SESSIONS/$sid.json"
  part="$(jq -r .partition "$st")" codebase="$(jq -r .codebase "$st")" tz="$(jq -r .tz "$st")"
  stamp="$(TZ="$tz" date +%Y-%m-%d-%H%M)" created="$(TZ="$tz" date +%Y-%m-%dT%H:%M:%S%:z)"
  first="$(grep -m 1 -vE '^[[:space:]]*(#.*)?$|^[[:space:]]*\*\*[^*]+\*\*[[:space:]]*$' <<< "$text" || true)"
  slug="$(slugify "$first")"
  dir="$MEM_VAULT/raw/$part/notes"
  mkdir -p "$dir"
  name="$stamp-${sid:0:8}-$slug" n=1
  while [[ -e "$dir/$name.md" ]]; do n=$(( n + 1 )); name="$stamp-${sid:0:8}-$slug-$n"; done
  redacted="$(printf '%s' "$text" | "$MEM_VAULT/system/scripts/redact.py" 2> "$dir/.$name.count")" || return 1
  count="$(sed -n 's/^redactions: //p' "$dir/.$name.count")"
  rm -f -- "$dir/.$name.count"
  if [[ "${JARVIS_CREW:-}" == 1 && "${JARVIS_TASK_ID:-}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    task="task_id: \"$JARVIS_TASK_ID\""$'\n'
  fi
  # Written as a dotfile, then renamed: intake skips dotfiles, so it never sees a half-written digest.
  printf -- '---\ntype: session_digest\npartition: "%s"\ncodebase: "%s"\nsession_id: "%s"\ncreated_at: "%s"\nprovenance: ["session"]\nredactions: "%s"\n%s---\n%s\n' \
    "$part" "$codebase" "$sid" "$created" "${count:-0}" "$task" "$redacted" > "$dir/.$name.md.tmp" || return 1
  mv -f -- "$dir/.$name.md.tmp" "$dir/$name.md"
  mem_log "captured raw/$part/notes/$name.md"
}

main() {
  local input sid cwd msg body st events since now minutes trimmed reason tz
  input="$(cat)"
  mem_env_ok || return 0
  [[ -z "$(jq -r '.agent_id // empty' <<< "$input")" ]] || return 0
  sid="$(jq -r '.session_id // empty' <<< "$input")"
  mem_valid_sid "$sid" || { mem_log "Stop: invalid session_id"; return 0; }
  cwd="$(jq -r '.cwd // empty' <<< "$input")"
  [[ -n "$cwd" ]] || cwd="$PWD"
  mem_freeze "$sid" "$cwd" || return 0  # frozen scope: a later cd never moves the session
  st="$MEM_SESSIONS/$sid.json"
  now="$(date +%s)" tz="$(jq -r .tz "$st")"
  msg="$(jq -r '.last_assistant_message // ""' <<< "$input")"

  # 1. A marked digest (requested by this hook, or written on demand with /digest).
  if [[ "$msg" == *"<vault-digest>"*"</vault-digest>"* ]]; then
    body="${msg#*<vault-digest>}"
    body="${body%%</vault-digest>*}"
    write_digest "$sid" "$body" || { mem_log "Stop: digest write failed for ${sid:0:8}"; return 0; }
    mem_state_set "$sid" ".last_digest_at = $now | .awaiting_digest = false"
    printf '0\n' > "$MEM_SESSIONS/$sid.events"
    return 0
  fi
  [[ "${JARVIS_CREW:-}" == 1 ]] && return 0  # crewmates: on-demand digests only

  # 2. We asked last time and got no digest: alert, reset, and never ask twice in a row.
  if [[ "$(jq -r .awaiting_digest "$st")" == true ]]; then
    mem_alert "$tz" "session ${sid:0:8} did not return the requested digest"
    mem_state_set "$sid" '.awaiting_digest = false'
    printf '0\n' > "$MEM_SESSIONS/$sid.events"
    return 0
  fi

  # 3. Ask only after substantive work, and never when the assistant just asked the user something.
  events="$(mem_events "$sid")"
  since="$(jq -r 'if .last_digest_at > 0 then .last_digest_at else .started_at end' "$st")"
  minutes=$(( (now - since) / 60 ))
  trimmed="${msg%"${msg##*[![:space:]]}"}"
  [[ "$trimmed" == *"?" ]] && return 0
  (( events >= $(jq -r .digest_min_events "$st") )) || return 0
  (( minutes >= $(jq -r .digest_min_minutes "$st") )) || return 0
  reason="$(< "$(dirname "${BASH_SOURCE[0]}")/digest_instructions.md")"
  mem_state_set "$sid" '.awaiting_digest = true' || return 0
  jq -cn --arg r "$reason" '{decision: "block", reason: $r}'
}

main 2>> "$MEM_LOG"
exit 0
