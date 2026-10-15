# Telemetry escalation: dependency status and persistent groups

**Date:** 2026-10-15
**Status:** Draft for the owner's review.
**Issue:** #171, asks 1 and 2. Asks 3 and 4, the logs-signal join and the Sentry side are deferred (§6).
**Extends:** `2026-10-05-error-monitoring-design.md` (the fetch, the notes, the brief's telemetry rules); `2026-10-09-now-page-design.md` (Now lines); `2026-10-14-alert-tags-design.md` (`telemetry` alerts are `brief` severity, owner 2026-10-15).

## 1. Problem

From 2026-10-05 to 2026-10-14 a partner's API returned 401 to every call from one non-prod environment. The fetch wrote three groups on day 1: a log group (sample message "credential service call failed"), a span group for the same route with status 500, and a log group from the partner's client ("unexpected error"). Five briefs listed them under New and Recurring as counts climbed from 11 to 54. On day 8 the brief's objectives added a "route these groups" line that sat for three days. On day 10 a developer read the logs and found the 401.

What the sources show:

- **The note cannot show the cause.** A span group's note holds service, route, status and counts, and no message. A log group's note holds one masked sample `Body` (since 2026-10-07; `maintenance.md` still says notes hold no message text, which is stale). Neither holds the outbound call that failed: the fetch reads only server spans (`SpanKind == "SPAN_KIND_SERVER"`) and error logs.
- **Nothing escalates.** `brief.md` applies the same New, Recurring and Resolved lines to every environment. No rule turns a group into a Now line; the "route" line was an objective the brief's model wrote. The template has no prod-only decision rule either: "same as prod" in the issue describes how the owner's Foreman behaved.

## 2. Decisions

- **The fetch classifies, the brief prints.** The rule runs in `telemetry_store.py` (deterministic, no model, as the error-monitoring spec decided) and writes one field the brief reads. The brief only filters by time and applies the cap.
- **ADX spans only.** The dependency join runs for span groups. The incident's span group carried the route; it alone would have escalated on day 1.
- **Every environment, ADX groups only.** The rule ignores `environment`, so no prod flag is needed. It skips Sentry groups: their `detected_at` is the issue's lifetime `firstSeen` and their `count` a lifetime total, so every ongoing issue would escalate and outrank the ADX groups; Sentry's own `substatus` (`escalating`, `regressed`) already puts them under New.
- **One path to Now.** Escalated groups become `owed` lines through the brief's existing **Add to Now** step (`now.py add` interactive, the staged edit headless).
- **No new alert.** `telemetry` alerts stay `brief` severity; a day-1 partner auth failure reaches the owner at the next brief.

## 3. Design

### 3.1 The dependency query (`vaultlib/telemetry.py`, new `kql_deps`)

Confirmed against the existing KQL: table `Traces`; columns `TraceID`, `SpanKind`, `SpanName`, `SpanStatus`, `StartTime`, `ResourceAttributes`, `TraceAttributes`; the attributes `service.name`, `http.route`, `http.response.status_code`; the `SPAN_KIND_SERVER` literal. The issue's "dependencies table joined on operation id" is Application Insights wording; these databases hold OpenTelemetry tables, where an outbound call is a client span sharing the server span's `TraceID`.

```kql
let deps = Traces
| where StartTime >= <start> and StartTime < <end> and SpanKind == "SPAN_KIND_CLIENT"
<adx_filter lines>
| extend host = tostring(TraceAttributes["server.address"]), code = toint(TraceAttributes["http.response.status_code"])
| where isnotempty(host) and isnotnull(code)
| project TraceID, host, code;
<the kql_spans where, filter and extend lines, unchanged>
| distinct TraceID, service, route, status
| join kind=inner deps on TraceID
| summarize n = count() by service, route, status, host, code
| order by n desc
| take 2000
```

It selects host and status code only: no `url.full`, no path, no query string, no body. It runs once per ADX source per fetch when `spans` is in `adx_signals`. Each row maps to its group by the existing fingerprint (`fingerprint(src.name, "span", {service, route, status})` over sanitized keys). Rows past 2000 are dropped (ordered by count, so the smallest go first).

**Assumptions, not confirmable from the code:** outbound HTTP calls are exported as `SPAN_KIND_CLIENT` rows in the same `Traces` table, and they carry `server.address` and `http.response.status_code` (the stable semantic conventions the server query already relies on). Plan task 1 checks both against the live cluster with `--dry-run`, as Plan 11 task 1 checked trace coverage. If the codebase emits the older `net.peer.name` and `http.status_code`, the query takes `coalesce` of both names.

### 3.2 Host aliases (`telemetry_source`, new field)

| Field | Kind | Set by | Read by |
|---|---|---|---|
| `adx_hosts` | map of string (host → alias) | the owner, in the gitignored `system/telemetry/<name>.md` | the fetch |

A host in the map is an external partner: the note shows its alias and it can raise a partner auth failure. Any other host prints as `sanitize(host)` (note: `sanitize` collapses 4+ digits, so `api1234.example.com` prints `api<n>.example.com`) and never counts as external. The template ships only `example.md`, with `adx_hosts: {"api.example.com": "partner-a"}`. Per source because a non-prod environment usually calls a partner's sandbox host. `adx_hosts` joins `ADX_FIELDS` in `index.py` so the linter rejects it on a Sentry source. `/setup` phase 6a gets one sentence pointing at the field; no new question.

### 3.3 Note fields (`production_error`, all optional)

| Field | Kind | Written by | Read by |
|---|---|---|---|
| `dep_host` | string | fetch: the alias or sanitized host with the most 4xx/5xx calls (ties by name) | brief, the Workcell with `telemetry` |
| `dep_codes` | string, e.g. `401: 41, 504: 3, 200: 10` | fetch: that host's codes, by count, at most 5 | brief, Workcell |
| `escalate` | enum `partner-auth`, `persistent` | fetch (§3.4) | brief |
| `escalated_at` | datetime | fetch: the first time `escalate` was set; never changed after | brief |

`_clean` passes `dep_host` through `sanitize` whether it is an alias or a host, so `example.md` tells the owner to keep aliases free of 4+ digit runs. `NOTE_FIELDS` gains the four names (it is a whitelist; anything else is dropped). The state file keeps running totals per group as `deps: {host: {code: n}}`, merged across windows like `count`, at most 5 hosts. A rebuild from notes restores the top host's totals from `dep_codes` and loses the others. The new schema fields become `v_production_error` columns with no index change.

### 3.4 The escalation rule (`Store.upsert`)

On every write of an active `log` or `span` group (never `sentry`):

1. `partner-auth` (span groups) when any host in the group's `deps` totals is listed in `adx_hosts` and has a 401 or 403. `dep_host` then names that host, even when an unlisted host has more failed calls. Day 1: the first fetch that sees it.
2. Else `persistent` when the UTC date of `last_seen` is later than the UTC date of `detected_at`: the group fired on two or more days. A write happens only when the fetch saw the group, so it is still firing ("growing" in the issue).
3. Else no `escalate`.

`escalated_at` is set the first time 1 or 2 holds. A resolved group keeps both fields; it reappears through `regressed` as today.

### 3.5 The brief (`.claude/commands/brief.md`)

- The telemetry `SELECT` adds `partition, dep_host, dep_codes, escalate, escalated_at`.
- **Escalated**, a new first part of the Telemetry blocker, across all environments: active groups with `escalate` set and `last_seen` in the last 24 hours, `partner-auth` first, then by `count`. At most 3 rows, then "and N more". Row: `partner auth failure` or `persistent`, environment, `dep_host` and `dep_codes` when present, the route and status (`exception`), and the note path. A printed Escalated row is not repeated under New or Recurring; escalated groups past the cap stay under New or Recurring as today. Covered groups are skipped, as today.
- **Add to Now**, one more bullet: each Escalated row whose `escalated_at` is in the last 24 hours, at most 3 per brief, becomes an `owed` line on the Now page of its note's `partition` (`default_partition` for `shared`). Statement: `Telemetry <environment>: <label>, <dep_host or service> on <exception>; decide an owner (proposed: read-only analysis by the Workcell with telemetry)`. Evidence: the note path, a label the evidence check ignores (`evidence_state` returns None for it), so the owner ticks the line. The statement holds no count or date, so `now.py add` and the headless "none repeating an open line" rule keep one line per group; `escalated_at` keeps a ticked line from coming back. A group past the cap on its first day stays in the Escalated block while it fires and gets no Now line (the cap's ceiling; a per-group "line added" mark in the state file would lift it).

