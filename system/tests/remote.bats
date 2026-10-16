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
  need_user_systemd
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
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-smoke.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
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

# The unattended update commits a dirty tree the way the sync does (audit C4 spec §2), so these cases run the
# pre-commit hook and may hold a pending published run.
hooks_on() {
  cp -r "$REPO/.githooks" .githooks
  git config core.hooksPath .githooks
  git add -A
  git commit -qm hooks
}

pending_run() {  # <run_id>: a published brief run whose briefing is pending commit
  mkdir -p "system/logs/runs/$1" briefings
  echo 20200101T000000 > system/logs/commit_runs.since
  printf '{"run_id": "%s", "status": "published", "published": ["briefings/2026-10-04.md"], "conflicts": [], "problems": []}\n' "$1" > "system/logs/runs/$1/publish.json"
  printf -- '---\ntype: briefing\ndate: "2026-10-04"\n---\n# Briefing\n' > briefings/2026-10-04.md
}

note() {  # <name> <frontmatter>: a work concept with the given frontmatter lines
  mkdir -p wiki/work/concepts
  printf -- '---\n%s\n---\n# %s\n[[Index]]\n' "$2" "$1" > "wiki/work/concepts/$1.md"
}

@test "--unattended commits uncommitted changes as the sync does, then merges (audit C4 spec §4)" {
  template_setup
  hooks_on
  upstream_commit new.txt hello
  pending_run 20261004T060000-brief-cd34
  note Fresh $'type: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work'
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
  [ -z "$(git status --porcelain)" ]
  [ "$(git log --first-parent --format=%s -3 | tr '\n' '|')" = "Merge remote-tracking branch 'template/$(git -C "$W" rev-parse --abbrev-ref HEAD)'|sync(standalone): 1 file(s)|brief 2026-10-04: briefings/2026-10-04.md|" ]
  [ "$(alerts | grep -c '\[update\]')" -eq 1 ]
  alerts | grep -qF '[update] template updated: committed first: brief 2026-10-04: briefings/2026-10-04.md; sync(standalone): 1 file(s); merged 1 change(s): upstream: new.txt'
}

@test "--unattended stops on a note the hook refuses, before fetching (audit C4 spec §4)" {
  template_setup
  hooks_on
  upstream_commit new.txt hello
  note Bad 'type: concept'
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ -z "$(git for-each-ref refs/remotes/template)" ]
  [ ! -e new.txt ]
  [ "$(git status --porcelain)" = '?? wiki/work/concepts/Bad.md' ]
  alerts | grep -qF '[update] template update failed: the sync commit was refused: '
  alerts | grep -q 'Bad.md'
}

# refused_run: a published run whose note Bad.md the hook refuses, beside an ordinary new note (audit C7).
refused_run() {
  pending_run 20261004T060000-brief-cd34
  printf '{"run_id": "20261004T060000-brief-cd34", "status": "published", "published": ["wiki/work/concepts/Bad.md"], "conflicts": [], "problems": []}\n' > system/logs/runs/20261004T060000-brief-cd34/publish.json
  rm briefings/2026-10-04.md
  note Bad 'type: concept'
  note Fresh $'type: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work'
}

@test "--unattended leaves a published run the hook refused uncommitted, merges and names it (audit C7 spec §3, #136 2026-10-15)" {
  template_setup
  hooks_on
  upstream_commit new.txt hello
  refused_run
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
  [ "$(git status --porcelain)" = '?? wiki/work/concepts/Bad.md' ]
  [ "$(git log --first-parent --format=%s -2 | tr '\n' '|')" = "Merge remote-tracking branch 'template/$(git -C "$W" rev-parse --abbrev-ref HEAD)'|sync(standalone): 1 file(s)|" ]
  [ "$(alerts | grep -c '\[update\]')" -eq 1 ]
  alerts | grep -qF '[update] template updated: committed first: sync(standalone): 1 file(s); a published run was refused by the pre-commit hook and left uncommitted: wiki/work/concepts/Bad.md (the hook'"'"'s line is in today'"'"'s [commit_runs] alert); merged 1 change(s): upstream: new.txt'
  [ "$(alerts | grep -c ' \[commit_runs\] run ')" -eq 1 ]
}

@test "--unattended ends in a failed merge naming a refused note the template also changes (audit C7 spec §2, #136 2026-10-15)" {
  template_setup
  hooks_on
  mkdir -p "$W/wiki/work/concepts"
  upstream_commit wiki/work/concepts/Bad.md theirs
  refused_run
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ ! -e .git/MERGE_HEAD ]
  [ "$(git log -1 --format=%s)" = "sync(standalone): 1 file(s)" ]
  [ "$(git status --porcelain)" = '?? wiki/work/concepts/Bad.md' ]
  alerts | grep -qF '[update] template update failed: committed first: sync(standalone): 1 file(s); a published run was refused by the pre-commit hook and left uncommitted: wiki/work/concepts/Bad.md'
  alerts | grep '\[update\]' | grep -qE "git merge template/[^ ]+ was refused: .* wiki/work/concepts/Bad.md$"
}

@test "--unattended leaves a file with a secret shape uncommitted, merges and names it without the value (#166, #136 2026-10-15)" {
  template_setup
  hooks_on
  upstream_commit new.txt hello
  note Leak $'type: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\nsource: AKIA''IOSFODNN7EXAMPLE'
  note Fresh $'type: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work'
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(cat new.txt)" = hello ]
  [ "$(git status --porcelain)" = '?? wiki/work/concepts/Leak.md' ]
  [ "$(git log --first-parent --format=%s -2 | tail -n 1)" = "sync(standalone): 1 file(s)" ]
  [ "$(alerts | grep -c '\[update\]')" -eq 1 ]
  alerts | grep -qF '[update] template updated: committed first: sync(standalone): 1 file(s); a file adds a secret shape and was left out of the commit: secret shape: wiki/work/concepts/Leak.md:6: aws_key; merged 1 change(s): upstream: new.txt'
  [ -z "$(alerts | grep 'IOSFODNN7EXAMPLE')" ]
}

