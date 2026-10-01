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
