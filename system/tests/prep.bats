#!/usr/bin/env bats
# brief_prep.sh and debrief_prep.sh (spec §6.5).
load helpers

setup() {
  make_vault
  cd "$V"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  cat > "$STUBS/gcalcli" <<'EOF'
#!/bin/bash
printf '%s\n' "$@" > "$STUB_GCAL_ARGS"
readlink /proc/self/fd/0 > "$STUB_GCAL_STDIN"
case "${STUB_GCAL_MODE:-ok}" in
  ok) printf '2026-10-01\t09:00\t2026-10-01\t09:30\tStandup\n' ;;
  fail) echo "partial output"; exit 1 ;;
  missing) exit 127 ;;
esac
EOF
  chmod +x "$STUBS/gcalcli"
  export PATH="$STUBS:$PATH" STUB_GCAL_ARGS="$BATS_TEST_TMPDIR/gcal.args" STUB_GCAL_STDIN="$BATS_TEST_TMPDIR/gcal.stdin"
  BP="$V/system/scripts/brief_prep.sh"
  DP="$V/system/scripts/debrief_prep.sh"
  IN=system/logs/inputs/2026-10-01
  mkdir -p system/logs
}

commit_at() {  # <repo> <iso date> <message> [author email]
  GIT_AUTHOR_DATE="$2" GIT_COMMITTER_DATE="$2" GIT_AUTHOR_EMAIL="${4:-test@example.com}" \
    git -C "$1" commit -q --allow-empty -m "$3"
}

digest() {  # <path> <partition> <created_at> <body>
  mkdir -p "$(dirname "$1")"
  printf -- '---\ntype: session_digest\npartition: %s\ncodebase: "vault"\nsession_id: "s"\ncreated_at: "%s"\n---\n%s\n' "$2" "$3" "$4" > "$1"
}

codebase() {  # <name> <path>
  mkdir -p system/codebases
  printf -- '---\ntype: codebase\nname: "%s"\npath: "%s"\npartition: "work"\nsearch_globs: ["*.md"]\n---\n' "$1" "$2" > "system/codebases/$1.md"
}

@test "brief_prep: calendar and yesterday's focus are written" {
  printf '[09:00:00] Kafka\n' > system/logs/obsidian_focus_2026-09-30.log
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -q 'Standup' "$IN/calendar.tsv"
  [ "$(tr '\n' ' ' < "$STUB_GCAL_ARGS")" = "agenda 2026-10-01T00:00 2026-10-01T23:59 --tsv " ]
  [ "$(cat "$STUB_GCAL_STDIN")" = /dev/null ]
  grep -qx '# Focus: 2026-09-30' "$IN/focus_yesterday.md"
  grep -qx '| Kafka | 1 | 0.5 |' "$IN/focus_yesterday.md"
  [ ! -e "$IN/unavailable.md" ]
}

@test "brief_prep: a failing gcalcli is recorded, leaves no partial file, and still exits 0" {
  STUB_GCAL_MODE=fail run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/calendar.tsv" ]
  grep -q '^- brief_prep: calendar: gcalcli agenda failed (exit 1' "$IN/unavailable.md"
  grep -qx -- '- brief_prep: focus_yesterday: no focus log for 2026-09-30' "$IN/unavailable.md"
}

@test "brief_prep: gcalcli not installed is recorded as such" {
  STUB_GCAL_MODE=missing run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- brief_prep: calendar: gcalcli is not installed' "$IN/unavailable.md"
}

@test "brief_prep: the default date is today in the configured timezone" {
  run "$BP"
  [ "$status" -eq 0 ]
  [ -d "system/logs/inputs/$(TZ=America/Denver date +%F)" ]
}

@test "prep scripts: a bad date or extra arguments exit 2 and write nothing" {
  for s in "$BP" "$DP"; do
    run "$s" 2026-13-01
    [ "$status" -eq 2 ]
    run "$s" 2026-10-01 extra
    [ "$status" -eq 2 ]
  done
  [ ! -e system/logs/inputs ]
}

