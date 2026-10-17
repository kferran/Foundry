---
type: schema
schema_for: meeting
folders: ["wiki/work/meetings/", "wiki/personal/meetings/"]
fields:
  type: {kind: const, value: meeting, required: true, readers: [system/scripts/vaultlib/schema.py]}
  title: {kind: string, required: true, readers: [system/scripts/vaultlib/intake.py, .claude/commands/debrief.md]}
  date: {kind: date, required: true, readers: [system/scripts/meeting_actions.py, system/scripts/vaultlib/meeting_prep.py]}
  start: {kind: datetime, required: true, readers: [system/scripts/vaultlib/intake.py]}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true, readers: [.claude/commands/debrief.md]}
  attendees: {kind: list, of: string, readers: [system/scripts/vaultlib/intake.py]}
  source: {kind: string, required: true, readers: [system/scripts/vaultlib/intake.py, system/scripts/meetings_extract.py]}
  source_name: {kind: string, readers: []}
  transcript: {kind: link, required: true, readers: []}
  status: {kind: enum, values: [canonical, deprecated], default: canonical, readers: [system/scripts/vaultlib/intake.py, system/scripts/meeting_actions.py]}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
---
# Meeting
One meeting, written by `system/scripts/meeting_import.py` from a Gemini Doc (`source: gdoc:<id>`) or a dropped transcript (`source: drop:<sha256 of the file>`). Body: `## Summary`, `## Decisions`, `## Action items` (`- [ ] [Owner, …] Title: text`; tick a line to close it) and `## Details`. No headless run rewrites a meeting note, except the import filling a note's empty sections from a later Gemini Doc of the same meeting, or adding an `Another transcript: [[<name>.transcript]]` line under the title for a later dropped transcript; retire one with `status: deprecated`.
