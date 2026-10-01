---
type: schema
schema_for: plan_gate
folders: ["wiki/"]
fields:
  type: {kind: const, value: plan_gate, required: true}
  target_branch: {kind: string, required: true}
  status: {kind: enum, values: [PENDING_REVIEW, APPROVED, REJECTED], required: true}
  created_at: {kind: date, required: true}
  superpower_alignment: {kind: string}
  partition: {kind: enum, values: [work, personal, shared]}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Plan gate
An intent proposal created from `system/templates/intent-shaper.md`.
