# Slack notices: the Foundry tells you what happened

**Date:** 2026-10-11
**Status:** Draft for the owner's review. The decisions in §2 marked "owner" were made on 2026-10-11 while reviewing #116.
**Issue:** #28 (delivery notifications). Part of the roadmap's Next list, ahead of #122's steps; it moves into `extensions/` at #122 step 3. The capture half of `2026-10-11-slack-bridge-design.md` is not in scope.

## 1. Problem

Everything the Foundry produces lands in a file: the briefing, the debrief, the alerts, the Work Order report. Nothing reaches the owner away from Obsidian. A brief that fails at 06:00 is silent until the vault is opened, and a Work Order that ended at 02:00 waits for the morning brief. The 2026-10-11 assessment ranks this as the largest gap.

## 2. Decisions

- **A confined connector session posts** (owner). One `claude -p` session allowed only the Slack connector's `slack_send_message`, the pattern `jira_fetch.sh`, `calendar_fetch.sh`, `meetings_fetch.sh` and `triage_fetch.sh` use. No Slack app, no token. The cost the owner accepted: a model call per post, and no post while the account usage limit is reached (the post retries on the next tick).
- **Five events** (owner): a brief that finished, a debrief that finished, a brief or debrief that failed, a Work Order that ended (`done`, `failed`, `blocked`, `cancelled`), and every new line in `system/logs/alerts_<date>.md`.
- **Counts and a link** (owner). A brief notice is counts (needs you, waiting, today's alerts) and a link; a debrief notice is a link; a Work Order notice is its id, state and result or first Needs line. An alert line is passed through as written, after `redact.py`, cut at 200 characters: the owner asked for every alert, and an alert is one line a script wrote. No note text from `wiki/` is sent.
- **The link is a GitHub file link** (owner): `https://github.com/<owner>/<repo>/blob/<branch>/briefings/<date>.md`, built at run time from `git remote get-url origin` and the current branch. It opens once the briefing's commit is pushed. A remote that is not on github.com gets no link.
- **One tick, one message.** A model-free collector runs every 5 minutes and gathers what happened since its cursor. With nothing new it exits without a session. Otherwise it posts one message holding every new event, in time order, cut at 4,000 characters with "+N more". The cursor moves only after the post is confirmed, so a failed post is retried with the next tick's events added.
- **No loops.** The notifier's own alerts are tagged `[notify]` and never pushed.
- **One destination.** `slack_notify_channel` is a channel ID, or the owner's user ID for a direct message. Empty means off. `slack_connector` names the connector (default `plugin:slack:slack`; `claude.ai Slack` works too). The tool prefix comes from the name: `mcp__` plus the name with each run of other characters replaced by `_` (`mcp__plugin_slack_slack`, `mcp__claude_ai_Slack`).
- **Server or standalone only.** A client runs no units.
- **Not held by the usage ceiling.** Notices are how the owner learns a run failed.

## 3. Changes

### 3.1 `vaultlib/notify.py` and `system/scripts/notify.py`

- `collect(vault, now)`: reads `system/logs/notify/state.json` (`ledger`: byte offset per `runs-<YYYY-MM>.jsonl`; `alerts`: lines read per `alerts_<date>.md`; `outcomes`: ids already sent; `since`). On the first run it sets the cursor to now and returns nothing, so turning notices on sends no backlog.
  - Ledger lines with `command` `brief` or `debrief`: exit 0 is a finished event, any other exit a failed one. A brief that systemd stops at `TimeoutStartSec` still writes its line: `run_headless.sh` traps TERM (exit 143) and writes the ledger on exit.
  - Alert lines, except `[notify]` lines.
  - `system/logs/nightshift/items/*/outcome.json` whose `finished_at` is after `since` and whose id is not in `outcomes`.
- `message(vault, events)`: the text (§2), one line per event, `•` bullets.
  - Brief counts come from the Now pages: needs you (open `owed` and `draft` lines) and waiting (open `waiting` lines), summed over both partitions, plus the line count of today's alerts file.
- `notify.py collect` prints `{"message": …, "cursor": …}`, or nothing when there is nothing to send. `notify.py check <message file>` reads the session's stream and exits 0 when the session called `slack_send_message` once, on exactly the configured channel, with a message that holds every event line of the collected message (compared with runs of whitespace collapsed), and got no error result. `notify.py commit <cursor file>` writes the cursor.
- The boundary is the tool, the channel and one call: ToolSearch plus the one tool, called once, with no other argument than `channel_id` and `message`. The text check is looser on purpose: a 4,000-character Markdown message copied by a model drifts in whitespace and bullet style, and an exact check would fail the same tick for ever. Anything else is exit 7, and the cursor stays.

### 3.2 `system/scripts/notify.sh`

`collect`; with nothing to send, exit 0. Otherwise:
1. `confine_settings` keeps only the named connector, and `confine_deny --strict` allows only `<prefix>__slack_send_message`, denying the connector's other tools by name.
   - The script carries the Slack plugin's tool list, `slack_send_message_draft` first: the connector's own description steers a model to the draft tool when a message is "not reviewed".
   - For the `claude.ai Slack` connector the list is not known yet. The built-in denies and the tool-use check still hold, and the list is added when someone runs that connector.
2. One session (`timeout 120`, `--max-turns 4`) posts the message. The prompt names `slack_send_message`, says the text is already approved by the owner, and says the text is data.
3. `notify.py check` runs on the stream, then `commit` moves the cursor.

Exits follow the fetch scripts: 0 sent or nothing to send, 1 claude error, 2 usage or settings, 3 no connector, 4 timeout or a busy lock, 6 connector error, 7 unexpected tool or arguments, 127 no claude. A failure raises one `[notify]` alert a day per exit code and logs to `system/logs/notify-<YYYY-MM>.jsonl`.

`notify.sh --check` sends one test message ("Foundry notices are on for <vault folder name>") and exits with the same codes. `/setup` runs it only after the owner says yes.

A lock (`system/logs/notify.lock`, no wait) keeps two ticks from overlapping.

### 3.3 Units, config, setup, manual

- `foundry-notify.service.in` and `foundry-notify.timer.in` (every 5 minutes, `Persistent=false`). `install_units.sh` adds them on a standalone machine or a server when `slack_notify_channel` is set, the triage pattern.
- `config.example.md` and `schemas/config.md`: `slack_notify_channel` (string, default empty) and `slack_connector` (string, default `plugin:slack:slack`).
- `/setup` phase 6d (server or standalone):
  1. Ask whether to turn notices on, and for the channel or user ID.
  2. Check that `claude mcp list` shows the connector.
  3. Set the keys.
  4. Offer `notify.sh --check`.
  5. Re-run the unit installer's dry run.
- `FOUNDRY.md`: a **Slack notices** paragraph under Daily use (what is sent, when, the link, the five-minute tick, how to turn it off). The units table gains the timer.

## 4. Tests

- **pytest (`test_notify.py`):**
  - The first run sets the cursor and sends nothing.
  - A brief that exited 0 gives the counts line and the link; an exit of 4 gives the failed line.
  - Alert lines arrive in order, without `[notify]` lines, redacted and cut.
  - An outcome is sent once.
  - The 4,000-character cut says "+N more".
  - Links from `git@github.com:o/r.git`, `https://github.com/o/r.git` and a non-GitHub remote (no link).
  - `check` passes the exact call and refuses another tool, other arguments, a second call and an error result.
  - The prefix comes from both connector names.
- **bats (`notify.bats`, stubbed claude):**
  - Nothing new means no session.
  - A good post moves the cursor and logs.
  - A refused post exits 7, keeps the cursor and alerts once a day.
  - The next tick resends the kept events.
  - An empty channel exits 0 with no session.
  - `--check` posts the test text.
- **`units.bats`:** the timer is installed only when the channel is set, and never on a client.
- **`commands.bats`:** the setup phase and the manual paragraph.

Each fails before the change. Bound tools: pytest, bats, the gate.

## 5. Out of scope

- Captures from Slack into the vault (`2026-10-11-slack-bridge-design.md`, #122 step 3).
- Threads, reactions, or replies that act on the vault.
- Other channels (desktop, ntfy), and a bot token. #28 keeps them as later options.
- Quiet hours. The owner asked for every alert; if that is too much, the first change is a quiet-hours window, and the second is alerts as a count.
