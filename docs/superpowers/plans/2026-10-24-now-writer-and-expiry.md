# Now Writer and Expiry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Now line names its writer in `[via:: …]`. A mail, chat or watch line the owner leaves untouched closes itself as expired after 7 days. Health counts dismissals per writer. A one-time verb tags the lines already open.

**Architecture:** `vaultlib/now.py` gains `VIA`, `via()`, an `EXPIRE_DAYS` rule in `check()`, and `tag_writers()`. Each path that re-renders a line passes `via` through `render()`. Writers pass their name: triage `mail`/`chat`, the watch `watch`, `fit_staged` `brief`, and sessions `session` by default. Health keys its dismissed share by `via`.

**Tech Stack:** Python 3 stdlib plus `vaultlib`, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-24-now-writer-and-expiry-design.md`

## Global Constraints

- The five writers are exactly `mail`, `chat`, `watch`, `brief` and `session`. The machine writers are `mail`, `chat` and `watch`.
- `EXPIRE_DAYS = 7`. An expired line becomes `- [-]<rest> _(closed: expired <today>)_`.
- `now.py list --json` only gains the `"via"` key; `v` stays `1`. Plain `now.py list` prints lines without `[via:: …]`.
- The brief prompt (`brief.md`) does not change; it is at its 2,500-word cap.
- No safety surface: `publish.py`, `redact.py`, settings and hooks are untouched. The PR auto-merges on green CI.
- Core budget: 15,100 lines (`vault_integrity.bats`). Measure the count before the PR.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. Run only the changed files' tests locally; CI runs the full suite.
- Commits end with `Claude-Session: https://claude.ai/code/session_01EZnnKRuLxKtqiULqPqSgoJ`.

## Review Focus

1. **A machine line under the 300-character cap.** Each cut must keep `[via::]`, or the line silently stops expiring. Test in Task 1 (`fit` cut).
2. **A hand-edited `[VIA:: Mail]` (any case, spaces).** It must read like `[rec::]` does, case-insensitive. Test in Task 1.
3. **A page where only an expiry happens and `gh` is down.** The page must still be written. Test in Task 3.
4. **A brief-staged line that already has `[via:: session]`** (copied from now.md by the model). It is kept, never overwritten with `brief`. Test in Task 2.
5. **`tag-writers` on a hand-shaped line.** It is left untouched and counted as skipped. Test in Task 4.

---

### Task 1: The field

**Files:** Modify `system/scripts/vaultlib/now.py`, `system/scripts/now.py` (plain `list`), `extensions/telemetry/scripts/telemetrylib/rca.py` (`reopen`). Test `system/tests/python/test_now.py`, `extensions/telemetry/tests/python/test_rca.py`.

**Interfaces (Produces):**
- `WRITERS = ("mail", "chat", "watch", "brief", "session")` and `MACHINE = ("mail", "chat", "watch")`.
- `VIA = re.compile(r"\s*\[via::\s*([a-z]+)\s*\]", re.IGNORECASE)`. `FIELD_KEY` matches `rec|due|via`.
- `via(statement: str) -> str` returns the lower-cased value when it is in `WRITERS`, else `""`.
- `fields()` also strips `VIA` from the bare statement and still returns its three-tuple.
- `render(..., due="", via="")` writes ` [via:: <via>]` after due.
- `add(..., fit=False, via="session")`. A repeat keeps the existing line's `via` (falling back to the caller's when the old line has none).
- `set_statement` renders with `via="session"`.
- `screen_line`'s fit cut, `screen()`'s canonical test and rebuild, and RCA `reopen` pass `via(m.group("statement"))`.
- `strip_via(line: str) -> str` returns `VIA.sub("", line)`. Plain `now.py list` prints `now.strip_via(line)`.
- `list_data` lines gain `"via": via(m.group("statement"))`.

