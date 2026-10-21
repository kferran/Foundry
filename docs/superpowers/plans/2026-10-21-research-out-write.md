# Absolute Path Rules for Session Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A research Work Order can write `out/` after a Bash `cd`, the headless private-folder denies hold after a `cd`, and a denied `out/` write fails with its own reason (#314).

**Architecture:** `nightshift_session.profile()` gains a required `cwd` keyword and rewrites every `Tool(./<p>)` rule to `Tool(//<cwd>/<p>)`. `headless.settings.json` keeps its relative private-folder pair (the only form the sandbox merges, resolved at launch) and adds the `//**/` pair (the form the Read and Edit tools honour after a `cd`). `parse_stream()` collects the Write and Edit paths in the result event's `permission_denials`, and `_deliver_research` turns a missing result or note into `out write denied` when one of them lies under `out/`.

**Tech Stack:** Python (stdlib), bats, jq, pytest.

**Spec:** `docs/superpowers/specs/2026-10-21-research-out-write-design.md` (probe: `docs/superpowers/spikes/2026-10-21-research-out-write-probe.md`, its Bash side section decides Design 2 and 4)

## Global Constraints

- Lane: feature on a safety surface (the Work Order profile and headless confinement): the owner merges; never enable auto-merge.
- Non-goals: stopping sessions from running `cd`; changing what any profile allows or denies.
- Design 2 as built (probe, Bash side): keep `Read(wiki/*/private/**)` and `Edit(wiki/*/private/**)`, add `Read(//**/wiki/*/private/**)` and `Edit(//**/wiki/*/private/**)`. Neither form alone fences both Bash and the Read tool after a `cd`.
- Design 4 as built: no `sandbox.filesystem.*` entry changes. `**/.env*` masks nothing with or without a `cd` (a glob gap, not a `cd` defect); a separate issue tracks it.
- Keep edits to `nightshift_run.py` small and local: a sibling PR (#298) edits `_screen`, `_research_dir` and `_deliver_research`'s output checks.
- `budget` and `cancelled` keep their precedence (they return before delivery); denials are read from the result event only.
- Core budget: `git ls-files -z system/scripts | xargs -0 cat | wc -l` stays at or under 13,950 (13,916 at master `1d152aa`).
- Template stays generic: no user paths, host, employer, client or people names.
- bats rule R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions. bats needs the sandbox off.
- Test commands: `system/scripts/test.sh <suite.bats | pytest path>`.
- CHANGELOG: one line under `## 2026-10-21`, in Task 4.

## Review Focus

1. **A symlinked `order_workspace`:** `_run_session` passes the unresolved path and the session may report either form; the profile carries both roots, and the out/ check resolves both sides (Task 1 and Task 3 tests).
2. **A workspace path with `(`, `)` or `*`:** the rule syntax would break; `profile()` refuses it with `ValueError` naming the path, which the worker turns into an alert (Task 1 test).
3. **A denial outside `out/`** (a write the brief never asked for) with no findings note: still `no result`, never `out write denied` (Task 3 test).
4. **A findings note written but `result.json` denied:** `out write denied` naming `result.json` (Task 3 test).
5. **A result event with no `permission_denials` key, or entries that are not objects:** no crash; `denied` is empty (Task 3 test).

---

### Task 1: The research profile anchors `./` rules at the session's directory

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_session.py` (`profile`)
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_selftest_once` and `_run_session` callers, one argument each)
- Test: `system/tests/python/test_nightshift_session.py`

**Interfaces:**
- Produces: `profile(vault, kind: str, hosts, web_hosts=(), deny=(), *, cwd) -> dict`. `cwd` is required; every caller passes the directory the session runs in.

- [ ] **Step 1: Write the failing tests** in `test_nightshift_session.py`, and add `cwd=REPO` (or `tmp_path`) to every existing `ss.profile(...)` call there.

