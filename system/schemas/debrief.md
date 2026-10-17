---
type: schema
schema_for: debrief
folders: ["briefings/"]
fields:
  type: {kind: const, value: debrief, required: true, readers: [system/scripts/vaultlib/schema.py]}
  date: {kind: date, required: true, readers: []}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
---
# Debrief
The evening debrief `briefings/<date>.debrief.md`, written by `/debrief` and embedded in the day's briefing.
