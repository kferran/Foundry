# Error Monitoring from Sentry and Azure Data Explorer (Plan 11)

**Date:** 2026-10-05
**Status:** Approved in brainstorming (2026-10-05), awaiting written-spec review
**Revised:** 2026-10-07: data policy (identifiers kept, credentials and emails masked); `docs/superpowers/plans/2026-10-07-telemetry-identifiers.md`
**Extends:** `2026-09-30-vault-template-design.md` (production telemetry, `raw/telemetry/`, the Workcell with `telemetry`); `2026-10-03-two-machines-design.md` (units by role)
**Roadmap:** Plan 11; sub-projects A (access layer) and B (scheduled error digest) of four. C (alerts) and D (on-demand `/logs`) get their own specs.

## 1. Problem and decisions

The vault already reserves a slot for production errors: `production_error` notes in `raw/telemetry/` are critical in `/brief` and route to the Workcell with `telemetry`. Nothing writes them. This plan fills the slot from the two places a registered codebase reports errors: Sentry (grouped issues) and Azure Data Explorer (ADX; OpenTelemetry `Logs` and `Traces` tables).

| Topic | Decision |
|---|---|
| Use | A scheduled digest: new and recurring error groups appear in the morning brief for triage. Alerts (C) and ad-hoc queries (D) come later and reuse the groups and state built here. |
| Sources | Sentry first: its issues already carry grouping, first/last seen, counts, regression state and a culprit. ADX supplements it with error logs and failed server spans, and covers environments Sentry cannot separate. |
| Signals | Sentry: unresolved issues of level error or fatal. ADX: logs with `SeverityNumber >= 17` (Error and above) and server spans with `STATUS_CODE_ERROR` or HTTP status 500 and above. Warnings are out of scope. |
| Cadence | Hourly timer, plus one fetch in `brief_prep.sh` before the brief. |
| Data policy | **Identifiers kept, credentials masked** (revised 2026-10-07; "aggregates only" is dropped for every source and environment). Notes hold group keys, counts, times, opaque IDs, links and one `message`: the Sentry issue `title`, or one sample `Body` per ADX log group, ticket identifiers (GUIDs, application IDs) included. Free text passes through `redact_credentials` (named token patterns, bearer tokens, URL passwords, connection-string keys, JSON secret fields, `password=`-style assignments) and emails become `<email>`; nothing else is masked. Group keys keep their shape (`<guid>`, `<n>`, `<hex>`, query strings dropped) so one group covers many tickets. State and the run log hold no free text. |
| Execution | Deterministic scripts with no model and no headless `claude` run. Network access stays out of the headless sandbox (security model unchanged). |
| Generality | Everything is generic to any registered codebase. Sources are configured per user in gitignored files; this repository ships only an example. |

Rejected: a headless `claude` run with a Kusto MCP server (needs network inside the sandbox, costs tokens every hour, non-deterministic grouping); Sentry through the claude.ai connector (about $0.20 a fetch, as the calendar, so about $5 a day hourly); ADX only (rebuilds the grouping Sentry already does and loses the culprit); Sentry only (blind to failures the SDK never captures); Azure Monitor scheduled-query rules (Azure-side infrastructure; reconsidered for C).

## 2. Sources

### 2.1 `telemetry_source` notes

One file per source in `system/telemetry/<name>.md`, gitignored except `system/telemetry/example.md`, with a new schema note `system/schemas/telemetry_source.md`:

