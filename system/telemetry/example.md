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
