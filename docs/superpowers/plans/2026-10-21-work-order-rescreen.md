# Work Order Re-screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (native, owner's default for Foundry plans). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The runner screens every capability-bearing field of a Work Order note at the tick that uses it, and the research session reads only background notes.

**Architecture:** `nc.check` splits into a field half, `nc.screen`, that reads only the note and `system/codebases/` (no git, no network), and the existing environment half. `_screen` runs `nc.screen` on every live note each pass. `_research_dir` rebuilds `context/` from three folders, skipping links; delivery reads its target from `delivery.json` and refuses a linked research output.

**Tech Stack:** Python 3 stdlib (`re`, `shutil`, `pathlib`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-21-work-order-rescreen-design.md`

## Global Constraints

- `nightshift_run.py` exit codes: 0 ok, 1 an item failed, 2 usage or invalid item, 4 locked.
- A refused note: `state: failed`, `reason: invalid: <errors>`, one alert keyed `invalid/<note name>`, text `<note name> refused: <errors>`, tag `[orders]`. Pre-loop refusal returns 2; in-loop refusal leaves running workers alone.
- One function, two callers: no second copy of the add-time rules in the runner. No git or network in `nc.screen`.
- Output rule: `wiki/<p>/(concepts|entities|summaries)/<name>.md`, `<p>` the note's `partition`. Context allowlist: the same three folders.
- `blocked`, `failed`, `done` and `cancelled` notes get `identifiers()` only.
- Hosts: `HOST` as today, and the last label must contain a letter (refuses IP literals only).
- Repo wall: a `repo` other than `template` must name a codebase whose `partition` is the order's or `shared`.
- Core budget: `system/scripts` at or under 13,950 lines (`vault_integrity.bats`); a raise goes to the owner with the measurement.
- Sibling PR (#314) edits `profile()`, `_run_session` and `_deliver_research`'s failure reason: keep edits there small and local; do not touch `profile()`.
- Template stays generic: no names, hosts or user paths.

## Review Focus

1. A note a worker is running is edited mid-session: `_screen` must not mark it (race with `_finish`); its next attempt is screened. Test: Task 2 runs a tick where a held id fails the screen and stays unmarked.
2. A `blocked` order whose output predates the rule survives the first tick after the update unchanged. Test: Task 2.
3. `repo: ../x` must never reach a codebase file read: `identifiers()` runs first and returns. Covered by the existing `test_identifiers_are_refused_before_any_git_call`.
4. `out/` itself replaced by a symlink (spec names only `out/<name>`): refused like a linked file. Test: Task 3.
5. A `delivery.json` written before the fix has no `repo` key: delivery falls back to `fm["repo"]`. Test: Task 4 (existing delivery-retry test keeps passing; the new test covers the recorded case).

---

### Task 1: `nc.screen`, the field half

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py` (`identifiers`, `check`, `_plan`, `_research`)
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`main`'s `check` command passes the note path)
- Modify: `system/schemas/codebase.md` (add `nightshift_check.py` to `partition` readers)
- Test: `system/tests/python/test_nightshift_check.py`

**Interfaces:**
- Produces: `nc.screen(vault, fm: dict, body: str, path=None) -> list[str]`; `nc.check(vault, fm, body, path=None) -> list[str]`. `path` is the queue note's path; when given, `Path(path).parent.parent.name` must equal `fm["partition"]`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("output", ["docs/injected.md", "extensions/telemetry/skills/evil/SKILL.md",
                                    "wiki/personal/concepts/X.md", "wiki/work/private/X.md", "wiki/work/meetings/X.md",
                                    "wiki/work/Now.md", "wiki/work/preferences/X.md"])
def test_research_output_must_be_a_background_note_of_its_partition(vault_repo, output):
    fm = plan_fm(kind="research", output=output, hosts=[])
    assert any("output" in e for e in nc.check(vault_repo, fm, BRIEF))
    assert any("output" in e for e in nc.screen(vault_repo, fm, BRIEF))

@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "*"])
def test_ip_literal_hosts_are_refused(vault_repo, host): ...   # "host" in an error from check and screen

def test_the_partition_must_match_the_note_folder(vault_repo):
    # partition personal, output wiki/personal/concepts/X.md, path raw/work/nightshift/<id>.md: a "partition" error;
    # the same fm with path raw/personal/nightshift/<id>.md: no error

def test_repo_must_be_a_codebase_in_the_order_partition_or_shared(vault_repo, tmp_path):
    # registered(...) work codebase "shop"; a personal research order naming repo shop -> error naming shop;
    # set_codebase(partition="shared") -> no such error; a work order -> no such error

def test_screen_reads_no_git(vault_repo, monkeypatch):
    # monkeypatch subprocess.run to raise; screen() on a plan_fm and a research fm returns [] / field errors only
