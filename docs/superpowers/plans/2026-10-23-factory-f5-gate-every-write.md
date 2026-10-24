# F5 PR 1: Every Now Write Passes One Check (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every write of an open Now line or a note under one is redacted, held to the 300-character cap and checked against the partition walls in `vaultlib/now.py`, machine callers drop a refused line with one alert a day, and the publish gate verifies a brief's added Now lines with the same check.

**Architecture:** `vaultlib/now.py` gains `screen_fields` (per-field redaction), `screen_line` (cap and walls on one rendered line) and `screen` (both, on a whole open line, for `fit_staged` and the gate). `now.write` refuses a symlinked page path. The wall loop moves out of `publish._walls` into `index.walled`, so the gate and `now` share it. The watch's once-a-day alert helper moves to `vaultlib/alerts.py` as `alert`, shared by triage, the watch and the RCA filer.

**Tech Stack:** Python 3 stdlib plus `vaultlib`, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-factory-f5-gate-every-write-design.md` (§4.1-§4.3; PR 2 covers §4.4-§4.6)

## Global Constraints

- PR 1 changes the publish gate and redaction: the owner merges it. No auto-merge. PR body: "Part of #310", "Closes #288 part 1" in words only (#288 stays open for PR 2).
- Redaction is `redact_credentials` only (no high-entropy guess: it eats ticket keys, GUID URLs and PR URLs).
- An alert never carries a Now line's text or any outside text: it names the caller and the `ValueError` reason from `add` (fixed strings, a count, a date or a vault path).
- No caller-side copy of the check: callers call `now` functions.
- Template stays generic: no hostnames, user paths, account IDs, or employer, client, codebase or people names in code, tests or the PR.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Core budget: 15,000 lines over `system/scripts`, `system/hooks`, `.claude/commands` (`vault_integrity.bats`). Net growth must fit; a raise needs the owner, with the reason, in this PR.
- Run only the changed files' tests locally (`system/scripts/test.sh <path>`, sandbox disabled for bats); CI runs the full suite.
- Commit messages end with `Claude-Session: https://claude.ai/code/session_01EZnnKRuLxKtqiULqPqSgoJ`; commit with `git commit -F <file>`.

## Plan decisions (refining the spec, my calls)

- **`set` keeps today's cap rule** (no `old`, no grandfather): `set` exists to shorten a line (#211), so a rewrite at the same over-cap length stays refused. The spec's §4.1 table said `old`; the current test `test_a_long_line_written_before_the_cap_keeps_working` holds today's rule.
- **`add` keeps its pre-cut** (`fit` cuts the statement before the repeat test), so a repeat machine add matches the cut line it wrote. Without `fit`, the cap runs only when `add` writes, so a repeat of an old long line still returns `exists`.
- **The alert helper is a module function**, `vaultlib.alerts.alert(vault, day, clock, tag, text, key="")`, since the watch passes its tick's day and clock and triage holds no `Intake`; `Intake.alert` calls it. `PART_HOMES` needs no line: it scans shell helpers, walkers, `Fail`, config readers and stubs, not Python alert functions.
- **Alert tags:** triage `triage` (waits for the brief; only its count goes now), the watch `intraday` (brief), the RCA filer `rca` (now, as its other alerts).
- **The symlink test sits in `now.write`**, the one write path of the Now page, so `check`, `archive` and the RCA functions get it too. `now` imports `publish._resolves` inside `write` (publish imports `now` at load time; `alerts.extension_tags` already imports this way).
- **The gate's walls stay in `_walls`** (it already walls every staged note, Now pages included); `screen` also raises on a wall, so a walled added Now line shows two Problems. Harmless.
- **A hand-shaped added line** (does not parse, or does not re-render to itself: text after the parenthesis, an invalid due) is not rebuilt. `screen` checks it whole: over the cap or holding credential-shaped text raises `ValueError`. A clean one passes as it does today.
- **`rec` redaction drops the marker's brackets** (`REDACTED:assignment`), since `validate` and `REC` refuse a bracket in `rec`. `ASSIGNMENT` and `CONNECTION` in `redact.py` then widen their guard to `(?!\[?REDACTED)`, so a second pass leaves a bracketless marker alone: `fit_staged` and the gate screen the same line twice, and a changed second pass would reject the brief.
- **Only `brief` stages a Now page** (`run_headless.sh:147-149`), so `fit-staged` stays brief-only.

## Review Focus

