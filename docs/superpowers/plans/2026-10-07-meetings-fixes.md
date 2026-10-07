# Meetings Fetch and Import Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Plan 11 final-review minors on `kferran/jarvis`: an apply-time conflict no longer quarantines a meeting (#37), a resumed import still logs its `imported` line (#43), UTF-16 transcripts import (#41), the no-connector exit ignores free text (#38), a failing search is alerted (#39), a stopped unit leaves no session directory (#40), a Doc title's zone sets the start (#42), and a skipped Doc can be retried (#44).

**Architecture:**
- `vaultlib/intake.py` `_import_meeting`: `status == "conflict"` leaves the source and alerts with the held-back paths; the same-source branch writes the missing `imported` line.
- `vaultlib/meetings.py`: `_decode` reads UTF-8 or BOM-marked UTF-16 and rejects text with NULs; `parse_gdoc` reads the title's zone from a fixed table of abbreviations.
- `meetings_extract.py`: `names_drive` counts only `tool_reference` blocks; `fetch_log` resets a Doc's failure count at a `retry` line.
- `meetings_fetch.sh`: `alert_once` on a search or filter exit 1; the running session's directory is global and removed by the EXIT trap; `--retry <id> <YYYY-MM-DD>`.

**Tech Stack:** Python 3.11, bash 5, jq 1.6, bats 1.8; the fetch tests use `system/tests/stub_claude_meetings`.

**Spec:** issues #37-#44 (`gh issue view <n> --repo kferran/jarvis`), the triage `docs/superpowers/plans/2026-10-07-template-issue-triage.md`, the meetings spec `docs/superpowers/specs/2026-10-05-meetings-design.md` §2.1 (fetch), §2.3 (import), and the acceptance record `docs/superpowers/spikes/2026-10-06-plan-11-acceptance.md` (live `tool_reference` shape; 8 `MDT` and 2 `CDT` titles).

## Global Constraints

