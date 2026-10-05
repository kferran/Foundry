# Meetings: Transcripts into The Core (Plan 11)

**Date:** 2026-10-05
**Status:** Approved in brainstorming (2026-10-05); revised after an independent review (rev 2)
**Extends:** `2026-09-30-vault-template-design.md` (§6.3 run ledger, §6.4 intake, §6.20 publish), `2026-10-03-two-machines-design.md` (§4 commit history, §5 sync), `2026-10-03-calendar-connector-design.md` (the confined fetch pattern), `2026-10-05-foundry-rename-design.md` (capabilities)
**Roadmap:** Plan 11, parts A (meetings core from text transcripts) and B (fetch from Google Drive). Parts C (recordings to text) and D (Zoom and Teams fetch) are later plans.

## 1. Problem and decisions

Meetings, scheduled or impromptu, produce transcripts and Gemini notes that never reach the vault. Today a transcript dropped in `raw/inbox/` on the server is ingested like any text, with no meeting structure and no action tracking; nothing fetches Gemini notes; a client cannot hand a file to the server (`raw/` is not synced).

| Topic | Decision (user, 2026-10-05) |
|---|---|
| Sources | Google Meet with Gemini notes (fetched), and any platform's text transcript (dropped). Recordings and Zoom/Teams fetch are later plans |
| Outcomes | a meeting note in the wiki; action items tracked in the briefing; facts compiled into concepts; the full transcript kept and searchable |
| Transcripts | committed beside the meeting note (redacted), indexed, synced to the client |
| Partition | a dropped file: its drop folder. A fetched meeting: `meetings_partition` (default `default_partition`). No calendar matching (rev 2: the brief's calendar file carries no calendar or event IDs and covers only the primary calendar at brief time) and no model step (rev 2: a run's partition is fixed before the model starts) |
| Model work | a script parses each meeting deterministically; one headless `/ingest` per meeting compiles facts into concepts |
| Actions tracked | every action item from every meeting; the briefing lists the user's own until ticked, and everyone else's for 14 days after the meeting |
| Fetch | a confined connector fetch (the calendar pattern), Drive `search_files` and `read_file_content` only, Doc text taken from the session's tool results; workdays hourly 08:00–18:00 |
| Seen tracking | no list of seen Docs: one timestamp file, the vault's own meeting notes and pending files, and a per-Doc failure count in the existing fetch log |

### 1.1 Probe results (2026-10-05, the user's calendar and Drive, shapes only)

- All meetings with a conference link over two weeks were Google Meet.
- Each Meet meeting with Gemini has one Google Doc titled `<event title> - YYYY/MM/DD HH:MM <TZ> - Notes by Gemini`; a meeting with no calendar event is titled `Meeting started YYYY/MM/DD HH:MM <TZ> - Notes by Gemini`. Event titles can contain ` - `, so the title is parsed from the right.
- The Doc, read with `read_file_content`, holds in order: Quick notes; Full notes with an `Invited` line, `### Summary`, `### Decisions`, `### Next steps` (lines `- \[Owner, Owner\] Title: text`) and `### Details` (with timestamp links); then the Transcript (`## <title> - Transcript`, `### HH:MM:SS` sections, `**Speaker:** text` turns, ending `### Transcription ended after HH:MM:SS` and a footer).
- Calendar event attachments are not reliable: a recurring event carries a past instance's Doc. The fetch finds Docs by searching Drive.
- A Doc another person owns appears in the user's Drive as a shortcut with no target ID in its metadata; searching with `mimeType = 'application/vnd.google-apps.document'` finds the real Doc among shared files, and it reads normally.
- About 4–7 Gemini Docs per workday.

## 2. Flow

```
Gemini Docs ── meetings_fetch.sh (confined claude -p) ──> raw/meetings/<doc id>.gdoc.md ──┐
Any transcript ── meetings/drop/{work,personal}/ (committed, synced) ───────────────────────┤
                                                                                          v
             intake tick: meeting_import.py (no model, under run.lock) ──> meeting run (gate, commit)
                                                                                          v
                         raw/<p>/notes/<date>-<HHMM>-<slug>.meeting-input.md (solo) ──> /ingest run
```

