# The Brief Fits One Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The weekday brief prints only what changes what the owner queues that morning: Waiting on from the meetings imported since the previous weekday brief, friction notes new since the last brief plus a count, telemetry New in full and Recurring as a line, no lines for sources the machine role never has, and a short Before today's meetings block from the calendar, the entity notes and the Now page.

**Architecture:** Every new input is a deterministic prep file under `system/logs/inputs/<date>/` written by `brief_prep.sh` from scripts in `vaultlib`; `/brief` copies the files and applies the section order. Three new modules: `vaultlib/briefings.py` (which briefing came before today), `vaultlib/friction.py` (`friction.md`), `vaultlib/meeting_prep.py` (`people.md`). `meeting_actions.py` changes its Waiting on window. The focus step becomes role-aware in both prep scripts. No model reads a note the scripts did not already print.

**Tech Stack:** Python 3 (stdlib and `vaultlib`), bash, bats 1.8.2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-brief-one-screen-design.md`

## Global Constraints

- Work on branch `feat/brief-one-screen` of `kferran/Foundry`, created from `docs/brief-one-screen` (the spec and this plan are its first commits). Every task commits there. No task pushes or opens a pull request; no task touches the vault's `master`.
- Template rule: never commit a hostname, user path, remote URL, employer, client, codebase or people name. Fixtures use "Avery Sample", "Blake Sample", "Gavin Sample", `acme`, `example.com`.
- New prose follows the Writing rules in `CLAUDE.md`.
- Run every command from the repository root after `mkdir -p .scratch/tmp` and `export TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch`. Read a test verdict from its exit code, never through a pipe. Never run two gates at once.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Commits use `git commit -q -F .scratch/<file>`.
- Headless tool rules in `brief.md` and `debrief.md` stay as they are (Bash only for `vault_index.py`, one call per step); the commands only read prep files the scripts wrote.
- Times: the meetings log records ISO 8601 with an offset; the previous brief's run time is that day's `brief_time` in the config `timezone`. Compare aware datetimes only.
- Bound tools: pytest (`system/tests/python/test_briefings.py`, `test_meeting_actions.py`, `test_friction.py`, `test_meeting_prep.py`, `test_now.py`), bats (`system/tests/prep.bats`, `commands.bats`) and the gate `system/scripts/verify_setup.sh`.

## Review Focus

1. **A vault with no earlier briefing** (first morning, or a client's first interactive `/brief`): Waiting on must fall back to a 7-day window and friction must print every flagged note, never crash on an empty `briefings/`. Pinned in Task 2 (`test_no_earlier_briefing_uses_a_seven_day_window`) and Task 3 (`test_with_no_earlier_briefing_every_flagged_note_is_new`).
2. **An `imported` record whose meeting note was deprecated or deleted since** must be skipped, not raise. Pinned in Task 2 (`test_an_imported_note_that_is_gone_or_deprecated_is_skipped`).
3. **An entity alias inside a longer word** ("Alex" in "Alexandria sync") must not match; a title with punctuation ("Acme / Porch sync") must. Pinned in Task 4 (`test_whole_word_match_only`).
4. **A Now line that names the entity inside a wikilink or in the statement** (`who` empty) must count for that entity. Pinned in Task 4 (`test_now_lines_match_by_who_or_by_name_in_the_statement`).
5. **An existing briefing with the old Friction Matrix heading** edited by `/brief` the morning after the update must come out with the Blockers heading once, not both. Pinned in Task 6 (the `commands.bats` assertion on the replace rule).

---

## File Structure

| File | Responsibility |
|---|---|
| `system/scripts/vaultlib/briefings.py` (create) | `earlier_briefings(vault, day)`: dated briefing paths before a day, newest first; `previous_weekday_briefing(vault, day)` |
| `system/scripts/vaultlib/now.py` (modify) | `latest_open_objectives` uses `briefings.earlier_briefings` |
| `system/scripts/vaultlib/meetings.py` (modify) | `owner_names(vault)`, `open_actions(body)`, moved from the script so two scripts share them |
| `system/scripts/meeting_actions.py` (modify) | Waiting on from imports since the previous weekday brief; first-name merge |
| `system/scripts/vaultlib/friction.py` (create) + `system/scripts/friction_notes.py` (create) | `friction.md`: new flagged notes plus the count |
| `system/scripts/vaultlib/meeting_prep.py` (create) + `system/scripts/meeting_prep.py` (create) | `people.md`: Before today's meetings |
| `system/scripts/brief_prep.sh`, `debrief_prep.sh` (modify) | the two new prep files; the focus step only on `standalone` |
| `.claude/commands/brief.md`, `debrief.md`, `system/templates/daily-briefing.md` (modify) | section order, Blockers heading, conditionals |
| `FOUNDRY.md` (modify) | the `/brief` row, Brief inputs, Friction and focus |
| tests | `test_briefings.py` (create), `test_meeting_actions.py`, `test_friction.py` (create), `test_meeting_prep.py` (create), `test_now.py`, `prep.bats`, `commands.bats` |

---

### Task 1: Which briefing came before today

**Files:**
- Create: `system/scripts/vaultlib/briefings.py`
- Modify: `system/scripts/vaultlib/now.py:197-215`
- Test: `system/tests/python/test_briefings.py` (create), `system/tests/python/test_now.py` (regression)

**Interfaces:**
- Produces: `briefings.LOOKBACK_DAYS = 30`; `briefings.earlier_briefings(vault, day: str, lookback: int | None = LOOKBACK_DAYS) -> list[tuple[str, Path]]`: `(date, path)` for each `briefings/<date>.md` or `briefings/archive/<YYYY-MM>/<date>.md` dated before `day`, newest first, within `lookback` days, or every dated briefing file under `briefings/` and `briefings/archive/` when `lookback` is `None` (the live file wins over an archive copy of the same date); `briefings.previous_weekday_briefing(vault, day: str) -> str | None`: the newest such date that is a Monday to Friday.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

Create `system/tests/python/test_briefings.py`:

````python
"""vaultlib/briefings.py: the briefings that came before a day (one-screen brief spec §3.2, §3.3)."""
from helpers import write
from vaultlib import briefings


def brief(vault, day, archived=False):
    rel = f"briefings/archive/{day[:7]}/{day}.md" if archived else f"briefings/{day}.md"
    return write(vault, rel, f'---\ntype: briefing\ndate: "{day}"\nstatus: active\n---\n# {day}\n')


def test_earlier_briefings_newest_first_from_live_and_archive(vault):
    brief(vault, "2026-10-09", archived=True)
    brief(vault, "2026-10-10")
    brief(vault, "2026-10-12")  # today: excluded
    brief(vault, "2026-09-01", archived=True)  # beyond the lookback
    assert [d for d, _ in briefings.earlier_briefings(vault, "2026-10-12")] == ["2026-10-10", "2026-10-09"]


def test_a_live_file_wins_over_its_archive_copy(vault):
    brief(vault, "2026-10-10", archived=True)
    live = brief(vault, "2026-10-10")
    assert briefings.earlier_briefings(vault, "2026-10-11") == [("2026-10-10", live)]


def test_previous_weekday_briefing_skips_the_weekend(vault):
    for day in ("2026-10-09", "2026-10-10", "2026-10-11"):  # Fri, Sat, Sun
        brief(vault, day)
    assert briefings.previous_weekday_briefing(vault, "2026-10-12") == "2026-10-09"
    assert briefings.previous_weekday_briefing(vault, "2026-10-10") == "2026-10-09"


def test_no_earlier_briefing_is_none(vault):
    assert briefings.earlier_briefings(vault, "2026-10-12") == []
    assert briefings.previous_weekday_briefing(vault, "2026-10-12") is None
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_briefings.py -q`
Expected: FAIL, `ModuleNotFoundError: vaultlib.briefings`.

