# Meetings: Transcripts into The Core (Plan 11)

**Date:** 2026-10-05
**Status:** Approved in brainstorming (2026-10-05); pending independent review
**Extends:** `2026-09-30-vault-template-design.md` (§6.3 run ledger, §6.4 intake, §6.20 publish), `2026-10-03-two-machines-design.md` (§4 commit history, §5 sync), `2026-10-03-calendar-connector-design.md` (the confined fetch pattern), `2026-10-05-foundry-rename-design.md` (capabilities)
**Roadmap:** Plan 11, parts A (meetings core from text transcripts) and B (fetch from Google Drive). Parts C (recordings to text) and D (Zoom and Teams fetch) are later plans.

## 1. Problem and decisions

Meetings, scheduled or impromptu, produce transcripts and Gemini notes that never reach the vault. Today a transcript dropped in `raw/inbox/` on the server is ingested like any text, with no meeting structure, no link to its calendar event, and no action tracking; nothing fetches Gemini notes; a client cannot hand a file to the server (`raw/` is not synced).

| Topic | Decision (user, 2026-10-05) |
|---|---|
| Sources | Google Meet with Gemini notes (fetched), and any platform's text transcript (dropped). Recordings and Zoom/Teams fetch are later plans |
| Outcomes | a meeting note in the wiki; action items tracked in the briefing; facts compiled into concepts; the full transcript kept and searchable |
| Transcripts | committed beside the meeting note (redacted), indexed, synced to the client |
| Partition | the calendar the event is on (config map), else the drop folder, else `/ingest` decides from the content |
| Model work | a script parses each meeting deterministically; one headless `/ingest` per meeting compiles facts into concepts |
| Actions tracked | every action item, from every meeting; the briefing lists the user's own first, then everyone else's grouped by owner |
| Fetch | a confined connector session (the calendar pattern), Drive `search_files` and `read_file_content` only, Doc text taken from the session's tool results; workdays hourly 08:00–18:00 plus a pre-step of the debrief |
| Seen tracking | no list of seen Docs: one timestamp file plus a lookup of existing meeting notes |

### 1.1 Probe results (2026-10-05, the user's calendar and Drive, shapes only)

- All meetings with a conference link over two weeks were Google Meet.
- Each Meet meeting with Gemini has one Google Doc titled `<event title> - YYYY/MM/DD HH:MM <TZ> - Notes by Gemini`; a meeting with no calendar event is titled `Meeting started YYYY/MM/DD HH:MM <TZ> - Notes by Gemini`.
- The Doc, read with `read_file_content`, holds in order: Quick notes; Full notes with `### Summary`, `### Decisions`, `### Next steps` (lines `- \[Owner, Owner\] Title: text`) and `### Details` (with timestamp links); then the Transcript (`## <title> - Transcript`, `### HH:MM:SS` sections, `**Speaker:** text` turns, ending `### Transcription ended after HH:MM:SS` and a footer).
- Calendar event attachments are not reliable: a recurring event carries a past instance's Doc. The fetch finds Docs by searching Drive, never through attachments.
- A Doc another person owns appears in the user's Drive as a shortcut whose metadata has no target ID; searching `mimeType = 'application/vnd.google-apps.document'` with the exact title among shared files finds the real Doc, which reads normally.
- About 4–7 Gemini Docs per workday.

## 2. Flow

```
Gemini Docs ── meetings_fetch.sh (confined claude -p) ──> raw/meetings/<doc id>.gdoc.md ──┐
Any transcript ── meetings/drop/{work,personal}/ (committed, synced) ───────────────────────┤
                                                                                          v
                                  intake: meeting_import.py (no model) ──> meeting run (publish gate, commit)
                                                                                          v
                                                       raw/<p>/meetings/<slug>.md ──> /ingest run (concepts)
```

### 2.1 Fetch: `system/scripts/meetings_fetch.sh`

Runs on `server` and `standalone` vaults when `meetings_enabled` is true; exits 0 and does nothing otherwise.

