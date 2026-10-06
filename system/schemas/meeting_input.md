---
type: schema
schema_for: meeting_input
folders: ["raw/work/notes/", "raw/personal/notes/", "raw/work/archive/", "raw/personal/archive/"]
fields:
  type: {kind: const, value: meeting_input, required: true}
  meeting: {kind: link, required: true}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true}
  created_at: {kind: datetime, required: true}
---
# Meeting input
What the meeting import hands to `/ingest`: the meeting note's link, and its summary, decisions and details as the body. Intake ingests each one alone.
