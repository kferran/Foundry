# Alert tags: one registry, a severity per tag, a Foreman push

**Date:** 2026-10-14
**Status:** Built (2026-10-15): PR #213.
**Issue:** #158. Owner's outcomes (2026-10-14): urgent pushes reach the owner now and the rest waits for the brief; the tag says at a glance which part raised the alert; the Foreman can push a line to the owner on its own.

## 1. Problem

Every alert is one line, `- HH:MM:SS [tag] text`, appended to `system/logs/alerts_<date>.md` by thirteen writers: `run_headless.sh` (`[intake]`), `intake.py` (`[intake]`), `update_template.sh` (`[update]`), `vault_sync.sh` (`[sync]`), `commit_runs.py` (`[commit_runs]`), `telemetry_run.py` (`[telemetry]`), `clearinghouse_run.py` (`[clearinghouse]`), `nightshift_run.py` (`[orders]`), `lib_memory.sh` (`[memory]`), and the `alert_once` helpers in `calendar_fetch.sh`, `meetings_fetch.sh`, `jira_fetch.sh` (`[handoffs]`), `triage_fetch.sh`, `rca_file.sh`, `notify.sh`, `smoke_check.sh`. Nothing lists the tags; a new script picks one. Three once-a-day mechanisms exist (`grep -F` on a key, a marker file, the notice cursor). Two readers route: `notify.py` sends every new line to Slack at the next 5-minute tick except `[notify]` lines, with `[triage]` lines as a count; the brief's prompt lists every line under Blockers, Pipeline. So a smoke failure and a sync block reach Slack the same way, and a session that wants to tell the owner something has no line to write.

The simplification review (2026-10-11, item 9) counted the eleven writers and proposed one alert writer; the owner left that out of step 2 (2026-10-13). This spec does not reopen it: the writers stay, the readers learn the tags.

## 2. Decisions

- **One registry, in code.** `vaultlib/alerts.py` holds the table below: tag, meaning, severity. `notify.py` imports it; the brief's prompt text and `FOUNDRY.md` carry the same table as documentation. No config key: a vault has no reason to differ until a second vault exists. **Owner decision:** a `notify_now_tags` override in `system/config.md` now, or none. Recommendation: none.
- **Three severities.** `now`: Slack at the next tick, as today. `brief`: waits for the next brief, never sent by the notifier. `never`: `[notify]` only (the notifier's own lines, so it never loops). `[triage]` keeps its count form. An untagged line, or a tag not in the registry, is `brief`, and the drift test (§4) keeps the registry complete.
- **The table.** The rule: `now` when the owner can act within the hour and the next brief is too late; `brief` for diagnostics the brief lists anyway. **Owner decision:** the whole table.

| Tag | Raised by | Severity |
|---|---|---|
| `foreman` | a session, by hand (§3.3) | now |
| `orders` | a Work Order that needs the owner, the self-test, the sandbox | now |
| `sync` | sync blocked, a failed merge or push | now |
| `update` | the daily template update: merged, conflict, stopped, failed | now |
| `rca` | a ticket filed, or a filing that stopped | now |
| `intake` | a failed brief or debrief, a publish refused, an input quarantined | now |
| `commit_runs` | a run the hook refused | brief |
| `smoke`, `calendar`, `meetings`, `handoffs`, `telemetry`, `clearinghouse`, `memory` | a fetch or check that failed | brief |
| `triage` | mail that needs the owner | now, as a count (unchanged) |
| `notify` | the notifier itself | never |

- **This supersedes the notices decision** of 2026-10-11 ("the owner asked for every alert") and that spec's deferred quiet-hours line: severity is the quiet hours.
- **The Foreman push** is a line with the `foreman` tag, written by `system/scripts/alert.py foreman "<text>"` from an interactive session. It is for a message to the owner now; something the owner owes or waits on stays a Now line (`now.py add`). The headless brief, debrief and ingest cannot write it: their Bash is sandboxed and only `run_headless.sh` writes alerts.
- **The dedupe and the cut stay.** The notifier's once-a-day rule (`_sans_time` against `sent`) and the 300-character cut apply to `now` lines as today. The brief's "N alerts today" count stays whole.

## 3. Changes

### 3.1 `vaultlib/alerts.py`
`TAGS: dict[str, tuple[str, str]]` (tag → meaning, severity), `severity(line) -> str` parsing `^- \d\d:\d\d:\d\d \[([a-z_]+)\] `, `brief` for anything else.

### 3.2 `notify.py`
`collect()` keeps a new alert line only when `severity(line) == "now"` (the `[notify]` exclusion folds into `never`); `[triage]` handling unchanged. The brief count line ("N alerts today") unchanged.

### 3.3 `system/scripts/alert.py <tag> <text>`
Appends one line with the vault's day and time; refuses a tag outside the registry (exit 2) and control characters in the text (as `commit_runs.py` strips them). `foreman` is the tag sessions use. `CLAUDE.md`'s Now rule gains one sentence: "To tell the user something now, outside the brief: `system/scripts/alert.py foreman "<one line>"`."

### 3.4 Documents
`FOUNDRY.md`: the table in the Slack notices paragraph ("Slack carries the `now` tags; the rest waits for the brief") and one sentence in Daily use on the Foreman push. The brief's prompt (`brief.md` line 65): Pipeline lists alerts grouped by tag. The notices spec: §2 "every new line" becomes "every new `now` line", the quiet-hours line closed.

## 4. Tests

`test_alerts.py`: `severity` on each tag in the table, on an untagged line, on a tag outside the registry. `test_notify.py`: a `brief` line is not collected, a `now` line is, `[triage]` still a count, `[notify]` never. `notify.bats` or `scripts.bats`: `alert.py foreman "x"` appends the line and `notify.sh` sends it; a tag outside the registry exits 2. `scripts.bats` drift test: every `[tag]` written by an alert line in `system/scripts/**` and `system/hooks/**` (the `printf -- '- %s [` and `f"- {…} [` forms) is a key of `TAGS`. `commands.bats`: `FOUNDRY.md` and `CLAUDE.md` carry the table and the push sentence. Each fails before the change.

## 5. Out of scope

- One alert writer and one once-a-day rule (the review's item 9; the owner's 2026-10-13 call stands).
- Per-tag channels (a second Slack channel, desktop, ntfy); severity is the first cut.
- Quiet hours by clock.
- Alerts from the headless brief or debrief sessions (sandboxed).
