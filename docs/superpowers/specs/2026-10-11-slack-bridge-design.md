# Slack bridge: notices out, captures in

**Date:** 2026-10-11
**Status:** Draft for the grill. The roadmap lists delivery notifications (#28, 11a) as "Grill first"; the owner asked on 2026-10-11 for Slack in both directions: the Foreman keeps them informed, and work dropped in Slack reaches the vault. §2 lists the proposed decisions and the questions the grill must settle.
**Issue:** #28 (delivery). Related: #99 (inbound triage, phase 2 of the Now page), which this spec does not replace (§6).

## 1. Problem

Every proactive channel the Foreman has lands in a file: the brief, the debrief, the Now page, alerts, the Work Orders report. Nothing reaches the owner away from Obsidian. A brief that fails at 06:00 is silent until someone opens the vault. A Work Order that finished at 02:00 with a pull request waits for the morning brief.

In the other direction, the vault takes inputs from `raw/inbox/` drops, meeting transcripts, session digests and connector fetches. A thought, a link or a task that arrives while the owner is on their phone or in Slack has no path in. The owner's words (2026-10-11): "enable my CoS to keep me informed and ingest work."

#28 (11a) proposed a deterministic `notify.sh` after the brief and the debrief with four channels (`none`, `desktop`, `ntfy`, `slack`). This spec builds the Slack channel first and adds the inbound half.

## 2. Decisions proposed, and what the grill settles

Proposed (the recommendation in each case; the grill may change any of them):

- **One Slack app, one bot token, no model.** Both directions call Slack's Web API from a Python script on the telemetry pattern (`telemetry_fetch.py`: standard library HTTP, a token outside the vault, a jsonl log, one alert a day per failure kind). No `claude -p` session runs for a notice or a capture. The alternative is the confined connector session (`jira_fetch.sh`, `meetings_fetch.sh`): no Slack app to create, and in exchange a model call, a 5-minute timeout and the account usage ceiling on every tick, which is the wrong dependency for the one notice that must reach the owner when the account limit stopped the brief. **Grill Q1:** bot token or connector?
- **Notices are counts by default.** A notice holds counts and a link to the briefing; it never holds note text unless `slack_notify_detail` is `headlines`, and then only Now statements and Work Order titles, passed through `redact.py` and cut at 120 characters. A Slack workspace is usually a work system; the counts default keeps `personal` lines out of it without a partition switch. **Grill Q2:** counts or headlines as the default?
- **Four notice events in v1:** the brief, the debrief, a brief or debrief that failed, and a Work Order that ended (done, failed or needs you). Alerts raised by the intake, the telemetry fetch or the watchers are not pushed one by one; they reach Slack as a count in the next brief or debrief notice. #28 proposed the same wait. **Grill Q3:** should a failed headless run (any `alerts_<date>.md` line) push at once?
- **One capture channel, one partition.** `slack_capture_channel` names a channel or DM the owner writes to on purpose. Every new message there becomes vault input. The partition is `slack_capture_partition` (default: `default_partition`, or `personal` when that is `shared`). A second channel for the other partition is a later phase. **Grill Q4:** is one channel enough to start?
- **A capture is an inbox drop.** Fetched messages are written under `raw/inbox/`, so the intake timer redacts, compiles and archives them as it does any other drop. No new note type, no new ingest rule. One file per fetch tick, holding every new message of that tick, so a burst of five messages costs one headless run against the daily cap. The owner sees a ✅ reaction on each captured message once its file is written.
- **Commands in the capture channel are a later phase.** A message is content to compile. `now:`, `order:` or `/query` prefixes acting on the vault are out of scope here (§5). #28's and #98's earlier cuts of chat prefixes stand.
- **Server or standalone only.** A client runs no units (two-machine spec §3.3).

## 3. Changes

### 3.1 The secret and the deny rules

- The bot token lives at `~/.config/foundry/slack.token` (mode 0600; `$XDG_CONFIG_HOME` honoured, as `sentry.token` is). The scopes it needs: `chat:write`, `channels:history`, `groups:history`, `im:history`, `reactions:write`, and `channels:read`/`groups:read` for the `--check`. The app is installed to the workspace by the owner; the bot is invited to both channels.
- `Read(~/.config/foundry/**)` joins the deny list in `.claude/settings.json` and `system/headless.settings.json`. Today neither file names that directory, and `sentry.token` already lives there. The confined connector settings (`lib_confine.sh`) deny `Read` outright, so they need no change.

### 3.2 `vaultlib/slack.py` and `system/scripts/slack_bridge.py`

`slack.py` holds the client and the two flows. `slack_bridge.py` is the CLI:

```
slack_bridge.py notify brief|debrief <date> [--exit <n>]   # after the brief or the debrief
slack_bridge.py notify order <item id>                      # after a Work Order ends
slack_bridge.py fetch                                       # the capture tick
slack_bridge.py --check                                     # auth.test, both channels resolvable
```

- HTTP goes through `vaultlib/http.py` `request`, which gains Slack routes in its stub (`slack-auth`, `slack-post`, `slack-history`, `slack-react`, `slack-info`) under `FOUNDRY_SLACK_STUB`, so bats can run the scripts end to end without a network.
- Every call logs one line to `system/logs/slack-<YYYY-MM>.jsonl` (`time`, `op`, `ok`, `reason`, `count`).
- Failures never raise out of the CLI: `notify` exits 0 whatever happens, so an `ExecStopPost` or a Work Order finish is never failed by Slack; `fetch` exits 1 on a Slack error, 4 when another fetch holds the lock, 2 on usage. Each failure kind (`auth`, `channel`, `rate`, `network`) raises one alert a day, `[slack]`-tagged, in `system/logs/alerts_<date>.md`.
- A 429 is honoured once (`Retry-After`, capped at 30 s); a second 429 is a `rate` failure for this tick.
- Every exit path is silent when the feature is off: `notify` returns 0 at once while `slack_notify_channel` is empty, `fetch` while `slack_capture_channel` is empty.

### 3.3 Notices

**Content**, built from files the brief and debrief already have, never from the model's text:

| Event | Source | Counts mode | Headlines mode adds |
|---|---|---|---|
| `brief <date>` | `system/logs/inputs/<date>/now.md`, `unavailable.md`, `nightshift.md`, `alerts_<date>.md`, `raw/telemetry/` | `Brief <date>: <n> needs you, <n> waiting, <n> alerts, <n> sources unavailable, <n> new error groups` and the briefing link | up to 5 open `owed` statements |
| `debrief <date>` | `system/logs/inputs/<date>/git.md`, `orders.md`, `prs.md`, `digests.md` | `Debrief <date>: <n> commits in <n> repos, <n> Work Orders ended, <n> pull requests, <n> digests` and the link | the Work Orders' titles and outcomes |
| `brief`/`debrief` with `--exit` non-zero | the exit code, the latest `runs-<YYYY-MM>.jsonl` line for that command | `Brief <date> failed (exit <n>): <ledger reason>`; exit 4 reads `account usage limit reached; inputs left in place` | nothing more |
| `order <id>` | `system/logs/nightshift/items/<id>/outcome.json` | `Work Order <id> <done/failed/needs you>` | the item title, and the pull request or findings note link |

The briefing link is `obsidian://open?path=<absolute path of briefings/<date>.md>`, which opens in any vault that holds the file. Counts are integers read from the prep files; a missing prep file counts as 0 and adds `(prep incomplete)` to the line. Text in headlines mode passes through `vaultlib.redact.redact` and is cut at 120 characters per item.

**Triggers:**

- `foundry-brief.service.in` and `foundry-debrief.service.in` gain `ExecStopPost=-"{{VAULT_ROOT}}/system/scripts/slack_bridge.py" notify brief --exit "${EXIT_STATUS}" "{{DATE}}"`, where the date is today in the unit's `TZ` (the script resolves it when the argument is empty, so the unit passes no date). systemd sets `$SERVICE_RESULT`, `$EXIT_CODE` and `$EXIT_STATUS` for `ExecStopPost`; on a server, the line runs after the post-run sync drop-in, so the briefing is already on `origin` when the owner opens the link on a client.
- `vaultlib/nightshift_run.py` `_finish` calls `slack.notify_order(vault, item_id)` after it writes `outcome.json`, inside a `try` that logs and continues. A Work Order's outcome is never changed by a notice failure.
- An interactive `/brief` or `/debrief` sends nothing. The owner is in the session.

### 3.4 Captures

`slack_bridge.py fetch`, every 15 minutes (§3.5):

1. Takes `system/slack.lock` (non-blocking; exit 4 when busy). Reads the cursor `system/logs/slack_fetch.since` (the last captured message `ts`; absent means "from now": the first run captures nothing and writes the cursor, so a channel's history is never swept in).
2. Calls `conversations.history` on `slack_capture_channel` with `oldest` = cursor, paging on `next_cursor`, at most 200 messages a tick (the rest wait for the next tick, and a `truncated` alert fires once a day). Thread replies are not fetched in v1: a reply posted in a thread of the capture channel is captured only when Slack also broadcasts it to the channel.
3. Skips messages with a `subtype` (joins, bot posts, edits), messages from the bot itself and messages that already carry the bot's ✅ reaction.
4. Writes one file, `raw/inbox/slack-<YYYY-MM-DD>T<HHMMSS>.md`, with frontmatter `partition: <slack_capture_partition>`, `source: slack`, `channel: <id>` and `captured_at`, and a body of one `## <HH:MM> <display name>` section per message holding the message text as Slack sent it (mrkdwn), a `Link:` line with the permalink, and for a shared message the shared text under `> `. Files are listed by name, never fetched: a `Files:` line names them. User mentions are left as `<@U…>`; the ingest reads them as data.
5. Adds the ✅ reaction to each captured message, then advances the cursor to the newest captured `ts`. A reaction failure is logged and does not move the cursor back; the message is in the file.
6. The file passes through the intake like any inbox drop: `redact.py` on the staging copy, one headless `/ingest`, archive on success. The name matches `RAW_NAME`, and the intake's 60-second freshness wait covers the write.

The ingest command needs no change: step 1 of `ingest.md` already reads the input's `partition` field, and the message sections are prose like any other drop. `system/templates/` gains `slack-capture.md` for the file layout, so the drift guard pins it.

### 3.5 Units and `install_units.sh`

- New `foundry-slack.service.in` (oneshot, `ExecStart=slack_bridge.py fetch`, `TimeoutStartSec=5min`, `SuccessExitStatus=1 4`) and `foundry-slack.timer.in` (`OnCalendar=*:0/15`, `Persistent=false`: a missed tick needs no catch-up, the next one reads the same cursor).
- `install_units.sh` adds them on a server or standalone when `slack_capture_channel` is set, next to the telemetry and DTCC rules, so they follow the config across re-runs and disappear when the channel is cleared.
- The `ExecStopPost` lines in the brief and debrief units are unconditional; the script's empty-channel exit keeps them silent.

### 3.6 `/setup` phase 6d: Slack

On a client, "not used on a client". Otherwise:

1. Ask whether notices should go to Slack. On yes, ask for the channel ID (`slack_notify_channel`) and the detail level (`slack_notify_detail`, default `counts`).
2. Ask whether a Slack channel should feed the vault. On yes, ask for the channel ID (`slack_capture_channel`) and the partition (`slack_capture_partition`).
3. When either is set, say where the token goes and which scopes the app needs (§3.1), wait until the owner says the file exists, then run `system/scripts/slack_bridge.py --check` and show its lines (`auth: ok as <bot name> in <workspace>`, `notify channel: <name>`, `capture channel: <name>`). A failed check leaves the config as written and says what to fix.
4. Write the keys with `vault_index.py set`, validate, and when phase 5 installed the units, show `install_units.sh --dry-run` and install on an explicit yes, as phases 6a and 6b do.

### 3.7 Config

`system/schemas/config.md` and `system/config.example.md` gain:

| Key | Kind | Default | Meaning |
|---|---|---|---|
| `slack_notify_channel` | string | `""` | channel or DM ID for notices; empty is off |
| `slack_notify_detail` | enum `counts`, `headlines` | `counts` | what a notice may hold (§3.3) |
| `slack_capture_channel` | string | `""` | channel or DM ID to capture; empty is off |
| `slack_capture_partition` | enum `work`, `personal` | `""` | partition of captured files; empty follows `default_partition` |

### 3.8 Documents

- `FOUNDRY.md`: a **Slack** paragraph in Daily use (what a notice holds, how a capture travels, where the token lives, the ✅ meaning), the two units in Machine roles, the deny rule in Security model, phase 6d in Getting started's setup prompt.
- `CLAUDE.md` Directory Map: `raw/inbox/` gains "and Slack captures".
- `.claude/settings.json` allow list: `Bash(system/scripts/slack_bridge.py --check)`.
- `docs/superpowers/roadmap.md`: the Delivery notifications row points here.

## 4. Tests

pytest (`test_slack.py`, `test_slack_notify.py`, `test_slack_fetch.py`):

- `token()`: missing file is an `auth` failure naming the path; mode other than 0600 is refused.
- `notify brief`: the counts line from fixture prep files; a missing prep file gives 0 and `(prep incomplete)`; `--exit 1` gives the failed line with the ledger reason; `--exit 4` names the usage limit; headlines mode lists at most 5 `owed` statements, redacted, cut at 120 characters, and never a `waiting` or `draft` line; an empty `slack_notify_channel` posts nothing and exits 0; a `channel_not_found` response alerts once and exits 0.
- `notify order`: done, failed and needs-you outcomes; the link only in headlines mode; a missing `outcome.json` logs and exits 0.
- `fetch`: no cursor captures nothing and writes the cursor; three new messages give one file with three sections in time order, the ✅ reaction on each, the cursor at the newest `ts`; a message with a `subtype`, the bot's own message and an already-reacted message are skipped; a shared message keeps its shared text as a quote; 201 messages capture 200 and alert `truncated` once; a 429 then 200 succeeds, two 429s fail the tick with one `rate` alert and leave the cursor; a reaction failure keeps the file and the cursor; the file name matches the intake's `RAW_NAME` and its frontmatter carries the configured partition; `shared` as `default_partition` falls back to `personal`.
- `http.request` stub routes for the five Slack endpoints.
- `_finish` in `nightshift_run`: a notice failure leaves `outcome.json` and the return code unchanged.

bats:

- `units.bats`: the brief and debrief services carry the `ExecStopPost` line; `foundry-slack.timer` renders only when `slack_capture_channel` is set, on server and standalone, never on a client, and goes away when the key is cleared.
- `slack.bats`: `slack_bridge.py fetch` end to end against `FOUNDRY_SLACK_STUB`: the file lands in `raw/inbox/`, and a following `intake_daemon.sh` run with the stub claude compiles and archives it; `--check` prints the three lines; `notify brief` after a stub brief posts the counts line (the stub records the request body).
- `settings`: both settings files deny `Read(~/.config/foundry/**)`.
- `vault_integrity.bats`: the new template is pinned by the drift guard; the config example validates against the schema with the new keys.

Each test fails before the change. Bound tools: pytest, bats, the gate (`verify_setup.sh`), and the live step: one real notice and one real capture on the owner's server, recorded in `docs/superpowers/spikes/`.

## 5. Out of scope, and later phases

- `desktop` and `ntfy` channels (#28). The `notify` entry point is channel-neutral in name only; a second transport is its own small spec.
- Pushing alerts one by one (Grill Q3 decides whether v1 adds it).
- Commands from Slack: `now:` lines, `/order add`, `/query` answers in a thread. Each is a write path from an external surface and needs its own gate rule.
- Thread replies that are not broadcast, file downloads, message edits and deletions after capture.
- A second capture channel for the other partition; a channel per codebase.
- Reading DMs and mentions as a triage source: that is #99 phase 2's deferred chat source (§6).
- The brief's interactive-only "Mail and chat" line stays as it is.

## 6. Relation to #28 and #99

- **#28, 11a Delivery:** this spec is its Slack channel, with the counts default, the deterministic post, the secret outside the vault and the `ExecStopPost` trigger it proposed. It adds the Work Order event, which did not exist when #28 was written, and the inbound half. The `~/.config/jarvis/notify.env` of #28 becomes `~/.config/foundry/slack.token`, one secret per service as `sentry.token` set the pattern.
- **#99, inbound triage:** the triage sweeps mail (v1) for items that need the owner and writes `owed` lines; chat DMs and mentions are deferred "after a miss in chat". The capture channel here is the owner pushing content in on purpose, with no judgement call and no Now line. The two meet later: when #99 adds chat, it can read through the same token and app, and a triage hit in Slack can carry the message permalink as evidence the same way a capture file does.