```python
PATH_RULE = re.compile(r"^(Read|Write|Edit|Glob|Grep|NotebookEdit)\((?!//|~/)")

def test_profiles_carry_no_rule_a_cd_can_move(tmp_path):
    for kind in ("plan", "research"):
        p = ss.profile(REPO, kind, [], cwd=tmp_path)
        assert [r for r in p["permissions"]["allow"] + p["permissions"]["deny"] if PATH_RULE.match(r)] == []
    allow = ss.profile(REPO, "research", [], cwd=tmp_path)["permissions"]["allow"]
    assert f"Write(//{str(tmp_path).lstrip('/')}/out/**)" in allow and f"Edit(//{str(tmp_path).lstrip('/')}/out/**)" in allow

def test_a_symlinked_workspace_gets_both_roots(tmp_path):
    (tmp_path / "real").mkdir(); (tmp_path / "link").symlink_to(tmp_path / "real")
    allow = ss.profile(REPO, "research", [], cwd=tmp_path / "link")["permissions"]["allow"]
    for root in (tmp_path / "link", tmp_path / "real"):
        assert f"Write(//{str(root).lstrip('/')}/out/**)" in allow

def test_a_workspace_the_rule_syntax_cannot_hold_is_refused(tmp_path):
    with pytest.raises(ValueError, match="order_workspace"):
        ss.profile(REPO, "research", [], cwd=tmp_path / "a(b)")
```

- [ ] **Step 2: Run** `system/scripts/test.sh system/tests/python/test_nightshift_session.py`. Expected: FAIL (`profile()` takes no `cwd`).
- [ ] **Step 3: Implement.** In `profile()`, after the deny list is built, replace each `allow` and `deny` rule matching `(\w+)\(\./(.*)\)` with one rule per root, `Tool(//<root without leading />/<p>)`, roots `os.path.abspath(cwd)` and `Path(cwd).resolve()` (deduplicated, order kept). Raise `ValueError(f"order_workspace path {cwd} holds a character the permission rule syntax treats as special")` when a root contains `(`, `)` or `*`. Comment: a `./` rule resolves against the shell's current directory, which a Bash `cd` moves (#314). `_selftest_once` passes `cwd=tmp`; `_run_session` passes `cwd=cwd`.
- [ ] **Step 4: Run** the session tests and `system/scripts/test.sh system/tests/python/test_nightshift_run.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(nightshift): anchor the research profile's ./ rules at the session's directory (#314)`.

### Task 2: Headless private-folder denies hold after a `cd`

**Files:**
- Modify: `system/headless.settings.json` (deny list)
- Modify: `FOUNDRY.md` (Security model, Private folder paragraph)
- Modify: `docs/superpowers/specs/2026-10-21-research-out-write-design.md` (one superseded marker under Design 2)
- Test: `system/tests/vault_integrity.bats` (private-folder test and the headless-rules test)

- [ ] **Step 1: Write the failing tests.** In `settings deny Read and Edit on wiki/<partition>/private/ (#166)`, keep the two relative checks, replace the comment with why both forms exist (the relative one is merged into the sandbox at launch; the `//**/` one fences the tools after a `cd`; probe Bash side), and add `jq -e` checks for `Read(//**/wiki/*/private/**)` and `Edit(//**/wiki/*/private/**)`. In `headless settings have no allows, no /-anchored rules, and a strict sandbox`, add: every bare or `./` deny rule has its `//**/` twin.

```bash
  [ "$(jq '[.permissions.deny[] | select(test("^[A-Za-z]+\\((?![/~])")) | capture("^(?<t>[A-Za-z]+)\\((\\./)?(?<p>.*)\\)$") | "\(.t)(//**/\(.p))"] - .permissions.deny | length' "$f")" = "0" ]
```

