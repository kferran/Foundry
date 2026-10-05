---
type: schema
schema_for: concept
folders: ["wiki/work/", "wiki/personal/", "wiki/shared/"]
fields:
  type: {kind: const, value: concept, required: true}
  tags: {kind: list, of: string, required: true}
  compiled_at: {kind: date, required: true}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true}
  codebase: {kind: string}
  capability: {kind: enum, values: [code, tests, refactor, vault-health, dependencies, telemetry, alerts]}
  is_friction: {kind: bool, default: "false"}
  status: {kind: enum, values: [canonical, draft, deprecated], default: canonical}
  supersedes: {kind: list, of: link}
  superseded_by: {kind: link}
  aliases: {kind: list, of: string}
  sources: {kind: list, of: link}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Concept
An evergreen, atomic knowledge node compiled from raw inputs and session digests. Retire with `status: deprecated` or supersession; never delete. `capability` is set only on a note that assigns work: the capability the work needs, from the union of the Workcells' `capabilities` in `system/agents/workcells/` (work for the Foreman needs no field).
