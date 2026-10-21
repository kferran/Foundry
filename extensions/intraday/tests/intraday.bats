#!/usr/bin/env bats
# The intraday extension as core sees it (phase D spec §3.1, §3.8, §3.9): the manifest, its config keys, the smoke
# row, the watch timer, the alert tags and the today schema.
# Runs from a vault checkout: the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

setup() {
  make_vault
  use_extension intraday
  cd "$V"
}

@test "the manifest loads with one smoke row, the watch unit on standalone and server, a tick and its scripts executable" {
  run system/scripts/extensions.py check
  [ "$status" -eq 0 ]
  run system/scripts/extensions.py smoke
  [ "$output" = "$(printf 'watch\t1140\t1\textensions/intraday/scripts/watch_fetch.sh --check')" ]
  run system/scripts/extensions.py units server
  [ "$output" = "$(printf 'intraday\tfoundry-watch')" ]
  run system/scripts/extensions.py units client
  [ -z "$output" ]
  run system/scripts/extensions.py brief
  [ "$output" = intraday ]
  run system/scripts/extensions.py debrief
  [ "$output" = intraday ]
  for s in watch_fetch.sh watch.py today_log.py; do
    [ -x "extensions/intraday/scripts/$s" ]
  done
}

@test "the config keys validate, and a channel without a label is an error" {
  sed -i '$d' system/config.md
  cat >> system/config.md <<'EOF'
watch_channels: [{id: "C0001", label: "ops"}, {id: "C0002", label: "oncall"}]
watch_group_dms: "true"
watch_user_id: "U0OWNER"
watch_partition: "work"
watch_commitments_mail: "false"
watch_inbound_mail: "true"
watch_inbound_skip: ["news@example.com", "@lists.example.com"]
capture_channel: "C0CAPTURE"
capture_partition: ""
---
EOF
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -eq 0 ]
  sed -i 's/{id: "C0002", label: "oncall"}/{id: "C0002"}/' system/config.md
  run system/scripts/vault_index.py validate system/config.md
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing required key label"* ]]
}

@test "a [watch] line reaches Slack at once; an [intraday] line waits for the brief" {
  run python3 -c 'import sys; sys.path.insert(0, "system/scripts")
from pathlib import Path
from vaultlib import alerts
ext = alerts.extension_tags(Path("."))
print(alerts.severity("- 09:00:00 [watch] Weekly huddle cancelled", ext), alerts.severity("- 09:00:00 [intraday] x", ext))'
  [ "$status" -eq 0 ]
  [ "$output" = "now brief" ]
}

@test "the watch timer installs on a server, at :15 and :45 on workdays, and never on a client" {
  need_user_systemd
  cp -r "$REPO/system/systemd" system/systemd
  mkdir -p "$BATS_TEST_TMPDIR/stubs"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n' > "$BATS_TEST_TMPDIR/stubs/systemctl"
  chmod +x "$BATS_TEST_TMPDIR/stubs/systemctl"
  ln -s "$REPO/system/tests/stub_claude" "$BATS_TEST_TMPDIR/stubs/claude"
  export PATH="$BATS_TEST_TMPDIR/stubs:$PATH" SYSTEMCTL="$BATS_TEST_TMPDIR/stubs/systemctl"
  export STUB_SYSTEMCTL_LOG="$BATS_TEST_TMPDIR/systemctl.log" SYSTEMD_USER_DIR="$BATS_TEST_TMPDIR/units" HOME="$BATS_TEST_TMPDIR/home"
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  run system/scripts/install_units.sh
  [ "$status" -eq 0 ]
  grep -q '^OnCalendar=Mon..Fri \*-\*-\* 08..17:15,45:00 America/Denver$' "$SYSTEMD_USER_DIR/foundry-watch.timer"
  grep -qF 'extensions/intraday/scripts/watch_fetch.sh' "$SYSTEMD_USER_DIR/foundry-watch.service"
  # Slack 420 s + mail 480 s + calendar 3 x 190 s + route 120 s = 1,590 s, plus 10 s kill grace a session (1,640 s),
  # inside 29 minutes and the 30-minute timer interval.
  grep -qx 'TimeoutStartSec=29min' "$SYSTEMD_USER_DIR/foundry-watch.service"
  # A client keeps no units: a plain install there removes the ones this vault installed.
  system/scripts/vault_index.py set system/config.md machine_role client > /dev/null
  run system/scripts/install_units.sh
  [ "$status" -eq 0 ]
  [ ! -e "$SYSTEMD_USER_DIR/foundry-watch.timer" ]
}

@test "a today file with its frontmatter lints clean in briefings/" {
  mkdir -p briefings
  printf -- '---\ntype: today\ndate: "2026-10-01"\n---\n- 09:00 **capture** 1 message\n' > briefings/2026-10-01.today.md
  run system/scripts/vault_index.py validate briefings/2026-10-01.today.md
  [ "$status" -eq 0 ]
}

@test "the brief section carries the today embed and yesterday's count; the debrief section lists the watch's open lines" {
  printf '{"key": "watch:a", "day": "2026-09-30", "time": "09:00", "kind": "deadline", "text": "QBR deck (#ops)", "link": "https://x.slack.com/archives/C1/p1", "now": "added"}\n' \
    > "$(mkdir -p system/logs/watch && echo system/logs/watch/items-2026-09.jsonl)"
  printf '{"time": "2026-09-30T10:00:00-06:00", "step": "route", "exit": 0, "reason": "", "count": 0}\n' > system/logs/watch_fetch-2026-09.jsonl
  run system/scripts/brief_prep.sh 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat system/logs/inputs/2026-10-01/sections/intraday.md)" = "$(printf 'today: [[2026-10-01.today]]\nyesterday (2026-09-30): 1 deadline')" ]
  grep -qF '## 🕑 Today so far' system/logs/inputs/2026-10-01/sections/intraday.prompt.md
  grep -q '^watch	ok' system/logs/inputs/2026-10-01/sources.given
  mkdir -p wiki/work
  printf -- '---\ntype: concept\ntags: [now]\npartition: work\n---\n# Now\n\n## Needs you\n- [ ] owed: QBR deck (in #ops) (Pat, since 2026-09-30, https://x.slack.com/archives/C1/p1)\n' > wiki/work/Now.md
  run system/scripts/debrief_prep.sh 2026-09-30
  [ "$status" -eq 0 ]
  [ "$(cat system/logs/inputs/2026-09-30/debrief_sections/intraday.md)" = "$(printf 'logged: 1 deadline\n- [ ] owed: QBR deck (in #ops) (Pat, since 2026-09-30, https://x.slack.com/archives/C1/p1)')" ]
}
