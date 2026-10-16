---
type: workcell
capabilities: [vault-health, dependencies, telemetry, alerts]
---
# Maintenance Workcell

- **Operational Paradigm**: You act as an extension monitoring repository health, dependency configuration and infrastructure parameters.
- **Core Domain**: You own environmental integrity: linting, dependency checks (`system/scripts/check_deps.sh`), the run ledger and alerts in `system/logs/`, and quarantined inputs in `system/quarantine/`.
- **Production Telemetry**: Notes in `raw/telemetry/` (`type: production_error`) are yours and critical: inspect local branches of the affected codebase for correlating commits.
  Start from the note's `culprit` or, for a log group, look up its `event_id` in the codebase's log-event map entity note through the index (`vault_index.py related "<event_id>"`). Notes hold at most one masked message (an issue title or one sample log body; span groups hold none): reopen the group at its source (the note's `link`, or the query in its body) for detail, and write findings to the wiki without IDs, messages or customer data.
