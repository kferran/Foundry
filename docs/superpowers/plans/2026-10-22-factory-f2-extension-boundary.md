# Factory F2: the Extension Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (native, the owner's default for Foundry plans), with superpowers:test-driven-development for every task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Core names no extension tag, route, folder or note type (D3), and extension scripts import core only through `vaultlib/api.py` (D4), with every alert, route, lint and index result unchanged.

**Architecture:** PR 1 moves four alert tags and the telemetry text rule into manifests (`alert_tags` with a new `now_when` key), wires the loader's `importer` field into the inbox, replaces `system/telemetry/` in `NAME_EXCLUDED` with a `system/<extension>/` convention, moves the rca citation filter into telemetry's lint module as `CITED`, and moves the `rca` reserved tag into a `reserved_tag` schema key. PR 2 adds `vaultlib/api.py`, rewrites every extension import onto it and bans everything else with an `ast` test.

**Tech Stack:** Python 3 stdlib (`re`, `ast`, `importlib`), PyYAML through `vaultlib.frontmatter`, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-22-factory-f2-extension-boundary-design.md`

## Global Constraints

- Manifest `contract` stays 1; `FIELDS` keeps accepting `config_keys` (a vault's own manifest still loads).
- New manifest key: `now_when` on an `alert_tags` entry, a regex matched with `.match(line, m.end())` (the text after the tag), exactly as core's `NOW_WHEN`. A bad regex is a reason from `extensions.py check` and the tag falls back to its `severity`; the extension still loads.
- `importer: {type: <note type>}`: an inbox `.md` whose frontmatter `type` matches moves to `raw/<extension name>/`, after the duplicate check and before `held()`, and is not a run. Read from **present** extensions (`extensions/*/extension.md` that loads, listed or not). An `importer` without a `type` string is a reason; the extension still loads.
- `system/<name>/` of each present extension is walked and indexed, never resolved by bare `[[name]]`.
- Telemetry lint module: `CITED = {"rca": ["draft", "approved"]}`; core's live `citation_issues` reads `CITED` from each present lint module. A cited note with no `status` counts as open.
- Schema key `reserved_tag: true`: the tag named like the schema is written only on notes of that type. Core keeps `now` (a path rule).
- Precedence: a manifest severity for a core tag is ignored; `incident`, `rca`, `handoffs`, `telemetry` are no longer core tags.
- `alert.py` accepts core tags plus every enabled manifest's tags, bare ones included; an unknown tag exits 2 with usage.
- Core-clean pattern 2: `handoffs|intraday|telemetry|production_error|\brca\b|\bincident\b` over `system/scripts`, `system/schemas`, `system/systemd`, `system/hooks`, `.githooks`; hits in `core_clean.allow`, one `file:term` line each.
- `config_keys` stated once, in `schemas/config.md`; the three template manifests and the demo fixture drop it.
- PR 2: `vaultlib/api.py` exports what extension scripts import today, in the form they import it, plus `schema` and `yamlload`; the ban test skips when `system/config.md` exists.
- Template stays generic; core line count is printed, not capped (report it).
- Keep `intake.py` edits to the production-error branch only (sibling meetings work rebases on it).

## Review Focus

1. An unreadable or non-UTF-8 manifest in `extensions/`: the inbox, the index and the publish gate must keep running (the importer and `name_excluded` skip it). Test: Task 3 seeds a `\xff` manifest and runs the intake.
2. A `now_when` regex that does not compile must not stop notify or `away.py`: the tag falls back to its severity. Test: Task 2.
3. Telemetry present but not listed in `extensions:`: a `production_error` inbox note still routes, `[incident]` waits for the brief, `alert.py rca x` exits 2. Tests: Tasks 2 and 3.
4. A vault's own manifest that still has `config_keys` keeps loading. Test: Task 6 keeps the loader accepting it.
5. An extension whose name collides with a core `system/` folder (`schemas`, `logs`) must not change indexing of that folder beyond bare-name resolution. Covered by `name_excluded` returning only a name-exclusion prefix; no new test.

---

## PR 1: D3, names out of core (branch `feat/factory-f2-boundary`)

### Task 1: The core-clean test learns the extension words

**Files:** Modify `system/tests/vault_integrity.bats` ("core names no vendor or customer"), `system/tests/core_clean.allow`.

- [ ] Step 1: Add the second pattern, over code only, appended to the same `$want` file (same `awk` shaping, same `diff` against the allowlist).
- [ ] Step 2: Run `system/scripts/test.sh system/tests/vault_integrity.bats -f "core names"`; expect FAIL listing today's hits.
- [ ] Step 3: Add every hit to `core_clean.allow` with a comment block: the keepers of spec §3.2 with reasons, and the lines in `alerts.py`, `intake.py`, `index.py`, `schema.py` marked "leaves with F2 PR 1".
- [ ] Step 4: Run again; expect PASS. Commit.

### Task 2: Alert tags leave core

**Files:** Modify `system/scripts/vaultlib/alerts.py`, `system/scripts/alert.py`, `system/scripts/vaultlib/extensions.py` (`check`), `extensions/telemetry/extension.md`, `system/tests/python/test_alerts.py`, `system/tests/python/test_extensions.py`, `extensions/telemetry/tests/python/test_telemetry_run.py`, `extensions/handoffs/tests/` (one test), `core_clean.allow`.

**Interfaces:** Produces `alerts.extension_tags(vault) -> {tag: severity | (severity, re.Pattern)}` covering every enabled manifest tag (bare and invalid-severity entries as `"brief"`); `alerts.severity(line, extra)` unchanged in signature; `extensions.check(vault)` adds non-fatal field reasons.

- [ ] Step 1: Tests first. Move the `incident`, `rca`, `handoffs`, `telemetry` parametrize rows and the four `[telemetry]` text rows out of `test_alerts.py` into `test_telemetry_run.py` (and one `handoffs` row into the handoffs suite), each calling `severity(line, alerts.extension_tags(v))` with telemetry and handoffs enabled. Make `test_telemetry_run.py:625` pass `extension_tags(v)`. Add: with telemetry present and not listed, `[incident] x` is `brief` and `alert.py rca x` exits 2; a `now_when: '('` is a reason from `check` and the tag takes its severity; `extension_tags` returns `{"plain": "brief", "watch": "now", "odd": "brief"}` for the existing fixture. Add a core test: `alerts.TAGS` holds none of the four.
- [ ] Step 2: Run the touched suites; expect FAIL.
- [ ] Step 3: Remove the four tags and `NOW_WHEN["telemetry"]` from `alerts.py` (reword the comment); `extension_tags` compiles `now_when`; `severity` checks core `NOW_WHEN`, then core `TAGS`, then `extra` (a tuple value matches its pattern at `m.end()`, else its severity). `alert.py` validates against `set(TAGS) | set(extension_tags(VAULT))`. `check` appends `"<name>: alert tag <tag>: now_when is not a valid regex (<err>)"`. Telemetry manifest: block-style `alert_tags` with `{tag: telemetry, severity: brief, now_when: '<today's regex>'}`, `{tag: incident, severity: now}`, `{tag: rca, severity: now}`, `{tag: telemetry_source, severity: now}`.
- [ ] Step 4: Run `test_alerts.py`, `test_extensions.py`, the telemetry and handoffs suites, `scripts.bats` (registry test), `intraday.bats`; expect PASS. Drop the `alerts.py` allowlist lines. Commit.

### Task 3: The production-error route becomes an importer

**Files:** Modify `system/scripts/vaultlib/extensions.py` (`present`, `importer_for`, `check`), `system/scripts/vaultlib/intake.py` (the one branch), `extensions/telemetry/extension.md`, `system/tests/fixtures/extensions/demo/extension.md`, `system/tests/python/test_intake.py`, `system/tests/python/test_extensions.py`, `core_clean.allow`.

**Interfaces:** Produces `extensions.present(vault) -> [(name, data)]` (every `extensions/*/extension.md` that loads, sorted, unreadable ones skipped) and `extensions.importer_for(vault, ntype) -> str | None`.

- [ ] Step 1: Tests first. Rewrite `test_production_error_routed_to_telemetry` and `test_usage_ceiling_holds_only_sessions_so_telemetry_notes_still_route` on the demo fixture (`importer: {type: demo_drop}` → `raw/demo/`, not listed in `extensions:`), keeping the second as the proof that routing runs before `held()`. Add: a non-UTF-8 manifest beside it does not stop the intake; a telemetry-suite test that a `production_error` drop lands in `raw/telemetry/`; `check` reports `"<name>: importer needs a type string"` for `importer: {}`.
- [ ] Step 2: Run; expect FAIL.
- [ ] Step 3: Implement; telemetry manifest gains `importer: {type: production_error}`; `intake.py` asks `importer_for` and renames into `raw/<name>/`.
- [ ] Step 4: Run `test_intake.py`, `test_extensions.py`, telemetry suite; expect PASS. Drop the `intake.py` allowlist lines. Commit.

### Task 4: Index rules: extension config folders and citations

**Files:** Modify `system/scripts/vaultlib/index.py`, `publish.py`, `evals.py`, `cli.py`, `extensions/telemetry/scripts/telemetrylib/lint.py`, `system/tests/python/test_index_rules.py` (or `test_cli.py`), `core_clean.allow`.

**Interfaces:** Produces `index.name_excluded(vault) -> tuple`, `index.lint_modules(vault) -> [(name, rel, module | Exception)]`, `index.citation_issues(conn, cited: dict)`, `index.cited(vault) -> {type: [statuses]}`.

- [ ] Step 1: Tests first: a `system/demo/x.md` note is not resolved by `[[x]]` while `extensions/demo/` is present; the existing citation tests pass with telemetry present (copy `extensions/telemetry` into the test vault) and give no rca row with it absent; `citation_issues` with `cited={}` still checks codebase notes.
- [ ] Step 2: Run; expect FAIL.
- [ ] Step 3: Implement; `_extension_issues` reuses `lint_modules`; `cli.cmd_issues` passes `cited(vault)`. Reword comments.
- [ ] Step 4: Run `test_index*.py`, `test_cli.py`, `test_publish.py`, `test_eval_check.py`, telemetry suite; expect PASS. Drop the `index.py` lines. Commit.

### Task 5: The reserved tag becomes a schema key

**Files:** Modify `system/scripts/vaultlib/schema.py` (`Schema.reserved_tag`, `reserved_tags(schemas)`, `tag_issues(..., schemas)`), `index.py:303`, `publish.py:380`, `cli.py:387`, `system/schemas/schema.md`, `extensions/telemetry/schemas/rca.md`, new fixture schema `system/tests/fixtures/extensions/demo/schemas/memo.md`, `test_cli.py`, `core_clean.allow`.

- [ ] Step 1: Tests first: rewrite `test_system_tags_warn_off_their_notes` on the demo `memo` schema (`reserved_tag: "true"`, a `tags` field): tag `memo` on a concept warns, on a memo note does not, `now` keeps its path rule; a telemetry-suite test that tag `rca` on a concept warns and on an rca note does not; `tags` omits a reserved tag.
- [ ] Step 2: Run; expect FAIL.
- [ ] Step 3: Implement; the message for a schema tag reads `written only on <type> notes`.
- [ ] Step 4: Run `test_schema*.py`, `test_cli.py`, `test_publish.py`, telemetry suite; expect PASS. Drop the `schema.py` lines. Commit.

### Task 6: `config_keys` stated once, docs, measurement

**Files:** Modify the three manifests, the demo fixture manifest, `.claude/commands/setup.md`, `FOUNDRY.md` (D3 row, the manifest sentence), `test_extensions.py`.

- [ ] Step 1: Test first: no template manifest under `extensions/` or the fixture has `config_keys`; a manifest with `config_keys` still loads. Run; expect FAIL.
- [ ] Step 2: Remove the keys; `/setup` says "write the keys its `schemas/config.md` lists"; FOUNDRY.md documents `now_when`, `importer`, `system/<name>/`, `CITED`, `reserved_tag` in one sentence each and marks D3 fixed (keep `| D3 |`).
- [ ] Step 3: Run the full gate (`verify_setup.sh`, sandbox off) and every extension suite; print the core line count. Commit; review; PR.

---

## PR 2: D4, the extension API (branch `feat/factory-f2-api`, built on PR 1)

Measured at master `4449573` (all seven F1 retrofits merged), `ast` over every tracked `extensions/**/*.py` outside `tests/`:

| Form | Exports |
|---|---|
| Modules | `frontmatter`, `now`, `cli`, `triage`, plus kept `schema`, `yamlload` |
| Names | `briefings.cut`, `connector.Fail`, `connector.check_stream`, `connector.strip_cursor`, `connector.text_json`, `connector.walk`, `intake.Intake`, `meetings.open_actions`, `meetings.owner_names`, `notify.prefix`, `notify.thread_state`, `redact.redact_credentials`, `state.append`, `state.load`, `state.records`, `state.save`, `stream.blocks`, `stream.messages`, `triage.config`, `triage.one_line`, `triage.reply`, `cli.UsageError`, `cli.set_scalar` |

### Task 7: `vaultlib/api.py` and the ban

**Files:** Create `system/scripts/vaultlib/api.py`, `system/tests/python/test_extension_api.py`. Modify every extension script above, `system/tests/conformance.bats` (delete the `private-import` rule and the two extension `config` lines), `FOUNDRY.md` (D4 row).

- [ ] Step 1: Write the ban test (skips when `system/config.md` exists): the four cases of spec §3.3, plus an unused `__all__` entry not on the keep list (`schema`, `yamlload`). Seed each case in a temp tree and assert it fails (the seeded-failure proofs). Run on the real tree; expect FAIL (no `api.py`, direct imports).
- [ ] Step 2: Create `api.py` with `__all__`; rewrite each import to `from vaultlib.api import …`; retire `jira_handoffs.config` and `telemetrylib/rca.config` onto the exported `config` (`triage.config(vault)`, identical body).
- [ ] Step 3: Run the ban test, every extension suite, `conformance.bats`; expect PASS. Full gate. Commit; review; PR ("builds on PR 1").
