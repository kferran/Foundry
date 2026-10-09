# Notes Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The briefing's 📝 Notes section ships with the ingest markers, and its block reaches the wiki exactly once, just after midnight (#61, option A).

**Architecture:** `Intake._extract_locked(path, notes=False)` tracks which `## ` section each `#wiki-ingest` block starts in. On the day, it sends every block outside 📝 Notes, as before. The new `_extract_notes_locked()`, run in the same `extract_briefing()` under `run.lock`, sends the 📝 Notes blocks of each earlier-day briefing still in `briefings/`. It then records `{"kind": "notes"}` for that briefing in `extracted_blocks.jsonl`, so the briefing is never read for Notes again. The template places the markers, and the README, `/setup` and `CLAUDE.md` describe the timing.

**Tech Stack:** Python 3, pytest, bats 1.8.2.

**Spec:** `docs/superpowers/specs/2026-10-09-notes-markers-design.md`

## Global Constraints

- Work on branch `feat/notes-markers`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Template rule: no machine, employer or people names.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once), outside a sandbox. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_intake.py`), bats (`commands.bats`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- **Mid-day edits:** a Notes block edited many times during the day sends nothing that day and exactly one drop after midnight. Tests: `test_todays_notes_block_waits_while_other_blocks_go_now`, `test_after_midnight_the_notes_block_goes_once`.
- **Upgrade day:** a Notes block already sent by the old behavior (same briefing, same hash) is not sent again. Test: `test_a_notes_block_already_sent_is_not_sent_again`.
- **A broken Notes section:** nothing is sent, it is alerted once a day, and the briefing is not marked done, so a fix still goes out. Test: `test_a_broken_notes_section_waits_and_alerts`.
- **The archive and debriefs:** never read for Notes. Test: `test_an_archived_briefing_and_a_debrief_are_not_read`.
- **The accepted gap:** notes that reach the server after the 06:00 archive are not sent. The README says so.

---

### Task 1: Notes markers and the midnight send

**Files:**
- Modify: `system/scripts/vaultlib/intake.py`, `system/templates/daily-briefing.md`, `README.md`, `.claude/commands/setup.md`, `CLAUDE.md`
- Test: `system/tests/python/test_intake.py`, `system/tests/commands.bats`

**Interfaces:**
- Produces `Intake._extract_locked(path, notes=False) -> bool`, which is True when the briefing was read and no marker problem blocked it, and `Intake._extract_notes_locked()`.
- New record kind `{"kind": "notes", "briefing": <rel>, "time": …}` in `system/logs/extracted_blocks.jsonl`.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/python/test_intake.py`. Find:

````text
    assert any(p.name.startswith("a-dup-") for p in (iv / "raw/archive").iterdir())
````

Replace with:

````text
    assert any(p.name.startswith("a-dup-") for p in (iv / "raw/archive").iterdir())


# -- the Notes block goes out once, after midnight (#61) ----------------------
NOTES_BRIEF = ("# Briefing\n### 1. Objectives\n#wiki-ingest-start\nright away\n#wiki-ingest-end\n"
               "## 📝 Notes\n<!-- yours -->\n#wiki-ingest-start\n{notes}\n#wiki-ingest-end\n## 🌌 Evening\n")


def dated(iv, day, text):
    path = write(iv, f"briefings/{day}.md", text)
    old = time.time() - 600
    os.utime(path, (old, old))
    return path


