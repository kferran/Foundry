# Connector runner: one file runs every confined connector session

**Date:** 2026-10-13
**Status:** Approved for build (feature lane: it moves the confined-session code).
**Issue:** Part of #122 (step 2, the connector runner only; grill decisions 2026-10-13).

## 1. Problem

Six scripts drive a confined `claude -p` session against one connector tool: `calendar_fetch.sh`, `meetings_fetch.sh`, `jira_fetch.sh`, `triage_fetch.sh`, `notify.sh` and `rca_file.sh`. Each repeats the same block: find `claude`, `confine_settings`, `confine_deny`, a fresh session directory, `timeout -k 10`, `FOUNDRY_HEADLESS=1`, `--settings … --disable-slash-commands --no-session-persistence --permission-mode dontAsk --output-format stream-json --verbose --max-budget-usd 1 --allowedTools … --disallowedTools …`, then the mapping of the session's exit and the checker's exit to one code and reason. A `claude` flag change (the 2026-10-11 review's "fragile coupling to Claude Code CLI flags") is six edits, and the six blocks already disagree in small ways: calendar confines without `--strict`, and notify and rca treat a timed-out session whose checker passed as success while the four fetches report a timeout.

## 2. Decisions

- **One library, `system/scripts/lib_connector.sh`, two functions.** `connector_run <prompt> <work dir>` confines and runs the session; `connector_outcome <checker exit> <work dir>` maps the session's exit and the checker's exit (its stderr at `<work dir>/check.err`) to the final code and reason. The checker call stays in the caller: its arguments differ per script. Every `claude` flag a connector session gets is in this file.
- **Inputs are variables, set before the call:** `CONNECTOR_SERVER` (the connector's name in `claude mcp list`), `CONNECTOR_PREFIX`, `CONNECTOR_TOOL`, `CONNECTOR_OTHERS` (the server's other tools, bare names), `CONNECTOR_TIMEOUT` (seconds; each script keeps its `<NAME>_TIMEOUT` override as the default), `CONNECTOR_TURNS` (`--max-turns`) and, for calendar only, `CONNECTOR_SCHEMA` (a `--json-schema` file). A caller that runs several sessions (meetings) sets them once and calls `connector_run` per session; `confine_settings` runs once per process (`connector_run` skips it when `CONFINE_SETTINGS` is set), as `meetings_fetch.sh` does today.
- **The session directory is a fresh `mktemp -d` under the work directory**, removed after the call (each of a run's sessions gets its own, as `meetings.bats` checks). It is under `/tmp` because the work directory is, and the caller's existing `rm -rf "$work"` trap covers a unit stopped mid-session (#40), so the callers drop their `sdir` bookkeeping.
- **One outcome rule for all six.** The checker's verdict wins: its exit 0 is success whatever the session's exit (the checker saw the whole result, or the post or ticket it confirms exists), and its exit 7 (an unexpected tool) stands. Another checker failure after a session exit of 124 or 137 is 4, "timed out after Ns"; after any other non-zero session exit it keeps the checker's code and appends "; claude exited N: <first 200 bytes of stderr>" to the reason, so a `claude` that refuses a flag no longer reads as "no connector". The four fetches change in one case: a session that timed out or exited non-zero after its checker had everything it needed now succeeds, as notify and rca already do.
- **Every connector confines with `--strict`.** Calendar did not. A vault whose settings allow the whole Calendar server (`mcp__claude_ai_Google_Calendar`) then fails closed with the rule to narrow, as every other connector has since inbox triage. Owner's call to confirm, since the live vault's settings are not readable from here; the recommendation is strict, and the change back is one argument.
- **Out of the runner:** the usage hold (triage and meetings call `triage.py hold` before the session; the brief's fetches, notices and approved filing never hold), each script's `logline`, `alert_once`, lock and `--check` handling, and the checker. The grill dropped the wider helper layer.

## 3. Changes

- Create `system/scripts/lib_connector.sh` (sources nothing; callers source `lib_confine.sh` as now, or the library sources it). `connector_run` returns 127 when `claude` is not found and 1 when `confine_deny` refuses a rule, with the text in `CONNECTOR_REASON`; otherwise it runs the session, leaves `<work>/out.jsonl` and `<work>/claude.err`, sets `CONNECTOR_RC` to the session's exit and returns 0. `connector_outcome` sets `CONNECTOR_EXIT` and `CONNECTOR_REASON` (the checker's first stderr line with its `<name>: ` prefix removed).
- The six scripts: delete their inline block and call the two functions. `calendar_fetch.sh` passes `CONNECTOR_SCHEMA`. Exit codes, log lines, alerts and `--check` output are unchanged.
- `FOUNDRY.md`: the Headless isolation paragraph says `run_headless.sh` "is the only way automation calls `claude`", which the connector fetches made stale; it now names `lib_connector.sh` as the second way (one connector tool, dontAsk, every other tool denied). Development's acceptance paragraph adds: after a `claude` version change, one `calendar_fetch.sh` run proves the connector flags.

**Existing vault:** no config, unit or schema change. A vault whose settings allow the whole Calendar server gets calendar exit 1 with the rule to narrow (the strict decision above).

## 4. Tests

- bats (`connector.bats`, with `stub_claude_calendar`): `connector_run` passes the prompt first and `--allowedTools`/`--disallowedTools` last, `--permission-mode dontAsk`, `--output-format stream-json`, `--max-turns $CONNECTOR_TURNS`, `--json-schema` only when `CONNECTOR_SCHEMA` is set, `FOUNDRY_HEADLESS=1`, a cwd under `<work>` that is gone after the call, and stdin from `/dev/null`; it returns 127 with no `claude` and 1 with a refused rule, running nothing; two calls in one process run `claude mcp list` once and use two session directories. `connector_outcome` (checker exit, session exit): (0, 0) → 0; (0, 2) → 0; (0, 124) → 0; (7, 124) → 7; (6, 124) → 4 "timed out"; (3, 0) → 3 with the checker's prefix stripped; (3, 2) → 3 with "; claude exited 2: …" appended.
- bats (`scripts.bats`): `--permission-mode` and `--disallowedTools` appear under `system/scripts/*.sh` only in `lib_connector.sh` and `run_headless.sh`, so a seventh connector cannot inline the block.
- The six existing suites (`calendar`, `meetings`, `handoffs`, `triage`, `notify`, `rca`) pass unchanged; `calendar.bats` gains the strict case (a rule allowing the whole server is refused, exit 1).
- Against a real `claude`: one `calendar_fetch.sh <today>` from a throwaway clone under `.scratch/` (read-only; what the brief runs anyway). The stubs accept any argv, so this is the only check that the flag list is one `claude` accepts. Live acceptance proper (brief, debrief, ingest) is not triggered: `run_headless.sh`, the settings files and the three commands are untouched.

Each fails before the change. Bound tools: bats, the gate, the one real calendar fetch.

## 5. Out of scope

- The helper layer the grill dropped (one config reader, one alert writer, one lock across bash and Python).
- The Work Order and `run_headless.sh` flags: they stay where they are.
- The smoke check (`2026-10-11-smoke-check-design.md`): built on this runner next, on its own timer at `brief_time` minus 15 minutes (grill decision 2026-10-13, which closes that spec's §2 open question).
- A shared tool-use check in `stream.py`: each checker keeps its own.
