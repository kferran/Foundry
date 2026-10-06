---
type: schema
schema_for: meeting
folders: ["wiki/work/meetings/", "wiki/personal/meetings/"]
fields:
  type: {kind: const, value: meeting, required: true}
  title: {kind: string, required: true}
  date: {kind: date, required: true}
  start: {kind: datetime, required: true}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true}
  attendees: {kind: list, of: string}
  source: {kind: string, required: true}
  source_name: {kind: string}
  transcript: {kind: link, required: true}
  status: {kind: enum, values: [canonical, deprecated], default: canonical}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Meeting
One meeting, written by `system/scripts/meeting_import.py` from a Gemini Doc (`source: gdoc:<id>`) or a dropped transcript (`source: drop:<sha256 of the file>`). Body: `## Summary`, `## Decisions`, `## Action items` (`- [ ] [Owner, …] Title: text`; tick a line to close it) and `## Details`. No headless run rewrites a meeting note; retire one with `status: deprecated`.
