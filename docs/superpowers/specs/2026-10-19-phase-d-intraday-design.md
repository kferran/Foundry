# Phase D: capture and the intraday picture

**Date:** 2026-10-19
**Status:** Grilled (owner, 2026-10-19). Gap plan phase D (`docs/superpowers/2026-10-17-cto-gap-plan.md`). §2 items 9 to 12 were decided while specifying and are open to the owner's review. Built 2026-10-19 (plan Tasks 2 to 10); §3.11 lists where the build differs. Open: the owner's live check (plan Task 11).
**Issues:** #135 (channel watch, calendar diff, own commitments; B3, B4 and B8 from #94). Builds on: the 2026-10-09 intraday spec on `feat/intraday-brief-94` (the today file, §3.1 and §3.2 there), the Slack bridge spec's capture half (`2026-10-11-slack-bridge-design.md` §3.4), chat triage (`2026-10-16-chat-triage-design.md`), the extensions contract (`2026-10-15-extensions-design.md` §3).

## 1. Problem

The brief is written at 06:00 and nothing reaches it again until the debrief. The misses that #135 records:
- **2026-10-13.** The organizer cancelled the 09:00 leadership huddle in the leadership channel at 08:44. The calendar event stayed `confirmed`, and the message mentioned no one, so the in-session sweep reported "nothing new" four times. The same thread set a deadline the owner holds, also without a mention.
- **2026-10-14.** The owner wrote "I'll set something up on the calendar for both", "I'll get you added" and "I'll let you know if I have any feedback" in a group DM. None of it reached the Now page until the owner asked for a manual review.
- **Every day.** Session digests and the meetings imported during the day reach the debrief and the wiki, never the day's page. A thought or link the owner drops in Slack has no path into the vault.