- [ ] **Step 1: Failing tests** in `test_now.py`:
  - `test_add_writes_session_and_a_repeat_keeps_the_writer`: `add(...)` gives a line ending `[via:: session] (since …)`. `add(..., via="mail")` of the same statement returns `exists` and the line stays `session`.
  - `test_set_hands_the_line_to_the_session`: a `[via:: mail]` line after `set_statement` has `via() == "session"`.
  - `test_the_writer_survives_every_re_render`: a 320-character `add(..., fit=True, via="watch")` keeps `[via:: watch]` and is at most 300 characters. `screen()` of a canonical `[via:: chat]` line returns it unchanged. `fields()` of `"x [via:: mail]"` is `("x", "", "")`. `via("x [VIA::  Mail ]") == "mail"`. `via("x [via:: robot]") == ""`. `add` with a statement holding `[via:: mail]` raises `ValueError`.
  - `test_list_json_has_via_and_plain_list_leaves_it_out`: `list_data` has `"via": "session"`. The CLI `now.py list` output holds no `[via::`. Use the file's existing CLI pattern.
  - In `test_rca.py`, extend `test_reopen_unticks_the_line_with_the_reason_and_returns_the_draft` so the reopened line keeps `[via:: session]`.
- [ ] **Step 2:** Run both files. The new tests fail.
- [ ] **Step 3:** Implement the Interfaces block.
- [ ] **Step 4:** Run both files, plus `test_publish.py` and `test_triage.py` (rendered lines change there): PASS. Update any existing assertion that compares a full rendered line, adding ` [via:: session]` where `add` wrote it. Note each such edit in the ledger.
- [ ] **Step 5:** Commit `feat(now): each line names its writer in [via::] (#333)`.

### Task 2: The writers

**Files:** Modify `system/scripts/vaultlib/triage.py` (`record`: both `add` calls pass `via="chat" if source == "chat" else "mail"`), `extensions/intraday/scripts/watchlib/route.py` (`now_line`: both `add` calls pass `via="watch"`), and `system/scripts/vaultlib/now.py` (`fit_staged`). Test `test_triage.py`, `extensions/intraday/tests/python/test_watch_route.py`, `test_now.py`, `test_publish.py`.

**Interfaces:**
- `fit_staged`: for an added line that `LINE` parses and that has no `via()`, insert ` [via:: brief]` before the parenthesis by re-rendering a canonical line. Then `screen()` it. A line with any `via` is kept as it is. A hand-shaped line is left for the gate, as today.

- [ ] **Step 1: Failing tests:**
  - `test_record_adds_one_owed_line_per_new_message_and_records_the_tick` expects `[via:: mail]` in its line. A chat `record` (`source="chat"`) gives `[via:: chat]`.
  - In `test_watch_route.py`, a deadline item's line holds `[via:: watch]`.
  - `test_fit_staged_tags_brief_lines_and_keeps_a_writer_already_there`: an added line with no via becomes `[via:: brief]`. An added line with `[via:: session]` stays `session`.
  - In `test_publish.py`, `brief_run` with a `[via:: brief]` canonical line gives no Problem.
- [ ] **Steps 2-4:** RED, implement, GREEN on the four files and `system/tests/headless.bats`.
- [ ] **Step 5:** Commit `feat(now): triage, the watch and the brief name themselves (#333)`.

### Task 3: Machine lines expire

**Files:** Modify `system/scripts/vaultlib/now.py` (`check`). Test `test_now.py`.

**Interfaces (Produces):**
- `EXPIRE_DAYS = 7`.
- `expires(lines: list, i: int, today: str) -> bool` decides one line of a page's lines. It is true when all of these hold:
  - `parse(lines[i])` gives `via()` in `MACHINE`;
  - `(today - since).days >= EXPIRE_DAYS`;
  - the line has no due, or its due is before `today`;
  - every line in `lines[i+1:_block_end(lines, i)]` matches `^\s+- \d{4}-\d{2}-\d{2}: free: `.
- `check()` reads every page fresh, closes evidence lines as today, then marks each line that `expires()` as `- [-]{key[5:]} _(closed: expired {today})_`. It writes a page when either changed. It returns the evidence closures plus the expired count.

