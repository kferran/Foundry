# Intraday brief: the day's sessions, meetings and chat threads

**Date:** 2026-10-09
**Status:** Approved by the owner, 2026-10-09.
**Issue:** #94, part B. Part A (telemetry) is `2026-10-09-telemetry-shared-services-design.md`.
**Builds on:** two-machines design §3.1 (roles) and §5.6 (non-destructive extraction); meetings design (meeting notes, `owner_names`); delivered-work design §3.2 (the confined connector fetch).

## 1. Problem

The briefing is written at 06:00 and not touched again until the debrief. On the day this issue was filed, a teammate reported an outage in chat at 11:12. It was investigated in a Claude session on the client and escalated by email, and none of it reached the briefing until the owner asked a session to add it by hand.

| Source | Captured today | Reaches the briefing |
|---|---|---|
| Session digests (`system/hooks/memory_capture.sh`) | server and standalone sessions; `/setup` never installs the hooks on a client (`setup.md`, phase 5a) | the debrief (the model reads whole digests from `debrief_prep.sh` `digests.md`) and the wiki; never the briefing |
| Meetings | imported by intake during the day (`system/logs/meetings-<YYYY-MM>.jsonl`, `kind: imported`) | the owner's open action items in the next morning's brief |
| Chat threads | not read | never |

## 2. Owner decisions (2026-10-09)

1. Updates come from captured data, not from a rule each session must remember ("digest-driven").
2. Sources: session digests, meetings imported today, and chat threads the owner is in.
3. Digest follow-ups and threads waiting on the owner's reply become `- [ ]` items that carry forward until ticked or dropped.

## 3. Design

### 3.1 `briefings/<date>.today.md`

Intake never rewrites a briefing (two-machines §5.6). The updates therefore go to a separate file that only the server writes, embedded in the briefing the way the debrief is.

- **Created** by the writer (§3.3) with its first entry of the day. It is append-only: a run adds lines at the end and never changes or removes a line.
- **Each entry ends with a blank line.** On the client the owner ticks a checkbox on line N; on the server the writer appends after the blank line N+1. Because one unchanged line separates the two changes, git merges them without a conflict. A sync test pins this.
- **Template:** `system/templates/daily-briefing.md` gains `## 🕑 Today so far` and `![[{{date}}.today]]`, placed before `## 📝 Notes`. `/brief` keeps that line, and adds the section to an existing briefing that lacks it.
- **Archive:** `brief_prep.sh` moves `<date>.today.md` along with its briefing (the archive regex `(\.debrief)?` becomes `(\.debrief|\.today)?`).
- **Schema:** `system/schemas/today.md` (`type: today`). `briefings/` is schema-checked, and a file without frontmatter fails lint (`missing frontmatter`), as `<date>.debrief.md` would without `system/schemas/debrief.md`.

### 3.2 Entries

Entries are chronological, and each starts with the local time and a kind. Copied text is folded to one line, cut at 200 characters after masking with `redact_credentials` (part of the telemetry identifiers change), and stripped of `[[`, `]]` and leading `- [`, so a copied line cannot become a link or a checkbox.

```markdown
- 11:41 **session** Traced the 404s to the partner's QA endpoint; posted evidence in the thread ([[2026-10-09-1141-1a2b3c4d-traced-the-404s]])
  - delivered: message — thread reply with traces and query

- [ ] Confirm the endpoint returns OK after the partner's fix _(follow-up, session 11:41)_

- 10:09 **meeting** [[2026-10-09-1009-pilot-sync]]: 2 decisions; yours: "Send the capability doc"

- 11:52 **chat** #uat-testing: "UAT is currently not working" (you replied) https://example.slack.com/archives/C1/p1

- [ ] Reply in #team-x: "Can you confirm pre-prod…" (Blake Sample, 14:05) https://example.slack.com/archives/C2/p2 _(chat)_

```

