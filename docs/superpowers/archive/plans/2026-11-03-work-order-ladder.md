# Work Order ladder (Foreman dispatch D1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plan Work Order whose verify fails, whose new tests prove nothing, or whose session leaves no commits or no result goes back to a fresh session with a handoff (rung 1 on the item's model, rung 2 on Opus) inside a fence, before it reaches the owner; and a plan order states a red command at queue time.

**Architecture:** `run_item` checks each plan delivery outcome with `_climbs()`. A climbing outcome writes `.nightshift/handoff.md` in the kept clone and puts the note back to `queued` with `rung: <n>`; the next tick starts a fresh session there with `ss.fix_prompt()`, the rung's model and half the budget. `_deliver_plan` checks a rung's history and fence against `items/<id>/ladder.json`, and runs `nd.red_sha()` after a green verify. `nc.fence()` reads the plan's **Files** blocks. `add` takes `--red` and `--escalate`.

**Tech Stack:** Python 3 stdlib, git, bwrap (the existing sealed verify), pytest, bats.

**Spec:** `docs/superpowers/archive/specs/2026-11-03-work-order-ladder-design.md`

## Global Constraints

- The spec's §9 rows R1 to R5 are decided as recommended (owner, 2026-11-03): fresh session, own model then Opus, no early exit, half the budget per rung, and `verify`, `red`, `no commits`, `no result` climb.
- Exit codes, alert tags, the report's columns and the Now line's shape stay as they are. No new unit, config key, alert tag or note type.
- Tests stub `claude` (`system/tests/stub_claude_nightshift`); no test calls the real `claude` or the network. End-to-end cases that need `bwrap` skip without it, like the existing ones.
- Run single suites with `system/scripts/test.sh <path>`; run `system/scripts/verify_setup.sh` at the end of Task 8.
- Core cap: one raise for this spec, 16,480 → 16,640, with one comment line in `system/tests/vault_integrity.bats` (Task 8). Going past it is the owner's call.
- Anti-goals: no climb for `session`, `protected`, `toolchain`, `fence`, `containment`, `profile`, `budget`, `cancelled`, an `order_install` failure or an exit 127; no step down to a cheaper model; a rung never rewrites the earlier commits; the pull request still waits for the owner's merge.
- Never run `git` inside the session's clone from the runner except the reads `_clone` and `_deliver_plan` already make; history and fence checks run in the runner's repository (`nightshift-runner.git`).
- Task text names no branch of the template repository: the readiness check refuses a task that names one.
- Every task ends with its suite green and one commit; the last task's commit marks D1 done in the roadmap and the program plan.

## Review Focus

1. A rung on an item queued on `opus` stops after one rung, and rung 2 of a `sonnet` item runs with `--model opus` (Task 4, `test_ladder_models`).
2. A rung that amends or rebases an earlier commit blocks with `fence` and never pushes (Task 5, `test_a_rung_that_rewrites_history_blocks`).
3. The red check overlays only the plan's `Test:` paths on the base, and a red command that passes there climbs with reason `red` (Task 3, `test_red_passes_on_base_is_red`).
4. A note queued before the update, with no `red`, passes the tick's screen and runs (Task 2, `test_a_note_without_red_still_runs`).
5. An `order_install` failure and an exit 127 never climb (Task 4, `test_environment_failures_do_not_climb`).

---

### Task 1: Note fields, the fence reader and the screen

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_item.py`
- Modify: `system/scripts/vaultlib/nightshift_check.py`
- Modify: `system/schemas/nightshift_item.md`
- Modify: `docs/superpowers/roadmap.md`
- Modify: `docs/superpowers/2026-10-29-foreman-dispatch-plan.md`
- Test: `system/tests/python/test_nightshift_check.py`

**Interfaces:**
- Produces: `ni.ORDER` gains `"red", "escalate", "rung"` after `"verify"`.
- Produces: `nc.fence(plan_text: str, tasks) -> tuple[list[str], list[str]]`, `(fence, tests)`: the paths from the selected tasks' `**Files:**` blocks, in plan order, without duplicates; `tests` is the `Test:` subset. `tasks` is the item's `tasks` string or empty for every task.
- Produces: `nc.in_fence(path: str, fence) -> bool`: equal to an entry, or under an entry that ends `/`.
- Produces: `nc.screen()` errors `red must be a command or "none: <why>"`, `escalate must be on or off`, `rung must be 0, 1 or 2`.

- [ ] **Step 1: Mark D1 in progress.** In `docs/superpowers/roadmap.md`, the Foreman dispatch row's state cell ends `; D1 spec 2026-11-03-work-order-ladder-design.md, build in progress`. In the program plan's phase table, D1's spec-and-plan cell becomes `archive/specs/2026-11-03-work-order-ladder-design.md`, plan `archive/plans/2026-11-03-work-order-ladder.md`, and its state `building`.

- [ ] **Step 2: Write the failing tests** in `test_nightshift_check.py`:

```python
FILES_PLAN = """# P
### Task 1: Parser
**Files:**
- Modify: `system/scripts/a.py` (after `parse`)
- Create: `system/scripts/vaultlib/b.py`
- Test: `system/tests/python/test_a.py`

Body text naming `system/scripts/other.py` is not a fence path.
### Task 2: Docs
**Files:**
- Modify: `FOUNDRY.md:88-90`
- Create: `docs/notes/`
- Test: `system/tests/python/test_a.py`
### Task 3: None listed
Do the thing.
"""


