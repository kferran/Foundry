---
type: schema
schema_for: config
fields:
  watch_channels: {kind: list, of: {kind: map, fields: {id: {kind: string, required: true}, label: {kind: string, required: true}}}}
  watch_group_dms: {kind: bool, default: "true"}
  watch_user_id: {kind: string}
  watch_partition: {kind: enum, values: [work, personal], default: work}
  watch_commitments_mail: {kind: bool, default: "true"}
  capture_channel: {kind: string}
  capture_partition: {kind: enum, values: ["", work, personal], default: ""}
---
The intraday extension's keys (phase D spec §3.8). `watch_channels` lists the Slack channels read in full, each `{id: C…, label: <name>}`; `watch_group_dms` adds the owner's group DMs. `watch_user_id` is the owner's Slack user ID for the own-commitments query (empty turns it off). `watch_partition` is the Now page and today file the watch writes to. `watch_commitments_mail` runs the sent-mail session. `capture_channel` is a channel or DM ID whose new messages become `raw/inbox/` drops (empty is off), in `capture_partition` (empty follows `default_partition`, `personal` when that is `shared`).