- **Where:** a worktree of the template repository on its own branch, for example `git -C ~/Foundry fetch -q template && git -C ~/Foundry worktree add ~/Foundry-worktrees/meetings-fixes -b fix/meetings template/master`. Never on a vault's `master`; never push or merge from the plan.
- **Never** run `meetings_fetch.sh`, `meeting_import.py`, `install_units.sh` or a real `claude` against the real user session or a real vault. Tests use `$BATS_TEST_TMPDIR` / `tmp_path` vaults and the stub claude.
- **No `system/config.md`** in the worktree.
- **Decision gates:** Task 7 (#42) and Task 8 (#44) run only after the user confirms the option in the triage's Decisions (2 and 3). Tasks 1-6 do not depend on them.
- **Tool floor:** jq 1.6, bats 1.8 (no `run -N`), Python 3.11. No mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions (Task 6 polls for a file, with a 10-second cap).
- **Verify (no network, sandbox-safe):** `python3 -m pytest system/tests/python -q` and `bats system/tests/meetings.bats system/tests/commands.bats`.
- **Edits:** each "replace" block quotes the current text exactly and must match once; if not, stop and compare with `template/master` at fb81fca.

## Review Focus

1. **The meeting note itself (not the transcript) is held back at apply time.** Expected: the source stays and the alert names the note. The next tick finds no note with that source and publishes under a `-2` name, which leaves the first run's transcript unpaired. Pinned only for the transcript case (Task 1); the note case is left as a known limit of #37's fix.
2. **A UTF-16 `.vtt` from Teams.** Expected: the same cues as its UTF-8 twin. Pinned by Task 3.
3. **A `CST` title from a team in China.** Expected: read as US Central (documented in the spec line); anything outside the table uses the config zone. Pinned by Task 7 (`IST` falls back).
4. **A search that fails every hour for a day.** Expected: one alert that day (`alert_once`), and the next morning's brief reads it from yesterday's alerts file. Pinned by Task 5 (two runs, one alert).
5. **`--retry` for a Doc that is already imported, quarantined or not in the window.** Expected: exit 1 with a reason, no read, `.since` untouched. Pinned by Task 8.

---

### Task 1: an apply-time publish conflict leaves the source (#37)

**Files:**
- Modify: `system/scripts/vaultlib/intake.py:524-526` (`_import_meeting`)
- Test: `system/tests/python/test_meetings.py`

**Interfaces:**
- Produces: alert text `meeting import of <rel> held back <path>[, <path>] (changed during the publish); will retry`. Task 2 defines `meeting_log(vault)` in the same test file, below this task's test; this task's test does not use it.

- [ ] **Step 1: Write the failing test.** In `system/tests/python/test_meetings.py`, insert before `def test_a_bad_source_is_quarantined_and_the_rest_continue(iv):`:

```python
def test_a_target_changed_at_apply_time_leaves_the_source_for_the_next_tick(iv, monkeypatch):
    config(iv, meetings_partition="work")
    src = fetched(iv)
    real = publish._apply
    transcript = f"wiki/work/meetings/{NAME}.transcript.md"

    def racing(vault, journal):  # an edit lands between validation and apply
        write(vault, transcript, "someone else\n")
        return real(vault, journal)
    monkeypatch.setattr(publish, "_apply", racing)
    tick(iv)
    assert src.exists() and not (iv / "system/quarantine/meetings").exists()
    assert meeting_runs(iv)[0]["publish"]["status"] == "conflict"
    assert f"held back {transcript}" in alerts(iv)
    monkeypatch.setattr(publish, "_apply", real)
    tick(iv)
    assert not src.exists() and (iv / f"raw/work/notes/{NAME}.meeting-input.md").is_file()


```

- [ ] **Step 2: Run it to see it fail.**

Run: `python3 -m pytest system/tests/python/test_meetings.py -q -k apply_time`
Expected: FAIL at `assert src.exists()` (the source went to `system/quarantine/meetings/` with the reason `the publish gate rejected it: `).

- [ ] **Step 3: Leave the source.** In `system/scripts/vaultlib/intake.py`, replace:

```python
            if report["status"] != "published":
                problems = [p["reason"] for p in report.get("problems") or []]
```

with:

```python
            if report["status"] == "conflict":  # held back at apply time (#37): the next tick finishes or retries
                self.alert(f"meeting import of {rel} held back {', '.join(report['conflicts'])} "
                           "(changed during the publish); will retry")
                return
            if report["status"] != "published":
                problems = [p["reason"] for p in report.get("problems") or []]
```

- [ ] **Step 4: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_meetings.py -q`
Expected: all passed.

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/vaultlib/intake.py system/tests/python/test_meetings.py
git commit -m "fix(meetings): an apply-time conflict leaves the source for the next tick (#37)"
```

---

### Task 2: the resume path writes the missing `imported` line (#43)

**Files:**
- Modify: `system/scripts/vaultlib/intake.py:516-517` (`_import_meeting`, same-source branch)
- Test: `system/tests/python/test_meetings.py`

**Interfaces:**
- Produces: test helper `meeting_log(vault) -> list[dict]` (every line of `system/logs/meetings-*.jsonl`). The `imported` record is `{"kind": "imported", "source": <rel>, "note": "wiki/<partition>/meetings/<name>.md", "complete": <bool>}`, as `meeting_actions.py` `notices()` reads it.

- [ ] **Step 1: Write the failing test.** In `system/tests/python/test_meetings.py`, insert before `def test_a_bad_source_is_quarantined_and_the_rest_continue(iv):`:

```python
def meeting_log(vault):
    return [json.loads(line) for p in sorted((vault / "system/logs").glob("meetings-*.jsonl"))
            for line in p.read_text().splitlines()]


def test_a_crash_before_the_imported_line_is_logged_by_the_next_tick(iv, monkeypatch):
    config(iv, meetings_partition="work")
    fetched(iv, body=NOTES + TRANSCRIPT)  # no end marker: complete is false
    real = Intake._meeting_log

    def dies_once(self, record):
        if record.get("kind") == "imported":
            raise OSError("killed")
        real(self, record)
    monkeypatch.setattr(Intake, "_meeting_log", dies_once)
    tick(iv)
    assert [r for r in meeting_log(iv) if r["kind"] == "imported"] == []
    monkeypatch.setattr(Intake, "_meeting_log", real)
    tick(iv)
    tick(iv)
    [line] = [r for r in meeting_log(iv) if r["kind"] == "imported"]
    assert (line["note"], line["complete"]) == (f"wiki/work/meetings/{NAME}.md", False)


```

- [ ] **Step 2: Run it to see it fail.**

Run: `python3 -m pytest system/tests/python/test_meetings.py -q -k imported_line`
Expected: FAIL, `ValueError: not enough values to unpack (expected 1, got 0)`.

- [ ] **Step 3: Log it on resume.** In `system/scripts/vaultlib/intake.py`, replace:

```python
        if same is not None:  # published by an earlier tick: finish its hand-off
            name, partition = same.name[:-3], same.parent.parent.name
        else:
```

with:

```python
        if same is not None:  # published by an earlier tick: finish its hand-off
            name, partition = same.name[:-3], same.parent.parent.name
            note = f"wiki/{partition}/meetings/{name}.md"
            if not any(r.get("kind") == "imported" and r.get("note") == note
                       for log in sorted(self.logs.glob("meetings-*.jsonl"))[-2:] for r in self._jsonl(log)):
                # that tick stopped before its log line (#43): the brief's Notices read complete from it
                self._meeting_log({"kind": "imported", "source": rel, "note": note, "complete": m.complete})
        else:
```

`m` is the source re-parsed this tick, so `m.complete` equals what the earlier tick would have logged.

- [ ] **Step 4: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_meetings.py system/tests/python/test_meeting_actions.py -q`
Expected: all passed.

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/vaultlib/intake.py system/tests/python/test_meetings.py
git commit -m "fix(meetings): a resumed import logs its imported line (#43)"
```

---

### Task 3: UTF-16 drops import; other non-UTF-8 text is quarantined with a reason (#41)

**Files:**
- Modify: `system/scripts/vaultlib/meetings.py:209-211` (`parse_drop`)
- Modify: `docs/superpowers/specs/2026-10-05-meetings-design.md:80` (§2.3 step 1, plain transcripts)
- Test: `system/tests/python/test_meetings.py`

**Interfaces:**
- Produces: `meetings._decode(data: bytes) -> str`; raises `ParseError("not UTF-8 text (save the transcript as UTF-8)")`.

- [ ] **Step 1: Write the failing tests.** In `system/tests/python/test_meetings.py`, insert before `def test_a_markdown_drop_with_the_gemini_structure_is_a_gemini_doc():`:

```python
def test_a_utf16_drop_parses_like_its_utf8_twin():
    start = datetime(2026, 10, 5, 15, 0, tzinfo=TZ)
    text = "Avery Sample: Hello.\n**Blake Sample:** Hi.\n"
    twin = meetings.parse_drop("notes.txt", text.encode(), TZ, start).turns
    assert meetings.parse_drop("notes.txt", text.encode("utf-16"), TZ, start).turns == twin
    assert meetings.parse_drop("notes.txt", b"\xfe\xff" + text.encode("utf-16-be"), TZ, start).turns == twin
    assert (meetings.parse_drop("call.vtt", VTT.encode("utf-16"), TZ, start).turns
            == meetings.parse_drop("call.vtt", VTT.encode(), TZ, start).turns)
    with pytest.raises(meetings.ParseError, match="not UTF-8 text"):
        meetings.parse_drop("notes.txt", text.encode("utf-16-le"), TZ, start)  # no byte-order mark


```

Insert before `def test_a_source_that_keeps_failing_is_quarantined_on_the_third_tick(iv, monkeypatch):`:

```python
def test_a_drop_of_nul_bytes_is_quarantined_as_not_utf8(iv):
    dropped(iv, "work/notes.txt", "\x00" * 8)
    tick(iv)
    assert meeting_runs(iv) == []
    assert "not UTF-8 text" in (iv / "system/quarantine/meetings/notes.txt.reason.txt").read_text()


```

- [ ] **Step 2: Run them to see them fail.**

Run: `python3 -m pytest system/tests/python/test_meetings.py -q -k "utf16 or nul_bytes"`
Expected: 2 failed (turns full of `\x00`; the NUL drop is published).

- [ ] **Step 3: Decode.** In `system/scripts/vaultlib/meetings.py`, replace:

```python
def parse_drop(name: str, data: bytes, tz, start: datetime) -> Meeting:
    """A dropped transcript (.vtt, .srt, .txt or .md); a .md with the Gemini structure is a Gemini Doc."""
    text = data.decode("utf-8", errors="replace").lstrip("﻿")
```

(the last line's `lstrip` argument is a literal U+FEFF character) with:

```python
def _decode(data: bytes) -> str:
    """UTF-8 (a byte-order mark is dropped), or UTF-16 with its byte-order mark, as Windows tools save it (#41).
    Any other text holds NULs once decoded and is a ParseError, so it is quarantined with a reason."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    text = data.decode("utf-8", errors="replace").lstrip("\ufeff")
    if "\x00" in text:
        raise ParseError("not UTF-8 text (save the transcript as UTF-8)")
    return text


def parse_drop(name: str, data: bytes, tz, start: datetime) -> Meeting:
    """A dropped transcript (.vtt, .srt, .txt or .md); a .md with the Gemini structure is a Gemini Doc."""
    text = _decode(data)
```

- [ ] **Step 4: Update the spec.** In `docs/superpowers/specs/2026-10-05-meetings-design.md`, replace:

```text
   - Plain transcripts: `.vtt` and `.srt` cues as turns
```

with:

```text
   - Plain transcripts (UTF-8, or UTF-16 with a byte-order mark; any other encoding is quarantined as "not UTF-8 text"): `.vtt` and `.srt` cues as turns
```

- [ ] **Step 5: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_meetings.py -q`
Expected: all passed.

- [ ] **Step 6: Commit.**

```bash
git add system/scripts/vaultlib/meetings.py system/tests/python/test_meetings.py docs/superpowers/specs/2026-10-05-meetings-design.md
git commit -m "fix(meetings): import UTF-16 drops and quarantine other non-UTF-8 text (#41)"
```

---

### Task 4: the no-connector exit counts only `tool_reference` blocks (#38)

**Files:**
- Modify: `system/scripts/meetings_extract.py:54` (new function before `results`), `:67`
- Test: `system/tests/meetings.bats`

**Interfaces:**
- Produces: `names_drive(content) -> bool`.

- [ ] **Step 1: Write the failing test.** In `system/tests/meetings.bats`, insert before `@test "fetch: the third failed read of a Doc is alerted once and the Doc is skipped from then on" {`:

```bash
@test "fetch: a ToolSearch reply that only repeats the Drive tool's name in its text is no connector, exit 3 (#38)" {
  printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"ToolSearch","input":{"query":"select:mcp__claude_ai_Google_Drive__search_files"}}]}}' \
    '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"No matching deferred tools found for select:mcp__claude_ai_Google_Drive__search_files"}]}}' \
    '{"type":"result","subtype":"success","is_error":false,"num_turns":4}' > "$STUB_STREAMS/search.jsonl"
  run "$MF"
  [ "$status" -eq 3 ]
}

