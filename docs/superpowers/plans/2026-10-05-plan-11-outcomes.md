# Plan 11 Outcomes

Execution of docs/superpowers/plans/2026-10-05-plan-11-error-monitoring.md on feat/plan-11 (31763de..c435eff). Tasks 1–8 complete with per-task reviews; final whole-branch review and one fix wave done. Task 9 (README, gate, live acceptance) pending.

## Rulings made during execution

- Ruling R1: LOCK_WAIT = int(os.environ.get("TELEMETRY_LOCK_WAIT", "120")) — the plan's Step 5 requires it for the lock test — cost if wrong: none (default unchanged).
- Ruling R2: write off.md as its own literal source with name "off" and enabled: "false" — the chained replace is fragile — cost if wrong: none.
- Ruling R3: implementer writes kusto-logs.json as a v2 frame list (DataSetHeader, PrimaryResult with columns service, scope, event_id, n, first, last, traces, sample_trace and one row using a 32-hex trace id, DataSetCompletion) and kusto-check.json with one column ok and row [1] — cost if wrong: fixture rework only.
- Ruling R4: covers stays as an opt-in (generic code unchanged in Task 6); no automatic "coverage unavailable" detection and no brief fallback grouping — the spike shows covers simply should not be set for this codebase, and setup 6a (Task 8) asks for covers only when the user confirms shared trace IDs — cost if wrong: a later codebase with shared traces gets coverage by setting covers; nothing is lost.
- Ruling R5: fix the plan-mandated HasErrors bug (kusto.query returns partial rows as success when DataSetCompletion.HasErrors follows PrimaryResult) — a partial result would advance the checkpoint and silently lose groups (spec §3.1/§5.1 say failures keep the checkpoint) — cost if wrong: one extra loop over frames.
- Ruling R6: also reset request.last_headers at the top of http.request (stale headers could feed a wrong Link cursor to Task 4) — cheap, removes a cross-call leak — cost if wrong: none.
- Ruling R7: accept that Sentry `environment` may be None from the issues list, using the project slug for `service` — spec §4 names that fallback; per-issue tag fetches would add calls for a display field — cost if wrong: brief rows show the project slug instead of the service name.
- Ruling R8: the store enforces the data policy on whitelisted fields itself (defense in depth): keys → sanitize except event_id → event_id(); service/culprit → sanitize; exception for kind log → sanitize(scope)#event_id(id), else sanitize; operation_id → trace_id() or a plain digit Sentry ID, else ""; sentry_issue → ^[A-Za-z0-9_-]+$ else dropped; link → query string cut — the privacy guarantee should not rest on every caller — cost if wrong: idempotent double-sanitizing, negligible.
- Ruling R9: regressed persists (state carries it) until the group is resolved again — spec §3.5 marks a returning group regressed; one run is too short for a daily brief — cost if wrong: a regressed flag lingers until resolve.
- Ruling R10: upsert keeps status "deprecated" (manual retirement wins); otherwise active — vault lifecycle rule — cost if wrong: none.
- Ruling R11: include two cheap minors: `| order by n desc` before `| take` in both KQL builders; last_seen = max(old, new) — truncation should drop the smallest groups; time must not run backward — cost if wrong: none.
- Ruling R12: catch any exception per source (rc 1, failures+1, error = exception type name only, no message) and save state in a finally block outside dry-run — spec §5.1 "one source fails, others still run"; an unsaved state double-counts ADX on the next run — cost if wrong: none.
- Ruling R13: coverage retry — groups not looked up because of the 20 cap are marked cover_pending in state and looked up first on later runs (spec §3.4 "retried next run") — cost if wrong: a little state.
- Ruling R14: no alerts written in --dry-run (spec §5.1 "write nothing").
- Ruling R15: fold cheap minors: tests derive the alerts filename from now.astimezone() (alerts stay local-day like vault_sync); truncated accumulates across signals; failure log lines carry window and zero counters; remove unused Usage class and _adx_groups by_name param.
- Ruling R16: brief selects active groups plus groups with resolved_at in the last 24 h (resolved line), and the commands test asserts resolved_at — spec §6 requires the resolved line — cost if wrong: none.
- Ruling R17: drop the plan's mock filter; mock notes stay listed, marked "(mock)" — spec §6 "mock notes ... still shown by the brief, as before" outranks the plan's coalesce(mock,0)=0 — cost if wrong: test notes appear in the brief, labeled.
- Ruling R18: fold minors: split the nested parenthetical into sub-bullets; name the `sentry_issue` column for the short ID; remove "(Plan 11)" from setup.md prose; confirm the maintenance.md bullet continuation renders.
- Ruling R19: fix C1 two ways — Store tolerates a missing note (drops or skips the group) AND main restores the source's state snapshot on any exception so a failed source leaves no partial counts — Review Focus 2 — cost if wrong: none.
- Ruling R20: fix I2 — issue_for_trace returns None unless issue matches ^[A-Za-z0-9_-]+$ and issue.id is digits; set_covered re-applies the regex.
- Ruling R21: fix I3 — Sentry issue_status 404 counts as resolved; other per-issue errors skip that issue and continue.
- Ruling R22: fix I4 — reopen KQL built with the group's time range, the source's adx_filter, quoted keys (service/scope/event_id or service/route/status).
- Ruling R23: fold minors 5 (dry-run loads state read-only), 6 (sanitize: 16+ hex runs → <hex>, URL-decode before matching), 7 (brief cutoff in UTC +00:00), 9 (load_sources skips a source with bad rank/enabled/unknown codebase and reports it as a failed source line instead of crashing), 10 (one end-to-end privacy test through telemetry_run with raw Sentry and ADX payloads, scanning notes, state, jsonl, alerts and stdout). Deferred: 8 (extra frontmatter dropped on rewrite), 11 (coverage failure fails the covering ADX source; covers unset).

