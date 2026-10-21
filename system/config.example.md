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
transcript_keep_dir: ""         # memory hooks: where transcript copies go, outside the vault (empty: ~/.local/state/foundry/transcripts)
transcript_keep_days: "90"      # memory hooks: delete transcript copies not refreshed for this many days (0: never)
template_remote: ""             # set by setup_remote.sh
machine_role: "standalone"      # standalone | server | client; what this machine does (see FOUNDRY.md)
sync_interval_minutes: "5"      # server only: minutes between vault syncs (1-60)
meetings_enabled: "false"       # server and standalone: fetch Gemini notes from Google Drive on workdays
meetings_partition: ""          # work | personal: where fetched meetings go (empty: default_partition, or personal when that is shared)
owner_names: []                 # your names as they appear in meeting action items, e.g. ["Avery Sample"]
triage_enabled: "false"         # server and standalone: every 30 minutes on workdays, mail that needs you goes to the Now page
triage_partition: "work"        # work | personal: the Now page triage writes to
triage_watch_senders: []        # domains or addresses whose mail archived unread still reaches the Now page, e.g. ["@example.com"]
triage_chat_enabled: "false"    # with triage on: also the Slack channels you are in (not DMs), every tick
slack_notify_channel: ""        # server and standalone: a Slack channel ID, or your user ID for a DM; empty is off
slack_connector: "claude.ai Slack"  # the Slack connector a headless session loads (notify.sh --check names it)
notify_links: "github"          # notice links: github (a GitHub file link) or obsidian (an obsidian:// link)
slack_notify_thread: "off"      # daily: every notice is a reply in one thread a day, and the channel can be the capture channel
orders_enabled: "false"         # server and standalone: the Work Orders tick every 15 minutes (/setup asks)
update_enabled: "false"         # server and standalone: merge template updates every morning (/setup asks)
extensions: []                 # extensions turned on, by folder name under extensions/ (/setup phase 6e asks)
superpowers: []
---
# Config (example)

`/setup` copies this file to `system/config.md` (gitignored) and fills it in with you. Edit `system/config.md`, not this file.
