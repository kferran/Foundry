---
name: handoffs
contract: 1
description: "Stalled Jira handoffs in the morning brief"
requires: []
config_keys:
  handoffs_projects: {kind: list, of: string}
sources:
  - {name: handoffs, credential: "Atlassian connector", renew: "reconnect it at claude.ai, Settings, Connectors"}
smoke:
  - {source: handoffs, timeout: 360, connector: true, run: "scripts/jira_fetch.sh --check"}
brief: true
units: []
alert_tags: [handoffs]
allow: ["Bash(extensions/handoffs/scripts/jira_fetch.sh --check)"]
deps: []
index_ignore: []
---
**Handoffs to chase.** Each morning brief lists the Jira tickets you reported that someone else holds, open with no status-category change for 7 days (delivered work spec §3).

Ask for the Jira site's host name, such as `example.atlassian.net` (`handoffs_site`, a core key the RCA filer shares), and the project keys whose handoffs the brief lists (`handoffs_projects`, a list such as `["EX"]`; empty is off). Write both by editing `system/config.md`, then run `system/scripts/vault_index.py validate system/config.md`. Only keys, summaries and links are read, and nothing is written to Jira. Then run `extensions/handoffs/scripts/jira_fetch.sh --check` with a Bash timeout of at least 400000 ms (one search session). On exit 0, report its `the search listed N stalled handoffs` line. Otherwise report the reason it printed and what to do: exit 1 with an allow rule named, replace a rule that allows every Atlassian tool with single tools (the fetch will not run while the whole server is allowed); exit 2, fix the setting it names; exit 3, connect Atlassian in the account's connector settings at claude.ai (same account as this machine); exit 6, reconnect it (unless the reason says a result was too large for the model to read: report that, reconnecting does not fix it); exit 4, try again later; exit 7, show the handoffs alert in `system/logs/alerts_<date>.md`. A Jira failure never blocks setup: the brief then shows handoffs as failed on its Sources line.
