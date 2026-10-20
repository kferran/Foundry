---
type: schema
schema_for: config
fields:
  watch_channels: {kind: list, of: {kind: map, fields: {id: {kind: string, required: true}, label: {kind: string, required: true}}}}
  watch_group_dms: {kind: bool, default: "true"}
  watch_user_id: {kind: string}
  watch_partition: {kind: enum, values: [work, personal], default: work}
  watch_commitments_mail: {kind: bool, default: "true"}
  watch_inbound_mail: {kind: bool, default: "true"}
  watch_inbound_skip: {kind: list, of: string}
  watch_inbound_rules: {kind: list, of: {kind: map, fields: {from: {kind: string, required: true}, subject: {kind: string}, snippet: {kind: string}, kind: {kind: enum, values: [request, incident, deadline], required: true}}}}
  capture_channel: {kind: string}
  capture_partition: {kind: enum, values: ["", work, personal], default: ""}
---
The intraday extension's keys (phase D spec §3.8). `watch_channels` lists the Slack channels read in full, each `{id: C…, label: <name>}`; `watch_group_dms` adds the owner's group DMs. `watch_user_id` is the owner's Slack user ID for the own-commitments query (empty turns it off). `watch_partition` is the Now page and today file the watch writes to. `watch_commitments_mail` reads sent mail for commitments; `watch_inbound_mail` reads incoming mail (less promotions, social and forums) for review requests, assigned tasks, production alerts and deadlines, skipping the senders in `watch_inbound_skip` (addresses or domains: `news@example.com`, `@example.com` or `example.com`). `watch_inbound_rules` makes items without the model: an incoming thread whose newest incoming message (at or after the cursor) comes from `from` (an address, or a domain and its subdomains, written as in `watch_inbound_skip`) and matches `subject` and `snippet` (case-insensitive regexes of up to 200 characters, at least one of the two; both must match when both are given) becomes a `kind` item (`request`, `incident` or `deadline`) whose text is the subject, such as `{from: "@code.example.com", subject: "pull request", snippet: "added you as a reviewer", kind: request}` or `{from: "alerts@example.com", subject: "^\\[?sev ?1", kind: incident}`. A bad rule stops the tick (exit 2) before any session runs. `capture_channel` is a channel or DM ID whose new messages become `raw/inbox/` drops (empty is off; the notices channel only with `slack_notify_thread: daily`, #293), in `capture_partition` (empty follows `default_partition`, `personal` when that is `shared`).
