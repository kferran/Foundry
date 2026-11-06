---
type: schema
schema_for: config
fields:
  demo_site: {kind: string}
  demo_model: {kind: string, default: "sonnet"}
  demo_timeout_minutes: {kind: int, min: "1", default: "20"}
---
Config fragment for the demo extension.