def test_fence_reads_files_blocks_of_the_selected_tasks():
    fence, tests = nc.fence(FILES_PLAN, "1-2")
    assert fence == ["system/scripts/a.py", "system/scripts/vaultlib/b.py", "system/tests/python/test_a.py",
                     "FOUNDRY.md", "docs/notes/"]
    assert tests == ["system/tests/python/test_a.py"]
    assert nc.fence(FILES_PLAN, "2") == (["FOUNDRY.md", "docs/notes/", "system/tests/python/test_a.py"],
                                         ["system/tests/python/test_a.py"])
    assert nc.fence(FILES_PLAN, "3") == ([], [])


def test_in_fence_takes_folders_by_prefix():
    fence = ["FOUNDRY.md", "docs/notes/"]
    assert nc.in_fence("docs/notes/x/y.md", fence) and nc.in_fence("FOUNDRY.md", fence)
    assert not nc.in_fence("docs/notesx.md", fence) and not nc.in_fence("README.md", fence)


@pytest.mark.parametrize("fields,err", [
    ({"red": "none:"}, 'red must be a command or "none: <why>"'),
    ({"red": ["x"]}, 'red must be a command or "none: <why>"'),
    ({"escalate": "maybe"}, "escalate must be on or off"),
    ({"rung": "3"}, "rung must be 0, 1 or 2"),
])
def test_screen_checks_the_ladder_fields(vault, fields, err):
    fm = {"id": "2026-11-03-x", "partition": "work", "kind": "plan", "verify": ["true"], **fields}
    assert err in nc.screen(vault, fm, "")


def test_screen_takes_a_note_with_no_red(vault):
    fm = {"id": "2026-11-03-x", "partition": "work", "kind": "plan", "verify": ["true"]}
    assert nc.screen(vault, fm, "") == []
```

`vault` is the conftest fixture the other suites use.

- [ ] **Step 3: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_check.py` (fails: `nc.fence` missing).

- [ ] **Step 4: Implement.**
  - `nightshift_item.ORDER`: insert `"red", "escalate", "rung"` after `"verify"`.
  - `nightshift_check.py`:

```python
FILES_HEAD = re.compile(r"^\*\*Files:\*\*\s*$", re.M)
FILES_LINE = re.compile(r"^- (Create|Modify|Test): `([^`]+)`", re.M)


def fence(plan_text: str, tasks) -> tuple:
    """(fence, tests): the paths on the Create, Modify and Test lines of the selected tasks' Files blocks (spec §6).
    A path is cut at the first ':' after it (a line cite) and keeps a trailing '/' (a folder)."""
    blocks = task_blocks(plan_text)
    wanted = parse_tasks(tasks) or set(blocks)
    paths, tests = [], []
    for n in sorted(wanted & set(blocks)):
        head = FILES_HEAD.search(blocks[n])
        if not head:
            continue
        seg = blocks[n][head.end():].split("\n\n", 1)[0]   # the list ends at the first blank line
        for m in FILES_LINE.finditer(seg):
            p = m.group(2).split(":", 1)[0].strip()
            if p and p not in paths:
                paths.append(p)
            if m.group(1) == "Test" and p not in tests:
                tests.append(p)
    return paths, tests


def in_fence(path: str, fence_paths) -> bool:
    return any(path == f or (f.endswith("/") and path.startswith(f)) for f in fence_paths)
```

  - In `screen()`, under `kind == "plan"`:

```python
        red = fm.get("red")
        if red is not None and (not isinstance(red, str) or not red.strip()
                                or (red.startswith("none:") and not red[5:].strip())):
            errs.append('red must be a command or "none: <why>"')
        if fm.get("escalate") not in (None, "on", "off"):
            errs.append("escalate must be on or off")
        if str(fm.get("rung") or "0") not in ("0", "1", "2"):
            errs.append("rung must be 0, 1 or 2")
```

  - `system/schemas/nightshift_item.md`: add after `verify`:
    `red: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_run.py]}`,
    `escalate: {kind: enum, values: ["on", "off"], default: "on", readers: [system/scripts/vaultlib/nightshift_run.py]}`,
    `rung: {kind: int, min: "0", readers: [system/scripts/vaultlib/nightshift_run.py]}`.

- [ ] **Step 5: Run** `system/scripts/test.sh system/tests/python/test_nightshift_check.py` and `system/scripts/test.sh system/tests/python/test_nightshift_item.py` and `system/scripts/test.sh system/tests/python/test_schema_notes.py`: all pass.

- [ ] **Step 6: Commit** `feat(orders): ladder note fields, the fence reader and their screen (D1)`.

### Task 2: `add` takes `--red` and `--escalate`

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_parser`, `_add`, the plain `list` in `main()`)
- Modify: `system/scripts/vaultlib/nightshift_check.py` (`_plan_at`)
- Test: `system/tests/python/test_nightshift_run.py`
- Test: `system/tests/python/test_nightshift_check.py`

**Interfaces:**
- Consumes: `nc.fence` (Task 1).
- Produces: `nightshift.py add … --red "<cmd>" | --red "none: <why>" [--escalate on|off]`. The note carries `red` always and `escalate` only when `off`.
- Produces: `_plan_at` error `red needs a Test: file in the selected tasks` for a red command (not `none:`) when `nc.fence(...)[1]` is empty.
- Produces: `list` prints `queued (rung N)` in the state column when the note has `rung` above 0.