- **Confinement:** the calendar fetch's pattern (calendar spec §4): user settings loaded, `--permission-mode dontAsk`, `--allowedTools` the Drive connector's `search_files` and `read_file_content` only, the same deny list and broad-allow-rule refusal, `--output-format stream-json`, a turn and budget limit, a fresh working directory under `/tmp`. The tool-use check fails the fetch (exit 7, alert) on any other tool.
- **Window:** `system/logs/meetings.since` holds an ISO time; the session searches Docs whose title contains `Notes by Gemini`, `mimeType = 'application/vnd.google-apps.document'`, and `createdTime` after `.since` minus 24 hours. A missing `.since` means the last 24 hours.
- **Selection:** the session reads a Doc only when it was modified more than 10 minutes ago (Gemini may still be writing) and no meeting note records its ID (the script passes the known IDs for the window, found through the index: `v_meeting.source`). The prompt lists the Doc IDs to skip.
- **Text:** `meetings_extract.py` reads the stream and writes, for each `read_file_content` tool result, the `fileContent` exactly as returned to `raw/meetings/<doc id>.gdoc.md`, with the title and IDs in a small header. The model writes nothing a script uses except the tool calls.
- **Success:** `.since` is set to the fetch's start time only after every selected Doc was written. On any failure it stays, and the overlap catches up.
- **Exit codes** follow the calendar fetch's (0 ok, 1 claude error, 3 no connector, 6 connector error, 7 unexpected tool). `brief_prep.sh` and `debrief_prep.sh` read the last result line from `system/logs/meetings_fetch-<YYYY-MM>.jsonl` and add a "meetings" line to Unavailable Sources when the last fetch today failed.

### 2.2 Drops: `meetings/drop/<partition>/`

- A committed folder (with `.gitkeep` in `work/` and `personal/`), so a client's Obsidian Git or `/backup` carries a dropped file to the server. Accepted files: `.vtt`, `.srt`, `.txt`, `.md`; others are left in place and alerted once per file.
- On the server (and on a standalone vault), intake takes each file older than 60 seconds, imports it (§2.3) and deletes it; the next sync commit records the deletion. A client never imports.

### 2.3 Import: `system/scripts/meeting_import.py`

Called by the intake daemon each tick for `raw/meetings/*.gdoc.md` and `meetings/drop/**`. No model.

