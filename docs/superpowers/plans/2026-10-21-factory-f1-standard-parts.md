# F1: Standard Parts and Retrofits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift the connector stream checker, the fetch-script helpers, the state-file helpers and the test doubles into shared parts, then move the seven connector features onto them, one pull request each.

**Architecture:** Three libraries in core (`vaultlib/connector.py`, `vaultlib/state.py`, `system/scripts/lib_fetch.sh`), each lifted from a named copy, plus one connector stub and one `stream()` test builder. Task 1 ships them with ported tests and moves every suite onto the stub. Tasks 2 to 8 retrofit triage, meetings, the watch, notify, the calendar, handoffs and the RCA filer, in that order; each keeps its exit codes, log keys, alert keys and pinned reasons, and removes its F0 ratchet entries.

**Tech Stack:** Bash, Python (stdlib), bats, pytest, jq.

**Spec:** `docs/superpowers/specs/2026-10-21-factory-f1-standard-parts-design.md`

## Global Constraints

- Extract, don't invent: each part is lifted from the copy the spec names; no part holds a behaviour no feature uses.
- One pull request per task, body "Part of #<F1 issue>". Connector confinement is a safety surface: the owner merges every F1 PR.
- A retrofit changes only what spec §3.6 lists for it. Exit codes, log line keys, alert keys, `--check` output and every reason a test pins stay.
- Template stays generic: no vault, employer, client, people or host names and no user paths; "the live vault" where one is meant. Core names no Atlassian or Jira (`vault_integrity.bats` clean-names test).
- Core budget: measure with `git ls-files -z system/scripts | xargs -0 cat | wc -l`. Task 1 sets the cap in `vault_integrity.bats` to its measured count (owner's temporary raise, spec §7); each core retrofit (Tasks 2, 3, 5, 6) lowers it to its measured count. The comment names the change and the value the cap returns to.
- Each task removes its entries from the `system/tests/conformance.bats` allowlist (F0) and the suite passes.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- Test commands: `python3 -m pytest -q -n auto <paths>` and `bats <paths>`, or either through `system/scripts/test.sh <suite | path>`, which sets the gate's environment (temporary files under `.scratch/tmp`, a git ceiling). bats needs the sandbox disabled.
- CHANGELOG: Task 2 only (triage's paging is user-visible). Docs and test changes add none.
- Gate: CI's `gate`, with every extension off and with every extension on.

## Review Focus

1. **Pinned reasons drift:** a reason the brief, the smoke check or `sources.py` matches ("no Gmail connector reachable", "the session never called …", handoffs' and the RCA filer's "other arguments" texts, the calendar's `pageSize` hint) changes wording. Task 1 pins the library's texts; each retrofit's suite pins its own.
2. **A write session's result path:** a create with no result message must still return its key (Task 8); a landed post beside an errored one must count as sent (Task 5).
3. **The calendar's overflow forms:** "Output too large (78 KB)…" and "MCP tool response (N tokens) exceeds maximum allowed tokens" must count; event JSON quoting the limit must not (Tasks 1, 6).
4. **The `named` check (#38):** free text naming the tool in a ToolSearch result must give exit 3, never 1 (Task 1).
5. **The interim budget overshoot:** each core PR's measured count is at or under its cap, and the last one at or under 13,950 or an owner decision (Tasks 1, 2, 3, 5, 6).

---

### Task 1: The libraries and the connector stub

**Files:**
- Create: `system/scripts/vaultlib/connector.py`, `system/scripts/vaultlib/state.py`, `system/scripts/lib_fetch.sh`, `system/tests/stub_claude_connector`, `system/tests/python/test_connector.py`, `system/tests/python/test_state.py`
- Modify: `system/tests/python/helpers.py` (`call`, `stream`), `system/tests/connector.bats`, `system/scripts/smoke_check.sh:32-35` (`alert_once` from `lib_fetch.sh`, `FETCH_TAG=smoke`), `system/tests/vault_integrity.bats:409-430` (cap), `system/tests/conformance.bats` (allowlist)
- Switch to `stub_claude_connector`: `system/tests/{triage,prep,notify,connector,calendar,meetings}.bats`, `extensions/telemetry/tests/rca.bats`, `extensions/intraday/tests/watch.bats`, `extensions/handoffs/tests/handoffs.bats`
- Delete: `system/tests/stub_claude_calendar`, `stub_claude_meetings`, `extensions/intraday/tests/stub_claude_watch`

**Interfaces:**
- Produces (Python, `vaultlib.connector`): `Fail(code, reason)`; `too_large(content) -> bool`; `structured(block, message) -> dict`; `text_json(block, message) -> dict`; `strip_cursor(i: dict) -> dict`; `Walk(calls, results, named, result)`; `walk(stream, tool, accept, max_calls=None) -> Walk`; `check_stream(stream, tool, accept, max_pages=None, server="", persisted=None, take=structured, need_result=True) -> (dict[str, list], dict | None)`. `accept(input) -> str | None` may raise `Fail(7, reason)`.
- Produces (Python, `vaultlib.state`): `load(path, default)`, `save(path, data) -> None`, `append(path, record) -> None`, `records(*paths) -> list`.
- Produces (bash, `lib_fetch.sh`): variables `FETCH_NAME FETCH_TAG FETCH_LOG FETCH_FIELDS FETCH_LABEL FETCH_ALERTS`; functions `logline <exit> <reason> [<json>]`, `alert_once <key> <text>`, `fetch_reason <exit> <reason>` (sets `FETCH_REASON`), `fail <exit> <reason>`, `skip <reason> [<json>]`, `fetch_check_arg "$@"` (sets `check`), `fetch_workdir` (sets `work`), `fetch_others <tools...>` (sets `CONNECTOR_OTHERS`); arrays `GMAIL_TOOLS SLACK_TOOLS DRIVE_TOOLS CALENDAR_TOOLS`.
- Produces (tests): `helpers.call(input=None, text="…", sc=None, error=False) -> dict`; `helpers.stream(tool, calls=(), reply=None, result="success", named=True, **result_fields) -> list`; `stub_claude_connector` (spec §3.4).

- [ ] **Step 1: Write the failing pytest** (`test_connector.py`, `test_state.py`), ported from `test_watch_check.py`, `test_triage.py`, `test_calendar_tsv.py`, meetings' #38 case and `test_rca.py`:

`BIG` is claude's MCP note, as `test_watch_check.py:12` defines it.

```python
@pytest.mark.parametrize("text", [BIG, "<persisted-output>\nPreview…", '{"a": 1}\n\n[OUTPUT TRUNCATED - exceeded 25000 tokens]',
    "Output too large (78 KB). Full output saved to: /x/1.txt",
    "MCP tool response (31,000 tokens) exceeds maximum allowed tokens (25000).", [{"type": "text", "text": BIG}]])
def test_too_large_knows_each_stand_in(text): assert connector.too_large(text)

@pytest.mark.parametrize("text", ['{"results": "Error: result (9 characters) exceeds maximum allowed tokens"}',
                                  '[{"description": "Output too large"}]', '{"threads": []}'])
def test_result_text_cannot_fake_a_stand_in(text): assert not connector.too_large(text)

def test_walk_refuses_another_tool_but_not_toolsearch_or_structured_output():   # Fail 7 "unexpected tool: Bash"
def test_walk_refuses_an_input_accept_refuses_and_keeps_a_reason_accept_raises():
def test_walk_counts_calls_at_the_call():          # max_calls=1, second call → 7 even when the first result is_error
def test_free_text_naming_the_tool_is_not_a_connector():   # ToolSearch text block → check_stream Fail 3, not 1 (#38)
def test_check_stream_order():                     # no result → 1 "claude produced no result"; error → 6;
                                                   # named, no call → 1 "never called"; not named → 3
                                                   # "no Gmail connector reachable"; error_max_turns → 1
def test_pages_group_by_name_and_take():           # two names; take=text_json parses Slack text; default structured
def test_a_too_large_result_fails_6_or_counts_into_persisted():  # persisted None → 6; {} → {"mail": 1}, page still taken
def test_need_result_false_returns_pages_without_a_result_message():
def test_save_is_atomic_and_load_falls_back():     # no temporary file left; missing or bad JSON → default
def test_records_reads_each_path_in_order_and_skips_bad_lines():
```

- [ ] **Step 2: Write the failing bats** in `connector.bats`:
  - `logline 0 "" '{"items": 3}'` with `FETCH_FIELDS='{"items": 0, "source": "mail"}'` writes keys `time exit reason items source`, `items` 3;
  - `alert_once` writes `[$FETCH_TAG] <key>` once for two calls the same day;
  - `fail 3 "no Gmail connector reachable"` with `FETCH_ALERTS="1 3"` exits 3, logs `auth: no Gmail connector reachable`, alerts `<FETCH_LABEL> failed (exit 3):`, prints `<FETCH_NAME>: auth: …`; `fail 2 x` alerts nothing;
  - `skip "outside hours"` logs `skipped: outside hours` and exits 0;
  - `fetch_check_arg` sets 0, 1, and exits 2 on `--bogus` with the usage line;
  - `fetch_workdir` leaves no directory after the subshell exits;
  - `fetch_others "${SLACK_TOOLS[@]}"` with `CONNECTOR_TOOL=<prefix>__slack_send_message` omits `slack_send_message` and keeps `slack_search_public_and_private`;
  - the stub: a Slack, a Gmail and a Calendar session each print their `STUB_<KIND>_STREAM`; `STUB_STREAMS` picks `read-<id>.jsonl` from the prompt's `fileId`; `STUB_STREAM.next` replaces `STUB_STREAM` after one session; `mcp list` prints the Calendar line by default.

- [ ] **Step 3: Run them to verify they fail**

Run: `python3 -m pytest -q -n auto system/tests/python/test_connector.py system/tests/python/test_state.py` and `bats system/tests/connector.bats`
Expected: FAIL (`vaultlib.connector` missing, `lib_fetch.sh` missing).

- [ ] **Step 4: Implement** `connector.py`, `state.py`, `lib_fetch.sh`, `stub_claude_connector`, `helpers.call` and `helpers.stream` to spec §3.1 to §3.4, lifting from the named lines. `check_stream`'s steps run in the spec's order (§3.1, 1 to 5).

- [ ] **Step 5: Run them to verify they pass** (same commands). Expected: PASS.

- [ ] **Step 6: Move every suite onto the stub and delete the three old stubs.** `watch.bats`: `STUB_ARGS_<KIND>` → `STUB_<KIND>_ARGS`, and `STUB_STREAM` set to a one-line empty success result in setup. `meetings.bats`, `handoffs.bats`: set `STUB_MCP_LIST` where they relied on the Drive default. `smoke_check.sh` sources `lib_fetch.sh` for `alert_once`.

Run: `bats system/tests/triage.bats system/tests/prep.bats system/tests/notify.bats system/tests/connector.bats system/tests/calendar.bats system/tests/meetings.bats system/tests/smoke.bats extensions/telemetry/tests/rca.bats extensions/intraday/tests/watch.bats extensions/handoffs/tests/handoffs.bats`
Expected: PASS with no assertion changed.

- [ ] **Step 7: Budget and ratchet.** Measure core lines; set the cap to the count (about 14,125) with the comment "F1 libraries; returns to ≤ 13,950 after the calendar retrofit (owner, temporary)". In `conformance.bats` (spec §3.7):
  - add the parts' homes (`vaultlib/connector.py`, `lib_fetch.sh`) as the allowed definitions; remove `smoke_check.sh`'s `alert_once`; give `nightshift_session.py`'s entry its "different shape" reason;
  - add `@test "one connector stub"`: the `stub_claude_*` files under `system/tests` and `extensions/*/tests` are exactly `stub_claude_connector` and `stub_claude_nightshift`; seeded by copying a stub to `stub_claude_extra`, it fails;
  - add `@test "one stream builder"`: no file under `*/tests/python` but `helpers.py` and `test_connector.py` holds `"tool_reference"`, outside an allowlist of `test_triage.py`, `test_notify.py`, `test_watch_check.py`, `test_handoffs_jira.py`, `test_rca.py` (stale entries fail, as F0's do).

Run: `bats system/tests/vault_integrity.bats system/tests/conformance.bats`
Expected: PASS.

- [ ] **Step 8: Commit** (`feat(factory): shared connector, state and fetch parts, one connector stub (F1)`).

### Task 2: Inbox and chat triage

**Files:** `system/scripts/vaultlib/triage.py`, `system/scripts/triage.py` (the `extract` command's JSON gains `hold` and `stats`; `record` reads `hold`), `system/scripts/triage_fetch.sh`, `system/tests/python/test_triage.py`, `system/tests/triage.bats`, `FOUNDRY.md` (Inbox triage paragraph), `CHANGELOG.md`, `system/tests/vault_integrity.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `check_stream`, `structured`, `text_json`, `strip_cursor`, `Fail` (connector); `records`, `append` (state); `lib_fetch.sh` with `GMAIL_TOOLS`, `SLACK_TOOLS`.
- Produces: `MAX_PAGES = 6`; `extract(stream, q) -> {"items", "full", "hold", "stats"}`; `chat_extract(stream, q, tool, notify_channel) -> {"items", "full", "hold": False, "stats"}`; `stats = {"results", "rows", "kept", "persisted", "dropped": {"unknown", "empty", "duplicate"}}`; `record(..., source)` writes `"hold": true` on the tick when `found["hold"]`; `cursor` skips held ticks. `vaultlib.triage` re-exports `Fail`, `_structured`, `_text_json` until Task 4.

- [ ] **Step 1: Write the failing tests.** pytest (each suite builder now wraps `helpers.stream`):
  - `test_mail_reads_up_to_six_pages_and_a_last_page_with_a_token_is_full`: 7 calls → Fail 7; 2 pages, token on the second → `full` true; 6 pages, no token → false (replaces `test_more_than_three_pages_is_refused_and_a_full_third_page_is_flagged`);
  - `test_the_mail_search_must_ask_the_minimal_view`: `view` `THREAD_VIEW_FULL` → Fail 7;
  - `test_a_mail_page_too_large_is_counted_and_holds_the_cursor`: `hold` true, `stats["persisted"] == 1`, items of the other page kept; after `record`, `cursor(...)` equals the cursor before the tick;
  - `test_extract_counts_results_rows_kept_and_drops`: 3 threads, 4 rows (one unknown thread, one empty ask, one duplicate) → `{"results": 3, "rows": 4, "kept": 1, "dropped": {"unknown": 1, "empty": 1, "duplicate": 1}}`;
  - `test_a_chat_page_too_large_fails_6`.
  bats (`triage.bats`):
  - the mail prompt asks `pageSize 10` and "6 calls";
  - a tick's log line has `.stats.kept` and `.items`; a failure line still has `items: 0` and `source`;
  - a too-large page writes one `[triage] Inbox triage returned a page too large for the model to read:` alert for two ticks the same day, and the next query's `after:` is unchanged;
  - `--check` prints the threads returned.

- [ ] **Step 2: Run to verify they fail.**
Run: `python3 -m pytest -q -n auto system/tests/python/test_triage.py` and `bats system/tests/triage.bats`
Expected: FAIL on the new tests only.

- [ ] **Step 3: Implement.** `pages`, `Fail`, `_structured`, `_text_json` go (one re-export line); `extract` and `chat_extract` call `check_stream` (`server="Gmail"`/`"Slack"`, mail `persisted={}`); ledger on `state`. `triage_fetch.sh`: `source lib_fetch.sh` with `FETCH_NAME=triage_fetch FETCH_TAG=triage FETCH_LABEL="$label" FETCH_ALERTS="1 2 3 4 6 7" FETCH_FIELDS` (`items: 0`, and `source` when set); the two lists → `fetch_others`; `fetch_workdir`; prompt: `pageSize 10`, follow `nextPageToken` "until none is left or the search has had 6 calls"; `CONNECTOR_TURNS=16`; the full alert key `Inbox triage read 6 full pages:`; the hold alert; the log line's `stats`.

- [ ] **Step 4: Run to verify they pass** (same commands, plus `bats system/tests/smoke.bats system/tests/prep.bats`). Expected: PASS.

- [ ] **Step 5: Docs, budget, ratchet.** FOUNDRY.md: "at most 60 threads a tick, in pages of 10" and the hold alert. CHANGELOG under today's date:
  `- Fixed: inbox triage reads mail in pages of 10, at most 60 threads a tick (was 3 pages of 50). A page of 50 threads can pass the size the model can read, and the model then sees none of them; that cost the intraday watch its mail in #289 and is not confirmed for triage. A page still too large keeps triage's place in the inbox and raises one [triage] alert a day, and each tick's log line counts the threads returned and the rows kept and dropped. (#<n>)`
  Lower the core cap to the measured count. Remove triage's allowlist entries (walker, `Fail`, `logline`, `alert_once`, `fail`, `skip`, and `test_triage.py` from the builder list).
Run: `bats system/tests/vault_integrity.bats system/tests/conformance.bats`. Expected: PASS.

- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for triage.

### Task 3: Meetings fetch

**Files:** `system/scripts/meetings_extract.py`, `system/scripts/meetings_fetch.sh`, `system/tests/meetings.bats`, `system/tests/vault_integrity.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `check_stream`, `Fail` (connector); `lib_fetch.sh` with `DRIVE_TOOLS`, `fetch_check_arg`.
- Produces: `search(stream) -> list` and `read(stream, doc_id, listing)` unchanged in signature; `results` and `names_drive` removed.

- [ ] **Step 1: Write the failing bats:**
  - a read whose result content is claude's too-large note still writes `raw/meetings/<id>.gdoc.md` from `structuredContent` and exits 0;
  - a search result that is too large exits 6 with one `[meetings] Drive fetch failed (exit 6):` alert and keeps `.since`;
  - a ToolSearch text block naming the Drive tool, with no call, exits 3 (#38).
- [ ] **Step 2: Run to verify they fail.** Run: `bats system/tests/meetings.bats`. Expected: FAIL on the first two.
- [ ] **Step 3: Implement.** `search`: `check_stream(stream, TOOLS["search"], lambda i: "search", server="Google Drive")`. `read`: `accept` returns `"read"` for `fileId == doc_id`, else raises `Fail(7, f"the session read a Doc that was not requested: {i.get('fileId')}")`; `persisted={}`. The script on `lib_fetch.sh` (`FETCH_NAME=meetings_fetch FETCH_TAG=meetings`, `FETCH_LOG`, `FETCH_FIELDS` none); `logline` callers pass `{"step", "doc"}`; the session's alert rule stays.
- [ ] **Step 4: Run to verify they pass.** Run: `bats system/tests/meetings.bats system/tests/prep.bats`. Expected: PASS.
- [ ] **Step 5: Budget and ratchet.** Lower the cap to the measured count; remove meetings' entries. Run: `bats system/tests/vault_integrity.bats system/tests/conformance.bats`. Expected: PASS.
- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for meetings.

### Task 4: Intraday watch

**Files:** `extensions/intraday/scripts/watchlib/check.py`, `watchlib/common.py`, `extensions/intraday/scripts/watch_fetch.sh`, `system/scripts/vaultlib/triage.py` (drop the re-export line), `extensions/intraday/tests/python/test_watch_check.py`, `extensions/intraday/tests/watch.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `check_stream`, `too_large`, `text_json`, `structured`, `strip_cursor`, `Fail` (connector); `load`, `save`, `append`, `records` (state); `lib_fetch.sh` with `GMAIL_TOOLS`, `SLACK_TOOLS`.
- Produces: `slack_extract` and `mail_extract` unchanged in signature and return; `common.Fail is connector.Fail`.

- [ ] **Step 1: Write the failing tests:** `test_watch_check.py` imports `too_large` from `vaultlib.connector` and asserts `common.Fail is connector.Fail` and that `watchlib.check` defines no `query_pages`; the too-large cases that moved to `test_connector.py` in Task 1 leave this file. `watch.bats`: a failed session's log line has keys `time exit reason step count`.
- [ ] **Step 2: Run to verify they fail.** Run: `python3 -m pytest -q -n auto extensions/intraday/tests/python` and `bats extensions/intraday/tests/watch.bats`. Expected: FAIL on the import assertions.
- [ ] **Step 3: Implement.** `slack_extract`: `check_stream(stream, tool, lambda i: next((n for n, q in queries.items() if strip_cursor(i) == q), None), MAX_PAGES, "Slack", take=text_json)`, then `{n: pages.get(n, []) for n in queries}`. `mail_extract`: the same `name_of` as `accept`, `MAIL_PAGES`, `"Gmail"`, `persisted`. `common.py` re-exports from `connector` and `state`. `watch_fetch.sh` on `lib_fetch.sh` (`FETCH_TAG=intraday`, `FETCH_FIELDS='{"count": 0}'`); `logline <step> …` callers pass `{"step", "count", "stats"}`; `failed` on `fetch_reason`. Remove triage's re-export line.
- [ ] **Step 4: Run to verify they pass.** Run: `python3 -m pytest -q -n auto extensions/intraday/tests/python system/tests/python/test_triage.py` and `bats extensions/intraday/tests/watch.bats extensions/intraday/tests/intraday.bats`. Expected: PASS.
- [ ] **Step 5: Ratchet.** Remove the watch's entries, including its private imports from `vaultlib.triage` (`_structured`, `_text_json`) and `test_watch_check.py` from the builder list. Run: `bats system/tests/conformance.bats`. Expected: PASS.
- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for the watch.

### Task 5: Notify

**Files:** `system/scripts/vaultlib/notify.py`, `system/scripts/notify.sh`, `system/tests/python/test_notify.py`, `system/tests/notify.bats`, `system/tests/vault_integrity.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `walk`, `Fail` (connector); `load`, `save` (state); `lib_fetch.sh` with `SLACK_TOOLS`, `fetch_check_arg`.
- Produces: `check(stream, tool, channel, message_text, lines, thread=None) -> (drift, ts list)` unchanged.

- [ ] **Step 1: Write the failing tests:** `test_notify.py`: `test_a_landed_post_beside_an_errored_call_counts_as_sent` (two calls, the first `is_error`, the second landed → `("", [<its ts>])`, no Fail), and `notify.Fail is connector.Fail`; the builder wraps `helpers.stream`.
- [ ] **Step 2: Run to verify they fail.** Run: `python3 -m pytest -q -n auto system/tests/python/test_notify.py`. Expected: FAIL on the identity assertion.
- [ ] **Step 3: Implement.** `check`: `w = walk(stream, tool, accept)`, where `accept` raises today's two Fail 7 reasons and returns `"post"`; the end rules read `w.results`, `w.named`, `w.result` and the init message as today. `_load`, `commit` on `state`. `notify.sh` on `lib_fetch.sh` (`FETCH_NAME=notify FETCH_TAG=notify FETCH_LABEL=Notices FETCH_ALERTS="1 2 3 4 5 6 7 127" FETCH_FIELDS='{"events": 0}'`).
- [ ] **Step 4: Run to verify they pass.** Run: `python3 -m pytest -q -n auto system/tests/python/test_notify.py` and `bats system/tests/notify.bats`. Expected: PASS.
- [ ] **Step 5: Budget and ratchet.** Lower the cap; remove notify's entries and `test_notify.py` from the builder list. Run: `bats system/tests/vault_integrity.bats system/tests/conformance.bats`. Expected: PASS.
- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for notify.

### Task 6: Calendar

**Files:** `system/scripts/calendar_tsv.py`, `system/scripts/calendar_fetch.sh`, `system/tests/python/test_calendar_tsv.py`, `system/tests/calendar.bats`, `system/tests/vault_integrity.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `walk`, `too_large`, `Fail` (connector); `messages` (stream); `lib_fetch.sh` with `CALENDAR_TOOLS`, `fetch_reason`, `fetch_workdir`.
- Produces: `calendar_tsv.py YYYY-MM-DD --summary FILE` unchanged (exits 0, 1, 2, 3, 5, 6, 7, 8; the summary's keys).

- [ ] **Step 1: Write the failing tests:** the suite's builder gives each `tool_use` an id (`t1`, …) and the oversized test's result pairs with it; new: `test_an_ok_status_without_a_list_events_call_exits_1_or_3` (named → 1, not named → 3); `test_two_unexpected_tools_exit_7_and_both_reach_the_summary`.
- [ ] **Step 2: Run to verify they fail.** Run: `python3 -m pytest -q -n auto system/tests/python/test_calendar_tsv.py`. Expected: FAIL on the new rule.
- [ ] **Step 3: Implement.** Remove `Fail`, `OVERFLOW`, `overflowed`, `parse_stream`. `main`: `messages(stdin)`; empty → Fail 1; the summary pass stays and no longer raises; `walk(messages, TOOL, lambda i: "events")`; `too_large` over `walk.results` raises today's Fail 6 text; then the result and status rules; an `ok` status with no `walk.calls` raises `Fail(1 if named else 3, …)`. `calendar_fetch.sh`: `fetch_others "${CALENDAR_TOOLS[@]}"`, `fetch_workdir`, `finish` on `fetch_reason`.
- [ ] **Step 4: Run to verify they pass.** Run: `python3 -m pytest -q -n auto system/tests/python/test_calendar_tsv.py` and `bats system/tests/calendar.bats system/tests/prep.bats system/tests/smoke.bats`. Expected: PASS.
- [ ] **Step 5: Budget and ratchet.** Set the cap to the measured count; at or under 13,950 the comment closes the temporary raise, above it the PR asks the owner with the number. Remove the calendar's entries. Run: `bats system/tests/vault_integrity.bats system/tests/conformance.bats`. Expected: PASS.
- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for the calendar.

### Task 7: Handoffs

**Files:** `extensions/handoffs/scripts/jira_handoffs.py`, `extensions/handoffs/scripts/jira_fetch.sh`, `extensions/handoffs/tests/python/test_handoffs_jira.py`, `extensions/handoffs/tests/handoffs.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `check_stream`, `Fail` (connector); `lib_fetch.sh` with `fetch_check_arg`, `fetch_others`.
- Produces: `extract(stream, cfg) -> list` unchanged; the full Atlassian table stays in `jira_fetch.sh`.

- [ ] **Step 1: Write the failing test:** `test_a_page_too_large_for_the_model_fails_6`; the builder wraps `helpers.stream`.
- [ ] **Step 2: Run to verify it fails.** Run: `python3 -m pytest -q -n auto extensions/handoffs/tests/python`. Expected: FAIL.
- [ ] **Step 3: Implement.** `pages` → `check_stream(stream, TOOL, accept, server="Atlassian")`, `accept` raising today's reason for another `jql` or `cloudId`. `jira_fetch.sh` on `lib_fetch.sh` (`FETCH_TAG=handoffs FETCH_LABEL="Jira fetch" FETCH_ALERTS="1 3 6 7" FETCH_FIELDS='{"lines": 0}'`); `OTHER_TOOLS` becomes the full list, search included, passed to `fetch_others`.
- [ ] **Step 4: Run to verify it passes.** Run: `python3 -m pytest -q -n auto extensions/handoffs/tests/python` and `bats extensions/handoffs/tests/handoffs.bats`. Expected: PASS.
- [ ] **Step 5: Ratchet.** Remove handoffs' entries and `test_handoffs_jira.py` from the builder list. Run: `bats system/tests/conformance.bats`. Expected: PASS.
- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for handoffs.

### Task 8: RCA filer

**Files:** `extensions/telemetry/scripts/telemetrylib/rca.py`, `extensions/telemetry/scripts/rca_file.sh`, `extensions/telemetry/tests/python/test_rca.py`, `extensions/telemetry/tests/rca.bats`, `system/tests/conformance.bats`.

**Interfaces:**
- Consumes: `check_stream`, `Fail` (connector); `lib_fetch.sh` with `fetch_workdir`, `fetch_others`.
- Produces: `extract(stream, args) -> str` unchanged; `called`, `rejected_create` unchanged.

- [ ] **Step 1: Write the failing tests:** `test_a_create_with_no_result_message_still_returns_its_key` (the stream cut before the result message → `"EX-7"`); `test_a_second_create_call_fails_7_even_after_an_error`; `test_a_session_that_used_another_tool_is_never_a_clean_rejection` (a rejected create plus a `Bash` call → `rejected_create` returns None); `rca.Fail is connector.Fail`; the builder wraps `helpers.stream`.
- [ ] **Step 2: Run to verify they fail.** Run: `python3 -m pytest -q -n auto extensions/telemetry/tests/python/test_rca.py`. Expected: FAIL on the last three.
- [ ] **Step 3: Implement.** `extract`: `check_stream(stream, TOOL, accept, max_pages=1, server="Atlassian", need_result=False)`, `accept` raising "the session called the create tool with other arguments than the approved draft"; the key from `pages["create"][0]`. `rejected_create`: `walk(stream, TOOL, lambda i: "create")` inside `try`, None on `Fail`, then today's rule over `calls` and `results`. `rca_file.sh` on `lib_fetch.sh` (`FETCH_TAG=rca FETCH_LABEL="Filing $stem" FETCH_ALERTS="1 2 3 4 5 6 7"`, `FETCH_FIELDS` with `note` and `key: ""`); the full Atlassian list to `fetch_others`.
- [ ] **Step 4: Run to verify they pass.** Run: `python3 -m pytest -q -n auto extensions/telemetry/tests/python` and `bats extensions/telemetry/tests/rca.bats extensions/telemetry/tests/extension.bats`. Expected: PASS.
- [ ] **Step 5: Ratchet.** Remove the RCA filer's entries and `test_rca.py` from the builder list; the allowlist now holds no walker but `nightshift_session.py`, and no `class Fail`, `logline`, `alert_once`, `fail` or `skip` outside the parts' homes. Run: `bats system/tests/conformance.bats`. Expected: PASS.
- [ ] **Step 6: Commit.** After merge (owner): spec §3.9 for the RCA filer (the audit waits for the next filing). Tick F1's "Done when" on the issue and the roadmap row.
