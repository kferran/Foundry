# Incident push: a new production error reaches Slack within the hour

**Date:** 2026-10-15
**Issue:** #158 follow-up. Owner (2026-10-15): production issues seen first in team chat channels "would have been helpful to have elevated"; "include production alerts as a small follow up".

## 1. Problem

Production error groups reach the owner only through the next brief (Blockers → Telemetry, and the Escalated block after 24 hours, #171). The `[telemetry]` alert lines are about the fetch itself, never about the errors, so an incident that starts after the 05:00 brief is silent until the next morning, before and after the alert tags change (#213).

## 2. Decisions

- **A new tag, `incident`, severity `now`.** The hourly telemetry run writes one `[incident]` line for each group that is new, or that was resolved and came back, in a source whose `environment` starts with `prod` (case-insensitive; the example source uses `prod`). Line: `<source>: new production error in <service>: <error> (<n> events) raw/telemetry/<note>.md`, or `… a resolved production error is back in …`.
- **Bounded.** At most 3 lines per source per run, then one `<source>: and <n> more new production errors (see the brief)` line; once a day per group (the run's existing alert key store). A source's first run (no checkpoint) pushes nothing, so turning a source on sends no backlog. An ADX group covered by a Sentry issue is left to the Sentry source.
- **The brief does not repeat it.** Pipeline leaves `[incident]` lines out; Telemetry already lists the groups.
- **Not here:** a count spike on an old group (no baseline yet); team chat channels that mention production problems (a separate source, its own spec).

## 3. Changes

`vaultlib/telemetry_run.py` (`_push`, the tag on `_alert`, control characters stripped from error text), `vaultlib/alerts.py` (`incident`), `brief.md` Pipeline, `FOUNDRY.md` (table row and one paragraph).

## 4. Tests

`test_telemetry_run.py`: first run pushes nothing, a new production group pushes one line once, a non-production source pushes nothing, a returning group pushes, a burst is capped at 3 plus a count line. `test_alerts.py`: `incident` is now. `commands.bats`: the manual and the brief rule.
