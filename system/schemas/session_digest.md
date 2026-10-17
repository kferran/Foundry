---
type: schema
schema_for: session_digest
folders: ["raw/work/notes/", "raw/personal/notes/", "raw/shared/notes/", "raw/work/archive/", "raw/personal/archive/", "raw/shared/archive/"]
fields:
  type: {kind: const, value: session_digest, required: true, readers: [system/scripts/vaultlib/schema.py]}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true, readers: [system/scripts/vaultlib/recall.py, system/scripts/debrief_prep.sh]}
  codebase: {kind: string, required: true, readers: [system/scripts/vaultlib/recall.py, system/scripts/debrief_prep.sh]}
  session_id: {kind: string, required: true, readers: []}
  created_at: {kind: datetime, required: true, readers: [system/scripts/vaultlib/recall.py, system/scripts/debrief_prep.sh]}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
  redactions: {kind: int, default: "0", readers: []}
  work_order: {kind: string, readers: []}
---
# Session digest
A memory digest written by the Stop hook from `last_assistant_message`. Compiled into the wiki by the intake compiler.