- [ ] **Step 1: Update the existing callers first.** In `test_nightshift_run.py`, the `add()` helper passes `"--red", "none: fixture plan"`; every direct `nr.main(["add", …])` that expects exit 0 does the same (the calls near the workspace, codebase and abbreviation tests). `test_add_refuses_unready` keeps no `--red`.

- [ ] **Step 2: Write the failing tests** in `test_nightshift_run.py`:

```python
def test_add_needs_red(env, capsys):
    vault, tmp = env
    assert nr.main(["add", "--kind", "plan", "--title", "x", "--partition", "work", "--repo", "template",
                    "--base", "feat/x", "--plan", "docs/p.md", "--tasks", "1-2", "--verify", "true"], vault, NOW) == 2
    assert '--red needs a command that fails on the base, or "none: <why>"' in capsys.readouterr().out
    assert ni.items(vault) == []


def test_add_records_red_and_escalate_off(env):
    vault, tmp = env
    assert add(vault, "--escalate", "off") == 0
    _, fm = only_item(vault)
    assert fm["red"] == "none: fixture plan" and fm["escalate"] == "off"


def test_a_note_without_red_still_runs(env):
    vault, tmp = env
    assert add(vault, "--now") == 0
    path, fm = only_item(vault)
    ni.update(path, red=None)   # queued before the update
    nr.main(["tick"], vault, NOW)
    assert not str(only_item(vault)[1].get("reason") or "").startswith("invalid")
```

  In `test_nightshift_check.py`, a `_plan_at` case: a plan committed with `FILES_PLAN` (Task 1), `red: "pytest -q"`, `tasks: "3"` returns `red needs a Test: file in the selected tasks`; `tasks: "1"` returns no such error; `red: "none: docs"` with `tasks: "3"` returns none. Build the repository the way this file's existing `_plan_at` tests do.

- [ ] **Step 3: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_run.py -k "red or escalate"` and `system/scripts/test.sh system/tests/python/test_nightshift_check.py -k red`.

- [ ] **Step 4: Implement.**
  - `_parser`: on `a` (the `add` subparser) add `a.add_argument("--red")` and `a.add_argument("--escalate", choices=["on", "off"], default="on")`.
  - `_add`, plan branch: `fm.update(…, red=a.red, escalate="off" if a.escalate == "off" else None)`. Before `nc.check`, when `kind == "plan"` and not `a.red`, print `not ready: --red needs a command that fails on the base, or "none: <why>"` and return 2.
  - `_plan_at`, after the task loop:

```python
    red = str(fm.get("red") or "")
    if red and not red.startswith("none:") and not fence(shown.stdout, fm.get("tasks"))[1]:
        errs.append("red needs a Test: file in the selected tasks")
```

  - The plain `list` in `main()`: the state column is `f"{fm.get('state')} (rung {fm['rung']})" if str(fm.get('rung') or '0') != '0' else fm.get('state')`. `list --json` is unchanged.

- [ ] **Step 5: Run** `system/scripts/test.sh system/tests/python/test_nightshift_run.py` and `system/scripts/test.sh system/tests/python/test_nightshift_check.py`: all pass.

- [ ] **Step 6: Commit** `feat(orders): add takes --red and --escalate; list shows the rung (D1)`.

### Task 3: The red check in the sealed verify

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_deliver.py` (after `verify_sha`)
- Test: `system/tests/python/test_nightshift_deliver.py`

**Interfaces:**
- Produces: `nd.red_sha(runner_repo, base: str, tip: str, tests, vdir, cmd: str, log_path, lfs_store="", install="", toolchain=()) -> tuple[bool, str]`. `(True, "")` when the red command fails on `base` with `tip`'s copies of `tests` on top; otherwise `(False, text)` whose first line is one of:
  - `red: none of the plan's Test: files exist at <tip7>`
  - `red: <cmd> passed on the base commit with the new tests, so they do not show the change`
  - `<cmd>: exit 127 (command not found in the sealed verify sandbox)` (from `run_verify`, unchanged)
  - `order_install: …` (from `run_install`, unchanged)

- [ ] **Step 1: Write the failing tests** in `test_nightshift_deliver.py`, with a small runner repository: commit A holds `src.txt` = `old`; commit B (child of A) changes `src.txt` to `new` and adds `t/test_src.sh` = `grep -qx new src.txt`. Fetch both into a bare runner repository the way this file's `verify_sha` tests do.

```python
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_red_fails_on_base_with_the_new_test(runner, tmp_path):
    ok, text = nd.red_sha(runner.repo, runner.a, runner.b, ["t/test_src.sh"], tmp_path / "v", "sh t/test_src.sh",
                          tmp_path / "red.log")
    assert (ok, text) == (True, "")
    assert "$ sh t/test_src.sh" in (tmp_path / "red.log").read_text()


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_red_passes_on_base_is_red(runner, tmp_path):
    ok, text = nd.red_sha(runner.repo, runner.a, runner.b, ["t/test_src.sh"], tmp_path / "v", "true",
                          tmp_path / "red.log")
    assert not ok and text.startswith("red: true passed on the base commit")


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_red_with_no_test_file_at_the_tip(runner, tmp_path):
    ok, text = nd.red_sha(runner.repo, runner.a, runner.b, ["t/missing.sh"], tmp_path / "v", "true", tmp_path / "l")
    assert not ok and text == f"red: none of the plan's Test: files exist at {runner.b[:7]}"


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_red_command_missing_is_an_environment_failure(runner, tmp_path):
    ok, text = nd.red_sha(runner.repo, runner.a, runner.b, ["t/test_src.sh"], tmp_path / "v", "no-such-tool",
                          tmp_path / "l")
    assert not ok and "exit 127" in text.splitlines()[0]
    assert not (tmp_path / "v").exists()   # the checkout is removed
```

