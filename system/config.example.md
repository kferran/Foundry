---
type: config
timezone: "America/Denver"
brief_time: "06:00"
debrief_time: "17:00"
remote_mode: "none"             # private | none | keep; set by setup_remote.sh
default_partition: "personal"   # partition for vault sessions and inbox files without one
digest_min_events: "5"          # tool calls/edits since the last digest before a digest is requested
digest_min_minutes: "20"        # minimum minutes between digests
preferences_enabled: "false"    # preference derivation, /brief acceptance and recall slot (a later phase)
recall_budget_chars: "9000"     # SessionStart recall size cap (hard max 9500)
template_remote: ""             # set by setup_remote.sh
superpowers:
  - "<strategic anchor>"
---
# Config (example)

`/setup` copies this file to `system/config.md` (gitignored) and fills it in with you. Edit `system/config.md`, not this file.
