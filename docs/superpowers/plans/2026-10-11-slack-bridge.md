# Slack Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `slack_bridge.py notify` posts brief, debrief, failed-run and Work Order notices to a Slack channel from a model-free script, and `slack_bridge.py fetch` turns new messages in a capture channel into `raw/inbox/` drops the intake compiles.

**Architecture:** `vaultlib/slack.py` (client, notices, captures) over `vaultlib/http.py` with stub routes; a CLI; `ExecStopPost` on the brief and debrief units; a `_finish` hook in `nightshift_run`; a service and timer pair gated by config; a `/setup` phase; four config keys.

**Tech Stack:** Python 3 (`vaultlib`, standard library HTTP), bash, systemd user units, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-11-slack-bridge-design.md`. This plan assumes the grill keeps §2's recommendations: bot token, counts default, no per-alert push, one capture channel. A different answer changes Task 1 (transport) or Task 2 (content) only.

## Global Constraints

- Work on branch `feat/slack-bridge-impl`. Commit there; do not push or open a pull request.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch`, outside a sandbox. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_slack.py`, `test_slack_notify.py`, `test_slack_fetch.py`, `test_nightshift_run.py`, `test_schema_notes.py`), bats (`slack.bats`, `units.bats`, `vault_integrity.bats`, `setup.bats`), the gate. The live step (one real notice, one real capture on the server) is the owner's, recorded under `docs/superpowers/spikes/`.
- Commits use `git commit -F .scratch/<file>`.
- Edits are described by place and content; the implementer anchors them in the current file text.
- No network in any test: every HTTP call goes through `http.request`, stubbed by `FOUNDRY_SLACK_STUB`.

## Review Focus

- `notify` exits 0 on every path, including a missing token, so `ExecStopPost` and `_finish` never fail because of Slack.
- Headlines mode content passes through `vaultlib.redact.redact` and is cut at 120 characters; counts mode carries no note text at all.
- The first `fetch` with no cursor captures nothing and writes the cursor (no history sweep).
- A captured file's name matches `vaultlib.intake.RAW_NAME` and the intake's end-to-end bats test compiles and archives it.
- Both settings files deny `Read(~/.config/foundry/**)`.

---

### Task 1: The client, the token and the stub routes

**Files:**
- Create: `system/scripts/vaultlib/slack.py`, `system/scripts/slack_bridge.py`
- Modify: `system/scripts/vaultlib/http.py` (stub routes `slack-auth`, `slack-post`, `slack-history`, `slack-react`, `slack-info` under `FOUNDRY_SLACK_STUB`)
- Test: `system/tests/python/test_slack.py`

**Interfaces:**
- Produces: `slack.token() -> str` (reads `~/.config/foundry/slack.token`, `$XDG_CONFIG_HOME` honoured, refuses a mode other than 0600); `slack.call(method, payload) -> dict` (POST to `https://slack.com/api/<method>`, one 429 retry capped at 30 s, raises `SlackError(kind, reason)` with kinds `auth`, `channel`, `rate`, `network`); `slack.log(vault, op, ok, reason, count)` to `system/logs/slack-<YYYY-MM>.jsonl`; `slack.alert_once(vault, key, text)`; the CLI skeleton with `--check` (`auth.test`, `conversations.info` on each configured channel, three lines).

- [ ] **Step 1: Write the tests:** token missing, wrong mode, ok; `call` success, `ok: false` with `channel_not_found` → `channel`, `invalid_auth` → `auth`, one 429 then 200 succeeds, two 429s → `rate`, URLError → `network`; `--check` prints the three lines with the stub and exits 0, exits 1 naming the failed line otherwise; `alert_once` writes one line per key per day.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement.** Follow `vaultlib/sentry.py` for the token and `vaultlib/telemetry_run.py` for the log and alert helpers.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.** `.scratch/msg-1.txt`:

```text
feat(slack): a Slack client, token and --check for the bridge (#28)

vaultlib/slack.py calls the Web API through http.request (stub routes
for tests), reads the bot token from ~/.config/foundry/slack.token, logs
to system/logs/slack-<YYYY-MM>.jsonl and alerts once a day per failure
kind. slack_bridge.py --check proves auth and both channels.
```

### Task 2: Notices for the brief and the debrief

**Files:**
- Modify: `system/scripts/vaultlib/slack.py`, `system/scripts/slack_bridge.py`, `system/systemd/foundry-brief.service.in`, `system/systemd/foundry-debrief.service.in`
- Test: `system/tests/python/test_slack_notify.py`, `system/tests/units.bats`

**Interfaces:**
- Produces: `slack.brief_notice(vault, date, exit_code, detail) -> str`, `slack.debrief_notice(...)`, `slack.notify(vault, text) -> bool`; CLI `notify brief|debrief [<date>] [--exit <n>]`; the two units gain `ExecStopPost=-"{{VAULT_ROOT}}/system/scripts/slack_bridge.py" notify brief --exit "${EXIT_STATUS}"` (debrief likewise).

- [ ] **Step 1: Write the tests** from spec §4 (counts line from fixture prep files; missing prep file → 0 and `(prep incomplete)`; `--exit 1` → the failed line with the ledger reason; `--exit 4` → usage limit; headlines mode: at most 5 `owed`, redacted, cut at 120, no `waiting` or `draft`; empty channel → nothing posted, exit 0; `channel_not_found` → one alert, exit 0); `units.bats`: both services carry the line.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement.** Counts come from `system/logs/inputs/<date>/now.md` (open lines by kind), `unavailable.md`, `nightshift.md` (Needs-you lines), `system/logs/alerts_<date>.md`, `raw/telemetry/` (groups first seen that day); debrief counts from `git.md`, `orders.md`, `prs.md`, `digests.md`. The link is `obsidian://open?path=<absolute briefing path>`. The ledger reason comes from the latest `runs-<YYYY-MM>.jsonl` line for that command.
- [ ] **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-2.txt`:

```text
feat(slack): brief and debrief notices after each run, counts by default (#28)

ExecStopPost on the brief and debrief units posts a counts line and the
briefing link, or the failure with its ledger reason. Headlines mode
adds up to five redacted owed statements. An empty channel is silent.
```

### Task 3: Work Order notices

**Files:**
- Modify: `system/scripts/vaultlib/slack.py`, `system/scripts/slack_bridge.py`, `system/scripts/vaultlib/nightshift_run.py` (`_finish`)
- Test: `system/tests/python/test_slack_notify.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `slack.order_notice(vault, item_id, detail) -> str` from `outcome.json`; CLI `notify order <id>`; `_finish` calls `slack.notify_order(vault, item_id)` in a `try` after writing the outcome.

- [ ] **Step 1: Write the tests:** done, failed and needs-you outcomes; the link only in headlines mode; missing `outcome.json` logs and exits 0; `_finish` keeps its return code and the outcome when the notice raises.
- [ ] **Step 2: Run them to verify they fail.** **Step 3: Implement.** **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-3.txt`: `feat(slack): a notice when a Work Order ends (#28)`.

### Task 4: Captures

**Files:**
- Modify: `system/scripts/vaultlib/slack.py`, `system/scripts/slack_bridge.py`
- Create: `system/templates/slack-capture.md`
- Test: `system/tests/python/test_slack_fetch.py`, `system/tests/vault_integrity.bats` (template pinned)

**Interfaces:**
- Produces: `slack.fetch(vault) -> int` (messages captured); CLI `fetch` (exit 0, 1 Slack error, 4 lock busy, 2 usage); cursor at `system/logs/slack_fetch.since`; file `raw/inbox/slack-<YYYY-MM-DD>T<HHMMSS>.md` from the template with `partition`, `source`, `channel`, `captured_at` frontmatter and one `## <HH:MM> <name>` section per message (text, `Link:`, shared text as a quote, `Files:` names).

- [ ] **Step 1: Write the tests** from spec §4 (no cursor; three messages → one file, three sections in time order, ✅ on each, cursor advanced; subtype, own and already-reacted messages skipped; shared text quoted; 201 → 200 and one `truncated` alert; 429 handling; reaction failure keeps file and cursor; file name matches `RAW_NAME`; partition from config, `shared` default falls back to `personal`; empty channel → exit 0, nothing read).
- [ ] **Step 2: Run them to verify they fail.** **Step 3: Implement.** **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-4.txt`:

```text
feat(slack): capture a channel into raw/inbox/ for the intake (#28)

fetch reads conversations.history from a cursor, writes one inbox file
per tick with the configured partition, reacts with a check mark on
each captured message and advances the cursor. The first run captures
nothing and only sets the cursor.
```

### Task 5: Units, install rules, config and deny rules

**Files:**
- Create: `system/systemd/foundry-slack.service.in`, `system/systemd/foundry-slack.timer.in`
- Modify: `system/scripts/install_units.sh`, `system/schemas/config.md`, `system/config.example.md`, `.claude/settings.json`, `system/headless.settings.json`
- Test: `system/tests/units.bats`, `system/tests/python/test_schema_notes.py`, `system/tests/commands.bats` (deny rule in both settings files; `--check` allow rule)

- [ ] **Step 1: Write the tests:** the timer renders only with `slack_capture_channel` set, for server and standalone, never client, and goes away when cleared; the config example validates with the four keys; both settings files deny `Read(~/.config/foundry/**)`; the allow list has `Bash(system/scripts/slack_bridge.py --check)`.
- [ ] **Step 2: Run them to verify they fail.** **Step 3: Implement.** **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-5.txt`: `feat(slack): units, config keys and the config-directory deny rule (#28)`.

### Task 6: `/setup` phase 6d and the manual

**Files:**
- Modify: `.claude/commands/setup.md`, `FOUNDRY.md`, `CLAUDE.md` (Directory Map, one phrase), `docs/superpowers/roadmap.md`
- Test: `system/tests/setup.bats` or `commands.bats` (phase 6d present and names `slack_bridge.py --check`; `FOUNDRY.md` names the token path and the ✅ meaning)

- [ ] **Step 1: Write the tests.** **Step 2: Verify they fail.** **Step 3: Write** phase 6d as spec §3.6 and the manual paragraphs as §3.8. **Step 4: Run the suites and the gate.**
- [ ] **Step 5: Commit.** `.scratch/msg-6.txt`: `docs(slack): /setup phase 6d and the Slack paragraphs in the manual (#28)`.

### Task 7: End to end

**Files:**
- Test: `system/tests/slack.bats`

- [ ] **Step 1: Write the tests:** `fetch` against the stub lands a file in `raw/inbox/`, then `intake_daemon.sh` with `stub_claude` compiles and archives it; `--check` prints three lines; `notify brief` after a stub brief posts the counts line (the stub records the request body).
- [ ] **Step 2: Run them.** Expected: PASS with Tasks 1 to 6 in place; fix what is not.
- [ ] **Step 3: Run the gate.** Expected: exit 0.
- [ ] **Step 4: Commit.** `.scratch/msg-7.txt`: `test(slack): the bridge end to end against the stub (#28)`.

### Task 8: Live step (owner, not for a Work Order)

- [ ] Create the Slack app with the scopes in spec §3.1, install it, invite the bot to both channels, write the token file with mode 0600.
- [ ] Run `/setup` phase 6d on the server, then `system/scripts/slack_bridge.py --check`.
- [ ] Post one message in the capture channel; confirm the ✅, the inbox file, and the compiled note after the next intake tick.
- [ ] Wait for the next brief; confirm the notice. Record both in `docs/superpowers/spikes/<date>-slack-bridge-acceptance.md`.
