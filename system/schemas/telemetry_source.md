---
type: schema
schema_for: telemetry_source
folders: ["system/telemetry/"]
fields:
  type: {kind: const, value: telemetry_source, required: true}
  name: {kind: string, required: true}
  codebase: {kind: string, required: true}
  environment: {kind: string, required: true}
  kind: {kind: enum, values: [sentry, adx], required: true}
  enabled: {kind: bool, default: "true"}
  rank: {kind: int, default: "50", min: "0", max: "999"}
  sentry_url: {kind: string}
  sentry_org: {kind: string}
  sentry_projects: {kind: list, of: string}
  sentry_query: {kind: string, default: "is:unresolved level:[error,fatal]"}
  adx_cluster: {kind: string}
  adx_database: {kind: string}
  adx_filter: {kind: map, of: string}
  adx_signals: {kind: list, of: {kind: enum, values: [logs, spans]}}
  adx_group_keys: {kind: list, of: string}
  covers: {kind: string}
---
# Telemetry source
One error source for a registered codebase (Plan 11 spec §2.1): a set of Sentry projects or one ADX database with a filter. Written by `/setup` phase 6a; gitignored except `example.md`. The linter checks the cross-field rules: only the fields of its `kind`, `name` equal to the file name, an existing `codebase`, and `covers` naming an enabled `sentry` source with the same `environment`.
