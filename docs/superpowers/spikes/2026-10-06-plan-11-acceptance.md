# Plan 11 acceptance

**Date:** 2026-10-06 · **Branch:** `feat/plan-11` · **Commit:** d76e98f (run 2) · **Debian host:** Debian 12 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2, Claude Code 2.1.291. Executed natively on the Debian host. The host name is kept out of this record (template rule). The record holds exits, counts and stream shapes only, never meeting content, titles, names or Doc IDs (spec §7).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Debian host | 1022532 (Tasks 1–8) | 0 | 17/17 PASS | lint 0 errors, 4 warnings (older than this plan) |
| Debian host | 16931e5 (final-review fix pass) | 0 | 17/17 PASS | lint 0 errors, 4 warnings |
| Debian host | d76e98f (acceptance fixes) | 0 | 17/17 PASS | lint 0 errors, 4 warnings |

## Setup

Throwaway clones under `.scratch/foundry-accept/` in the dev repo (a server clone, a client clone and a local bare origin), each with `system/config.md` from the example and `core.hooksPath .githooks`; the server clone with `machine_role: server`, `meetings_enabled: true`, `meetings_partition: work`, `commit_runs.py --init-cutover` (exit 0) and `.since` three hours back (a 27-hour window). No units were installed. One script ran Steps 1–5 outside the sandbox (`claude` needs the network). The fetch ran through a `claude` wrapper that kept only the key and tool names of each stream.

## Run 1 (commit 16931e5): FAIL

| Step | Result |
|---|---|
| 2 fetch | exit 0; search exit 0; 10 reads exit 0 but 7 Docs: 3 Docs were read twice (the listing held repeats) |
| 2 import, commit, push | exit 0; 7 meeting runs `published`, 2 targets each; `meeting(work): …` commits; push 0 |
| 2 meeting notes | every note: 0 sections, 0 action items, 0 transcript turns, `complete: false`; attendees parsed |
| 2 compile | 7 solo ingests, exit 0, every one `noop`; 0 concepts cite a meeting note |
| 2b no connector | exit 3; log line `{"step":"search","exit":3}`; the session listed no MCP server |
| 3 client drop | pull, commit (hook accepted), push, pull, import all 0; drop folder empty; 2 notes (meeting and transcript) |
| 4 brief | `brief_prep.sh` 0; `actions.md` held only Notices (7, the `complete: false` imports); `run_headless.sh brief` 0 |
| 5 tick | skipped: no action parsed |

**Cause** (a follow-up probe fetched the same window without importing; structure read with every word masked): real Gemini Docs wrap every heading's text in bold (`### **Summary**`, `## **<title> - Transcript**`, `### **HH:MM:SS**`, `### **Transcription ended after HH:MM:SS**`), group Decisions under level-2 topic headings (`## **Topic**`), and indent action lines with escaped brackets (`  - \[Owner\] Title: text`). The synthetic fixtures had plain headings (Review Focus 2). The repeats came from the search session calling `search_files` three times (with `pageToken` and with `excludeContentSnippets`). The plan's shape filter bound `A | B, C` as `A | (B, C)` and recorded only `system` events.

**Fixed**, each test-first: bad13f9 (headings drop surrounding `**`; a topic heading inside a section stays in it as a bold line), 9f0fe5c (the listing keeps one entry per Doc), d76e98f (the plan's shape filter parenthesized).

## Run 2 (commit d76e98f): PASS

| Step (spec §7) | Result |
|---|---|
| 2 fetch | exit 0; search exit 0 (2 `search_files` calls); 10 reads exit 0, 10 distinct Docs |
| 2 parse (counts) | summary 10/10, details 10/10, decisions 7/10 (the 3 without have no Decisions heading), 3–12 action items each (80 in all, 1 owner a single first name), transcript turns in 7 Docs (26–471 turns, 4–45 headings); 2 Docs had no transcript in the read text (`complete: false`) and 1 had an empty transcript |
| 2 title zones (finding I6) | 8 `MDT`, 2 `CDT`; the config zone reads `MDT`. Two Docs carry another zone and get a start an hour off: tracked in #42 |
| 2 import, commit, push (item 1) | exit 0; 10 meeting runs, `published`, 2 targets each, partition `work`; `meeting(work): …` subjects; push 0 |
| 2 compile (item 1) | 3 intake ticks, every input taken; 11 ingest runs: 10 `published` (1–5 targets each), 1 `rejected` (exit 5: "conflict: target modified in the last 60 s" on a concept the previous meeting's ingest had just written), taken again on the next tick; **24 concepts cite a meeting note in `sources`** |
| 2 lint | exit 0; 0 errors, 14 warnings: the 4 older ones, 3 "no other note links here", 7 "ambiguous link" (see Findings) |
| 2b no connector | exit 3; `{"step":"search","exit":3}`; the session listed no MCP server |
| 3 client drop (item 2) | pull 0, commit 0 (hook accepted), push 0, pull 0, import 0; the drop folder lists nothing; 2 notes; push 0 |
| 4 brief (item 3) | `owner_names` set to the user's full name; `brief_prep.sh` 0; `actions.md`: Yours 0, Waiting on 80 lines, Notices 2; `run_headless.sh brief` 0, the briefing has a "Waiting on" block. The user owns no action in these 10 meetings, so "the user's first" is shown by the pytest cases only |
| 5 tick (item 4) | the user owns no action, so another owner's open action was ticked on the client, committed (hook 0) and pushed, and the server pulled: Waiting on 80 → 79 (`meeting_actions.py`, local) |

### Stream shapes (run 2, counts)

```
11 {"block":"tool_use","tool":"ToolSearch","input":["max_results","query"]}
10 {"block":"tool_use","tool":"mcp__claude_ai_Google_Drive__read_file_content","input":["fileId"]}
 1 {"block":"tool_use","tool":"mcp__claude_ai_Google_Drive__search_files","input":["excludeContentSnippets","query"]}
 1 {"block":"tool_use","tool":"mcp__claude_ai_Google_Drive__search_files","input":["query"]}
10 {"result":["content","structuredContent"],"structured":["fileContent","title","viewUrl"]}
 2 {"result":["content","structuredContent"],"structured":["files"]}
11 {"result":["matches","query","total_deferred_tools"],"structured":[]}
11 {"tool_result_block":"tool_reference","keys":["tool_name","type"]}
11 {"mcp_servers":["claude.ai Slack","claude.ai Google Drive"]}   6 {"mcp_servers":[]}
```

Against D12: the text sits in `tool_use_result.structuredContent` (`fileContent` for a read, `files` and `nextPageToken` for a search), each read call's input is `fileId`, and a `ToolSearch` result names the Drive tool in a `tool_reference` block with `tool_name` (the shape the no-connector rule counts; #38's echo case did not occur). A session's `init` event can list no MCP server while the connector loads later. A connector error (exit 6) stays unconfirmed: no safe way to provoke one.

## Findings for issues

- A rejected ingest leaves its staged copy in `system/quarantine/<run_id>/staged/wiki/…`, and link resolution counts it, so every link to that note is "ambiguous" until the quarantine is cleared (older than this plan; seen here because two meetings touched one concept within 60 seconds).
- 2 of 10 real Docs had no transcript in `read_file_content`'s text (`complete: false`, listed under Notices as designed); whether the transcript sits in another Docs tab or the text was cut is not known.

## Verdict

**PASS** on run 2 for spec §7 items 1–4, with item 3 ("the user's first") and item 4 shown on another owner's action because the user owned none in the window. Run 1 found that the parser did not read real Docs; that was fixed test-first and re-run.
