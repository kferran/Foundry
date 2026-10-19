---
type: schema
schema_for: today
folders: ["briefings/"]
fields:
  type: {kind: const, value: today, required: true, readers: [extensions/intraday/scripts/today_log.py]}
  date: {kind: date, required: true, readers: [extensions/intraday/scripts/today_log.py]}
---
# Today
The day's log `briefings/<date>.today.md` (phase D spec §3.6), appended by the intraday extension's writer on the server and embedded in the day's briefing under 🕑 Today so far. Append-only: one line per watched item, calendar change, session digest, imported meeting and capture. Never edit it by hand.
