---
type: schema
schema_for: concept
folders: ["wiki/work/", "wiki/personal/", "wiki/shared/"]
fields:
  type: {kind: const, value: concept, required: true, readers: [system/scripts/vaultlib/schema.py]}
  tags: {kind: list, of: string, required: true, readers: [system/scripts/vaultlib/index.py, system/scripts/vaultlib/publish.py]}
  compiled_at: {kind: date, required: true, readers: [system/scripts/vaultlib/friction.py, system/scripts/vaultlib/retrieve.py, .claude/commands/lint.md]}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true, readers: [system/scripts/vaultlib/index.py]}
  codebase: {kind: string, readers: [system/scripts/vaultlib/retrieve.py]}
  capability: {kind: enum, values: [code, tests, refactor, vault-health, dependencies, telemetry, alerts, research], readers: []}
  is_friction: {kind: bool, default: "false", readers: [system/scripts/vaultlib/friction.py]}
  status: {kind: enum, values: [canonical, draft, deprecated], default: canonical, readers: [system/scripts/vaultlib/index.py]}
  supersedes: {kind: list, of: link, readers: [system/scripts/vaultlib/index.py]}
  superseded_by: {kind: link, readers: [system/scripts/vaultlib/index.py]}
  aliases: {kind: list, of: string, readers: [system/scripts/vaultlib/index.py, system/scripts/vaultlib/meeting_prep.py]}
  sources: {kind: list, of: link, readers: [system/scripts/vaultlib/index.py, system/scripts/vaultlib/nightshift_deliver.py]}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
---
# Concept
An evergreen, atomic knowledge node compiled from raw inputs and session digests. Retire with `status: deprecated` or supersession; never delete. `capability` is set only on a note that assigns work: the capability the work needs, from the union of the Workcells' `capabilities` in `system/agents/workcells/` (work for the Foreman needs no field). `tags` are lowercase kebab-case, `/` between the parts of a nested tag; reuse one from `system/scripts/vault_index.py tags --partition <p>` before inventing one.