- **session.** One entry per digest: the first sentence of Outcome, with each Delivered bullet as a `delivered:` sub-bullet. The link is the digest note. Each Follow-ups bullet becomes its own `- [ ] … _(follow-up, session HH:MM)_` entry. A follow-up whose normalized text (case-folded, whitespace folded) is already in today's file is skipped.
- **meeting.** One entry per meeting imported today: the note link, the number of bullets under `## Decisions`, and the owner's open action items quoted. Ownership is decided by `owner_names`, the same rule `meeting_actions.py` uses. Meeting actions stay plain text, because they are ticked on the meeting note.
- **chat.** One entry per thread the owner posted in or was mentioned in today, and one per DM or group DM conversation with a message today. Top-level DM messages are grouped by conversation (most DMs have no threads, so grouping them by message would leave every DM waiting on a reply); the entry links that conversation's earliest top-level message of the day. If someone mentioned the owner after the owner's last message in that thread, the entry is a `- [ ] Reply in …` line instead. Each thread is written once a day: a later "needs reply" for a thread already listed adds the `- [ ]` line only.

### 3.3 Writer: `system/scripts/today_log.py`

A deterministic script that makes no model call. Intake runs it on the server and on standalone vaults after `process_digests()` in each tick, inside the `intake.lock` block. Following the meetings step, it is wrapped so that an exception becomes an alert and the tick continues, and it takes `run.lock` with timeout 0, so a busy lock waits for the next tick. It returns at once on a client.

- **Digests.** It reads `SELECT path, created_at, partition FROM v_session_digest WHERE substr(created_at,1,10) = <today>`, the query `debrief_prep.sh` uses. That covers digests in `raw/<p>/notes/` and in `raw/<p>/archive/`. Outcome and Follow-ups come from `vaultlib.recall.digest_sections`; the Delivered section gets a parser in the same module.
- **Meetings.** It reads today's `kind: imported` records from `system/logs/meetings-<YYYY-MM>.jsonl`, each with its `note` path. A record whose note does not exist yet is retried on the next tick, and no ledger entry is written for it.
- **Chat.** It reads `system/logs/inputs/<date>/chat.jsonl` (§3.5).
- **Ledger.** `system/logs/today_log.jsonl` holds one record per written item: `kind`, `source` (a path or thread link), and the `sha256` of the source. An item already in the ledger is never written again. A digest that changes after it was written is not written twice.
- **Partitions.** Only `work` sources go to the briefing, matching the brief. Sources with `personal` and `shared` partitions are skipped.
- **Failures.** An unreadable source is skipped and raises one alert a day under the key `[today]`.

### 3.4 Digests from client sessions

`/setup` phase 5a offers the memory hooks on a client too (today it says "On a client, never install the hooks"). The hook code needs no change: `mem_env_ok` checks only the session environment.

**Open decision D1 (owner).** `.gitignore:11` ignores `raw/**` (template design "Raw inputs in git": compiled `wiki/` is the durable record), so a client digest never reaches the server. Client digests need one of:
1. un-ignore `raw/*/notes/*.md`: pending digests (already redacted at capture) enter the private origin's history;
2. leave §3.4 out: client sessions stay invisible to the brief.

Plan 1 builds everything else first and stops before its client-digest task until the owner decides.

### 3.5 Chat fetch: `system/scripts/chat_fetch.sh` and `chat_threads.py`

These follow `jira_fetch.sh` and `jira_handoffs.py` (delivered-work design §3.2).

- **Session.** One confined `claude -p` session, allowed only the Slack connector's search tool (`mcp__claude_ai_Slack__slack_search_public_and_private`). `confine_deny --strict` denies every other Slack tool by name, the session has a timeout, and it writes `system/logs/chat_fetch-<YYYY-MM>.jsonl` and raises at most one `[chat]` alert a day. The exit codes match `jira_fetch.sh`: 0, 1, 2, 3, 4, 6, 7 and 127.
- **Query.** It is built only from settings: `chat_user_id`, which leaves the fetch off while empty. There are three searches, each `sort: timestamp`, `include_context: false`, `limit: 20`, following `cursor` until the last page:
  1. from the owner: `filters: "from:<@ID> on:<date>"`;
  2. mentions: `keywords: ["<@ID>"]`, `filters: "on:<date>"` (a `<@ID>` *filter* matches every message of the day: probed 2026-10-09);
  3. DMs and group DMs: `filters: "is:dm on:<date>"`.
