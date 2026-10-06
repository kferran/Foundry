# Plan 11 spike: Sentry trace-ID coverage (Task 1)

**Date:** 2026-10-05
**Question (spec §3.4):** do Sentry error events carry the OpenTelemetry trace ID that the same requests have in Azure Data Explorer, so that an ADX error group can be matched to its Sentry issue by trace?

## Method

On the first configured codebase, interactive session, read-only:

1. ADX production database: the distinct `TraceID` of three recent `Logs` rows with `SeverityNumber >= 17`.
2. Sentry production project, Discover on the `errors` dataset: `query=trace:[<the three IDs>]`, fields `issue`, `trace`, last 7 days.
3. Sentry: the five latest error events with `has:trace`, fields `issue`, `issue.id`, `trace`.
4. ADX: those five Sentry trace IDs in `Logs` and `Traces` over the last day.

## Result

| Check | Result |
|---|---|
| Sentry error events carry a trace ID | yes (5 of 5, 32 hex digits) |
| ADX error traces found in Sentry | no (0 of 3) |
| Sentry traces found in ADX `Logs` or `Traces` | no (0 of 4 distinct) |

The two systems use different trace IDs for the same requests on this codebase: the Sentry SDK starts its own traces instead of continuing the OpenTelemetry ones.

## Consequence

- `covers` stays in Plan 11 as an opt-in for codebases whose Sentry SDK continues OpenTelemetry traces. It is not set for this codebase, and `/setup` phase 6a asks for it only when the user confirms the two share trace IDs.
- With `covers` unset, the brief lists ADX groups and Sentry issues separately under each environment.
- Endpoint and fields that work for the lookup: `GET /api/0/organizations/<org>/events/?dataset=errors&field=issue&field=issue.id&field=trace&query=trace:<id>&statsPeriod=14d` (the `issue` column holds the short ID).