| Field | Kind | Meaning |
|---|---|---|
| `type` | const `telemetry_source` | |
| `name` | string, required, unique | file name without `.md`; letters, digits, `.`, `_`, `-` |
| `codebase` | string, required | a registered codebase's `name` |
| `environment` | string, required | label shown in notes and the brief, e.g. `prod`, `uat` |
| `kind` | enum `sentry`, `adx`, required | |
| `enabled` | bool, default `"true"` | |
| `rank` | int, default `"50"` | brief order across environments (lower first) |
| `sentry_url` | string | `kind: sentry`: API base, e.g. `https://us.sentry.io` |
| `sentry_org` | string | `kind: sentry` |
| `sentry_projects` | list of string | `kind: sentry`: project slugs |
| `sentry_query` | string, default `is:unresolved level:[error,fatal]` | `kind: sentry`: extra issue search filter |
| `adx_cluster` | string | `kind: adx`: `https://<cluster>.<region>.kusto.windows.net` |
| `adx_database` | string | `kind: adx` |
| `adx_filter` | map of string | `kind: adx`: resource-attribute equality filters ANDed into both queries, e.g. `deployment.instance: "uat-1"`; empty for a whole database |
| `adx_group_keys` | list of string, default empty | `kind: adx`: extra `LogsAttributes` names to group error logs by (e.g. a module or component attribute) |
| `adx_signals` | list of enum `logs`, `spans`, default both | `kind: adx` |
| `covers` | string | `kind: adx`: the `name` of a Sentry source for the same environment. When set, an ADX group whose sample trace belongs to an issue of that source is marked covered (§3.4). |

The linter validates the cross-field rules: the fields of the other kind are absent, `codebase` exists, `covers` names an enabled `kind: sentry` source with the same `environment`. Separate files are used because the codebase schema holds only scalar maps, and a source's lifecycle (enable, disable) is independent of its codebase.

### 2.2 Credentials

- **ADX:** `az account get-access-token --resource <adx_cluster>`; the Azure CLI's own login. No secret is stored by the vault. Missing `az` or an expired login disables ADX sources (§5).
- **Sentry:** a read-only token (internal integration or personal token with `event:read`, `project:read`, `org:read`) in `${XDG_CONFIG_HOME:-~/.config}/foundry/sentry.token`, mode 0600 (the script refuses a group- or world-readable file). It lives outside the vault so neither git nor a sync can carry it. `/setup` asks for it and writes the file.

### 2.3 Setup

A new `/setup` phase 6a, **Telemetry** (skipped on a client), after the calendar:

1. Show existing `system/telemetry/*.md` (except `example.md`) and ask whether to edit any.
2. For each registered codebase, ask whether it reports to Sentry and/or ADX. For Sentry: org, region URL, projects per environment; for ADX: cluster, database and the filter that separates each environment.
3. Write each source, validate it, and run `system/scripts/telemetry_fetch.py --check <name>` (§3.6) to prove access. A failed check leaves the source written with `enabled: "false"` and states what is missing.

## 3. Components and data flow

| Unit | Purpose | Depends on |
|---|---|---|
| `system/scripts/kusto_query.py` | `query(cluster, db, kql, timeout, max_rows) → rows`: token from `az`, POST to `/v2/rest/query`, parse the primary result. Refuses KQL whose first non-blank character is `.` (management commands) and sets the request property `request_readonly`. | `az`, stdlib `urllib` |
| `system/scripts/sentry_api.py` | `issues(source, since) → list`: GET `/api/0/organizations/<org>/issues/` with the project IDs (resolved once from `sentry_projects` slugs and cached in state), `sentry_query` and `lastSeen:>=<since>`, following the `Link` cursor up to 5 pages of 100. `event_for_trace(source, trace_id) → issue id or None`: one Discover call. | stdlib `urllib`, the token file |
| `system/scripts/telemetry_fetch.py` | One run over every enabled source: fetch, group, update state, write notes, log. | the two clients, `vaultlib` |
| `system/logs/telemetry_state.json` | Per source: `checkpoint`, consecutive `failures`, `last_alerted`. Per group: `fingerprint`, `note`, `first_seen`, `last_seen`, `count`. | |
| `raw/telemetry/<source>-<fingerprint>.md` | One `production_error` note per group (§4). | extended schema |
| `system/logs/telemetry-<YYYY-MM>.jsonl` | One line per run and source (§5.2). | |
| `foundry-telemetry.service` / `.timer` | Hourly (`OnBootSec=5min`, `OnUnitActiveSec=1h`) on standalone and server; nothing on a client. On a server, the sync drop-in is **not** applied: the notes are gitignored and nothing to sync is produced. | `install_units.sh` |

