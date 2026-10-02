#!/bin/bash
# Merge Soundwave's memory hooks into the user's Claude Code settings (spec §6.19).
# Touches only owned entries: hook commands under <vault>/system/hooks/memory_*.sh, the three
# absolute vault_index.py allow rules, and a commands/digest.md carrying the managed-by line.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CONFIG_DIR/settings.json"
DIGEST="$CONFIG_DIR/commands/digest.md"
MANAGED="<!-- managed by vault: "

die() { echo "install_hooks: $2" >&2; exit "$1"; }
usage() { die 2 "usage: install_hooks.sh [--dry-run | --uninstall]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  *) usage ;;
esac

# Hook commands and Bash allow rules are matched as plain strings, so the vault path must not need quoting.
[[ "$VAULT_ROOT" =~ ^/[A-Za-z0-9._/@+-]+$ ]] \
  || die 1 "the vault path must not contain spaces or shell metacharacters: $VAULT_ROOT"
for h in memory_recall.sh memory_capture.sh memory_activity.sh; do
  [[ -x "system/hooks/$h" ]] || die 1 "missing or not executable: system/hooks/$h"
done

current='{}'
if [[ -e "$SETTINGS" ]]; then
  current="$(cat -- "$SETTINGS")"
  jq -e 'type == "object"' <<< "$current" > /dev/null 2>&1 \
    || die 1 "$SETTINGS is not a JSON object; fix it by hand first (nothing was changed)"
fi

# Owned = ours from any vault location, so moving the vault re-points the entries instead of duplicating them.
STRIP='
  def owned_cmd: (. // "") | test("/system/hooks/memory_(recall|capture|activity)\\.sh$");
  def owned_allow: test("^Bash\\(/.*/system/scripts/vault_index\\.py (related|show|backlinks):\\*\\)$");
  (if (.hooks | type) == "object" then
     .hooks |= with_entries(
       if (.value | type) == "array" then
         .value |= (map(if (.hooks | type) == "array" then .hooks |= map(select(.command | owned_cmd | not)) else . end)
                    | map(select((.hooks | type) != "array" or (.hooks | length) > 0)))
       else . end)
     | .hooks |= with_entries(select((.value | type) != "array" or (.value | length) > 0))
     | if .hooks == {} then del(.hooks) else . end
   else . end)
  | (if (.permissions.allow | type) == "array" then
       .permissions.allow |= map(select(type != "string" or (owned_allow | not)))
       | if .permissions.allow == [] then del(.permissions.allow) else . end
       | if .permissions == {} then del(.permissions) else . end
     else . end)'
ADD='
  .hooks.SessionStart = ((.hooks.SessionStart // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_recall.sh"), timeout: 5}]}])
  | .hooks.Stop = ((.hooks.Stop // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_capture.sh"), timeout: 10}]}])
  | .hooks.PostToolUse = ((.hooks.PostToolUse // []) + [{matcher: "Edit|Write|MultiEdit|NotebookEdit|Bash",
      hooks: [{type: "command", command: ($v + "/system/hooks/memory_activity.sh"), timeout: 5}]}])
  | .permissions.allow = ((.permissions.allow // []) + [
      "Bash(" + $v + "/system/scripts/vault_index.py related:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py show:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py backlinks:*)"])'
if [[ "$mode" == uninstall ]]; then
  new="$(jq "$STRIP" <<< "$current")"
else
  new="$(jq --arg v "$VAULT_ROOT" "$STRIP | $ADD" <<< "$current")"
fi
jq -e 'type == "object"' <<< "$new" > /dev/null || die 1 "the merged settings did not parse; nothing was changed"

digest_body() {
  printf -- '---\ndescription: Write a Jarvis session digest of the work since the last one.\n---\n%s%s -->\n\n' "$MANAGED" "$VAULT_ROOT"
  cat system/hooks/digest_instructions.md
}
digest_owned() { [[ -f "$DIGEST" ]] && grep -qF -- "$MANAGED" "$DIGEST"; }
if [[ "$mode" == uninstall ]]; then
  if digest_owned; then digest_action=remove; else digest_action=none; fi
elif [[ ! -e "$DIGEST" ]]; then
  digest_action=new
elif ! digest_owned; then
  digest_action=foreign
elif [[ "$(cat -- "$DIGEST")" == "$(digest_body)" ]]; then
  digest_action=unchanged
else
  digest_action=changed
fi

if [[ "$(jq -S . <<< "$current")" == "$(jq -S . <<< "$new")" ]]; then settings_action=unchanged; else settings_action=changed; fi

if [[ "$mode" == dry ]]; then
  diff -u --label "$SETTINGS (current)" --label "$SETTINGS (after install)" \
    <(jq -S . <<< "$current") <(jq -S . <<< "$new") || true
  echo "settings: $settings_action (dry run, nothing written)"
  echo "digest command: $digest_action (dry run, nothing written)"
  exit 0
fi

if [[ "$settings_action" == changed ]]; then
  mkdir -p -- "$CONFIG_DIR"
  [[ -e "$SETTINGS" ]] && cp -p -- "$SETTINGS" "$SETTINGS.bak.$(date +%s)"
  if [[ -L "$SETTINGS" ]]; then
    jq . <<< "$new" > "$SETTINGS"  # write through a symlink (dotfile managers), keeping the link
  else
    jq . <<< "$new" > "$SETTINGS.tmp.$$"
    mv -f -- "$SETTINGS.tmp.$$" "$SETTINGS"
  fi
fi
echo "settings: $settings_action"

case "$digest_action" in
  new|changed) mkdir -p -- "$(dirname "$DIGEST")"; digest_body > "$DIGEST"; echo "digest command: $digest_action" ;;
  remove) rm -f -- "$DIGEST"; echo "digest command: removed" ;;
  foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault)" ;;
  *) echo "digest command: $digest_action" ;;
esac