```

- [ ] **Step 2: Run** `python3 -m pytest system/tests/python/test_nightshift_check.py -q` — Expected: the new tests FAIL (`screen` missing, outputs and hosts accepted).

- [ ] **Step 3: Implement.** `screen` = `identifiers()` (return on error) + partition/folder + repo wall + budget + `start_at` + kind rules (plan: `verify`; research: sections, `OUTPUT` regex, hosts with a letter in the last label; other kind: the kind error). `check` = `screen`, return on errors, then the workspace rule, `_plan` (without its `verify` line) or `_research_repo`. `main`'s `check` passes `a.note`.

- [ ] **Step 4: Run** the check suite — Expected: PASS, existing tests unchanged.

- [ ] **Step 5: Commit** `feat(orders): one field screen for add and the tick (#298)`.

### Task 2: the tick screens every live note

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_screen`, `tick`)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `nc.screen(vault, fm, body, path)` from Task 1.
- Produces: `_screen(ctx, held=()) -> (entries, refused)`; `held` is the ids a worker holds (`pool.threads`), returned unscreened and never marked.

- [ ] **Step 1: Write the failing tests** (house style: research `add` through `nr.main`, `ni.update`, tick):
  - `test_a_hosts_edit_after_add_is_refused_at_the_tick[*, 169.254.169.254]`: tick returns 2; `state == "failed"`; `reason.startswith("invalid: host")`; no `items/<id>/settings.json`; alert text `<name>.md refused:`.
  - `test_an_output_edit_after_add_is_refused_and_never_written`: output `docs/injected.md`; tick 2; `failed`; `vault/docs/injected.md` absent.
  - `test_outputs_outside_the_three_folders_are_refused_at_the_tick[extensions/…/SKILL.md, wiki/personal/concepts/X.md, wiki/work/private/X.md, wiki/work/meetings/X.md, partition personal]`.
  - `test_a_blocked_note_keeps_identifiers_only`: blocked note with `output: docs/x.md`; tick returns 0; state still `blocked`.
  - `test_the_loop_screen_leaves_a_note_a_worker_holds`: `_screen(ctx, held={id})` on a note that fails `screen` returns it in entries and leaves its state.

- [ ] **Step 2: Run** them — Expected: FAIL (tick returns 0 and runs the session).

- [ ] **Step 3: Implement.** In `_screen`: terminal states gain `blocked` for the choice of `identifiers` vs `screen`; marking stays for states other than `failed`, `done`, `cancelled`; ids in `held` are appended unscreened. `tick`'s in-loop call passes `pool.threads`.

- [ ] **Step 4: Run** `test_nightshift_run.py` and `test_nightshift_parallel.py` — Expected: PASS.

- [ ] **Step 5: Commit** `feat(orders): the tick screens every live note in full (#298)`.

### Task 3: the research read set and its output

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_research_dir`, `_deliver_research`)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `_research_dir(ctx, fm) -> Path` rebuilds `context/` every call from `wiki/<p>/{concepts,entities,summaries}/`, skipping dotfiles and symlinks; a `context` symlink is unlinked. `_deliver_research` returns `{"state": "failed", "reason": "invalid: output is a link"}` and alerts `invalid/<id>` when `out/` or `out/<name>` is a symlink.

- [ ] **Step 1: Write the failing tests** (direct `nr._research_dir` calls, as in `test_research_reads_a_pinned_copy_of_its_codebase`; the stub ignores `SHELL`'s exit code):
  - `test_research_context_holds_background_notes_only`: partition holds `private/Secret.md`, `Now.md`, `meetings/M.md`, `concepts/Background.md` and `concepts/Link.md` (a symlink to a file outside the vault); `context/` has `concepts/Background.md` and none of the others.
  - `test_a_resumed_order_loses_a_context_built_before_the_fix`: pre-made `context/private/Secret.md` is gone after `_research_dir`.
  - `test_a_context_replaced_by_a_link_is_unlinked`: `context` → a directory outside; after `_research_dir` the target still holds its file and `context` is a real directory.
  - `test_a_linked_research_output_is_refused[file, out dir]`: `out/Answer.md` (or `out/`) a symlink to a vault note; `_deliver_research` returns `failed` / `invalid: output is a link`; nothing published; one alert.

- [ ] **Step 2: Run** them — Expected: FAIL.

- [ ] **Step 3: Implement** as in Interfaces; the guard sits right before the existing `is_file()` line.

- [ ] **Step 4: Run** `test_nightshift_run.py` — Expected: PASS.

- [ ] **Step 5: Commit** `fix(orders): research reads background notes only and never a linked output (#298)`.

### Task 4: delivery pushes to the recorded repo

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_deliver_plan`'s `delivery.json`, `_deliver`)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `delivery.json` gains `repo` and `pr_base`; `_deliver` overlays them on `fm` when present.

- [ ] **Step 1: Write the failing test** `test_delivery_after_a_repo_edit_pushes_to_the_recorded_repo`: `delivery.json` with `repo: template` and a real sha on `runner.git`; note edited to `repo: shop` (a registered codebase); `_deliver` pushes to the template remote (the branch appears there, not in shop's origin).

- [ ] **Step 2: Run** — Expected: FAIL (push goes to shop's origin).

- [ ] **Step 3: Implement** one overlay line in `_deliver`; two keys in `_deliver_plan`'s dump.

- [ ] **Step 4: Run** the nightshift Python suites — Expected: PASS.

- [ ] **Step 5: Commit** `fix(orders): delivery retries push to the repo recorded at verify (#298)`.

### Task 5: docs, budget, verification

**Files:**
- Modify: `.claude/skills/order/SKILL.md:23`, `FOUNDRY.md:88`, `CHANGELOG.md` (`## 2026-10-21`)
- Test: `system/tests/commands.bats` (order skill names the three folders)

- [ ] **Step 1:** Add a docs test that `.claude/skills/order/SKILL.md` names `wiki/<partition>/concepts/`; run it, expect FAIL.
- [ ] **Step 2:** Update the skill line and FOUNDRY.md (output rule, context allowlist, re-screen at each tick); CHANGELOG line with the action: queue a refused order again with a `wiki/<p>/concepts|entities|summaries/` output.
- [ ] **Step 3: Verify:** all `test_nightshift_*.py`, `bats system/tests/nightshift.bats`, the commands.bats order tests, `vault_integrity.bats` (core budget), `conformance.bats` (output shows `ok`, not `skip`).
- [ ] **Step 4:** Name grep on the diff; commit; push; open the PR ("Part of #298", owner merges, Out-of-scope items listed).
