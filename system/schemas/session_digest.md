---
type: schema
schema_for: session_digest
folders: ["raw/work/notes/", "raw/personal/notes/", "raw/shared/notes/", "raw/work/archive/", "raw/personal/archive/", "raw/shared/archive/"]
fields:
  type: {kind: const, value: session_digest, required: true}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true}
  codebase: {kind: string, required: true}
  session_id: {kind: string, required: true}
  created_at: {kind: datetime, required: true}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
  redactions: {kind: int, default: "0"}
  work_order: {kind: string}
---
# Session digest
A memory digest written by the Stop hook from `last_assistant_message`. Compiled into the wiki by the intake compiler.