- [ ] **Step 2: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_deliver.py -k red`.

- [ ] **Step 3: Implement** beside `verify_sha`, reusing its checkout and clean-up shape:

```python
def red_sha(runner_repo, base: str, tip: str, tests, vdir, cmd: str, log_path, lfs_store: str = "", install: str = "",
            toolchain=()) -> tuple:
    """The red check (ladder spec §5): base's tree with tip's copies of the plan's Test: paths, then cmd offline. It
    must fail. Runs in a runner-made checkout, like verify_sha."""
    vdir = Path(vdir)
    shutil.rmtree(vdir, ignore_errors=True)
    checkout, corepack = vdir / "checkout", vdir / "corepack"
    lfs = ["-c", f"lfs.storage={lfs_store}"] if lfs_store else []
    try:
        corepack.mkdir(parents=True)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(runner_repo), str(checkout)], check=True,
                       capture_output=True, env=_git_env())
        subprocess.run(["git", "-C", str(checkout), "-c", "advice.detachedHead=false", *lfs, "checkout", "-q", "--detach", base],
                       check=True, capture_output=True, env=_git_env())
        present = [p for p in tests if subprocess.run(["git", "-C", str(checkout), "cat-file", "-e", f"{tip}:{p.rstrip('/')}"],
                                                      capture_output=True, env=_git_env()).returncode == 0]
        if not present:
            return False, f"red: none of the plan's Test: files exist at {tip[:7]}"
        subprocess.run(["git", "-C", str(checkout), *lfs, "checkout", "-q", tip, "--", *[p.rstrip("/") for p in present]],
                       check=True, capture_output=True, env=_git_env())
        if install:
            ok, out = run_install(checkout, install, toolchain, log_path, corepack_home=corepack)
            if not ok:
                return ok, out
        ok, out = run_verify(checkout, [cmd], log_path, toolchain=toolchain, corepack_home=corepack)
        if ok:
            return False, f"red: {cmd} passed on the base commit with the new tests, so they do not show the change"
        return (False, out) if "exit 127" in out.splitlines()[0] else (True, "")
    finally:
        shutil.rmtree(vdir, ignore_errors=True)
```

- [ ] **Step 4: Run** `system/scripts/test.sh system/tests/python/test_nightshift_deliver.py`: all pass.

- [ ] **Step 5: Commit** `feat(orders): the red check runs the new tests on the base in the sealed verify (D1)`.

### Task 4: Climbing: the handoff, the rung's session and the fix prompt

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_elapsed`, `_run_session`, `_deliver_plan`'s verify block, `run_item`, new `_climbs`, `_ladder`, `_save_ladder`, `_first_line`, `_handoff`, `_climb`)
- Modify: `system/scripts/vaultlib/nightshift_session.py` (new `fix_prompt`)
- Test: `system/tests/python/test_nightshift_run.py`
- Test: `system/tests/python/test_nightshift_session.py`

**Interfaces:**
- Consumes: the note fields (Task 1).
- Produces: `ss.fix_prompt(fm: dict, rung: int) -> str`.
- Produces: `nr.RUNGS(fm) -> list[str]`, the models of rungs 1.., `["opus"]` for an `opus` item, else `[fm model, "opus"]`.
- Produces: `items/<id>/ladder.json` as spec §4.6, `items/<id>/handoff-<rung>.md`, `.nightshift/handoff.md` in the clone, `items/<id>/elapsed-<rung>`.
- Produces: `_deliver_plan`'s verify-blocked outcome carries `"detail": <run_verify text>`; climbing outcomes are read from `reason` and `detail`.

- [ ] **Step 1: Write the failing tests.** In `test_nightshift_session.py`:

```python
def test_fix_prompt_names_the_handoff_the_fence_and_no_rewrite():
    p = ss.fix_prompt({"plan": "docs/p.md", "tasks": "1-2"}, 1)
    for part in (".nightshift/handoff.md", "new commits", "never amend, rebase or reset", "only the paths",
                 ".nightshift/result.json", ".nightshift/protected/claude/"):
        assert part in p
    assert ss.CONTRACT in p
```

  In `test_nightshift_run.py`, a helper that makes the stub's verify fail until a given session, through a counter file (the stub runs `NIGHTSHIFT_STUB_SHELL` on every call). Every session commits `done.txt` (so the fixture plan's fallback fence, the files rung 0 changed, holds every rung), with a distinct second line (so each rung adds a commit); its first line is `yes` only from session `fixed_on` on. Items using it are queued with `add(vault, "--now", *YES)`.