- [ ] **Step 3: Implement `vaultlib/briefings.py`**

`earlier_briefings` with a lookback walks `day - 1` back to `day - lookback`, checks the live path then the archive path for each date, and returns the hits in that order; with `lookback=None` it globs `briefings/*.md` and `briefings/archive/*/*.md`, keeps the names matching `^\d{4}-\d{2}-\d{2}\.md$` dated before `day`, and sorts newest first with the live file first for a duplicate date. `previous_weekday_briefing` returns the first date from `earlier_briefings` whose `date.fromisoformat(d).weekday() < 5`.

- [ ] **Step 4: Make `now.latest_open_objectives` use it**

In `system/scripts/vaultlib/now.py`, replace the `for back in range(1, LOOKBACK_DAYS + 1)` loop's path search with `for earlier, path in briefings.earlier_briefings(vault, day):` and keep the section parsing. Keep `LOOKBACK_DAYS` in `now.py` as an alias of `briefings.LOOKBACK_DAYS`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_briefings.py system/tests/python/test_now.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

`git add system/scripts/vaultlib/briefings.py system/scripts/vaultlib/now.py system/tests/python/test_briefings.py` then `git commit -q -F .scratch/c1` with the message `feat(brief): vaultlib/briefings knows which briefing came before today`.

---

### Task 2: Waiting on from the meetings imported since the previous weekday brief

**Files:**
- Modify: `system/scripts/vaultlib/meetings.py` (append), `system/scripts/meeting_actions.py`
- Test: `system/tests/python/test_meeting_actions.py`