### 3.1 Window

For each source the run covers `[checkpoint, now - lag)`, where `lag` is 10 minutes for ADX (ingestion delay) and 2 minutes for Sentry. The first run uses `now - 24h` as the checkpoint; a window is never longer than 7 days (an older checkpoint is moved up and the gap is logged). The checkpoint advances to the window's end only after every note for that source is written.

Ceiling: an ADX row ingested more than 10 minutes after its timestamp, once its window has closed, is missed. Overlapping windows plus deduplication by trace ID would close this if it matters.

### 3.2 Sentry

Each issue returned for the window is one group. Fingerprint: `s-<issue id>`. Kept per group: issue `id`, `shortId`, `permalink`, `project` slug, `level`, `status` and `substatus` (`new`, `regressed`, `escalating`, `ongoing`), `firstSeen`, `lastSeen`, `count`, `userCount`, `metadata.type` (the exception type, without its value), `culprit` (code location), and the event's `environment` tag (which some codebases use for the service name). `title` is kept and written as the note's `message` (masked as in §1, folded to one line, at most 500 characters); `metadata.value` and every tag value except `environment` are dropped at parse time. `culprit` is kept but passed through `redact.py` and cut at the first `?` (URLs).

### 3.3 ADX

Two fixed queries, each with `adx_filter` applied to `ResourceAttributes` and aggregation in ADX, so only group keys, aggregates and one sample message per log group leave the cluster. `<keys>` are the columns the grouping uses; at most 500 groups per query, with a second query for the total group count when the cap is reached.

- **Logs:** `Logs | where Timestamp >= start and Timestamp < end and SeverityNumber >= 17` grouped by `service = ResourceAttributes["service.name"]`, `scope = LogsAttributes["scope.name"]`, `event_id = LogsAttributes["logrecord.event.id"]`, and each attribute in the source's `adx_group_keys`. It also returns `message = take_any(body)` (`body = tostring(Body)`), outside the grouping.
- **Spans:** `Traces | where StartTime >= start and StartTime < end and SpanKind == "SPAN_KIND_SERVER" and (SpanStatus == "STATUS_CODE_ERROR" or toint(TraceAttributes["http.response.status_code"]) >= 500)` grouped by `service`, `route = coalesce(TraceAttributes["http.route"], SpanName)` and `status = TraceAttributes["http.response.status_code"]`.

Each returns `count()`, `min` and `max` of the time column, `dcount(TraceID)` and `sample_trace = take_any(TraceID)`. Fingerprint: `a-` plus the first 12 hex digits of SHA-1 over `source|signal|key=value|…` in a fixed key order. The fingerprint hashes the keys as notes show them (`sanitize`: credentials and emails masked, IDs collapsed to their shape). Since 2026-10-07 key cleaning skips the generic high-entropy guess, which had merged long GUID-bearing routes and long type names into one `[REDACTED:high_entropy]` group; those groups split into their real errors, and their old notes stop updating and resolve after 7 quiet days. Every other fingerprint is unchanged.

### 3.4 Coverage

For a **new** ADX group from a source with `covers`, the run asks Sentry once whether the sample trace has an event (`event_for_trace`). If it does, the note records `sentry_issue: <shortId>` and `covered: "true"`; the brief folds covered groups into their Sentry issue instead of listing them twice. At most 20 lookups per run; groups beyond that stay uncovered and are retried next run. Plan task 1 verifies that Sentry events carry the OpenTelemetry trace ID for the first configured codebase; if they do not, `covers` is accepted but logs `coverage: unavailable` and the brief groups both kinds under the same service instead.

### 3.5 Notes and lifecycle

