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

# --uninstall is the escape hatch: it needs only jq and the settings file, never the hooks or a plain path.
if [[ "$mode" != uninstall ]]; then
  # Hook commands and Bash allow rules are matched as plain strings, so the vault path must not need quoting.
  [[ "$VAULT_ROOT" =~ ^/[A-Za-z0-9._/@+-]+$ ]] \
    || die 1 "the vault path must not contain spaces or shell metacharacters: $VAULT_ROOT"
  for h in memory_recall.sh memory_capture.sh memory_activity.sh; do
    [[ -x "system/hooks/$h" ]] || die 1 "missing or not executable: system/hooks/$h"
  done
fi

refuse() { die 1 "$SETTINGS $1; fix it by hand first (nothing was changed)"; }
current='{}'
if [[ -e "$SETTINGS" ]]; then
  current="$(cat -- "$SETTINGS")"
  # Slurped, so "{} {}" (two documents) is refused instead of passing a per-document check.
  jq -s -e 'length == 1 and (.[0] | type) == "object"' <<< "$current" > /dev/null 2>&1 \
    || refuse "is not a single JSON object"
fi

# The merge writes into these four containers; anything else in their place is refused up front.
SHAPE='
  [ ([["hooks"], "object"], [["hooks", "SessionStart"], "array"], [["hooks", "Stop"], "array"],
     [["hooks", "PostToolUse"], "array"], [["permissions"], "object"], [["permissions", "allow"], "array"]) as [$p, $t]
    | (try getpath($p) catch null) as $x
    | select($x != null and ($x | type) != $t) | $p | join(".") ] | join(", ")'
if [[ "$mode" != uninstall ]]; then
  bad="$(jq -r "$SHAPE" <<< "$current")"
  [[ -z "$bad" ]] || refuse "has an unexpected shape at: $bad (hooks and permissions must be objects, hook events and allow arrays)"
fi

# Owned = ours from any vault location, so moving the vault re-points the entries instead of duplicating them.
STRIP='
  def owned_cmd: type == "string" and test("/system/hooks/memory_(recall|capture|activity)\\.sh$");
  def owned_allow: type == "string" and test("^Bash\\(/.*/system/scripts/vault_index\\.py (related|show|backlinks):\\*\\)$");
  def has_owned: type == "object" and (.hooks | type) == "array" and any(.hooks[]; type == "object" and (.command | owned_cmd));
  # Only containers that held an owned element are pruned; foreign empty ones are left as found.
  (if (.hooks | type) == "object" then
     ([.hooks[] | select(type == "array") | .[] | select(has_owned)] | length > 0) as $had
     | .hooks |= with_entries(
         if (.value | type) == "array" then
           (.value | any(.[]; has_owned)) as $held
           | .value |= map(if has_owned then (.hooks |= map(select((type == "object" and (.command | owned_cmd)) | not))) | select((.hooks | length) > 0) else . end)
           | select(($held | not) or (.value | length) > 0)
         else . end)
     | if $had and .hooks == {} then del(.hooks) else . end
   else . end)
  | (if (.permissions | type) == "object" and (.permissions.allow | type) == "array" then
       (.permissions.allow | any(.[]; owned_allow)) as $held
       | .permissions.allow |= map(select(owned_allow | not))
       # An emptied allow array is indistinguishable from a foreign empty one, so it is dropped only
       # when it was the sole permissions key (the shape a fresh install creates); otherwise it stays.
       | if $held and .permissions.allow == [] and (.permissions | keys) == ["allow"] then del(.permissions) else . end
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
  new="$(jq "$STRIP" <<< "$current" 2> /dev/null)" || refuse "could not be read for the uninstall"
else
  new="$(jq --arg v "$VAULT_ROOT" "$STRIP | $ADD" <<< "$current" 2> /dev/null)" || refuse "could not be merged"
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
  case "$digest_action" in
    foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault) (dry run, nothing written)" ;;
    remove) echo "digest command: removed (dry run, nothing written)" ;;
    *) echo "digest command: $digest_action (dry run, nothing written)" ;;
  esac
  exit 0
fi

if [[ "$settings_action" == changed ]]; then
  mkdir -p -- "$CONFIG_DIR"
  if [[ -e "$SETTINGS" ]]; then
    # Never overwrite an earlier backup: an install and an uninstall can land in the same second.
    stamp="$(date +%s)"
    bak="$SETTINGS.bak.$stamp"
    n=1
    while [[ -e "$bak" ]]; do bak="$SETTINGS.bak.$stamp.$n"; n=$((n + 1)); done
    cp -p -- "$SETTINGS" "$bak"
    echo "backup: $bak"
  fi
  if [[ -L "$SETTINGS" ]]; then
    jq . <<< "$new" > "$SETTINGS"  # write through a symlink (dotfile managers), keeping the link
  else
    tmp="$SETTINGS.tmp.$$"
    ( umask 077; jq . <<< "$new" > "$tmp" )  # settings often hold env secrets: never wider than the original
    [[ -e "$SETTINGS" ]] && chmod --reference="$SETTINGS" -- "$tmp"
    mv -f -- "$tmp" "$SETTINGS"
  fi
fi
echo "settings: $settings_action"

case "$digest_action" in
  new|changed) mkdir -p -- "$(dirname "$DIGEST")"; digest_body > "$DIGEST"; echo "digest command: $digest_action" ;;
  remove) rm -f -- "$DIGEST"; echo "digest command: removed" ;;
  foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault)" ;;
  *) echo "digest command: $digest_action" ;;
esac