**Interfaces:**
- Consumes: `briefings.previous_weekday_briefing`; `frontmatter.parse`; the `imported` records `{"time", "kind": "imported", "source", "note", "complete"}` in `system/logs/meetings-<YYYY-MM>.jsonl`.
- Produces: `meetings.OPEN_ACTION` (the `OPEN` regex, moved); `meetings.owner_names(vault) -> set[str]` and `meetings.open_actions(body: str) -> list[tuple[list[str], str | None, str]]`, moved from the script unchanged in behavior; `meeting_actions.window_start(vault, day: str) -> datetime` (aware, config timezone): `previous_weekday_briefing` at `brief_time`, else `day - 7 days` at 00:00; `meeting_actions.merge_first_names(groups: dict[str, list[str]]) -> dict[str, list[str]]`.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_meeting_actions.py`, replace `test_others_actions_drop_off_after_14_days_and_the_users_stay` with these, and add the helper:

````python
def imported(vault, note, when):
    rec = {"time": when, "kind": "imported", "source": "raw/meetings/x.gdoc.md", "note": note, "complete": True}
    path = vault / f"system/logs/meetings-{when[:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def brief(vault, day):
    write(vault, f"briefings/{day}.md", f'---\ntype: briefing\ndate: "{day}"\nstatus: active\n---\n')


def test_waiting_on_lists_only_what_was_imported_since_the_previous_weekday_brief(av):
    brief(av, "2026-10-05")  # Monday, run at 06:00 America/Denver
    before, after = "2026-10-02-0900-friday", "2026-10-05-1500-monday"
    for name in (before, after):
        write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{before}.md", "2026-10-05T05:30:00-06:00")
    imported(av, f"wiki/work/meetings/{after}.md", "2026-10-05T16:00:00-06:00")
    waiting = section(actions(av, "2026-10-06"), "Waiting on")
    assert f"[[{after}]]" in "".join(waiting) and f"[[{before}]]" not in "".join(waiting)
    assert len(section(actions(av, "2026-10-06"), "Yours")) == 4  # the user's own, any age


def test_a_friday_meeting_imported_monday_morning_prints_on_tuesday(av):
    brief(av, "2026-10-05")
    name = "2026-10-02-1730-late-friday"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-05T08:00:00-06:00")
    assert f"[[{name}]]" in "".join(section(actions(av, "2026-10-06"), "Waiting on"))


def test_a_weekend_brief_lists_no_waiting_on_and_monday_covers_since_friday(av):
    brief(av, "2026-10-09")  # Friday
    name = "2026-10-09-1500-friday"
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-09T16:00:00-06:00")
    assert section(actions(av, "2026-10-10"), "Waiting on") == ["None."]
    assert section(actions(av, "2026-10-11"), "Waiting on") == ["None."]
    assert f"[[{name}]]" in "".join(section(actions(av, "2026-10-12"), "Waiting on"))


def test_no_earlier_briefing_uses_a_seven_day_window(av):
    old, recent = "2026-09-27-0900-old", "2026-10-01-0900-recent"
    for name in (old, recent):
        write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))
    imported(av, f"wiki/work/meetings/{old}.md", "2026-09-28T10:00:00-06:00")
    imported(av, f"wiki/work/meetings/{recent}.md", "2026-10-01T10:00:00-06:00")
    waiting = "".join(section(actions(av, "2026-10-06"), "Waiting on"))
    assert f"[[{recent}]]" in waiting and f"[[{old}]]" not in waiting


def test_an_imported_note_that_is_gone_or_deprecated_is_skipped(av):
    brief(av, "2026-10-05")
    gone, dep = "2026-10-05-0900-gone", "2026-10-05-1000-dep"
    write(av, f"wiki/work/meetings/{dep}.md", meeting("work", dep, body=ACTIONS, status="deprecated"))
    imported(av, f"wiki/work/meetings/{gone}.md", "2026-10-05T16:00:00-06:00")
    imported(av, f"wiki/work/meetings/{dep}.md", "2026-10-05T16:00:00-06:00")
    assert section(actions(av, "2026-10-06"), "Waiting on") == ["None."]


def test_a_bare_first_name_joins_the_one_full_name_that_starts_with_it(av):
    brief(av, "2026-10-05")
    name = "2026-10-05-1500-sync"
    body = ("## Action items\n- [ ] [Gavin] Send link: Send the link.\n- [ ] [Gavin Sample] Fix 1133: Fix it.\n"
            "- [ ] [Blake] Spec: Update the spec.\n- [ ] [Blake Sample] Deck: Make the deck.\n"
            "- [ ] [Blake Samples] Other: Another Blake.\n")
    write(av, f"wiki/work/meetings/{name}.md", meeting("work", name, body=body))
    imported(av, f"wiki/work/meetings/{name}.md", "2026-10-05T16:00:00-06:00")
    waiting = section(actions(av, "2026-10-06"), "Waiting on")
    assert waiting.count("### Gavin Sample") == 1 and "### Gavin" not in waiting
    assert "### Blake" in waiting  # two full names start with Blake: left as written
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_meeting_actions.py -q`
Expected: FAIL on the six new tests (the old 14-day window prints the Friday item, the weekend brief prints items, the names stay split).

- [ ] **Step 3: Move `owner_names` and `open_actions` into `vaultlib/meetings.py`**

Append `OPEN_ACTION`, `owner_names(vault)` and `open_actions(body)` to `system/scripts/vaultlib/meetings.py` with the bodies from `meeting_actions.py`; the script imports them. Behavior unchanged.

- [ ] **Step 4: Implement the window in `meeting_actions.py`**