- **Result shape (probed 2026-10-09).** The tool returns `{"results": "<markdown>", "pagination_info": "<text>"}`. Each message is a `### Result N of M` block with `Channel:`, `From: … (ID: U…)`, `Time:`, `Message_ts:`, `Permalink: [link](…)` and `Text:` lines. A reply's permalink carries `?thread_ts=<ts>&cid=<channel>`; a top-level message's does not, and its thread key is its own `Message_ts`.
- **Checks.** `chat_threads.py extract` checks the stream: only the allowed tool, only the queries built from settings, no errors, and a result in the expected shape (fail closed). It groups the results by thread and writes one JSON line per thread: `link`, `channel`, `first_line`, `last_author`, `last_time`, `needs_reply`. Message text is masked and cut, and none of the model's own words are used.
- **Large results.** A tool result too large for the stream is replaced by a `<persisted-output>` marker. The checker fails closed on it; if the probe shows the result reaches the stream only as text, `limit` drops until a page fits, and the plan stops at its probe task if none does.
- **Schedule.** `foundry-chat.timer` runs on the server and standalone vaults, `OnCalendar=Mon..Fri *-*-* 08..18:30:00 {{TZ}}`: hourly like the meetings timer, at half past so the two connector sessions do not start together. It is installed only when `chat_user_id` is set. Because `--update` does not install new units (#35), `/setup` installs it.
- **Setup.** A new phase, 6d Chat, follows the shape of 6c: it asks for the owner's chat user ID and runs `chat_fetch.sh --check`. A chat failure never blocks setup.

### 3.6 Carry-forward

`carry_forward.py <date>` also reads the `- [ ] ` lines of the earlier briefing day's `<day>.today.md` and of every later day's `.today.md` up to yesterday (in place or archived), so a day with no briefing does not drop its follow-ups. It prints them like section 1 items, with `_(open since <that day>)_` and the single-stamp rule from #84. The next brief lists them under **Carried forward**.

### 3.7 Debrief

`debrief_prep.sh` writes `system/logs/inputs/<date>/today_open.md` with the open `- [ ] ` lines of `<date>.today.md`. `/debrief` lists them under an **Open from today** heading inside section 1 (a new numbered section would break the rule that `### 6. Delivered Today` is last), or writes "None." Delivered Today is unchanged.

## 4. Out of scope

- Server writes to the briefing itself, because §5.6 still holds.
- Email. A later Gmail fetch can reuse §3.5.
- Rewriting or reordering `<date>.today.md`. The owner corrects an entry by ticking `[x]` or dropping `[-]`.

## 5. Tests and bound tools

- **pytest.** `test_today_log.py` covers entries, masking and cutting, link and checkbox stripping, follow-up dedupe, ledger idempotence, the partition wall, an unreadable source, a meeting note not yet present, and the client no-op. `test_recall.py` covers the Delivered parser. `test_carry_forward.py` covers `.today.md` lines, including an archived day. `test_chat_threads.py` covers the stream checks, modeled on `test_jira_handoffs.py`. `test_intake.py` checks that the writer runs after digests and that a writer failure is an alert while the tick continues.
- **bats.** `chat.bats` runs the fetch with `stub_claude_meetings`. `sync.bats` checks that a client tick on an entry merges cleanly with a server append. `prep.bats` checks the archive of `.today.md` and `today_open.md`. `commands.bats` checks the `/brief`, `/debrief` and `/setup` 5a and 6d text and the briefing template. `units.bats` checks `foundry-chat.timer`.
- **The gate.** `system/scripts/verify_setup.sh`.

## 6. Plans

1. **Intraday brief:** §3.1 to §3.4, §3.6 and §3.7.
2. **Chat threads:** §3.5 and its entries in §3.2. Depends on plan 1.

## 7. Open questions

1. ~~Do search results carry thread links?~~ Yes (probed 2026-10-09; §3.5 "Result shape"). Plan 2's first task still captures one real `claude -p` stream, to see whether the result reaches `tool_use_result` as `structuredContent` or as text content only, and the checker reads whichever it is.
2. ~~Should chat cover private channels and DMs?~~ Yes (owner, 2026-10-09): the fetch uses `slack_search_public_and_private`.