### 3.6 Documents

- `maintenance.md` line 10 (stale): notes hold at most one masked message (a Sentry title or a sample log body; span groups none) and, for span groups, the dependency host and status codes.
- `FOUNDRY.md`: the Error telemetry paragraph gains `adx_hosts` and the dependency fields; the Brief inputs telemetry clause and the `/brief` row gain the Escalated block and its Now lines; the Security paragraph says only host and status code of a dependency call leave the cluster.
- `CLAUDE.md`'s Now rule lists a telemetry note path as a fourth evidence form.

## 4. Out of scope

- Message text, URLs, paths or tokens of dependency calls. Only host and status code leave the cluster.
- A prod flag, per-environment thresholds or a daily-rate test for "growing".
- A `now`-severity alert for partner auth failures.
- Closing the Now line when the group resolves; the owner ticks it.

## 5. Tests the plan must include

- **pytest `test_telemetry_core.py`:** `kql_deps` holds the client-span `let`, `join kind=inner deps on TraceID`, the source's `adx_filter` lines on both sides, and none of `url.full`, `url.path`, `Body`.
- **pytest `test_telemetry_store.py`:** dependency rows land on the span group with the matching fingerprint; an aliased host prints its alias, an unaliased one its sanitized host; totals merge across two runs; `dep_codes` order and the 5-code cut; `partner-auth` on day 1 for a listed host with 401, none for an unlisted host with 401 on day 1; a listed host with one 401 wins `dep_host` over an unlisted host with more 5xx calls; a Sentry group seen on two days never escalates; `persistent` when `last_seen` falls on a later UTC date; `escalated_at` set once and kept; a rebuild restores `dep_host` and `dep_codes`.
- **Privacy test:** a client span whose `url.full` holds a query-string token and whose host is listed: no token, path or query string in the note, the state file, the run log or the dry-run output.
- **Schema tests:** the four fields validate; `adx_hosts` on a Sentry source is a lint error.
- **bats `telemetry.bats`, the issue's acceptance:** a stubbed ADX source with `environment: uat`, a listed host and client spans answering 401; one fetch writes a note with `dep_host: "partner-a"`, `dep_codes` starting `401:`, `escalate: "partner-auth"` and no `message`.
- **bats `commands.bats`:** `brief.md` carries the Escalated rule, the cap of 3 and the Add to Now bullet; `maintenance.md` no longer says notes hold no message text; `FOUNDRY.md` and `CLAUDE.md` carry the §3.6 sentences.
- **Live acceptance:** plan task 1 (§3.1), then one brief on the owner's server showing the Escalated block.

