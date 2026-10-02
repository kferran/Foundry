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
