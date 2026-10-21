# F1: standard parts and retrofits

**Date:** 2026-10-21
**Status:** Draft for the owner. Program: the factory plan (`docs/superpowers/2026-10-21-factory-plan.md`, phase F1). Depends on F0 (`system/tests/conformance.bats` and its allowlist). §2 items 4 to 10 were decided while specifying and are open to the owner's review; §7 lists the owner's decisions.
**Program:** `docs/superpowers/2026-10-21-factory-plan.md` (phase F1)
**Grill:** 2026-10-21, recorded in the program plan's `## Grill` section (the factory is the owner's idea).
**Builder check:** 2026-10-21, six questions. Settled as the builder's calls: merge sequence (§2 item 10), F0 as the ratchet authority (§3.7), who runs the server checks (§3.9), `StructuredOutput` for the calendar only (§3.1). Answered: no vault-only code imports what moves (the live vault's session checked 2026-10-21: its only vault-only extension imports `frontmatter`, `schema` and `yamlload`), so the triage re-export is temporary and needs no cutover note. The owner's §7 decisions are recorded there.
**Blueprint:** Source (the shared parts every Source uses); the retrofits keep each feature's shape.
**Inputs:** the development pattern survey (`docs/reviews/`, feature matrix and defect classes C1 to C13), the phase D spec (`2026-10-19-phase-d-intraday-design.md` §3.11, the #289 and #297 page fixes), the connector runner spec (`lib_connector.sh`, unchanged here).

## 1. Problem

Seven connector features share one shape: a confined `claude -p` session run by `lib_connector.sh`, then a deterministic checker of its stream-json. The runner is shared. Everything around it was copied per feature:

- **The stream walker, 7 copies:** `vaultlib/triage.py:162` (`pages`), `extensions/intraday/scripts/watchlib/check.py:42` (`query_pages`), `system/scripts/meetings_extract.py:46` (`results`), `vaultlib/notify.py:322` (`check`), `system/scripts/calendar_tsv.py:110-148` (`main`), `extensions/handoffs/scripts/jira_handoffs.py:60` (`pages`), `extensions/telemetry/scripts/telemetrylib/rca.py:140` (`extract`). Each checks the allowed tools, the call inputs, error results, the result message and whether the connector loaded, and each differs a little.
- **`class Fail`, 6 copies** (triage, notify, calendar, meetings, handoffs, RCA).
- **Shell helpers:** `logline` in 6 fetch scripts, `alert_once` in 7 (the 6 plus `smoke_check.sh`), `fail` in 4, the `--check` parser in 3, the work-directory trap in 7, and the deny lists (`*_OTHERS`) in 7, which disagree (triage's Slack list holds the send tool, notify's holds the search).
- **State files:** atomic JSON save and JSONL ledgers in the watch (`watchlib/common.py:31-60`), triage (`triage.py:47-70`) and notify (`notify.py:73-85`).
- **Test doubles:** 3 connector stubs (`stub_claude_calendar`, `stub_claude_meetings`, `stub_claude_watch`) and a `stream()` builder in 5 pytest suites.

The defects follow the copies. Too-large detection (C1) exists only in the watch and the calendar. Triage mail still asks for pages of 50 threads with no too-large check (`triage_fetch.sh:111`): the setup that cost the watch its mail in #289, where 50 threads passed the model's 25,000-token result limit, the model saw a stand-in note, and the checker read the full `structuredContent` anyway. Whether triage lost mail this way is **not established**: triage logs only the items it added, never the threads a search returned, so its log cannot show a tick with many threads and no rows. Connector detection (C4) differs per copy: meetings counts a ToolSearch hit only from a `tool_reference` block (#38), the others from any block with a `tool_name`.

## 2. Decisions

Owner, 2026-10-21:
1. Existing features move onto the shared parts.
2. CI conformance tests enforce the line (F0's ratchet now, F3's rules later).
3. Development skills ship in `.claude/skills/` (F4; nothing here).

Decided while specifying (for the owner's review):

4. **Extract, don't invent.** Each part is lifted from a named copy (§3). A part holds a behaviour only when a current feature uses it. No cursor prune is added: no cursor copy has one (notify's 7-day `THREAD_DAYS` prunes its post record, and stays in notify).
5. **Two walker functions, layered.** `check_stream` (for read sessions) is built on `walk` (the tool and input guard). Five walkers use `check_stream`. Notify and the calendar use `walk` and keep their own end rules, because their end rules differ in substance (§3.5). This replaces the program's single `check_stream` for all seven.
6. **`others` is shell.** The program placed `others(server, tool)` in `connector.py`; no such function exists. The deny lists are bash arrays that `lib_connector.sh` reads, so the part is `fetch_others` in `lib_fetch.sh`, lifted from `meetings_fetch.sh:71-72` (one full tool table per server, the allowed tool subtracted).
7. **The Atlassian tool list stays in the extensions.** Core's clean-names test (`vault_integrity.bats`, "core names no vendor") refuses `atlassian` and `jira` in `system/scripts/`, so `lib_fetch.sh` holds the Gmail, Slack, Drive and Calendar tables only. Handoffs and the RCA filer each keep one full Atlassian table; F2's extension API is where a shared one would go.
8. **One connector stub, in the library PR.** The three connector stubs merge into `system/tests/stub_claude_connector`, and every suite moves onto it in the library PR (tests only, no feature change). `system/tests/stub_claude` (headless runs, `STUB_MODE`) and `stub_claude_nightshift` are not connector stubs and stay.
9. **Triage too-large: count and hold, as the watch's mail.** A triage mail page the model saw only as too large is counted, its tick keeps the cursor, and one `[triage]` alert a day says so; the rows from the pages the model did read still land. Failing the session (exit 6) would also keep the cursor but drop those rows. Chat triage fails a too-large page with exit 6, as the watch's Slack session does.
10. **Order:** triage, meetings, watch, notify, calendar, handoffs, RCA filer. One PR each. Triage goes first because of the possible mail loss (§1). *Builder's call:* the PRs build in parallel and merge one at a time in this order, each rebased on the last (they share the ratchet allowlist and the budget cap). A retrofit merges after the previous one's live `--check` passed; triage's 24-hour audit also passes before the meetings PR merges, since triage is the 30-minute source that proves the library. The later 24-hour audits run but do not hold the next merge.

## 3. Design

### 3.1 `system/scripts/vaultlib/connector.py`

Lifted from `watchlib/check.py:27-90` (`_strip_cursor`, `too_large`, `query_pages`), `triage.py:36-39` (`Fail`) and `triage.py:145-159` (`_structured`, `_text_json`). Built on `vaultlib/stream.py` (`messages`, `blocks`), which stays.

```python
class Fail(Exception):                       # .code, .reason; every retrofitted module imports this one
def too_large(content) -> bool
def structured(block: dict, message: dict) -> dict      # the result's tool_use_result.structuredContent, else {}
def text_json(block: dict, message: dict) -> dict       # the result's text parsed as one JSON object, else {}
def strip_cursor(i: dict) -> dict                       # the input less its "cursor" key
class Walk(NamedTuple):
    calls: list          # (name, tool_use block) for each call of `tool`, in stream order
    results: list        # (name, tool_result block, user message) for each result of `tool`
    named: bool          # a ToolSearch result held a tool_reference block naming `tool`
    result: dict | None  # the last message of type "result"
def walk(stream: list, tool: str, accept, max_calls: int | None = None) -> Walk
def check_stream(stream: list, tool: str, accept, max_pages: int | None = None, server: str = "",
                 persisted: dict | None = None, take=structured, need_result: bool = True) -> tuple[dict, dict | None]
```

**`accept(input) -> str | None`** names the built call an input runs (a query name, `"search"`, `"read"`, `"create"`), or returns None to refuse it. It may raise `Fail(7, <reason>)` itself where a caller's tests pin a reason. It replaces `query_pages`' `queries` plus `name_of` and triage's `same`. Pages come back as `{name: [payload, ...]}` for every caller; a name with no call is absent.

**`walk`** rules, in stream order:
- A `tool_use` named anything but `ToolSearch`, `tool`, or `StructuredOutput` when the caller passes `structured=True` (only the calendar does; it runs with `--json-schema`), raises `Fail(7, "the session used an unexpected tool: <name>")`.
- A call of `tool` whose `accept` returns None raises `Fail(7, "the session called <tool> with other arguments than the ones built for this run")`.
- A call beyond `max_calls` for its name raises `Fail(7, "the session made <n> <name> calls; the limit is <max_calls>")` at the call, lifted from `rca.py:151` (the only copy that counts calls as they are made). The other copies counted result pages at the end.
- `named` is true only for a `tool_reference` block whose `tool_name` is `tool`, as meetings checks (#38). Free text naming the tool never counts.

**`check_stream`** runs `walk(stream, tool, accept, max_pages)`, then, in the order triage and the watch use:
1. Each result of `tool`: when `too_large(content)`, `persisted` None raises `Fail(6, "a <name> result was too large for the model to read")`, else `persisted[name] += 1` and the payload is still taken (the stream's `structuredContent` holds the whole result). Else an `is_error` result is kept as an error. Else `take(block, message)` joins `pages[name]`.
2. `need_result` and no result message: `Fail(1, "claude produced no result")`. This comes first so a session that never started (a refused flag) is not read as a missing connector.
3. Any error result: `Fail(6, "the connector returned an error: <first 200 characters>")`.
4. No call of `tool`: `Fail(1, "the session never called <tool>")` when `named`, else `Fail(3, "no <server> connector reachable")`. `server` is the display name the suites pin: `Gmail`, `Slack`, `Google Drive`, `Google Calendar`, `Atlassian`.
5. `need_result` and a result with `is_error` or a subtype other than `success`: `Fail(1, "claude returned an error result (<subtype>)")`.

`need_result=False` is for a write session whose tool result proves the write: the RCA filer saves a ticket key a session returned before it was killed (`rca.bats` #122). It skips steps 2 and 5.

**`too_large`** is the union of the watch's and the calendar's tests, over the result's text (a list of blocks joined, stripped):
- it starts with `<persisted-output>`;
- it holds `\n\n[OUTPUT TRUNCATED - exceeded `;
- it does not start with `{` or `[`, and its first 200 characters say `exceeds maximum allowed tokens` (claude's MCP note, "Error: result (N characters) exceeds…", and the "MCP tool response (N tokens) exceeds…" form) or it starts with `Output too large` (`calendar_tsv.py:24`, test_calendar_tsv.py:87-88).

A JSON result text starts with `{` or `[` and holds no raw newline, so mail, chat or event text cannot fake any of the four.

### 3.2 `system/scripts/lib_fetch.sh`

Lifted from `triage_fetch.sh:50-69` and `watch_fetch.sh:57-60` (`logline` with a merged object), `meetings_fetch.sh:71-72` (`fetch_others`), the triage, notify and calendar deny lists (merged into full tables), and the work-directory lines every script carries. Sourced after `lib_connector.sh`; `lib_connector.sh` stays as it is.

The script sets, before calling:

| Variable | Meaning | Example |
|---|---|---|
| `FETCH_NAME` | the stderr prefix | `triage_fetch` |
| `FETCH_TAG` | the alert tag | `triage` |
| `FETCH_LOG` | the month's JSONL log | `system/logs/triage_fetch-2026-10.jsonl` |
| `FETCH_FIELDS` | a JSON object merged into every log line (default `{}`) | `{"items": 0, "source": "mail"}` |
| `FETCH_LABEL` | the alert key's lead | `Inbox triage` |
| `FETCH_ALERTS` | the exits that alert, space-separated | `1 2 3 4 6 7` |

```bash
logline <exit> <reason> [<JSON object>]   # {time, exit, reason} + FETCH_FIELDS + the object, one line to FETCH_LOG
alert_once <key> <text>                   # "- HH:MM:SS [FETCH_TAG] <key> <text>", at most once a day per key
fetch_reason <exit> <reason>              # FETCH_REASON = "<connector class>: <reason>" (connector_classify; no class, no prefix)
fail <exit> <reason>                      # fetch_reason; logline; alert_once "<FETCH_LABEL> failed (exit N):" when N is in
                                          # FETCH_ALERTS; "<FETCH_NAME>: <reason>" to stderr; exit N
skip <reason> [<JSON object>]             # logline 0 "skipped: <reason>"; exit 0
fetch_check_arg "$@"                      # check=0 for no argument, 1 for --check, else "usage: <FETCH_NAME>.sh [--check]", exit 2
fetch_workdir                             # work = a new directory under /tmp, removed by an EXIT trap
fetch_others <server tools...>            # CONNECTOR_OTHERS = each listed name whose CONNECTOR_PREFIX__name is not CONNECTOR_TOOL
GMAIL_TOOLS=(…) SLACK_TOOLS=(…) DRIVE_TOOLS=(…) CALENDAR_TOOLS=(…)   # each server's full tool list, the allowed tool included
```

`FETCH_FIELDS` keeps failure lines identical: today's `fail` writes `items: 0` (triage), `events: 0` (notify), `lines: 0` (handoffs), `count: 0` (watch) and the fixed `source` or `note`, and those defaults move into it. Per-line counts go in the object argument and override it.

Kept in their scripts, built on these functions:
- the watch's `failed` (logs, alerts and keeps the first failing exit without exiting; `fetch_reason`, `logline`, `alert_once`);
- the meetings session's alert rule (3, 6, 7 per session; 1 once on the search);
- the calendar's `finish` (its own log shape, written on success too; `fetch_reason` and `fetch_workdir` only) and its exit-7 alert, which is not once a day;
- the argument parsers that take more than `--check` (triage `--source`, the watch `--inbound-since`, the calendar's date).

### 3.3 `system/scripts/vaultlib/state.py`

Lifted from `watchlib/common.py:31-60`. Notify's `_load` and `commit` (`notify.py:73-85`) and triage's `records` and `_append` (`triage.py:47-70`) do the same with small differences that no reader depends on (a trailing newline, the temporary file's name, key order in a JSONL line).

```python
def load(path: Path, default)                 # the parsed JSON, or default when missing or unreadable
def save(path: Path, data) -> None            # indent=1, sort_keys, written to a temporary file then os.replace
def append(path: Path, record: dict) -> None  # one JSON line, parents created
def records(*paths: Path) -> list             # every JSON object line of each existing path, in order; bad lines skipped
```

### 3.4 Test doubles

**`system/tests/stub_claude_connector`**, the union of the three connector stubs, dispatching on `--allowedTools`:
1. `mcp list`: touches `STUB_MCP_PROBE` when set, exits 1 when `STUB_MCP_FAIL=1`, prints `STUB_MCP_LIST` (default: the Google Calendar line `stub_claude_calendar` prints).
2. A session whose allowed tool is the Slack search, the Gmail thread search or the Calendar `list_events` has a kind (`SLACK`, `MAIL`, `CAL`). With `STUB_<KIND>_STREAM` set, it writes its argv to `STUB_<KIND>_ARGS`, prints that stream and exits `STUB_RC`.
3. Else, with `STUB_STREAMS` set (the meetings mode), it appends its argv and `--end--` to `STUB_ARGS` and its directory to `STUB_CWD`, prints `STUB_STREAMS/read-<id>.jsonl` when the prompt names `fileId "<id>"`, else `STUB_STREAMS/search.jsonl`, and exits `STUB_RC`.
4. Else (the calendar mode): argv to `STUB_ARGS`, directory to `STUB_CWD`, `FOUNDRY_HEADLESS` to `STUB_ENV`, stdin's target to `STUB_STDIN`, sleeps `STUB_SLEEP`, prints `STUB_STREAM`, moves `STUB_STREAM.next` over it when present, exits `STUB_RC`.

Suite changes: `watch.bats` renames `STUB_ARGS_<KIND>` to `STUB_<KIND>_ARGS` and sets `STUB_STREAM` to a one-line empty success result in its setup (the watch stub's default); `meetings.bats` and `handoffs.bats` set `STUB_MCP_LIST` where they relied on the meetings stub's Drive default; triage's `STUB_SLACK_ARGS` keeps its name.

**`stream()` in `system/tests/python/helpers.py`**, lifted from `test_watch_check.py:28` and `test_triage.py:22`:

```python
def call(input: dict = None, text: str = "…", sc: dict = None, error: bool = False) -> dict
def stream(tool: str, calls=(), reply: str = None, result: str = "success", named: bool = True, **result_fields) -> list
```
A ToolSearch call whose result names `tool` in a `tool_reference` block (when `named`); then per call a `tool_use` (`id` `t1`, `t2`, …) and its `tool_result` (`text` as content, `sc` as `tool_use_result.structuredContent`, `is_error`); then the result message (`result` text `reply`, default `{"items": []}`, `is_error` when the subtype is not `success`, plus `result_fields`). Each retrofit turns its suite's builder into a wrapper over it. The calendar suite keeps its own builder (an init message, calls with no results, `structured_output`), with `tool_use` ids added so results pair with calls.

### 3.5 What each walker needs, and what absorbs it

| Walker | Session | Input check (`accept`) | Pages | Too large | Error result | Result message | Uses |
|---|---|---|---|---|---|---|---|
| Triage mail | read | `query` equal; `view` `THREAD_VIEW_MINIMAL` (new, as the watch) | 3 → 6 (§3.6.1) | not detected → counted, hold | 6 | required | `check_stream` |
| Triage chat | read | the input less `cursor` equal | 5 | failed as a bad shape (1) → 6 | 6 | required | `check_stream`, `take=text_json` |
| Meetings search | read | any | no limit | not detected → 6 | 6 | required | `check_stream` |
| Meetings read | read | `fileId` equal, own reason (was checked after the walk) | no limit | not detected → counted and ignored | 6 | required | `check_stream` |
| Watch Slack | read | the built query less `cursor` | 5 per query | 6 | 6 | required | `check_stream`, `take=text_json` |
| Watch mail | read | `query` by name, `view` minimal | 6 per query | counted, hold | 6 | required | `check_stream` |
| Notify | write | channel, keys, `thread_ts`, text length; own reasons | none | not checked | tolerated when another post landed | not needed when a post landed | `walk` |
| Calendar | `--json-schema` | any | the model pages | own reason (names `pageSize`) | the model's `status` | required | `walk`, `too_large` |
| Handoffs | read | `jql` and `cloudId` equal, own reason | no limit | not detected → 6 | 6 | required | `check_stream` |
| RCA filer | write | the arguments exactly, own reason | 1 call | not detected → 6 | 6 | not required | `check_stream(need_result=False)` |

Every walker accepts ToolSearch and its one connector tool; the calendar also accepts `StructuredOutput`. Exit codes other than 1, 3, 6 and 7 belong to the callers and do not change: 2 (usage and settings), 4 (timeout, set by `connector_outcome`, or a busy lock), 5 and 8 (the calendar's list rules; notify's hold and the RCA filer's unresolved marker are 5 too), 127 (no claude).

Why notify and the calendar stop at `walk`:
- **Notify** posts. A post that reached the channel counts as sent even when another call errored or the result is missing, so a good post is never repeated; it raises `Fail 4` on the usage-limit text and names the Slack server the session did load (#133). `check_stream`'s fail-on-any-error would re-send a landed post.
- **The calendar** takes its events from the model's `structured_output`, reports connector errors through the model's `status`, and logs every unexpected tool in `summary.unexpected_tools` (calendar.bats:193). It keeps its summary pass and its end rules; `walk` adds the guard.

### 3.6 Retrofits

Each retrofit is one PR (Part of the F1 issue), merged by the owner. It keeps identical: the script's documented exit codes, every log line's keys, every alert key, the `--check` output lines and every reason a test pins. Its changes are listed below and nothing else; the suites are the proof. Each removes its entries from the `conformance.bats` allowlist (F0).

**1. Inbox and chat triage** (`triage.py`, `triage_fetch.sh`, `triage.bats`, `test_triage.py`, `FOUNDRY.md`, `CHANGELOG.md`).
- `pages` → `check_stream`; `Fail`, `_structured`, `_text_json` come from `connector` (one re-export line keeps `vaultlib.triage.Fail`, `_structured` and `_text_json` importable for `watchlib` until the watch retrofit); `records` and `_append` on `state`; the script on `lib_fetch.sh` with `GMAIL_TOOLS` and `SLACK_TOOLS`.
- Mail pages (§3.6.1), the too-large hold, per-search counts in the log line (§3.6.2).
- Chat: a too-large page exits 6 (was 1, "not in the shape asked for").
- A call past the limit exits 7 at the call (was counted at the end, after the error check).

**2. Meetings fetch** (`meetings_extract.py`, `meetings_fetch.sh`, `meetings.bats`). `results` and `names_drive` → `check_stream`; the read's `fileId` check moves into `accept` with its reason ("the session read a Doc that was not requested: <id>"), so it fails at the call. A read whose result was too large for the model is counted and still written: the checker reads `structuredContent`, and the model only replies "done". A search page too large exits 6 (new: the model could not see its `nextPageToken`). The script on `lib_fetch.sh` (`fetch_check_arg`, `DRIVE_TOOLS`, `fetch_others`).

**3. Intraday watch** (`watchlib/check.py`, `watchlib/common.py`, `watch_fetch.sh`, the watch suites). `too_large`, `_strip_cursor` and `query_pages` leave `check.py`; `slack_extract` and `mail_extract` call `check_stream` with the same `take`, limits and `persisted`. `common.py` re-exports `Fail` from `connector` and `load`, `save`, `append`, `records` from `state`. The triage re-export line goes. The script on `lib_fetch.sh`; `failed` keeps its no-exit rule on `fetch_reason`. No intended change beyond the call-time limit.

**4. Notify** (`notify.py`, `notify.sh`, `notify.bats`, `test_notify.py`). `check`'s loop → `walk` with an `accept` that raises its two reasons (another channel, thread or argument; text nobody collected); its end rules stay. `_load` and `commit` on `state`. The script on `lib_fetch.sh` (`FETCH_ALERTS` `1 2 3 4 5 6 7 127`). No intended change.

**5. Calendar** (`calendar_tsv.py`, `calendar_fetch.sh`, `calendar.bats`, `test_calendar_tsv.py`). `Fail`, `OVERFLOW`, `overflowed` and `parse_stream` go (`stream.messages` reads the input; output that is not stream-json still exits 1). `walk` raises the exit 7 (the reason names the first unexpected tool; `summary.unexpected_tools` still lists all of them); `too_large` over `walk`'s results raises its exit 6 with today's reason. One rule is new (C4): a status `ok` from a session that never called `list_events` exits 1, or 3 when the tool was never found, instead of passing an empty day.

**6. Handoffs** (`jira_handoffs.py`, `jira_fetch.sh`, `handoffs.bats`, `test_handoffs_jira.py`). `pages` → `check_stream` (`server="Atlassian"`, `accept` with today's reason). A too-large page exits 6 (new; it read as a partial list or exit 1). The script on `lib_fetch.sh` with its own full Atlassian table (§2 decision 7).

**7. RCA filer** (`telemetrylib/rca.py`, `rca_file.sh`, `rca.bats`, `test_rca.py`). `extract`'s loop → `check_stream(max_pages=1, need_result=False)` with today's argument reason; `_find_key` reads the one page. `called` reads the stream as today. `rejected_create` reads `walk(stream, TOOL, lambda i: "create")` and returns None when `walk` raises, so a session that used another tool is never read as a clean rejection (before, it could be, and its draft was handed back). A second create call exits 7 even when the first errored (was 6 or 7 by order). The script on `lib_fetch.sh` (`FETCH_LABEL` `Filing <stem>`) with its Atlassian table.

#### 3.6.1 Triage mail pages

As #297 did for the watch: `pageSize 10`, `view THREAD_VIEW_MINIMAL`, follow `nextPageToken` until none is left or the search has had 6 calls (`MAX_PAGES = 6`, the watch's `MAIL_PAGES`), so a tick reads at most 60 threads (was 150 in 3 pages of 50). The watch's 16-hour replay returned 50 threads for a wider search (all incoming mail less promotions), so 60 covers an overnight window. A search whose last page read still has a `nextPageToken` is full, at its limit or before it, and keeps today's alert with the new number (`Inbox triage read 6 full pages:`). Turns rise from 12 to 16 (3 ToolSearch calls, 6 searches, the reply, room for one retry). `TRIAGE_TIMEOUT` stays 300 s, so `foundry-triage.service` (20 minutes) and the smoke check's 360 s still fit; the watch's mail session runs 12 pages of 10 in 480 s. The live `--check` measures it.

**Hold.** A mail page the model saw only as too large is counted (`persisted`). `extract` returns `hold: true`; `record` writes the items it has and a tick record with `"hold": true`, which `cursor` skips, so the next tick reads the window again. The ledger keys items by thread and date, so a re-read adds no second line. One alert a day: `[triage] Inbox triage returned a page too large for the model to read: its cursor stays, so the next tick reads it again`. Known ceiling: a page that is always too large holds the cursor until the owner acts on the alert.

#### 3.6.2 Triage counts in the log

`extract` and `chat_extract` return `stats`: `results` (threads, or chat messages, the search returned), `rows` (the reply's items), `kept`, `persisted`, and `dropped` by reason (`unknown`, `empty`, `duplicate`). The tick's log line carries them: `logline 0 "" '{"items": N, "stats": {…}}'`. Counts only, never mail or chat text. `--check` prints the threads returned next to the count that need the owner.

### 3.7 The ratchet

F0's copy ratchet (F0 spec §3.5) finds, in `system/scripts` and `extensions/*/scripts`, Python files that read `"tool_result"` or `tool_use_id` themselves, top-level `logline()`, `alert_once()`, `fail()` and `skip()`, `class Fail` and `def config(`, and extension imports of a private `vaultlib` name. It fails on a hit not in its allowlist and on an allowlisted entry that no longer exists, so each PR must shrink the list exactly.

- **The library PR** adds the parts' homes as the allowed definitions (`vaultlib/connector.py` for the walker and `Fail`, `lib_fetch.sh` for the shell helpers) and removes `smoke_check.sh`'s `alert_once`. F0's ratchet (its §3.5, the authority for the allowlist and its entry format) already covers test doubles: the library PR removes the three connector stubs' entries and adds `stub_claude_connector` as the home; `stub_claude` and `stub_claude_nightshift` are listed by F0 as other shapes. Each suite's own `stream(` builder, the calendar suite's included (`test_calendar_tsv.py:19`), moves to `helpers.stream` in its source's retrofit and leaves the list then.
- **Each retrofit** removes its own entries in the same PR. The RCA filer's `rejected_create` reads tool results too, so its retrofit moves it onto `walk` (§3.6, item 7).
- **`vaultlib/nightshift_session.py`** (F0 left the call to F1) does not share the walker: it reads a Work Order session with many allowed tools, no input check and no single connector, for its usage, init and result. It stays on the allowlist as a different shape, with that reason beside the entry.
- `config()` copies stay listed (§6).

The F1 extension retrofits import `vaultlib.connector` and `vaultlib.state` directly; these are public names, so the private-import rule does not fire, and F2's `vaultlib/api.py` re-exports them.

### 3.8 Core budget

`vault_integrity.bats:409-432` caps `system/scripts` at 13,950 lines. Measured in this worktree at master `1ca9198`: **13,912**.

| Change | Core lines (estimate) |
|---|---|
| `connector.py` (from the watch, an extension) | +115 |
| `lib_fetch.sh` (helpers and four tool tables) | +65 |
| `state.py` (from the watch) | +35 |
| `smoke_check.sh` on `lib_fetch.sh` | −2 |
| Triage (walker, `Fail`, ledger, shell helpers and lists; plus paging, hold and counts) | −80 |
| Meetings (walker, `names_drive`, `Fail`, shell helpers and Drive list) | −57 |
| Notify (guard loop, `Fail`, state, shell helpers and Slack list) | −54 |
| Calendar (`Fail`, `OVERFLOW`, `overflowed`, `parse_stream`; plus the new rule) | −32 |
| Watch, handoffs, RCA filer | 0 (extensions) |

The library PR takes core to about **14,125**, over the cap, before any copy is removed. The four core retrofits bring it back to about **13,900** (net about −10, ±40). Each PR measures its count; the budget test's comment states the value the cap returns to.

### 3.9 Live acceptance

After each retrofit merges and the server updates (the 05:30 update, or `update_template.sh` by hand):
1. **`--check` on the server** for the source, run by the live vault's own session with the owner's OK (as the #289 replays were; this repository's sessions only read the live vault): `system/scripts/triage_fetch.sh --check` (mail and chat), `system/scripts/meetings_fetch.sh --check`, `extensions/intraday/scripts/watch_fetch.sh --check`, `system/scripts/notify.sh --check` (posts one test message; the owner runs it), `system/scripts/calendar_fetch.sh --check`, `extensions/handoffs/scripts/jira_fetch.sh --check`. The RCA filer has no `--check`; its acceptance is the audit alone.
2. **A read-only log audit 24 hours later** of that source's `system/logs/<script>-<YYYY-MM>.jsonl` and the alerts files: ticks at the expected rate, every failure line explained, no new alert key. For triage, every mail tick line carries `stats`, and a tick with `results` above 0 and `kept` 0 is compared with the inbox by hand. For the RCA filer, a day with no filing proves nothing (no instrument ran) and the audit waits for the next filing.

The result goes on the F1 issue as counts, with no mail, chat or ticket text.

## 4. Tests and validation

- **pytest:** `system/tests/python/test_connector.py` and `test_state.py`, ported from `test_watch_check.py` (too large, other queries, page limits, the session rules), `test_triage.py` (cursor pages, no connector), `test_calendar_tsv.py` (the two overflow forms, event text quoting the limit), meetings' #38 case and `test_rca.py` (one call, exact arguments). Each retrofit keeps its suite and adds the tests of its listed changes.
- **bats:** `connector.bats` gains the `lib_fetch.sh` functions and the stub's dispatch. Every connector suite runs on `stub_claude_connector`.
- **Ratchet:** `conformance.bats` passes after every PR, with a shorter allowlist each time.
- **Budget:** `vault_integrity.bats` at each PR's measured count.
- **Gate:** CI's `gate`, with every extension off and with every extension on.

**Done when:** the allowlist holds no walker (but `nightshift_session.py`), `class Fail`, `logline`, `alert_once`, `fail` or `skip` entry outside the parts' homes, no connector stub but `stub_claude_connector` and no pytest `stream()` builder but `helpers.stream`; each retrofitted source passed its live `--check` and audit; core is at or under 13,950 lines, or the owner set a new cap from the measurement.

## 5. Risks

1. **One bug in a shared part breaks every source on it.** The library is unused until a retrofit adopts it, each retrofit is one revert, and the order puts a 30-minute source first, so its live audit sees many runs before the once-a-day sources move.
2. **Pinned reasons drift.** The brief, the smoke check and `sources.py` match reason text ("no Gmail connector reachable", "auth: …"). The library emits today's texts; `accept` raises the callers' own where tests pin them.
3. **Write sessions on the read rules.** Notify stays on `walk`; the RCA filer runs with `need_result=False`. Tests pin both paths (a landed post beside an errored one; a create with no result message).
4. **Triage paging is unmeasured live.** 6 pages in 300 s and 16 turns rest on the watch's numbers. The live `--check` and F0's timing ratchet check it; a timeout shows as exit 4 in the audit.
5. **The track-S trigger cannot fire from triage's log.** The program moves the page fix to the safety track if the live logs show a tick with many threads and no rows, but triage logs no thread counts. The watch's `inbound` stats on the same mailbox are the available instrument; without them, the fix ships as retrofit 1.
6. **The interim budget overshoot** needs the owner's temporary raise (§7).

## 6. Out of scope

- F2 (core manifests, extension tags out of core, `vaultlib/api.py`), F3 (conformance rules, timing budget), F4 (skills).
- `config()` (6 copies) and the ToolSearch prompt preamble (9 copies): F2's API and F4's scaffold.
- Python alert-once writers (`watchlib.common.alert`, telemetry's): one caller each among the F1 sources.
- A shared Atlassian tool table (§2 decision 7) and telemetry, the HTTP-poller shape.

## 7. Decisions for the owner

**Decided (owner, 2026-10-21):** 1 raise the cap to the library PR's measured count, lowering with each core retrofit; 2 take the calendar rule; 3 take the 60-thread cap; 4 **B**, triage's page fix ships inside retrofit 1.


1. **Temporary core budget raise.** The library PR takes core to about 14,125 of 13,950 lines. Recommendation: set the cap to the library PR's measured count, lower it to each core retrofit's measured count, and end at or under 13,950 after the calendar retrofit.
2. **Calendar's new C4 rule** (an `ok` with no `list_events` call fails). Recommendation: take it; an empty day from a session that never read the calendar is a silent failure today.
3. **Triage's 60-thread cap** (was 150). Recommendation: take it; a full search still alerts, and the replay's 50 threads fit.
4. **When triage's page fix ships.** Triage asks for pages of 50 with no too-large check, the setup that lost mail in #289; its log has no thread counts, so the live loss can't be confirmed (two catch-up ticks after gaps kept 0 rows). Option A: ship pages of 10, the too-large hold and the counts as one PR on today's `triage.pages()` before the library, then retrofit 1 moves it onto the library. Option B: ship them inside retrofit 1. Recommendation: A, because it is a possible live data loss and the factory work ahead of retrofit 1 (F0, the library PR) would hold it back.
