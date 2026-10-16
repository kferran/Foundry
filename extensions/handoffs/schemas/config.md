---
type: schema
schema_for: config
fields:
  handoffs_site: {kind: string}
  handoffs_projects: {kind: list, of: string}
---
`handoffs_site` is the Jira site's host name. `handoffs_projects` (Jira project keys) turns on the brief's Handoffs to chase (delivered work spec §3.1); it stays off while `handoffs_projects` is empty. The telemetry extension's RCA filer files to `handoffs_site` too, so it requires this extension.
