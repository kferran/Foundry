# Phase D: Capture and the Intraday Picture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `intraday` extension. A 30-minute weekday watch reads the listed channels in full, the owner's own messages, sent mail, the capture channel and the calendar. Each tick appends to `briefings/<date>.today.md`, writes Now lines for deadlines, blocks and commitments, alerts at once on meeting changes and incidents, and drops captures into `raw/inbox/`.

**Architecture:** One tracked extension, `extensions/intraday/`, off until listed in `extensions:`. Each tick runs three confined connector sessions (Slack search, Gmail search, Calendar list). The model only classifies messages; links, times and capture text come from the tool results, checked by `watchlib`. A deterministic writer, the manifest's `tick`, appends to the today file. Core changes only for two loader generalizations and one archive regex.

**Tech Stack:** Bash, Python (stdlib), bats, pytest, systemd units.

**Spec:** `docs/superpowers/specs/2026-10-19-phase-d-intraday-design.md`

## Global Constraints

- Follow the `triage_fetch.sh` / `vaultlib/triage.py` pattern for every session: `connector_run`, one tool per session, the strict deny list, the checker compares each call's whole input dict, fail closed.
- Model words reach only `what` (redacted, cut at 160); links, times and captured text come from results.
- Every script exits 0 at once on a client.
- Core changes: the debrief loader, alert severity from the manifest, the archive regex. Raise the core line budget by exactly the measured lines of the first two, with a comment naming the rule (spec §2 decision 10).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- CHANGELOG line under the merge date ending `(#PR)`.
- Gate: `system/scripts/verify_setup.sh --require-suites`, with every extension off and with every extension on.

## Review Focus

1. **Model words stay data:** no Now line, alert or today-file line takes a link, date or capture text from the model's output.
2. **No double lines with triage:** the evidence dedupe holds for a message triage already listed.
3. **The today file never conflicts:** only the server writes it; the client never runs the writer.
4. **Core budget:** only the two loader changes raise it.

---

### Task 1: Probe the Slack and Gmail queries (done 2026-10-19)

**Files:** `docs/superpowers/spikes/2026-10-19-watch-probe.md`.

- [x] Repeated `in:` is an OR; group DMs use `channel_types: "mpim"`; `from:<@id>` covers every channel type, so `watch_user_id` is a setting; Gmail `search_threads` gives subject and snippet only. The spec carries the results.

### Task 2: Core loader generalizations

**Files:** `system/scripts/debrief_prep.sh`, `system/scripts/vaultlib/extensions.py`, `system/scripts/vaultlib/alerts.py`, `system/scripts/brief_prep.sh`, `system/tests/prep.bats`, `system/tests/python/test_alerts.py`, `system/tests/vault_integrity.bats`.

- [ ] Write failing tests:
  - an extension `debrief/prep.sh` writes its section file through `debrief_prep.sh`;
  - a manifest `alert_tags` entry `{tag: watch, severity: now}` makes `severity()` return `now`, and a bare string stays `brief`;
  - a `<date>.today.md` archives with its briefing.
- [ ] Implement: `extensions.py debrief` (mirror `brief`); `alerts.severity` reads extension tags with severity; the archive regex becomes `(\.[a-z]+)?`.
- [ ] Measure core lines; set the budget to the measured count, with the comment.
- [ ] Run `prep.bats`, the alerts pytest, `vault_integrity.bats`. Commit.

### Task 3: The extension skeleton and config

**Files:** `extensions/intraday/extension.md`, `schemas/config.md`, `schemas/today.md`, `units/foundry-watch.{service,timer}.in`, `tests/`.

- [ ] Failing tests: `extensions.py check` accepts the manifest; the config keys validate (spec §3.8); `units.bats` renders the timer only while on, never on a client, `OnCalendar=Mon..Fri *-*-* 08..17:15,45:00 {{TZ}}`.
- [ ] Write the manifest, the schemas and the units. Run the tests. Commit.

### Task 4: Queries and the stream checker (`watchlib`)

**Files:** `extensions/intraday/scripts/watchlib/{query,check}.py`, tests.

