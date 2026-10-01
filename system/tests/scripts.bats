#!/usr/bin/env bats

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  V="$BATS_TEST_TMPDIR/vault"
  unset VAULT_ROOT
  cp -r "$REPO/system/tests/fixtures/vault" "$V"
  mkdir -p "$V/system/scripts" "$V/.githooks"
  cp -r "$REPO/system/schemas" "$V/system/schemas"
  cp -r "$REPO/system/scripts/vault_index.py" "$REPO/system/scripts/vaultlib" "$REPO/system/scripts/lint_vault.sh" "$V/system/scripts/"
  cp "$REPO/.githooks/pre-commit" "$V/.githooks/pre-commit"
  git -C "$V" init -q
  git -C "$V" config user.email test@example.com
  git -C "$V" config user.name test
  git -C "$V" config core.hooksPath .githooks
}

bad_note() {
  mkdir -p "$V/wiki/work/concepts"
  printf -- '---\ntype: concept\n---\n# Bad\n' > "$V/wiki/work/concepts/Bad.md"
}

@test "lint passes on the fixture vault" {
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"0 errors"* ]]
}

@test "lint fails on a schema error" {
  bad_note
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"missing required field tags"* ]]
}

@test "dead links are warnings only" {
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n---\n# D\n[[Nowhere]] [[Index]]\n' > "$V/wiki/work/concepts/D.md"
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"warning: dead link [[Nowhere]]"* ]]
}

@test "--staged limits scope to staged files" {
  bad_note
  echo hi > "$V/README.txt"
  git -C "$V" add README.txt
  run "$V/system/scripts/lint_vault.sh" --staged
  [ "$status" -eq 0 ]
}

@test "hook blocks a commit with a schema error" {
  bad_note
  git -C "$V" add wiki/work/concepts/Bad.md
  run git -C "$V" commit -qm bad
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing required field tags"* ]]
  ! git -C "$V" rev-parse --verify HEAD
}

@test "hook blocks a bad note with a space and non-ASCII in its name" {
  mkdir -p "$V/wiki/work/concepts"
  printf -- '---\ntype: concept\n---\n# Bad\n' > "$V/wiki/work/concepts/Café Note.md"
  git -C "$V" add "wiki/work/concepts/Café Note.md"
  run git -C "$V" commit -qm cafe
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing required field tags"* ]]
  ! git -C "$V" rev-parse --verify HEAD
}

@test "hook allows a commit with nothing lintable staged" {
  echo hi > "$V/README.txt"
  git -C "$V" add README.txt
  run git -C "$V" commit -qm readme
  [ "$status" -eq 0 ]
}

@test "hook fails loudly when the linter is missing" {
  rm "$V/system/scripts/lint_vault.sh"
  git -C "$V" add wiki/Index.md
  run git -C "$V" commit -qm index
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing or not executable"* ]]
}
