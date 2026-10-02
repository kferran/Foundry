#!/usr/bin/env bats
# install_hooks.sh (spec §6.19). Always runs against a temporary HOME, never the real ~/.claude.
load helpers

setup() {
  make_vault
  cp -r "$REPO/system/hooks" "$V/system/hooks"
  export HOME="$BATS_TEST_TMPDIR/home"
  unset CLAUDE_CONFIG_DIR
  CFG="$HOME/.claude"
  SET="$CFG/settings.json"
  mkdir -p "$CFG/commands"
  cat > "$SET" <<'EOF'
{
  "model": "opus",
  "env": {"FOO": "1"},
  "permissions": {"allow": ["Bash(npm test)"], "deny": ["Read(~/.ssh/**)"]},
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/notify-done"}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/opt/guard.sh"}]}]
  }
}
EOF
  cp "$SET" "$BATS_TEST_TMPDIR/original.json"
  relocate "$V"
}

relocate() {  # relocate <path>: move the vault there and re-derive its paths
  [ "$1" = "$V" ] || mv "$V" "$1"
  V="$1"
  VP="$(cd "$V" && pwd -P)"
  IH="$VP/system/scripts/install_hooks.sh"
}

ours() { jq -r '[.hooks[][] | .hooks[] | .command | select(test("memory_"))] | .[]' "$SET"; }

@test "install merges the three hooks and three allows, leaving foreign entries alone" {
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.hooks.SessionStart[0].hooks[0].command' "$SET")" = "$VP/system/hooks/memory_recall.sh" ]
  [ "$(jq -r '.hooks.Stop | map(.hooks[].command) | join(",")' "$SET")" = "/usr/local/bin/notify-done,$VP/system/hooks/memory_capture.sh" ]
  [ "$(jq -r '.hooks.PostToolUse[0].matcher' "$SET")" = "Edit|Write|MultiEdit|NotebookEdit|Bash" ]
  [ "$(jq -r '.hooks.PreToolUse[0].hooks[0].command' "$SET")" = /opt/guard.sh ]
  [ "$(jq -r '.model + .env.FOO' "$SET")" = opus1 ]
  [ "$(jq -c '.permissions.allow' "$SET")" = "[\"Bash(npm test)\",\"Bash($VP/system/scripts/vault_index.py related:*)\",\"Bash($VP/system/scripts/vault_index.py show:*)\",\"Bash($VP/system/scripts/vault_index.py backlinks:*)\"]" ]
  run jq -r '.permissions.allow[] | select(test("query|^Read"))' "$SET"
  [ -z "$output" ]
  [ "$(jq -c '.permissions.deny' "$SET")" = '["Read(~/.ssh/**)"]' ]
}

@test "install writes the managed /digest command; a foreign one is never touched" {
  run "$IH"
  [ "$status" -eq 0 ]
  grep -qF "<!-- managed by vault: $VP -->" "$CFG/commands/digest.md"
  grep -qF '<vault-digest>' "$CFG/commands/digest.md"
  printf 'my own digest command\n' > "$CFG/commands/digest.md"
  run "$IH"
  [ "$status" -eq 0 ]
  [[ "$output" == *"left alone"* ]]
  [ "$(cat "$CFG/commands/digest.md")" = "my own digest command" ]
}

@test "a second run changes nothing and writes no new backup" {
  run "$IH"
  [ "$status" -eq 0 ]
  backups="$(ls "$CFG" | grep -c 'settings.json.bak')"
  sum="$(sha256sum "$SET")"
  run "$IH"
  [ "$status" -eq 0 ]
  grep -qx 'settings: unchanged' <<< "$output"
  grep -qx 'digest command: unchanged' <<< "$output"
  [ "$(sha256sum "$SET")" = "$sum" ]
  [ "$(ls "$CFG" | grep -c 'settings.json.bak')" -eq "$backups" ]
}

@test "a change is preceded by a timestamped backup of the old file" {
  run "$IH"
  [ "$status" -eq 0 ]
  bak="$(ls "$CFG"/settings.json.bak.*)"
  [ "$(jq -S . "$bak")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "--dry-run prints the diff and writes nothing" {
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"+"*"memory_recall.sh"* ]]
  [ "$(sha256sum < "$SET")" = "$(sha256sum < "$BATS_TEST_TMPDIR/original.json")" ]
  [ ! -e "$CFG/commands/digest.md" ]
  run ls "$CFG"/settings.json.bak.*
  [ "$status" -ne 0 ]
}

@test "--uninstall restores the original settings and removes only the owned /digest" {
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  [ ! -e "$CFG/commands/digest.md" ]
  printf 'foreign\n' > "$CFG/commands/digest.md"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(cat "$CFG/commands/digest.md")" = foreign ]
}