- A new fingerprint creates `raw/telemetry/<source>-<fingerprint>.md` from `system/templates/production-error.md`.
- A known fingerprint updates `count`, `last_seen`, `status` and, for Sentry, `substatus`, in place. The body is rewritten from the template; nothing else is in it.
- A group not seen for 7 days gets `status: resolved`. A Sentry issue that Sentry reports resolved gets `status: resolved` on the next run. A resolved group that is seen again returns to `active` with `regressed: "true"`.
- Notes are never deleted (vault lifecycle rule). `raw/` is gitignored and `raw/telemetry/` is never ingested, so notes stay on the machine that fetched them.

### 3.6 Command line

```
telemetry_fetch.py                 # every enabled source
telemetry_fetch.py --source <name> # one source
telemetry_fetch.py --check <name>  # access check only: one tiny query; nothing written
telemetry_fetch.py --dry-run       # fetch and print the groups; no notes, no state change
```

Exit codes: 0 every source succeeded; 1 at least one source failed (others still ran); 2 usage; 4 another run holds the lock.

## 4. `production_error` schema

The existing fields keep their meaning; the new fields are optional so existing notes and `mock` notes stay valid.

| Field | Value from Sentry | Value from ADX |
|---|---|---|
| `service` | the `environment` tag, else the project slug | `service.name` |
| `exception` | `metadata.type` | logs: `<scope>#<event_id>`; spans: `<route> <status>` |
| new `message` | issue `title` | logs: one sample `Body`; spans: absent |
| `operation_id` | the latest event's trace ID when present, else the issue ID | the sample trace ID |
| `detected_at` | `firstSeen` | first `min(time)` |
| `codebase`, `partition` | from the source's codebase | same |
| new `environment` | the source's `environment` | same |
| new `source` | the source's `name` | same |
| new `kind` | `sentry` | `log` or `span` |
| new `fingerprint` | `s-<issue id>` | `a-<12 hex>` |
| new `count` | issue `count` | running total across windows |
| new `last_seen` | `lastSeen` | latest `max(time)` |
| new `status` | `active`, `resolved` | same |
| new `resolved_at` | when the run set `resolved` | same |
| new `substatus` | Sentry's substatus | absent |
| new `regressed` | bool | bool |
| new `sentry_issue` | the `shortId` | when covered (§3.4) |
| new `covered` | absent | bool |
| new `culprit` | redacted culprit | absent |
| new `link` | `permalink` | absent |

Body (template): one table of the group keys and counts, and for ADX a KQL query that reopens the group in the cluster for the note's time range by its keys, so investigation reads the raw data in ADX and not in the vault.

## 5. Failure handling

### 5.1 Behavior

| Failure | Behavior |
|---|---|
| `az` missing, or not logged in | ADX sources are skipped. Alert `telemetry: <source>: run az login` (once a day per source). |
| Sentry token file missing, unreadable or too permissive; HTTP 401 or 403 | Sentry sources skipped; alert once a day naming the file and the fix. |
| HTTP 429, 5xx, timeout (60 s per request) | The source's checkpoint stays; the next run retries the window. After 3 consecutive failed runs: alert once a day. |
| More groups than the cap | Notes for the returned groups are written; the jsonl line and an alert record `truncated: <total>`. |
| One source fails | The others still run; exit 1. |
| Timer and `brief_prep.sh` overlap | `flock` on `system/telemetry.lock`, waiting up to 120 s, then exit 4. `brief_prep.sh` reports exit 4 as "telemetry: a fetch was already running". |
| Corrupt state file | Moved to `system/quarantine/`; state is rebuilt from the frontmatter of the existing notes (checkpoints restart at `now - 24h`; existing fingerprints are matched, so no duplicate notes). |

Alerts go to `system/logs/alerts_<date>.md` with the `[telemetry]` tag, through the same once-a-day pattern `vault_sync.sh` uses.

### 5.2 Run log

One jsonl line per source and run: `started_at`, `source`, `window` (`from`, `to`), `new`, `updated`, `resolved`, `covered`, `truncated`, `exit`, `error` (a short reason, no response bodies). `/debrief` adds telemetry to System State Deltas from these lines.

