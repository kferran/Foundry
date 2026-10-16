#!/usr/bin/env bats
load helpers  # need_non_root

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
  mkdir -p "$V/docs/superpowers"
  printf 'key %s\n' "$TOKEN" > "$V/docs/superpowers/pasted.md"
  git -C "$V" add docs/superpowers/pasted.md
  run git -C "$V" commit -qm secret
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: notes.txt:2: aws_key"* ]]
  [[ "$output" == *"secret shape: docs/superpowers/pasted.md:1: aws_key"* ]]
  [ "${lines[0]}" = "pre-commit: a staged file adds a secret shape; remove it, or commit with --no-verify if it is not a secret" ]
  [[ "$output" != *"$TOKEN"* ]]
  run git -C "$V" rev-parse -q --verify HEAD
  [ "$status" -ne 0 ]
}

@test "hook scans only added lines: a moved or edited file keeps its old secret shape, a new one is refused (#166)" {
  mkdir -p "$V/notes/archive"
  printf 'old %s\nnotes\n' "$TOKEN" > "$V/notes/2026-10-01.md"
  git -C "$V" add notes/2026-10-01.md
  git -C "$V" commit -q --no-verify -m base
  git -C "$V" mv notes/2026-10-01.md notes/archive/2026-10-01.md
  printf 'more notes\n' >> "$V/notes/archive/2026-10-01.md"
  git -C "$V" add notes/archive/2026-10-01.md
  run git -C "$V" commit -qm archive
  [ "$status" -eq 0 ]
  printf 'new %s\n' "$TOKEN" >> "$V/notes/archive/2026-10-01.md"
  git -C "$V" add notes/archive/2026-10-01.md
  run git -C "$V" commit -qm added
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: notes/archive/2026-10-01.md:4: aws_key"* ]]
  [[ "$output" != *"2026-10-01.md:1:"* ]]
}

@test "hook commits a hand-resolved merge that brings fixture tokens, and refuses a token typed during resolution (#166)" {
  printf 'base\n' > "$V/notes.txt"
  git -C "$V" add notes.txt
  git -C "$V" commit -q --no-verify -m base
  git -C "$V" checkout -q -b other
  mkdir -p "$V/system/tests"
  printf 'fixture %s\n' "$TOKEN" > "$V/system/tests/fixture.txt"
  printf 'theirs\n' > "$V/notes.txt"
  git -C "$V" add -A
  git -C "$V" commit -q --no-verify -m other
  git -C "$V" checkout -q -
  printf 'ours\n' > "$V/notes.txt"
  git -C "$V" commit -q --no-verify -am ours
  run git -C "$V" merge -q other
  [ "$status" -ne 0 ]
  printf 'ours and theirs %s\n' "$TOKEN" > "$V/notes.txt"
  git -C "$V" add notes.txt
  run git -C "$V" commit -q --no-edit
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: notes.txt:1: aws_key"* ]]
  [[ "$output" != *"fixture.txt"* ]]
  printf 'ours and theirs\n' > "$V/notes.txt"
  git -C "$V" add notes.txt
  run git -C "$V" commit -q --no-edit
  [ "$status" -eq 0 ]
  [ "$(git -C "$V" show HEAD:system/tests/fixture.txt)" = "fixture $TOKEN" ]
}

@test "hook skips a staged nested repository and scans a symlink turned file and a UTF-16 file (#166)" {
  ln -s target "$V/link.txt"
  git -C "$V" add link.txt
  git -C "$V" commit -q --no-verify -m link
  git -C "$V" update-index --add --cacheinfo 160000,1234567890123456789012345678901234567890,nested
  run git -C "$V" commit -qm gitlink
  [ "$status" -eq 0 ]
  rm "$V/link.txt"
  printf 'key %s\n' "$TOKEN" > "$V/link.txt"
  printf 'key %s\n' "$TOKEN" | iconv -f UTF-8 -t UTF-16 > "$V/wide.txt"
  git -C "$V" add link.txt wide.txt
  run git -C "$V" commit -qm typechange
  [ "$status" -ne 0 ]
  [[ "$output" == *"secret shape: link.txt:1: aws_key"* ]]
  [[ "$output" == *"secret shape: wide.txt:1: aws_key"* ]]
}