- [ ] Failing pytest:
  - the Slack queries are built from settings and cursors as the probe found (repeated `in:`, an `mpim` query, `from:<@watch_user_id>`, an `after:<date>` filter on each);
  - the result parser reads the channel, group DM and DM variants of a result block;
  - the Gmail input (`in:sent`, `THREAD_VIEW_MINIMAL`, `internalDate` against the cursor) and the Calendar input;
  - the checker refuses another tool, an altered input or a `<persisted-output>` marker;
  - an item whose `(channel_id, ts)` is not in its query's results is dropped;
  - the 5-page cap alerts once a day.
- [ ] Implement. Run. Commit.

### Task 5: Calendar snapshot, diff and free slots

**Files:** `watchlib/calendar.py`, tests.

- [ ] Failing pytest:
  - cancelled (status, and the event gone), moved, new, organizer out;
  - the first tick of a day is a baseline;
  - the cross-check flags "cancelled per <label> (calendar still confirmed)";
  - free slots: at most 3, within 09:00–17:00 on workdays, before the deadline or within 5 workdays.
- [ ] Implement. Run. Commit.

### Task 6: Routing

**Files:** `watchlib/route.py`, tests.

- [ ] Failing pytest, one case per row of spec §3.5:
  - Now lines through `now.py add`, with `--due` and `--who`;
  - the free-slot note;
  - skipping on evidence in an open or archived Now line (a triage line included), on a covering statement and on a calendar event;
  - the item ledger;
  - the 3-alert cap with a count line;
  - `watch_partition`.
- [ ] Implement. Run. Commit.

### Task 7: Captures

**Files:** `watchlib/capture.py`, tests, `system/tests/golden/ingest/slack-capture/`.

- [ ] Failing pytest: the file name matches the intake's `RAW_NAME`; frontmatter and sections as spec §3.7; no cursor captures nothing and sets the cursor; the cursor moves only after the write; `capture_partition` falls back.
- [ ] Add the `slack-capture` eval case (a fact, a link, an uncertainty word; `archived`, `body_contains`).
- [ ] Implement. Run. Commit.

### Task 8: `watch_fetch.sh`, the tick

**Files:** `extensions/intraday/scripts/watch_fetch.sh`, `tests/watch.bats`.

- [ ] Failing bats with the stub `claude`:
  - a non-mention cancellation gives one item, one today-file line and one `[watch]` alert;
  - a commitment gives one `owed` line with its link;
  - a capture gives one inbox file that `intake_daemon.sh` compiles and archives;
  - one session failing leaves the other two running, and its cursor unmoved;
  - the usage-ceiling hold;
  - `--check slack|gmail|calendar`;
  - the client no-op.
- [ ] Implement: three `connector_run` calls, then routing. Run. Commit.

### Task 9: `today_log.py` and the brief and debrief sections

**Files:** `extensions/intraday/scripts/today_log.py`, `brief/`, `debrief/`, tests.

- [ ] Failing pytest:
  - the entries of spec §3.6 (watch, session with delivered sub-bullets, meeting, capture);
  - masking, cutting, link and checkbox stripping;
  - the ledger;
  - the `work` wall;
  - an unreadable source alerts once a day;
  - a meeting note not yet present is retried;
  - the client no-op.
- [ ] Failing bats: the brief section carries the embed line; the debrief section lists today's open watch lines.
- [ ] Implement. Run. Commit.

### Task 10: Setup, smoke, documents

**Files:** `extension.md` body (setup text), `FOUNDRY.md`, `CLAUDE.md`, `docs/superpowers/roadmap.md`, the gap plan's phase D section, `CHANGELOG.md`.

- [ ] The setup steps of spec §3.9. The smoke entries. The FOUNDRY.md Intraday paragraph and the `watch` tag row. The two Directory Map phrases; `CLAUDE.md` stays at 50 lines.
- [ ] Run the gate with every extension off and with every extension on. Commit.

### Task 11: Live acceptance (owner)

- [ ] Turn the extension on in the vault and seed `watch_channels`.
- [ ] Check the three cases in spec §4: a watched cancellation alerts within one tick with no session open; a group-DM commitment becomes an `owed` line; a capture reaches the wiki within one intake tick.
- [ ] Record each session's cost per tick in the spike note.
- [ ] Then 5 weekdays with no hand annotations on the brief.
