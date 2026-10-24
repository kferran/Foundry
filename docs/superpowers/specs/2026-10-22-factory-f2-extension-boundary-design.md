# F2: the extension boundary

**Date:** 2026-10-22
**Status:** approved and built (#350, #352; #307 closed)
**Program:** docs/superpowers/2026-10-21-factory-plan.md (phase F2)
**Grill:** 2026-10-21, recorded in the program plan's `## Grill` section (the factory is the owner's idea).
**Builder check:** 2026-10-22, two questions, settled in §3.5 (the seven `def config(` copies; whole-module versus named exports); the spec passes the pipeline test.
**Blueprint:** none: the boundary between core and extensions
**Lane:** feature (alerts, intake routing: the owner merges)

## 1. Why

Two departures in FOUNDRY.md Architecture break principle P9 (features plug in through their manifest). **D3:** core names extension features: `alerts.py` hard-codes the `incident`, `rca`, `handoffs` and `telemetry` tags and a telemetry text rule, `intake.py:357` routes `production_error`, `index.py:26` and `:69-80` know telemetry folders and rca notes, `schema.py:19` reserves the `rca` tag. **D4:** extensions import whatever they like from `vaultlib`, private names included (`_structured`, `_text_json`), and F0's ratchet sees only single-line `from … import` of a `_` name. Each extension also states its config keys twice, and the copies have drifted (`handoffs_site` is in the handoffs schema, missing from its manifest).

The grill cut F2 to these two fixes. The core manifest (units, smoke rows and core tags read from a manifest) waits until a ratchet shows those blocks drifting.

## 2. Goals and non-goals