@test "moving the vault re-points the entries instead of duplicating them" {
  run "$IH"
  [ "$status" -eq 0 ]
  relocate "$BATS_TEST_TMPDIR/moved"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(ours | wc -l)" -eq 3 ]
  [ "$(ours | grep -c "^$VP/system/hooks/")" -eq 3 ]
  [ "$(jq '[.permissions.allow[] | select(test("vault_index"))] | length' "$SET")" -eq 3 ]
  grep -qF "<!-- managed by vault: $VP -->" "$CFG/commands/digest.md"
}

@test "no settings file yet: one is created" {
  rm "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(ours | wc -l)" -eq 3 ]
}

@test "invalid settings JSON aborts and leaves the file untouched" {
  printf '{ not json' > "$SET"
  run "$IH"
  [ "$status" -eq 1 ]
  [ "$(cat "$SET")" = '{ not json' ]
}

@test "a symlinked settings.json stays a symlink" {
  mv "$SET" "$BATS_TEST_TMPDIR/dotfiles.json"
  ln -s "$BATS_TEST_TMPDIR/dotfiles.json" "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ -L "$SET" ]
  [ "$(jq '[.hooks[][] | .hooks[] | select(.command | test("memory_"))] | length' "$BATS_TEST_TMPDIR/dotfiles.json")" -eq 3 ]
}

@test "a vault path that would need quoting is refused" {
  relocate "$BATS_TEST_TMPDIR/my vault"
  run "$IH"
  [ "$status" -eq 1 ]
  [[ "$output" == *"must not contain spaces"* ]]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "CLAUDE_CONFIG_DIR redirects the target" {
  export CLAUDE_CONFIG_DIR="$BATS_TEST_TMPDIR/alt"
  run "$IH"
  [ "$status" -eq 0 ]
  [ -f "$CLAUDE_CONFIG_DIR/settings.json" ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "usage errors exit 2" {
  run "$IH" --bogus
  [ "$status" -eq 2 ]
}

@test "a mode-600 settings.json stays 600 through install and uninstall" {
  chmod 600 "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(stat -c %a "$SET")" = 600 ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(stat -c %a "$SET")" = 600 ]
}

@test "a newly created settings.json is mode 600" {
  rm "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(stat -c %a "$SET")" = 600 ]
}

@test "foreign empty containers survive install and uninstall untouched" {
  printf '%s' '{"permissions":{"allow":[],"deny":[]},"hooks":{"Notification":[],"Stop":[{"matcher":"","hooks":[]}]}}' > "$SET"
  jq -S . "$SET" > "$BATS_TEST_TMPDIR/fixture.json"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(jq -c '.hooks.Notification' "$SET")" = '[]' ]
  [ "$(jq -c '.hooks.Stop[0]' "$SET")" = '{"matcher":"","hooks":[]}' ]
  [ "$(jq -c '.permissions.deny' "$SET")" = '[]' ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  jq -S . "$SET" > "$BATS_TEST_TMPDIR/after.json"
  run diff "$BATS_TEST_TMPDIR/fixture.json" "$BATS_TEST_TMPDIR/after.json"
  [ "$status" -eq 0 ]
}

@test "--dry-run reports a foreign digest.md as left alone, with the dry-run suffix" {
  printf 'my own digest command\n' > "$CFG/commands/digest.md"
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"digest command: left alone ("*") (dry run, nothing written)"* ]]
  [[ "$output" != *"foreign"* ]]
  [ "$(cat "$CFG/commands/digest.md")" = "my own digest command" ]
}

@test "a settings.json holding two JSON documents is refused, not rewritten" {
  printf '{} {}\n' > "$SET"
  run "$IH"
  [ "$status" -eq 1 ]
  [[ "$output" == *"is not a single JSON object"* ]]
  [ "$(cat "$SET")" = '{} {}' ]
}

@test "well-formed JSON of an unexpected shape exits 1 with a message and is left untouched" {
  for doc in '{"hooks": []}' '{"hooks": {"Stop": {}}}' '{"permissions": "ask"}' '{"permissions": {"allow": "Bash(x)"}}'; do
    printf '%s\n' "$doc" > "$SET"
    for mode in "" --dry-run; do
      run "$IH" $mode
      [ "$status" -eq 1 ]
      [[ "$output" == *"unexpected shape at: "* ]]
      [ "$(cat "$SET")" = "$doc" ]
    done
  done
}

@test "install refuses a missing or non-executable hook and changes nothing" {
  chmod -x "$V/system/hooks/memory_capture.sh"
  run "$IH"
  [ "$status" -eq 1 ]
  [[ "$output" == *"missing or not executable: system/hooks/memory_capture.sh"* ]]
  [ "$(sha256sum < "$SET")" = "$(sha256sum < "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "--uninstall works without the hook files and from a path that needs quoting" {
  run "$IH"
  [ "$status" -eq 0 ]
  rm "$V/system/hooks/memory_recall.sh"
  chmod -x "$V/system/hooks/memory_capture.sh"
  relocate "$BATS_TEST_TMPDIR/my vault"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  [ ! -e "$CFG/commands/digest.md" ]
}

@test "a backup never overwrites an earlier one from the same second" {
  now="$(date +%s)"
  for t in $(seq "$now" $((now + 3))); do printf 'older %s\n' "$t" > "$SET.bak.$t"; done
  run "$IH"
  [ "$status" -eq 0 ]
  for t in $(seq "$now" $((now + 3))); do [ "$(cat "$SET.bak.$t")" = "older $t" ]; done
  bak="$(sed -n 's/^backup: //p' <<< "$output")"
  [ -f "$bak" ]
  [ "$(jq -S . "$bak")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  [ "$(ls "$CFG" | grep -c 'settings.json.bak')" -eq 5 ]
}

record() { jq -c --arg k "$SET" '.[$k]' "$V/system/logs/memory/install_hooks.json"; }

@test "permissions without an allow list come back without one after install and uninstall" {
  printf '%s\n' '{"permissions": {"deny": ["Read(~/.ssh/**)"], "defaultMode": "default"}}' > "$SET"
  jq -S . "$SET" > "$BATS_TEST_TMPDIR/fixture.json"
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(cat "$BATS_TEST_TMPDIR/fixture.json")" ]
}

@test "foreign empty containers of every kind the installer writes into survive install and uninstall" {
  for doc in '{"hooks": {}}' '{"permissions": {}}' '{"hooks": {"Stop": []}}' '{"hooks": {"SessionStart": [], "PostToolUse": []}, "permissions": {"allow": []}}'; do
    printf '%s\n' "$doc" > "$SET"
    run "$IH"
    [ "$status" -eq 0 ]
    [ "$(ours | wc -l)" -eq 3 ]
    run "$IH" --uninstall
    [ "$status" -eq 0 ]
    [ "$(jq -S . "$SET")" = "$(jq -S . <<< "$doc")" ]
  done
}

@test "the record names exactly the containers the install created, and uninstall drops it" {
  printf '%s\n' '{"hooks": {"Stop": []}, "permissions": {"deny": []}}' > "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(record)" = '[["hooks","SessionStart"],["hooks","PostToolUse"],["permissions","allow"]]' ]
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(record)" = '[["hooks","SessionStart"],["hooks","PostToolUse"],["permissions","allow"]]' ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(record)" = null ]
}

@test "--dry-run writes no record" {
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  [ ! -e "$V/system/logs/memory/install_hooks.json" ]
}

@test "an install made before records existed still uninstalls cleanly" {
  run "$IH"
  [ "$status" -eq 0 ]
  rm "$V/system/logs/memory/install_hooks.json"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  rm "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  printf 'not json\n' > "$V/system/logs/memory/install_hooks.json"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -c . "$SET")" = '{}' ]
}

@test "a rule the user adds after install keeps its allow list through uninstall" {
  printf '%s\n' '{"permissions": {"deny": []}}' > "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  jq '.permissions.allow += ["Bash(make test)"]' "$SET" > "$SET.new"
  mv "$SET.new" "$SET"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -c .permissions "$SET")" = '{"deny":[],"allow":["Bash(make test)"]}' ]
}