### 2.1 Fetch: `system/scripts/meetings_fetch.sh`

Runs on `server` and `standalone` vaults when `meetings_enabled` is true; exits 0 and does nothing otherwise. It takes its own `flock -n system/meetings.lock` (busy: exit 0, nothing done).

- **Confinement:** the calendar fetch's block (calendar spec §4), refactored into a shared helper that takes the allowed tools, the connector server prefix and the list of every other tool on that server to deny: user settings loaded, `--permission-mode dontAsk`, `--allowedTools` the Drive connector's `search_files` and `read_file_content` only, every other Drive tool denied by name (including `create_file`, `update_file`, `copy_file`, `share_file`, `trash_file`, `download_file_content`, `get_file_permissions`, `list_recent_files`, `get_file_metadata`), the broad-allow-rule refusal, `--output-format stream-json`, a turn and budget limit, a fresh working directory under `/tmp`. The tool-use check fails the session (exit 7, alert) on any other tool.
- **Two steps, one Doc per read session:**
  1. A search session lists Docs: title contains `Notes by Gemini`, `mimeType = 'application/vnd.google-apps.document'`, `createdTime` after `.since` minus 24 hours (missing `.since`: the last 24 hours). `meetings_extract.py` takes the search tool result from the stream (ID, title, modifiedTime).
  2. For each listed Doc, at most 10 per fetch, that passes the filter below, one read session calls `read_file_content` on that ID only.
- **Filter (script side):** keep a Doc only when its title matches `* - Notes by Gemini`, its `modifiedTime` is more than 10 minutes old, its ID is not a `source` in `v_meeting`, not pending under `raw/meetings/`, not under `system/quarantine/meetings/`, and it has failed fewer than 3 reads (counted from `system/logs/meetings_fetch-<YYYY-MM>.jsonl`; the third failure is alerted once and the Doc skipped from then on).
- **Text:** `meetings_extract.py` writes a read session's `read_file_content` result to `raw/meetings/<doc id>.gdoc.md` (a small header with the ID, title and modifiedTime, then `fileContent` exactly as returned), atomically (temp file, then rename), and only when the result's ID is the one requested. The model writes nothing a script uses except tool calls; any other result in the stream is ignored.
- **`.since`** is set to the fetch's start time when the search session succeeded, whether or not every read did (failed reads are retried through the overlap and capped by the failure count).
- **Exit codes** follow the calendar fetch's: 0 ok; 1 claude error; 3 no connector; 4 timeout; 6 connector error; 7 unexpected tool; 127 no `claude`. Exit 3 and 6 are read from the stream's tool results (this session has no structured output). Each session appends one result line to `meetings_fetch-<YYYY-MM>.jsonl` (time, step, Doc ID or `search`, exit, reason). `brief_prep.sh` and `debrief_prep.sh` add a "meetings" line to Unavailable Sources when the last search today failed.

### 2.2 Drops: `meetings/drop/<partition>/`

- A committed folder with `work/` and `personal/` (each with a `.gitkeep`), so a client's Obsidian Git or `/backup` carries a dropped file to the server. Accepted files: `.vtt`, `.srt`, `.txt`, `.md`.
- `.githooks/pre-commit` rejects a staged file under `meetings/drop/` with any other extension, or one in which `redact.py` finds a secret (the hook names the file and the reason). This runs on the client through Obsidian Git, so an unredacted secret never reaches the private origin through a drop.
- On the server and on a standalone vault, the intake tick takes each drop older than 60 seconds and imports it (§2.3). A client never imports.

### 2.3 Import: `system/scripts/meeting_import.py`

Called by the intake daemon each tick, before inbox and digest processing, for `raw/meetings/*.gdoc.md` and `meetings/drop/**`. No model. It takes `run.lock` like `run_headless.sh` (waiting up to 600 seconds; busy: alert once and try next tick) and is not stopped by the daily cap.

For each source, in this order, so a crash at any point is completed by the next tick:

