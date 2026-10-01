---
type: schema
schema_for: debrief
folders: ["briefings/"]
fields:
  type: {kind: const, value: debrief, required: true}
  date: {kind: date, required: true}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Debrief
The evening debrief `briefings/<date>.debrief.md`, written by `/debrief` and embedded in the day's briefing.
