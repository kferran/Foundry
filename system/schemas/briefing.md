---
type: schema
schema_for: briefing
folders: ["briefings/"]
fields:
  type: {kind: const, value: briefing, required: true, readers: [system/scripts/vaultlib/schema.py]}
  date: {kind: date, required: true, readers: []}
  status: {kind: enum, values: [active, closed], default: active, readers: []}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}, readers: [system/scripts/vaultlib/publish.py]}
---
# Briefing
The daily ledger `briefings/<date>.md`, written by `/brief`. The evening section embeds `<date>.debrief`.
