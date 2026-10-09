# Telemetry Shared Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A vault can report errors from shared services that log without the attribute its ADX sources filter on: the empty-value filter is pinned by tests, documented in `example.md`, and offered by `/setup` phase 6a (issue #94, part A).

**Architecture:** No fetch code changes. `adx_filter: {<attribute>: ""}` already renders `== ""`, which Kusto matches for a missing or empty attribute. Task 1 pins that behavior. Task 2 documents it and adds the `/setup` question.

**Tech Stack:** Python 3 stdlib, pytest, bats 1.8.2.

**Spec:** `docs/superpowers/specs/2026-10-09-telemetry-shared-services-design.md`

## Global Constraints

- Work on branch `feat/intraday-brief-94`. Commit there; do not push or open a pull request.
- Template rule: no employer, client, codebase or people names. Examples use `shop`, `instanceId` and `U1`.
- New prose follows the Writing rules in `CLAUDE.md`.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once). Never read a test result through a pipe: redirect to a file and read the exit code on the next line.
- Bound tools: pytest (`system/tests/python/test_telemetry_core.py`, `test_telemetry_schema.py`), bats (`system/tests/commands.bats`) and the gate (`system/scripts/verify_setup.sh`). Never run two gates at once.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains.
- Commits use `git commit -F .scratch/<file>`.
- The plan edits `.claude/commands/setup.md`: a Work Order session writes it through `.nightshift/protected/claude/commands/setup.md`.
- Every "Find" text below occurs exactly once in its file.

## Review Focus

1. **A later change drops empty filter values.** The shared source would then scan the whole database and repeat every other source's groups. Covered in Task 1: `test_empty_filter_value_selects_rows_without_the_attribute` checks the `== ""` line in the logs and spans KQL, and is shown to fail when empty values are dropped.
2. **The reopen KQL of a shared-services note.** Without the `== ""` line, "reopen" would select rows from every environment. Covered in Task 1 by the same test, which also checks `kql_reopen`.
3. **The linter rejects `""` as a map value.** The source would fail `/lint` and `load_sources` would skip it. Covered in Task 1 by `test_empty_filter_value_lints_clean`.
4. **First-run flood.** A new source looks back 24 hours on its first fetch, so every group it finds is new and the brief's 10-row cap per environment may fill. Not tested; the `/setup` text tells the user to expect it.
5. **Double counting.** `== "U1"` and `== ""` select disjoint rows, so no row is in two sources. Follows from Review Focus 1.

## File Structure

| File | Change |
|---|---|
| `system/tests/python/test_telemetry_core.py` | test: an empty filter value loads and renders in the logs, spans and reopen KQL |
| `system/tests/python/test_telemetry_schema.py` | test: a source with an empty filter value lints clean |
| `system/tests/commands.bats` | test: `/setup` phase 6a offers the shared-services source |
| `.claude/commands/setup.md` | phase 6a step 2 asks about shared services |
| `system/telemetry/example.md` | body text documents the empty-value filter |

---

### Task 1: Pin the empty-value filter

**Files:**
- Test: `system/tests/python/test_telemetry_core.py`, `system/tests/python/test_telemetry_schema.py`
- Temporarily modify, then revert: `system/scripts/vaultlib/telemetry.py` (`_filters`)

**Interfaces:**
- Consumes: `t.load_sources(vault) -> list[Source]`, `t.kql_logs(src, start, end)`, `t.kql_spans(src, start, end)`, `t.kql_reopen(kind, filters, first, last, keys)`, `t._filters(src) -> list[str]`; the `vault` fixture, `helpers.write`, and in the schema test the existing `CODEBASE`, `src()` and `issues()` helpers.
- Produces: two tests that later changes must keep green.

- [ ] **Step 1: Write the tests**

Append to `system/tests/python/test_telemetry_core.py`:

```python
def test_empty_filter_value_selects_rows_without_the_attribute(vault):
    write(vault, "system/codebases/shop.md", '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n')
    write(vault, "system/telemetry/shared.md", '---\ntype: telemetry_source\nname: "shared"\ncodebase: "shop"\nenvironment: "uat"\n'
          'kind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\nadx_filter: {instanceId: ""}\n---\n')
    [src] = t.load_sources(vault)
    assert src.adx_filter == {"instanceId": ""}
    want = '| where tostring(ResourceAttributes["instanceId"]) == ""'
    assert want in t.kql_logs(src, NOW - timedelta(hours=1), NOW).split("\n")
    assert want in t.kql_spans(src, NOW - timedelta(hours=1), NOW).split("\n")
    reopen = t.kql_reopen("log", t._filters(src), "2026-10-05T10:00:00+00:00", "2026-10-05T11:00:00+00:00", {"service": "worker"})
    assert want in reopen.split("\n")
```

Append to `system/tests/python/test_telemetry_schema.py`:

