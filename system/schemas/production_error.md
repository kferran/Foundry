---
type: schema
schema_for: production_error
folders: ["raw/telemetry/"]
fields:
  type: {kind: const, value: production_error, required: true}
  service: {kind: string, required: true}
  exception: {kind: string, required: true}
  message: {kind: string}
  operation_id: {kind: string, required: true}
  detected_at: {kind: datetime, required: true}
  is_friction: {kind: bool, default: "false"}
  codebase: {kind: string}
  partition: {kind: enum, values: [work, personal, shared]}
  mock: {kind: bool, default: "false"}
  environment: {kind: string}
  source: {kind: string}
  kind: {kind: enum, values: [sentry, log, span]}
  fingerprint: {kind: string}
  count: {kind: int, min: "0"}
  last_seen: {kind: datetime}
  status: {kind: enum, values: [active, resolved, deprecated], default: active}
  resolved_at: {kind: datetime}
  substatus: {kind: string}
  regressed: {kind: bool, default: "false"}
  sentry_issue: {kind: string}
  covered: {kind: bool, default: "false"}
  culprit: {kind: string}
  link: {kind: string}
---
# Production error
A production error group in raw/telemetry/, written by telemetry_fetch.py (Plan 11) or dropped by hand (mock). Routed to the Workcell with telemetry; never ingested. Holds group keys, counts, times, opaque IDs, links and one message (the Sentry issue title or a sample log message) with ticket identifiers; credentials and emails are masked.
