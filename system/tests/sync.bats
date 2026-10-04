#!/usr/bin/env bats
# vault_sync.sh (two-machine spec §5): a bare origin, the server vault and a client clone, no network.
load helpers

setup() {
  make_vault
  cd "$V"
  cp -r "$REPO/.githooks" "$V/.githooks"
  cp "$REPO/.gitignore" "$V/.gitignore"
  export HOME="$BATS_TEST_TMPDIR/home" GIT_ALLOW_PROTOCOL=file REAL_GIT="$(command -v git)"
  mkdir -p "$HOME" system/logs
  git config core.hooksPath .githooks
  sed -i -e 's/^remote_mode: .*/remote_mode: "private"/' -e '/^default_partition:/a machine_role: "server"' system/config.md
  echo "$BATS_TEST_TMPDIR/template.git" > system/template_source
  O="$BATS_TEST_TMPDIR/origin.git"
  git init -q --bare "$O"
  git add -A
  git commit -q --no-verify -m base
  git remote add origin "$O"
  git push -q -u origin HEAD 2> /dev/null
  B="$(git branch --show-current)"
  C="$BATS_TEST_TMPDIR/client"
  git clone -q "$O" "$C"
  git -C "$C" config user.email client@example.com
  git -C "$C" config user.name client
  VS="$V/system/scripts/vault_sync.sh"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$BATS_TEST_TMPDIR/systemctl.log"\n' > "$STUBS/systemctl"
  chmod +x "$STUBS/systemctl"
  export SYSTEMCTL="$STUBS/systemctl"
}

note() {  # <repo> <name> <body line>: write a valid work concept
  mkdir -p "$1/wiki/work/concepts"
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n---\n# %s\n%s\n[[Index]]\n' "$2" "$3" > "$1/wiki/work/concepts/$2.md"
}

client_push() {  # <name> <body line>: the client commits a note and pushes it
  note "$C" "$1" "$2"
  git -C "$C" add -A
  git -C "$C" commit -q -m "client: $1"
  git -C "$C" push -q
}

wrap_git() { ln -sf "$REPO/system/tests/stub_git" "$STUBS/git"; export PATH="$STUBS:$PATH"; }

alerts() { cat system/logs/alerts_*.md 2>/dev/null; }

@test "local changes get one scripted sync commit, pushed to origin" {
  printf 'more\n' >> wiki/work/concepts/Kafka.md
  note "$V" New "fresh"
  run "$VS"
  [ "$status" -eq 0 ]
  [ "$(git -C "$O" log -1 --format=%B "$B")" = "$(printf 'sync(server): 2 file(s)\n\nwiki/work/concepts/Kafka.md +1/-0\nwiki/work/concepts/New.md (new)\n\nJarvis-Command: sync\nJarvis-Role: server')" ]
  [ "$(git rev-parse HEAD)" = "$(git -C "$O" rev-parse "$B")" ]
}

@test "gitignored paths are never committed and nothing to do makes no commit" {
  head="$(git rev-parse HEAD)"
  mkdir -p raw/inbox
  echo x > system/logs/x.log
  echo y > raw/inbox/y.md
  run "$VS"
  [ "$status" -eq 0 ]
  [ "$(git rev-parse HEAD)" = "$head" ]
  [ "$(git -C "$O" rev-parse "$B")" = "$head" ]
}

@test "a client commit reaches the server through a scripted merge" {
  client_push FromClient "typed on the laptop"
  note "$V" FromServer "written by a run"
  run "$VS"
  [ "$status" -eq 0 ]
  [ -f wiki/work/concepts/FromClient.md ]
  [ "$(git log -1 --format=%B)" = "$(printf 'sync(server): merge origin/%s\n\nJarvis-Command: sync\nJarvis-Role: server' "$B")" ]
  [ "$(git -C "$O" rev-parse "$B")" = "$(git rev-parse HEAD)" ]
}

@test "commit_runs.py runs first: a published run gets its own commit before the sync commit" {
  rid="20261004T060000-brief-cd34"
  echo 20200101T000000 > system/logs/commit_runs.since
  mkdir -p "system/logs/runs/$rid" briefings
  printf '{"run_id": "%s", "status": "published", "published": ["briefings/2026-10-04.md"], "conflicts": [], "problems": []}\n' "$rid" > "system/logs/runs/$rid/publish.json"
  printf -- '---\ntype: briefing\ndate: "2026-10-04"\n---\n# Briefing\n' > briefings/2026-10-04.md
  printf 'more\n' >> wiki/work/concepts/Kafka.md
  run "$VS"
  [ "$status" -eq 0 ]
  [ "$(git log -2 --format=%s | tr '\n' '|')" = "sync(server): 1 file(s)|brief 2026-10-04: briefings/2026-10-04.md|" ]
}

