---
type: schema
schema_for: config
folders: ["system/config.md", "system/config.example.md"]
fields:
  type: {kind: const, value: config, required: true}
  timezone: {kind: timezone, required: true}
  brief_time: {kind: time, required: true}
  debrief_time: {kind: time, required: true}
  remote_mode: {kind: enum, values: [private, none, keep], required: true}
  template_remote: {kind: string}
  default_partition: {kind: enum, values: [work, personal, shared], required: true}
  digest_min_events: {kind: int, default: "5"}
  digest_min_minutes: {kind: int, default: "20"}
  recall_budget_chars: {kind: int, default: "9000"}
  transcript_keep_dir: {kind: string}
  transcript_keep_days: {kind: int, min: "0", default: "90"}
  preferences_enabled: {kind: bool, default: "false"}
  superpowers: {kind: list, of: string}
  machine_role: {kind: enum, values: [standalone, server, client], default: "standalone"}
  sync_interval_minutes: {kind: int, min: "1", max: "60", default: "5"}
  meetings_enabled: {kind: bool, default: "false"}
  meetings_partition: {kind: enum, values: [work, personal]}
  owner_names: {kind: list, of: string}
  order_workspace: {kind: string}
  run_window: {kind: string}
  order_max_five_hour: {kind: string, default: "0.6"}
  nightshift_workspace: {kind: string}
  nightshift_window: {kind: string}
  triage_enabled: {kind: bool, default: "false"}
  triage_partition: {kind: enum, values: [work, personal]}
  triage_watch_senders: {kind: list, of: string}
  triage_chat_enabled: {kind: bool, default: "false"}
  slack_notify_channel: {kind: string}
  slack_connector: {kind: string, default: "claude.ai Slack"}
  notify_links: {kind: enum, values: [github, obsidian], default: "github"}
  orders_enabled: {kind: bool, default: "true"}
  update_enabled: {kind: bool, default: "true"}
  extensions: {kind: list, of: string}
---
# Config
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.

`run_window` is the window for Work Orders queued with `--window`, as `HH:MM-HH:MM`; empty (the default) or `00:00-24:00` means always. `order_max_five_hour` is the 5-hour usage fraction at or above which no new Work Order starts.

`triage_enabled` turns on inbox triage on a standalone machine or a server (inbox triage spec): every 30 minutes on workdays, mail that needs the owner becomes an `owed` line on the Now page of `triage_partition` (default `work`). `triage_watch_senders` lists domains (`@example.com`) or addresses whose unread mail outside the inbox from the last two days also becomes an `owed` line: mail from them archived unread is not missed. `triage_chat_enabled` adds the Slack channels the owner is a member of (public and private, not DMs, bots skipped) to each triage tick, through `slack_connector` (chat triage spec).

`slack_notify_channel` turns on Slack notices on a standalone machine or a server (Slack notices spec): a Slack channel ID, or the owner's user ID for a direct message; empty is off. `slack_connector` is the connector a headless session loads: `claude.ai Slack` (the default) for Slack connected at claude.ai; `plugin:slack:slack` only when headless sessions load the Slack plugin. `claude mcp list` can show the plugin while a headless session loads only the claude.ai connector (#133); `notify.sh --check` names the server the session loaded. `notify_links` picks the notices' links: `github` (the default) or `obsidian`, an `obsidian://open?file=<path>` link that names no vault; with several vaults on one device, check which one it opens (#157).

`orders_enabled` and `update_enabled` turn on the Work Orders tick and the daily template update on a standalone machine or a server. Absent means on, so vaults made before 2026-10-12 keep both; the example config sets both to `false`, and `/setup` asks.

`nightshift_workspace` and `nightshift_window` are the old names of `order_workspace` and `run_window`. They are still read when the new key is absent; the new key wins when both are set. `order_workspace` (default `~/code/worktrees`) must sit outside the vault: every Work Order session denies the vault root, so `/order add` and the tick refuse a workspace inside it (audit S3/S7 spec).

`extensions` lists the extensions turned on (extensions spec §3): each is a tracked folder `extensions/<name>/` with an `extension.md` manifest, shipped by the template or kept by the vault alone. A listed extension with no folder is reported once a day and skipped. An extension's own config keys validate while its folder is present.