1. **Parse** (`vaultlib/meetings.py`):
   - Gemini Docs: title, start (date and time from the title, zone from the config timezone), attendees (the `Invited` names; when they cannot be split, the transcript's speakers), summary, decisions, actions (`[Owners] Title: text`), details, transcript turns, and `complete` (the end marker `### Transcription ended after` is present).
   - Plain transcripts (`.vtt`, `.srt`, `.txt`, `.md`): transcript turns only; title from the file name; start from the file's first cue time on its modification date, else the modification time.
2. **Redact** the parsed text fields with `redact.py`. The frontmatter (`source` with the Doc ID, title, start) is built from the unredacted header, so the ID survives; Drive links inside the body are redacted and lost.
3. **Partition:** a drop's folder; a fetched Doc's `meetings_partition`.
4. **Name:** `<date>-<HHMM>-<slug>` from the start and the folded title.
5. **Duplicate check:**
   - A meeting note with the same `source` exists (an earlier run published it): skip to step 7.
   - A meeting note with a start within 15 minutes and the same folded title exists from the other source kind: a Gemini Doc is preferred. If the existing note came from a drop and this is the Gemini Doc, the Doc is imported and the briefing lists both notes as a possible duplicate; if the existing note came from the Gemini Doc and this is a drop, the drop is archived to `raw/archive/` with an alert line naming the meeting note.
6. **Stage and publish** through the existing gate as its own run: `run_id` `<ts>-meeting-<rand4>`; snapshot targets the two exact paths below; ledger line with `command: "meeting"`; `system/logs/runs/<run_id>/publish.json`. It publishes `wiki/<p>/meetings/<name>.md` (`meeting`) and `wiki/<p>/meetings/<name>.transcript.md` (`meeting_transcript`). The gate stamps `provenance: [headless]` on both. No decisions file is needed (not an ingest run).
7. **Hand to compile:** write `raw/<p>/notes/<name>.meeting-input.md` (`meeting_input`: the meeting note's link, partition, `created_at`, and the summary, decisions and details as body) atomically, and add its sha256 to `system/logs/intake_solo.json` before the file is old enough for intake, so intake ingests it alone. A meeting input that already exists for this note is not written again.
8. **Remove the source:** delete `raw/meetings/<id>.gdoc.md`, or the drop file (the next sync commit records the deletion).
9. On a parse or schema failure: the source moves to `system/quarantine/meetings/` with a reason file (unredacted, local only, never committed), an alert, and a briefing line; other sources in the tick continue.

Changes this needs in existing code:
- `vaultlib/publish.py` `RUN_ID` and `commit_runs.py`'s run-id pattern accept `meeting`.
- `commit_runs.py` `message()` gains a `meeting` branch: subject `meeting(<p>): <title>` (partition from the ledger line, title from the published note, control characters stripped, under 72 characters with an ellipsis), body listing the two paths, trailers `Foundry-Command: meeting`, `Foundry-Run`, `Foundry-Role`.
- `run_headless.sh`'s daily-cap count excludes `command: "meeting"`.
- `vaultlib/publish.py` `_check` rejects any ingest run that stages a file of type `meeting` (so no model run ever rewrites a meeting note, and the user's ticks are never overwritten by the server).

### 2.4 Compile: `/ingest` of a meeting input

A meeting input lives in `raw/<p>/notes/`, so intake ingests it like a session digest, alone because its sha is in `intake_solo.json`; `run_headless.sh`, intake's batching and `--retry` need no change. The ingest prompt gains a meeting rule:
- merge the meeting's facts and decisions into concept notes, and put the meeting note (not the input) in each concept's `sources`, so the meeting note shows them as backlinks;
- open the transcript note only when the summary and details leave a fact unclear;
- set `capability` on a concept only when the meeting assigns work;
- never stage the meeting note or its transcript (the gate refuses it);
- a `wiki/shared/` concept never cites a work or personal meeting (the partition wall).

### 2.5 Briefing and debrief

- `system/scripts/meeting_actions.py <date>` (run by `brief_prep.sh`) writes `system/logs/inputs/<date>/actions.md` from the unticked `- [ ]` lines under `## Action items` in notes listed by `v_meeting` (never transcripts, never `status: deprecated`): lines whose bracketed owners include one of `owner_names` (case-folded, whole entries only) first, each with its meeting link and days open; then everyone else's, grouped by owner, only for meetings in the last 14 days.
- `brief.md` lists `actions.md` as an input: the user's open actions under Active Objectives, the rest in a "Waiting on" block; it also lists any "possible duplicate" and quarantined meetings. `/debrief` lists today's meetings (`v_meeting` where `date` is today) under Execution Logs.
- The user ticks an action (`- [x]`) in Obsidian on either machine; sync carries it.

## 3. Schemas, config and index

- **`meeting`** (`system/schemas/meeting.md`, folders `wiki/work/meetings/`, `wiki/personal/meetings/`): `type` const; `title` string required; `date` date required; `start` datetime required; `partition` enum `work|personal` matches folder; `attendees` list of string; `source` string required (`gdoc:<id>` or `drop:<file name>`); `transcript` link required; `codebase` string; `status` enum `canonical|deprecated` default `canonical`; `provenance`. Body: `## Summary`, `## Decisions`, `## Action items` (`- [ ] [Owner, …] Title: text`), `## Details`.
- **`meeting_transcript`** (same folders; the import names these files `*.transcript.md`; the validator picks the schema by `type`, so both schemas share the folders without code changes): `type` const; `meeting` link required; `partition` matches folder; `source` string required; `complete` bool; `provenance`. Body: the redacted transcript, one `**Speaker:** text` turn per line under `### HH:MM:SS` headings.
- **`meeting_input`** (folders `raw/work/notes/`, `raw/personal/notes/` and their archives, shared with `session_digest`): `type` const; `meeting` link required; `partition` matches folder; `created_at` datetime required.
- **Config** (`system/config.md`, `system/config.example.md`, the config schema):
  - `meetings_enabled`: bool, default `false`; `/setup` asks on `server` and `standalone`, and checks the Drive connector the way phase 6 checks the calendar.
  - `meetings_partition`: enum `work|personal`, default `default_partition`; where fetched meetings go.
  - `owner_names`: list of the user's names as they appear in meeting notes.
- **Index:** `v_meeting` and `v_meeting_transcript` come from the schemas. `raw/meetings/` and `meetings/drop/` join `NOT_INDEXED`. `related()` skips `meeting_transcript` notes unless the caller asks for that type; `/query` asks for it, so transcripts are searchable without crowding ingest's context search.

## 4. Units

- `foundry-meetings.service` (oneshot, `ExecStart=…/meetings_fetch.sh`, `TimeoutStartSec` sized by the plan as the connector listing plus one search session plus ten read sessions plus kill margin) and `foundry-meetings.timer` (`OnCalendar=Mon..Fri *-*-* 08..18:00:00 {{TZ}}`, `Persistent=false`).
- Installed only on `server` and `standalone` when `meetings_enabled` is true; `install_units.sh` reads the key with `vault_index.py field` and adds the pair to that role's unit list. The unit writes only gitignored files, so it gets no sync drop-in.
- No debrief pre-step: the 17:00 fetch and the next intake ticks bring the afternoon's meetings in before the 17:00 debrief writes, and later ones reach the next brief.

## 5. Failure handling

| Condition | Behavior |
|---|---|
| Connector missing or logged out; a tool outside the two Drive tools attempted | the session stops before any write (exit 3, 6 or 7), alerted once a day; Unavailable Sources says "meetings"; `.since` stays when the search failed |
| A Doc modified in the last 10 minutes | skipped; the 24-hour overlap catches it later |
| A read fails | retried at later fetches; after 3 failures alerted once and skipped |
| A Doc's text cut short (no end marker) | imported; the transcript note has `complete: false`; the briefing lists it |
| Parse or schema failure | that source quarantined with a reason, listed in the briefing; the rest continue |
| The same meeting twice | §2.3 step 5 |
| A crash mid-import | the next tick completes the remaining steps (§2.3 order) |
| An ingest run fails | intake's retry and poisoning rules; the meeting note is already published, so its actions show |
| Secrets in a transcript | fetched text redacted before staging; drops refused by the pre-commit hook when they hold one. Quarantined sources keep unredacted text locally and are never committed |
| A conflict on a meeting note | the two-machine conflict rules; no server run rewrites a published meeting note |

## 6. Tests

Hermetic: synthetic fixtures (no real meeting content), stubs on `PATH`, no network, no `claude`. Bats ruling R1 and the tool floor apply. `meetings.bats` is a new gated suite (17 suites).

- **pytest `test_meetings.py`** (parser and import): synthetic Gemini Docs (every section; no Decisions; cut short; `Meeting started …`; an event title containing ` - `; `Invited` names that cannot be split), `.vtt`, `.srt`, `.txt`, `.md`; exact fields and action lines; the Doc ID surviving redaction while a secret in the body is redacted; partition by drop folder and by `meetings_partition`; duplicates both ways; the `<date>-<HHMM>-<slug>` names for two same-title meetings on one day; the run's ledger line, `publish.json` and commit subject; a meeting input in `raw/<p>/notes/` with its sha in `intake_solo.json`; a crash after publish completed on the next call; quarantine on a bad source.
- **pytest for existing code:** `RUN_ID` and `commit_runs.py` accept `meeting` runs and build the subject; the daily cap ignores meeting runs; the gate refuses an ingest that stages a `meeting` note; `related()` skips transcripts unless asked; `raw/meetings/` and `meetings/drop/` are not indexed.
- **pytest `test_meeting_actions.py`:** open, ticked and grouped items; the user's first (case-folded bracket matches only); others' hidden after 14 days; transcripts and deprecated notes ignored.
- **bats `meetings.bats`:** `meetings_fetch.sh` with a stubbed `claude` emitting synthetic recorded streams: search then one read per Doc; the filter (title, age, known, pending, quarantined, failure count); a read result whose ID was not requested is dropped; `.since` advances on a good search; an unexpected tool exits 7 with an alert; a busy lock exits 0; disabled config does nothing. Intake imports a drop and deletes it. The pre-commit hook refuses a drop with a bad extension or a secret. Units: the meetings timer only when enabled, only for `server` and `standalone`; `systemd-analyze verify` passes.
- **commands.bats:** `/brief` reads `actions.md`; `/debrief` lists today's meetings; `/ingest`'s meeting rule; `/setup` asks about meetings and checks the Drive connector.
- Every existing suite stays green, including the old-name and capability tests.

## 7. Live probe (during planning) and acceptance

- **Probe** (confined `claude -p` sessions in a throwaway clone): the search result and a read result appear in full in the stream's tool results; the deny list and tool-use check hold with the Drive connector; how a long Doc is cut short, with and without `MAX_MCP_OUTPUT_TOKENS` raised; how `Invited` names are delimited in the text. If a tool result does not carry the full text, planning stops and the user chooses between this approach and a Drive API client.
- **Acceptance** (throwaway clones and a local bare origin, no units installed; the record holds shapes and counts, never meeting content):
  1. A fetch with a short `.since` window imports one or two of today's meetings: meeting and transcript notes published, a `meeting(<p>)` commit, then a solo `/ingest` that puts the meeting note in concepts' `sources`.
  2. A `.vtt` dropped in a client clone's `meetings/drop/work/` and pushed is imported by the server.
  3. A brief lists open actions, the user's first.
  4. An action ticked on the client and synced is gone from the next brief's list.

## 8. Docs

README (machine roles and the vault layout name `meetings/drop/`), the `CLAUDE.md` directory map, `/setup`'s client notes (drop transcripts into `meetings/drop/<partition>/`), and the roadmap's Plan 11 row.

## 9. Out of scope

- Recordings (audio or video) to text: Plan 11 part C.
- Zoom and Teams fetch: part D, only if manual export proves tedious.
- Matching meetings to calendar events.
- Editing or closing actions anywhere but the meeting note's checkbox.
