# Extensions: vendor features out of core, into tracked extension folders

**Date:** 2026-10-15
**Status:** Approved (owner, 2026-10-15), with the review decisions in §6. Scope narrowed (owner, 2026-10-16, §7): only the vendor-specific features move. Home changed (owner, 2026-10-16, §8): extensions are tracked folders in the template, with no separate repository. The loader (#226) and the Jira handoffs move (#232) are merged; telemetry with RCA moves next (§9), and DTCC moves into the owner's vault.
**Plan:** phase 4 of `docs/superpowers/2026-10-15-next-phase-plan.md`; simplification step 3 of `2026-10-11-simplification-review.md` §4. Overlaps #62 (closed out below).

## 1. Facts (master after #209)

| | Lines |
|---|---|
| `system/scripts/**` (sh, py) | 13,858 |
| Commands, skills, schemas, units | 1,568 |
| Tests (bats and pytest) | 19,077 |

There are 19 schemas.

| Feature | Code | Tests | Schemas | Units | Claude-facing | Config keys |
|---|---|---|---|---|---|---|
| Jira handoffs | 231 | 235 | none | none (runs in `brief_prep.sh`) | none | `handoffs_site`, `handoffs_projects` |
| DTCC watcher | 811 | 540 | `dtcc_change` | dtcc-watch | skill `dtcc-watch` | none (on when `system/dtcc/map.yaml` exists) |
| Telemetry and RCA | 1,355 (with `http.py`) | 1,628 | `production_error`, `telemetry_source`, `rca` | telemetry | command `/rca` | `rca_*` |
| Meetings | 1,063, plus 256 in `vaultlib/intake.py` | 1,673 | `meeting`, `meeting_input`, `meeting_transcript` | meetings | none | `meetings_enabled`, `meetings_partition`, `owner_names` |
| Inbox triage | 401 | 280 | none | triage | none | `triage_*` |
| Slack notices | 493 | 438 | none | notify | none | `slack_*`, `notify_links` |
| Two-machine sync | 292 | 991 | none | sync, plus the sync drop-ins | none | `machine_role`, `sync_interval_minutes` |
| Work Orders (stay in core) | 1,770 | 2,069 | `nightshift_item` | nightshift | skill `order` | `orders_enabled` and others |

Core special-cases these features in about 20 shared files:
- `install_units.sh`, `brief_prep.sh`, `debrief_prep.sh`, `lib_prep.sh`, `smoke_check.sh`
- `vaultlib/index.py`, `intake.py`, `sources.py`, `quarantine.py`, `publish.py`, `commit_runs.py`
- `check_deps.sh`, `run_headless.sh`
- `.claude/settings.json`
- `brief.md`, `debrief.md`, `setup.md`
- `FOUNDRY.md`, `CLAUDE.md`

Owner-specific names in core include `dtcc.com`, `atlassian.net` and `sentry.io`, the Sentry and ADX lint rules in `index.py`, and Gemini in `intake.py`.

**Cross-feature coupling:**
- The usage ceiling lives in `vaultlib/triage.py` and reads Work Orders' usage record. Intake, the smoke check and the meetings fetch call it.
- `rca_file.sh` files to Jira through `handoffs_site`.

## 2. Decisions (owner, 2026-10-15)

1. **What moves (narrowed 2026-10-16, §7):** three extensions, the vendor-specific features.
   - Jira handoffs, DTCC, and telemetry with RCA.
   - Meetings, inbox triage, Slack notices and two-machine sync stay in core, with their own switches.
   - Work Orders stay in core, off by default.
2. **Target (revised 2026-10-16).** Phase 4 is done when:
   - no DTCC, Sentry, ADX, Kusto, Azure, Jira or Atlassian name or domain is left in core, enforced by the core-clean test;
   - there are 14 schemas or fewer (`dtcc_change`, `production_error`, `telemetry_source`, `rca` and `plan_gate` leave);
   - the gate is green with no extensions and with every extension on.
   - The core line budget is set at 12,500 lines (12,270 measured on 2026-10-16, after the three moves), pinned with the 14-schema cap by a vault_integrity test. The 8,800-line target assumed all seven moves. Raised to 12,750 by #222 (parallel Work Orders and chat triage brought core to 12,606), and to 12,800 by #254 (skipping non-UTF-8 file names in the index).
3. **Home (changed 2026-10-16, §8): tracked folders `extensions/<name>/` in the template.**
   - The template ships every extension, each off until it is listed in `extensions:`.
   - The template update brings them with the normal merge. There is no clone, no pin and no `extensions_remote`.
   - DTCC is a vault-only extension: `extensions/dtcc/`, tracked only in the owner's vault repository.
4. **Packaging: skills plus a Foundry manifest.**
   - An extension's Claude-facing parts are skills in its `skills/` folder, linked into `.claude/skills/` while the extension is on. `/rca` becomes a skill.
   - What Claude Code cannot load is declared in `extension.md`, which Foundry's loader reads: units, scripts, schemas, the brief section, the smoke check, sources, config keys, dependencies and allow rules.
5. **Switch: one `extensions:` list** in `system/config.md`, for example `extensions: ["handoffs", "dtcc"]`.
   - It replaces DTCC's "map file exists" rule and the handoffs and telemetry on-rules.
   - Core features keep their own switches (`meetings_enabled`, `triage_enabled`, `slack_notify_channel`, `machine_role`).
   - The update migrates the old keys once.
   - Each extension keeps its own settings keys, declared in its manifest and validated against its own schema fragment.
6. **First move: Jira handoffs.** It is the smallest, has no units, and touches every mechanism point except units (brief prep, brief section, smoke check, sources, setup, config). The rest follow in this order:
   1. DTCC
   2. telemetry and RCA
7. **Leftovers:**
   - Delete the debrief's **Agent Health** section, the metrics template and the coding Workcell's instruction to write `system/logs/metrics/`, since nothing writes that folder.
   - Delete the `plan_gate` schema and the intent-shaper template.
   - Keep the `workcell` schema: `CLAUDE.md` routing and the recall hooks read the three Workcell files.
   - Close the #62 leftovers (the `vault/` move and the Nightshift renames) as won't-do.

## 3. The extension contract

```
extensions/<name>/
  extension.md       manifest (frontmatter, below) and a short description
  scripts/           the extension's scripts; run as extensions/<name>/scripts/<script>
  schemas/           note-type schemas and its config schema fragment (config.md)
  units/*.in         systemd unit templates, rendered by install_units.sh like core's
  skills/<skill>/    Claude Code skills, linked into .claude/skills/ while on
  brief/prep.sh      optional: writes system/logs/inputs/<date>/sections/<name>.md, exits 0
  brief/section.md   optional: the brief prompt text for that section, included only while on
  debrief/…          optional, same shape as brief/
  tests/             bats and pytest, run by the gate while the extension is present
```

Manifest frontmatter (validated by the loader; the index skips `extensions/`, so there is no note schema for it):

| Field | Meaning |
|---|---|
| `name` | Folder name; the value in `extensions:` |
| `requires` | Other extensions it needs, e.g. telemetry's RCA filing needs handoffs (it reads `jira_site`) |
| `config_keys` | Its keys, with defaults; validated by `schemas/config.md` |
| `units` | Unit names, and the roles (`standalone`, `server`) that install them |
| `smoke` | The check command and its source name(s) for `smoke_check.sh` |
| `sources` | Rows for the Sources line: name, credential, renewal (moves the table out of `vaultlib/sources.py`) |
| `alert_tags` | Its alert tags (#158 alert tags land with the first extension) |
| `deps` | Tools for `check_deps.sh` (e.g. `az`, `pdftotext`) |
| `allow` | Bash allow rules its skills need |
| `index_ignore` | Paths the index skips (e.g. `raw/meetings`) |
| `importer` | Optional: the intake importer hook (meetings) |

Core gets one loader, `system/scripts/extensions.py`, with these commands:
- `list`: the enabled extensions, in dependency order.
- `field <name> <key>`: one manifest field.
- `check`: validates every manifest, reports missing `requires`, and flags a listed extension with no folder.
- `link`: links skills in and out of `.claude/skills/`.

Every shared file reads the loader in place of its per-feature `if` blocks:
- `install_units.sh`, `brief_prep.sh`, `debrief_prep.sh`, `smoke_check.sh`, `sources.py`, `check_deps.sh`
- the schema loader, `index.py`'s ignore list, intake's importer list
- `setup.md` gets one generic "Extensions" phase that walks each enabled extension's manifest.

**Core keeps, generic:**
- the usage ceiling, which stays in `vaultlib/triage.py` (inbox triage stays in core, §7);
- the connector runner (`lib_connector.sh`, `lib_confine.sh`) and `connector_classify`;
- `http.py`, the run ledger, the publish gate, quarantine, the Now page and Work Orders;
- the standalone role (the sync extension adds `server` and `client`).

## 4. Migration and the owner's vault

- `update_template.sh` (and `/setup`) turns a non-empty `handoffs_projects` and an existing telemetry source into `extensions:` entries, once. DTCC is vault-only, so the template carries no rule for it: its cutover lists `dtcc` by hand (DTCC plan, task 4).
  - It then runs `extensions.py check`. A listed extension with no folder is reported (`[extensions] <name> …`) and skipped. Nothing fails.
- Each move is one PR to the template: it deletes the code from core and adds it under `extensions/<name>/` with its tests. The update brings both halves together, so the owner's features keep running across the move. DTCC's move lands in the owner's vault instead (§8).
- A live acceptance run follows each move that changes brief, debrief or ingest text or the settings.

## 5. Tests

- **Core alone:** the gate runs with no extension listed (it runs only the suites of listed extensions), and every core suite passes with no feature skipped for being absent.
- **Everything on:** CI enables every tracked extension and runs the core gate plus each extension's `tests/`. With no extension tracked it prints one skip line.
- **Core is clean:** a bats test fails when a core file (outside `extensions.py` and the docs) names DTCC, Sentry, ADX, Kusto, Azure, Jira or Atlassian, or one of their domains. Slack, Gemini and Google Drive stay in core with the features that use them (§7). It extends the owner-leak test.
- **Loader:** a manifest with a missing `requires`, an unknown key, or a listed extension with no folder is reported by `extensions.py check`.
- **Line budget:** a test counts core script lines and fails above the budget, set once at the end of phase 4.

## 6. Review decisions (owner, 2026-10-15)

1. **Allow rules:** `/setup` writes each enabled extension's `allow` rules from its manifest into `.claude/settings.json` and removes the rules of an extension that is turned off. Every rule stays specific; there is no generic `extensions/*` rule.
2. **Visibility (superseded 2026-10-16, §8):** extensions are public in the template, apart from the vault-only DTCC.
3. **Sequencing with phases 2 and 3:** phase 2 (brief section files) is not built. The first move builds the section-file mechanism for its own section only; phase 2 then moves the remaining core sections onto it.

## 7. Scope decision (owner, 2026-10-16)

Only the vendor-specific features move: Jira handoffs, DTCC, and telemetry with RCA. Meetings, inbox triage, Slack notices, two-machine sync and Work Orders stay in core.

Why: the extensions repository is private, so a feature that moves is gone from the template for anyone who clones it. The four generic features are what a new vault most needs. The part of the design that pays is the core-clean test: vendor and owner names leave core and stay out. Each move costs a pair of PRs that merge together and a live acceptance run, and the loader (#226) already serves the three moves.

What changes from §2:
- The core features keep their own switches; `extensions:` lists only extensions.
- The usage ceiling stays where it is.
- The core-clean test drops Slack, Gemini and Google Drive from its terms, and their allowlist lines go.
- The line budget is set after the three moves.

## 8. Home decision (owner, 2026-10-16)

Extensions are tracked folders `extensions/<name>/` in the template, turned on by the `extensions:` list. The separate extensions repository is dropped and archived once nothing uses it.

Why: every problem the separate repository caused on 2026-10-16 came from the split: a deploy key, an empty repository breaking the checkout, a fixture vault copying the clone, and pairs of PRs that had to merge together. In the template, a move is one PR, the update is the normal merge, and the all-on CI job needs no checkout. The vendor names that move live under `extensions/`, which the core-clean test excludes.

What changes:
- `.gitignore` no longer excludes `extensions/`. `extensions_remote` is gone, and so are the clone and pull in `update_template.sh` and `/setup` phase 6e. The update re-links skills and runs `extensions.py check` after each merge.
- DTCC moves into the owner's vault as a vault-only extension, so no DTCC name ships in the template. The template merge never touches a folder the template does not have.
- With the template shipping extensions, the §7 reason for keeping meetings, inbox triage, Slack notices and sync in core is gone. They stay in core anyway: moving them mostly shrinks a line count, and any of them can move later as one PR.

## 9. The telemetry move (2026-10-16)

Telemetry with RCA needed four contract additions, each generic:
- **`smoke` rows checked per item.** A row with `each: "<list command>"` runs the list, then `run` once per item it prints, with `{}` replaced by the item, reported as `<source>/<item>`. A list that fails is one failed `<source>` line (audit C5); an empty list is `<source>: off`. The list prints `item[<tab>credential<tab>renewal]` lines, so `sources.py` reads the Sources rows and the expired-login renewals from it too (`telemetry_fetch.py --sources`).
- **`tick: {run, timeout}`.** The intake tick runs each enabled extension's tick command once, under `intake.lock`; a failure or a timeout is one `[intake]` alert. RCA filing is telemetry's tick (`rca.py tick`).
- **`lint: <module path>`.** `vault_index.py` lint loads the module of each present extension (present, like its schemas) and calls `issues(conn, add)`; a module that fails is one error on its manifest. The `telemetry_source` cross-field rules moved there from `index.py`.
- **`migrate` reads the vault and enables `requires` first.** Each `MIGRATIONS` rule is `(vault, cfg)`. Telemetry's rule is "a source file other than `example.md` exists in `system/telemetry/`"; it turns on `handoffs` first.

What moved with it: `http.py` (its only user is telemetry, and its stub routes name the vendors), the `production-error` and `rca` templates, the example source, `handoffs_site` (into the handoffs extension's config fragment, beside `handoffs_projects`), and the `rca_*` keys. `/rca` is a skill; on a client, `/setup` phase 6e writes that machine's own `extensions` list (config is per machine) and runs only `link`.

What stays: `~/.azure` in the two credential deny lists (`headless.settings.json`, `nightshift_session.py`). They deny reads; dropping an entry would weaken the sandbox, so `core_clean.allow` keeps those two lines.
