---
type: schema
schema_for: preference
folders: ["wiki/work/preferences/", "wiki/personal/preferences/"]
fields:
  type: {kind: const, value: preference, required: true, readers: [system/scripts/vaultlib/schema.py]}
  statement: {kind: string, required: true, readers: [.claude/commands/ingest.md]}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true, readers: [.claude/commands/ingest.md]}
  codebase: {kind: string, readers: []}
  evidence: {kind: list, of: link, readers: [.claude/commands/ingest.md]}
  counter_evidence: {kind: list, of: link, readers: []}
  supersedes: {kind: list, of: link, readers: [system/scripts/vaultlib/index.py]}
  superseded_by: {kind: link, readers: [system/scripts/vaultlib/index.py]}
  accepted_at: {kind: date, readers: [system/scripts/vaultlib/publish.py]}
  rejected_at: {kind: date, readers: [system/scripts/vaultlib/index.py, system/scripts/vaultlib/publish.py]}
  created_at: {kind: date, readers: []}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
---
# Preference
A user correction or stated preference. Status (unconfirmed, candidate, confirmed, retired) is derived in the index, never stored. Spec §6.21.