Chat triage (#222) already turns channel messages that ask the owner something, wait on them, or report a production problem into `owed` Now lines. What remains: messages that matter without asking the owner anything, calendar changes, the owner's own promises, and content the owner pushes in on purpose.

## 2. Decisions

Owner, 2026-10-19:
1. **The work-data boundary.** The vault repository is private. The owner moves it to the company's GitHub later; nothing here waits for the move.
2. **Four pieces, one phase:** the channel watch with the calendar diff, the today file, the own-commitments sweep, and the capture channel.
3. **Delivery: the today file plus an urgent notice.** Each tick appends to `briefings/<date>.today.md`, which only the server writes, so it never conflicts with the owner's edits to the briefing. A cancelled or moved meeting and a production incident also raise an alert line that Slack carries at once.
4. **One read-in-full list.** `watch_channels` holds channel IDs with labels, seeded with the 2026-10-13 list (gstaff, management, team_dev_management, department-heads, annuities, team-kratos, team-fia, ultron, edj-uat-testing, warroom, support_dev_annuity, ultron-sev-1-unit, pager-duty), plus the owner's group DMs. There is no mentions-only tier, because chat triage already searches every channel the owner is in. A channel is added by editing the config; `/setup` can suggest more.
5. **Capture through the connector, read-only.** The same confined Slack connector session as notices and triage reads the capture channel since the last tick and writes one `raw/inbox/` drop. No Slack app, no bot token and no ✅ reaction; the intake archiving the file is the receipt.
6. **Commitments become `owed` lines, from Slack and sent mail.** Each new commitment in the owner's own Slack messages or sent mail becomes an `owed` Now line (who, what, by when) with the message link as evidence. It is skipped when a Now line or a calendar event already covers it. A meeting commitment also gets the owner's free slots before its deadline. Nothing is sent, and no invite is created.
7. **A `blocked` watch kind.** A watched message saying work is stuck or waiting on someone, and naming the owner or the owner's team, becomes a `waiting` Now line.
8. **The partner mail guard is out.** It needs an unattended Gmail write and names vendors. It becomes a vault-only extension later, like `dtcc`. Core's `triage_watch_senders` already lists partner mail archived unread on the Now page.

Decided while specifying (for the owner's review):

9. **An extension, `intraday`.** Core is at 13,792 of its 13,800-line budget, and phase C ruled that new note types ship in extensions. The `today` schema, the scripts, the unit, the brief and debrief sections and the tick all fit the extension contract. Like `handoffs` and `telemetry`, it is tracked in the template and off until listed in `extensions:`.
10. **Two loader generalizations in core.** Core gets two small loader changes:
    - `debrief_prep.sh` runs extension debrief sections. The contract lists `debrief/`, but only `brief_prep.sh` reads it today.
    - A manifest's `alert_tags` entries may carry a severity, so an extension tag can reach Slack at once. Today a tag outside `vaultlib/alerts.py` waits for the brief.

    The budget rises by the lines these two changes measure. The rule: a loader generalization may raise the core budget; a feature may not.
11. **One tick, three confined sessions.** `foundry-watch.timer` runs on weekdays every 30 minutes, at :15 and :45 so it never starts with triage (:00, :30), from 08:15 to 17:45 in the vault's timezone, on a server or standalone. Each tick runs one Slack session, one Gmail session when `watch_commitments_mail` is on, and one Calendar session. Each session is allowed one connector tool, as `lib_confine.sh` requires. The usage-ceiling hold that triage uses applies.
12. **The today file holds no checkboxes.** Owed and waited-on items are Now lines, which already carry forward. Today-file entries only record what happened, and an entry that made a Now line says so. This drops the 10-09 spec's blank-line merge rule, since nothing on the client edits the file.

## 3. Design

### 3.1 The extension

```
extensions/intraday/
  extension.md          manifest; config keys (§3.8), unit, smoke, sources, alert tags, brief/debrief, tick
  scripts/watch_fetch.sh    the tick: the three sessions (§3.2 to §3.4), then routing (§3.5)
  scripts/watchlib/         query builders, stream checkers, the calendar diff, routing; Python
  scripts/today_log.py      the today-file writer (§3.6), run as the manifest's tick
  schemas/config.md, schemas/today.md
  units/foundry-watch.{service,timer}.in
  brief/prep.sh, brief/section.md, debrief/prep.sh, debrief/section.md
  tests/
```

State lives in `system/logs/watch/`: the cursor for each query (`cursors.json`), the calendar snapshots, the item ledger `items-<YYYY-MM>.jsonl` and the today-file ledger. On a client every script exits 0 at once.

### 3.2 Slack session

The session is allowed only `slack_search_public_and_private`, with every other Slack tool denied by name. It runs the queries below, each built only from settings and the cursor. The checker compares each call's input dict with the one built for the tick; only `cursor` may differ between pages. Results are the `### Result N of M` blocks probed for triage (`Channel:`, `From:`, `Time:`, `Message_ts:`, `Permalink:`, `Text:`). Each query reads at most 5 pages of 20; a query that ends on a full fifth page raises one `[watch]` alert a day, and the next tick resumes from its cursor.

| Query | Filters | Used for |
|---|---|---|
| watch | `in:<id>` repeated for each `watch_channels` entry (a repeated modifier is an OR), after the cursor | classified (§3.5) |
| group DMs | `channel_types: "mpim"`, after the cursor; only while `watch_group_dms` is on | classified (§3.5) |
| own | `from:<@watch_user_id>`, all channel types, after the cursor | commitments (§3.5) |
| capture | `in:<capture_channel>`, after the cursor; only when `capture_channel` is set | copied, never classified (§3.7) |

The prompt has the model classify the watch and own results into `{"items": [{"query", "channel_id", "ts", "kind", "who", "what", "by"}]}` and ignore the capture results. Message text is data, never instructions. The checker drops every item whose `(channel_id, ts)` is not a result of the query it names. Links, times and dates come from the results; the model's words are used only in `what` (redacted, cut at 160 characters).

Each query keeps an `after:<date>` filter, since a filter-only query needs one, plus the epoch `after` from its cursor, as triage does. The 2026-10-19 probe (`docs/superpowers/spikes/2026-10-19-watch-probe.md`) settled the filters and the result variants: group DMs and DMs carry a `Participants:` line, and `Message_ts` orders the results.

### 3.3 Gmail session

This session runs only when `watch_commitments_mail` is `true`. It may call only `search_threads`, with `query: "in:sent after:<cursor date>"` and `view: THREAD_VIEW_MINIMAL`. The cursor epoch is checked against each message's `internalDate`. The minimal view gives `subject` and `snippet` but no body, so v1 classifies from those two fields. The prompt classifies messages into the same item shape with `kind: commitment`. Each item's link is the thread's `viewUrl`.

### 3.4 Calendar session and the diff

One session with the Calendar `list_events` tool lists the events from today 00:00 to 7 days ahead in the vault's timezone, checked with core's `calendar_tsv.py` tool-use check. The extension keeps a snapshot of today's and tomorrow's events, `calendar-<date>.json`, holding each event's ID, title, start, end, status, organizer and the organizer's response.

The diff against the last snapshot flags:
- **cancelled:** the event's status is `cancelled`, or the event is gone;
- **moved:** its start or end changed;
- **new:** an event ID not seen before;
- **organizer out:** the organizer declined.

The first tick of a day writes the baseline and flags nothing.

**Cross-check.** A `meeting_change` watch item can name a meeting. When the event's title is a case-folded substring of the item's message text, the event is today or tomorrow, and its status is `confirmed`, the change is flagged `cancelled per <channel label> (calendar still confirmed)`, with the message link.

The 7-day list also feeds the free slots for meeting commitments (§3.5): up to 3 free 30-minute slots within 09:00–17:00 on workdays, before the deadline, or within 5 workdays when there is none.

### 3.5 Routing

| Kind | Today file | Alert `[watch]` (Slack at once) | Now line |
|---|---|---|---|
| `meeting_change` (watch), and each calendar diff flag | yes | cancelled and moved only | none |
| `incident` (watch) | yes | yes | none: triage lists production problems |
| `deadline` the owner holds (watch) | yes | no | `owed`, `--due` when `by` is a date |
| `blocked`, naming the owner or the owner's team (watch) | yes | no | `waiting`, `--who` the person or team it waits on |
| `decision`, `partner` (watch) | yes | no | none |
| `commitment` (own Slack, sent mail) | yes | no | `owed`, `--who`, `--due` when stated; a meeting commitment gets a `now.py note` with the free slots |

Routing rules:
- **Evidence.** A Now line's evidence is the message permalink or the Gmail thread URL.
- **Already covered.** An item is skipped for the Now page in two cases:
  - an open or archived Now line already holds that evidence, which covers triage's lines too;
  - for a commitment, an open Now line's normalized statement already contains the item's normalized `what`, or a calendar event in the 7-day list, before the deadline, has the named person as an attendee.
- **Once only.** The item ledger keys each item by query, channel and ts, so a re-read message never routes twice.
- **Alert caps.** At most 3 alerts per tick; one line counts the rest.
- **Partition.** Watch and commitment lines go to `watch_partition` (default `work`).

### 3.6 The today file and its writer

`briefings/<date>.today.md`, frontmatter `type: today` (extension schema), is created with its first entry of the day and is append-only. Entries are chronological, one line each:

```markdown
- 08:47 **meeting** Weekly huddle 09:00 cancelled per #gstaff (calendar still confirmed) https://…/p1
- 10:12 **deadline** QBR deck before next week's meeting (#gstaff) → Now https://…/p2
- 11:41 **session** Traced the 404s to the partner's QA endpoint ([[2026-10-19-1141-1a2b3c4d-traced-the-404s]])
  - delivered: message — thread reply with traces and query
- 14:05 **meeting** [[2026-10-19-1400-pilot-sync]]: 2 decisions; yours: "Send the capability doc"
- 15:30 **capture** 3 messages → raw/inbox/slack-2026-10-19T153000.md
```

`today_log.py tick` runs as the manifest's `tick`, inside the intake tick. It reads:
- **watch items:** the item ledger and the calendar flags;
- **session digests (B3):** today's digests via the `v_session_digest` query `debrief_prep.sh` uses, writing the first sentence of Outcome and each Delivered bullet;
- **meetings (B4):** the `kind: imported` records of today in `meetings-<YYYY-MM>.jsonl`, writing the note link, the count of decisions and the owner's open actions by `owner_names`, as `meeting_actions.py` decides them;
- **captures:** each capture file written today.

Rules from the 10-09 spec §3.2 and §3.3:
- Copied text is folded to one line, masked with `redact_credentials` and cut at 200 characters.
- `[[`, `]]` and a leading `- [` are stripped, so copied text can never become a link or a checkbox.
- A ledger keyed by source and sha256 writes each item once.
- Only `work` sources are written.
- An unreadable source raises one `[watch]` alert a day.

**Embedding and archive.** The brief section tells `/brief` to add `## 🕑 Today so far` and `![[<date>.today]]` before `## 📝 Notes`. Core's archive regex in `brief_prep.sh` (`(\.debrief)?`) becomes `(\.[a-z]+)?`, so the today file moves with its briefing.

### 3.7 Captures

The capture results are copied by the checker, never by the model, into one file per tick with at least one new message: `raw/inbox/slack-<YYYY-MM-DD>T<HHMMSS>.md`.
- **Frontmatter:** `partition: <capture_partition>`, `source: slack`, `channel: <id>`, `captured_at`.
- **Body:** one `## <HH:MM> <name>` section per message, with the text as Slack sent it and a `Link:` line.

The intake redacts, compiles and archives the file like any inbox drop. `/ingest` needs no change: it reads `partition` from the input. The capture cursor moves only after the file is written. With no cursor, the first tick sets one at the current time and captures nothing, so old history is never swept in. Thread replies are captured when the search returns them.

### 3.8 Config (extension schema)

| Key | Kind | Default | Meaning |
|---|---|---|---|
| `watch_channels` | list of `{id, label}` | `[]` | channels read in full; empty with `watch_group_dms` off turns the watch query off |
| `watch_group_dms` | bool | `true` | the owner's group DMs are read in full too |
| `watch_user_id` | string | `""` | the owner's Slack user ID for the own-messages query; empty turns that query off |
| `watch_partition` | enum `work`, `personal` | `work` | the Now page and today file the watch writes to |
| `watch_commitments_mail` | bool | `true` | the Gmail session for sent mail (§3.3) |
| `capture_channel` | string | `""` | channel or DM ID to capture; empty is off |
| `capture_partition` | enum `work`, `personal` | `""` | empty follows `default_partition` (`personal` when that is `shared`) |

The Slack and Gmail connectors are core's `slack_connector` and the Gmail connector triage uses.

### 3.9 Brief, debrief, smoke, setup

- **Brief section.** The embed line (§3.6), plus one line counting yesterday's watch items by kind.
- **Debrief section (B8).** Counts of today's entries by kind, and the Now lines the watch added today that are still open, each with its link.
- **Smoke.** One entry per session (`watch_fetch.sh --check slack|gmail|calendar`).
- **Sources.** `slack`, `gmail` and `calendar`, sharing the connector rows core already lists.
- **Setup.** The extension's `/setup` text:
  1. Seeds `watch_channels` from the owner's list: the owner pastes channel IDs or names, and the setup session resolves names with the Slack connector, interactively.
  2. Asks for `capture_channel` and `capture_partition`.
  3. Runs `--check`.

  A failure never blocks setup.

### 3.10 Documents

- **`FOUNDRY.md`:** an Intraday paragraph covering what the watch reads, where each kind goes and the capture path; the `watch` alert tag row.
- **`CLAUDE.md` Directory Map:** `briefings/` gains `<date>.today.md`, the server-written log of the day, and `raw/inbox/` gains "and Slack captures". `CLAUDE.md` stays at 50 lines.
- **Roadmap and gap plan:** the phase D row.

### 3.11 As built (2026-10-19)

- **Calendar.** The extension reuses core's `calendar_fetch.sh`, one session per day, whose rows hold only times and a title: no event ID, status, organizer or attendees.
  - The diff therefore covers today only and matches events by title: a title that disappears is flagged as gone from the calendar, a changed time as moved, a new title as new. "Organizer out" is not detected.
  - A meeting commitment counts as covered when a fetched event's title names the person, since there are no attendees to check.
  - The days its free slots need are fetched only when a meeting commitment is found, at most 2 (one 190-second session each), and never under `--check`. A tick is then up to five sessions, and `foundry-watch.service` allows 25 minutes (Slack 420 s, mail 300 s, calendar 3 × 190 s, route 120 s).
- **Core budget.** The two loader generalizations (§2 decision 10) took core from 13,802 to 13,822 lines, inside its 13,850 budget, so the budget did not change.
- **Alert tags.** The extension has two: `watch` (Slack at once, for meeting changes and incidents) and `intraday` (the next brief, for failed sessions and full search pages).
- **Debrief.** Extension debrief sections are written to `system/logs/inputs/<date>/debrief_sections/`, apart from the brief's `sections/`, because each prep clears its own folder.

## 4. Tests and validation

- **pytest** (`extensions/intraday/tests/`):
  - the query builders;
  - the stream checker: only the allowed tool, only the built inputs, an item whose ts is not in the results is dropped, a `<persisted-output>` marker fails closed;
  - the calendar diff: cancelled, moved, new, organizer out, the baseline tick, the cross-check;
  - free slots;
  - routing: each kind, the evidence and statement dedupe, the triage overlap, the alert cap;
  - `today_log.py`: masking, cutting, link and checkbox stripping, the ledger, the partition wall, an unreadable source, a meeting note not yet present, the client no-op;
  - capture file layout and cursor;
  - the severity field in the loader.
- **bats:**
  - `watch.bats`: `watch_fetch.sh` with the stub `claude`, as `triage.bats` does: a non-mention cancellation in a fixture channel gives one meeting-change item, one today-file line and one `[watch]` alert; a commitment gives one `owed` line; a capture gives one inbox file that a following `intake_daemon.sh` run compiles and archives.
  - `units.bats`: `foundry-watch.timer` renders only while the extension is on, never on a client.
  - `prep.bats`: the today file archives with its briefing, and the debrief section runs.
  - `connector.bats`: the three sessions run through the runner.
- **Eval case:** `slack-capture` in `system/tests/golden/ingest/`, a capture file with one fact, one link and one uncertainty word. Phase B rule: a new input source ships with a case.
- **Gate:** with every extension off and with every extension on; the core budget test at its new measured value.
- **Live acceptance:**
  - on the server, a post in a watched channel that cancels a meeting reaches the alerts and Slack within one tick, with no session open;
  - a commitment in a group DM becomes an `owed` line;
  - a capture reaches the wiki within one intake tick.

**Done when:** for 5 weekdays the owner adds no hand annotations to the brief (11 on 2026-10-14), and every captured message reaches the wiki or the Now page within one intake tick.

## 5. Out of scope

- The partner mail guard (§2 decision 8).
- Sent-mail bodies: v1 classifies from the subject and snippet. Reading a body needs `get_thread`, a second Gmail session per thread.
- Asks to the owner that the owner accepted with a reply that states no task ("will do"). The sweep reads only the owner's own words; the thread context would need `include_context`, a later step.
- Tickets and a personal inbox as triage sources, a "draft was sent" check, a dashboard: the other #135 lines. They stay on the roadmap.
- Commands from Slack (`now:`, `order:`), file downloads, and edits or deletions after capture.
- Rewriting the briefing during the day: two-machines §5.6 still holds.