Add `window_start(vault, day)` as in Interfaces (`brief_time` and `timezone` from `system/config.md` through `frontmatter.parse`, defaults `06:00` and UTC). In `main`: when `date.fromisoformat(day).weekday() >= 5`, `others` stays empty. Otherwise read every `system/logs/meetings-*.jsonl` record with `kind == "imported"` and an aware `time` after `window_start`; for each distinct `note` whose file exists and whose frontmatter has no `status: deprecated`, add its others' open actions to `others`, keyed by owner, with the meeting's `date` as today. `mine` keeps the current loop over `v_meeting`. Then `others = merge_first_names(others)`: a key with no space joins the one key that starts with `key + " "` (case-folded) when exactly one does; `### Unassigned` is untouched.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_meeting_actions.py system/tests/python/test_meetings.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -q -F .scratch/c2` with `feat(brief): Waiting on lists what was imported since the previous weekday brief, once`.

---

### Task 3: Friction notes new since the last brief, plus a count

**Files:**
- Create: `system/scripts/vaultlib/friction.py`, `system/scripts/friction_notes.py` (executable)
- Modify: `system/scripts/brief_prep.sh` (after the `now.md` step)
- Test: `system/tests/python/test_friction.py` (create), `system/tests/prep.bats`

**Interfaces:**
- Consumes: `briefings.earlier_briefings` (with `LOOKBACK_DAYS` lifted to cover the whole archive: pass `lookback=None` to walk every file under `briefings/` and `briefings/archive/`); the index view `v_concept` (`path`, `title`, `compiled_at`, `is_friction`).
- Produces: `friction.listed_before(vault, day: str) -> set[str]`: the `[[Name]]` targets under a `**Friction**` part or the old `**Friction notes**` bullet in every briefing dated before `day`; `friction.render(vault, day: str) -> str`: `- [[Name]]` lines (newest `compiled_at` first, then path) for active flagged notes not listed before, then `N open friction notes` on its own line; `friction_notes.py YYYY-MM-DD` prints it (exit 2 on a bad date).

- [ ] **Step 1: Write the failing tests**

Create `system/tests/python/test_friction.py`:

````python
"""vaultlib/friction.py: friction notes new since the last brief (one-screen brief spec §3.3)."""
import shutil
import subprocess
import sys

from helpers import REPO, concept, write
from vaultlib import friction

NEW_STYLE = "## 🛑 Blockers\n- **Telemetry**: none.\n- **Friction**:\n  - [[Alpha]]\n  3 open friction notes\n"
OLD_STYLE = "## 🛑 Real-Time Workflow Friction Matrix\n- **Systemic Blockers**:\n  - **Friction notes** (2). Act on today: [[Beta]], [[Gamma]].\n"


def flagged(vault, name, compiled, active=True):
    extra = {"is_friction": '"true"', "compiled_at": f'"{compiled}"'}
    if not active:
        extra["status"] = "deprecated"
    write(vault, f"wiki/work/concepts/{name}.md", concept("work", name, **extra))


def brief(vault, day, body):
    write(vault, f"briefings/{day}.md", f'---\ntype: briefing\ndate: "{day}"\nstatus: active\n---\n{body}')


def test_a_flagged_note_prints_once_and_is_counted_after(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Delta", "2026-10-10")
    brief(vault, "2026-10-10", NEW_STYLE)
    assert friction.render(vault, "2026-10-11") == "- [[Delta]]\n2 open friction notes\n"


def test_a_name_under_the_old_friction_notes_bullet_is_not_new(vault):
    flagged(vault, "Beta", "2026-10-01")
    flagged(vault, "Gamma", "2026-10-01")
    brief(vault, "2026-10-10", OLD_STYLE)
    assert friction.listed_before(vault, "2026-10-11") == {"Beta", "Gamma"}
    assert friction.render(vault, "2026-10-11") == "2 open friction notes\n"


def test_with_no_earlier_briefing_every_flagged_note_is_new(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Delta", "2026-10-10")
    assert friction.render(vault, "2026-10-11") == "- [[Delta]]\n- [[Alpha]]\n2 open friction notes\n"


def test_an_inactive_flagged_note_is_neither_printed_nor_counted(vault):
    flagged(vault, "Alpha", "2026-10-09")
    flagged(vault, "Old", "2026-10-09", active=False)
    assert friction.render(vault, "2026-10-11") == "- [[Alpha]]\n1 open friction note\n"


def test_the_script_prints_the_rendering(vault):
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    flagged(vault, "Alpha", "2026-10-09")
    p = subprocess.run([sys.executable, str(vault / "system/scripts/friction_notes.py"), "2026-10-11"],
                       capture_output=True, text=True)
    assert (p.returncode, p.stdout) == (0, "- [[Alpha]]\n1 open friction note\n")
    assert subprocess.run([sys.executable, str(vault / "system/scripts/friction_notes.py"), "bad"]).returncode == 2
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_friction.py -q`
Expected: FAIL, `ModuleNotFoundError: vaultlib.friction`.

- [ ] **Step 3: Implement `vaultlib/friction.py` and the script**

