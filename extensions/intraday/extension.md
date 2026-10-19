---
name: intraday
contract: 1
description: "What changed since the brief: watched channels, calendar changes, your commitments and a capture channel, logged in a today file"
requires: []
config_keys:
  watch_channels: {kind: list, of: {kind: map, fields: {id: {kind: string, required: true}, label: {kind: string, required: true}}}}
  watch_group_dms: {kind: bool, default: "true"}
  watch_user_id: {kind: string}
  watch_partition: {kind: enum, values: [work, personal], default: work}
  watch_commitments_mail: {kind: bool, default: "true"}
  capture_channel: {kind: string}
  capture_partition: {kind: enum, values: ["", work, personal], default: ""}
sources:
  - {name: watch, credential: "Slack, Gmail and Google Calendar connectors", renew: "reconnect them at claude.ai, Settings, Connectors"}
smoke:
  - {source: watch, timeout: 960, connector: true, run: "scripts/watch_fetch.sh --check"}
brief: true
debrief: true
units:
  - {name: foundry-watch, roles: [standalone, server]}
tick: {run: "scripts/today_log.py tick", timeout: 120}
alert_tags: [{tag: watch, severity: now}, intraday]
allow: ["Bash(extensions/intraday/scripts/watch_fetch.sh --check)"]
deps: []
index_ignore: []
---
**Intraday.** Every 30 minutes on workdays (08:15 to 17:45), `foundry-watch.timer` runs three confined connector sessions and logs what changed since the brief to `briefings/<date>.today.md`, which the briefing embeds under 🕑 Today so far (phase D spec).
