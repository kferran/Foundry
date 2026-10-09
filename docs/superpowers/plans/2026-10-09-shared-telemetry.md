# Shared-Services Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owners can cover shared services that log without the instance attribute, because an empty ADX filter value is documented and pinned by tests (#94 A).

**Architecture:** No code change. `vaultlib/telemetry._filters` already renders `tostring(ResourceAttributes["<key>"]) == ""` for an empty value, and `tostring()` of a missing attribute is `""`. This plan documents that in the example source, the README and `/setup` phase 6a, and pins it with tests: load, lint, and the logs, spans and reopen KQL.

**Tech Stack:** Python 3, pytest, bats 1.8.2.

**Spec:** `docs/superpowers/specs/2026-10-09-shared-telemetry-design.md`

## Global Constraints

- Work on branch `feat/shared-telemetry`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Template rule: no machine, employer or people names.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once), outside a sandbox. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_telemetry_core.py`, `test_telemetry_schema.py`), bats (`commands.bats`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- **The pytest tests pass before any change.** They pin behavior that already works; only the bats documentation test fails first.
- **An instance source and an empty-filter source on the same database:** no row matches both, so a group is never counted twice. The README says so.

---

### Task 1: Document and pin the empty filter value

**Files:**
- Modify: `system/telemetry/example.md`, `README.md`, `.claude/commands/setup.md`
- Test: `system/tests/python/test_telemetry_core.py`, `system/tests/python/test_telemetry_schema.py`, `system/tests/commands.bats`

**Interfaces:** none new.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/python/test_telemetry_core.py`. Find:

````text
    assert "aggregate-only" not in readme and "no message text, titles or attribute values" not in readme
````

Replace with:

````text
    assert "aggregate-only" not in readme and "no message text, titles or attribute values" not in readme


def test_an_empty_filter_value_selects_rows_without_the_attribute(vault):
    """#94 A: shared services log without the instance attribute; tostring() of a missing attribute is ""."""
    write(vault, "system/codebases/shop.md", '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n')
    write(vault, "system/telemetry/shared.md", '---\ntype: telemetry_source\nname: "shared"\ncodebase: "shop"\nenvironment: "prod"\n'
          'kind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\nadx_filter: {instanceId: ""}\n---\n')
    src = t.load_sources(vault)[0]
    assert src.adx_filter == {"instanceId": ""}
    want = '| where tostring(ResourceAttributes["instanceId"]) == ""'
    assert want in t.kql_logs(src, NOW - timedelta(hours=1), NOW).splitlines()
    assert want in t.kql_spans(src, NOW - timedelta(hours=1), NOW).splitlines()
    reopen = t.kql_reopen("log", t._filters(src), "2026-10-05T10:00:00Z", "2026-10-05T11:00:00Z", {"service": "api"})
    assert want in reopen.splitlines()
````


Edit 1 in `system/tests/python/test_telemetry_schema.py`. Find:

````text
    assert not [r for r in rows if r[0] in ("unknown-field", "schema")], rows
    assert [i for i in issues(vault) if i[0].startswith("raw/telemetry/")] == []
````

Replace with:

````text
    assert not [r for r in rows if r[0] in ("unknown-field", "schema")], rows
    assert [i for i in issues(vault) if i[0].startswith("raw/telemetry/")] == []


def test_an_empty_adx_filter_value_lints_clean(vault):
    write(vault, "system/codebases/shop.md", CODEBASE)
    write(vault, "system/telemetry/prod-shared.md", src("prod-shared", kind='"adx"', adx_cluster='"https://example.kusto.windows.net"',
                                                        adx_database='"prod"', adx_filter='{instanceId: ""}'))
    assert [i for i in issues(vault) if i[0].startswith("system/telemetry/")] == []
````


Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'skip phases 3, 6, 6a and 9' ".claude/commands/setup.md"
}

````

Replace with:

````text
  grep -qF 'skip phases 3, 6, 6a and 9' ".claude/commands/setup.md"
}

@test "an empty ADX filter value for shared services is documented (#94 A)" {
  sec="$(sed -n '/^## 6a\. Telemetry/,/^## 7\./p' ".claude/commands/setup.md")"
  [[ "$sec" == *'A filter value of `""` selects the rows that lack the attribute'* ]]
  grep -qF 'An empty filter value (`adx_filter: {instanceId: ""}`) selects the rows that lack that attribute' README.md
  grep -qF 'An empty value, `{instanceId: ""}`, selects the rows that lack the attribute' system/telemetry/example.md
}