@test "a commit the hook refuses is unstaged and alerted, exit 1" {
  mkdir -p wiki/work/concepts
  printf -- '---\ntype: concept\n---\n# Bad\n' > wiki/work/concepts/Bad.md
  run "$VS"
  [ "$status" -eq 1 ]
  [ -z "$(git diff --cached --name-only)" ]
  alerts | grep -q '\[sync\] sync failed (commit)'
}

@test "an unreachable origin is alerted once a day and its recovery once" {
  chmod 000 "$O"
  run "$VS"
  [ "$status" -eq 1 ]
  run "$VS"
  [ "$status" -eq 1 ]
  chmod 755 "$O"
  [ "$(alerts | grep -c 'sync failed (fetch)')" -eq 1 ]
  run "$VS"
  [ "$status" -eq 0 ]
  [ "$(alerts | grep -c 'sync recovered')" -eq 1 ]
  [ ! -e system/logs/sync-state.json ]
}

@test "a merge refused by a file written after the commit step exits 1 and leaves no merge" {
  client_push Clash "from the client"
  wrap_git
  export WRAP_AFTER_FETCH="mkdir -p wiki/work/concepts; echo local > wiki/work/concepts/Clash.md"
  run "$VS"
  [ "$status" -eq 1 ]
  [ ! -e .git/MERGE_HEAD ]
  alerts | grep -q 'sync failed (merge)'
}

@test "a push rejected because origin moved is retried once" {
  wrap_git
  export WRAP_BEFORE_PUSH="note \"$C\" Racer x; git -C \"$C\" add -A; git -C \"$C\" commit -q -m racer; git -C \"$C\" push -q"
  export -f note
  printf 'more\n' >> wiki/work/concepts/Kafka.md
  run "$VS"
  [ "$status" -eq 0 ]
  [ -f wiki/work/concepts/Racer.md ]
  [ "$(git -C "$O" rev-parse "$B")" = "$(git rev-parse HEAD)" ]
}

@test "a busy run.lock exits 4; --pre and --post exit 0" {
  exec 9> system/run.lock
  flock 9
  run "$VS"
  [ "$status" -eq 4 ]
  run "$VS" --pre
  [ "$status" -eq 0 ]
  run "$VS" --post
  [ "$status" -eq 0 ]
}

@test "--pre exits 3 on a sync-blocked marker even with run.lock busy" {
  echo "conflict" > system/logs/sync-blocked
  exec 9> system/run.lock
  flock 9
  run "$VS" --pre
  [ "$status" -eq 3 ]
}

conflicting_merge() {  # leave the server vault mid-merge on Kafka.md
  printf 'client line\n' >> "$C/wiki/work/concepts/Kafka.md"
  git -C "$C" commit -q -am client
  git -C "$C" push -q
  printf 'server line\n' >> wiki/work/concepts/Kafka.md
  git commit -q --no-verify -am server
  git fetch -q origin
  run git merge --no-edit "origin/$B"
}

@test "--pre during an unfinished merge exits 3 and writes no marker" {
  conflicting_merge
  run "$VS" --pre
  [ "$status" -eq 3 ]
  [ ! -e system/logs/sync-blocked ]
}

@test "an unfinished merge blocks the sync: marker, alert, exit 3, nothing committed" {
  conflicting_merge
  head="$(git rev-parse HEAD)"
  run "$VS"
  [ "$status" -eq 3 ]
  grep -q 'operation in progress' system/logs/sync-blocked
  alerts | grep -q 'sync blocked'
  [ "$(git rev-parse HEAD)" = "$head" ]
}

@test "a stale index.lock blocks the sync with exit 3" {
  touch -d '20 minutes ago' .git/index.lock
  run "$VS"
  [ "$status" -eq 3 ]
  grep -q 'stale index.lock' system/logs/sync-blocked
}

@test "TERM during a merge aborts it before exiting" {
  conflicting_merge
  git merge --abort
  wrap_git
  export WRAP_AFTER_MERGE='kill -TERM $PPID'
  run "$VS"
  [ "$status" -eq 143 ]
  [ ! -e .git/MERGE_HEAD ]
}

@test "remote_mode none, a template origin and a missing upstream exit 1 with the reason" {
  sed -i 's/^remote_mode: .*/remote_mode: "none"/' system/config.md
  run "$VS"
  [ "$status" -eq 1 ]
  [[ "$output" == *"remote_mode is none"* ]]
  sed -i 's/^remote_mode: .*/remote_mode: "private"/' system/config.md
  echo "$O" > system/template_source
  run "$VS"
  [ "$status" -eq 1 ]
  [[ "$output" == *"origin is the template repository"* ]]
  echo "$BATS_TEST_TMPDIR/template.git" > system/template_source
  git branch -q --unset-upstream
  run "$VS"
  [ "$status" -eq 1 ]
  [[ "$output" == *"no upstream; run /setup phase 4"* ]]
}

