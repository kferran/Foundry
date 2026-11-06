---
type: schema
schema_for: config
fields:
  demo_site: {kind: string}
  demo_model: {kind: string, default: "sonnet"}
  demo_timeout_minutes: {kind: int, min: "1", default: "20"}
  demo_runs_per_day: {kind: int, min: "1", max: "4", default: "1"}
---
Config fragment for the demo extension.