```python
YES = ("--verify", "grep -qx yes done.txt")


def climbing_stub(tmp, fixed_on=2):
    """Session n (1-based) commits done.txt with `yes` on its first line only from session `fixed_on` on. Each call
    appends its --model to models.txt."""
    stub(tmp, ARGS=str(tmp / "args.txt"), SHELL=(
        f'n=$(( $(cat {tmp}/calls 2>/dev/null || echo 0) + 1 )); echo $n > {tmp}/calls; '
        f'grep -A1 -x -- --model {tmp}/args.txt | tail -1 >> {tmp}/models.txt; '
        f'v=no; [ "$n" -ge {fixed_on} ] && v=yes; printf "%s\\n%s\\n" "$v" "$n" > done.txt; '
        f'git add done.txt && git -c user.name=t -c user.email=t@e commit -qm "work $n"'))


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_verify_failure_climbs_and_rung_1_delivers(env):
    vault, tmp = env
    climbing_stub(tmp, fixed_on=2)
    assert add(vault, "--now", *YES) == 0
    nr.main(["tick"], vault, NOW)
    path, fm = only_item(vault)
    assert fm["state"] == "queued" and fm["rung"] == "1" and not fm.get("session_id")
    idir = rep.item_dir(vault, fm["id"])
    handoff = (idir / "handoff-1.md").read_text()
    assert "## Failing check" in handoff and "grep -qx yes done.txt" in handoff and fm["base_sha"] in handoff
    assert (tmp / "ws" / f"nightshift-{fm['id']}" / ".nightshift" / "handoff.md").is_file()
    assert nr.main(["tick"], vault, NOW + timedelta(minutes=15)) == 0
    _, fm = only_item(vault)
    assert fm["state"] == "done" and fm["result"] == "https://github.com/o/r/pull/1"
    (row,) = rep.data(vault, "2026-10-07")["items"]   # the table shows the result for a done item; notes are here
    assert "rungs: 1 sonnet (green)" in row["notes"]


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_ladder_models(env):
    vault, tmp = env
    climbing_stub(tmp, fixed_on=99)
    assert add(vault, "--now", *YES) == 0
    for i in range(3):
        nr.main(["tick"], vault, NOW + timedelta(minutes=15 * i))
    _, fm = only_item(vault)
    assert fm["state"] == "blocked" and fm["reason"] == "verify"
    assert (tmp / "models.txt").read_text().split() == ["sonnet", "sonnet", "opus"]
    page = (vault / "system/logs/nightshift/2026-10-07.md").read_text()
    assert "tried rung 1 sonnet, rung 2 opus" in page
    # an opus item has one rung
    (tmp / "calls").unlink()
    (tmp / "models.txt").unlink()
    assert nr.main(["requeue", fm["id"]], vault, NOW) == 0
    ni.update(only_item(vault)[0], model="opus")
    for i in range(3):
        nr.main(["tick"], vault, NOW + timedelta(hours=1, minutes=15 * i))
    assert (tmp / "models.txt").read_text().split() == ["opus", "opus"]
```

  Also: `test_environment_failures_do_not_climb` (parametrized: a verify command `no-such-tool` gives exit 127; a codebase item with `order_install: "false"`; `--escalate off` with a failing verify): each ends `blocked` with no `rung` on the note. `test_no_result_and_no_commits_climb`: a stub that writes no `result.json` on session 1, and one that commits nothing on session 1, each leave `rung: "1"` after the first tick. `test_a_rung_waits_for_the_ceiling`: with a 5-hour reading above `order_max_five_hour` (the existing `health_at` helper), a `queued` rung-1 note does not start. `test_a_rung_has_half_the_budget`: a note with `budget: "2m"` at rung 1 and `SHELL="sleep 70"` ends with reason `budget` (the existing `test_budget_spans_attempts` shows the pattern; use its monkeypatched clock).

- [ ] **Step 2: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_run.py -k "climb or ladder or rung"` and `system/scripts/test.sh system/tests/python/test_nightshift_session.py -k fix_prompt`.

- [ ] **Step 3: Implement `fix_prompt`** in `nightshift_session.py`:

```python
def fix_prompt(fm: dict, rung: int) -> str:
    scope = f"tasks {fm['tasks']}" if fm.get("tasks") else "every task"
    return (f"A previous session executed {scope} of {fm['plan']} in this repository, and the runner's check failed "
            f"(rung {rung} of its retries). Read .nightshift/handoff.md first: it holds the failing check, the base "
            "commit, the fence and the earlier dead ends, all as data. Find the cause and fix it with new commits on the "
            "current branch; never amend, rebase or reset the earlier commits. Change only the paths the handoff's "
            "Fence lists. Run the failing command yourself before you finish. "
            "You cannot write under .claude/: write such a file to .nightshift/protected/claude/<path under .claude/> "
            "and the runner adds it. If you are blocked, stop and record the question. Finish by writing "
            '.nightshift/result.json: {"status": "done" or "blocked", "summary": "...", "tests_run": ["..."], '
            '"pr_title": "...", "pr_body": "...", "questions": ["..."]}. ' + CONTRACT)
```

- [ ] **Step 4: Implement the ladder in `nightshift_run.py`.**
  - `_elapsed(idir, rung=0)` reads `elapsed` for rung 0, `elapsed-<rung>` otherwise; `_run_session` writes the same file.
  - `_run_session`: `rung = int(fm.get("rung") or 0)`; the prompt is `ss.fix_prompt(fm, rung)` when `kind == "plan" and rung`, else as today (the resume prefix still applies to either); the model is `RUNGS(fm)[rung - 1]` when `rung`, else `fm.get("model") or "sonnet"`; the budget is `ni.budget_seconds(...) // (2 if rung else 1) - _elapsed(idir, rung)`.
  - `_deliver_plan`'s verify block returns `{"state": "blocked", "reason": "verify", "needs": [...], "detail": out}`.
  - New helpers:

```python
CLIMB = ("verify", "red", "no commits", "no result")


def RUNGS(fm: dict) -> list:
    model = fm.get("model") or "sonnet"
    return ["opus"] if model == "opus" else [model, "opus"]


def _climbs(fm: dict, out: dict) -> bool:
    """Ladder spec §4.1: a code failure climbs; the environment and the owner's blocks do not."""
    if fm.get("escalate") == "off" or out.get("reason") not in CLIMB:
        return False
    first = (out.get("detail") or "").splitlines()[:1]
    return not (first and (first[0].startswith("order_install:") or "exit 127" in first[0]))


def _ladder(idir: Path) -> dict:
    f = idir / "ladder.json"
    return json.loads(f.read_text()) if f.is_file() else {"last_sha": "", "fence": [], "tests": [], "rungs": []}


def _save_ladder(idir: Path, lad: dict) -> None:
    (idir / "ladder.json").write_text(json.dumps(lad))


FAILING = re.compile(r"FAIL|Error|error:|not ok|assert", re.I)


def _first_line(out: dict) -> str:
    """Spec §4.6: the command line plus the first failing line of its tail, at most 200 characters."""
    text = out.get("detail") or ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return out.get("reason") or ""
    hit = next((l for l in lines[1:] if FAILING.search(l)), lines[-1] if len(lines) > 1 else "")
    return f"{lines[0]} | {hit}"[:200] if hit else lines[0][:200]
```

  - `_handoff(ctx, fm, idir, cwd, out, lad, rung)` builds the spec §4.3 text: the failing-check block is `_first_line(out)` then the last 200 lines of `verify.log` (or `red.log` when `reason == "red"`), omitted for `no result` and `no commits` (which say what happened instead); the fence from `lad["fence"]` (`(none recorded)` when empty); dead ends from `lad["rungs"]`; the last 2,000 characters of `ss.parse_stream(idir / "stream.last.jsonl")["result"].get("result")` when present. Write it to `cwd / ".nightshift" / "handoff.md"` (make the folder) and to `idir / f"handoff-{rung}.md"`.
  - `_climb(ctx, path, fm, idir, cwd, out) -> bool`:

```python
def _climb(ctx: Ctx, path: Path, fm: dict, idir: Path, cwd: Path, out: dict) -> bool:
    """Record this rung; queue the next one with a handoff, or say which rungs ran and return False."""
    rung = int(fm.get("rung") or 0)
    lad = _ladder(idir)
    lad["rungs"].append({"rung": rung, "model": RUNGS(fm)[rung - 1] if rung else (fm.get("model") or "sonnet"),
                         "reason": out["reason"], "line": _first_line(out),
                         "started_at": fm.get("started_at"), "finished_at": ctx.clock_now().isoformat()})
    _save_ladder(idir, lad)
    if rung < len(RUNGS(fm)):
        _handoff(ctx, fm, idir, cwd, out, lad, rung + 1)
        ni.update(path, state="queued", rung=str(rung + 1), attempts=None, session_id=None, reason=None)
        ctx.log({"item": fm["id"], "state": "queued", "rung": rung + 1, "reason": out["reason"]})
        return True
    tried = ", ".join(f"rung {r['rung']} {r['model']}" for r in lad["rungs"] if r["rung"])
    head = (out.get("needs") or [f"{out['reason']}: {_first_line(out)}"])[0]
    out["needs"] = [f"{head} (tried {tried}; handoffs in {idir})"] + (out.get("needs") or [])[1:]
    return False
```

  - `run_item`, plan branch:

```python
    elif fm["kind"] == "plan":
        out = _deliver_plan(ctx, fm, cwd, idir, before)
        if _climbs(fm, out) and _climb(ctx, path, fm, idir, cwd, out):
            return 0
```

  - `_finish`, for a final plan outcome with a `ladder.json` that has rungs above 0: prefix `notes` with `rungs: ` and one `<rung> <model> (<reason>: <line>)` per failed rung and `<rung> <model> (green)` for a delivered last rung, joined by `; `. Write this through a small `_ladder_note(idir, out)` helper.

- [ ] **Step 5: Run** `system/scripts/test.sh system/tests/python/test_nightshift_run.py` and `system/scripts/test.sh system/tests/python/test_nightshift_session.py`: all pass, the older tests included.

- [ ] **Step 6: Commit** `feat(orders): a code failure climbs to a fresh session with a handoff, own model then Opus (D1)`.

