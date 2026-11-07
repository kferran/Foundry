# Plan 8d outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-04 (plan: `2026-10-04-plan-8d-calendar-connector.md`, commits 9e23922..18f5499 plus this status commit). Executed natively on the Debian host: every task applied the plan's tested patches with red-then-green tests, then one final whole-branch review and one fix wave. Acceptance: `docs/superpowers/spikes/2026-10-04-plan-8d-acceptance.md`.

Final verification at 18f5499: `verify_setup.sh` exit 0 (15/15) on the Debian host (Debian 12.15, jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2); lint 0 errors.

**Next on the roadmap:** Plan 8b (scripted commit history), then 8c (sync).

## Rulings

- Ruling: the plan names base 6d15ab5; the branch was at 9e23922, which adds only the plan doc — cost if wrong: none.
- Ruling: the plan's `verify_on_host.sh <debian-host>` step was replaced by the native gate, since execution ran on the Debian host — cost if wrong: one extra remote run.
- Ruling: the final reviewer ran on Opus, the session model, because the ranking between the available top models was unclear and Opus matches earlier plan reviews — cost if wrong: a weaker review pass.
- Ruling: plan Step 3 (interactive phase 6) was satisfied by live run 1, which ran from an interactive session through the Bash tool with a 300000 ms timeout — cost if wrong: the `/setup` phase 6 wording is pinned by `commands.bats` but was never driven live.
- Ruling: the branch was pushed and the PR opened with the laptop fetch still pending — cost if wrong: a merge before the laptop run; the fail-closed allow-rule check reads the laptop's settings, which no live run has seen since the fix.
- Final: Ruling: an allow rule broader than the calendar server (`mcp__*`, `*`, `mcp__claude_ai_*`) matches `list_events`, so it can't be denied, and spec §4.2 skipped it, which left every other connector's tools allowed in the `dontAsk` session. The fetch now exits 1 before `claude` runs and names the rule to narrow. A per-server deny was rejected: the display-name-to-prefix mapping is unverified and `claude mcp list` does not list every connector. Spec §4.2, §4.5 and §7 were updated; this contradicts the plan's Review Focus #2 expectation — cost if wrong: a user with such a rule must narrow it before the calendar works.
- Final: Ruling: the reviewer's declined-to-judge items stand as is: project and local settings (the working directory is a fresh `/tmp` directory), managed-only permission interplay, the all-day `end_date` convention, exit 2 writing no log line, a stale `calendar.tsv` after a failed re-run (earlier `prep_write` behavior), and non-Linux managed paths — cost if wrong: small; each surfaces in a log or the brief.

## Acceptance notes

- `claude` is on `PATH` only in a login shell on the Debian host; the live runs set `CLAUDE_BIN` to its absolute path. Units already carry the absolute path.
- The laptop fetch was pending when this was written; this session reaches only the server.

## Final-review fixes

- fixed broad allow globs leaving other servers' tools allowed (see the ruling): `calendar.bats` "an allow rule broader than the calendar server stops the fetch before claude runs" RED→GREEN.
- fixed a timed-out session skipping the tool-use check, so an injected tool call followed by a timeout gave exit 4 and no alert: the validator now runs on every session, `parse_stream` skips lines that do not parse (a line cut off by the kill), and an unexpected tool gives exit 7 with the alert. `calendar.bats` "a session that times out is still checked for unexpected tools" and `test_cut_off_stream_still_checks_tools` RED→GREEN.
- fixed a newline or non-ASCII digit passing the time check (`TIME.match` with `$` accepted `"09:00\n"`, which split a TSV row): `fullmatch` and `[0-9]`. `test_invalid_outputs_exit_5` gained two cases, RED→GREEN.

## Deferred minors

- `claude.err` is not reported when `claude` exits non-zero with an empty stream (for example, logged out); the reason reads "claude produced no result".
- The `tool_error` reason is model text that reaches `unavailable.md` without the control-character scrub titles get (one line only).
- Unexpected tool names are not scrubbed in the alert, and `server_tool_use`/`mcp_tool_use` blocks are not checked.
- `brief_prep.sh`'s exit-7 line says the session "used" an unexpected tool; "attempted" is more accurate.
- The `/tmp` working directory lets another local user plant `/tmp/CLAUDE.md` (a misleading list at worst; the tool confinement holds); spec §4.1's comment overstates the isolation.
- An unreadable managed settings file reports "cannot parse".
- The `too_many` prompt line omits "events empty".
- Lines that are JSON but not objects crashed the parser; the timeout fix now skips them, with no dedicated test.
