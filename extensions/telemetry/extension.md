---
name: telemetry
contract: 1
description: "Production errors from Sentry and Azure Data Explorer in the brief, and /rca with ticket filing"
requires: [handoffs]
config_keys:
  rca_project: {kind: string}
  rca_issue_type: {kind: string, default: "Bug"}
  rca_labels: {kind: list, of: string}
  rca_assignee: {kind: string}
  rca_extra_fields: {kind: map, of: string}
sources: []
smoke:
  - {source: telemetry, timeout: 120, connector: false, each: "scripts/telemetry_fetch.py --sources", run: "scripts/telemetry_fetch.py --check {}"}
brief: true
units:
  - {name: foundry-telemetry, roles: [standalone, server]}
tick: {run: "scripts/rca.py tick", timeout: 1900}
lint: scripts/telemetrylib/lint.py
alert_tags: [telemetry, incident, rca]
allow: ["Bash(extensions/telemetry/scripts/telemetry_fetch.py --list)", "Bash(extensions/telemetry/scripts/telemetry_fetch.py --check *)"]
deps: [az]
index_ignore: []
---
**Error telemetry.** Each error group from your sources becomes a `production_error` note in `raw/telemetry/`, listed in the brief's Blockers, and `/rca` diagnoses one group and drafts a ticket that is filed only after you tick its Now line. Requires the `handoffs` extension: tickets are filed to its `handoffs_site`.

**Setup.** Skipped on a client.
1. Show existing `system/telemetry/*.md` and ask whether to edit any. Never replace one.
2. For each registered codebase, ask whether it reports errors to Sentry, ADX, both or neither. For Sentry: the API base URL (for example `https://us.sentry.io`), the organization slug, and the project slugs per environment. For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database). A filter value of `""` selects the rows that lack the attribute: offer that as a separate source when shared services log without it. Ask for a `rank` per environment (lower is listed first in the brief). Ask whether an ADX source `covers` its Sentry source only after the user confirms the codebase's Sentry SDK continues the OpenTelemetry traces (shares trace IDs with ADX); otherwise leave `covers` unset.
3. Sentry needs a read-only token (`event:read`, `project:read`, `org:read`). Ask the user to write it themselves: `! mkdir -p ~/.config/foundry && (umask 077; cat > ~/.config/foundry/sentry.token)`, paste, Ctrl-D. Never ask for the token in chat. Check it is mode 0600.
4. ADX uses the Azure CLI login: if `az account show` fails, ask the user to run `! az login`.
5. Write each source as `system/telemetry/<name>.md` (`<codebase>-<environment>-<kind>` by default) from `extensions/telemetry/templates/telemetry-source.example.md`, run `system/scripts/vault_index.py validate system/telemetry/<name>.md`, then `extensions/telemetry/scripts/telemetry_fetch.py --check <name>`. On a failed check, set `enabled: "false"` and report its line.
6. **RCA filing.** Ask whether approved `/rca` drafts should be filed to Jira (RCA spec §3.4). On yes, check that `handoffs_site` is set (the handoffs extension's setup asks for it), then ask for the project key (`rca_project`), the issue type (`rca_issue_type`, default `Bug`), labels (`rca_labels`, one per line) and, optionally, the Atlassian account ID to assign tickets to (`rca_assignee`). Write the scalars with `system/scripts/vault_index.py set` and `rca_labels` by editing the file, then validate. Nothing is filed until you tick an RCA draft's line on the Now page; an empty `rca_project` keeps filing off.

**The fetch.** `foundry-telemetry.timer` runs `telemetry_fetch.py` every hour, and the brief's prep runs it once more before the brief. Each source in `system/telemetry/<name>.md` is a set of Sentry projects or one Azure Data Explorer database with a filter. An empty filter value (`adx_filter: {deployment.instance: ""}`) selects the rows that lack that attribute, so shared services that log without it get a source of their own. A filter on one value and an empty filter on the same key never select the same row; a source with no filter (`{}`) overlaps both and counts their groups twice. Each error group becomes one `production_error` note in `raw/telemetry/` holding group keys, counts, times, opaque IDs, links and the Sentry issue title or one sample log message, ticket identifiers included; credentials and emails are masked. The fetch sets `escalate: persistent` on an active ADX group once the group has been seen over at least 24 hours and is still firing. Sentry groups never escalate (their own `substatus` lists them as new). Sentry needs a read-only token in `~/.config/foundry/sentry.token` (mode 0600); ADX uses your `az login`. `--check <name>` tests a source, `--dry-run` prints the groups without writing, and `--sources` lists each enabled source with the login it needs (the smoke check and the Sources line read it).

**The brief.** The brief's prep writes the active groups and those resolved in the last 24 hours to its section file: first an **Escalated** block across environments, at most 3 rows by count, then per environment new groups as a table, recurring as one line with a count and the three largest, resolved as a count; each group escalated in the last 24 hours, at most 3 per brief, becomes an `owed` Now line whose evidence is the note path, which you tick.

**RCA.** `/rca raw/telemetry/<note>.md` diagnoses one production error group in an interactive session, read-only on code: symptom to code areas through the index, the environment from the note, the logs the note stores, a trace to `file:line`, and a root-cause confidence and a fix confidence (1 to 5 each). It writes an `rca` note to `wiki/<partition>/rca/` with a Ticket draft and adds "Review RCA draft: …" to the Now page. Ticking that line approves filing: on the next intake tick (this extension's `tick`), `rca_file.sh` runs a confined session that may only create one Jira issue, with the draft's summary and description and the `rca_*` settings, then writes the key back to the note. The tick marks the note `approved`, so the approval outlasts the line. A ticket is never filed twice: if a session called the create tool and no key came back, filing that draft stops with a `[rca]` alert until you find the ticket in Jira and record it with `extensions/telemetry/scripts/rca.py filed <partition> <stem> <key>`, or delete the `.attempt` file the alert names to file again. When Jira refuses the create with a client error (a required field, a bad value, no permission), nothing exists, so the draft goes back to `draft` and its Now line is unticked with the reason; set the field in `rca_extra_fields` (Jira field id to value) and tick the line again. Tickets go to `rca_assignee` or stay unassigned. Dropping the line (`[-]`) rejects a draft. Filing and rejecting are off until `rca_project` is set. A draft marked `hotfix_candidate` also raises an alert line.

**Security.** `telemetry_fetch.py` runs no model and keeps network access out of headless runs. Sentry and ADX responses are reduced to group keys, counts and one title or sample message before anything is written. Group keys keep their shape (GUIDs, emails, long hex and digit runs, URL query strings collapsed); titles and messages keep ticket identifiers with credentials and emails masked; the note store re-checks every field. The Sentry token lives outside the vault, so git and sync never carry it. The RCA filer is one connector session allowed only the Atlassian connector's create tool.