def yesterday():
    from datetime import timedelta
    return (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def test_todays_notes_block_waits_while_other_blocks_go_now(iv):
    briefing(iv, NOTES_BRIEF.format(notes="draft one"))
    Intake(iv, now=later()).extract_briefing()
    briefing(iv, NOTES_BRIEF.format(notes="draft two"))
    Intake(iv, now=later()).extract_briefing()
    assert [d.read_text() for d in drops(iv)] == ["right away\n"]


def test_after_midnight_the_notes_block_goes_once(iv):
    path = dated(iv, yesterday(), NOTES_BRIEF.format(notes="final notes"))
    Intake(iv, now=later()).extract_briefing()
    assert [d.read_text() for d in drops(iv)] == ["final notes\n"]  # its other blocks went out on their day
    path.write_text(NOTES_BRIEF.format(notes="edited after midnight"))
    old = time.time() - 600
    os.utime(path, (old, old))
    Intake(iv, now=later()).extract_briefing()
    assert len(drops(iv)) == 1
    assert [r["kind"] for r in blocks_log(iv)].count("notes") == 1


def test_an_empty_notes_block_makes_no_drop(iv):
    dated(iv, yesterday(), NOTES_BRIEF.format(notes="   "))
    Intake(iv, now=later()).extract_briefing()
    assert drops(iv) == []


def test_an_archived_briefing_and_a_debrief_are_not_read(iv):
    day = yesterday()
    dated(iv, f"archive/{day[:7]}/{day}", NOTES_BRIEF.format(notes="archived"))
    dated(iv, f"{day}.debrief", NOTES_BRIEF.format(notes="debrief"))
    Intake(iv, now=later()).extract_briefing()
    assert drops(iv) == []


def test_a_notes_block_already_sent_is_not_sent_again(iv):
    import hashlib
    day = yesterday()
    write(iv, "system/logs/extracted_blocks.jsonl", json.dumps(
        {"kind": "block", "briefing": f"briefings/{day}.md", "hash": hashlib.sha256(b"sent before").hexdigest(),
         "drop": "raw/inbox/x.md", "time": "t"}) + "\n")
    dated(iv, day, "## 📝 Notes\n#wiki-ingest-start\nsent before\n#wiki-ingest-end\n")
    Intake(iv, now=later()).extract_briefing()
    assert drops(iv) == []


def test_a_broken_notes_section_waits_and_alerts(iv):
    dated(iv, yesterday(), "## 📝 Notes\n#wiki-ingest-start\nhalf typed\n")
    Intake(iv, now=later()).extract_briefing()
    assert drops(iv) == []
    assert "unterminated" in next((iv / "system/logs").glob("alerts_*.md")).read_text()
    assert "notes" not in [r["kind"] for r in blocks_log(iv)]
````


Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'Never edit the **📝 Notes** section' "$f"
````

Replace with:

````text
  grep -qF 'Never edit the **📝 Notes** section' "$f"
}

