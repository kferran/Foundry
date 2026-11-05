# Digest Follow-ups Become Proposed Now Lines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each `## Follow-ups` bullet of a session digest that intake archives becomes one proposed owed line (`[via:: digest]`) on its partition's Now page, unless the page already covers it.

**Architecture:** `_archive_batch` appends each archived digest's path to a queue file; a new `vaultlib/followups.py` step, run in `check_now` under `run.lock` after `heldmod.step`, reads the queue, parses each digest's Follow-ups section, skips bullets that match a candidate line, and adds the rest through `nowmod.add` with per-digest and per-day caps. `digest` joins `WRITERS` and `MACHINE`, so an untouched proposal expires after 7 days.

**Tech Stack:** Python 3 standard library (vaultlib), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-11-03-digest-followups-design.md` (approved by the owner's merge of #501, 2026-11-04; O1 = (b)).

## Global Constraints

- No model call, no staged publish, no new unit; the publish gate is untouched (spec §2 anti-goals, §3.1).
- Every line goes through `nowmod.add(..., fit=True, via="digest")`, which redacts, caps at 300 characters and enforces the partition wall.
- Line form: `- [ ] owed: <bullet> [due:: <decide-by>] [via:: digest] (since <today>, raw/<p>/archive/<name>.md)`; no `--rec`, no `who`.
- Caps: 5 bullets per digest; 10 `digest` lines per page per day. Match window: lines closed within 14 days. Contained-text floor: 12 characters. Shared-word rule: at least 3 words of 4 or more letters (a trailing `s` dropped), at least 60% of the smaller set, and only against a candidate whose `since` is on or after the day before the digest's `created_at`.
- A `shared` digest's lines go on the work page (`held.page`).
- Queue file: `system/logs/followups_queue.txt`, one vault-relative path per line, rewritten with a temp file and `os.replace`.
- Tests stub everything and use invented digest names and statements (template rule: no hostnames, user paths, employer, client, codebase or people names).
- Bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Core: 16,743 of `CORE_CAP=16750` at plan time. This PR raises the cap by what it measures over, in its own commit, with a history comment naming the spec; the owner approves it at merge (spec §4).

## Review Focus

1. A bullet cut by `fit` whose cut text drops a date the full text named: `default_due` of the cut statement may differ from the stored due, and `expires()` then treats the line as having a deadline and never expires it. Test in Task 1: a 400-character digest line with no date expires after 7 days.
2. A digest re-read the next day after the per-day cap stopped it mid-way: the bullets added the day before must match (open, `since` yesterday) so none doubles, and the per-digest alert must not repeat. Test in Task 2.
3. A queued path whose file is gone (archived digest moved or deleted by hand): one alert, dropped from the queue, never retried forever. Test in Task 2.
4. A bullet holding `[due::`, `[rec::` or `[via::` text: `validate` refuses it; one alert through `nowmod.refusal`, the other bullets still added. Test in Task 2.
5. A queue line that names a path outside `raw/<partition>/archive/` (a hand edit): skipped with one alert, never read. Test in Task 2.

---

### Task 1: `digest` is a machine writer

**Files:**
- Modify: `system/scripts/vaultlib/now.py:48-49`
- Modify: `docs/superpowers/roadmap.md` (the `#476 (digest follow-ups …): spec (#501)` line)
- Test: `system/tests/python/test_now.py`

**Interfaces:**
- Produces: `nowmod.via("x [via:: digest]") == "digest"`; `nowmod.add(..., via="digest")` writes `[via:: digest]`; `expires()` treats `digest` like `mail`.

- [ ] **Step 1: Write the failing tests** in `test_now.py`, next to the existing writer tests (around line 1043):

```python
def test_digest_is_a_writer_and_a_machine_line(vault):
    assert now.via("x [via:: digest]") == "digest"
    status, line = now.add(vault, "work", "owed", "Write the release notes", TODAY, evidence="raw/work/archive/2026-10-10-0900-a1b2c3d4-x.md", via="digest")
    assert line.endswith(f"[via:: digest] (since {TODAY}, raw/work/archive/2026-10-10-0900-a1b2c3d4-x.md)")

def test_an_untouched_digest_line_expires_after_7_days_and_a_noted_one_stays(vault):
    # lines since TODAY minus 7 days: one bare, one with a note under it, one cut to fit (400 characters, no date)
    # check() closes the bare and the cut line as "- [-] … _(closed: expired <TODAY>)_" and keeps the noted one open
```

Write the second test's body in the style of the existing expiry test at `test_now.py:1095-1107`, with `[via:: digest]` lines and the cut line produced by `now.add(..., fit=True, via="digest")` on its `since` day.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_now.py -k digest` (from the worktree root)
Expected: FAIL (`via` returns `""` for `digest`).

- [ ] **Step 3: Add `"digest"` to `WRITERS` and to `MACHINE`** in `now.py:48-49`, and extend the comment on line 46 to name it.

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest -q system/tests/python/test_now.py`
Expected: PASS, the whole file.

- [ ] **Step 5: Commit** with the roadmap mark: change the roadmap line to `#476 (…): spec merged (#501); plan and build in progress (#PR)` and commit the plan file with it.

```bash
git add docs/superpowers/plans/2026-11-04-digest-followups.md docs/superpowers/roadmap.md system/scripts/vaultlib/now.py system/tests/python/test_now.py
git commit -F <msg>   # "feat(now): digest is a machine writer (#476)"
```

### Task 2: `vaultlib/followups.py`, the step

**Files:**
- Create: `system/scripts/vaultlib/followups.py`
- Test: `system/tests/python/test_followups.py`

**Interfaces:**
- Consumes: `nowmod.add`, `nowmod.read`, `nowmod.archived`, `nowmod.LINE`, `nowmod.STAMP`, `nowmod.WIKILINK`, `nowmod.fields`, `nowmod.via`, `nowmod.refusal`, `held.page`, `frontmatter.parse`.
- Produces (Task 3 relies on these):
  - `QUEUE = Path("system/logs/followups_queue.txt")`
  - `queue(vault, rels: list) -> None`: append each vault-relative path as one line; `OSError` propagates.
  - `bullets(text: str) -> list`: the Follow-ups bullets of a digest's full text, `[]` unless its frontmatter `type` is `session_digest`.
  - `step(vault, today: str, alert) -> None`: the whole step; the caller holds `run.lock`.

Decisions the spec leaves to the builder (§9), settled here:
- Section start `^#{1,6}\s*follow[- ]?ups?\b` (any case); it ends at the next line starting with `#`.
- A bullet is a top-level line matching `^(?:[-*]|\d+\.)\s+(.+)` (any number, so a numbered list's later items count). A leading `[ ] ` is stripped; a leading `[x] ` or `[X] ` marks it done in the session and it is skipped. Whitespace collapsed. `none`, `nothing`, `n/a` (any case, optional trailing period) skipped.
- Normalize: `nowmod.WIKILINK.sub(r"\1", s)`, lowercase, `re.sub(r"[^a-z0-9]+", " ", s).strip()`.
- Candidates for a page: every line `nowmod.LINE` matches on the page and in `nowmod.archived(vault, page, today - 14 days, today)` that is open, or closed with a `STAMP` date on or after today minus 14 days; each as `(normalized bare statement, evidence, since)`. A bullet added earlier in the same digest is appended to the list.
- `created` is the digest's `created_at[:10]` when it is a real date, else `today`.
- Per-day count: lines on the page (any mark) whose `via` is `digest` and whose `since` is `today`.
- The per-digest alert is raised only when the digest leaves the queue, so a re-read never repeats it: `digest <name>: <n> follow-ups, 5 proposed`.
- A refused bullet: `alert(f"digest {name}: a follow-up was skipped: {nowmod.refusal(exc)}")`.
- A queued path that is not `raw/<work|personal|shared>/archive/<name>.md`, or a file that cannot be read: one alert (`follow-ups of <rel> skipped: <reason>`; for a bad path, `a follow-ups queue line is not an archived digest`, naming no path), and the entry leaves the queue.
- The queue is rewritten with what is left through `.followups_queue.txt.tmp` and `os.replace`; an empty queue is removed.

- [ ] **Step 1: Write the failing tests** in `test_followups.py`. Fixture: `vault` plus `system/templates` copied (as `test_held.py:18-21`); a helper `digest(vault, p, name, body, created="2026-10-12T09:00:00-06:00", provenance="session")` that writes `raw/<p>/archive/<name>.md` with the frontmatter of `test_intake_digests.py:14-17` and calls `followups.queue(vault, [rel])`. `TODAY = "2026-10-12"`. Tests, each one assertion group:

```python
def test_three_follow_ups_become_three_digest_lines_with_the_archive_path():
    # body "## Outcome\nx\n## Follow-ups\n- Write the release notes\n- Book the venue review\n* Send the survey summary\n"
    # work page gains 3 lines, each "[via:: digest]", a "[due:: " field and "(since 2026-10-12, raw/work/archive/<name>.md)"
    # the queue file is gone

def test_a_bullet_equal_to_or_inside_an_open_line_is_skipped():          # rule 1, a waiting line counts too
def test_a_bullet_naming_an_open_lines_pull_request_is_skipped():        # rule 2: evidence https://github.com/acme/tpl/pull/7
def test_shared_words_match_a_same_day_line_and_not_a_week_old_one():    # rule 3, both sides
def test_a_line_dropped_within_14_days_skips_the_bullet_on_the_page_and_in_the_archive():
def test_a_handled_digest_leaves_the_queue_and_a_second_run_adds_nothing():
def test_a_rerun_after_a_crash_before_the_queue_rewrite_adds_nothing():  # step, restore the queue file, step again
def test_six_bullets_add_five_and_alert_once():                          # alert text "digest <name>: 6 follow-ups, 5 proposed"
def test_eleven_digests_add_ten_lines_and_the_rest_waits_for_tomorrow(): # one bullet each; 10 lines, 1 path left; next day adds 1
def test_a_digest_cut_off_by_the_day_cap_doubles_nothing_and_alerts_once_next_day():   # Review Focus 2
def test_a_personal_digest_goes_only_on_the_personal_page_and_shared_on_work():
def test_a_cross_wall_bullet_is_skipped_with_an_alert_naming_no_note():  # "[[PersonalNote]]" from a work digest; alert has "partition wall", no note name
def test_a_bullet_with_a_field_key_is_skipped_and_the_others_added():    # Review Focus 4: "Set [due:: 2026-10-20] for it"
def test_a_credential_shaped_bullet_lands_redacted():                    # a GitHub token shape; the page holds "[REDACTED:" and not the token
def test_a_long_bullet_is_cut_and_keeps_its_tag_and_evidence():          # 400 characters; line <= 300, "[via:: digest]" and the path kept
def test_non_digests_stale_claims_and_empty_sections_add_nothing():      # type meeting_input; "## Stale claims" only; no section; "- None."; "1. n/a"
def test_a_done_checkbox_bullet_is_skipped_and_numbered_items_count():   # "- [x] Merged it", "1. First", "2. Second"
def test_a_backfilled_digest_is_proposed_like_any_other():               # provenance ["headless"], name ending -backfill
def test_a_missing_file_and_a_bad_queue_line_alert_once_and_leave_the_queue():   # Review Focus 3 and 5
```

Use `test_held.py:39-41`'s `alerts()` pattern for the alert sink. Read lines back with `now.read(vault, page)`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_followups.py`
Expected: FAIL at collection (`cannot import name 'followups'`).

- [ ] **Step 3: Implement `followups.py`** with `QUEUE`, `queue`, `bullets`, `step` and private helpers for normalizing, candidates and matching, per the decisions above. Constants: `PER_DIGEST = 5`, `PER_DAY = 10`, `CLOSED_DAYS = 14`, `MIN_CONTAINED = 12`, `MIN_SHARED = 3`, `SHARED_SHARE = 0.6`. The matcher, since its three rules are what the tests pin:

```python
def _matches(bullet: str, cands: list, created: str) -> bool:
    b = _norm(bullet)
    for text, evidence, since in cands:
        short, long_ = sorted((b, text), key=len)
        if b == text or (len(short) >= MIN_CONTAINED and short in long_):
            return True
        if evidence and not evidence.startswith("raw/") and evidence in bullet:
            return True
        if since >= _day_before(created):
            x, y = _words(b), _words(text)
            shared = x & y
            if len(shared) >= MIN_SHARED and len(shared) >= SHARED_SHARE * min(len(x), len(y)):
                return True
    return False
```

`_words(s)` is `{w[:-1] if w.endswith("s") else w for w in s.split() if len(w) >= 4 and w.isalpha()}`.

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest -q system/tests/python/test_followups.py system/tests/python/test_now.py system/tests/python/test_held.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/followups.py system/tests/python/test_followups.py
git commit -F <msg>   # "feat(intake): digest follow-ups become proposed Now lines, the step (#476)"
```

### Task 3: wire it into intake, the graph and the cap

**Files:**
- Modify: `system/scripts/vaultlib/intake.py:16` (import), `:295-302` (`check_now`), `:480-490` (`_archive_batch`)
- Modify: `system/pipeline.yml` (intake node)
- Modify: `system/tests/vault_integrity.bats:9` and its history comment (after line 580)
- Test: `system/tests/python/test_intake_digests.py`, `system/tests/pipeline.bats`, `system/tests/vault_integrity.bats`

**Interfaces:**
- Consumes: `followups.queue(vault, rels)`, `followups.step(vault, today, alert)`, `followups.QUEUE` (Task 2).

- [ ] **Step 1: Write the failing tests** in `test_intake_digests.py`, using its `digest()` helper and the `iv` fixture:

```python
def test_an_archived_batch_queues_both_destinations_including_a_renamed_one(iv):
    # two digests; one name already exists in raw/work/archive/, so unique() renames it
    # Intake(iv).run(); followups_queue.txt lists both archive paths, the renamed one by its new name

def test_a_failed_rename_queues_nothing(iv, monkeypatch):
    # Path.rename raises OSError for one digest; the queue lists only the other

def test_check_now_with_a_busy_run_lock_leaves_the_queue(iv):
    # queue holds one archived digest with a follow-up; hold system/run.lock with fcntl.flock (as test_intake.py:684)
    # Intake(iv).check_now(); the queue is unchanged and the work page has no digest line
    # release the lock; check_now() again; the line is added and the queue is gone
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_intake_digests.py -k "queue or busy_run_lock"`
Expected: FAIL (no queue file is written).

- [ ] **Step 3: Implement.** In `_archive_batch`, keep each `unique(archive / p.name)` destination of a successful rename; after the loop, when any, call `followups.queue(self.vault, rels)` inside `try`, and on `OSError` raise one alert naming the digests (`could not queue the follow-ups of <names>: <exc class>: <exc>`); the digests stay archived. In `check_now`, call `followups.step(self.vault, self.today(), self.alert)` after `heldmod.step`, inside the same `with`. Update `check_now`'s docstring.

- [ ] **Step 4: Update `system/pipeline.yml`'s intake node:** `scripts` gains `system/scripts/vaultlib/followups.py`; `reads` gains `raw/*/archive/` and `system/logs/followups_queue.txt`; `writes` gains `system/logs/followups_queue.txt`.

- [ ] **Step 5: Run them to verify they pass**

Run: `python3 -m pytest -q system/tests/python/test_intake_digests.py system/tests/python/test_intake.py system/tests/python/test_followups.py`
Run: `bats system/tests/pipeline.bats`
Expected: PASS both.

- [ ] **Step 6: Commit**

```bash
git add system/scripts/vaultlib/intake.py system/pipeline.yml system/tests/python/test_intake_digests.py
git commit -F <msg>   # "feat(intake): queue archived digests and run the follow-ups step (#476)"
```

- [ ] **Step 7: Measure core and raise the cap** in its own commit. Run the core count (`git ls-files -z system/scripts system/hooks .claude/commands | xargs -0 cat | wc -l` in the worktree). Set `CORE_CAP` to the measured count rounded up to the next 10, and add the history comment after line 580: `# 16,750 -> <new> (#476 digest follow-ups, docs/superpowers/specs/2026-11-03-digest-followups-design.md, owner to approve at merge): followups.py and the intake queue took core from 16,743 to <measured>.`

Run: `bats system/tests/vault_integrity.bats`
Expected: PASS.

```bash
git add system/tests/vault_integrity.bats
git commit -F <msg>   # "test(core): cap for #476's follow-ups step (owner to approve)"
```

### Task 4: docs, release note and live acceptance

**Files:**
- Modify: `FOUNDRY.md:133` (the Now paragraph)
- Create: `changes/2026-11-04-digest-followups.md`
- Modify: `docs/superpowers/roadmap.md` (the #476 line)

- [ ] **Step 1: FOUNDRY.md.** In the Now paragraph's machine-writer sentences: `[via:: digest]` (a session digest's `## Follow-ups` bullet, added by intake after it archives the digest, with the archived digest's path as evidence, at most 5 a digest and 10 a page a day, skipped when an open line or one closed in the last 14 days already covers it) joins `mail`, `chat` and `watch` in the 7-day expiry sentence.

- [ ] **Step 2: Change file**, one line in the existing style: `- Added: each \`## Follow-ups\` bullet of a session digest becomes a proposed owed line on its partition's Now page (\`[via:: digest]\`, the digest as evidence); one you leave for 7 days expires, a note under it keeps it. (#476)`

- [ ] **Step 3: Run the docs and conformance checks**

Run: `bats system/tests/commands.bats system/tests/conformance.bats`
Expected: PASS.

- [ ] **Step 4: Live acceptance** (spec §7) in a throwaway clone of this branch under `.scratch/`, `system/config.md` from the example, intake run by hand (`system/scripts/intake.py`), sandboxed:
  1. Check first whether a stub `CLAUDE_BIN` (a script that exits 0) gets a digest archived. If it does not, stop and ask the owner for a real-claude run (sandbox off); record which one ran.
  2. Add `now.py add --partition work --kind owed --statement "Book the venue review"`; drop a digest into `raw/work/notes/` whose Follow-ups are `- Book the venue review` and `- Write the release notes`.
  3. Tick 1 archives and queues it; tick 2 (after the 60-second fresh window) adds one `[via:: digest]` line, for the release notes only.
  4. Mark it `[-]`, run intake again: nothing comes back. Remove the clone.

- [ ] **Step 5: Roadmap and commit.** Mark the roadmap line `#476 (…): first phase done (#PR); the future phase stays open on #476`, then:

```bash
git add FOUNDRY.md changes/2026-11-04-digest-followups.md docs/superpowers/roadmap.md
git commit -F <msg>   # "docs: digest follow-ups on the Now page (#476)"
```

After merge: tick the first phase on #476, leave its future-phase items open, remove the worktree.