### Task 5: Delivery on a rung: history, fence and no commits

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_deliver_plan`, new `_rung_problem`)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `nc.fence`, `nc.in_fence` (Task 1), `_ladder` (Task 4).
- Produces: `ladder.json` gains `fence`, `tests` and `last_sha` at rung 0's delivery (after `fetch_branch`), whatever the outcome after it.

- [ ] **Step 1: Write the failing tests:**

```python
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_rung_that_rewrites_history_blocks(env):
    vault, tmp = env
    climbing_stub(tmp, fixed_on=99)
    assert add(vault, "--now", *YES) == 0
    nr.main(["tick"], vault, NOW)
    stub(tmp, SHELL="echo again >> done.txt && git add done.txt && git -c user.name=t -c user.email=t@e commit -q --amend -m again")
    nr.main(["tick"], vault, NOW + timedelta(minutes=15))
    _, fm = only_item(vault)
    assert (fm["state"], fm["reason"]) == ("blocked", "fence")
    assert git(tmp / "remote.git", "branch", "--list", "order/*").strip() == ""


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_rung_outside_the_fence_blocks(env):
    vault, tmp = env
    write(vault, "docs/p.md", "# P\n### Task 1: A\n**Files:**\n- Create: `done.txt`\n\nDo it.\n### Task 2: B\nMore.\n")
    git(vault, "add", "-A")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "plan with files")
    git(vault, "branch", "-f", "feat/x")
    git(vault, "push", "-q", "-f", str(tmp / "remote.git"), "feat/x")
    climbing_stub(tmp, fixed_on=99)
    assert add(vault, "--now", *YES) == 0
    nr.main(["tick"], vault, NOW)
    stub(tmp, SHELL="echo y > stray.txt && git add stray.txt && git -c user.name=t -c user.email=t@e commit -qm stray")
    nr.main(["tick"], vault, NOW + timedelta(minutes=15))
    _, fm = only_item(vault)
    assert (fm["state"], fm["reason"]) == ("blocked", "fence")
    assert "stray.txt" in (vault / "system/logs/nightshift/2026-10-07.md").read_text()
```

  And `test_a_rung_with_no_new_commit_is_no_commits`: rung 1's stub commits nothing; the rung records `no commits` and climbs to rung 2.

- [ ] **Step 2: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_run.py -k "rung_"`.

- [ ] **Step 3: Implement.** In `_deliver_plan`, right after the `fetch_branch` fallback and before `if sha == before["base_sha"]`:

```python
    lad, rung = _ladder(idir), int(fm.get("rung") or 0)
    if rung:
        problem = _rung_problem(runner, lad, sha)
        if problem:
            return problem
    else:
        plan = nc.git(runner, "show", f"{before['base_sha']}:{fm['plan']}").stdout
        lad["fence"], lad["tests"] = nc.fence(plan, fm.get("tasks"))
        if not lad["fence"]:
            lad["fence"] = [p for p in nc.git(runner, "diff", "--name-only", before["base_sha"], sha).stdout.split("\n") if p]
    lad["last_sha"] = sha
    _save_ladder(idir, lad)
```

```python
def _rung_problem(runner: Path, lad: dict, sha: str) -> dict | None:
    """Ladder spec §4.5, read in the runner's repository: the rung kept the earlier commits, stayed in the fence and
    added a commit."""
    last = lad.get("last_sha") or ""
    if last and nc.git(runner, "merge-base", "--is-ancestor", last, sha).returncode:
        return {"state": "blocked", "reason": "fence", "needs": ["The retry rewrote the earlier commits; nothing was pushed"]}
    if sha == last:
        return {"state": "blocked", "reason": "no commits"}
    changed = [p for p in nc.git(runner, "diff", "--name-only", last, sha).stdout.split("\n") if p]
    out = [p for p in changed if not nc.in_fence(p, lad.get("fence") or [])]
    if out:
        return {"state": "blocked", "reason": "fence", "needs": [f"The retry changed files outside the plan: {', '.join(out[:5])}"]}
    return None
```

  The protected files a rung proposes (`.nightshift/protected/claude/…`) are not commits, so they never appear in this diff; `apply_protected` adds them after. `nc.git` takes a repository path and works on the bare runner repository.

- [ ] **Step 4: Run** `system/scripts/test.sh system/tests/python/test_nightshift_run.py`: all pass.

- [ ] **Step 5: Commit** `feat(orders): a rung keeps the earlier commits, stays in the plan's files and adds a commit (D1)`.

### Task 6: Wire the red check into delivery

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_deliver_plan`, verify call)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `nd.red_sha` (Task 3), `lad["tests"]` (Task 5).

- [ ] **Step 1: Write the failing tests:** a template item whose plan has Task 1 with `**Files:**` listing `- Create: \`done.txt\`` and `- Test: \`t.sh\`` (rewrite `docs/p.md` and move `feat/x` the way `test_a_rung_outside_the_fence_blocks` does), queued with `--red "sh t.sh"` and `--verify "sh t.sh"`. Read notes through `rep.data(vault, "2026-10-07")["items"]`, since the report table shows a done item's result.
  - Session commits `t.sh` = `test -f done.txt` and `done.txt`: the order is `done` (red on the base, green on the tip).
  - Session commits `t.sh` = `true` and `done.txt`, queued with `--red "sh t.sh"`: rung 0 climbs with reason `red`, and `handoff-1.md` holds `passed on the base commit`.
  - Queued with `--red "none: docs only"`: no red check runs (`red.log` absent) and the report row's notes carry `red: none (docs only)`.
  - A note with no `red` (field removed after `add`): the report row's notes carry `red: none (queued before --red)`.

- [ ] **Step 2: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_run.py -k red`.

- [ ] **Step 3: Implement.** In `_deliver_plan`:
  - The verify commands are `cmds = list(fm.get("verify") or [])`, plus the red command when it is not `none:` and not already in the list.
  - After a green verify and before writing `delivery.json`:

```python
    red = str(fm.get("red") or "")
    if red and not red.startswith("none:"):
        ok, out = nd.red_sha(runner, before["base_sha"], sha, _ladder(idir).get("tests") or [],
                             ctx.workspace / f"nightshift-{fm['id']}-red", red, idir / "red.log", nc.lfs_store(src),
                             str(cb.get("order_install") or ""), nc.toolchain(cb))
        if not ok:
            return {"state": "blocked", "reason": "red", "needs": [f"Fix the red check: {out.splitlines()[0]}"],
                    "detail": out}