## 6. Brief, debrief and the Workcell

- **`brief_prep.sh`** runs `telemetry_fetch.py` after the calendar. A failure adds an Unavailable Sources line by exit code, as the calendar does; it never fails the prep.
- **`/brief`**, Friction Matrix → Systemic Blockers: telemetry from `raw/telemetry/` in source `rank` order, active groups only:
  1. **New**: `detected_at` in the last 24 hours, and Sentry groups with `substatus: regressed` or `escalating`.
  2. **Recurring**: other groups with `last_seen` in the last 24 hours, with their count.
  3. One line: the number of groups with `resolved_at` in the last 24 hours.

  At most 10 rows per environment, then "and N more". Covered ADX groups are not listed; their Sentry issue is. Each row names the environment, service, exception, count, and the Sentry short ID or note path.
- **`/debrief`**: per source, the day's run totals and any failure.
- **The Workcell with `telemetry`** (unchanged routing): for each note it looks for correlating commits in local branches of `codebase`. New: it starts from `culprit` for Sentry groups, and for ADX log groups it looks up `event_id` in the codebase's log-event map entity note when one exists (the `/setup` onboarding assignment produces it).
- **Mock notes:** `mock: "true"` notes are skipped by the fetch and still shown by the brief, as before.

## 7. Dependencies and roles

- `check_deps.sh`: `az` is **optional** on standalone and server (install hint per distribution); without it, ADX sources stay off. No new required dependency.
- `install_units.sh`: `foundry-telemetry.service` and `.timer` for standalone and server, enabled only when at least one enabled source exists; nothing on a client. A role change removes them as other units are removed.
- `.gitignore`: `system/telemetry/*.md` except `example.md`, `system/telemetry.lock`. `system/logs/*` already covers the state and the run log.

## 8. Testing

Gating suites, following the existing patterns:

- **pytest** (`system/tests/python/`): fingerprint stability and key order; KQL building with and without `adx_filter` and `adx_group_keys`; the read-only guard; window math (first run, 7-day cap, failure keeps the checkpoint); Sentry pagination; note create, update, resolve and regress; state rebuild from notes; coverage lookups and the 20-lookup cap. A **privacy test** feeds Sentry issues and ADX rows whose fields hold credentials (an AWS key, bearer tokens, `password=`, SQL and Azure Storage connection strings, a URL password, a SAS `sig=`, a JSON `"password"` field), plain and URL-encoded emails, a ticket GUID and an application ID, and asserts that no credential or email appears in any note, the state file, the run log or the dry-run output, and that the GUID, the application ID and the title text do appear in the notes.
- **bats** (`system/tests/telemetry.bats`): `telemetry_fetch.py` end to end with a stub `az` and canned HTTP responses (`FOUNDRY_TELEMETRY_STUB` points the two clients at a directory of fixture files); lock contention (exit 4); auth failure alerts once a day; a token file with mode 0644 is refused; `--check` and `--dry-run` write nothing.
- **Existing suites extended:** `units.bats` (units by role, enabled only with a source), `setup.bats` (`az` optional), `vault_integrity.bats` and the schema-note tests (the new schema and fields), `prep.bats` (brief prep exit-code lines), `commands.bats` (brief and debrief mention telemetry).
- **Live acceptance** (`docs/superpowers/spikes/2026-10-xx-plan-11-acceptance.md`): one run against every source configured on the real server; a scripted scan of `raw/telemetry/` and the state file for credentials and emails; then `/brief` renders the telemetry rows.

## 9. Out of scope

- Alerts (C): reuse `telemetry_state.json` and the run log; Sentry alert rules are likely the main channel.
- On-demand queries (D): a `/logs` command over the same clients, read-only, interactive only.
- Warnings, metrics, and frontend performance data.
- Separating environments that the source data cannot separate (for example, shared services that serve several environments). A source covers only what its filter selects.