```

- [ ] **Step 2: Run it to see it fail.**

Run: `bats -f '#38' system/tests/meetings.bats`
Expected: `not ok 1` (exit 1, "the session never called …").

- [ ] **Step 3: Match the block shape.** In `system/scripts/meetings_extract.py`, replace:

```python
def results(stream, step):
```

with:

```python
def names_drive(content):
    """True when a ToolSearch result names a Drive tool in a tool_reference block. Free text never counts: a
    "not found" reply can repeat the query, which names the tool too (#38)."""
    return isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_reference" and str(c.get("tool_name", "")).startswith(PREFIX)
        for c in content)


def results(stream, step):
```

Replace:

```python
                if call.get("name") == "ToolSearch" and PREFIX in json.dumps(b.get("content")):
```

with:

```python
                if call.get("name") == "ToolSearch" and names_drive(b.get("content")):
```

- [ ] **Step 4: Run the tests.**

Run: `bats system/tests/meetings.bats`
Expected: all `ok` (the fixtures' `search_says` already sends a `tool_reference` block).

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/meetings_extract.py system/tests/meetings.bats
git commit -m "fix(meetings): decide no-connector from tool_reference blocks only (#38)"
```

---

### Task 5: a search or filter that exits 1 is alerted once a day (#39)

**Files:**
- Modify: `system/scripts/meetings_fetch.sh:103-106`, `:116-121`
- Test: `system/tests/meetings.bats`

