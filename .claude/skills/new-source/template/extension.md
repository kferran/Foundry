---
name: @@name@@
contract: 1
description: "@@description@@"
requires: []
sources:
  - {name: @@name@@, credential: "@@credential@@", renew: "@@renew@@"}
smoke:
  - {source: @@name@@, timeout: 360, connector: true, run: "scripts/@@name@@_fetch.sh --check"}
brief: true
units: []
alert_tags: [@@name@@]
allow: ["Bash(extensions/@@name@@/scripts/@@name@@_fetch.sh --check)"]
deps: []
index_ignore: []
budget:
  values: {@@NAME@@_TIMEOUT: 300}
  steps:
    - "brief 1 grace.listing listing"  # the brief's prep runs @@name@@_fetch.sh, its own process
    - "brief 1 grace.connector @@NAME@@_TIMEOUT"
    - "smoke/@@name@@ 1 grace.listing listing"
    - "smoke/@@name@@ 1 grace.connector @@NAME@@_TIMEOUT"
---
**@@description@@.** Each morning brief reads `@@tool@@` once, in a session allowed only that tool, and lists what it read. TODO(feature): say what the call reads and what each brief line shows.

Run `extensions/@@name@@/scripts/@@name@@_fetch.sh --check` with a Bash timeout of at least 400000 ms (one session). On exit 0, report its `the session read N lines` line. Otherwise report the reason it printed and what to do: exit 1 with an allow rule named, replace a rule that allows every tool on the server with single tools (the fetch will not run while the whole server is allowed); exit 3, connect @@server@@ in the account's connector settings at claude.ai (same account as this machine); exit 6, @@renew@@; exit 4, try again later; exit 7, show the @@name@@ alert in `system/logs/alerts_<date>.md`. A failure never blocks setup: the brief then shows @@name@@ as failed on its Sources line.
