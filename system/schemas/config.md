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
  handoffs_site: {kind: string}
  handoffs_projects: {kind: list, of: string}
  rca_project: {kind: string}
  rca_issue_type: {kind: string, default: "Bug"}
  rca_labels: {kind: list, of: string}
  rca_assignee: {kind: string}
  triage_enabled: {kind: bool, default: "false"}
  triage_partition: {kind: enum, values: [work, personal]}
  slack_notify_channel: {kind: string}
  slack_connector: {kind: string, default: "plugin:slack:slack"}
  orders_enabled: {kind: bool, default: "true"}
  update_enabled: {kind: bool, default: "true"}
---
# Config
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.

`run_window` is the window for Work Orders queued with `--window`, as `HH:MM-HH:MM`; empty (the default) or `00:00-24:00` means always. `order_max_five_hour` is the 5-hour usage fraction at or above which no new Work Order starts.

`handoffs_site` (the Jira site's host name) and `handoffs_projects` (Jira project keys) turn on the brief's Handoffs to chase (delivered work spec §3.1); it stays off while `handoffs_projects` is empty.

`rca_project` (a Jira project key) turns on filing approved `/rca` drafts to `handoffs_site`, as `rca_issue_type` (default `Bug`) with `rca_labels` and, when set, the Atlassian account ID `rca_assignee` (RCA spec §3.4); filing stays off while `rca_project` is empty.

`triage_enabled` turns on inbox triage on a standalone machine or a server (inbox triage spec): every 30 minutes on workdays, mail that needs the owner becomes an `owed` line on the Now page of `triage_partition` (default `work`).

`slack_notify_channel` turns on Slack notices on a standalone machine or a server (Slack notices spec): a Slack channel ID, or the owner's user ID for a direct message; empty is off. `slack_connector` is the connector as `claude mcp list` names it (default `plugin:slack:slack`).

`orders_enabled` and `update_enabled` turn on the Work Orders tick and the daily template update on a standalone machine or a server. Absent means on, so vaults made before 2026-10-12 keep both; the example config sets both to `false`, and `/setup` asks.

`nightshift_workspace` and `nightshift_window` are the old names of `order_workspace` and `run_window`. They are still read when the new key is absent; the new key wins when both are set.
