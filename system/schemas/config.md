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
---
# Config
The per-user global configuration written by `/setup` (gitignored). `system/config.example.md` is the committed example.