````


- [ ] **Step 2: Run them to verify the documentation test fails**

Run: `python3 -m pytest -q system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_schema.py`
Expected: PASS (the behavior already works; these tests pin it).

Run: `bats system/tests/commands.bats`
Expected: FAIL, 1 `not ok` (the documentation test).

- [ ] **Step 3: Implement**

Edit 1 in `system/telemetry/example.md`. Find:

````text
An example ADX source. `/setup` phase 6a writes real ones next to it (gitignored). A Sentry source sets `kind: "sentry"`, `sentry_url`, `sentry_org` and `sentry_projects` instead of the `adx_*` fields.
````

Replace with:

````text
An example ADX source. `/setup` phase 6a writes real ones next to it (gitignored). A Sentry source sets `kind: "sentry"`, `sentry_url`, `sentry_org` and `sentry_projects` instead of the `adx_*` fields.

`adx_filter` selects rows by resource attribute, for example `{instanceId: "U1"}`. An empty value, `{instanceId: ""}`, selects the rows that lack the attribute: shared services that log without it. Give them a second source on the same database.
````


Edit 1 in `README.md`. Find:

````text
**Error telemetry.** `foundry-telemetry.timer` runs `telemetry_fetch.py` every hour, and `brief_prep.sh` runs it once more before the brief. Each source in `system/telemetry/<name>.md` (written by `/setup` phase 6a, gitignored) is a set of Sentry projects or one Azure Data Explorer database with a filter. Each error group becomes one `production_error` note in `raw/telemetry/` holding group keys, counts, times, opaque IDs, links and the Sentry issue title or one sample log message, ticket identifiers included; credentials and emails are masked. Sentry needs a read-only token in `~/.config/foundry/sentry.token` (mode 0600); ADX uses your `az login`. `--check <name>` tests a source, `--dry-run` prints the groups without writing.
````

Replace with:

````text
**Error telemetry.** `foundry-telemetry.timer` runs `telemetry_fetch.py` every hour, and `brief_prep.sh` runs it once more before the brief. Each source in `system/telemetry/<name>.md` (written by `/setup` phase 6a, gitignored) is a set of Sentry projects or one Azure Data Explorer database with a filter. An empty filter value (`adx_filter: {instanceId: ""}`) selects the rows that lack that attribute, so shared services that log without it get a source of their own; an instance filter and an empty filter never select the same row. Each error group becomes one `production_error` note in `raw/telemetry/` holding group keys, counts, times, opaque IDs, links and the Sentry issue title or one sample log message, ticket identifiers included; credentials and emails are masked. Sentry needs a read-only token in `~/.config/foundry/sentry.token` (mode 0600); ADX uses your `az login`. `--check <name>` tests a source, `--dry-run` prints the groups without writing.
````


Edit 1 in `.claude/commands/setup.md`. Find:

````text
2. For each registered codebase, ask whether it reports errors to Sentry, ADX, both or neither. For Sentry: the API base URL (for example `https://us.sentry.io`), the organization slug, and the project slugs per environment. For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database). Ask for a `rank` per environment (lower is listed first in the brief). Ask whether an ADX source `covers` its Sentry source only after the user confirms the codebase's Sentry SDK continues the OpenTelemetry traces (shares trace IDs with ADX); otherwise leave `covers` unset.
````

Replace with:

````text
2. For each registered codebase, ask whether it reports errors to Sentry, ADX, both or neither. For Sentry: the API base URL (for example `https://us.sentry.io`), the organization slug, and the project slugs per environment. For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database). A filter value of `""` selects the rows that lack the attribute: offer that as a separate source when shared services log without it. Ask for a `rank` per environment (lower is listed first in the brief). Ask whether an ADX source `covers` its Sentry source only after the user confirms the codebase's Sentry SDK continues the OpenTelemetry traces (shares trace IDs with ADX); otherwise leave `covers` unset.
````


- [ ] **Step 4: Run the tests and the gate**

Run: the commands from Step 2.
Expected: PASS, no failures and no `not ok`.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
docs(telemetry): an empty ADX filter value covers shared services (#94 A)

tostring() of a missing resource attribute is "", so adx_filter: {instanceId: ""}
already selects the rows that lack it. Document it in the example source, the
README and /setup phase 6a, and pin it with tests (load, lint, logs, spans and
reopen KQL).
```

Run: `git add system/telemetry/example.md README.md .claude/commands/setup.md system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_schema.py system/tests/commands.bats`

Run: `git commit -q -F .scratch/msg-1.txt`