- [ ] **Step 2: Run** `system/scripts/test.sh system/tests/vault_integrity.bats`. Expected: both tests FAIL.
- [ ] **Step 3: Implement.** Add the two `//**/` rules after the relative pair in `headless.settings.json`. In FOUNDRY.md, the headless half of the Private folder sentence names both forms and what each fences; the sandbox-merge clause says a `//**/` glob is not merged. Under spec Design 2 add: `superseded 2026-10-21, was "The two private-folder denies become Read(//**/…) and Edit(//**/…)": both forms ship (probe, Bash side).`
- [ ] **Step 4: Run** `vault_integrity.bats` and `headless.bats`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(headless): private-folder denies hold after a cd (#314)`.

### Task 3: A denied `out/` write fails as `out write denied`

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_session.py` (`parse_stream`)
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_run_session` return, `_deliver_research`, its `run_item` call)
- Test: `system/tests/python/test_nightshift_session.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: Task 1's `profile(..., cwd=)`.
- Produces: `parse_stream(path)["denied"] -> list[str]`, the `tool_input.file_path` of each `Write` or `Edit` entry in the result event's `permission_denials` (entry shape from the probe: `{"tool_name", "tool_use_id", "tool_input": {"file_path", ...}}`). `_run_session` adds `"denied"` to its `finished` outcome. `_deliver_research(ctx, fm, d, denied=())`.

- [ ] **Step 1: Write the failing tests.**
  - `test_nightshift_session.py::test_parse_collects_denied_writes`: a stream whose result carries a Write denial at `/w/out/A.md`, an Edit denial at `/w/out/B.md`, a Bash denial, and a non-dict entry gives `denied == ["/w/out/A.md", "/w/out/B.md"]`; `ok.jsonl` (no key) gives `[]`.
  - `test_nightshift_run.py::test_research_out_write_denied_is_its_own_reason`: a research item whose stub writes nothing and whose stream's result denies a Write at `<ws>/nightshift-<id>/out/Answer.md` (the stub's `SHELL` rewrites a placeholder in the stream with `$PWD`) fails with reason `out write denied`, and the outcome's needs line names the path and `stream.jsonl`.
  - `test_nightshift_run.py::test_research_no_write_and_no_denial_is_no_result`: same item, no denial: `no result`.
  - `test_nightshift_run.py::test_research_denial_outside_out_is_no_result`: a denial at `<ws>/nightshift-<id>/code/out/Answer.md`: `no result`.
  - `test_nightshift_run.py::test_research_result_json_denied_names_it`: the stub writes the findings note, the stream denies `out/result.json`: `out write denied` naming `result.json`.
- [ ] **Step 2: Run** both files. Expected: the new tests FAIL (`KeyError: 'denied'`, reason `no result`).
- [ ] **Step 3: Implement.** `parse_stream` adds `"denied"` from `out["result"]`. `_run_session` returns `{"outcome": "finished", "usage": s["usage"], "denied": s["denied"]}`. `run_item` calls `_deliver_research(ctx, fm, cwd, run.get("denied", ()))`. In `_deliver_research`, both `no result` returns go through one helper `_no_result(ctx, fm, d, denied) -> dict` that returns `{"state": "failed", "reason": "out write denied", "needs": [f"The session's write to {path} was denied: see {item_dir}/stream.jsonl"]}` for the first denied path whose `(d / path).resolve()` lies under `(d / "out").resolve()`, else `{"state": "failed", "reason": "no result"}`.
- [ ] **Step 4: Run** `test_nightshift_*.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(nightshift): a denied out/ write fails as out write denied (#314)`.

### Task 4: Verify, live acceptance, release note

- [ ] **Step 1:** Run `test_nightshift_*.py`, `headless.bats`, `vault_integrity.bats`, `nightshift*.bats`, `conformance.bats`, and the core budget count (≤ 13,950). Expected: all pass.
- [ ] **Step 2: Live headless run:** a throwaway clone under `.scratch/`, one ingest of a tiny neutral inbox drop through `run_headless.sh`; it publishes. Delete the clone. Record pass/fail for the PR body.
- [ ] **Step 3: Live research session:** the probe setup (runner `profile(..., cwd=W)` and `command("research", ...)`, settings outside `W`, `session_env()`), a prompt that runs `cd context` and then writes `out/x.md`; `W/out/x.md` exists and the result has no denial. Delete the directory.
- [ ] **Step 4:** CHANGELOG line under `## 2026-10-21`: research Work Orders whose session runs `cd` now publish their findings note, and a denied `out/` write fails as `out write denied`; headless private-folder denies hold after a `cd`. Ends `(#<PR>)`.
- [ ] **Step 5: Commit** and open the PR ("Fixes #314", label `defect:C4-confinement`); the owner merges.
