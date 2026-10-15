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
machine_role: "standalone"      # standalone | server | client; what this machine does (see FOUNDRY.md)
sync_interval_minutes: "5"      # server only: minutes between vault syncs (1-60)
meetings_enabled: "false"       # server and standalone: fetch Gemini notes from Google Drive on workdays
meetings_partition: ""          # work | personal: where fetched meetings go (empty: default_partition, or personal when that is shared)
owner_names: []                 # your names as they appear in meeting action items, e.g. ["Avery Sample"]
handoffs_site: ""               # server and standalone: your Jira site's host name, e.g. example.atlassian.net
handoffs_projects: []           # Jira project keys whose stalled handoffs the brief lists, e.g. ["EX"]; empty is off
rca_project: ""                 # Jira project key approved /rca drafts are filed to, e.g. "EX"; empty is off
rca_issue_type: "Bug"           # the issue type /rca files
rca_labels: []                  # labels /rca puts on each ticket, e.g. ["production-finding"]
rca_assignee: ""                # Atlassian account ID to assign /rca tickets to; empty leaves them unassigned
rca_extra_fields: {}            # a required custom field per Jira field id, e.g. {customfield_10042: '{"id": "10042"}'}; JSON values are sent as JSON
triage_enabled: "false"         # server and standalone: every 30 minutes on workdays, mail that needs you goes to the Now page
triage_partition: "work"        # work | personal: the Now page triage writes to
triage_watch_senders: []        # domains or addresses whose mail archived unread still reaches the Now page, e.g. ["@example.com"]
slack_notify_channel: ""        # server and standalone: a Slack channel ID, or your user ID for a DM; empty is off
slack_connector: "claude.ai Slack"  # the Slack connector a headless session loads (notify.sh --check names it)
notify_links: "github"          # notice links: github (a GitHub file link) or obsidian (an obsidian:// link)
orders_enabled: "false"         # server and standalone: the Work Orders tick every 15 minutes (/setup asks)
update_enabled: "false"         # server and standalone: merge template updates every morning (/setup asks)
superpowers: []
---
# Config (example)

`/setup` copies this file to `system/config.md` (gitignored) and fills it in with you. Edit `system/config.md`, not this file.
