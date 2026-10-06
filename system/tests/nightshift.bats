#!/usr/bin/env bats
# Nightshift: .gitignore exception, CLI exit codes, units and brief wiring (Nightshift spec §9).
load helpers

setup() {
  make_vault
  cd "$V"
}

@test "only queue notes under raw/ become trackable" {
  cp "$REPO/.gitignore" .gitignore
  git init -q .
  mkdir -p raw/work/nightshift raw/work/notes raw/inbox
  touch raw/work/nightshift/a.md raw/work/nightshift/a.txt raw/work/notes/n.md raw/inbox/i.md
  run git check-ignore -q raw/work/nightshift/a.md
  [ "$status" -eq 1 ]
  git check-ignore -q raw/work/nightshift/a.txt
  git check-ignore -q raw/work/notes/n.md
  git check-ignore -q raw/inbox/i.md
}

@test "nightshift.py: empty queue tick exits 0; bad subcommand exits 2" {
  run system/scripts/nightshift.py tick
  [ "$status" -eq 0 ]
  run system/scripts/nightshift.py frobnicate
  [ "$status" -eq 2 ]
}
