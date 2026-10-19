#!/usr/bin/env bats
# eval_ingest.sh and the golden cases (ingest evals spec §3, §4). The stub claude tests the harness only; the model
# is tested by hand with the real claude (plan Task 6).
load helpers

setup() {
  make_vault
  cd "$V"
  mkdir -p system/tests/fixtures
  cp -r "$REPO/system/tests/fixtures/vault" system/tests/fixtures/vault
  export CLAUDE_BIN="$REPO/system/tests/stub_claude" STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_STDIN="$BATS_TEST_TMPDIR/stdin"
  EI="$V/system/scripts/eval_ingest.sh"
  LOG="system/logs/evals/ingest-$(date +%Y-%m).jsonl"
}

# stub_case <name> [<dir>]: an inbox note the stub answers with a new work concept (STUB_MODE=write).
stub_case() {
  local d="${2:-system/tests/golden/ingest}/$1"
  mkdir -p "$d/inputs/inbox"
  printf 'A note about the export queue.\n' > "$d/inputs/inbox/note.md"
  printf 'min_pass_rate: 1.0\npublish: published\ncreates:\n  wiki/work/concepts/New.md: {type: concept, partition: work}\nwalls: true\narchived: [note.md]\n' > "$d/expect.yaml"
}

@test "a case runs through one intake tick, is recorded and prints its pass rate" {
  stub_case one
  run "$EI" --runs 1
  [ "$status" -eq 0 ]
  [ "$output" = 'one: 1/1 (min 1) PASS, $0.00 a run' ]
  [ "$(wc -l < "$LOG")" -eq 1 ]
  [ "$(jq -r '.case, .repeat, (.run_ids | length), .publish[0], (.failed | length)' "$LOG" | tr '\n' ' ')" = 'one 1 1 published 0 ' ]
  grep -q 'raw/inbox/.staging/note.md' "$STUB_ARGS"   # the tick, not the harness, staged the input
}

@test "a failed check fails the case and names the check in the record" {
  stub_case one
  printf 'min_pass_rate: 1.0\npublish: noop\n' > system/tests/golden/ingest/one/expect.yaml
  run "$EI" --runs 2
  [ "$status" -eq 1 ]
  [ "$output" = 'one: 0/2 (min 1) FAIL, $0.00 a run' ]
  jq -r '.failed[0]' "$LOG" | grep -q '^publish: .* is published, want noop$'
}

@test "--max-usd 0 skips every case and exits 1" {
  stub_case one
  stub_case two
  run "$EI" --max-usd 0
  [ "$status" -eq 1 ]
  [ "$output" = "$(printf 'one: skipped (budget)\ntwo: skipped (budget)')" ]
  [ "$(jq -r .skipped "$LOG" | sort -u)" = true ]
}

@test "a case without expect.yaml is refused by name, and --case and --local pick the cases" {
  stub_case one
  stub_case mine system/tests/golden/local
  run "$EI" --runs 1 --case mine
  [ "$status" -eq 2 ]
  [ "$output" = 'eval_ingest: no case to run' ]
  run "$EI" --runs 1 --case mine --local
  [ "$status" -eq 0 ]
  [ "$output" = 'mine: 1/1 (min 1) PASS, $0.00 a run' ]
  mkdir -p system/tests/golden/ingest/broken
  run "$EI" --runs 1
  [ "$status" -eq 2 ]
  [ "$output" = 'eval_ingest: case broken has no expect.yaml' ]
}

@test "a tick that runs no ingest fails its case" {
  stub_case one
  rm system/tests/golden/ingest/one/inputs/inbox/note.md
  run "$EI" --runs 1
  [ "$status" -eq 1 ]
  [ "$(jq -r '.failed[0]' "$LOG")" = 'runs: the tick ran no ingest' ]
}

@test "every golden case has its parts and an expect.yaml whose keys all load" {
  cases="$(ls "$REPO/system/tests/golden/ingest" | tr '\n' ' ')"
  [ "$cases" = "alias-patch batch-merge correction-patch format-docx format-pdf format-pptx format-xlsx friction-flag inbox-injection no-shrink no-shrink-long-note restated-noop shared-placement slack-capture supersede wall-respect " ]
  for d in "$REPO"/system/tests/golden/ingest/*/; do
    [ -f "$d/README.md" ]
    [ -d "$d/vault" ]
    [ -d "$d/inputs" ] || [ -f "$d/make_input.py" ]
    run "$REPO/system/scripts/eval_check.py" check "$V" "$d/expect.yaml" "$d/vault" no-such-run
    [ "$status" -le 1 ]   # check lines, never a parse error (2)
    [[ "$output" != *"expect: unknown keys"* ]]
    rate="$("$REPO/system/scripts/eval_check.py" rate "$d/expect.yaml")"
    [[ "$rate" == 1.0 || "$rate" == 0.67 ]]
  done
  for c in wall-respect inbox-injection no-shrink no-shrink-long-note shared-placement; do
    [ "$("$REPO/system/scripts/eval_check.py" rate "$REPO/system/tests/golden/ingest/$c/expect.yaml")" = 1.0 ]
  done
}

@test "a format case's input is made by make_input.py and converted by the tick (#257)" {
  mkdir -p system/tests/golden/ingest
  cp -r "$REPO/system/tests/golden/ingest/format-docx" system/tests/golden/ingest/
  run "$EI" --runs 1
  [ "$status" -eq 1 ]   # the stub writes no note holding the fact
  grep -q 'raw/inbox/.staging/warehouse-report.docx.md' "$STUB_ARGS"
  [ "$(jq -r '.failed[]' "$LOG" | grep -c '^archived:')" -eq 0 ]
  jq -r '.failed[]' "$LOG" | grep -q '^body_contains: no published wiki/\*\* holds .412.$'
}

@test "a format case that cannot run here is skipped with its reason" {
  mkdir -p system/tests/golden/ingest/cannot
  printf 'min_pass_rate: 1.0\n' > system/tests/golden/ingest/cannot/expect.yaml
  printf 'import sys\nprint("converter missing")\nsys.exit(3)\n' > system/tests/golden/ingest/cannot/make_input.py
  run "$EI" --runs 1
  [ "$status" -eq 1 ]
  [ "$output" = 'cannot: skipped (converter missing)' ]
}

@test "the template ships no vault-derived case" {
  grep -qxF 'system/tests/golden/local/' "$REPO/.gitignore"
  run git -C "$REPO" ls-files system/tests/golden/local
  [ -z "$output" ]
}