@test "prep scripts: re-running one keeps the other's unavailable lines and never duplicates its own" {
  run "$DP" 2026-10-01
  run "$BP" 2026-10-01
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(grep -c -- '- debrief_prep: focus: no focus log for 2026-10-01' "$IN/unavailable.md")" -eq 1 ]
  [ "$(grep -c -- '- brief_prep: focus_yesterday: no focus log for 2026-09-30' "$IN/unavailable.md")" -eq 1 ]
}

@test "debrief_prep: git.md lists the vault's commits of that day in the configured timezone" {
  commit_at "$V" 2026-09-30T23:59:00-06:00 "day before"
  commit_at "$V" 2026-10-01T23:30:00-06:00 "late on the day"
  commit_at "$V" 2026-10-02T00:30:00-06:00 "day after"
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '## vault' "$IN/git.md"
  grep -qE '^- 23:30 [0-9a-f]+ late on the day$' "$IN/git.md"
  run grep -E 'day before|day after' "$IN/git.md"
  [ "$status" -eq 1 ]
}

@test "debrief_prep: codebase sections list only your commits on local branches" {
  C="$BATS_TEST_TMPDIR/app"
  git init -q "$C"
  git -C "$C" config user.email me@example.com
  git -C "$C" config user.name me
  commit_at "$C" 2026-10-01T10:00:00-06:00 "mine" me@example.com
  commit_at "$C" 2026-10-01T11:00:00-06:00 "a teammate's" other@example.com
  git -C "$C" checkout -q -b tmp
  commit_at "$C" 2026-10-01T12:00:00-06:00 "only on a remote" me@example.com
  git -C "$C" update-ref refs/remotes/origin/elsewhere HEAD
  git -C "$C" checkout -q -
  git -C "$C" branch -q -D tmp
  codebase app "$C"
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '## app' "$IN/git.md"
  grep -qE '^- 10:00 [0-9a-f]+ mine$' "$IN/git.md"
  run grep -E "teammate|only on a remote" "$IN/git.md"
  [ "$status" -eq 1 ]
}

@test "debrief_prep: a codebase without a repository is recorded, the rest still runs" {
  codebase gone /nonexistent
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- debrief_prep: git: codebase gone has no git repository at /nonexistent' "$IN/unavailable.md"
  grep -qx '## vault' "$IN/git.md"
  [ -f "$IN/digests.md" ]
  [ -f "$IN/focus.md" ]
}

@test "debrief_prep: digests.md holds that day's digests from every partition, oldest first" {
  digest raw/work/notes/w1.md work 2026-10-01T09:00:00-06:00 "Work digest."
  digest raw/personal/archive/p1.md personal 2026-10-01T08:00:00-06:00 "Personal digest."
  digest raw/work/notes/old.md work 2026-09-30T09:00:00-06:00 "Old digest."
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '## p1.md (personal, vault, 2026-10-01T08:00:00-06:00)' "$IN/digests.md"
  grep -qx '## w1.md (work, vault, 2026-10-01T09:00:00-06:00)' "$IN/digests.md"
  grep -qx 'Work digest.' "$IN/digests.md"
  run grep -E 'Old digest|type: session_digest' "$IN/digests.md"
  [ "$status" -eq 1 ]
  [ "$(grep -n 'p1.md' "$IN/digests.md" | cut -d: -f1)" -lt "$(grep -n 'w1.md' "$IN/digests.md" | cut -d: -f1)" ]
}

@test "debrief_prep: no digests and no focus data are stated, not left blank" {
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx 'No session digests.' "$IN/digests.md"
  grep -qx 'no focus data' "$IN/focus.md"
  grep -qx -- '- debrief_prep: focus: no focus log for 2026-10-01' "$IN/unavailable.md"
}