```

  - `_finish`'s notes for a plan outcome add `red: none (<why>)` for a `none:` value and `red: none (queued before --red)` for a missing one, after any `rungs:` part.
  - `_climbs` already treats reason `red` as climbing and an exit 127 first line as the environment (Task 4).
  - The 7-day clean-up in `_reconcile` and `_requeue` also removes `nightshift-<id>-red`.

- [ ] **Step 4: Run** `system/scripts/test.sh system/tests/python/test_nightshift_run.py`: all pass.

- [ ] **Step 5: Commit** `feat(orders): delivery runs the red check after a green verify (D1)`.

### Task 7: Requeue, cancel and the Needs-you line

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_requeue`)
- Test: `system/tests/python/test_nightshift_run.py`

- [ ] **Step 1: Write the failing tests:** `test_requeue_clears_the_rung` (a blocked note with `rung: "2"` is requeued with no `rung`, and the old `ladder.json` moved to `items/<id>.1/`); `test_cancel_stops_a_queued_rung` (a note at `queued`, `rung: "1"`, cancelled, is never started by the next tick); `test_a_final_block_leaves_one_now_line_naming_the_rungs` (after `test_ladder_models`' three ticks, the Now page has exactly one open line for the item and it contains `tried rung 1 sonnet, rung 2 opus`, within 300 characters).

- [ ] **Step 2: Run them and see them fail:** `system/scripts/test.sh system/tests/python/test_nightshift_run.py -k "requeue_clears or queued_rung or final_block"`.

- [ ] **Step 3: Implement.** `_requeue`'s `ni.update` adds `rung=None`. The Now line is `_owed`'s statement from `out["needs"][0]`, which `_climb` already rewrote; `nowmod.add(..., fit=True)` cuts it to 300 characters. Fix whatever the tests show.

- [ ] **Step 4: Run** `system/scripts/test.sh system/tests/python/test_nightshift_run.py`: all pass.

- [ ] **Step 5: Commit** `feat(orders): requeue clears the rung; a final block names each rung (D1)`.

### Task 8: Docs, release note, the core cap and the gate

**Files:**
- Modify: `FOUNDRY.md` (the **Work Orders** paragraph under Daily use)
- Modify: `.claude/skills/order/SKILL.md`
- Create: `changes/2026-11-03-work-order-ladder.md`
- Modify: `system/tests/vault_integrity.bats`
- Modify: `docs/superpowers/roadmap.md`
- Modify: `docs/superpowers/2026-10-29-foreman-dispatch-plan.md`

- [ ] **Step 1: FOUNDRY.md.** After the sentence that says a plan item is verified, pushed to a branch and ends in a pull request, add: a plan item states `--red "<cmd>"` (a command the plan's new tests make fail on the base and pass on the delivered commit; the runner checks both in the sealed verify, with the plan's `Test:` files on top of the base) or `--red "none: <why>"`; when the verify fails, the red check finds the new tests pass on the base, or the session leaves no commits or no result, the item climbs: a fresh session in the kept clone reads `.nightshift/handoff.md` (the failing check, the base commit, the plan's files as a fence, earlier dead ends) on the item's model, then on Opus, each with half the budget, before a Needs-you line names each rung; a retry that changes files outside the plan's **Files** lists or rewrites earlier commits blocks with `fence`; `--escalate off` turns it off; the record is `items/<id>/ladder.json`. Keep to the paragraph's style; one run of sentences, no list.

- [ ] **Step 2: Order skill.** In `/order add`'s step 2, after proposing `--verify`: propose `--red` from the plan's test command for the tasks' `Test:` files, or `--red "none: <why>"` for a plan with no new tests; show it with the others. Add `--red` and `[--escalate off]` to step 3's command line, and one sentence that a failing check climbs twice before it reaches the user.

- [ ] **Step 3: Release note** `changes/2026-11-03-work-order-ladder.md`:

```
- Changed: a plan Work Order whose verify fails, whose new tests already pass before the change, or whose session leaves no commits or no result now retries in a fresh session with the failure in hand, first on its own model and then on Opus, before it reaches you; a retry that touches files outside the plan's Files lists blocks. `--escalate off` turns it off. (#N)
  - Action: queue plan orders with `--red "<test command>"` (or `--red "none: <why>"`); `/order add` proposes it.
```

  Replace `#N` with this pull request's number.

- [ ] **Step 4: Core cap.** In `system/tests/vault_integrity.bats`, `CORE_CAP=16640`, the test name's line count updated, and one comment line under the last raise: `# 16,480 -> 16,640 (Foreman dispatch D1, the Work Order ladder, owner to approve at merge): climbing, the handoff, the fence, the red check and --red took core from 16,184 to <measured>.` Measure with `git ls-files -z system/scripts system/hooks .claude/commands | xargs -0 cat | wc -l`.

- [ ] **Step 5: Roadmap and program plan.** The Foreman dispatch row's state cell: D1 done with this pull request; D2 next. The program plan's D1 state: `done`.

- [ ] **Step 6: Run the gate:** `system/scripts/verify_setup.sh`. Read its verdict from the exit code. Fix anything it reports.

- [ ] **Step 7: Commit** `docs(orders): the ladder in FOUNDRY.md, the order skill, release note and core cap; D1 done`.