Bound tools: pytest, bats and the gate.

## 6. Deferred (checklist lines on #171)

- **Ask 3, re-check dates on "background" calls.** Neither `rca.md` nor its schema records a noise or background verdict, so there is no field to date. The rule in §3.4 escalates such a group anyway on day 2. Revisit if a group is escalated, dismissed and missed again.
- **Ask 4, route lines start the Workcell.** `telemetry` belongs to the maintenance Workcell (`maintenance.md`), so #168 (the research Workcell) is not the dependency. The headless brief cannot start a Workcell or queue a Work Order, so an automatic start needs an unattended path that does not exist. In a session, the Foreman's "No approval bottleneck" rule already lets it run the read-only analysis the Now line proposes.
- **Logs signal:** join log groups to client spans on `TraceID` (the same query shape keyed by the log group keys).
- **Sentry:** breadcrumb status lives on events, not the issues list the fetch reads; it needs one event fetch per new issue under a budget like the coverage lookups.
- **A named owner** for the `who` slot (a per-source field), if the capability proposal is not enough.

## 7. Rollout

Template update only. The new fields are optional, so existing notes stay valid. The owner adds `adx_hosts` to each ADX source file; until then hosts print sanitized and only `persistent` escalates. Groups gain dependency fields as they fire after the update; there is no backfill. The first fetches after the update escalate every group they see that has fired on two days, so the first brief adds at most 3 Now lines; the others stay in the Escalated block ("and N more") while they fire and get no Now line, because their `escalated_at` passes the 24-hour window.

## 8. Owner decisions

1. **Thresholds:** two UTC days for `persistent`, day 1 for `partner-auth` on a listed host. Recommendation: as written.
2. **"Growing":** still firing (as written), or a daily count above the day before (needs per-day counts in the state file). Recommendation: as written.
3. **Cap:** 3 Escalated rows and 3 new Now lines per brief, across environments. Recommendation: as written; per environment would allow 3 per environment.
4. **Scope:** every environment, or non-prod only (needs a prod flag on the source). Recommendation: every environment. Sentry groups stay out of the rule either way (§2).
5. **Alias home:** `adx_hosts` per source (as written), or one `telemetry_hosts` map in `system/config.md`. Recommendation: per source, because sandbox hosts differ by environment.
6. **Proposed owner:** the Workcell with `telemetry` in the statement (as written), or a per-source person field. Recommendation: as written; the person field is deferred.
7. **Asks 3 and 4 and the Sentry side deferred** as in §6. Recommendation: defer.