**Interfaces:**
- Produces: alert line `- <HH:MM:SS> [meetings] Drive fetch failed (exit 1): <reason>` (same `alert_once` key as exits 3, 6 and 7, so at most one exit-1 alert a day).

- [ ] **Step 1: Write the failing test.** In `system/tests/meetings.bats`, insert before `@test "fetch: the third failed read of a Doc is alerted once and the Doc is skipped from then on" {`:

```bash
@test "fetch: a search that fails with exit 1 is alerted once a day, and so is a failed filter (#39)" {
  search_says "$(doc FAKE-doc-0001)"
  jq -c 'if .tool_use_result then .tool_use_result = {"structuredContent": {"items": []}} else . end' \
    "$STUB_STREAMS/search.jsonl" > "$BATS_TEST_TMPDIR/odd.jsonl"
  cp "$BATS_TEST_TMPDIR/odd.jsonl" "$STUB_STREAMS/search.jsonl"
  run "$MF"
  [ "$status" -eq 1 ]
  run "$MF"
  [ "$status" -eq 1 ]
  [ "$(grep -c '\[meetings\] Drive fetch failed (exit 1):.*files list' system/logs/alerts_*.md)" -eq 1 ]
  rm system/logs/alerts_*.md
  search_says "$(doc FAKE-doc-0001)"
  rm -f system/index.db
  mkdir system/index.db
  run "$MF"
  [ "$status" -eq 1 ]
  grep -q '\[meetings\] Drive fetch failed (exit 1): filter: ' system/logs/alerts_*.md
}

```

- [ ] **Step 2: Run it to see it fail.**

Run: `bats -f '#39' system/tests/meetings.bats`
Expected: `not ok 1` (no alerts file).

- [ ] **Step 3: Alert.** In `system/scripts/meetings_fetch.sh`, replace:

```bash
if (( rc != 0 )); then
  echo "meetings_fetch: $(jq -r .reason <<< "$(tail -n 1 "$log")")" >&2
  exit "$rc"
fi
```

with:

```bash
if (( rc != 0 )); then
  reason="$(jq -r .reason <<< "$(tail -n 1 "$log")")"
  # Exit 1 (a refused allow rule, a claude error, a result in an unexpected shape) is alerted too: the brief
  # reads yesterday's alerts, and a search that fails every hour must reach it (#39).
  (( rc != 1 )) || alert_once "Drive fetch failed (exit 1):" "$reason"
  echo "meetings_fetch: $reason" >&2
  exit "$rc"
fi
```

Replace:

```bash
  logline search search 1 "$reason"
  echo "meetings_fetch: $reason" >&2
  exit 1
```

with:

```bash
  logline search search 1 "$reason"
  alert_once "Drive fetch failed (exit 1):" "$reason"
  echo "meetings_fetch: $reason" >&2
  exit 1
```

- [ ] **Step 4: Run the tests.**

Run: `bats system/tests/meetings.bats`
Expected: all `ok`.

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/meetings_fetch.sh system/tests/meetings.bats
git commit -m "fix(meetings): alert a search or filter that exits 1, once a day (#39)"
```

---

### Task 6: a stopped fetch removes the running session's directory (#40)

**Files:**
- Modify: `system/scripts/meetings_fetch.sh:39-40`, `:62`, `:80`
- Test: `system/tests/meetings.bats`

**Interfaces:** none (`sdir` becomes a script-level variable, empty between sessions).

- [ ] **Step 1: Write the failing test.** In `system/tests/meetings.bats`, insert before `@test "fetch: the third failed read of a Doc is alerted once and the Doc is skipped from then on" {`:

```bash
@test "fetch: a fetch stopped mid-session removes that session's /tmp directory (#40)" {
  search_says
  STUB_SLEEP=30 setsid "$MF" > /dev/null 2>&1 &
  pid=$!
  for i in $(seq 1 100); do [ -s "$STUB_CWD" ] && break; sleep 0.1; done
  [ -s "$STUB_CWD" ]
  d="$(head -n 1 "$STUB_CWD")"
  [ -d "$d" ]
  kill -TERM -- "-$pid"
  wait "$pid" || true
  [ ! -e "$d" ]
}

```

`setsid` puts the fetch in its own process group, and `kill -- -<pid>` stops the whole group, as systemd does at `TimeoutStartSec`.

- [ ] **Step 2: Run it to see it fail.**

Run: `bats -f '#40' system/tests/meetings.bats`
Expected: `not ok 1` at `[ ! -e "$d" ]`.

- [ ] **Step 3: Track the directory.** In `system/scripts/meetings_fetch.sh`, replace:

```bash
work="$(mktemp -d -p /tmp)"
trap 'rm -rf -- "$work"' EXIT
```

with:

```bash
work="$(mktemp -d -p /tmp)"
sdir=""  # the running session's directory: a unit stopped mid-session (TimeoutStartSec) must not leave it (#40)
trap 'rm -rf -- "$work" ${sdir:+"$sdir"}' EXIT
```

Replace:

```bash
  local step="$1" prompt="$2" id="${3:-}" tool rc=0 prc=0 reason t sdir
```

with:

```bash
  local step="$1" prompt="$2" id="${3:-}" tool rc=0 prc=0 reason t
```

Replace:

```bash
  rm -rf -- "$sdir"
```

with:

```bash
  rm -rf -- "$sdir"
  sdir=""
```

- [ ] **Step 4: Run the tests.**

Run: `bats system/tests/meetings.bats`
Expected: all `ok` (the confinement test still finds every session directory gone).

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/meetings_fetch.sh system/tests/meetings.bats
git commit -m "fix(meetings): remove the running session's directory when the fetch is stopped (#40)"
```

---

### Task 7 (decision gate: triage Decision 2): the title's zone sets the start (#42)

**Files:**
- Modify: `system/scripts/vaultlib/meetings.py:5`, `:11-12`, `:131-134` (`parse_gdoc`)
- Modify: `docs/superpowers/specs/2026-10-05-meetings-design.md:79` (§2.3 step 1, Gemini Docs)
- Test: `system/tests/python/test_meetings.py`

**Interfaces:**
- Produces: `meetings.TITLE_ZONES: dict[str, int]` (abbreviation to UTC offset hours). `DOC_TITLE` and `IMPROMPTU` gain a last group, the zone. `Meeting.start` stays in the config zone.

- [ ] **Step 1: Write the failing test.** In `system/tests/python/test_meetings.py`, insert before `@pytest.mark.parametrize("title", ["Weekly sync - Notes by Gemini",`:

```python
@pytest.mark.parametrize("when, start", [("15:00 MDT", "2026-10-05T15:00:00-06:00"),
                                         ("15:00 CDT", "2026-10-05T14:00:00-06:00"),
                                         ("15:00 MST", "2026-10-05T16:00:00-06:00"),
                                         ("00:30 EDT", "2026-10-04T22:30:00-06:00"),
                                         ("15:00 IST", "2026-10-05T15:00:00-06:00")])
def test_the_title_zone_sets_the_start_when_it_is_known(when, start):
    m = meetings.parse_gdoc(gdoc(title=f"Weekly sync - 2026/10/05 {when} - Notes by Gemini"), TZ)
    assert m.start.isoformat() == start
    assert m.start.tzinfo == TZ


```

- [ ] **Step 2: Run it to see it fail.**

Run: `python3 -m pytest system/tests/python/test_meetings.py -q -k title_zone`
Expected: 3 failed (`CDT`, `MST`, `EDT`), 2 passed.

- [ ] **Step 3: Read the zone.** In `system/scripts/vaultlib/meetings.py`, replace:

```python
from datetime import datetime, timezone
```

with:

```python
from datetime import datetime, timedelta, timezone
```

Replace:

```python
DOC_TITLE = re.compile(r"^(.*) - (\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) \S+ - Notes by Gemini$")
IMPROMPTU = re.compile(r"^(Meeting started) (\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) \S+ - Notes by Gemini$")
```

with:

```python
DOC_TITLE = re.compile(r"^(.*) - (\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) (\S+) - Notes by Gemini$")
IMPROMPTU = re.compile(r"^(Meeting started) (\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) (\S+) - Notes by Gemini$")
# A Doc title's zone abbreviation, as UTC offset hours (#42). The title is written in its owner's zone, which can
# differ from the vault's. Any other abbreviation (IST, …) is ambiguous and read in the config timezone.
TITLE_ZONES = {"UTC": 0, "GMT": 0, "BST": 1, "CET": 1, "CEST": 2, "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
               "MST": -7, "MDT": -6, "PST": -8, "PDT": -7, "AKST": -9, "AKDT": -8, "HST": -10}
```

Replace:

```python
    try:
        start = datetime(*map(int, match.groups()[1:]), tzinfo=tz)
    except ValueError:
```

with:

```python
    *parts, zone = match.groups()[1:]
    offset = TITLE_ZONES.get(zone)
    try:
        start = datetime(*map(int, parts), tzinfo=tz if offset is None else timezone(timedelta(hours=offset)))
        start = start.astimezone(tz)
    except ValueError:
```

- [ ] **Step 4: Update the spec.** In `docs/superpowers/specs/2026-10-05-meetings-design.md`, replace:

```text
start (date and time from the title, zone from the config timezone)
```

with:

```text
start (date and time from the title; the zone from the title's abbreviation when it is one of `UTC`, `GMT`, `BST`, `CET`/`CEST`, `EST`/`EDT`, `CST`/`CDT`, `MST`/`MDT`, `PST`/`PDT`, `AKST`/`AKDT` or `HST` (US meanings), else the config timezone; the start is then expressed in the config timezone)
```

- [ ] **Step 5: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_meetings.py system/tests/python/test_meeting_actions.py -q`
Expected: all passed.

- [ ] **Step 6: Commit.**

```bash
git add system/scripts/vaultlib/meetings.py system/tests/python/test_meetings.py docs/superpowers/specs/2026-10-05-meetings-design.md
git commit -m "fix(meetings): read a Doc title's zone abbreviation for its start (#42)"
```

---

### Task 8 (decision gate: triage Decision 3): `meetings_fetch.sh --retry` (#44)

**Files:**
- Modify: `system/scripts/meetings_extract.py:133-142` (`fetch_log`)
- Modify: `system/scripts/meetings_fetch.sh:4`, `:21-27`, `:97-98`, `:122`, `:127`, `:132`
- Modify: `README.md` (new **Meetings fetch.** paragraph before **Debrief inputs.**), `.claude/commands/setup.md:87` (phase 6b)
- Test: `system/tests/meetings.bats`, `system/tests/commands.bats`

**Interfaces:**
- Produces: `meetings_fetch.sh --retry <Doc ID> <YYYY-MM-DD>`: exit 2 on a bad ID or date; logs `{"step":"retry","doc":<id>,"exit":0,…}`; searches with `createdTime > '<date - 1 day>T00:00:00Z'`; reads only that Doc; never writes `.since`; exit 1 when the Doc is not eligible. A `retry` line resets the Doc's failure count in both `fetch_log()` and the shell's three-failures alert.

- [ ] **Step 1: Write the failing tests.** In `system/tests/meetings.bats`, insert before `@test "fetch: a timeout exits 4, a missing claude 127, a failing claude 1" {`:

```bash
@test "fetch: --retry reads one skipped Doc again from a wider window and leaves .since (#44)" {
  search_says "$(doc FAKE-doc-0001)" "$(doc FAKE-doc-0002)"
  read_says FAKE-doc-0001
  read_says FAKE-doc-0002
  for i in 1 2 3; do printf '{"step":"read","doc":"FAKE-doc-0001","exit":1}\n' >> "$LOG"; done
  printf 'keep\n' > system/logs/meetings_fetch.since
  run "$MF" --retry FAKE-doc-0001 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 2 ]
  grep -qF "createdTime > '2026-09-30T00:00:00Z'" "$STUB_ARGS"
  [ -f raw/meetings/FAKE-doc-0001.gdoc.md ]
  [ ! -e raw/meetings/FAKE-doc-0002.gdoc.md ]
  [ "$(cat system/logs/meetings_fetch.since)" = keep ]
  run "$MF" --retry FAKE-doc-0001 2026-10-01
  [ "$status" -eq 1 ]
  [[ "$output" == *"not a new Gemini Doc"* ]]
  for a in 'FAKE/../x 2026-10-01' 'FAKE-doc-0001 yesterday' 'FAKE-doc-0001'; do
    run "$MF" --retry $a
    [ "$status" -eq 2 ]
  done
}

@test "fetch: after a retry, the Doc is read again and its third new failure is alerted (#44)" {
  search_says "$(doc FAKE-doc-0001)"
  read_says FAKE-doc-0001 'x' FAKE-other
  for i in 1 2 3; do printf '{"step":"read","doc":"FAKE-doc-0001","exit":1}\n' >> "$LOG"; done
  printf '{"step":"retry","doc":"FAKE-doc-0001","exit":0}\n' >> "$LOG"
  for i in 1 2; do printf '{"step":"read","doc":"FAKE-doc-0001","exit":1}\n' >> "$LOG"; done
  run "$MF"
  [ "$status" -eq 0 ]
  [ "$(sessions)" -eq 2 ]
  grep -q '\[meetings\] FAKE-doc-0001 failed 3 reads' system/logs/alerts_*.md
}

```

Append to `system/tests/commands.bats`:

```bash

@test "the README and /setup name the retry for a skipped meetings Doc (#44)" {
  grep -qF 'system/scripts/meetings_fetch.sh --retry <id> <YYYY-MM-DD>' README.md
  sec="$(setup_section '6b. Meetings')"
  [[ "$sec" == *'system/scripts/meetings_fetch.sh --retry <id> <YYYY-MM-DD>'* ]]
}
```

- [ ] **Step 2: Run them to see them fail.**

Run: `bats -f '#44' system/tests/meetings.bats; bats -f '#44' system/tests/commands.bats`
Expected: three `not ok`.

- [ ] **Step 3: Reset the count at a retry line.** In `system/scripts/meetings_extract.py`, replace:

```python
    """(failed read counts, skipped IDs) from this month's and last month's fetch logs."""
```

with:

```python
    """(failed read counts, skipped IDs) from this month's and last month's fetch logs. A retry line
    (meetings_fetch.sh --retry) starts a Doc's count again (#44)."""
```

Replace:

```python
            if r.get("skipped") is True:
                skipped.add(r.get("doc"))
            elif r.get("step") == "read"
```

with:

```python
            if r.get("skipped") is True:
                skipped.add(r.get("doc"))
            elif r.get("step") == "retry":
                failures.pop(r.get("doc"), None)
            elif r.get("step") == "read"
```

- [ ] **Step 4: Add the flag.** In `system/scripts/meetings_fetch.sh`, replace:

```bash
# or standalone vault with meetings_enabled true. --check runs the search only and prints how many Docs it listed.
```

with:

```bash
# or standalone vault with meetings_enabled true. --check runs the search only and prints how many Docs it listed.
# --retry <Doc ID> <YYYY-MM-DD> reads one Doc skipped after three failed reads again: it starts the Doc's failure
# count anew, searches from the day before that date, reads only that Doc and leaves the fetch window alone.
```

Replace:

```bash
check=0
case "${1:-}" in
  "") ;;
  --check) check=1 ;;
  *) echo "usage: meetings_fetch.sh [--check]" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { echo "usage: meetings_fetch.sh [--check]" >&2; exit 2; }