1. A brief's added line that is clean but hand-shaped (two spaces, an invalid `[due::]`): the gate must pass it, as it does today. Test in Task 4.
2. A credential in `--rec`: the line must still parse and keep its `[rec::]` field. Test in Task 2.
3. An evidence URL carrying `?token=…`: the line is added without evidence, never refused. Test in Task 2.
4. A line whose link resolves to `wiki/Index.md` or to a file in `shared`: not a wall. Test in Task 2.
5. `now.py check` on a page with an owner-reopened walled or long line: the tick succeeds and the line is untouched. Test in Task 2.

---

### Task 1: Shared parts: `index.walled` and `alerts.alert`

**Files:**
- Modify: `system/scripts/vaultlib/index.py` (after `wall_blocked`, :96)
- Modify: `system/scripts/vaultlib/publish.py:306-320` (`_walls`)
- Modify: `system/scripts/vaultlib/alerts.py`, `system/scripts/vaultlib/intake.py:97-100`, `system/scripts/vaultlib/api.py`
- Modify: `extensions/intraday/scripts/watchlib/common.py:44-54`
- Test: `system/tests/python/test_alerts.py`, `system/tests/python/test_publish.py` (existing wall tests stay green)

**Interfaces:**
- Produces: `index.walled(resolver, src_rel: str, links) -> list[str]`: the resolved paths of `links` (from `linkmod.extract`) that `src_rel`'s partition may not link to; `[]` when `src_rel` is `wiki/Index.md` (`publish.INDEX_NOTE`'s value) or has no partition.
- Produces: `alerts.alert(vault, day: str, clock: str, tag: str, text: str, key: str = "") -> bool`, the body of `watchlib/common.alert` moved unchanged; `api` exports it as `alert`; `common.py` re-exports it (`from vaultlib.api import alert  # noqa: F401`), so `route.py`, `watch.py` and `today_log.py` keep their imports.
- `Intake.alert(message)` keeps its signature and writes through `alerts.alert(self.vault, self.today(), self.dt().strftime("%H:%M:%S"), "intake", message)`.

- [ ] **Step 1: Failing test** in `test_alerts.py`:

```python
def test_alert_writes_once_a_day_per_key(vault):
    assert alerts.alert(vault, "2026-10-23", "09:00:00", "triage", "k1 first", key="k1")
    assert not alerts.alert(vault, "2026-10-23", "09:05:00", "triage", "k1 again", key="k1")
    assert alerts.alert(vault, "2026-10-23", "09:06:00", "triage", "no key")
    text = (vault / "system/logs/alerts_2026-10-23.md").read_text(encoding="utf-8")
    assert text == "- 09:00:00 [triage] k1 first\n- 09:06:00 [triage] no key\n"
```

- [ ] **Step 2:** Run `system/scripts/test.sh system/tests/python/test_alerts.py`: FAIL (no `alert`).
- [ ] **Step 3:** Move the function, add `walled`, make `_walls` call `index.walled(resolver, target, body_links + fm_links)` and turn each hit into `Problem(target, f"partition wall: {src_part} note links to {hit}")` (message unchanged). `walled` keeps `_walls`' resolve call: `resolver.resolve(link.target, src_rel, "md" if link.kind == "md" else "wiki", lambda c: (len(c), c))`.
- [ ] **Step 4:** Run `test_alerts.py`, `test_publish.py`, `test_extension_api.py`, `extensions/intraday/tests/python/`: PASS.
- [ ] **Step 5:** Commit `refactor(f5): one wall loop and one once-a-day alert helper (#310)`.

### Task 2: The check in `vaultlib/now.py` and its interactive callers

**Files:**
- Modify: `system/scripts/vaultlib/now.py` (`write`, `note`, `add`, `set_statement`, `seed`; `_fits` goes)
- Modify: `system/scripts/vaultlib/redact.py:24,27-28` (`ASSIGNMENT`, `CONNECTION` guard `(?!\[?REDACTED)`)
- Modify: `system/scripts/now.py` (help text: line 13 says what add and set refuse and redact)
- Test: `system/tests/python/test_now.py`

