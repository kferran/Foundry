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

@test "<url> over https on a known host suggests its SSH form when that works without a prompt" {
  git init -q --bare "$BATS_TEST_TMPDIR/ssh/me/vault.git"
  git config url."$BATS_TEST_TMPDIR/ssh/".insteadOf git@github.com:  # the SSH form, served locally
  run "$SR" https://github.com/me/vault
  [ "$status" -eq 0 ]
  [ "$(git remote get-url origin)" = https://github.com/me/vault ]
  [[ "$output" == *"not reachable"* ]]
  [[ "$output" == *"hint: git@github.com:me/vault.git works without a prompt; to use it, run system/scripts/setup_remote.sh git@github.com:me/vault.git"* ]]
  run "$SR" https://github.com/me/other
  [ "$status" -eq 0 ]
  [[ "$output" != *"hint:"* ]]
  run "$SR" https://example.com/me/vault
  [ "$status" -eq 0 ]
  [[ "$output" != *"hint:"* ]]
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
  printf '# Managed by vault: %s\nstale\n' "$(pwd -P)" > "$SYSTEMD_USER_DIR/foundry-brief.service"
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  [ -f system/index.db ]
  grep -qE '^[0-9]{8}T[0-9]{6}$' system/logs/commit_runs.since
  grep -qx 'changed foundry-brief.service' <<< "$output"
  grep -q '^ExecStart=' "$SYSTEMD_USER_DIR/foundry-brief.service"
}

@test "update_template re-renders units when only an owned drop-in is installed" {
  template_setup
  mkdir -p "$SYSTEMD_USER_DIR/foundry-brief.service.d"
  printf '# Managed by vault: %s\n[Service]\n' "$(pwd -P)" > "$SYSTEMD_USER_DIR/foundry-brief.service.d/foundry-sync.conf"
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  [[ "$output" != *"units not installed"* ]]
}

@test "update_template reports a unit the new template adds and never installs or enables it" {
  template_setup
  printf '#!/bin/bash\n' > "$STUBS/systemd-analyze"  # verify needs a user session; this test is about the unit list
  chmod +x "$STUBS/systemd-analyze"
  system/scripts/install_units.sh > /dev/null
  rm "$SYSTEMD_USER_DIR"/foundry-nightshift.service "$SYSTEMD_USER_DIR"/foundry-nightshift.timer
  : > "$STUB_SYSTEMCTL_LOG"
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  grep -qx 'new unit available: foundry-nightshift.timer (install it with system/scripts/install_units.sh)' <<< "$output"
  grep -qx 'unchanged foundry-brief.service' <<< "$output"
  [ ! -e "$SYSTEMD_USER_DIR/foundry-nightshift.timer" ]
  [ ! -e "$SYSTEMD_USER_DIR/foundry-nightshift.service" ]
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "update_template on a server re-renders the sync drop-ins of the services it installed" {
  template_setup
  printf '#!/bin/bash\n' > "$STUBS/systemd-analyze"
  chmod +x "$STUBS/systemd-analyze"
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  system/scripts/install_units.sh > /dev/null
  rm "$SYSTEMD_USER_DIR"/foundry-nightshift.service "$SYSTEMD_USER_DIR"/foundry-nightshift.timer
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  grep -qx 'unchanged foundry-brief.service.d/foundry-sync.conf' <<< "$output"
  grep -qx 'unchanged foundry-sync.timer' <<< "$output"
  grep -qx 'new unit available: foundry-nightshift.service (install it with system/scripts/install_units.sh)' <<< "$output"
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

# alerts: today's update alerts in the vault's timezone.
alerts() { cat "system/logs/alerts_$(TZ=America/Denver date +%F).md" 2>/dev/null; }

# upstream_pr <n> <title> <file>: a pull request merged on the template's default branch, as GitHub writes it.
upstream_pr() {
  git -C "$W" checkout -q -b "pr$1"
  printf '%s\n' "$3" > "$W/$3"
  git -C "$W" add -A
  git -C "$W" commit -qm "$2"
  git -C "$W" checkout -q -
  git -C "$W" merge -q --no-ff "pr$1" -m "Merge pull request #$1 from someone/pr$1" -m "$2"
  git -C "$W" push -q
}

@test "--unattended merges and raises one alert listing the merged pull requests (#87)" {
  template_setup
  upstream_pr 7 "Add the export job" a.txt
  upstream_commit b.txt direct
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(cat a.txt)" = a.txt ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  [ "$(alerts | grep -c '\[update\]')" -eq 1 ]
  alerts | grep -qF '[update] template updated: merged 2 change(s): upstream: b.txt; #7 Add the export job'
}

@test "--unattended with nothing new merges nothing and stays silent (#87)" {
  template_setup
  before="$(git rev-parse HEAD)"
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(git rev-parse HEAD)" = "$before" ]
  [ -z "$(alerts)" ]
}

@test "--unattended aborts a conflict, leaves the vault unchanged and alerts (#87)" {
  template_setup
  upstream_commit "my notes.txt" theirs
  printf 'ours\n' > "my notes.txt"
  git commit -qam ours
  before="$(git rev-parse HEAD)"
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ ! -e .git/MERGE_HEAD ]
  [ "$(git rev-parse HEAD)" = "$before" ]
  [ -z "$(git status --porcelain)" ]
  alerts | grep -qF '[update] template update stopped on a conflict in my notes.txt; the vault is unchanged.'
}

@test "--unattended skips with an alert while another run holds run.lock (#87)" {
  template_setup
  upstream_commit new.txt hello
  exec 8> system/run.lock
  flock 8
  UPDATE_LOCK_WAIT=1 run "$UT" --unattended
  exec 8>&-
  [ "$status" -eq 0 ]
  [ ! -e new.txt ]
  alerts | grep -qF '[update] template update skipped: another run held run.lock'
}

@test "--unattended fails with an alert on uncommitted changes and never commits them (#87)" {
  template_setup
  upstream_commit new.txt hello
  echo x > dirty.txt
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ ! -e new.txt ]
  [ "$(git status --porcelain)" = '?? dirty.txt' ]
  alerts | grep -qF '[update] template update failed: working tree is not clean'
}