```python
def test_empty_filter_value_lints_clean(vault):
    write(vault, "system/codebases/shop.md", CODEBASE)
    write(vault, "system/telemetry/uat-shared.md", src("uat-shared", kind='"adx"', adx_cluster='"https://example.kusto.windows.net"',
                                                       adx_database='"uat"', adx_filter='{instanceId: ""}'))
    assert [i for i in issues(vault) if i[0].startswith("system/telemetry/")] == []
```

- [ ] **Step 2: Run them; they pass on the current code**

Run: `python3 -m pytest -q system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_schema.py > .scratch/t1.out 2>&1`
Then: `echo $?`
Expected: `0`. Both tests pin behavior that already works.

- [ ] **Step 3: Prove the core test can fail (red before green)**

In `system/scripts/vaultlib/telemetry.py`, find:

```python
    return [f"| where tostring(ResourceAttributes[{_q(k)}]) == {_q(v)}" for k, v in sorted(src.adx_filter.items())]
```

Replace with:

```python
    return [f"| where tostring(ResourceAttributes[{_q(k)}]) == {_q(v)}" for k, v in sorted(src.adx_filter.items()) if v]
```

Run: `python3 -m pytest -q system/tests/python/test_telemetry_core.py > .scratch/t1-red.out 2>&1`
Then: `echo $?`
Expected: `1`; `.scratch/t1-red.out` shows `test_empty_filter_value_selects_rows_without_the_attribute` failing.

Revert with: `git checkout -- system/scripts/vaultlib/telemetry.py`
Then run: `git diff --exit-code system/scripts/vaultlib/telemetry.py`
Expected: exit `0`.

- [ ] **Step 4: Commit**

Write `.scratch/msg-1.txt`:

```text
test(telemetry): pin empty adx_filter values (#94)

A source selects rows that have no value for a resource attribute
with adx_filter: {key: ""}. The tests check that such a source loads,
lints clean and renders the == "" condition in the logs, spans and
reopen KQL, so a later change cannot drop it and turn the source into
a scan of the whole database.
```

Run: `git add system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_schema.py`
Run: `git commit -q -F .scratch/msg-1.txt`

### Task 2: Document the filter and offer it in `/setup`

**Files:**
- Modify: `.claude/commands/setup.md` (phase 6a step 2), `system/telemetry/example.md` (body)
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: the filter behavior pinned in Task 1.
- Produces: the `/setup` text the bats test checks.

- [ ] **Step 1: Write the failing test**

Append to `system/tests/commands.bats`:

```bash

@test "/setup phase 6a offers a shared-services source with an empty filter value (#94)" {
  s=.claude/commands/setup.md
  sec="$(awk '$0 == "## 6a. Telemetry" { on = 1; next } /^## / { on = 0 } on' "$s")"
  [[ "$sec" == *'ask whether some services log without that attribute'* ]]
  [[ "$sec" == *'`<codebase>-<environment>-shared-adx`'* ]]
  [[ "$sec" == *'set to `""`'* ]]
  grep -qF 'An empty filter value' system/telemetry/example.md
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `bats system/tests/commands.bats > .scratch/t2-red.out 2>&1`
Then: `echo $?`
Expected: `1`; `.scratch/t2-red.out` has one `not ok` line, for the new test.

- [ ] **Step 3: Implement**

In `.claude/commands/setup.md`, find:

```text
For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database).
```

Replace with:

```text
For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database). When environments share a database and are told apart by a filter, ask whether some services log without that attribute (shared workers and APIs). On yes, offer one more source, `<codebase>-<environment>-shared-adx`, with that attribute set to `""` (it selects rows where the attribute is missing or empty), the environment the user names for it, and a `rank` just after that environment's source. Say that its groups can include traffic from every environment in the database, and that its first fetch looks back 24 hours, so the next brief may list many new groups.
```

In `system/telemetry/example.md`, find:

```text
A Sentry source sets `kind: "sentry"`, `sentry_url`, `sentry_org` and `sentry_projects` instead of the `adx_*` fields.
```

Replace with:

```text
A Sentry source sets `kind: "sentry"`, `sentry_url`, `sentry_org` and `sentry_projects` instead of the `adx_*` fields. An empty filter value, such as `adx_filter: {instanceId: ""}`, selects rows where that resource attribute is missing or empty: use it for shared services that log without the attribute the other sources filter on.
```

- [ ] **Step 4: Run the tests and the gate**

Run: `bats system/tests/commands.bats > .scratch/t2.out 2>&1`
Then: `echo $?`
Expected: `0`.

Run: `system/scripts/verify_setup.sh > .scratch/gate.out 2>&1`
Then: `echo $?`
Expected: `0`.

- [ ] **Step 5: Commit**

Write `.scratch/msg-2.txt`:

```text
feat(telemetry): offer a source for shared services (#94)

Shared services in a multi-environment ADX database log without the
attribute each source filters on, so no source reported them. /setup
phase 6a now asks about them and offers a <codebase>-<environment>-
shared-adx source with that attribute set to "", and example.md
documents the empty-value filter. The fetch code is unchanged.
```

Run: `git add .claude/commands/setup.md system/telemetry/example.md system/tests/commands.bats`
Run: `git commit -q -F .scratch/msg-2.txt`
