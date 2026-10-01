---
type: schema
schema_for: production_error
folders: ["raw/telemetry/"]
fields:
  type: {kind: const, value: production_error, required: true}
  service: {kind: string, required: true}
  exception: {kind: string, required: true}
  operation_id: {kind: string, required: true}
  detected_at: {kind: datetime, required: true}
  is_friction: {kind: bool, default: "false"}
  assigned_agent: {kind: enum, values: [CodingAgent, SystemMaintenance, Optimus]}
  codebase: {kind: string}
  partition: {kind: enum, values: [work, personal, shared]}
  mock: {kind: bool, default: "false"}
---
# Production error
A production exception note dropped into `raw/telemetry/`. Routed to SystemMaintenance; never ingested.
