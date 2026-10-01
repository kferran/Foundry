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