@test "the briefing template's Notes section holds the ingest markers, sent once after midnight (#61)" {
  t=system/templates/daily-briefing.md
  notes="$(sed -n '/^## 📝 Notes$/,/^## 🌌 /p' "$t")"
  [ "$(grep -cx '#wiki-ingest-start' <<< "$notes")" -eq 1 ]
  [ "$(grep -cx '#wiki-ingest-end' <<< "$notes")" -eq 1 ]
  start="$(grep -nx '#wiki-ingest-start' "$t" | cut -d: -f1)"
  end="$(grep -nx '#wiki-ingest-end' "$t" | cut -d: -f1)"
  [ "$start" -lt "$end" ]
  grep -qF 'the block goes to the wiki once, just after midnight' "$t"
  grep -qF 'markers already in 📝 Notes: the server sends that block to the wiki once, just after midnight' README.md
  grep -qF 'which go to the wiki once, just after midnight' .claude/commands/setup.md
  grep -qF 'that block goes to the wiki once, just after midnight' CLAUDE.md
````


- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_intake.py`
Expected: FAIL, 3 failed (the Notes block goes out on the day, is never sent after midnight, and a broken Notes section in an earlier briefing is never alerted). The empty-block, archive and already-sent tests pass before the change: they pin what must not start happening.

Run: `bats system/tests/commands.bats`
Expected: FAIL, 1 `not ok` (the template and wording test).

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/intake.py`. Find:

````text
START, END = "#wiki-ingest-start", "#wiki-ingest-end"
````

Replace with:

````text
START, END = "#wiki-ingest-start", "#wiki-ingest-end"
NOTES = "## 📝 Notes"
BRIEFING_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
````

Edit 2 in `system/scripts/vaultlib/intake.py`. Find:

````text
                self._extract_locked(path)
````

Replace with:

````text
                self._extract_locked(path)
                self._extract_notes_locked()
````

Edit 3 in `system/scripts/vaultlib/intake.py`. Find:

````text
    def _extract_locked(self, path: Path) -> None:
        """Drop each new #wiki-ingest block; the briefing is never rewritten (two-machine spec §5.6)."""
        try:
            if not path.is_file():
                return
            if self.now() - path.stat().st_mtime < FRESH_SECONDS:
                return
````

Replace with:

````text
    def _extract_notes_locked(self) -> None:
        """After midnight, send each earlier briefing's 📝 Notes blocks once (#61); the archive is never read."""
        record_path = self.logs / "extracted_blocks.jsonl"
        done = {r.get("briefing") for r in self._jsonl(record_path) if r.get("kind") == "notes"}
        for path in sorted((self.vault / "briefings").glob("*.md")):
            rel = path.relative_to(self.vault).as_posix()
            if not BRIEFING_NAME.match(path.name) or path.name[:10] >= self.today() or rel in done:
                continue
            if self._extract_locked(path, notes=True):
                _append_jsonl(record_path, {"kind": "notes", "briefing": rel,
                                            "time": self.dt().isoformat(timespec="seconds")})

    def _extract_locked(self, path: Path, notes: bool = False) -> bool:
        """Drop each new #wiki-ingest block; the briefing is never rewritten (two-machine spec §5.6).
        Blocks inside 📝 Notes wait for the end of the day (#61): notes=False sends the others, notes=True only
        those. True when the briefing was read and nothing blocked its blocks."""
        try:
            if not path.is_file():
                return False
            if self.now() - path.stat().st_mtime < FRESH_SECONDS:
                return False
````

Edit 4 in `system/scripts/vaultlib/intake.py`. Find:

````text
            return
        if START not in text:
            return
        blocks, current, problem = [], None, ""
        for line in text.split("\n"):
            stripped = line.strip()
````

Replace with:

````text
            return False
        if START not in text:
            return True
        blocks, current, problem, in_notes = [], None, "", False
        for line in text.split("\n"):
            stripped = line.strip()
            if current is None and line.startswith("## "):
                in_notes = stripped == NOTES
````

Edit 5 in `system/scripts/vaultlib/intake.py`. Find:

````text
                current = []
            elif stripped == END and current is not None:
                blocks.append(current)
````

Replace with:

````text
                current, block_in_notes = [], in_notes
            elif stripped == END and current is not None:
                if block_in_notes == notes:
                    blocks.append(current)
````

Edit 6 in `system/scripts/vaultlib/intake.py`. Find:

````text
            problem = "has an unterminated #wiki-ingest-start"
````

Replace with:

````text
            problem = "has an unterminated #wiki-ingest-start"
        if problem and notes:
            blocks = []  # a broken Notes section waits until it is fixed
````

Edit 7 in `system/scripts/vaultlib/intake.py`. Find:

````text
            self.alert(f"briefing extraction failed ({exc.__class__.__name__}); will retry")
            return
````

Replace with:

````text
            self.alert(f"briefing extraction failed ({exc.__class__.__name__}); will retry")
            return False
````

Edit 8 in `system/scripts/vaultlib/intake.py`. Find:

````text
                _append_jsonl(record_path, {"kind": "alert", "briefing": rel, "reason": problem, "date": day})
````

Replace with:

````text
                _append_jsonl(record_path, {"kind": "alert", "briefing": rel, "reason": problem, "date": day})
        return not problem
````


Edit 1 in `system/templates/daily-briefing.md`. Find:

````text
<!-- Yours: /brief never edits this section. Put `#wiki-ingest-start` and `#wiki-ingest-end` on lines of their own around a block to send it to the wiki. -->
````

Replace with:

````text
<!-- Yours: /brief never edits this section. Write between the markers below: the block goes to the wiki once, just after midnight. A block marked anywhere else in the briefing goes within a few minutes. -->

#wiki-ingest-start

#wiki-ingest-end
````


Edit 1 in `README.md`. Find:

````text
- **Client.** The Obsidian Git plugin commits and syncs every few minutes; `/setup` prints its settings. Write notes in today's briefing between `#wiki-ingest-start` and `#wiki-ingest-end`: the server compiles each new block and leaves the briefing as it is (on every role, blocks stay in the briefing after compiling). Files in `raw/inbox/` on a client are not synced. Meeting transcripts dropped into `meetings/drop/<partition>/` are synced, and the server imports them; move a finished file in (an empty one is quarantined).
````

Replace with:

````text
- **Client.** The Obsidian Git plugin commits and syncs every few minutes; `/setup` prints its settings. Write notes in today's briefing between the `#wiki-ingest-start` and `#wiki-ingest-end` markers already in 📝 Notes: the server sends that block to the wiki once, just after midnight, so you can edit it all day. A block you mark anywhere else in the briefing is compiled within a few minutes. The briefing stays as it is (on every role, blocks stay in the briefing after compiling). Notes that reach the server after the 06:00 brief has archived the briefing are not sent. Files in `raw/inbox/` on a client are not synced. Meeting transcripts dropped into `meetings/drop/<partition>/` are synced, and the server imports them; move a finished file in (an empty one is quarantined).
````


Edit 1 in `.claude/commands/setup.md`. Find:

````text
If `git ls-files --error-unmatch .obsidian/plugins/obsidian-git/data.json` succeeds, run `git rm --cached .obsidian/plugins/obsidian-git/data.json` (the file is machine-specific and gitignored). The plugin runs the pre-commit hook inside Obsidian, whose `PATH` can differ from a terminal's: ask the user to make one test edit and confirm the plugin's commit succeeds; the hook's error names any missing tool. Then give the client notes: files dropped into `raw/inbox/` on a client are not synced (write notes in today's briefing between `#wiki-ingest-start` and `#wiki-ingest-end`); disable any plugin that creates `briefings/<date>.md` (daily notes, templates), because the server creates it; `/backup` on a client runs lint and then `vault_sync.sh`; to hand a meeting transcript to the server, drop transcripts (`.vtt`, `.srt`, `.txt` or `.md`) into `meetings/drop/<partition>/`: the plugin commits them, and the pre-commit hook refuses any other file type and any file that holds a secret. Write or paste a transcript elsewhere and move the finished file in: the server imports a drop a minute after it arrives and quarantines an empty one. Obsidian mobile runs no hooks, so a drop from a phone is checked only by the server's redaction.
````

