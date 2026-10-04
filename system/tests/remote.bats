#!/usr/bin/env bats
# lib_git.sh, setup_remote.sh (spec §6.11) and update_template.sh (spec §6.12).
load helpers

setup() {
  make_vault
  cd "$V"
  T="$BATS_TEST_TMPDIR/template.git"
  git init -q --bare "$T"
  echo "$T" > system/template_source
  # Only local repositories are reachable: ssh/https remotes fail at once instead of touching the network.
  export GIT_ALLOW_PROTOCOL=file
  SR="$V/system/scripts/setup_remote.sh"
  UT="$V/system/scripts/update_template.sh"
  source "$V/system/scripts/lib_git.sh"
}

field() { system/scripts/vault_index.py field system/config.md "$1"; }

@test "url normalization: ssh, scp-style and https forms of one repo are equal" {
  a="$(git_url_normalize git@GitHub.com:Me/Vault.git)"
  [ "$a" = github.com/Me/Vault ]
  for u in ssh://git@github.com/Me/Vault https://GitHub.com/Me/Vault/ https://user@github.com:443/Me/Vault.git ssh://git@github.com:22/Me/Vault.git/; do
    [ "$(git_url_normalize "$u")" = "$a" ]
  done
  [ "$(git_url_normalize "file://$T/")" = "$(git_url_normalize "$T")" ]
  git_url_same https://github.com/Me/Vault git@github.com:Me/Vault.git
  run git_url_same https://github.com/Me/Vault https://github.com/Me/Other
  [ "$status" -ne 0 ]
  run git_url_same "" ""
  [ "$status" -ne 0 ]
}

@test "a plain clone has its origin renamed to template" {
  git remote add origin "file://$T/"
  run "$SR" --none
  [ "$status" -eq 0 ]
  [[ "$output" == *"plain clone"* ]]
  [ "$(git remote get-url template)" = "file://$T/" ]
  run git remote get-url origin
  [ "$status" -ne 0 ]
  [ "$(field remote_mode)" = none ]
  [ "$(field template_remote)" = "$T" ]
  [ "$(git config core.hooksPath)" = .githooks ]
}

@test "a repo created from the template keeps its origin and gains a template remote" {
  git remote add origin git@example.com:me/vault.git
  run "$SR" --none
  [ "$status" -eq 0 ]
  [ "$(git remote get-url origin)" = git@example.com:me/vault.git ]
  [ "$(git remote get-url template)" = "$T" ]
}

@test "with no origin, only the template remote is added" {
  run "$SR" --none
  [ "$status" -eq 0 ]
  [ "$(git remote get-url template)" = "$T" ]
  run git remote get-url origin
  [ "$status" -ne 0 ]
}

@test "<url> sets a private origin and warns when it is unreachable" {
  run "$SR" git@example.com:me/vault.git
  [ "$status" -eq 0 ]
  [ "$(git remote get-url origin)" = git@example.com:me/vault.git ]
  [ "$(field remote_mode)" = private ]
  [[ "$output" == *"not reachable"* ]]
}

@test "<url> that is reachable sets origin without a warning" {
  git init -q --bare "$BATS_TEST_TMPDIR/private.git"
  run "$SR" "$BATS_TEST_TMPDIR/private.git"
  [ "$status" -eq 0 ]
  [ "$(git remote get-url origin)" = "$BATS_TEST_TMPDIR/private.git" ]
  [[ "$output" != *"not reachable"* ]]
}

@test "a plain clone given <url> keeps the template and gets the new origin" {
  git remote add origin "$T"
  run "$SR" git@example.com:me/vault.git
  [ "$status" -eq 0 ]
  [ "$(git remote get-url template)" = "$T" ]
  [ "$(git remote get-url origin)" = git@example.com:me/vault.git ]
}

@test "an origin that is the template is refused and nothing changes" {
  before="$(sha256sum system/config.md)"
  run "$SR" "file://$T/"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing"* ]]
  run git remote
  [ -z "$output" ]
  [ "$(sha256sum system/config.md)" = "$before" ]
}

@test "--keep leaves the remotes untouched" {
  git remote add origin "$T"
  run "$SR" --keep
  [ "$status" -eq 0 ]
  [ "$(git remote)" = origin ]
  [ "$(git remote get-url origin)" = "$T" ]
  [ "$(field remote_mode)" = keep ]
  [ "$(git config core.hooksPath)" = .githooks ]
}

@test "a second run is a no-op" {
  run "$SR" git@example.com:me/vault.git
  before="$(sha256sum system/config.md)"
  remotes="$(git remote -v)"
  run "$SR" git@example.com:me/vault.git
  [ "$status" -eq 0 ]
  [ "$(sha256sum system/config.md)" = "$before" ]
  [ "$(git remote -v)" = "$remotes" ]
}

@test "--detect reports the case and changes nothing" {
  git remote add origin "file://$T/"
  before="$(sha256sum system/config.md)"
  run "$SR" --detect
  [ "$status" -eq 0 ]
  [[ "$output" == *"plain clone"* ]]
  [ "$(git remote)" = origin ]
  [ "$(git remote get-url origin)" = "file://$T/" ]
  [ "$(sha256sum system/config.md)" = "$before" ]
  run git config --get core.hooksPath
  [ "$status" -ne 0 ]
}

@test "setup_remote: usage errors exit 2; a missing template_source or config exits 1" {
  run "$SR"
  [ "$status" -eq 2 ]
  run "$SR" --bogus
  [ "$status" -eq 2 ]
  run "$SR" a b
  [ "$status" -eq 2 ]
  : > system/template_source
  run "$SR" --none
  [ "$status" -eq 1 ]
  echo "$T" > system/template_source
  rm system/config.md
  run "$SR" --none
  [ "$status" -eq 1 ]
}

# A published template (UP) that this vault tracks as "template", and a working clone (W) of it.
template_setup() {
  cp -r "$REPO/system/systemd" system/systemd
  cp "$REPO/.gitignore" .gitignore  # generated files (index.db) must not dirty the tree
  printf 'base\n' > "my notes.txt"
  git add -A
  git commit -qm base
  UP="$BATS_TEST_TMPDIR/up.git"
  git clone -q --bare "$V" "$UP"
  git remote add template "$UP"
  W="$BATS_TEST_TMPDIR/work"
  git clone -q "$UP" "$W"
  git -C "$W" config user.email up@example.com
  git -C "$W" config user.name up
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  ln -s "$REPO/system/tests/stub_claude" "$STUBS/claude"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n' > "$STUBS/systemctl"
  chmod +x "$STUBS/systemctl"
  export PATH="$STUBS:$PATH" SYSTEMCTL="$STUBS/systemctl" STUB_SYSTEMCTL_LOG="$BATS_TEST_TMPDIR/systemctl.log"
  export SYSTEMD_USER_DIR="$BATS_TEST_TMPDIR/units" HOME="$BATS_TEST_TMPDIR/home"
}

upstream_commit() {  # <file> <text>
  printf '%s\n' "$2" > "$W/$1"
  git -C "$W" add -A
  git -C "$W" commit -qm "upstream: $1"
  git -C "$W" push -q
}

@test "update_template merges a clean update, then rebuilds the index and re-renders installed units" {
  template_setup
  system/scripts/install_units.sh > /dev/null
  printf '# Managed by vault: %s\nstale\n' "$(pwd -P)" > "$SYSTEMD_USER_DIR/jarvis-brief.service"
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  [ -f system/index.db ]
  grep -qE '^[0-9]{8}T[0-9]{6}$' system/logs/commit_runs.since
  grep -qx 'changed jarvis-brief.service' <<< "$output"
  grep -q '^ExecStart=' "$SYSTEMD_USER_DIR/jarvis-brief.service"
}

@test "update_template re-renders units when only an owned drop-in is installed" {
  template_setup
  mkdir -p "$SYSTEMD_USER_DIR/jarvis-brief.service.d"
  printf '# Managed by vault: %s\n[Service]\n' "$(pwd -P)" > "$SYSTEMD_USER_DIR/jarvis-brief.service.d/jarvis-sync.conf"
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"units not installed"* ]]
}

