---
type: telemetry_source
name: "example"
codebase: "example"
environment: "prod"
kind: "adx"
enabled: "false"
adx_cluster: "https://example.westus.kusto.windows.net"
adx_database: "production"
adx_filter: {}
---
An example ADX source. `/setup` phase 6a writes real ones next to it (gitignored). A Sentry source sets `kind: "sentry"`, `sentry_url`, `sentry_org` and `sentry_projects` instead of the `adx_*` fields.

`adx_filter` selects rows by resource attribute, for example `{instanceId: "U1"}`. An empty value, `{instanceId: ""}`, selects the rows that lack the attribute: shared services that log without it. Give them a second source on the same database.