- [ ] **Step 1: Failing test** `test_check_expires_untouched_machine_lines_only`: on `TODAY = "2026-10-09"`, a page holds the lines below. One `check` with a `gh` stub that exits 1 (Review Focus 3) closes exactly the first two lines as expired and leaves the rest open.
  - expires: `mail` since `2026-10-02`, no note
  - expires: `watch` since `2026-10-01` with only a `free: …` note
  - stays: `mail` since `2026-10-03` (six days)
  - stays: `chat` since `2026-10-01` with `[due:: 2026-10-09]`
  - stays: `mail` since `2026-10-01` with a note `  - 2026-10-05: called them`
  - stays: `session` since `2026-09-01`
  - stays: a line since `2026-09-01` with no `via`
- [ ] **Steps 2-4:** RED, implement, GREEN on `test_now.py`.
- [ ] **Step 5:** Commit `feat(now): an untouched machine line expires after 7 days (#333)`.

### Task 4: `tag-writers`

**Files:** Modify `system/scripts/vaultlib/now.py` and `system/scripts/now.py` (a verb under `run.lock`). Test `test_now.py`.

**Interfaces (Produces):**
- `tag_writers(vault, today: str, dry_run: bool) -> dict` returns `{partition: {"tagged": n, "expiring": n, "skipped": n}}`.
  - Each open line with no `via` whose evidence holds `mail.google.com` gets `mail`, and one holding `slack.com` gets `chat`.
  - A parsed line that does not re-render to itself (hand-shaped) is `skipped` and left as it is.
  - `expiring` counts tagged lines that `expires()` would close on `today`.
  - `dry_run` writes nothing.
- CLI: `now.py tag-writers [--dry-run]` prints `tag-writers <partition>: <tagged> tagged, <expiring> expire at the next check, <skipped> skipped` per partition. Exit 0.

- [ ] **Step 1: Failing test** `test_tag_writers_dry_run_then_once`:
  - A page holds an old Gmail line, a Slack line, a GitHub-evidence line, a no-evidence line and a hand-shaped Gmail line (text after the parenthesis).
  - The dry run returns `{"work": {"tagged": 2, "expiring": 2, "skipped": 1}, "personal": {…zeros}}` and leaves the page bytes unchanged.
  - The real run tags the two lines.
  - A second run returns `tagged == 0`.
- [ ] **Steps 2-4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(now): now.py tag-writers tags the lines already open (#333)`.

### Task 5: Health reads the writer

**Files:** Modify `extensions/health/scripts/health.py` (`dismissed`). Test `extensions/health/tests/python/test_platform.py`.

**Interfaces:**
- The key is `nowmod.via(m["statement"]) or "guess:" + _host(m["evidence"] or "")`. `DISMISS_MIN` and the thresholds are unchanged.

- [ ] **Step 1:** Change `test_dismissed_share_per_evidence_host_with_five_closed` to expect `{"guess:mail": 60}` and text `guess:mail 60%`. Add `test_dismissed_share_is_keyed_by_writer`: five closed `[via:: watch]` lines, three of them `[-]`, give `{"watch": 60}`.
- [ ] **Steps 2-4:** RED, implement, GREEN.
- [ ] **Step 5:** Commit `feat(health): the dismissed share per writer (#333)`.

### Task 6: Docs, budget, PR

- [ ] **Step 1: FOUNDRY.md.** The Now paragraph states the `[via:: …]` field and the five writers, the expiry rule, how to keep a line (a note, or delete the field), and `now.py tag-writers --dry-run` for a vault that has untagged lines. The health paragraph says the dismissed share is per writer.
- [ ] **Step 2: `now.py` help and CHANGELOG.** The help text gains the `tag-writers` line, and `add` mentions `[via:: session]`. The CHANGELOG line comes with an `Action:` line telling a vault to run `system/scripts/now.py tag-writers --dry-run`, then without `--dry-run`, so the brief's What changed shows it first.
- [ ] **Step 3: Key check.** `commands.bats`: FOUNDRY.md holds `[via::` and `now.py tag-writers`.
- [ ] **Step 4: The spec.** Put §3.3 back before §3.4.
- [ ] **Step 5: Suites and checks.** Run `vault_integrity.bats`, `commands.bats`, `conformance.bats` and `review_diff.py`. Push, open the PR (`Part of #333`), set auto-merge, watch CI.