@test "each network call gets the smaller of 120 s and the time left" {
  printf '#!/bin/bash\necho "$1" >> "$BATS_TEST_TMPDIR/timeouts"\nshift\nexec "$@"\n' > "$STUBS/timeout"
  chmod +x "$STUBS/timeout"
  export PATH="$STUBS:$PATH"
  run "$VS"
  [ "$status" -eq 0 ]
  [ "$(sort -u "$BATS_TEST_TMPDIR/timeouts")" = 120 ]
  rm "$BATS_TEST_TMPDIR/timeouts"
  SYNC_DEADLINE=40 run "$VS"
  [ "$status" -eq 0 ]
  while read -r t; do
    [ "$t" -ge 1 ]
    [ "$t" -le 40 ]
  done < "$BATS_TEST_TMPDIR/timeouts"
}

@test "unknown arguments exit 2" {
  run "$VS" --bogus
  [ "$status" -eq 2 ]
}

diverge_on_kafka() {  # the client and the server change the same line; the client pushes first
  printf 'client line\n' >> "$C/wiki/work/concepts/Kafka.md"
  git -C "$C" commit -q -am client
  git -C "$C" push -q
  printf 'server line\n' >> wiki/work/concepts/Kafka.md
}

@test "a conflict aborts the merge, pushes jarvis/server-pending, writes the marker and alerts once" {
  diverge_on_kafka
  run "$VS"
  [ "$status" -eq 3 ]
  [ ! -e .git/MERGE_HEAD ]
  [ "$(git -C "$O" rev-parse refs/heads/jarvis/server-pending)" = "$(git rev-parse HEAD)" ]
  grep -qx 'wiki/work/concepts/Kafka.md' system/logs/sync-blocked
  grep -q 'pending branch: jarvis/server-pending' system/logs/sync-blocked
  run "$VS"
  [ "$status" -eq 3 ]
  [ "$(alerts | grep -c 'sync blocked')" -eq 1 ]
  run "$VS" --pre
  [ "$status" -eq 3 ]
}

@test "resolving from the client clears the marker, deletes the pending branch and alerts" {
  diverge_on_kafka
  run "$VS"
  [ "$status" -eq 3 ]
  git -C "$C" fetch -q origin
  run git -C "$C" merge --no-edit origin/jarvis/server-pending
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-01"\npartition: work\n---\n# Kafka\nresolved\n[[Index]]\n' > "$C/wiki/work/concepts/Kafka.md"
  git -C "$C" commit -q -am resolved
  git -C "$C" push -q
  run "$VS"
  [ "$status" -eq 0 ]
  [ ! -e system/logs/sync-blocked ]
  [ -z "$(git -C "$O" for-each-ref refs/heads/jarvis/)" ]
  grep -qx resolved wiki/work/concepts/Kafka.md
  alerts | grep -q 'sync unblocked'
}

@test "a cycle with nothing to merge clears a marker" {
  printf 'reason: operation in progress\n' > system/logs/sync-blocked
  run "$VS"
  [ "$status" -eq 0 ]
  [ ! -e system/logs/sync-blocked ]
  alerts | grep -q 'sync unblocked'
}

@test "on unblocking, a daily run whose time has passed with no run today is started" {
  sed -i -e 's/^brief_time: .*/brief_time: "00:00"/' -e 's/^debrief_time: .*/debrief_time: "00:00"/' system/config.md
  printf '{"run_id": "x", "command": "debrief", "started_at": "%s", "exit": 0}\n' "$(TZ=America/Denver date -Iseconds)" \
    > "system/logs/runs-$(TZ=America/Denver date +%Y-%m).jsonl"
  printf 'reason: conflict\n' > system/logs/sync-blocked
  run "$VS"
  [ "$status" -eq 0 ]
  [ "$(cat "$BATS_TEST_TMPDIR/systemctl.log")" = "--user start --no-block jarvis-brief.service" ]
}

@test "a client's conflict pushes jarvis/client-pending and starts no runs" {
  sed -i 's/^machine_role: .*/machine_role: "client"/' system/config.md
  sed -i -e 's/^brief_time: .*/brief_time: "00:00"/' -e 's/^debrief_time: .*/debrief_time: "00:00"/' system/config.md
  diverge_on_kafka
  run "$VS"
  [ "$status" -eq 3 ]
  git -C "$O" rev-parse -q --verify refs/heads/jarvis/client-pending
  rm system/logs/sync-blocked
  git reset -q --hard "origin/$B"
  printf 'reason: conflict\n' > system/logs/sync-blocked
  run "$VS"
  [ "$status" -eq 0 ]
  [ -z "$(git -C "$O" for-each-ref refs/heads/jarvis/)" ]
  [ ! -e "$BATS_TEST_TMPDIR/systemctl.log" ]
}
