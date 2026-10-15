# Telemetry Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** span groups carry the host and status codes of their failed outbound calls (`dep_host`, `dep_codes`), the fetch marks groups `partner-auth` (day 1, 401/403 from a listed host) or `persistent` (seen over at least 24 hours and still firing), and the brief prints an Escalated block (at most 3 rows) and adds up to 3 `owed` Now lines per brief.

**Architecture:** one new KQL builder (`kql_deps`) beside `kql_spans`, sharing its server-span lines; `_adx_groups` runs it once per ADX source with `spans` and attaches `{host: {code: n}}` to the span group with the same fingerprint; `Store.upsert` merges the totals, writes the four note fields and applies the rule. The brief only filters by time and caps. No new config key outside the spec's `adx_hosts`, no new dependency, no now.py change (a note path is evidence `evidence_state` ignores).

**Tech Stack:** Python (vaultlib), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-15-telemetry-escalation-design.md` (merged in #186). Issue #171; its deferred lines are not built here.

**Amended 2026-10-15 (owner):** dependency status is held (spec §9). Tasks 0, 1, 2 (`adx_hosts`), 4 and the dependency parts of 3 and 5 were built and then removed before merge; what ships is `escalate: persistent` (24 hours seen and still firing), `escalated_at`, the Escalated block and its Now lines.

## Global Constraints

- Work on branch `feat/telemetry-escalation` in worktree `.scratch/escalate`. Commit there; do not push or open a pull request.
- Run suites through `system/scripts/test.sh <suite.bats | pytest path>` outside the sandbox, one at a time. Never run the gate here.
- Bound tools: pytest (`test_telemetry_core.py`, `test_telemetry_store.py`, `test_telemetry_run.py`, `test_telemetry_schema.py`, `test_schema_notes.py`), bats (`telemetry.bats`, `commands.bats`, `vault_integrity.bats`), the gate (main session).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- No message text, URL, path, query string or token from a dependency call is read, stored or printed: the query selects host and status code only, and the fetch reads only `host`, `code` and `n` from each row.
- Tests stub the ADX client (`monkeypatch` on `kusto.query`, `FOUNDRY_TELEMETRY_STUB` in bats); nothing calls the network.
- Template rule: the only host in any file is `api.example.com`.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- The client-span kind and the host and code attribute names are constants in one place (`telemetry.py`); the spec marks them as assumptions until the live check below.
- `kql_spans` output stays byte-identical (existing tests pin it).
- The state file keys dependency hosts by their printed form (alias or sanitized host), so a rebuild from notes restores the top host under the same key and the partner check still matches it.
- A listed host is never trimmed by the 5-host cap.
- `escalated_at` comes from the note first, so it is set once and survives a state rebuild and a resolve.
- `NOTE_FIELDS` carries the four names, so `set_status` and `set_covered` keep them.

---

### Task 0: Live confirmation (main session, owner's server; not run here)

No ADX access in the build session. Run once, read-only, counts only, against a non-prod database:

```kql
Traces
| where StartTime >= ago(1d)
| summarize n = count(), host = countif(isnotempty(tostring(TraceAttributes["server.address"]))), peer = countif(isnotempty(tostring(TraceAttributes["net.peer.name"]))), code = countif(isnotnull(toint(TraceAttributes["http.response.status_code"]))), old_code = countif(isnotnull(toint(TraceAttributes["http.status_code"]))) by SpanKind
```

A `SPAN_KIND_CLIENT` row with `host` and `code` above 0 confirms the constants. If only `peer` or `old_code` is filled, change the constants to `coalesce` both names (spec §3.1). Then `system/scripts/telemetry_fetch.py --dry-run --source <a non-prod ADX source>` prints each span group's `deps`.

### Task 1: `kql_deps` and the stub route

**Files:**
- Modify: `system/scripts/vaultlib/telemetry.py`, `system/scripts/vaultlib/http.py`
- Test: `system/tests/python/test_telemetry_core.py` (after `test_kql_filter_and_group_keys_are_quoted`)

**Interfaces:**
- Produces: `CLIENT_KIND`, `DEP_HOST`, `DEP_CODE` constants; `kql_deps(src, start, end, limit=2000) -> str`; stub route `kusto-deps` for a query starting `let deps`.

- [ ] **Step 1: Write the test** (spec §5): `kql_deps` starts `let deps = Traces`, holds `SpanKind == "SPAN_KIND_CLIENT"`, `TraceAttributes["server.address"]`, `join kind=inner deps on TraceID`, `| distinct TraceID, service, route, status`, `| take 2000`, the source's filter line twice, and none of `url.full`, `url.path`, `Body`. Add `kql_deps` to `test_kql_aliases_avoid_reserved_words`.
- [ ] **Step 2: Run it red.** `system/scripts/test.sh system/tests/python/test_telemetry_core.py`. Expected: AttributeError (no `kql_deps`).
- [ ] **Step 3: Implement.** `_span_lines(src, start, end)` returns the first six `kql_spans` lines; `kql_spans` appends its summarize lines; `kql_deps` prepends the `let` block. `http._route`: `let deps` → `kusto-deps`.
- [ ] **Step 4: Run green**, then `test_telemetry_run.py`.
- [ ] **Step 5: Commit.** `feat(telemetry): kql_deps joins client spans to failing server spans on TraceID`.

### Task 2: `adx_hosts` and the schemas

**Files:**
- Modify: `system/schemas/telemetry_source.md`, `system/schemas/production_error.md`, `system/scripts/vaultlib/index.py` (`ADX_FIELDS`), `system/scripts/vaultlib/telemetry.py` (`Source.adx_hosts`, `load_sources`), `system/telemetry/example.md`
- Test: `system/tests/python/test_telemetry_schema.py`, `test_telemetry_core.py`

**Interfaces:**
- Produces: `Source.adx_hosts: dict` (host → alias); `production_error` fields `dep_host`, `dep_codes`, `escalate` (enum `partner-auth`, `persistent`), `escalated_at` (datetime); `adx_hosts` on a Sentry source is a `telemetry-source` lint error.

- [ ] **Step 1: Write the tests:** a note with the four fields validates; a bad `escalate` value is a schema error; an ADX source with `adx_hosts: {"api.example.com": "partner-a"}` lints clean and `load_sources` reads the map; the same field on a Sentry source is a lint error.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement**, then add the `adx_hosts` example and its sentence to `example.md`.
- [ ] **Step 4: Run green**, plus `test_schema_notes.py` and `vault_integrity.bats`.
- [ ] **Step 5: Commit.** `feat(telemetry): adx_hosts on ADX sources and the dependency and escalation note fields`.

### Task 3: The store: dependency totals and the escalation rule

**Files:**
- Modify: `system/scripts/vaultlib/telemetry_store.py`
- Test: `system/tests/python/test_telemetry_store.py` (after `test_the_stored_reopen_query_keeps_an_empty_filter_value`)

**Interfaces:**
- Consumes: group dict keys `deps` (`{printed host: {code: n}}`) and `listed` (printed aliases).
- Produces: note fields `dep_host`, `dep_codes`, `escalate`, `escalated_at`; state `groups[key]["deps"]`.

- [ ] **Step 1: Write the tests** (spec §5): totals merge across two upserts; `dep_codes` by count, at most 5; an unaliased host prints sanitized; `partner-auth` on day 1 for a listed host with 401, none for an unlisted host with 401; a listed host with one 401 wins `dep_host` over an unlisted host with more 5xx; a Sentry group seen on two days never escalates; `persistent` once `last_seen` is 24 hours after `detected_at`; `escalated_at` set once and kept through a later upsert and a resolve; a rebuild from notes restores `dep_host` and `dep_codes`.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement** `_deps_merge`, `_dep_host`, `_escalate` helpers called from `upsert`; `_clean` sanitizes host keys and keeps integer codes only; `_rebuild` parses `dep_codes`.
- [ ] **Step 4: Run green**, then the other telemetry pytest files.
- [ ] **Step 5: Commit.** `feat(telemetry): span groups carry dependency totals and escalate as partner-auth or persistent`.

### Task 4: The fetch wiring, privacy and the issue's acceptance

**Files:**
- Modify: `system/scripts/vaultlib/telemetry_run.py`
- Create: `system/tests/fixtures/telemetry/kusto-spans.json`, `system/tests/fixtures/telemetry/kusto-deps.json`
- Test: `system/tests/python/test_telemetry_run.py`, `system/tests/telemetry.bats`

**Interfaces:**
- Consumes: `kql_deps`, `Source.adx_hosts`.
- Produces: span groups with `deps` and `listed`; `--dry-run` prints `deps` for span groups.

- [ ] **Step 1: Write the tests:** dependency rows land on the span group with the matching fingerprint and on no other; the privacy test (a deps row with a listed host carrying a `url.full` column with a query-string token, plus an unlisted host with a path and query: no token, path or query string in the notes, state, run log or dry-run output); bats: an `environment: uat` source with `adx_hosts` and client spans answering 401 writes a note with `dep_host: "partner-a"`, `dep_codes: "401: …"`, `escalate: "partner-auth"` and no `message`.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement:** in `_adx_groups`, after the spans signal, query `kql_deps`, map each row by `fingerprint(src.name, "span", {service, route, status})` (sanitized as the span branch does) to `{alias or sanitize(host): {str(code): n}}`, skip rows with no host or no matching group.
- [ ] **Step 4: Run green:** `test_telemetry_run.py`, `telemetry.bats`.
- [ ] **Step 5: Commit.** `feat(telemetry): the fetch attaches dependency hosts and codes to span groups`.

### Task 5: The brief and the documents

**Files:**
- Modify: `.claude/commands/brief.md`, `system/agents/workcells/maintenance.md`, `FOUNDRY.md`, `CLAUDE.md`, `.claude/commands/setup.md`
- Test: `system/tests/commands.bats` (after "/brief lists telemetry from v_production_error, new first, capped per environment")

- [ ] **Step 1: Write the test:** `brief.md` selects the new columns, holds the Escalated rule, the cap of 3 and the Add to Now bullet with the statement shape; `maintenance.md` names the dependency host and codes and drops the old "hold no message text" wording; `FOUNDRY.md` names `adx_hosts`, the Escalated block and that only host and status code of a dependency call leave the cluster; `CLAUDE.md`'s Now rule lists a telemetry note path; setup 6a names `adx_hosts`.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Write the sentences** (spec §3.5, §3.6).
- [ ] **Step 4: Run green:** `commands.bats`, `vault_integrity.bats`.
- [ ] **Step 5: Commit.** `feat(brief): an Escalated telemetry block and its Now lines`.
