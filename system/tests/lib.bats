#!/usr/bin/env bats
load helpers

setup() {
  make_vault
  cd "$V"
  VAULT_ROOT="$(pwd -P)"
  source system/scripts/lib_args.sh
}

@test "args_date accepts real dates only" {
  args_date 2026-10-01
  run args_date 2026-02-30
  [ "$status" -ne 0 ]
  run args_date 2026-1-01
  [ "$status" -ne 0 ]
  run args_date "2026-10-01; rm -rf /"
  [ "$status" -ne 0 ]
  run args_date ""
  [ "$status" -ne 0 ]
}

@test "args_vault_path resolves inside the vault" {
  run args_vault_path wiki/work/concepts/Kafka.md
  [ "$status" -eq 0 ]
  [ "$output" = "wiki/work/concepts/Kafka.md" ]
  cd wiki
  run args_vault_path ../wiki/work/concepts/Kafka.md
  [ "$status" -eq 0 ]
  [ "$output" = "wiki/work/concepts/Kafka.md" ]
}

@test "args_vault_path rejects outside, missing, directories and escaping symlinks" {
  echo x > "$BATS_TEST_TMPDIR/out.md"
  ln -s "$BATS_TEST_TMPDIR/out.md" wiki/work/concepts/Link.md
  run args_vault_path "$BATS_TEST_TMPDIR/out.md"
  [ "$status" -ne 0 ]
  run args_vault_path ../out.md
  [ "$status" -ne 0 ]
  run args_vault_path wiki/nope.md
  [ "$status" -ne 0 ]
  run args_vault_path wiki
  [ "$status" -ne 0 ]
  run args_vault_path wiki/work/concepts/Link.md
  [ "$status" -ne 0 ]
}

@test "args_raw_filename and sanitize" {
  args_raw_filename "Meeting notes 2026-10-01.md"
  run args_raw_filename ".hidden.md"
  [ "$status" -ne 0 ]
  run args_raw_filename "bad:name?.md"
  [ "$status" -ne 0 ]
  run args_raw_filename "café.md"
  [ "$status" -ne 0 ]
  run args_sanitize_filename 'bad:name?.md'
  [ "$output" = "bad_name_.md" ]
  run args_sanitize_filename '..hidden'
  [ "$output" = "hidden" ]
  run args_sanitize_filename '???'
  [ "$output" = "___" ]
  run args_sanitize_filename ''
  [ "$output" = "file" ]
}

lib_config_setup() {
  source system/scripts/lib_config.sh
  mkdir -p system/codebases
  mkdir -p "$BATS_TEST_TMPDIR/repo-a" "$BATS_TEST_TMPDIR/repo-b"
  git -C "$BATS_TEST_TMPDIR/repo-a" init -q
  git -C "$BATS_TEST_TMPDIR/repo-b" init -q
  printf -- '---\ntype: codebase\nname: "a"\npath: "%s"\npartition: work\ndefault: "true"\nstack: [vue3, dotnet]\nsearch_globs: ["*.ts"]\nlayers:\n  ui: "web/"\n---\n' "$BATS_TEST_TMPDIR/repo-a" > system/codebases/a.md
  printf -- '---\ntype: codebase\nname: "b"\npath: "%s"\npartition: personal\nsearch_globs: ["*.py"]\n---\n' "$BATS_TEST_TMPDIR/repo-b" > system/codebases/b.md
  printf -- '---\ntype: codebase\nname: "example"\npath: "~/code/example"\npartition: work\ndefault: "false"\nsearch_globs: ["*"]\n---\n' > system/codebases/example.md
}

@test "config_get returns values, defaults and expands ~" {
  lib_config_setup
  [ "$(config_get timezone)" = "America/Denver" ]
  [ "$(config_get missing fallback)" = "fallback" ]
  run "$V/system/scripts/vault_index.py" set system/config.md template_remote "~/x"
  [ "$(config_get template_remote)" = "$HOME/x" ]
}

