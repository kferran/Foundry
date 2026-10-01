---
type: schema
schema_for: preference
folders: ["wiki/work/preferences/", "wiki/personal/preferences/"]
fields:
  type: {kind: const, value: preference, required: true}
  statement: {kind: string, required: true}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true}
  codebase: {kind: string}
  evidence: {kind: list, of: link}
  counter_evidence: {kind: list, of: link}
  supersedes: {kind: list, of: link}
  superseded_by: {kind: link}
  accepted_at: {kind: date}
  rejected_at: {kind: date}
  created_at: {kind: date}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Preference
A user correction or stated preference. Status (unconfirmed, candidate, confirmed, retired) is derived in the index, never stored. Spec §6.21.