1. **Parse** (`vaultlib/meetings.py`): Gemini Docs into title, start (with zone), attendees (the Full notes' `Invited` names), summary, decisions, actions (`[Owners] Title: text`), details, transcript, and `complete` (the end marker `### Transcription ended after` is present). Plain transcripts (`.vtt`, `.srt`, `.txt`, `.md`) into transcript turns only; title from the file name, start from the file's first timestamp or modification time.
2. **Redact** with the existing `redact.py` before anything is staged.
3. **Match** a calendar event: today's and yesterday's events from the calendar fetch's TSV (`system/logs/inputs/<date>/calendar.tsv`), matched on start within 15 minutes and title (case and punctuation folded, `Meeting started …` never matches).
4. **Partition:** the matched event's calendar in `meeting_calendars`, else the drop folder, else unknown (§2.5).
5. **Duplicates:** a meeting whose calendar event, or start within 15 minutes and folded title, matches an existing meeting note is not imported again; a drop that duplicates a Gemini meeting is archived to `raw/archive/` with an alert line naming the meeting note.
6. **Stage and publish** through the existing gate as a run: `run_id` `<ts>-meeting-<rand4>`, ledger line with `command: "meeting"`, `system/logs/runs/<run_id>/publish.json`. It publishes `wiki/<p>/meetings/<date>-<slug>.md` and `wiki/<p>/meetings/<date>-<slug>.transcript.md` (§3). `commit_runs.py` commits it as `meeting(<p>): <title>` with the `Foundry-Command: meeting`, `Foundry-Run` and `Foundry-Role` trailers; the body lists the two paths. Meeting runs never call `claude` and do not count toward `HEADLESS_MAX_RUNS_PER_DAY`.
7. **Hand to compile:** writes `raw/<p>/meetings/<date>-<slug>.md` (schema `meeting_input`: the meeting note's path, partition, codebase when the title or attendees name a registered codebase, and the summary, decisions and details as body) for intake to ingest like a session digest.
8. On parse or schema failure: the source goes to `system/quarantine/meetings/` with a reason file, an alert, and the briefing lists it; other sources in the tick continue.

### 2.4 Compile: `/ingest` of a meeting input

Intake runs one `run_headless.sh ingest` per meeting input (meeting inputs are never batched). The ingest prompt gains a meeting rule: merge the meeting's facts and decisions into concept notes, link them to the meeting note, open the transcript note only when the summary and details leave a fact unclear, set `capability` on a concept only when the meeting assigns work, and never edit the meeting note's action lines.

### 2.5 Partition unknown

A Gemini Doc titled `Meeting started …` from a fetch has no calendar event and no drop folder. The import then publishes nothing yet: it writes the meeting input to `raw/inbox/meeting-<date>-<slug>.md` with the parsed fields in its frontmatter and keeps the transcript under `raw/meetings/pending/`. `/ingest` picks the partition from the content (falling back to `default_partition`) and publishes the meeting note itself from the parsed fields, unchanged. On a later tick the import finds a published meeting note whose `source` matches a pending transcript and publishes the transcript note in the same partition as its own meeting run.

### 2.6 Briefing and debrief

- `system/scripts/meeting_actions.py <date>` (run by `brief_prep.sh`) writes `system/logs/inputs/<date>/actions.md`: every unticked `- [ ]` action line in `wiki/*/meetings/*.md` (not transcripts), each with its meeting link and days open; lines naming any of `owner_names` first, then the rest grouped by owner.
- `/brief` puts the user's open actions under Active Objectives and the rest in a "Waiting on" block; `/debrief` lists today's meetings (`v_meeting` where `date` is today) under Execution Logs.
- The user ticks an action (`- [x]`) in Obsidian on either machine; sync carries it. The server never rewrites a published meeting note.

## 3. Schemas and config

- **`meeting`** (`system/schemas/meeting.md`, folders `wiki/work/meetings/`, `wiki/personal/meetings/`, `wiki/shared/meetings/`): `type` const; `title` string required; `date` date required; `start` datetime required; `partition` enum matches folder; `attendees` list of string; `source` string required (`gdoc:<id>` or `drop:<file name>`); `calendar_event` string; `transcript` link; `codebase` string; `capability` enum (the concept schema's values); `provenance`. Body: `## Summary`, `## Decisions`, `## Action items` (`- [ ] [Owner, …] Title: text`), `## Details`. The `.transcript.md` files in the same folders are not `meeting` notes.
- **`meeting_transcript`** (same folders, files matching `*.transcript.md`): `type` const; `meeting` link required; `partition` enum matches folder; `source` string required; `complete` bool (false when the Doc's end marker was missing); `provenance`. Body: the redacted transcript, one `**Speaker:** text` turn per line under `### HH:MM:SS` headings.
- **`meeting_input`** (`raw/<p>/meetings/` and their archive folders): `type` const; `meeting` link required; `partition`; `codebase`; `created_at` datetime.
- If a schema's `folders` cannot tell `*.transcript.md` from other notes in the same folder, the transcript notes live in `wiki/<p>/meetings/transcripts/` instead; the plan settles this from the schema code.
- **Config** (`system/config.md`, `system/config.example.md`, the config schema):
  - `meetings_enabled`: bool, default `false`; `/setup` asks on `server` and `standalone`.
  - `meeting_calendars`: map of calendar ID to partition; the primary calendar defaults to `default_partition`.
  - `owner_names`: list of the user's names as they appear in meeting notes.
- **Index:** `v_meeting` and `v_meeting_transcript` come from the schemas; `/query` searches both; `meetings/drop/` is excluded from the index.

## 4. Units

- `foundry-meetings.service` (oneshot, `ExecStart=meetings_fetch.sh`, `TimeoutStartSec` sized by the plan from the fetch's own limits) and `foundry-meetings.timer` (`OnCalendar=Mon..Fri *-*-* 08..18:00:00` in the config time zone, `Persistent=false`), installed only when `meetings_enabled` is true on `server` or `standalone`.
- The debrief unit gains `ExecStartPre=-…/meetings_fetch.sh` before its prep step when meetings are enabled (on a server, inside the sync drop-in's order: sync, fetch, prep).
- On a server, fetched files are imported by the next intake tick and committed by the next sync, like any run.

## 5. Failure handling

| Condition | Behavior |
|---|---|
| Connector missing or logged out; a tool outside the two Drive tools attempted | the fetch stops before any write (exit 3, 1 or 7), alerted once a day, Unavailable Sources says "meetings"; `.since` stays |
| A Doc modified in the last 10 minutes | skipped; the overlap catches it later |
| A Doc's text cut short (no end marker) | imported; the transcript note has `complete: false`; the briefing lists it |
| Parse or schema failure | that source quarantined with a reason, listed in the briefing; the rest continue |
| No calendar match and no drop folder | §2.5: `/ingest` picks the partition, `default_partition` as fallback |
| The same meeting twice | §2.3 step 5 |
| An ingest run fails | intake's retry and poisoning rules; the meeting note is already published, so its actions show |
| Secrets in a transcript | redacted before staging; only the redacted text is committed |
| A conflict on a meeting note | the two-machine conflict rules; the server never rewrites a published meeting note |

## 6. Tests

Hermetic: fixtures, stubs on `PATH`, no network, no `claude`. Bats ruling R1 and the tool floor apply.

- **pytest `test_meetings.py`** (parser and import): synthetic Gemini Docs (every section; no Decisions; cut short; `Meeting started …`), `.vtt`, `.srt`, `.txt`, `.md`; exact fields and action lines; calendar match on time and title; partition order; duplicates; redaction before staging; `complete: false`; the published notes pass their schemas; the run's ledger line, `publish.json` and commit subject; a meeting input for ingest; quarantine on a bad source; §2.5 pending transcript published after its meeting note appears.
- **pytest `test_meeting_actions.py`:** open, ticked and grouped items; the user's first; days open; transcripts ignored.
- **bats `meetings.bats`:** `meetings_fetch.sh` with a stubbed `claude` emitting a recorded stream: new Docs written with their exact text; known IDs passed as skips; `.since` advances only on success; an unexpected tool exits 7 with an alert; disabled config does nothing. Intake imports a drop and deletes it. Units: the meetings timer and the debrief pre-step only when enabled, only for `server` and `standalone`. Config schema accepts the new keys and rejects a bad partition in `meeting_calendars`.
- **commands.bats:** `/brief` and `/debrief` read the actions input and today's meetings; `/ingest`'s meeting rule; `/setup` asks about meetings.
- Every existing suite stays green (including the old-name and capability tests).

## 7. Live probe (during planning) and acceptance

- **Probe** (one confined `claude -p` fetch of one Doc, in a throwaway clone): the full `fileContent` appears in the stream's tool result; the deny list and tool-use check hold with the Drive connector; how a long Doc is cut short; the exact-title search finds a shortcut's target. If the tool result does not carry the full text, planning stops and the user chooses between this approach and a Drive API client.
- **Acceptance** (throwaway clones and a local bare origin, no units installed; the record holds shapes and counts, never meeting content):
  1. A fetch with a short `.since` window imports one or two of today's meetings: meeting and transcript notes published, a `meeting(<p>)` commit, then an `/ingest` that links concepts.
  2. A `.vtt` dropped in a client clone's `meetings/drop/work/` and pushed is imported by the server.
  3. A brief lists open actions, the user's first.
  4. An action ticked on the client and synced is gone from the next brief's list.

## 8. Out of scope

- Recordings (audio or video) to text: Plan 11 part C.
- Zoom and Teams fetch: part D, only if manual export proves tedious.
- Editing or closing actions anywhere but the meeting note's checkbox.
- Meetings on a client vault beyond dropping files and ticking actions.