@test "update_template leaves units alone in a vault that never installed them" {
  template_setup
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
  [[ "$output" == *"units not installed; skipped"* ]]
  [ ! -e "$SYSTEMD_USER_DIR" ]
  [ ! -e "$STUB_SYSTEMCTL_LOG" ]
}

@test "update_template finds the default branch under a non-English locale" {
  template_setup
  upstream_commit new.txt hello
  # Translations need an installed locale; en_US.UTF-8 plus LANGUAGE=de gives German git output.
  LANGUAGE=de LC_ALL=en_US.UTF-8 run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
}

@test "update_template refuses a dirty working tree before fetching" {
  template_setup
  upstream_commit new.txt hello
  echo x > dirty.txt
  run "$UT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"not clean"* ]]
  [ -z "$(git for-each-ref refs/remotes/template)" ]
  [ ! -e new.txt ]
}

@test "update_template stops on a conflict, lists the files and leaves the merge to the user" {
  template_setup
  upstream_commit "my notes.txt" theirs
  printf 'ours\n' > "my notes.txt"
  git commit -qam ours
  run "$UT"
  [ "$status" -eq 1 ]
  grep -qx '  my notes.txt' <<< "$output"
  [ -f .git/MERGE_HEAD ]
  [ ! -e "$SYSTEMD_USER_DIR" ]
}

@test "update_template refuses a template that shares no history with the vault" {
  template_setup
  O="$BATS_TEST_TMPDIR/other"
  git init -q "$O"
  git -C "$O" -c user.email=o@example.com -c user.name=o commit -q --allow-empty -m root
  git remote set-url template "$O"
  run "$UT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"shares no history"* ]]
  [ ! -e .git/MERGE_HEAD ]
}

@test "update_template without a template remote points at setup_remote.sh" {
  run "$UT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"setup_remote.sh"* ]]
}
