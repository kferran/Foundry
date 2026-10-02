#!/usr/bin/env bats
# check_deps.sh (spec §6.2) and verify_setup.sh (spec §6.14).

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  CD="$REPO/system/scripts/check_deps.sh"
  # A PATH holding exactly the tools under test: real ones linked in, the rest stubbed.
  BIN="$BATS_TEST_TMPDIR/bin"
  mkdir -p "$BIN"
  for c in git jq bats systemctl python3 flock timeout systemd-analyze; do
    ln -s "$(command -v "$c")" "$BIN/$c"
  done
  for c in claude gcalcli hyprctl; do
    printf '#!/bin/bash\n' > "$BIN/$c"
    chmod +x "$BIN/$c"
  done
}

@test "check_deps: every item present reports ok and --strict passes" {
  run env PATH="$BIN" "$CD" --strict
  [ "$status" -eq 0 ]
  for item in claude git jq bats gcalcli systemctl hyprctl python3 flock timeout pyyaml pytest fts5 systemd-analyze; do
    grep -qx "ok $item" <<< "$output"
  done
}

@test "check_deps: a missing required tool gets an install hint and fails only --strict" {
  rm "$BIN/gcalcli"
  run env PATH="$BIN" "$CD"
  [ "$status" -eq 0 ]
  grep -qx 'missing gcalcli pipx install gcalcli' <<< "$output"
  run env PATH="$BIN" "$CD" --strict
  [ "$status" -eq 1 ]
}

@test "check_deps: optional session backends are reported but never fail --strict" {
  printf '#!/bin/bash\n' > "$BIN/tmux"
  chmod +x "$BIN/tmux"
  run env PATH="$BIN" "$CD" --strict
  [ "$status" -eq 0 ]
  grep -qx 'ok tmux' <<< "$output"
  grep -q '^optional herdr ' <<< "$output"
}

@test "check_deps: python module checks run against the python3 on PATH" {
  real="$(command -v python3)"
  rm "$BIN/python3"
  printf '#!/bin/bash\nfor a in "$@"; do [[ "$a" == "import yaml" ]] && exit 1; done\nexec %s "$@"\n' "$real" > "$BIN/python3"
  chmod +x "$BIN/python3"
  run env PATH="$BIN" "$CD" --strict
  [ "$status" -eq 1 ]
  grep -qx 'missing pyyaml sudo pacman -S python-yaml' <<< "$output"
  grep -qx 'ok pytest' <<< "$output"
  grep -qx 'ok fts5' <<< "$output"
}

@test "check_deps: without python3 every python check is missing" {
  rm "$BIN/python3"
  run env PATH="$BIN" "$CD"
  [ "$status" -eq 0 ]
  for item in python3 pyyaml pytest fts5; do
    grep -q "^missing $item " <<< "$output"
  done
}

@test "check_deps: an unknown argument exits 2" {
  run "$CD" --bogus
  [ "$status" -eq 2 ]
}

mini_vault() {
  M="$BATS_TEST_TMPDIR/mini"
  mkdir -p "$M/system/scripts" "$M/system/tests/python"
  cp "$REPO/system/scripts/verify_setup.sh" "$M/system/scripts/"
  printf '#!/usr/bin/env bats\n@test "ok" { true; }\n' > "$M/system/tests/a.bats"
  printf 'def test_ok():\n    assert True\n' > "$M/system/tests/python/test_ok.py"
  VS="$M/system/scripts/verify_setup.sh"
}

failing_bats() { printf '#!/usr/bin/env bats\n@test "no" { false; }\n' > "$M/system/tests/$1"; }

@test "verify_setup: passing suites exit 0 and are listed" {
  mini_vault
  run "$VS"
  [ "$status" -eq 0 ]
  grep -qx 'PASS system/tests/a.bats' <<< "$output"
  grep -qx 'PASS pytest system/tests/python' <<< "$output"
}

@test "verify_setup: a failing bats suite fails the run and the others still run" {
  mini_vault
  failing_bats b.bats
  run "$VS"
  [ "$status" -eq 1 ]
  grep -qx 'FAIL system/tests/b.bats (exit 1)' <<< "$output"
  grep -qx 'PASS system/tests/a.bats' <<< "$output"
  grep -qx 'PASS pytest system/tests/python' <<< "$output"
}

@test "verify_setup: a failing pytest run fails the run" {
  mini_vault
  printf 'def test_no():\n    assert False\n' > "$M/system/tests/python/test_no.py"
  run "$VS"
  [ "$status" -eq 1 ]
  grep -q '^FAIL pytest system/tests/python (exit ' <<< "$output"
}

@test "verify_setup: system_health.bats is not gated and runs only with --health" {
  mini_vault
  failing_bats system_health.bats
  run "$VS"
  [ "$status" -eq 0 ]
  [[ "$output" != *system_health* ]]
  run "$VS" --health
  [ "$status" -eq 0 ]
  grep -qx 'HEALTH FAIL (exit 1; advisory)' <<< "$output"
}

@test "verify_setup: --health without a health suite says so" {
  mini_vault
  run "$VS" --health
  [ "$status" -eq 0 ]
  grep -qx 'HEALTH skipped: system/tests/system_health.bats is not present' <<< "$output"
}

@test "verify_setup: no gating bats suites is a failure, not a pass" {
  mini_vault
  rm "$M/system/tests/a.bats"
  run "$VS"
  [ "$status" -eq 1 ]
  grep -qx 'FAIL no gating bats suites in system/tests/' <<< "$output"
}

@test "verify_setup: an unknown argument exits 2" {
  mini_vault
  run "$VS" --bogus
  [ "$status" -eq 2 ]
}