```

with:

```bash
usage() { echo "usage: meetings_fetch.sh [--check | --retry <Doc ID> <YYYY-MM-DD>]" >&2; exit 2; }
check=0 retry="" retry_day=""
case "${1:-}" in
  "") (( $# == 0 )) || usage ;;
  --check) (( $# == 1 )) || usage; check=1 ;;
  --retry)
    (( $# == 3 )) || usage
    retry="$2" retry_day="$3"
    [[ "$retry" =~ ^[A-Za-z0-9_-]{1,200}$ ]] || usage
    [[ "$retry_day" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && date -d "$retry_day" > /dev/null 2>&1 || usage ;;
  *) usage ;;
esac
```

Replace:

```bash
since="$(cat "$since_file" 2>/dev/null || true)"
after="$(date -u -d "${since:-now} -24 hours" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '-24 hours' +%Y-%m-%dT%H:%M:%SZ)"
```

with:

```bash
if [[ -n "$retry" ]]; then
  logline retry "$retry" 0 "retry requested"
  after="$(date -u -d "$retry_day - 1 day" +%Y-%m-%dT%H:%M:%SZ)"
else
  since="$(cat "$since_file" 2>/dev/null || true)"
  after="$(date -u -d "${since:-now} -24 hours" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '-24 hours' +%Y-%m-%dT%H:%M:%SZ)"
fi
```

Replace:

```bash
mapfile -t ids < "$work/ids"
```

with:

```bash
mapfile -t ids < "$work/ids"
if [[ -n "$retry" ]]; then
  if [[ " ${ids[*]} " != *" $retry "* ]]; then
    echo "meetings_fetch: $retry is not a new Gemini Doc created from $retry_day on (imported, quarantined or not listed)" >&2
    exit 1
  fi
  ids=("$retry")
fi
```

Replace:

```bash
  n="$(jq -R --arg d "$id" 'fromjson? | select(.step == "read" and .doc == $d and .exit != 0) | 1' "${logs[@]}" | wc -l)"
```

with:

```bash
  # Failed reads since the Doc's last retry line, the count meetings_extract.py filter skips at.
  n="$(jq -nR --arg d "$id" 'reduce (inputs | fromjson? | select(.doc == $d)) as $r (0;
        if $r.step == "retry" then 0 elif $r.step == "read" and $r.exit != 0 then . + 1 else . end)' "${logs[@]}")"
```

Replace:

```bash
if (( ${#ids[@]} <= MAX_READS )); then
```

with:

```bash
if [[ -z "$retry" ]] && (( ${#ids[@]} <= MAX_READS )); then
```

- [ ] **Step 5: Document it.** In `README.md`, replace:

```text
**Debrief inputs.**
```

with:

```text
**Meetings fetch.** With `meetings_enabled`, `foundry-meetings.timer` runs `meetings_fetch.sh` every hour from 08:00 to 18:00 on workdays: one Google Drive search, then one confined read per new Gemini Doc. A Doc whose read fails three times is skipped and alerted (`<id> failed 3 reads`). Once the cause is gone (a usage limit, a connector outage), run `system/scripts/meetings_fetch.sh --retry <id> <YYYY-MM-DD>` with the date from the Doc's title: it reads that Doc once more and leaves the hourly window as it is.

**Debrief inputs.**
```

In `.claude/commands/setup.md`, replace:

```text
A Drive failure never blocks setup: the brief then lists meetings under Unavailable Sources.
```

with:

```text
A Drive failure never blocks setup: the brief then lists meetings under Unavailable Sources. Tell the user that a Doc skipped after three failed reads is read again with `system/scripts/meetings_fetch.sh --retry <id> <YYYY-MM-DD>` (the date from its title).
```

- [ ] **Step 6: Run the tests.**

Run: `bats system/tests/meetings.bats system/tests/commands.bats`
Expected: all `ok`.

- [ ] **Step 7: Commit.**

```bash
git add system/scripts/meetings_extract.py system/scripts/meetings_fetch.sh README.md .claude/commands/setup.md \
  system/tests/meetings.bats system/tests/commands.bats
git commit -m "feat(meetings): --retry reads a Doc skipped after three failed reads (#44)"
```

---

### Task 9: Verify the branch

- [ ] **Step 1: Run the suites.**

```bash
python3 -m pytest system/tests/python -q; echo "pytest exit=$?"
bats system/tests/meetings.bats system/tests/commands.bats system/tests/vault_integrity.bats; echo "bats exit=$?"
```

Expected: both `exit=0`.

- [ ] **Step 2: Lint.** `system/scripts/vault_index.py rebuild > /dev/null && system/scripts/vault_index.py issues | tail -n 1`
Expected: `0 errors`.