@test "config_set writes a scalar" {
  lib_config_setup
  config_set remote_mode keep
  [ "$(config_get remote_mode)" = "keep" ]
}

@test "codebases_list excludes example and codebase_get reads nested and list keys" {
  lib_config_setup
  [ "$(codebases_list | tr '\n' ' ')" = "a b " ]
  [ "$(codebase_get a partition)" = "work" ]
  [ "$(codebase_get a layers.ui)" = "web/" ]
  [ "$(codebase_get a stack)" = "vue3,dotnet" ]
  [ "$(codebase_get b missing dflt)" = "dflt" ]
  run codebase_get "../config" timezone
  [ "$status" -ne 0 ]
}

@test "codebase_default picks default true, or the only codebase" {
  lib_config_setup
  [ "$(codebase_default)" = "a" ]
  rm system/codebases/a.md
  [ "$(codebase_default)" = "b" ]
}

@test "config_validate passes good config and fails a bad timezone" {
  lib_config_setup
  run config_validate
  [ "$status" -eq 0 ]
  "$V/system/scripts/vault_index.py" set system/config.md timezone "Mars/Olympus" || true
  sed -i 's#^timezone: .*#timezone: "Mars/Olympus"#' system/config.md
  run config_validate
  [ "$status" -eq 1 ]
}

@test "crash_trap: a set -e stop exits 70 and alerts once a day per unit (#436 S3)" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'f() { false; }' 'f' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  [ "$(grep -c '\[smoke\] foundry-x crashed: exit 1 at line [0-9]*; journalctl --user -u foundry-x' system/logs/alerts_*.md)" -eq 1 ]
}

@test "crash_trap: a failure inside || does not trip the trap (#436 S3)" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'rc=0' 'false || rc=$?' 'exit "$rc"' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 1 ]
  [ -z "$(ls system/logs/alerts_*.md 2>/dev/null)" ]
}

@test "crash_trap: a crash whose alert cannot be written still exits 70 (#436 S3 review)" {
  need_non_root
  mkdir -p system/logs
  chmod a-w system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'false' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  chmod u+w system/logs
  [ "$status" -eq 70 ]
}

@test "crash_trap: a failure inside a process substitution raises no alert (#436 S3 review)" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'while read -r _; do :; done < <(false; echo x)' 'exit 0' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 0 ]
  [ -z "$(ls system/logs/alerts_*.md 2>/dev/null)" ]
}

@test "crash_trap: an unset variable under set -u exits 70 and alerts once a day (no ERR fires)" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'echo "$nope"' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  [ "$(grep -c '\[smoke\] foundry-x crashed: exit 1; journalctl --user -u foundry-x' system/logs/alerts_*.md)" -eq 1 ]
}

@test "crash_trap --exit-only: a failed command is no crash; an unset variable is; an explicit exit stands (#436 S3)" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -uo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap --exit-only foundry-x' 'false' 'grep -q nothing /dev/null' 'case "${1:-}" in u) echo "$nope" ;; e) exit 3 ;; esac' \
    'exit 0' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 0 ]
  run bash "$BATS_TEST_TMPDIR/c.sh" e
  [ "$status" -eq 3 ]
  [ -z "$(ls system/logs/alerts_*.md 2>/dev/null)" ]
  run bash "$BATS_TEST_TMPDIR/c.sh" u
  [ "$status" -eq 70 ]
  [ "$(grep -c '\[smoke\] foundry-x crashed: exit 1; journalctl --user -u foundry-x' system/logs/alerts_*.md)" -eq 1 ]
}

@test "crash_trap: a bad arithmetic expression exits 70 and alerts (no ERR fires)" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'x=$(( 1/0 ))' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  grep -q '\[smoke\] foundry-x crashed: exit 1; journalctl --user -u foundry-x' system/logs/alerts_*.md
}

