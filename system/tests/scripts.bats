#!/usr/bin/env bats

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  V="$BATS_TEST_TMPDIR/vault"
  unset VAULT_ROOT
  cp -r "$REPO/system/tests/fixtures/vault" "$V"
  mkdir -p "$V/system/scripts" "$V/.githooks"
  cp -r "$REPO/system/schemas" "$V/system/schemas"
  cp -r "$REPO/system/scripts/vault_index.py" "$REPO/system/scripts/vaultlib" "$REPO/system/scripts/lint_vault.sh" \
    "$REPO/system/scripts/secret_scan.py" "$V/system/scripts/"
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

@test "hook rejects any staged text file holding a conflict block and names it" {
  printf 'a\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> origin/master\nb\n' > "$V/notes.txt"
  git -C "$V" add notes.txt
  run git -C "$V" commit -qm conflicted
  [ "$status" -ne 0 ]
  [[ "$output" == *"conflict markers in notes.txt"* ]]
  run git -C "$V" rev-parse --verify HEAD
  [ "$status" -ne 0 ]
}

@test "hook checks the staged content, not the working tree" {
  printf '<<<<<<< HEAD\nx\n>>>>>>> other\n' > "$V/notes.txt"
  git -C "$V" add notes.txt
  printf 'clean\n' > "$V/notes.txt"
  run git -C "$V" commit -qm staged-markers
  [ "$status" -ne 0 ]
  [[ "$output" == *"conflict markers in notes.txt"* ]]
}

@test "hook lints the staged blob, not the working copy (#166)" {
  bad_note
  git -C "$V" add wiki/work/concepts/Bad.md
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n---\n# Bad\n[[Index]]\n' > "$V/wiki/work/concepts/Bad.md"
  run git -C "$V" commit -qm fixed-on-disk-only
  [ "$status" -ne 0 ]
  [[ "$output" == *"wiki/work/concepts/Bad.md:2: error: missing required field tags"* ]]
  run git -C "$V" rev-parse -q --verify HEAD
  [ "$status" -ne 0 ]
  git -C "$V" add wiki/work/concepts/Bad.md
  printf -- '---\ntype: concept\n---\n# Bad\n' > "$V/wiki/work/concepts/Bad.md"
  run git -C "$V" commit -qm staged-clean
  [ "$status" -eq 0 ]
}

# A fixture token built by concatenation, so this file never holds the shape itself.
TOKEN="AKIA""IOSFODNN7EXAMPLE"

@test "hook refuses a staged secret shape, naming path, line and shape but never the value (#166)" {
  printf 'first\nkey %s here\n' "$TOKEN" > "$V/notes.txt"
  git -C "$V" add notes.txt
  printf 'fixed on disk only\n' > "$V/notes.txt"
  run git -C "$V" commit -qm secret
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: notes.txt:2: aws_key"* ]]
  [[ "$output" == *"pre-commit: a staged file holds a secret shape"* ]]
  [[ "$output" != *"$TOKEN"* ]]
  run git -C "$V" rev-parse -q --verify HEAD
  [ "$status" -ne 0 ]
}

@test "hook passes a clean commit, and a secret only in the working tree does not block it (#166)" {
  printf 'clean\n' > "$V/notes.txt"
  git -C "$V" add notes.txt
  printf 'key %s\n' "$TOKEN" > "$V/notes.txt"
  printf 'key %s\n' "$TOKEN" > "$V/untracked.txt"
  run git -C "$V" commit -qm clean
  [ "$status" -eq 0 ]
  [ "$(git -C "$V" show HEAD:notes.txt)" = clean ]
}

