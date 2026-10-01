---
type: schema
schema_for: briefing
folders: ["briefings/"]
fields:
  type: {kind: const, value: briefing, required: true}
  date: {kind: date, required: true}
  status: {kind: enum, values: [active, closed], default: active}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# Briefing
The daily ledger `briefings/<date>.md`, written by `/brief`. The evening section embeds `<date>.debrief`.