@test "a vault moved after install still uninstalls exactly" {
  printf '%s\n' '{"permissions": {"deny": []}, "hooks": {"Stop": []}}' > "$SET"
  jq -S . "$SET" > "$BATS_TEST_TMPDIR/fixture.json"
  run "$IH"
  [ "$status" -eq 0 ]
  relocate "$BATS_TEST_TMPDIR/moved"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(cat "$BATS_TEST_TMPDIR/fixture.json")" ]
}

@test "an empty or multi-document install record falls back instead of blocking install and uninstall" {
  for junk in '' '{} {}'; do
    rm -f "$SET"
    run "$IH"
    [ "$status" -eq 0 ]
    printf '%s\n' "$junk" > "$V/system/logs/memory/install_hooks.json"
    [ -n "$junk" ] || : > "$V/system/logs/memory/install_hooks.json"
    run "$IH"
    [ "$status" -eq 0 ]
    [ "$(ours | wc -l)" -eq 3 ]
    run "$IH" --uninstall
    [ "$status" -eq 0 ]
    [ "$(jq -c . "$SET")" = '{}' ]
  done
}

@test "after an install, --dry-run prints the two lines /setup reads as already installed" {
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  grep -qx 'settings: unchanged (dry run, nothing written)' <<< "$output"
  grep -qx 'digest command: unchanged (dry run, nothing written)' <<< "$output"
}