@test "hook refuses as unscanned when the shape list is empty or unreadable, or the scanner is missing (#166)" {
  echo hi > "$V/README.txt"
  git -C "$V" add README.txt
  cp "$V/system/scripts/vaultlib/redact.py" "$BATS_TEST_TMPDIR/redact.py"
  printf 'import re\nPATTERNS = []\nPEM_BEGIN = re.compile("x^")\n' > "$V/system/scripts/vaultlib/redact.py"
  run git -C "$V" commit -qm empty
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: unscanned (empty shape list)"* ]]
  [[ "$output" == *"pre-commit: the secret scan could not run"* ]]
  cp "$BATS_TEST_TMPDIR/redact.py" "$V/system/scripts/vaultlib/redact.py"
  chmod 000 "$V/system/scripts/vaultlib/redact.py"
  run git -C "$V" commit -qm unreadable
  chmod 644 "$V/system/scripts/vaultlib/redact.py"
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: unscanned (shape list unreadable"* ]]
  rm "$V/system/scripts/secret_scan.py"
  run git -C "$V" commit -qm missing
  [ "$status" -ne 0 ]
  [[ "$output" == *"pre-commit: the secret scan could not run"* ]]
  run git -C "$V" rev-parse -q --verify HEAD
  [ "$status" -ne 0 ]
}

@test "hook allows setext underlines and a start marker without an end marker" {
  mkdir -p "$V/wiki/work/concepts"
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n---\nTitle\n=======\n\n<<<<<<< not a conflict\n[[Index]]\n' > "$V/wiki/work/concepts/Setext.md"
  printf '>>>>>>> end first\n<<<<<<< start after\n' > "$V/order.txt"
  git -C "$V" add wiki/work/concepts/Setext.md order.txt
  run git -C "$V" commit -qm setext
  [ "$status" -eq 0 ]
}

@test "lint warns on a client when raw/inbox holds files, which a client never syncs" {
  mkdir -p "$V/system"
  printf -- '---\ntype: config\ntimezone: "UTC"\nbrief_time: "06:00"\ndebrief_time: "17:00"\nremote_mode: "none"\ndefault_partition: "work"\nmachine_role: "client"\n---\n' > "$V/system/config.md"
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" != *"raw/inbox/ holds"* ]]
  mkdir -p "$V/raw/inbox"
  echo note > "$V/raw/inbox/idea.md"
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"warning: raw/inbox/ holds 1 file(s); a client does not sync them, so write notes in the briefing"* ]]
  printf -- '---\ntype: config\ntimezone: "UTC"\nbrief_time: "06:00"\ndebrief_time: "17:00"\nremote_mode: "none"\ndefault_partition: "work"\nmachine_role: "standalone"\n---\n' > "$V/system/config.md"
  run "$V/system/scripts/lint_vault.sh"
  [[ "$output" != *"raw/inbox/ holds"* ]]
}

@test "hook blocks a Workcell file with invalid frontmatter" {
  mkdir -p "$V/system/agents/workcells"
  printf -- '---\ntype: workcell\n---\n# Bad Workcell\n' > "$V/system/agents/workcells/bad.md"
  git -C "$V" add system/agents/workcells/bad.md
  run git -C "$V" commit -qm bad
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing required field capabilities"* ]]
  run git -C "$V" rev-parse -q --verify HEAD
  [ "$status" -ne 0 ]
}

@test "test.sh runs one suite or one pytest target with the gate's environment (FOUNDRY.md Development)" {
  cp "$REPO/system/scripts/test.sh" "$V/system/scripts/"
  mkdir -p "$V/system/tests/python"
  printf '#!/usr/bin/env bats\n@test env { [ "$TMPDIR" = "%s/.scratch/tmp" ]; [ "$GIT_CEILING_DIRECTORIES" = "%s/.scratch" ]; }\n' "$V" "$V" \
    > "$V/system/tests/env.bats"
  printf 'import os\ndef test_env():\n    assert os.environ["TMPDIR"].endswith("/.scratch/tmp")\n' \
    > "$V/system/tests/python/test_env.py"
  run "$V/system/scripts/test.sh" system/tests/env.bats
  [ "$status" -eq 0 ]
  [ -d "$V/.scratch/tmp" ]
  run "$V/system/scripts/test.sh" system/tests/python/test_env.py
  [ "$status" -eq 0 ]
  run "$V/system/scripts/test.sh"
  [ "$status" -eq 2 ]
  run "$V/system/scripts/test.sh" system/scripts/lint_vault.sh
  [ "$status" -eq 2 ]
  [[ "$output" == *"neither a .bats suite nor a pytest path"* ]]
}

@test "every claude flag for a connector session lives in lib_connector.sh (connector runner spec §4)" {
  run grep -l -e '--permission-mode' -e '--disallowedTools' "$REPO"/system/scripts/*.sh
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf '%s/system/scripts/lib_connector.sh\n%s/system/scripts/run_headless.sh' "$REPO" "$REPO")" ]
}