- **Goals:** no extension tag, route, folder or note type named in core code; one module, `vaultlib/api.py`, that extension scripts import from, with a test that holds it; config keys stated once; every behaviour kept as it is today, with each extension on and off.
- **Non-goals:** a core manifest; merging the five core `def config(` readers (they stay on F0's ratchet list until F3; §3.5); the prose that describes extensions (FOUNDRY.md, CLAUDE.md, commands, Workcell files); F3's conformance rules.
- **Anti-goals:** a manifest `contract` bump (the loader refuses any other contract, which would take a live vault's own extension offline at its next update); a new manifest field where an existing one or a convention works.

## 3. Decisions

### 3.1 What leaves core, and where it goes

The loader (`vaultlib/extensions.py` `FIELDS`) already accepts `alert_tags`, `importer` and `lint`. `importer` is accepted and read by nothing. New: one key on an `alert_tags` entry, one optional attribute of a `lint` module, one schema key and one folder convention.

| Today in core | Moves to | Field |
|---|---|---|
| `alerts.TAGS`: `incident` now, `rca` now | telemetry `alert_tags`: `{tag: incident, severity: now}`, `{tag: rca, severity: now}` | `alert_tags` (exists) |
| `alerts.TAGS`: `handoffs`, `telemetry` (brief) | the bare tags both manifests already list | `alert_tags` (exists) |
| `alerts.NOW_WHEN["telemetry"]` (a credential-shape line goes to Slack now) | telemetry `{tag: telemetry, severity: brief, now_when: "<today's regex>"}` | **new key `now_when`:** the line is `now` when the regex matches the text after the tag, else its `severity` |
| `intake.py:357`: an inbox note with `type: production_error` moves to `raw/telemetry/` | telemetry `importer: {type: production_error}` | `importer` (exists, given its shape): an inbox `.md` whose frontmatter `type` matches moves to `raw/<extension name>/` |
| `index.py:26`: `system/telemetry/` in `NAME_EXCLUDED` | convention: `system/<name>/` of each present extension holds its config notes, walked and indexed, never resolved by bare name | none. `NAME_EXCLUDED` becomes a `name_excluded(vault)` reader at its three `Resolver` callers (`index.py`, `publish.py`, `evals.py`) |
| `index.py:69-80`: open rca notes' `file:NN` citations | telemetry's lint module: `CITED = {"rca": ["draft", "approved"]}`; core's `citation_issues` reads `CITED` from each present extension's lint module | `lint` (exists), one optional attribute |
| `schema.py:19` and `:304`: tag `rca` only on rca notes | `reserved_tag: true` in `extensions/telemetry/schemas/rca.md`; core keeps `now` (a path rule) | **new schema key**, read by `tag_issues` (index and publish gate) and `cli.py:387` |

Settled with each move:
- **The importer runs where the branch is today:** after the duplicate check, before `held()`, and a routed file is not a run. It reads **present** extensions, like schemas and lint, so a `production_error` never reaches a compile while telemetry is off, as today. The target folder comes from the extension's name, never from the manifest, so no path needs confining. *Builder's call:* one `type` per importer; a list waits for a second user.
- **Citations stay uncached.** The `lint` hook's `issues(conn, add)` runs inside the index build and its rows are stored; citations are read at `issues` time because the code moves on its own. So the rca rule moves as data (`CITED`) that core's live check reads, not into `issues()`.
- **`alert.py` accepts extension tags.** It validates against `TAGS` today, and the RCA skill runs `alert.py rca "HOTFIX candidate: …"`. It accepts core tags plus every enabled manifest's tags, bare ones included. With telemetry off, `alert.py rca` exits 2 with usage, and the skill is not linked then.
- **Precedence flips for these four only.** A manifest severity for a core tag is still ignored; the four moved tags are no longer core tags, so the manifest decides.
- **`config_keys` is stated once, in `schemas/config.md`** (validation already reads it from there). The three template manifests and the test fixture drop `config_keys`; `FIELDS` keeps accepting it so a vault's own manifest still loads; `/setup` says "write the keys its `schemas/config.md` lists".

### 3.2 The core-clean test learns the words

`vault_integrity.bats` "core names no vendor or customer" gains a second pattern, `handoffs|intraday|telemetry|production_error|\brca\b|\bincident\b`, over code only: `system/scripts`, `system/schemas`, `system/systemd`, `system/hooks`, `.githooks`. Hits go into the same `core_clean.allow`, one `file:term` line each. After this PR, `alerts.py`, `intake.py`, `index.py` and `schema.py` have none, so a word coming back there fails. Today's other code hits stay listed, each with its reason: `vaultlib/extensions.py` (the one-time migration table; the test's excluded file is the CLI, `system/scripts/extensions.py`), `quarantine.py` (`telemetry_state` backups), `redact.py` (a docstring), `triage.py` (a comment), `nightshift_session.py` (prompt text "never now or rca"), `schemas/concept.md` (the `telemetry` Workcell capability), `schemas/config.md` (the notify prose naming the intraday capture channel), the smoke unit comment, `.githooks/pre-commit` (`raw/telemetry/`).

### 3.3 The extension API

**Rule:** `vaultlib/api.py` re-exports exactly what extension scripts import today, in the form they import it (a module imported whole stays whole, a name stays a name), plus `connector` and `state` (F1) and the modules a vault's own extension uses (`frontmatter`, `schema`, `yamlload`). The F1 retrofits are landing in parallel and change this list; the build measures it with an import parser at its base. At master `c92253f` the measurement is:

| Form | Exports |
|---|---|
| Modules | `frontmatter`, `now`, `cli`, `connector`, `state`, `schema`, `yamlload` |
| Names | `stream.blocks`, `stream.messages`, `briefings.cut`, `intake.Intake`, `meetings.open_actions`, `meetings.owner_names`, `notify.prefix`, `notify.thread_state`, `redact.redact_credentials`, `triage.config`, `triage.hold`, `triage.one_line`, `triage.reply` |
| Leaving with F1 retrofit 3 | `triage.Fail`, `triage._structured`, `triage._text_json` (become `connector.Fail`, `structured`, `text_json`) |

`now` is used for far more than `add` (read, write, open_lines, parse, fields, note, is_date, archived, `PARTITIONS`, `LINE`, `STAMP`), so it is exported whole. Every extension script switches to `from vaultlib.api import …`.

**The ban** (`system/tests/python/test_extension_api.py`; it skips when `system/config.md` exists, like its neighbours, so a vault's own extension never fails that vault's gate). It parses every tracked `.py` under `extensions/` outside `tests/` (scripts, brief and debrief sections, skills) with `ast` and fails on:
1. `import vaultlib`, `import vaultlib.<x>` or `from vaultlib[.<x>] import …` for any module but `vaultlib.api`, whatever the line layout (multi-line parenthesised imports included);
2. a name imported from `vaultlib.api` that is not in its `__all__`;
3. a `_`-prefixed attribute read on a name bound from `vaultlib.api` (`now._x`), the attribute form F0's grep cannot see;
4. a `vaultlib.<x>` string other than `vaultlib.api` in any of those files, Python or not (inline `python3 -c`, `importlib`).

It also fails on an `__all__` entry no template extension script uses, unless the test's keep list names it (`schema`, `yamlload`: a vault's own extension), so the API shrinks when its last user goes. F0's `private-import` rule and its allowlist entries in `conformance.bats` are deleted in the same PR.

**Extension tests are outside the ban.** They pin an extension against core behaviour (`alerts.severity`, `index.Index`, `notify.collect`, `intake.RAW_NAME`, `schema.validate_note`) and run in this repository's CI, where a core change that breaks one fails the gate. Exporting those for tests would widen the API for no script.

### 3.4 Vault-only extensions keep working

Nothing is removed from `vaultlib`, the contract stays 1, `config_keys` still loads, and the ban skips in a vault. A vault's own extension that imports `frontmatter`, `schema` or `yamlload` from `vaultlib` runs as before and can move to `vaultlib.api` when its owner chooses.