@test "--unattended with nothing new to merge still reports the commits it made (audit C4 review)" {
  template_setup
  hooks_on
  pending_run 20261004T060000-brief-cd34
  note Fresh $'type: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work'
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ -z "$(git status --porcelain)" ]
  [ "$(alerts | grep -c '\[update\]')" -eq 1 ]
  alerts | grep -qF '[update] template update: committed first: brief 2026-10-04: briefings/2026-10-04.md; sync(standalone): 1 file(s); nothing new to merge'
}

@test "--unattended names the run commits that landed when the sync commit is refused (audit C4 review)" {
  template_setup
  hooks_on
  upstream_commit new.txt hello
  pending_run 20261004T060000-brief-cd34
  note Bad 'type: concept'
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ -z "$(git for-each-ref refs/remotes/template)" ]
  [ "$(git log -1 --format=%s)" = "brief 2026-10-04: briefings/2026-10-04.md" ]
  alerts | grep -qF '[update] template update failed: committed first: brief 2026-10-04: briefings/2026-10-04.md; the sync commit was refused: '
}

@test "--unattended: no git child of the update inherits run.lock's fd 9, with a pending run and a dirty tree (audit C4 spec §4)" {
  export REAL_GIT="$(command -v git)"
  template_setup
  hooks_on
  upstream_commit new.txt hello
  pending_run 20261004T060000-brief-cd34
  echo x > dirty.txt
  ln -s "$REPO/system/tests/stub_git" "$STUBS/git"
  export WRAP_EACH='[[ ! -e /proc/self/fd/9 ]] || echo "$1" >> "$BATS_TEST_TMPDIR/fd9"'
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ ! -e "$BATS_TEST_TMPDIR/fd9" ]
}

@test "--unattended alerts when a step after the merge fails, and names the merged changes (#87)" {
  template_setup
  upstream_commit system/scripts/commit_runs.py $'#!/bin/bash\nexit 3'
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  alerts | grep -qF '[update] template update failed: merged upstream: system/scripts/commit_runs.py, then commit_runs.py --init-cutover failed'
}

@test "--unattended names a unit the update adds in its alert (#87)" {
  template_setup
  printf '#!/bin/bash\n' > "$STUBS/systemd-analyze"
  chmod +x "$STUBS/systemd-analyze"
  system/scripts/install_units.sh > /dev/null
  rm "$SYSTEMD_USER_DIR"/foundry-nightshift.service "$SYSTEMD_USER_DIR"/foundry-nightshift.timer
  upstream_commit new.txt hello
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  alerts | grep -qF 'new unit available: foundry-nightshift.service, foundry-nightshift.timer (install with system/scripts/install_units.sh)'
}

# A vault with a README.md in its base commit and no .gitattributes, as on the first update after #90.
readme_setup() {
  printf 'landing\n' > README.md
  template_setup
}

@test "update_template keeps a README the vault changed, the first update included, and leaves no merge config (#90)" {
  readme_setup
  upstream_commit README.md "new landing"
  printf 'my vault\n' > README.md
  git commit -qam "my README"
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat README.md)" = "my vault" ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  run git config --get merge.ours.driver
  [ "$status" -eq 1 ]
  run git config --get core.attributesFile
  [ "$status" -eq 1 ]
  [ ! -e .gitattributes ]
}

@test "update_template gives an unedited README the template's new one (#90)" {
  readme_setup
  upstream_commit README.md "new landing"
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat README.md)" = "new landing" ]
}

@test "without the driver, a README changed on both sides still conflicts, as in a sync merge (#90)" {
  readme_setup
  upstream_commit README.md "theirs"
  printf 'ours\n' > README.md
  git commit -qam ours
  git fetch -q template
  run git merge --no-edit "template/$(git -C "$W" rev-parse --abbrev-ref HEAD)"
  [ "$status" -ne 0 ]
  grep -qx '<<<<<<< HEAD' README.md
  git merge --abort
}

@test "a template update brings a tracked extension, keeps a vault-only one and links the enabled skills (extensions spec §3, §7)" {
  template_setup
  mkdir -p extensions/local
  printf -- '---\nname: local\ncontract: 1\n---\nA vault-only extension.\n' > extensions/local/extension.md
  git add extensions/local
  git commit -qm "vault: a vault-only extension"
  mkdir -p "$W/extensions"
  cp -r "$REPO/system/tests/fixtures/extensions/demo" "$W/extensions/demo"
  upstream_commit new.txt hello
  sed -i 's/^default_partition: "personal"$/&\nextensions: ["demo"]/' system/config.md
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(git log -1 --format=%s -- extensions/demo/extension.md)" != "" ]
  [ -f extensions/local/extension.md ]
  [ "$(readlink .claude/skills/demo-skill)" = "../../extensions/demo/skills/demo-skill" ]
}

@test "after a template update, a listed extension that cannot load is alerted (extensions spec §4)" {
  template_setup
  upstream_commit new.txt hello
  sed -i 's/^default_partition: "personal"$/&\nextensions: ["nosuch"]/' system/config.md
  run "$UT"
  [ "$status" -eq 0 ]
  grep -qE '^- [0-9:]{8} \[extensions\] .*nosuch' "system/logs/alerts_$(date +%F).md"
}