`listed_before` reads each earlier briefing's body (every `briefings/*.md` and `briefings/archive/*/*.md` whose date is before `day`), finds the text from a line containing `**Friction**` or `**Friction notes**` up to the next line that starts a new part (`- **` at the same indent or a `## ` heading), and collects `WIKILINK` targets (`vaultlib.now.WIKILINK`). `render` queries the index (`Index(vault).refresh(timeout=60)`, then `SELECT path, title, compiled_at FROM v_concept WHERE is_friction = 1 ORDER BY compiled_at DESC, path`), prints `- [[<stem>]]` for each path whose stem is not in `listed_before`, then the count line with the singular for 1. `friction_notes.py` mirrors `meeting_actions.py`'s `main` (date argument, exit 2 on an invalid date).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_friction.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing bats test**

Append to `system/tests/prep.bats`:

````text
@test "brief_prep: friction.md lists the flagged notes no earlier brief named, then the count" {
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-09-30\npartition: work\nis_friction: "true"\n---\n# Stuck\n' > wiki/work/concepts/Stuck.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- [[Stuck]]' "$IN/friction.md"
  grep -qx '1 open friction note' "$IN/friction.md"
}
````

- [ ] **Step 6: Run it to verify it fails**

Run: `bats system/tests/prep.bats -f 'friction.md'`
Expected: FAIL, no `friction.md`.

- [ ] **Step 7: Add the prep step**

In `system/scripts/brief_prep.sh`, after the `now.md` step: `prep_write friction.md system/scripts/friction_notes.py "$PREP_DATE" || prep_unavailable "friction: friction_notes.py failed (see $PREP_DIR/prep_errors.log)"`.

- [ ] **Step 8: Run the bats test to verify it passes**

Run: `bats system/tests/prep.bats -f 'friction.md'`
Expected: PASS.

- [ ] **Step 9: Commit**

`git commit -q -F .scratch/c3` with `feat(brief): friction.md lists the notes new since the last brief, plus a count`.

---

### Task 4: Before today's meetings

**Files:**
- Create: `system/scripts/vaultlib/meeting_prep.py`, `system/scripts/meeting_prep.py` (executable)
- Modify: `system/scripts/brief_prep.sh` (after the `friction.md` step; it needs `calendar.tsv` and the Now pages)
- Test: `system/tests/python/test_meeting_prep.py` (create), `system/tests/prep.bats`

**Interfaces:**
- Consumes: `calendar.tsv` rows `start_date\tstart_time\tend_date\tend_time\ttitle`; the index (`notes` rows with `active = 1` under `wiki/<p>/entities/` for `<p>` in the default partition and `shared`, with `notes_fts.aliases`); `now.read`, `now.open_lines`, `now.LINE`; `meetings.open_actions`, `meetings.owner_names`.
- Produces: `meeting_prep.entities(vault, conn, partitions) -> list[tuple[str, str, list[str]]]` as `(path, title, aliases)`, the active notes under `wiki/<p>/entities/` for `<p>` in `partitions`, with `aliases` read from each note's frontmatter; `meeting_prep.matches(title: str, name: str) -> bool` (whole words, case-folded, punctuation-insensitive); `meeting_prep.render(vault, day: str, calendar: Path) -> str`; `meeting_prep.py YYYY-MM-DD` prints `render` for `system/logs/inputs/<date>/calendar.tsv` (empty output when the file is missing or empty; exit 2 on a bad date).
- Output format, per entity in calendar order, at most five entities and five lines each:
  ```
  ### [[Avery Sample]] (09:00 Avery Sync)
  - owed: Send the capability doc (Avery Sample, since 2026-10-03)
  - waiting: Lincoln contact name (Avery Sample, since 2026-10-05)
  - action: Draft plan: Send the draft. ([[2026-10-05-1500-weekly-sync]])
  ```
  Line 2 lines are the Now lines verbatim without their `- [ ] ` prefix, `owed` then `waiting` then `draft`; line 3 lines are the entity's open meeting actions, newest meeting first, only when the entity is one of the owners. An entity with nothing to show prints its heading line alone (builder's call, per spec §6).

- [ ] **Step 1: Write the failing tests**

Create `system/tests/python/test_meeting_prep.py`:

````python
"""vaultlib/meeting_prep.py: Before today's meetings (one-screen brief spec §3.6)."""
import shutil
import subprocess
import sys

from helpers import REPO, concept, meeting, write
from vaultlib import meeting_prep

NOW = ("---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n# Now\n\n## Needs you\n"
       "- [ ] owed: Send the capability doc (Avery Sample, since 2026-10-03)\n"
       "- [ ] draft: Reply to [[Avery Sample]] on the pilot (since 2026-10-04)\n"
       "- [ ] owed: Unrelated line (since 2026-10-04)\n\n## Waiting\n"
       "- [ ] waiting: Lincoln contact name (Avery Sample, since 2026-10-05)\n")
ACTIONS = "## Action items\n- [ ] [Avery Sample] Draft plan: Send the draft.\n- [ ] [Blake Sample] Deck: Make it.\n"


def calendar(vault, *rows):
    text = "".join("\t".join(r) + "\n" for r in rows)
    return write(vault, "system/logs/inputs/2026-10-06/calendar.tsv", text)


