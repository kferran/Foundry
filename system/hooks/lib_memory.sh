# shellcheck shell=bash
# Soundwave: shared helpers for the memory hooks (spec §6.17). Sourced by memory_*.sh.
# Hooks never fail a session: every helper returns non-zero on trouble and callers exit 0.

MEM_VAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
MEM_DIR="$MEM_VAULT/system/logs/memory"
MEM_SESSIONS="$MEM_DIR/sessions"
MEM_LOG="$MEM_DIR/hooks.log"
MEM_CACHE="$MEM_DIR/scope_cache.tsv"
mkdir -p "$MEM_SESSIONS" 2>/dev/null

mem_log() { printf '%s [memory] %s\n' "$(date -Iseconds)" "$1" >> "$MEM_LOG" 2>/dev/null; }

mem_valid_sid() { [[ "${1-}" =~ ^[A-Za-z0-9-]+$ ]]; }

# Interactive, attended main sessions only (spike item 12; undocumented variables, re-checked by
# system_health.bats). Crewmates (FOUNDRY_WORKCELL_SESSION=1) skip the attended check.
mem_env_ok() {
  [[ "${FOUNDRY_HEADLESS:-}" != 1 ]] || return 1
  [[ "${CLAUDE_CODE_ENTRYPOINT:-}" == cli ]] || return 1
  [[ "${FOUNDRY_WORKCELL_SESSION:-}" == 1 || "${CLAUDE_CODE_SESSION_ATTENDED:-}" == 1 ]]
}

_mem_vi() { (cd "$MEM_VAULT" && system/scripts/vault_index.py "$@"); }

# scope_cache.tsv: one "#config" line (default_partition, timezone, min events, min minutes), then
# "<git common dir>\t<codebase name>\t<partition>" per registered codebase. Rebuilt when the config
# or any codebase file is newer than the cache.
mem_cache_fresh() {
  local f
  [[ -s "$MEM_CACHE" ]] || return 1
  for f in "$MEM_VAULT/system/config.md" "$MEM_VAULT"/system/codebases/*.md; do
    [[ -e "$f" && "$f" -nt "$MEM_CACHE" ]] && return 1
  done
  return 0
}

mem_cache_build() {
  local cfg rows tmp line name path part common
  cfg="$(_mem_vi query --json "SELECT default_partition, timezone, digest_min_events, digest_min_minutes FROM v_config WHERE path = 'system/config.md'")" || return 1
  rows="$(_mem_vi query --json "SELECT name, fm_path, partition FROM v_codebase WHERE path != 'system/codebases/example.md'")" || return 1
  tmp="$MEM_CACHE.$$"
  jq -r '.rows[0] // ["personal", "UTC", 5, 20] | ["#config"] + map(tostring) | @tsv' <<< "$cfg" > "$tmp" || return 1
  while IFS=$'\t' read -r name path part; do
    [[ "$path" == "~/"* ]] && path="$HOME/${path#\~/}"
    common="$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || continue
    common="$(realpath -e -- "$common" 2>/dev/null)" || continue
    printf '%s\t%s\t%s\n' "$common" "$name" "$part" >> "$tmp"
  done < <(jq -r '.rows[] | map(tostring) | @tsv' <<< "$rows")
  mv -f -- "$tmp" "$MEM_CACHE"
}

mem_config() {  # prints "<default_partition> <timezone> <min_events> <min_minutes>"
  mem_cache_fresh || mem_cache_build || return 1
  awk -F'\t' '$1 == "#config" { print $2, $3, $4, $5; exit }' "$MEM_CACHE"
}

# memory_scope <cwd>: "vault <partition>", "codebase <name> <partition>", or nothing (out of scope).
memory_scope() {
  local real common
  real="$(realpath -e -- "${1-}" 2>/dev/null)" || return 1
  mem_cache_fresh || mem_cache_build || return 1
  if [[ "$real" == "$MEM_VAULT" || "$real" == "$MEM_VAULT"/* ]]; then
    awk -F'\t' '$1 == "#config" { print "vault", $2; exit }' "$MEM_CACHE"
    return 0
  fi
  common="$(git -C "$real" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  common="$(realpath -e -- "$common" 2>/dev/null)" || return 1
  # Exactly one registration for this repo; two registrations of one repo are ambiguous (none).
  awk -F'\t' -v c="$common" '$1 == c { n++; hit = "codebase " $2 " " $3 } END { if (n == 1) print hit }' "$MEM_CACHE"
}

# mem_freeze <sid> <cwd>: freeze the session's scope on first sight (SessionStart, or the first hook
# that sees a session started before the hooks were installed). Returns 0 iff the session is in scope.
mem_freeze() {
  local sid="$1" cwd="$2" st="$MEM_SESSIONS/$1.json" scope cfg kind name part real
  if [[ -e "$MEM_SESSIONS/$sid.out" ]]; then return 1; fi
  if [[ -e "$st" ]]; then return 0; fi
  scope="$(memory_scope "$cwd")" || scope=""
  if [[ -z "$scope" ]]; then
    : > "$MEM_SESSIONS/$sid.out"
    return 1
  fi
  cfg="$(mem_config)" || return 1
  read -r kind name part <<< "$scope"
  [[ "$kind" == vault ]] && { part="$name"; name="vault"; }
  read -r _ tz min_events min_minutes <<< "$cfg"
  real="$(realpath -e -- "$cwd")" || return 1
  jq -n --arg cwd "$real" --arg scope "$kind" --arg partition "$part" --arg codebase "$name" --argjson now "$(date +%s)" \
    --arg tz "$tz" --argjson events "${min_events:-5}" --argjson minutes "${min_minutes:-20}" \
    '{cwd: $cwd, scope: $scope, partition: $partition, codebase: $codebase, started_at: $now, last_digest_at: 0,
      awaiting_digest: false, tz: $tz, digest_min_events: $events, digest_min_minutes: $minutes}' \
    > "$st.tmp" && mv -f -- "$st.tmp" "$st" || return 1
  printf '0\n' > "$MEM_SESSIONS/$sid.events"
  : > "$MEM_SESSIONS/$sid.eligible"
}

mem_state_set() {  # mem_state_set <sid> <jq filter>: atomic update of the session state
  local st="$MEM_SESSIONS/$1.json"
  jq "$2" "$st" > "$st.tmp" && mv -f -- "$st.tmp" "$st"
}

mem_events() { local n=0; [[ -f "$MEM_SESSIONS/$1.events" ]] && read -r n < "$MEM_SESSIONS/$1.events"; [[ "$n" =~ ^[0-9]+$ ]] || n=0; printf '%s\n' "$n"; }

mem_alert() {  # mem_alert <tz> <message>
  local day
  day="$(TZ="$1" date +%F)"
  printf -- '- %s [memory] %s\n' "$(TZ="$1" date +%H:%M:%S)" "$2" >> "$MEM_VAULT/system/logs/alerts_$day.md"
}

mem_prune() { find "$MEM_SESSIONS" -maxdepth 1 -type f -mtime +14 -delete 2>/dev/null || true; }
