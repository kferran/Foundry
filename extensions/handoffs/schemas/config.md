---
type: schema
schema_for: config
fields:
  handoffs_projects: {kind: list, of: string}
---
`handoffs_projects` (Jira project keys) turns on the brief's Handoffs to chase (delivered work spec §3.1); it stays off while `handoffs_projects` is empty. The Jira site is core's `handoffs_site`, which the RCA filer also reads; it moves here with the telemetry extension.