Replace with:

````text
If `git ls-files --error-unmatch .obsidian/plugins/obsidian-git/data.json` succeeds, run `git rm --cached .obsidian/plugins/obsidian-git/data.json` (the file is machine-specific and gitignored). The plugin runs the pre-commit hook inside Obsidian, whose `PATH` can differ from a terminal's: ask the user to make one test edit and confirm the plugin's commit succeeds; the hook's error names any missing tool. Then give the client notes: files dropped into `raw/inbox/` on a client are not synced (write notes in today's briefing between the `#wiki-ingest-start` and `#wiki-ingest-end` markers in 📝 Notes, which go to the wiki once, just after midnight); disable any plugin that creates `briefings/<date>.md` (daily notes, templates), because the server creates it; `/backup` on a client runs lint and then `vault_sync.sh`; to hand a meeting transcript to the server, drop transcripts (`.vtt`, `.srt`, `.txt` or `.md`) into `meetings/drop/<partition>/`: the plugin commits them, and the pre-commit hook refuses any other file type and any file that holds a secret. Write or paste a transcript elsewhere and move the finished file in: the server imports a drop a minute after it arrives and quarantines an empty one. Obsidian mobile runs no hooks, so a drop from a phone is checked only by the server's redaction.
````


Edit 1 in `CLAUDE.md`. Find:

````text
- `briefings/`: `<date>.md` (morning briefing) and `<date>.debrief.md` (evening debrief, embedded in the briefing). Write your own notes in the briefing's 📝 Notes section. Each brief moves days before yesterday to `briefings/archive/<YYYY-MM>/`.
````

Replace with:

````text
- `briefings/`: `<date>.md` (morning briefing) and `<date>.debrief.md` (evening debrief, embedded in the briefing). Write your own notes in the briefing's 📝 Notes section, between its `#wiki-ingest` markers; that block goes to the wiki once, just after midnight. Each brief moves days before yesterday to `briefings/archive/<YYYY-MM>/`.
````


- [ ] **Step 4: Run the tests and the gate**

Run: the commands from Step 2.
Expected: PASS, no failures and no `not ok`.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(brief): Notes holds the ingest markers and goes to the wiki once, after midnight (#61)

The briefing template places #wiki-ingest-start and #wiki-ingest-end in
📝 Notes. Extraction skips blocks inside Notes on the day; after midnight
it sends each earlier briefing's Notes blocks once (a "notes" record in
extracted_blocks.jsonl) before the 06:00 brief archives the file. Blocks
elsewhere in the briefing still go out within minutes.
```

Run: `git add system/scripts/vaultlib/intake.py system/templates/daily-briefing.md README.md .claude/commands/setup.md CLAUDE.md system/tests/python/test_intake.py system/tests/commands.bats`

Run: `git commit -q -F .scratch/msg-1.txt`