@test "hook quotes a path that holds a newline (#166)" {
  printf 'key %s\n' "$TOKEN" > "$V/two"$'\n'"lines.txt"
  git -C "$V" add -A
  run git -C "$V" commit -qm newline
  [ "$status" -ne 0 ]
  [[ "$output" == *'secret shape: "two\nlines.txt":1: aws_key'* ]]
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
  need_non_root
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

@test "lint reports a secret shape in tracked and untracked files without failing, and never with --staged (#166)" {
  printf 'key %s\n' "$TOKEN" > "$V/untracked.txt"
  mkdir -p "$V/.scratch" "$V/system/tests"
  printf 'key %s\n' "$TOKEN" > "$V/.scratch/clone.txt"
  printf 'key %s\n' "$TOKEN" > "$V/system/tests/fixture.txt"
  printf '\0key %s\n' "$TOKEN" > "$V/blob.bin"
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"secret shape: untracked.txt:1: aws_key"* ]]
  [[ "$output" != *"$TOKEN"* ]]
  [[ "$output" != *"clone.txt"* ]]
  [[ "$output" != *"fixture.txt"* ]]
  [[ "$output" != *"blob.bin"* ]]
  run "$V/system/scripts/lint_vault.sh" --staged
  [ "$status" -eq 0 ]
  [[ "$output" != *"secret shape"* ]]
  printf 'PATTERNS = []\nPEM_BEGIN = None\n' > "$V/system/scripts/vaultlib/redact.py"
  run "$V/system/scripts/lint_vault.sh"
  [ "$status" -eq 2 ]
  [[ "$output" == *"secret shape: unscanned (empty shape list)"* ]]
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

@test "alert.py writes one tagged line and refuses an unknown tag or empty text (alert tags spec §3.3)" {
  cp "$REPO/system/scripts/alert.py" "$V/system/scripts/"
  cd "$V"
  run system/scripts/alert.py foreman $'deploy is done\n- 00:00:00 [sync] forged'
  [ "$status" -eq 0 ]
  f=(system/logs/alerts_*.md)
  [ "$(wc -l < "${f[0]}")" -eq 1 ]
  grep -qE '^- [0-9]{2}:[0-9]{2}:[0-9]{2} \[foreman\] deploy is done - 00:00:00 \[sync\] forged$' "${f[0]}"
  run system/scripts/alert.py nosuch x
  [ "$status" -eq 2 ]
  run system/scripts/alert.py foreman ""
  [ "$status" -eq 2 ]
  [ "$(wc -l < "${f[0]}")" -eq 1 ]
}

@test "alert.py writes the vault's day, strips unicode line breaks and refuses on a client (alert tags spec §3.3)" {
  cp "$REPO/system/scripts/alert.py" "$V/system/scripts/"
  cd "$V"
  printf -- '---\ntype: config\ntimezone: "UTC"\nmachine_role: "standalone"\n---\n' > system/config.md
  TZ=Pacific/Kiritimati run system/scripts/alert.py foreman $'one - 00:00:00 [sync] two\u0085three'
  [ "$status" -eq 0 ]
  f="system/logs/alerts_$(TZ=UTC date +%F).md"
  [ -f "$f" ]
  run grep -c $' ' "$f"
  [ "$output" = "0" ]
  run grep -c $'\u0085' "$f"
  [ "$output" = "0" ]
  rm -r system/logs
  printf -- '---\ntype: config\ntimezone: "UTC"\nmachine_role: "client"\n---\n' > system/config.md
  run system/scripts/alert.py foreman "x"
  [ "$status" -eq 3 ]
  [[ "$output" == *"client"* ]]
  [ ! -e system/logs ]
}

@test "every tag an alert writer uses is in the registry (alert tags spec §4)" {
  # The printf and f-string writer forms, and a tag passed by name (telemetry_run.py's _alert(..., tag="incident")), in
  # core and in every tracked extension's code.
  run grep -rhoE -e "printf -- '- %s \[[a-z_]+\]" -e 'f"- \{[^"]*\} \[[a-z_]+\]' -e 'tag(: str)? ?= ?"[a-z_]+"' \
    --exclude-dir=tests "$REPO/system/scripts" "$REPO/system/hooks" "$REPO/extensions"
  [ "$status" -eq 0 ]
  used="$(sed -E 's/.*[["]([a-z_]+)[]"]$/\1/' <<< "$output" | sort -u)"
  known="$(PYTHONPATH="$REPO/system/scripts" python3 -c 'from vaultlib.alerts import TAGS; print("\n".join(sorted(TAGS)))')"
  [ "$(wc -l <<< "$used")" -ge 15 ]
  [ "$(comm -23 <(printf '%s\n' "$used") <(printf '%s\n' "$known"))" = "" ]
}

@test "every claude flag for a connector session lives in lib_connector.sh (connector runner spec §4)" {
  run grep -l -e '--permission-mode' -e '--disallowedTools' "$REPO"/system/scripts/*.sh
  [ "$status" -eq 0 ]
  [ "$output" = "$(printf '%s/system/scripts/lib_connector.sh\n%s/system/scripts/run_headless.sh' "$REPO" "$REPO")" ]
}