## 4. Pull requests (each the owner merges)

1. **D3: names out of core.** §3.1 and §3.2: `alerts.py`, `alert.py`, `intake.py`, `index.py`, `schema.py`, `cli.py`, the three manifests and the fixture, the telemetry lint module and rca schema, `/setup`'s line, the core-clean pattern and allowlist, FOUNDRY.md's D3 row and manifest docs. No dependency on F1; the overlap is small (retrofit 7 also edits `telemetrylib/rca.py` and `test_telemetry_run.py`), so whichever merges second rebases. Live acceptance after the server updates: `extensions.py check` prints nothing; `telemetry_fetch.py --check <source>` and `jira_fetch.sh --check` pass; `vault_index.py issues` gives the same citation and `tag-reserved` rows as before the update; the 24 h audit finds `[incident]`, `[rca]` and `[telemetry_source]` lines sent to Slack at once as before (or none raised) and no usage error from `alert.py`.
2. **D4: the extension API.** §3.3: `vaultlib/api.py`, the import rewrites in every extension script, the ban test, F0's private-import rule removed, FOUNDRY.md's D4 row. Built after F1's last extension retrofit (the RCA filer) merges, since retrofits 3, 6 and 7 add `connector` and `state` imports and a ban landing first breaks their rebases. Live acceptance: each extension's `--check` and its next tick, with no import error in the 24 h audit.

Core lines: PR 1 removes about as much as it adds; PR 2 adds `api.py`. Each PR prints its measured count.

## 5. Tests

- **Behaviour kept, with the extension on:** the four `test_alerts.py` rows for the moved tags and its four `[telemetry]` text rows (two credential-shape lines `now`, two others `brief`) move to the telemetry and handoffs suites and pass `extension_tags(vault)`, as `test_telemetry_run.py:627` must too (it calls `severity` with none today).
- **With it off:** a `[incident]` line waits for the brief; `alert.py rca x` exits 2; an inbox `production_error` still routes while telemetry is present but not enabled.
- **Loader:** `now_when` that is not a valid regex is a reason from `extensions.py check`, and the tag falls back to its `severity`; an `importer` without a `type` string is a reason.
- **Index:** a `system/<ext>/` note is not resolved by `[[name]]`; an open rca note citing a missing file gives the same `citation` row, read live; tag `rca` on a concept note warns, on an rca note does not.
- **Fixture:** the demo extension gains an `importer` and a `reserved_tag` schema, so each rule is proved on an extension that is not telemetry.
- **Seeded failures:** each of the ban's four cases, and the core-clean test on an extension word added to `alerts.py`, fail before they pass.
- **Gate:** CI with every extension off and every extension on.

### 3.5 Settled by the builder check
- **`def config(` copies.** There are seven, not three: five in core (`triage.py`, `notify.py`, `nightshift_check.py`, `alert.py:22`, `commit_runs.py:29`) and two in extensions (`jira_handoffs.py:40`, `telemetrylib/rca.py:28`). PR 2 retires the two extension copies onto the API's config reader and removes their ratchet lines (F1 §6 handed them to F2's API). The five core copies stay on F0's list; F3 (#308) folds them into one core reader, since F3 turns the ratchet into a rule.
- **Whole module or names.** When scripts import a module both whole and by name, `api.py` exports the module whole (its names stay reachable as attributes) and also any name imported directly, so every existing import form still resolves through `vaultlib.api`. The import parser counts a whole-module import as using the module; the unused-export check treats a module export as used when any script imports it in either form.

## 6. Left to the builder

The internal shape of `extension_tags()` once it carries `now_when`; how the reserved-tag set reaches `tag_issues`; the exact allowlist lines; whether the ban runs as pytest or from `conformance.bats`.

## 7. Out of scope

The core manifest; the five core `def config(` copies (F0's list, F3's rule; §3.5); a shared Atlassian tool table in the API (F1 §7 named the API as its home if one is wanted; nothing needs it yet); the allowlisted words in §3.2; F3's "config keys match the schema" rule, which is moot once keys are stated once.

## 8. Risks

1. **An unreadable manifest delays urgent alerts.** The loader drops an extension whose manifest does not load, and with it that extension's tags, so `[incident]`, `[rca]` and credential-shape lines would wait for the brief instead of going to Slack at once. Today they are hard-coded. The daily `[extensions]` alert names the broken manifest; accepted.
2. **The import list moves under the build.** F1 retrofits change it while F2 is specified; PR 2 measures at its base, and the unused-export check catches a stale entry.
3. **The ban reads literal code.** A module name computed at run time (`importlib.import_module(name)`) passes; no extension does this today.
4. **One template update carries both sides.** `extensions/` and core update together, so a vault never runs new core with old manifests; a vault that edited a template manifest gets a merge conflict, and the update aborts on conflict.