## Open after the final fix wave

- The reopen KQL in ADX notes repeats the column (`Timestamp >= Timestamp >= …`) and does not parse. Fix: the where line is `rng(col)` alone; assert the whole line in the test.

## Deferred minors

- Task 2: minor (deferred): covers test combines three faults; no sentry-with-adx-fields test; no sentry-missing-field test.
- Task 2: minor (deferred): test_telemetry_schema.py:321 loose "name" substring assertion.
- Task 2: minor (deferred): .gitignore system/telemetry.lock redundant with system/*.lock (spec-mandated).
- Task 2: minor (deferred): unknown kind falls into adx branch (schema enum already errors).
- Task 3: minor (deferred): TOKEN_CMD override drops resource args for custom commands (plan-mandated, test-only seam).
- Task 3: minor (deferred): urllib redirects may re-send Authorization; no https check on cluster URL (config-driven).
- Task 3: minor (deferred): IncompleteRead / non-dict frame escape as non-TelemetryError.
- Task 3: minor (deferred): test gaps — network/timeout branch, max_rows slicing, kusto-count/check routes, requests.log, per-status parametrization.
- Task 4: minor (deferred): since.strftime drops tz (callers pass UTC); statsPeriod=14d hardcoded (plan-mandated, window cap 7d makes it safe).
- Task 4: minor (deferred): 5-page cap gives no truncated signal; Link header lookup case-sensitive.
- Task 4: minor (deferred): untested project_ids/issue_status/token missing+empty; page-cap test does not count calls.
- Task 4: minor (deferred): trace_id not validated before the Discover query (callers pass trace_id()-validated hex); missing issue.id becomes "None"; token read per request.
- Task 5: minor (deferred): naive timestamps raise TypeError; inverted window unguarded; missing type clobbers first field in _write_note; _rebuild int() on garbage count; quarantine name 1 s resolution; body str.replace re-substitution and | or newline in table cells; crash between write and save resets count.
- Task 5: minor (deferred): redundant substatus check in fm regressed expression.
- Task 6: minor (deferred): single "state" alert key drops a second distinct store warning per day; Sentry status checks oldest-first cap can starve newer stale issues (7-day resolve drains); unresolvable project slug re-queries IDs every run.
- Task 6: minor (deferred): missing note for a cover_pending group fails that source every run; pending lookups also run for resolved/deprecated groups; a source failing mid-way leaves notes written while the checkpoint stays (recount on retry, documented).
- Task 7: minor (deferred): install_units hides --list failures (2>/dev/null) → a transient failure removes the telemetry timer until the next install (plan-mandated, fails safe); no tests for stale removal, client role, az absent on client, hint text.
- Task 8: minor (deferred): brief 24 h cutoff is a placeholder the Foreman computes each run.
- Final: minor (deferred): span reopen omits the error-status filter; reopen keys can differ from raw after decode/cut; _cover new-group loop sends empty trace lookups (and dry-run makes Sentry calls); HEX before DIGITS turns 16+ digit numbers into <hex>; _note catches FileNotFoundError only; rebuild after a failed source reads a note count that state had rolled back.
