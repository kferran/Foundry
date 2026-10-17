---
type: schema
schema_for: config
folders: ["system/config.md", "system/config.example.md"]
fields:
  type: {kind: const, value: config, required: true, readers: [system/scripts/vaultlib/schema.py]}
  timezone: {kind: timezone, required: true, readers: [system/scripts/lib_prep.sh, system/scripts/vaultlib/intake.py]}
  brief_time: {kind: time, required: true, readers: [system/scripts/install_units.sh, system/scripts/vaultlib/nightshift_run.py]}
  debrief_time: {kind: time, required: true, readers: [system/scripts/install_units.sh]}
  remote_mode: {kind: enum, values: [private, none, keep], required: true, readers: [system/scripts/vault_sync.sh, .claude/commands/backup.md]}
  template_remote: {kind: string, readers: [system/scripts/lib_prep.sh, system/scripts/vaultlib/nightshift_check.py]}
  default_partition: {kind: enum, values: [work, personal, shared], required: true, readers: [system/scripts/run_headless.sh, system/scripts/vaultlib/recall.py]}
  digest_min_events: {kind: int, default: "5", readers: [system/hooks/lib_memory.sh]}
  digest_min_minutes: {kind: int, default: "20", readers: [system/hooks/lib_memory.sh]}
  recall_budget_chars: {kind: int, default: "9000", readers: [system/scripts/vaultlib/recall.py]}
  preferences_enabled: {kind: bool, default: "false", readers: []}
  superpowers: {kind: list, of: string, readers: [.claude/commands/brief.md]}
  machine_role: {kind: enum, values: [standalone, server, client], default: "standalone", readers: [system/scripts/install_units.sh, system/scripts/vaultlib/intake.py]}
  sync_interval_minutes: {kind: int, min: "1", max: "60", default: "5", readers: [system/scripts/install_units.sh]}
  meetings_enabled: {kind: bool, default: "false", readers: [system/scripts/meetings_fetch.sh, system/scripts/install_units.sh]}
  meetings_partition: {kind: enum, values: [work, personal], readers: [system/scripts/vaultlib/intake.py]}
  owner_names: {kind: list, of: string, readers: [system/scripts/triage_fetch.sh, system/scripts/vaultlib/meetings.py]}
  order_workspace: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py]}
  run_window: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  order_max_five_hour: {kind: string, default: "0.6", readers: [system/scripts/vaultlib/nightshift_run.py, system/scripts/vaultlib/triage.py]}
  nightshift_workspace: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py]}
  nightshift_window: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  triage_enabled: {kind: bool, default: "false", readers: [system/scripts/triage_fetch.sh]}
  triage_partition: {kind: enum, values: [work, personal], readers: [system/scripts/vaultlib/triage.py]}
  triage_watch_senders: {kind: list, of: string, readers: [system/scripts/vaultlib/triage.py]}
  triage_chat_enabled: {kind: bool, default: "false", readers: [system/scripts/triage_fetch.sh, system/scripts/vaultlib/triage.py]}
  slack_notify_channel: {kind: string, readers: [system/scripts/notify.sh, system/scripts/notify.py]}
  slack_connector: {kind: string, default: "claude.ai Slack", readers: [system/scripts/notify.sh, system/scripts/vaultlib/triage.py]}
  notify_links: {kind: enum, values: [github, obsidian], default: "github", readers: [system/scripts/vaultlib/notify.py]}
  orders_enabled: {kind: bool, default: "true", readers: [system/scripts/install_units.sh]}
  update_enabled: {kind: bool, default: "true", readers: [system/scripts/install_units.sh]}
  extensions: {kind: list, of: string, readers: [system/scripts/vaultlib/extensions.py]}
---
# Config
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.

`run_window` is the window for Work Orders queued with `--window`, as `HH:MM-HH:MM`; empty (the default) or `00:00-24:00` means always. `order_max_five_hour` is the 5-hour usage fraction at or above which no new Work Order starts.

`triage_enabled` turns on inbox triage on a standalone machine or a server (inbox triage spec): every 30 minutes on workdays, mail that needs the owner becomes an `owed` line on the Now page of `triage_partition` (default `work`). `triage_watch_senders` lists domains (`@example.com`) or addresses whose unread mail outside the inbox from the last two days also becomes an `owed` line: mail from them archived unread is not missed. `triage_chat_enabled` adds the Slack channels the owner is a member of (public and private, not DMs, bots skipped) to each triage tick, through `slack_connector` (chat triage spec).

`slack_notify_channel` turns on Slack notices on a standalone machine or a server (Slack notices spec): a Slack channel ID, or the owner's user ID for a direct message; empty is off. `slack_connector` is the connector a headless session loads: `claude.ai Slack` (the default) for Slack connected at claude.ai; `plugin:slack:slack` only when headless sessions load the Slack plugin. `claude mcp list` can show the plugin while a headless session loads only the claude.ai connector (#133); `notify.sh --check` names the server the session loaded. `notify_links` picks the notices' links: `github` (the default) or `obsidian`, an `obsidian://open?file=<path>` link that names no vault; with several vaults on one device, check which one it opens (#157).

`orders_enabled` and `update_enabled` turn on the Work Orders tick and the daily template update on a standalone machine or a server. Absent means on, so vaults made before 2026-10-12 keep both; the example config sets both to `false`, and `/setup` asks.

`nightshift_workspace` and `nightshift_window` are the old names of `order_workspace` and `run_window`. They are still read when the new key is absent; the new key wins when both are set. `order_workspace` (default `~/code/worktrees`) must sit outside the vault: every Work Order session denies the vault root, so `/order add` and the tick refuse a workspace inside it (audit S3/S7 spec).

`extensions` lists the extensions turned on (extensions spec §3): each is a tracked folder `extensions/<name>/` with an `extension.md` manifest, shipped by the template or kept by the vault alone. A listed extension with no folder is reported once a day and skipped. An extension's own config keys validate while its folder is present.
