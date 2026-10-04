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
  for c in claude gcalcli hyprctl pacman; do
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

@test "check_deps: --role client requires only what a client runs" {
  rm "$BIN/gcalcli" "$BIN/hyprctl" "$BIN/bats" "$BIN/systemctl" "$BIN/systemd-analyze" "$BIN/flock"
  run env PATH="$BIN" "$CD" --role client --strict
  [ "$status" -eq 0 ]
  for item in claude git jq python3 pyyaml fts5; do
    grep -qx "ok $item" <<< "$output"
  done
  run grep -E '^(ok|missing) (gcalcli|hyprctl|bats|systemctl|systemd-analyze|flock|timeout|pytest) ' <<< "$output"
  [ "$status" -eq 1 ]
}

@test "check_deps: --role server needs everything except hyprctl" {
  rm "$BIN/hyprctl"
  run env PATH="$BIN" "$CD" --strict --role server
  [ "$status" -eq 0 ]
  run grep hyprctl <<< "$output"
  [ "$status" -eq 1 ]
  rm "$BIN/gcalcli"
  run env PATH="$BIN" "$CD" --role server --strict
  [ "$status" -eq 1 ]
}

@test "check_deps: install hints follow the package manager on PATH" {
  rm "$BIN/bats"
  run env PATH="$BIN" "$CD"
  grep -qx 'missing bats sudo pacman -S bash-bats' <<< "$output"
  rm "$BIN/pacman"
  printf '#!/bin/bash\n' > "$BIN/apt-get"
  chmod +x "$BIN/apt-get"
  run env PATH="$BIN" "$CD"
  grep -qx 'missing bats sudo apt install bats' <<< "$output"
  rm "$BIN/apt-get"
  run env PATH="$BIN" "$CD"
  grep -qx 'missing bats install bats' <<< "$output"
}

@test "check_deps: the role defaults to the config's machine_role, else standalone" {
  load helpers
  make_vault
  rm "$BIN/hyprctl"
  run env PATH="$BIN" "$V/system/scripts/check_deps.sh" --strict
  [ "$status" -eq 1 ]
  grep -q '^missing hyprctl ' <<< "$output"
  printf 'machine_role: "server"\n' > "$BATS_TEST_TMPDIR/role"
  sed -i '/^default_partition:/r '"$BATS_TEST_TMPDIR/role" "$V/system/config.md"
  run env PATH="$BIN" "$V/system/scripts/check_deps.sh" --strict
  [ "$status" -eq 0 ]
}

@test "check_deps: an unknown or missing role exits 2" {
  run "$CD" --role laptop
  [ "$status" -eq 2 ]
  run "$CD" --role
  [ "$status" -eq 2 ]
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

# A fake host: an ssh stub that drops its options and host and runs the command here, with the
# "remote" /tmp redirected to the test's tmpdir.
host_repo() {
  H="$BATS_TEST_TMPDIR/hostrepo"
  mkdir -p "$H/system/scripts" "$H/system/tests" "$BATS_TEST_TMPDIR/remote-tmp" "$BATS_TEST_TMPDIR/sbin"
  cp "$REPO/system/tests/verify_on_host.sh" "$H/system/tests/"
  printf '#!/bin/bash\necho "===== summary"\necho "PASS fake"\nexit "${FAKE_GATE_RC:-0}"\n' > "$H/system/scripts/verify_setup.sh"
  chmod +x "$H/system/scripts/verify_setup.sh"
  git -C "$H" init -q
  git -C "$H" add -A
  git -C "$H" -c user.name=t -c user.email=t@e commit -qm init
  cat > "$BATS_TEST_TMPDIR/sbin/ssh" <<'STUB'
#!/bin/bash
while [[ "$1" == -o ]]; do shift 2; done
shift
exec bash -c "$*"
STUB
  chmod +x "$BATS_TEST_TMPDIR/sbin/ssh"
  export PATH="$BATS_TEST_TMPDIR/sbin:$PATH" VERIFY_TMP="$BATS_TEST_TMPDIR/remote-tmp"
}

@test "verify_on_host: a passing gate on the host exits 0, prints the summary and leaves nothing behind" {
  host_repo
  run "$H/system/tests/verify_on_host.sh" somehost
  [ "$status" -eq 0 ]
  grep -qx 'PASS fake' <<< "$output"
  [ -z "$(ls -A "$VERIFY_TMP")" ]
}

@test "verify_on_host: a failing gate exits with its code and keeps the copy and log" {
  host_repo
  run env FAKE_GATE_RC=1 "$H/system/tests/verify_on_host.sh" somehost
  [ "$status" -eq 1 ]
  grep -q '^kept: somehost:' <<< "$output"
  [ "$(ls "$VERIFY_TMP" | wc -l)" -eq 2 ]
}

@test "verify_on_host: copies HEAD, not uncommitted changes" {
  host_repo
  printf '#!/bin/bash\nexit 7\n' > "$H/system/scripts/verify_setup.sh"
  run "$H/system/tests/verify_on_host.sh" somehost
  [ "$status" -eq 0 ]
}

@test "verify_on_host: needs exactly one plain host argument" {
  host_repo
  run "$H/system/tests/verify_on_host.sh"
  [ "$status" -eq 2 ]
  run "$H/system/tests/verify_on_host.sh" 'h; rm -rf /'
  [ "$status" -eq 2 ]
}