**Interfaces:**
- Consumes: `index.walled` (Task 1), `redact.redact_credentials`, `links.extract`, `links.Resolver`, `index.Index(vault).walk()`, `index.name_excluded`.
- Produces:
  - `screen_fields(statement: str, who: str = "", evidence: str = "", rec: str = "") -> tuple` returning `(statement, who, evidence, rec)`: `redact_credentials` on statement, who and rec each; in rec, `[REDACTED:` becomes `REDACTED:` and its `]` goes; evidence is `""` when `redact_credentials(evidence) != evidence`.
  - `screen_line(vault, partition: str, line: str, old: str = "", fit: bool = False) -> str`: cap, then walls. Over `MAX_LINE` and longer than `old.rstrip()`: with `fit`, an open line (`- [ ] `, parsed by `LINE`) is re-rendered with `_cut` on its bare statement (the `fit_staged` rule from #366), a note line (`  - `) becomes `line[:MAX_LINE - 1].rstrip() + "…"`; still over, or without `fit`: `ValueError` with `_fits`' message ("the line is N characters; the limit is 300: …"). Walls: only when `links.extract(line, 0)[0]` is non-empty, build a `Resolver` over the vault's files and call `index.walled(resolver, f"wiki/{partition}/Now.md", links)`; a hit raises `ValueError(f"partition wall: the {partition} Now page may not link to {hit}")`.
  - `screen(vault, partition: str, line: str) -> str`: the fixed form of a whole open line (Task 4 uses it). A line `LINE` parses and that re-renders to itself is rebuilt from `screen_fields` on its parts and passed to `screen_line(..., fit=True)`. Any other line is returned unchanged, or `ValueError` when it is over the cap ("over 300 characters and not in now.py's form: …") or `redact_credentials(line) != line` ("credential-shaped text in a Now line not in now.py's form").
  - `note(vault, partition, match, text, today, fit: bool = False) -> str`: `text` through `redact_credentials` before the `FIELD_KEY` test; the note line through `screen_line(..., fit=fit)`.
  - `write(vault, partition, text)`: `ValueError("symlink on the Now page path")` before any write when `publish._resolves(vault, f"wiki/{partition}/Now.md")` is false.

`add`: `screen_fields` first (before `validate`), the rest as today with each `_fits(x, old)` replaced by `screen_line(vault, partition, x, old, fit)`. `set_statement`: `statement = screen_fields(statement.strip())[0]` first, `_fits` replaced by `screen_line(..., fit=False)`. `seed`: each statement through `screen_fields` and its rendered line through `screen_line(..., fit=True)`; an item that raises is skipped.

- [ ] **Step 1: Failing tests** in `test_now.py` (existing `vault`, `prepare`, `write`, `page`, `TODAY`; add `import pytest` and `KEY = "ghp_" + "a" * 36`):

```python
def test_add_redacts_each_field_and_the_line_still_parses(vault):
    prepare(vault)
    status, line = now.add(vault, "work", "owed", f"Rotate {KEY} today", TODAY, "Pat",
                           "https://example.com/x?token=abc123", rec=f"rotate: password={KEY}")
    assert status == "added" and KEY not in page(vault)
    m = now.LINE.match(line)
    assert m and m.group("evidence") is None
    assert now.fields(m.group("statement"))[1] == "rotate: password=REDACTED:github_token"
    assert now.add(vault, "work", "owed", f"Rotate {KEY} today", TODAY, "Pat")[0] == "exists"

def test_set_and_note_redact_and_note_fits(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Rotate the key", TODAY)
    assert KEY not in now.set_statement(vault, "work", "rotate", f"Rotate {KEY}", TODAY)
    assert KEY not in now.note(vault, "work", "rotate", f"token: {KEY}", TODAY)
    with pytest.raises(ValueError, match="limit is 300"):
        now.note(vault, "work", "rotate", "n" * 300, TODAY)
    assert now.note(vault, "work", "rotate", "n" * 300, TODAY, fit=True).endswith("n…")
    assert len(now.note(vault, "work", "rotate", "n" * 300, TODAY, fit=True)) == now.MAX_LINE

def test_a_link_across_the_wall_is_refused_and_index_and_shared_are_not(vault):
    prepare(vault)
    write(vault, "wiki/personal/concepts/diary.md", "---\ntype: concept\n---\n")
    write(vault, "wiki/shared/concepts/glossary.md", "---\ntype: concept\n---\n")
    with pytest.raises(ValueError, match="partition wall"):
        now.add(vault, "work", "owed", "Read [[diary]]", TODAY)
    assert now.add(vault, "work", "owed", "See [[glossary]] and [[Index]]", TODAY)[0] == "added"

def test_a_symlinked_now_page_is_refused(vault, tmp_path):
    prepare(vault)
    (tmp_path / "elsewhere").mkdir()
    shutil.rmtree(vault / "wiki" / "work")   # the fixture holds wiki/work/
    (vault / "wiki" / "work").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="symlink"):
        now.add(vault, "work", "owed", "Anything", TODAY)
    assert not any((tmp_path / "elsewhere").iterdir())

def test_check_leaves_an_owner_reopened_long_or_walled_line_alone(vault, tmp_path):
    prepare(vault)
    write(vault, "wiki/personal/concepts/diary.md", "---\ntype: concept\n---\n")
    kept = [f"- [ ] owed: {'w' * 400} (since 2026-10-01)", "- [ ] owed: Read [[diary]] (since 2026-10-01)"]
    done = "- [ ] owed: Ship it (since 2026-10-01, https://github.com/acme/shop/pull/7)"
    write(vault, "wiki/work/Now.md", "---\ntype: concept\n---\n# Now\n\n## Needs you\n" + "\n".join(kept + [done]) + "\n")
    assert now.check(vault, TODAY, lambda m: None, gh_stub(tmp_path)) == 1
    assert all(line in page(vault).split("\n") for line in kept)
```

Plus `test_screen_rebuilds_a_canonical_line_and_checks_a_hand_shaped_one_whole`: a canonical line holding `KEY` in its statement, who (`token=…`) and rec comes back without it, still parses, and `screen(screen(line)) == screen(line)`; a 320-character canonical line comes back at 300; `- [ ] owed: two  spaces (since 2026-10-01)` comes back unchanged; the same hand-shaped line with `KEY` raises `ValueError`.

- [ ] **Step 2:** Run `system/scripts/test.sh system/tests/python/test_now.py`: the new tests FAIL; the existing ones pass.
- [ ] **Step 3:** Implement the Interfaces block. Imports: `from . import briefings, frontmatter, index, links as linkmod, nightshift_item` and `from .redact import redact_credentials`.
- [ ] **Step 4:** Run `test_now.py`: PASS, existing tests unchanged (`test_add_and_set_refuse_a_line_over_300_characters` keeps "limit is 300").
- [ ] **Step 5:** Commit `feat(now): redact, cap and wall every Now write (#310, #288)`.

### Task 3: Machine callers drop a refused line with one alert a day

**Files:**
- Modify: `system/scripts/vaultlib/triage.py:280-284` (`record`)
- Modify: `extensions/intraday/scripts/watchlib/route.py:108-112` (`now_line`), `:143` (`free:` note), `route`
- Modify: `extensions/telemetry/scripts/telemetrylib/rca.py:167-183` (`reopen`), `extensions/telemetry/scripts/rca.py:57-59`
- Test: `system/tests/python/test_triage.py`, `extensions/intraday/tests/python/test_watch_route.py`, `extensions/telemetry/tests/python/test_rca.py`

**Interfaces:**
- Consumes: `alerts.alert` / `api.alert` (Task 1), `now.screen_fields`, `now.screen_line`, `now.note(..., fit=)` (Task 2).
- Alert texts (each starts with its key, so the key test finds it):
  - triage: key `"a Now line was refused"`, text `f"a Now line was refused ({exc})"`, tag `triage`, clock `now_iso[11:19]`.
  - watch: `now_line` returns `("refused", str(exc))` on its final `ValueError`; `route` alerts `f"a Now line was refused ({reason})"` with key `"a Now line was refused"`, tag `intraday`. The `free:` note passes `fit=True`.
  - RCA: `reopen` builds `statement = now.screen_fields(f"{bare}: not filed {today}, {why}")[0]` and writes `now.screen_line(vault, partition, now.render(kind, statement, since, who, evidence, rec, due), fit=True)` (render replaces the hand-built `rest`). `rca.py reopen` catches `ValueError` and calls `alert(VAULT, intake.today(), intake.dt().strftime("%H:%M:%S"), "rca", f"a Now line was refused ({exc})", key="a Now line was refused")`, exit 0.

- [ ] **Step 1: Failing tests:**
  - `test_triage.py::test_a_refused_line_is_dropped_with_one_alert_a_day_and_the_tick_goes_on`: two items whose ask links `[[diary]]` (a personal note) into the work page; `record` returns `[]`, logs both items and the tick, and the day's alerts file holds exactly one `[triage] a Now line was refused` line.
  - `test_watch_route.py::test_a_refused_now_line_alerts_once_and_the_tick_goes_on`: the same through `route`; counts `now == 0`, one `[intraday] a Now line was refused` line.
  - `test_rca.py::test_reopen_cuts_a_long_jira_reason_and_redacts_it`: an RCA line with a 200-character statement and a reason holding `KEY` plus 150 more characters; after `reopen` the line is open, at most 300 characters, holds no `KEY`, and ends with the line's `(…, since …, rca:<stem>)` parenthesis.
- [ ] **Step 2:** Run the three files: the new tests FAIL.
- [ ] **Step 3:** Implement the Interfaces block.
- [ ] **Step 4:** Run the three files (`system/scripts/test.sh <path>` each): PASS.
- [ ] **Step 5:** Commit `feat(f5): triage, the watch and the RCA filer drop a refused Now line with one alert a day (#310)`.

### Task 4: The gate verifies, `fit_staged` fixes

**Files:**
- Modify: `system/scripts/vaultlib/publish.py:380-385` (`_check`'s Now block)
- Modify: `system/scripts/vaultlib/now.py` (`fit_staged`), `system/scripts/now.py` (help line for `fit-staged`)
- Test: `system/tests/python/test_publish.py`, `system/tests/python/test_now.py`, `system/tests/headless.bats` (existing "a brief-added Now line over 300 characters is cut" test stays green)

**Interfaces:**
- Consumes: `now.screen` (Task 2).
- `_check`: for each added open line (`rstrip()` not in the live page, as today), with `partition = schemamod.path_partition(target)`: `ValueError` from `nowmod.screen` is `Problem(target, f"a Now line: {exc}")`; a result that differs from the line is `Problem(target, "a Now line the check would redact or cut: run now.py fit-staged before publish")`.
- `fit_staged(vault, run_id) -> int`: each added open line becomes `screen(...)`; a `ValueError` leaves the line for the gate. Returns the lines changed. The page is written only when one changed.

- [ ] **Step 1: Failing tests:**
  - `test_publish.py::test_the_gate_checks_added_now_lines_with_the_now_check`: a staged brief Now page with four added lines: one holding `KEY` (Problem), one canonical at 320 characters (Problem), one hand-shaped clean line `- [ ] owed: two  spaces (since 2026-10-01)` (no Problem), and the live page's old 400-character line (no Problem). Adapt `test_the_gate_refuses_a_new_now_line_over_300_characters` to the new message.
  - `test_now.py::test_fit_staged_redacts_and_cuts_added_lines`: a staged added canonical line holding `KEY` and over 300 characters comes back redacted and at most 300; `fit_staged` returns 1; the live page's old line is untouched.
- [ ] **Step 2:** Run both files: the new tests FAIL.
- [ ] **Step 3:** Implement the Interfaces block.
- [ ] **Step 4:** Run `test_publish.py`, `test_publish_commit.py`, `test_now.py`, and `system/scripts/test.sh system/tests/headless.bats` (sandbox disabled): PASS.
- [ ] **Step 5:** Commit `feat(gate): the gate checks a run's added Now lines with the Now check (#310)`.

### Task 5: CHANGELOG, budget, PR

- [ ] **Step 1:** CHANGELOG line under the current Unreleased heading: every Now line write (now.py, triage, the watch, the RCA filer, a brief) is redacted, kept to 300 characters and checked against the partition walls; a machine writer drops a refused line with one alert a day; a symlinked Now page is refused.
- [ ] **Step 2:** Run `system/scripts/test.sh system/tests/vault_integrity.bats` and `system/tests/conformance.bats` (sandbox disabled): PASS, core under 15,000 (print the count for the PR body).
- [ ] **Step 3:** Run `.claude/skills/foundry-review/review_diff.py`; fix or explain each hit.
- [ ] **Step 4:** Push `feat/f5-gate-every-write`, open the PR (body: what changed, the plan decisions above, "Part of #310", the core count, ends with the session link), watch CI, post the ready comment naming the head SHA.

---

## PR 2 (spec §4.4-§4.6, added 2026-10-24)

Small enough to run from this section (FOUNDRY.md Development: small features skip a separate plan). Auto-merge on green CI: it touches no safety surface (no publish gate, redaction, settings, hooks or notify code).

- **Today file** (`extensions/intraday/scripts/today_log.py:write`): the item's `link` goes through `clean`; the file path passes `resolves` (`publish._resolves`, exported by `vaultlib/api.py`), else one `[intraday] today file refused: a symlink on its path` alert a day and nothing written. Test: `test_today_log.py::test_a_credential_in_a_link_is_masked_and_a_symlinked_today_file_is_refused`.
- **Lint steps:** `brief.md` and `debrief.md` Self-edit, and the RCA skill's step 7: "finish with `system/scripts/lint_vault.sh` and fix each error in the files you wrote". The brief prompt stays under its 2,500-word cap by dropping one restatement, the `unavailable.md` aside (2,499 words). Test: `commands.bats` key check; `prep.bats` word cap.
- **One wall rule:** `index.py`'s lint exempts only `wiki/Index.md`. Test: `test_index_rules.py::test_only_the_cross_partition_index_is_exempt_from_walls`.
- **`[watch]` exception:** a comment at the watch's alert line and a line in foundry-review's `alert-text` row.
- Live acceptance for the edited headless brief text: the next scheduled brief after merge, read from its run ledger.