@test "crash_trap: a TERM is a stop, not a crash, even after a failed command" {
  mkdir -p system/logs
  # The TERM lands while a child runs after a failed command: the EXIT trap then reads that command's 3.
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'sh -c "exit 3" || sh -c "kill -TERM \$PPID; sleep 0.2"' 'exit 0' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 143 ]
  [ -z "$(ls system/logs/alerts_*.md 2>/dev/null)" ]
}

@test "crash_trap: a handled exit 1 from a function stays 1 with no crash alert" {
  mkdir -p system/logs
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'f() { echo "handled" >&2; exit 1; }' 'f' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 1 ]
  [ -z "$(ls system/logs/alerts_*.md 2>/dev/null)" ]
}

@test "crash_trap: the fetch workdir is still removed when an unset variable crashes the script" {
  mkdir -p system/logs "$BATS_TEST_TMPDIR/bin"
  # fetch_workdir's mktemp -p /tmp, sent under the test's directory (/tmp can be read-only in a sandbox)
  printf '#!/bin/bash\nexec %q -d -p %q\n' "$(command -v mktemp)" "$BATS_TEST_TMPDIR" > "$BATS_TEST_TMPDIR/bin/mktemp"
  chmod +x "$BATS_TEST_TMPDIR/bin/mktemp"
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'fetch_workdir' "echo \"\$work\" > '$BATS_TEST_TMPDIR/w'" 'echo "$nope"' > "$BATS_TEST_TMPDIR/c.sh"
  PATH="$BATS_TEST_TMPDIR/bin:$PATH" run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 70 ]
  [ -n "$(cat "$BATS_TEST_TMPDIR/w")" ]
  [ ! -e "$(cat "$BATS_TEST_TMPDIR/w")" ]
  grep -q 'foundry-x crashed:' system/logs/alerts_*.md
}

@test "crash_trap: a cleanup that fails leaves a clean run at 0 with no alert (#484 review)" {
  mkdir -p system/logs
  : > "system/logs/alerts_$(date +%F).md"
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'crash_trap foundry-x' 'exit_cleanup=false' 'exit 0' > "$BATS_TEST_TMPDIR/c.sh"
  run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 0 ]
  run grep -c 'crashed:' system/logs/alerts_"$(date +%F)".md
  [ "$output" = "0" ]
}

@test "fetch_workdir without crash_trap keeps the script's exit and removes the workdir (#484 review)" {
  mkdir -p "$BATS_TEST_TMPDIR/bin"
  printf '#!/bin/bash\nexec %q -d -p %q\n' "$(command -v mktemp)" "$BATS_TEST_TMPDIR" > "$BATS_TEST_TMPDIR/bin/mktemp"
  chmod +x "$BATS_TEST_TMPDIR/bin/mktemp"
  printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'source system/scripts/lib_fetch.sh' 'FETCH_TAG=smoke' \
    'fetch_workdir' "echo \"\$work\" > '$BATS_TEST_TMPDIR/w'" 'exit 3' > "$BATS_TEST_TMPDIR/c.sh"
  PATH="$BATS_TEST_TMPDIR/bin:$PATH" run bash "$BATS_TEST_TMPDIR/c.sh"
  [ "$status" -eq 3 ]
  [ -n "$(cat "$BATS_TEST_TMPDIR/w")" ]
  [ ! -e "$(cat "$BATS_TEST_TMPDIR/w")" ]
}

@test "git_github_slug reads https and ssh forms (#436 S2)" {
  source system/scripts/lib_git.sh
  run git_github_slug https://github.com/o/r.git
  [ "$status" -eq 0 ]
  [ "$output" = o/r ]
  run git_github_slug https://github.com/o/r
  [ "$output" = o/r ]
  run git_github_slug git@github.com:o/r.git
  [ "$output" = o/r ]
  run git_github_slug ssh://git@github.com/o/r
  [ "$output" = o/r ]
  run git_github_slug https://gitlab.com/o/r.git
  [ "$status" -eq 0 ]
  [ "$output" = "" ]
  run git_github_slug "$BATS_TEST_TMPDIR/up.git"
  [ "$status" -eq 0 ]
  [ "$output" = "" ]
}
