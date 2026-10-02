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