def setup(vault):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\ndefault_partition: "work"\n'
          'owner_names: ["Casey Owner"]\n---\n')
    write(vault, "wiki/work/entities/AverySample.md", concept("work", "Avery Sample", aliases='["Avery", "A. Sample"]'))
    write(vault, "wiki/work/entities/Acme.md", concept("work", "Acme"))
    write(vault, "wiki/personal/entities/BlakeSample.md", concept("personal", "Blake Sample"))
    write(vault, "wiki/work/Now.md", NOW)
    name = "2026-10-05-1500-weekly-sync"
    write(vault, f"wiki/work/meetings/{name}.md", meeting("work", name, body=ACTIONS))


def test_an_event_naming_an_entity_prints_its_block_in_calendar_order(vault):
    setup(vault)
    cal = calendar(vault, ("2026-10-06", "10:00", "2026-10-06", "10:30", "Acme / Porch sync"),
                   ("2026-10-06", "09:00", "2026-10-06", "09:30", "Avery Sync"))
    assert meeting_prep.render(vault, "2026-10-06", cal) == (
        "### [[Avery Sample]] (09:00 Avery Sync)\n"
        "- owed: Send the capability doc (Avery Sample, since 2026-10-03)\n"
        "- waiting: Lincoln contact name (Avery Sample, since 2026-10-05)\n"
        "- draft: Reply to [[Avery Sample]] on the pilot (since 2026-10-04)\n"
        "- action: Draft plan: Send the draft. ([[2026-10-05-1500-weekly-sync]])\n\n"
        "### [[Acme]] (10:00 Acme / Porch sync)\n")


def test_whole_word_match_only(vault):
    assert meeting_prep.matches("Alexandria sync", "Alex") is False
    assert meeting_prep.matches("acme / porch SYNC", "Acme") is True
    assert meeting_prep.matches("1:1 with A. Sample", "A. Sample") is True


def test_now_lines_match_by_who_or_by_name_in_the_statement(vault):
    setup(vault)
    cal = calendar(vault, ("2026-10-06", "09:00", "2026-10-06", "09:30", "Avery Sync"))
    out = meeting_prep.render(vault, "2026-10-06", cal)
    assert "Reply to [[Avery Sample]]" in out and "Unrelated line" not in out


def test_five_entities_and_five_lines_at_most_and_each_entity_once(vault):
    setup(vault)
    for i in range(7):
        write(vault, f"wiki/work/entities/Person{i}.md", concept("work", f"Person{i}"))
    rows = [("2026-10-06", f"{9 + i:02d}:00", "2026-10-06", f"{9 + i:02d}:30", f"Person{i} sync") for i in range(7)]
    rows.append(("2026-10-06", "17:00", "2026-10-06", "17:30", "Person0 again"))
    out = meeting_prep.render(vault, "2026-10-06", calendar(vault, *rows))
    assert out.count("### ") == 5 and out.count("[[Person0]]") == 1
    lines = ["- [ ] owed: Item %d (Person1, since 2026-10-01)" % i for i in range(8)]
    write(vault, "wiki/work/Now.md", NOW + "\n".join(lines) + "\n")
    block = meeting_prep.render(vault, "2026-10-06", calendar(vault, *rows[:2])).split("\n\n")[1]
    assert block.count("\n- ") == 5


def test_a_personal_entity_never_appears_in_a_work_brief_and_no_match_is_empty(vault):
    setup(vault)
    cal = calendar(vault, ("2026-10-06", "09:00", "2026-10-06", "09:30", "Blake Sample 1:1"))
    assert meeting_prep.render(vault, "2026-10-06", cal) == ""


