# Telemetry escalation: persistent groups

**Date:** 2026-10-15 (revised the same day: dependency status held, §9)
**Status:** Accepted by the owner (PR #186); the dependency half is held (owner, 2026-10-15).
**Issue:** #171, ask 2 (the persistent rule). Ask 1 (dependency status) and the partner auth rule are held (§9). Asks 3 and 4, the logs-signal join and the Sentry side are deferred (§6).
**Extends:** `2026-10-05-error-monitoring-design.md` (the fetch, the notes, the brief's telemetry rules); `2026-10-09-now-page-design.md` (Now lines); `2026-10-14-alert-tags-design.md` (`telemetry` alerts are `brief` severity, owner 2026-10-15).

## 1. Problem

From 2026-10-05 to 2026-10-14 a partner's API returned 401 to every call from one non-prod environment. The fetch wrote three groups on day 1: a log group (sample message "credential service call failed"), a span group for the same route with status 500, and a log group from the partner's client ("unexpected error"). Five briefs listed them under New and Recurring as counts climbed from 11 to 54. On day 8 the brief's objectives added a "route these groups" line that sat for three days. On day 10 a developer read the logs and found the 401.

What the sources show:

- **The note cannot show the cause.** A span group's note holds service, route, status and counts, and no message. A log group's note holds one masked sample `Body` (since 2026-10-07). Neither holds the outbound call that failed: the fetch reads only server spans (`SpanKind == "SPAN_KIND_SERVER"`) and error logs, and the owner's telemetry records no outbound calls at all (§9).
- **Nothing escalates.** `brief.md` applies the same New, Recurring and Resolved lines to every environment. No rule turns a group into a Now line; the "route" line was an objective the brief's model wrote. The template has no prod-only decision rule either: "same as prod" in the issue describes how the owner's Foreman behaved.

## 2. Decisions

- **The fetch classifies, the brief prints.** The rule runs in `telemetry_store.py` (deterministic, no model, as the error-monitoring spec decided) and writes one field the brief reads. The brief only filters by time and applies the cap.
- **Every environment, ADX groups only.** The rule ignores `environment`, so no prod flag is needed. It skips Sentry groups: their `detected_at` is the issue's lifetime `firstSeen` and their `count` a lifetime total, so every ongoing issue would escalate and outrank the ADX groups; Sentry's own `substatus` (`escalating`, `regressed`) already puts them under New.
- **One path to Now.** Escalated groups become `owed` lines through the brief's existing **Add to Now** step (`now.py add` interactive, the staged edit headless).
- **No new alert.** `telemetry` alerts stay `brief` severity.

## 3. Design

### 3.1 Note fields (`production_error`, both optional)

| Field | Kind | Written by | Read by |
|---|---|---|---|
| `escalate` | enum `persistent` | fetch (§3.2) | brief |
| `escalated_at` | datetime | fetch: the first time `escalate` was set; never changed after | brief |

`NOTE_FIELDS` gains both names (it is a whitelist; anything else is dropped). The new schema fields become `v_production_error` columns with no index change.

### 3.2 The escalation rule (`Store.upsert`)

On every write of an active `log` or `span` group (never `sentry`), `escalate` is `persistent` when `last_seen` is at least 24 hours after `detected_at`: the group has been seen over at least 24 hours. A write happens only when the fetch saw the group, so it is still firing ("growing" in the issue). Otherwise it has no `escalate`. A calendar-day test was dropped in review (#171): the fetch runs hourly, so a group seen at 23:30 and again at 00:30 UTC escalated after one hour.

`escalated_at` is set the first time the rule holds and never changes after. A resolved group keeps both fields; it reappears through `regressed` as today.

### 3.3 The brief (`.claude/commands/brief.md`)

- The telemetry `SELECT` adds `partition, escalate, escalated_at`.
- **Escalated**, a new first part of the Telemetry blocker, across all environments: active groups with `escalate` set and `last_seen` in the last 24 hours, by `count`. At most 3 rows, then "and N more". Row: `persistent`, environment, service, `exception` (the route and status, or the scope and event id), `count` and the note path. A printed Escalated row is not repeated under New or Recurring; escalated groups past the cap stay under New or Recurring as today. Covered groups are skipped, as today.
- **Add to Now**, one more bullet: each Escalated row whose `escalated_at` is in the last 24 hours, at most 3 per brief, becomes an `owed` line on the Now page of its note's `partition` (`default_partition` for `shared`). Statement: `Telemetry <environment>: persistent, <service> on <exception>; decide an owner (proposed: read-only analysis by the Workcell with telemetry)`. It names the group (service and route, or scope and event id) and nothing that changes between runs. Evidence: the note path, a label the evidence check ignores (`evidence_state` returns None for it), so the owner ticks the line. The statement holds no count or date, so `now.py add` and the headless "none repeating an open line" rule keep one line per group; `escalated_at` keeps a ticked line from coming back. A group past the cap on its first day stays in the Escalated block while it fires and gets no Now line (the cap's ceiling; a per-group "line added" mark in the state file would lift it).

### 3.4 Documents

- `FOUNDRY.md`: the Error telemetry paragraph gains the persistent rule; the Brief inputs telemetry clause and the `/brief` row gain the Escalated block and its Now lines.
- `CLAUDE.md`'s Now rule lists a telemetry note path as a fourth evidence form.

## 4. Out of scope

- A prod flag, per-environment thresholds or a daily-rate test for "growing".
- Closing the Now line when the group resolves; the owner ticks it.

## 5. Tests

- **pytest `test_telemetry_store.py`:** a Sentry group seen over three days never escalates while a log group does; `persistent` at 24 hours, not at 1 or 23 hours across midnight, for log and span groups; `escalated_at` set once and kept through a later write and a resolve.
- **pytest `test_telemetry_run.py`:** an ADX source sends one query per signal and nothing else.
- **Schema tests:** `escalate` and `escalated_at` validate; another `escalate` value is an error.
- **bats `telemetry.bats`:** a stubbed `environment: uat` span group seen over 24 hours gets `escalate: "persistent"`, an `escalated_at` and no `message`.
- **bats `commands.bats`:** `brief.md` carries the Escalated rule, the cap of 3 and the Add to Now bullet; `FOUNDRY.md` and `CLAUDE.md` carry the §3.4 sentences; no template file outside this spec and its plan names the held fields (§9).
- **Live acceptance:** one brief on the owner's server showing the Escalated block.

Bound tools: pytest, bats and the gate.

## 6. Deferred (checklist lines on #171)

- **Ask 3, re-check dates on "background" calls.** Neither `rca.md` nor its schema records a noise or background verdict, so there is no field to date. The rule in §3.2 escalates such a group anyway after 24 hours. Revisit if a group is escalated, dismissed and missed again.
- **Ask 4, route lines start the Workcell.** `telemetry` belongs to the maintenance Workcell (`maintenance.md`), so #168 (the research Workcell) is not the dependency. The headless brief cannot start a Workcell or queue a Work Order, so an automatic start needs an unattended path that does not exist. In a session, the Foreman's "No approval bottleneck" rule already lets it run the read-only analysis the Now line proposes.
- **Sentry:** breadcrumb status lives on events, not the issues list the fetch reads; it needs one event fetch per new issue under a budget like the coverage lookups.
- **A named owner** for the `who` slot (a per-source field), if the capability proposal is not enough.

## 7. Rollout

Template update only. The new fields are optional, so existing notes stay valid; there is no backfill. The first fetches after the update escalate every group they see that has been seen over at least 24 hours, so the first brief adds at most 3 Now lines; the others stay in the Escalated block ("and N more") while they fire and get no Now line, because their `escalated_at` passes the 24-hour window.

## 8. Owner decisions (accepted with PR #186)

1. **Threshold:** seen over at least 24 hours and still firing (changed from two UTC days in review).
2. **"Growing":** still firing, without per-day counts.
3. **Cap:** 3 Escalated rows and 3 new Now lines per brief, across environments.
4. **Scope:** every environment; Sentry groups stay out of the rule (§2).
5. **Proposed owner:** the Workcell with `telemetry` in the statement; the person field is deferred.
6. **Asks 3 and 4 and the Sentry side deferred** as in §6.
7. **Dependency status held** (2026-10-15), §9.

## 9. Dependency status: held

The owner's telemetry records no outbound calls. On the owner's non-prod database over one day: there are no `SPAN_KIND_CLIENT` rows; `server.address` and `http.response.status_code` exist only on server spans (the service's own address); no span carries `url.full`, `http.url`, `peer.service` or `rpc.system`; and the incident's log records carry no status-code attribute. A client-span join returns nothing on this data, so the dependency fields and the `partner-auth` rule (a 401 or 403 from a listed partner host escalates on day 1) wait until the codebase emits client spans (OpenTelemetry HTTP client instrumentation). The code built for them on the branch was removed before merge.

When client spans exist, this is the starting point:

- **Query** (`kql_deps`, once per ADX source with `spans`): the client spans of the failing traces, by span group, host and status code. Select host and status code only: no `url.full`, path, query string or body. Narrow the client spans to the failing `TraceID`s before reading attributes, and treat a failure of this query (a server timeout) as "no dependency data" so the source still succeeds.

  ```kql
  let failing = materialize(<the kql_spans where, filter and extend lines>
  | distinct TraceID, service, route, status);
  Traces
  | where StartTime >= <start> and StartTime < <end> and SpanKind == "SPAN_KIND_CLIENT"
  <adx_filter lines>
  | where TraceID in (failing | project TraceID)
  | extend host = tostring(TraceAttributes["server.address"]), code = toint(TraceAttributes["http.response.status_code"])
  | where isnotempty(host) and isnotnull(code)
  | project TraceID, host, code
  | join kind=inner failing on TraceID
  | summarize n = count() by service, route, status, host, code
  | order by n desc
  | take 2000
  ```

  Each row maps to its group by the existing fingerprint (`fingerprint(src.name, "span", {service, route, status})` over sanitized keys). Check the attribute names first with a count by `SpanKind` of rows carrying `server.address`, `net.peer.name`, `http.response.status_code` and `http.status_code`; take `coalesce` of the stable and older names if the older ones appear.
- **Host aliases:** `adx_hosts`, a per-source map (host to alias) in the gitignored `system/telemetry/<name>.md`, an ADX-only field the linter rejects on a Sentry source. A listed host is an external partner and prints as its alias. Before the lookup and before printing, a host is lowercased and loses any scheme, user info (everything before the last `@` of the authority), port, path, query and fragment; an unlisted IP literal prints as `ip`, never the address; any other host prints sanitized.
- **Note fields:** `dep_host` (a listed host that answered 401 or 403, else the host with the most 4xx/5xx calls) and `dep_codes` (that host's codes by count, at most 5, e.g. `401: 41, 504: 3, 200: 10`), with running totals per group in the state file (at most 5 hosts, listed hosts kept first).
- **Rule:** `partner-auth` before `persistent`; an upgrade from `persistent` to `partner-auth` sets `escalated_at` again so it gets its own Now line. The Now statement still names the group, never `dep_host`.
- **Privacy test:** a client span whose `url.full` holds a query-string token: no token, path or query string in the note, the state file, the run log or the dry-run output.
- **Logs signal:** the same join keyed by the log group keys.