def test_the_script_reads_the_days_calendar_and_is_empty_without_one(vault):
    setup(vault)
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    p = subprocess.run([sys.executable, str(vault / "system/scripts/meeting_prep.py"), "2026-10-06"],
                       capture_output=True, text=True)
    assert (p.returncode, p.stdout) == (0, "")
    calendar(vault, ("2026-10-06", "09:00", "2026-10-06", "09:30", "Avery Sync"))
    p = subprocess.run([sys.executable, str(vault / "system/scripts/meeting_prep.py"), "2026-10-06"],
                       capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.startswith("### [[Avery Sample]] (09:00 Avery Sync)\n")
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_meeting_prep.py -q`
Expected: FAIL, `ModuleNotFoundError: vaultlib.meeting_prep`.

- [ ] **Step 3: Implement `vaultlib/meeting_prep.py` and the script**

`matches` compares word sequences: both strings lower-cased, split on `[^\w.]+` after dropping empty tokens; `name` matches when its token list occurs as a contiguous run in the title's. `entities` reads `SELECT path, title, partition FROM notes WHERE active = 1 AND path LIKE 'wiki/%/entities/%'`, keeps the rows whose partition is in `partitions`, and reads each note's `aliases` list from its frontmatter (`frontmatter.parse`; `notes_fts` joins aliases with spaces, which loses multi-word aliases). `render` reads the calendar rows in start order, matches each title against every entity (title first, then aliases), keeps the first five distinct entities, and for each builds the lines: Now lines from `now.open_lines(now.read(vault, default_partition))` where `LINE` gives `who == title` or the title occurs in the statement (plain or inside `[[…]]`), ordered `owed`, `waiting`, `draft`; then open actions whose owners contain the title (case-folded), from `v_meeting` notes newest first; cut at five lines. Blocks are joined with a blank line; a day with no block returns `""`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_meeting_prep.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing bats test**

Append to `system/tests/prep.bats`:

````text
@test "brief_prep: people.md holds the Before today's meetings blocks, empty when no event names an entity" {
  printf -- '---\ntype: concept\ntags: []\ncompiled_at: 2026-09-30\npartition: personal\n---\n# Standup Crew\n' > wiki/personal/entities/StandupCrew.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ -f "$IN/people.md" ]
  [ ! -s "$IN/people.md" ]
  calendar_says '{"status":"ok","reason":"","events":[{"start_date":"2026-10-01","start_time":"09:00","end_date":"2026-10-01","end_time":"09:30","title":"Standup Crew sync"}]}'
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx '### \[\[Standup Crew\]\] (09:00 Standup Crew sync)' "$IN/people.md"
}
````

(The fixture vault's `default_partition` is `personal`; check `make_vault` in `helpers.bash` and use the partition it sets.)

- [ ] **Step 6: Run it to verify it fails**

Run: `bats system/tests/prep.bats -f 'people.md'`
Expected: FAIL, no `people.md`.

- [ ] **Step 7: Add the prep step**

In `system/scripts/brief_prep.sh`, after the `friction.md` step: `prep_write people.md system/scripts/meeting_prep.py "$PREP_DATE" || prep_unavailable "people: meeting_prep.py failed (see $PREP_DIR/prep_errors.log)"`.

- [ ] **Step 8: Run the bats test to verify it passes**

Run: `bats system/tests/prep.bats -f 'people.md'`
Expected: PASS.

- [ ] **Step 9: Commit**

`git commit -q -F .scratch/c4` with `feat(brief): people.md, the Before today's meetings block from the calendar, entities and the Now page`.

---

### Task 5: A source the role never has is not unavailable

**Files:**
- Modify: `system/scripts/brief_prep.sh` (the `focus_yesterday.md` step), `system/scripts/debrief_prep.sh` (the `focus.md` step)
- Test: `system/tests/prep.bats`

**Interfaces:**
- Consumes: `config_get machine_role standalone` (`lib_config.sh`).
- Produces: on `server` and `client`, neither script writes a focus file or a focus line in `unavailable.md`; on `standalone`, both behave as today.

- [ ] **Step 1: Write the failing bats tests**

Append to `system/tests/prep.bats`:

````text
@test "prep scripts: a server or client writes no focus file and no focus line; standalone does as today" {
  system/scripts/vault_index.py set system/config.md machine_role server
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/focus_yesterday.md" ]
  run "$DP" 2026-10-01
  [ "$status" -eq 0 ]
  [ ! -e "$IN/focus.md" ]
  run grep -c 'focus' "$IN/unavailable.md"
  [ "$status" -eq 1 ]
  system/scripts/vault_index.py set system/config.md machine_role standalone
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qx -- '- brief_prep: focus_yesterday: no focus log for 2026-09-30' "$IN/unavailable.md"
}
````

- [ ] **Step 2: Run it to verify it fails**

Run: `bats system/tests/prep.bats -f 'no focus file'`
Expected: FAIL, `focus_yesterday.md` exists on a server.

- [ ] **Step 3: Guard both focus steps**

In each prep script wrap the focus step: `if [[ "$(config_get machine_role standalone)" == standalone ]]; then … existing lines … fi`.

- [ ] **Step 4: Run the suite to verify it passes**

Run: `bats system/tests/prep.bats`
Expected: PASS (the existing focus tests run on the fixture's default role, which stays `standalone`; if `make_vault` sets another role, set `standalone` in those tests).

- [ ] **Step 5: Commit**

`git commit -q -F .scratch/c5` with `fix(prep): no focus step on a server or client`.

---

### Task 6: The commands, the template and the manual

**Files:**
- Modify: `.claude/commands/brief.md`, `.claude/commands/debrief.md`, `system/templates/daily-briefing.md`, `FOUNDRY.md`
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: `friction.md`, `people.md`, `actions.md` (its Waiting on now one brief's worth), the telemetry query as today.
- Produces: the section order of spec §3.1 and the wording the tests below pin.

- [ ] **Step 1: Write the failing bats assertions**

In `system/tests/commands.bats`, in the test `brief: headless contract, allowlisted index calls, template sections`, replace the `friction_line` lookup with `blockers_line="$(grep -nx '## 🛑 Blockers' "$t" | cut -d: -f1)"` and the comparison with `[ "$projects_line" -lt "$blockers_line" ]`. In the test `meetings: /brief reads actions.md…`, replace `grep -qF 'its Notices go under Systemic Blockers' "$f"` with `grep -qF 'its Notices go under **Pipeline**' "$f"`. Then add:

````text
@test "the one-screen brief: order, the people block, friction and Recurring as prep files give them, role-aware lines" {
  f=.claude/commands/brief.md
  grep -qF '`system/logs/inputs/<date>/friction.md`' "$f"
  grep -qF '`system/logs/inputs/<date>/people.md`' "$f"
  grep -qF '**Before today'"'"'s meetings**' "$f"
  grep -qF 'print `people.md` verbatim' "$f"
  grep -qF 'print `friction.md` verbatim' "$f"
  grep -qF 'Recurring: N groups' "$f"
  grep -qF 'one brief'"'"'s worth: the meetings imported since the previous weekday brief' "$f"
  grep -qF 'Omit **Focus Drift** when `focus_yesterday.md` does not exist' "$f"
  grep -qF 'replace the old `## 🛑 Real-Time Workflow Friction Matrix` heading with `## 🛑 Blockers`' "$f"
  t=system/templates/daily-briefing.md
  grep -qx -- '- **Telemetry**:' "$t"
  grep -qx -- '- **Friction**:' "$t"
  grep -qx -- '- **Pipeline**:' "$t"
  grep -qx -- '- **Communication Debt**:' "$t"
  run grep -c 'Focus Drift' "$t"
  [ "$status" -eq 1 ]
  d=.claude/commands/debrief.md
  grep -qF 'Omit the Focus paragraph when `focus.md` does not exist' "$d"
  grep -qF 'Omit **3. Agent Health** when `system/logs/metrics/` holds no file' "$d"
  grep -qF 'Before today'"'"'s meetings' FOUNDRY.md
  grep -qF 'imported since the previous weekday brief' FOUNDRY.md
}
````

- [ ] **Step 2: Run them to verify they fail**

Run: `bats system/tests/commands.bats`
Expected: FAIL on the new test and on the two edited assertions.

- [ ] **Step 3: Edit `brief.md`**

- Inputs: add `friction.md` (the lines to print under Friction) and `people.md` (the Before today's meetings blocks), and reword the `actions.md` line: Waiting on is one brief's worth: the meetings imported since the previous weekday brief, printed once. Remove the friction index query.
- Write the briefing: after the fixed commitments, **Before today's meetings**: print `people.md` verbatim, or nothing when it is empty. Keep From Now, Yours and Waiting on as they are, then 🎯 Active Projects, then the Blockers section with four parts in this order: **Telemetry** (the New tables as today; Recurring as one line per environment, `Recurring: N groups`, then the three largest by `count` as `service exception (count)`; Resolved as today), **Friction** (print `friction.md` verbatim, the count line last), **Pipeline** (pipeline alerts, quarantined inputs, the Notices from `actions.md` and `projects.md`, a FAILED Health line from `nightshift.md`; when `actions.md` has Notices, its Notices go under **Pipeline**), **Communication Debt** (as today). Omit **Focus Drift** when `focus_yesterday.md` does not exist; otherwise print yesterday's warnings as a fifth part. Then 🧾 Handoffs and 🛠 Work Orders as today.
- Existing briefing: when `/brief` edits a briefing that has the old heading, replace the old `## 🛑 Real-Time Workflow Friction Matrix` heading with `## 🛑 Blockers` and rewrite its parts; the Active Projects placement rule now says "before the Blockers section".

- [ ] **Step 4: Edit `debrief.md`, the template and `FOUNDRY.md`**

`debrief.md`: Omit the Focus paragraph when `focus.md` does not exist; Omit **3. Agent Health** when `system/logs/metrics/` holds no file (the section numbers stay). The template's Blockers block replaces the matrix with the four `- **…**:` lines. `FOUNDRY.md`: the `/brief` row names Before today's meetings, Friction and the Blockers section; **Brief inputs** adds `friction.md` and `people.md` and says Waiting on covers the meetings imported since the previous weekday brief; **Friction and focus** says the focus tracker runs on a standalone machine only and the brief prints friction notes new since the last brief plus a count.

- [ ] **Step 5: Run the suite to verify it passes**

Run: `bats system/tests/commands.bats`
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -q -F .scratch/c6` with `feat(brief): the one-screen brief: order, Blockers, the people block, role-aware lines`.

---

### Task 7: The gate

- [ ] **Step 1: Lint**

Run: `system/scripts/lint_vault.sh`
Expected: `0 errors`.

- [ ] **Step 2: The gate**

Run: `system/scripts/verify_setup.sh > .scratch/gate.log 2>&1; echo $?` (the one allowed redirect, to capture the exit code).
Expected: `0`. On a container without a systemd user manager, `units.bats`, `remote.bats` #14, `sync.bats` #6 and `hooks_install.bats` #32 and #33 fail for environment reasons; compare against `master` in the same container before treating any of them as this branch's.

- [ ] **Step 3: Live check**

In a throwaway clone with a few meeting notes, a Now page and two flagged concepts, run `system/scripts/brief_prep.sh <today>` and read `friction.md`, `people.md` and `actions.md`; then run `/brief` interactively once and check the briefing is under 8 KB above 📝 Notes and carries the four Blockers parts once.
