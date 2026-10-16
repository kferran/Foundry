# Extensions Loader and the Jira Handoffs Move: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Core gets one generic extension loader. Jira handoffs then leave core for a tracked `extensions/handoffs/` folder and keep working on the owner's vault.

**Architecture:** An extension is a folder `extensions/<name>/` with an `extension.md` manifest (YAML frontmatter). The template tracks `extensions/` (spec §8, 2026-10-16), so a vault gets it with the template merge.

`system/scripts/extensions.py` reads the manifests and prints what each shared script needs, as tab-separated lines bash can read. These scripts then read the loader in place of their per-feature `if` blocks:
- `brief_prep.sh`, `smoke_check.sh`, `install_units.sh`, `verify_setup.sh`
- `vaultlib/sources.py`, the schema loader, `/setup`
- `update_template.sh`

The loader validates manifests itself. The spec's "a new schema" for `type: extension` is dropped: the index skips `extensions/`, so no note schema would ever cover a manifest, and the schema count stays lower.

**Tech stack:** bash, Python 3.11 (PyYAML), bats, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-15-extensions-design.md` (approved 2026-10-15).

**Pull requests** (revised 2026-10-16, spec §8: extensions are tracked in the template, so B1 and B2 are one PR):
- **PR A (template):** the loader and every mechanism point, proven with a fixture extension. Nothing moves and no behaviour changes. Merged as #226.
- **PR B (template):** handoffs move from core into `extensions/handoffs/`, plus the one-time migration (tasks 12 and 13; task 11's skeleton is not needed). The repository paths below that name the extensions repository mean `extensions/` in this one.
- **PR C (template):** the leftovers (Agent Health, `plan_gate`, #62). #230.

## Global constraints

- The gate stays green at the end of every task. Before a push, run `system/scripts/test.sh <suite>` for each suite you touched.
- bats ruling R1 applies: no `!` in the middle of a test, no `&&` assertion chains, and no assertions on wall-clock timing.
- The template rule holds: no names, hosts or user paths. Fixture extensions use `example.invalid`.
- A change to the brief, debrief or setup command text, or to `.claude/settings.json`, needs a live acceptance run on the owner's host before merge (`FOUNDRY.md`, Development).
- Template rule for `.claude/settings.json`: never rewrite it with `jq`, which reformats the whole file and breaks every later template merge. Insert and remove whole lines as text, then check the result with `jq -e`.
- **Contract version 1:** a manifest's `contract` must equal `extensions.CONTRACT`. On a mismatch the extension is reported and skipped, never loaded.

## Review focus

1. A vault with no `extensions/` folder behaves exactly as it does today: PR A changes no output on master's fixtures (Tasks 3–6 tests).
2. A listed extension with no folder is reported once a day and skipped; nothing fails (Task 1, Task 9).
3. A manifest that names a missing `requires`, an unknown field, or the wrong contract is refused with one reason line (Task 1).
4. The settings writer touches only lines it owns and leaves the file valid JSON (Task 7).
5. The handoffs brief section, smoke line and Sources line read byte for byte as they do on master, now from the extension (B2 live acceptance).

## Owner steps (dropped 2026-10-16, spec §8: there is no separate repository)


---

## PR A: the loader (template)

### Task 1: `extensions.py` and a fixture extension

**Files:**
- Create `system/scripts/extensions.py`, `system/scripts/vaultlib/extensions.py`.
- Create `system/tests/fixtures/extensions/demo/` (manifest, `scripts/demo_check.sh`, `brief/prep.sh`, `brief/section.md`, `units/foundry-demo.service.in`, `units/foundry-demo.timer.in`, `skills/demo-skill/SKILL.md`, `schemas/config.md`).
- Create `system/tests/fixtures/extensions/needs-other/extension.md` (`requires: [missing]`).
- Test: `system/tests/python/test_extensions.py`.

The fixture manifest (`demo/extension.md`):

```yaml
---
name: demo
contract: 1
description: "A fixture extension for the loader tests"
requires: []
config_keys:
  demo_site: {kind: string, default: ""}
sources:
  - {name: demo, credential: "Demo connector", renew: "reconnect it at example.invalid"}
smoke:
  - {source: demo, timeout: 30, connector: false, run: "scripts/demo_check.sh"}
brief: true
units: [{name: foundry-demo, roles: [standalone, server]}]
alert_tags: [demo]
allow: ["Bash(extensions/demo/scripts/demo_check.sh)"]
deps: []
index_ignore: ["raw/demo"]
---
The text /setup shows when the owner turns demo on, and the questions it asks.
```

- [ ] **Step 1: Failing tests** in `test_extensions.py`. A fixture copies `system/tests/fixtures/extensions/*` into `<vault>/extensions/`, and writes `config.md` with `extensions: [...]`. The tests:
  - `test_list_returns_enabled_present_extensions_in_dependency_order`: `["b", "a"]`, where b requires a, lists a then b.
  - `test_listed_without_folder_is_reported_and_skipped`: `check()` returns `["demo2: listed in extensions but extensions/demo2/ does not exist"]`, and `enabled()` leaves it out.
  - `test_missing_requires_wrong_contract_unknown_field_each_refused_with_one_reason`
  - `test_field_reads_one_manifest_field`
  - `test_rows_prints_smoke_sources_units_allow_as_tsv`: `smoke` gives `demo\t30\t0\textensions/demo/scripts/demo_check.sh`.
  - `test_no_extensions_folder_is_empty_everywhere`: no folder and no key give `[]` and no error.
- [ ] **Step 2: Run red.** `python3 -m pytest system/tests/python/test_extensions.py -q` fails (no module).
- [ ] **Step 3: Implement** `vaultlib/extensions.py`:

```python
"""Extensions (extensions spec §3): read extensions/<name>/extension.md manifests for the shared scripts."""
from pathlib import Path

from . import frontmatter

CONTRACT = 1
FIELDS = {"name", "contract", "description", "requires", "config_keys", "sources", "smoke", "brief", "debrief",
          "units", "alert_tags", "allow", "deps", "index_ignore", "importer"}


def listed(vault: Path) -> list:
    cfg = frontmatter.parse((vault / "system/config.md").read_text(encoding="utf-8")).data or {} \
        if (vault / "system/config.md").is_file() else {}
    return [str(n) for n in (cfg.get("extensions") or [])]


def manifest(vault: Path, name: str):
    """(data, None) or (None, reason)."""
    p = vault / "extensions" / name / "extension.md"
    if not p.is_file():
        return None, f"{name}: listed in extensions but extensions/{name}/ does not exist"
    data = frontmatter.parse(p.read_text(encoding="utf-8")).data or {}
    unknown = sorted(set(data) - FIELDS)
    if data.get("name") != name:
        return None, f"{name}: extension.md names {data.get('name')!r}, not {name!r}"
    if data.get("contract") != CONTRACT:
        return None, f"{name}: contract {data.get('contract')!r}; this core reads contract {CONTRACT}"
    if unknown:
        return None, f"{name}: unknown manifest field(s) {', '.join(unknown)}"
    return data, None


def check(vault: Path) -> list:
    """One reason per listed extension that cannot load (missing folder, bad manifest, missing requires)."""
    ...  # manifest() for each listed name; a requires entry not listed, or not loadable, is a reason


def enabled(vault: Path) -> list:
    """(name, data) of the listed extensions that load, requires first (a stable topological order)."""
    ...
```

  The CLI `system/scripts/extensions.py` follows the shape of `meeting_actions.py` (VAULT from `parents[2]`). Its subcommands:

| Command | Prints |
|---|---|
| `list` | enabled names, one per line |
| `check` | the reasons; exit 1 when there are any, else exit 0 and print nothing |
| `field <name> <key>` | one manifest field, JSON-encoded unless it is a string |
| `smoke` | `name<TAB>timeout<TAB>connector(0/1)<TAB>extensions/<name>/<run>`, one line per smoke entry |
| `brief` | names with `brief: true` |
| `units <role>` | `<name><TAB><unit>` for the role |
| `allow` | every enabled extension's allow rules |
| `ignore` | `index_ignore` paths |
| `link` | links skills in and out of `.claude/skills/` (Task 8) |

  Usage errors exit 2.
- [ ] **Step 4: Run green.** Run the same pytest command, then `system/scripts/test.sh system/tests/python`.
- [ ] **Step 5: Commit.** `feat(extensions): the manifest loader and a fixture extension (extensions spec §3)`

### Task 2: config, schemas and the index

**Files:** Modify:
- `system/schemas/config.md`: add `extensions: {kind: list, of: string}` and `extensions_remote: {kind: string}`.
- `system/config.example.md`: add both, with comments.
- `vaultlib/schema.py`, in `load_schemas`.
- `vaultlib/index.py`: the ignore list.
- `.gitignore`: add `extensions/`.

Test: `system/tests/python/test_extensions.py` and `system/tests/python/test_schema.py`.

- [ ] **Step 1: Failing tests:**
  - `test_extension_config_keys_validate_while_present`: with demo present and `demo_site: "x"` in config, `vault_index.py validate system/config.md` reports no unknown field. With demo absent, it reports `unknown field demo_site`, which is today's behaviour for a stray key.
  - `test_extension_note_schemas_load_from_present_extensions`: a schema in `demo/schemas/thing.md` covers its folders. A config fragment (`schema_for: config`) merges its `fields` into the core config schema rather than being a second config schema.
  - `test_index_skips_extensions_and_their_ignore_paths`: no note under `extensions/` or `raw/demo/` is indexed.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement.**
  - `load_schemas` also globs `extensions/*/schemas/*.md` for every *present* folder, so that a key an owner turned off still validates.
  - A fragment with `schema_for: config` updates `schemas["config"].fields`, and a key both sides define is a `SchemaError`.
  - `index.py` adds `extensions` to its skipped top-level folders and appends `extensions.ignore(vault)` to the ignore paths.
- [ ] **Step 4: Run green.** `test.sh system/tests/python` and `test.sh system/tests/vault_integrity.bats`.
- [ ] **Step 5: Commit.** `feat(extensions): extension schemas and config keys; the index skips extensions/`

### Task 3: brief sections from extensions

**Files:**
- Modify `brief_prep.sh` (before the `sources.md` step).
- Modify `.claude/commands/brief.md` (Inputs, and one rule in Write the briefing).

Tests: `system/tests/prep.bats`, `system/tests/commands.bats`.

**Contract:**
- `brief_prep.sh` *sources* `extensions/<name>/brief/prep.sh` in a subshell, for each name `extensions.py brief` prints. The subshell has `PREP_DATE`, `PREP_DIR` and the `prep_*` functions.
- The script writes `$PREP_DIR/sections/<name>.md` (through `prep_write`) and records its readings with `prep_source` and `prep_unavailable`.
- `brief_prep.sh` copies `brief/section.md` to `$PREP_DIR/sections/<name>.prompt.md`, so the headless brief needs only Read.
- A prep script that exits non-zero is one `prep_unavailable "<name>: brief section failed (see …)"` line.

Steps:
- [ ] **Step 1: Failing tests.**
  - prep.bats:
    - `brief_prep: an enabled extension writes its section and prompt into sections/`: demo prep writes `- [ ] demo line`.
    - `a failing extension prep is one unavailable line and the rest of the prep still runs`.
    - `no extensions writes no sections/ folder`.
  - commands.bats: `brief.md` reads `sections/<name>.prompt.md` and `sections/<name>.md`, and says that a missing or empty section file means the section is omitted.
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement.**
  - The `brief_prep.sh` loop (about 12 lines). The `extensions.py brief` call is fed by process substitution, so a loader failure is one unavailable line.
  - `brief.md` Inputs gets: `` `system/logs/inputs/<date>/sections/`: one `<name>.prompt.md` and one `<name>.md` per enabled extension with a brief section ``.
  - Write the briefing gets: "For each `sections/<name>.prompt.md`, follow it with `sections/<name>.md` as its data; it says where its section goes. Omit a section whose data file is missing or empty."
- [ ] **Step 4: Run green.** `test.sh system/tests/prep.bats` and `test.sh system/tests/commands.bats`.
- [ ] **Step 5: Commit.** `feat(extensions): brief sections from enabled extensions (extensions spec §3; phase 2 mechanism)`

### Task 4: the smoke check and the Sources line

**Files:**
- Modify `smoke_check.sh`: one loop after the telemetry block.
- Modify `vaultlib/sources.py`: credentials, order and off rules merged from the manifests.

Tests: `smoke.bats`, `test_sources.py`.

- [ ] **Step 1: Failing tests.**
  - smoke.bats:
    - `an enabled extension's smoke entry runs and reads ok or failed like a core source`: the demo stub exits 0 or 6.
    - `an expired credential from a manifest names it and its renewal`: `demo_check.sh` prints `demo_check: auth: HTTP 401`, giving `demo: expired: Demo connector; renew: reconnect it at example.invalid`.
  - test_sources.py:
    - `test_report_lists_enabled_extension_sources_and_off_when_not_listed`
    - `test_credential_comes_from_the_manifest`
- [ ] **Step 2: Run red.**
- [ ] **Step 3: Implement.**
  - `smoke_check.sh`: read `extensions.py smoke` into an array, then run `connector` or `check` for each entry, by its connector flag.
  - `sources.py`:
    - `CREDENTIALS` gets each enabled manifest's `sources` rows at call time.
    - `report()` adds each enabled extension's source names before `dtcc`.
    - A listed-but-missing extension reads `failed: other: extensions/<name>/ is missing`.
    - An extension that is not listed is not shown.
- [ ] **Step 4: Run green.**
- [ ] **Step 5: Commit.** `feat(extensions): smoke entries and Sources rows from manifests`

### Task 5: units

**Files:**
- Modify `install_units.sh`: render `extensions/<name>/units/*.in` for `extensions.py units <role>`, with the same placeholders as core units, and remove the units of an extension no longer listed. Removal goes through the existing stale-unit path, so these units must carry the same `# Managed by vault:` header.

Test: `system/tests/units.bats`.

- [ ] **Step 1: Failing tests** (`need_user_systemd` where they run `systemctl`):
  - `an enabled extension's units render and install`
  - `turning it off removes them`
  - `--dry-run lists them under ===== headers`, which the smoke check's drift check reads.
- [ ] **Steps 2–5:** red, implement, green, then commit `feat(extensions): install_units renders extension units`.

### Task 6: dependencies

**Files:** Modify `check_deps.sh`. It reads `extensions.py field <name> deps` for each enabled extension and treats each tool as optional, with a hint naming the extension. Test: `system/tests/deps.bats` (or wherever `check_deps.sh` is tested).

- [ ] **Steps 1–5:** failing test (`demo` lists `deps: [example-tool]`, giving the hint `example-tool (extension demo)`), red, implement, green, then commit.

### Task 7: allow rules in `.claude/settings.json`

**Files:**
- Add `extensions.py allow --write` and `--remove <name>`.
- Modify `.claude/commands/setup.md`, adding the Extensions phase (Task 8 text).

Test: `test_extensions.py`.

**Rule:** a rule line goes right after the line `    "allow": [`, written exactly as `      "<rule>",`. Removal deletes lines that equal a known rule of a disabled extension. That needs the manifest, which a removed folder no longer has, so every rule written is also logged in `system/logs/extensions-allow.json` (`{"<rule>": "<name>"}`), and removal reads that file.

- [ ] **Step 1: Failing tests:**
  - `test_write_inserts_each_rule_once_after_the_allow_line_and_keeps_json_valid`
  - `test_write_twice_changes_nothing`
  - `test_remove_deletes_only_that_extensions_rules`
  - `test_a_rule_the_owner_wrote_by_hand_is_never_removed`
  - `test_bytes_outside_the_inserted_lines_are_unchanged`: diff against the original.
- [ ] **Steps 2–5:** red, implement, green, then commit `feat(extensions): /setup writes extension allow rules into settings.json`.

### Task 8: skills and the /setup phase

**Files:**
- `extensions.py link`: a relative symlink `.claude/skills/<skill>` pointing to `../../extensions/<name>/skills/<skill>` for each enabled extension. It removes links into `extensions/` whose extension is no longer enabled, and never touches a real folder.
- Links into `extensions/` are machine state, written per machine. `link` adds each link's path to `.git/info/exclude`, so the tracked `.gitignore` stays template-owned.
- `setup.md`: a new phase, `## 6e. Extensions`.

Phase 6e text:
- If `extensions_remote` is set and `extensions/` is missing, clone it (`git clone <remote> extensions`).
- Show each folder's manifest body.
- Ask which to turn on.
- Write `extensions:` with `vault_index.py set`.
- Ask each turned-on extension's `config_keys`.
- Run `extensions.py allow --write`, `extensions.py link`, `install_units.sh`, and each smoke entry once.
- A failure never blocks setup.

Tests: `test_extensions.py` for link and unlink. `commands.bats` for the phase text: the clone line, `allow --write` and `link`.

- [ ] **Steps 1–5:** red, implement, green, then commit `feat(extensions): skills links and the /setup Extensions phase`.

### Task 9: updates, the gate and CI

**Files:**
- `update_template.sh`: after the template merge, when `extensions/.git` exists, run `git -C extensions pull --ff-only`, then `extensions.py link`. Report the result in the `[update]` line. A failed pull is reported and never stops the update.
  - Also run `extensions.py check` and alert once a day per reason, as `[extensions] <reason>`.
- `verify_setup.sh`: for each `extensions/*/tests/*.bats`, the same gate as core suites. When any `extensions/*/tests/python` exists, pytest gets those paths too.
- `system/tests/helpers.bash`: `make_vault` also copies `$REPO/extensions` when present, and `use_extension <name>` sets `extensions:` in the fixture config.
- `.github/workflows/gate.yml`: a second job, `gate-all-extensions`.
  - It runs only when `vars.FOUNDRY_EXTENSIONS_REPO` is set and `secrets.EXTENSIONS_DEPLOY_KEY` is non-empty. Otherwise one step prints `extensions repository not configured: skipped` and succeeds.
  - It checks out the repository at `extensions/` (`actions/checkout` with `repository`, `ssh-key` and `path: extensions`), lists every folder in `extensions:` in a CI config, and runs `verify_setup.sh --require-suites`.

Tests:
- `sync.bats` or `update.bats`, wherever `update_template.sh` is tested: `a fast-forward of extensions/ is reported; a failed pull is reported and the update still merges`.
- `vault_integrity.bats`: `the gate runs an extension's suites` (the fixture with one bats file).

- [ ] **Steps 1–5:** red, implement, green, then commit `feat(extensions): updates pull extensions/; the gate runs extension suites; CI runs everything on`.

### Task 10: core stays clean

**Files:** Test `system/tests/vault_integrity.bats`.

- [ ] **Step 1: Write the test.** `core names no vendor or customer outside its allowlist`. It greps every tracked file outside `docs/`, `extensions/`, `system/tests/` and `system/scripts/extensions.py` for:
  - `dtcc`, `sentry`, `kusto`, `azure`, `\bjira\b`, `atlassian`, `gemini`, `google drive`, `slack`;
  - the domains `dtcc.com`, `dtcclearning.com`, `atlassian.net` and `sentry.io`.

  Each hit must be in the test's own `ALLOW` list of `file:term` pairs. The list starts at today's hits, generated once by the plan executor and pasted in. Each move deletes its lines. Phase 4 is done when the list is empty.
- [ ] **Step 2:** It passes on PR A, since the list equals today's hits. Then add one stray `jira` to a core file locally and see it fail. Revert that.
- [ ] **Step 3: Commit.** `test(extensions): core names no vendor outside a shrinking allowlist`

### PR A acceptance

Gate green; CI's core job green; `gate-all-extensions` prints its skip line (no extensions repository yet). Live acceptance on the owner's host (brief and setup text changed): one headless `/brief` with no `extensions/` produces the same briefing sections as master and no Sources line change.

---

## PR B1: the extensions repository (dropped 2026-10-16; task 12 joins PR B)

### Task 11: dropped

There is no separate repository to scaffold. The template's `gate-all-extensions` job enables every tracked extension.

### Task 12: the handoffs extension

**Files:**

```
handoffs/extension.md
handoffs/scripts/jira_fetch.sh           (from system/scripts/, VAULT_ROOT = ../../..)
handoffs/scripts/jira_handoffs.py        (VAULT = parents[3]; sys.path adds VAULT/system/scripts)
handoffs/brief/prep.sh                   (the brief_prep.sh handoffs block, writing sections/handoffs.md)
handoffs/brief/section.md                (brief.md lines 35 and 67, rewritten as a section prompt)
handoffs/schemas/config.md               (handoffs_site, handoffs_projects, moved from core)
handoffs/tests/handoffs.bats             (from system/tests/, using use_extension handoffs)
handoffs/tests/python/test_jira_handoffs.py, conftest.py (imports core's conftest)
```

`handoffs/extension.md`:

```yaml
---
name: handoffs
contract: 1
description: "Stalled Jira handoffs in the morning brief"
requires: []
config_keys:
  handoffs_site: {kind: string}
  handoffs_projects: {kind: list, of: string}
sources:
  - {name: handoffs, credential: "Atlassian connector", renew: "reconnect it at claude.ai, Settings, Connectors"}
smoke:
  - {source: handoffs, timeout: 360, connector: true, run: "scripts/jira_fetch.sh --check"}
brief: true
units: []
alert_tags: [handoffs]
allow: ["Bash(extensions/handoffs/scripts/jira_fetch.sh --check)"]
deps: []
index_ignore: []
---
(the body is the text of today's setup phase 6c for handoffs: the site, the project keys and the --check run
with a Bash timeout of at least 400000 ms; a Jira failure never blocks setup)
```

- [ ] **Step 1:** Move the tests first and adapt their paths. Run them against a template checkout that has PR A, with `extensions/` this repository. Red until the scripts move.
- [ ] **Step 2:** Move the scripts and write `prep.sh` and `section.md`. `prep.sh` keeps today's `case "$rc"` unavailable lines word for word, under `PREP_NAME=brief_prep`.
- [ ] **Step 3:** Green. Run the full core gate with `extensions: ["handoffs"]`.
- [ ] **Step 4: Commit.** `feat(handoffs): Jira handoffs as an extension (extensions spec §2.6)`

## PR B: handoffs leave core into extensions/handoffs/ (template)

### Task 13: delete and migrate

**Files:**
- Delete `system/scripts/jira_fetch.sh`, `system/scripts/jira_handoffs.py`, `system/tests/handoffs.bats` and `system/tests/python/test_jira_handoffs.py`.
- Remove:
  - `brief_prep.sh`: the handoffs block (lines 75–94 on master).
  - `smoke_check.sh`: the handoffs lines.
  - `sources.py`: the handoffs entries in `CREDENTIALS`, `order` and `off`.
  - `system/schemas/config.md`: the two keys and their paragraph.
  - `config.example.md`: the two lines.
  - `.claude/settings.json`: the `jira_fetch.sh --check` rule.
  - `brief.md`: lines 35 and 67.
  - `setup.md` 6c: the handoffs half. The RCA filing half stays as `## 6c. RCA filing` until telemetry moves.
  - `FOUNDRY.md`: the handoffs paragraph, which now points at the extensions README.
  - The handoffs cases in `prep.bats`, `smoke.bats`, `commands.bats` and `test_sources.py`, which move to B1.
- **Keep** `handoffs_site` readable by `vaultlib/rca.py`. RCA still files to that site, and the telemetry move later declares `requires: [handoffs]`.
- **Migration** in `update_template.sh` (one function, `migrate_extensions`, which later moves extend): when `handoffs_projects` is a non-empty list and `extensions` does not list `handoffs`, add it with `vault_index.py set`. Each migration runs once, recorded in `system/logs/extensions-migrated`.
  - If `extensions/` is missing, alert once a day: `[extensions] handoffs is listed but extensions/ has no folder for it; set extensions_remote and run /setup phase 6e`.
- Delete the core-clean allowlist lines for these files.

Tests:
- `update.bats`: `the update lists handoffs once when handoffs_projects is set, and never twice`.
- `vault_integrity.bats`: the allowlist shrank.

- [ ] **Steps 1–5:** red, implement, green, then commit `refactor(handoffs)!: Jira handoffs move to the extensions repository`.

### B acceptance (live, on the owner's host)

1. Set `extensions_remote` in a throwaway clone, then run `/setup` phase 6e: it clones the repository, lists handoffs, writes the allow rule and runs the smoke entry.
2. The smoke check prints `handoffs: ok` (or the same class line as master).
3. A headless `/brief` prints the 🧾 Handoffs to chase section and the Sources entry exactly as master did.
4. The update on the owner's live vault: `extensions:` gains `handoffs` once; after the clone the next brief keeps its handoffs section.

## PR C: leftovers (template, independent)

### Task 14: Agent Health, plan_gate and #62

**Files:**
- Remove the debrief's `3. Agent Health` section from `debrief.md` and `system/templates/daily-debrief.md`. Renumber the later sections only if the tests pin the numbers; otherwise leave the numbers.
- Remove `system/templates/compilation-metric.json`, and the coding Workcell's line telling a session to write `system/logs/metrics/`.
- Remove `system/schemas/plan_gate.md` and `system/templates/intent-shaper.md`, and their mentions in `FOUNDRY.md` (line 117 for metrics, line 123 for plan_gate).
- Update the `commands.bats` tests that pin Agent Health (lines 119, 123–127, 669 on master) to assert the section is gone.
- Close #62 with a comment naming this spec's decision 7. That is outward; the owner approved it in the grill.

- [ ] **Steps 1–5:** red, implement, green, then commit `refactor: drop the unfed Agent Health section and the plan_gate schema (extensions spec §2.7)`.
- [ ] **Live acceptance:** one headless `/debrief`. The debrief text changed.

## After this plan

The next moves reuse the mechanism, one plan each (narrowed by the owner 2026-10-16, spec §7):
1. DTCC (its map file becomes the switch's migration rule)
2. telemetry and RCA (`requires: [handoffs]`; `/rca` becomes a skill)

Meetings, inbox triage, Slack notices and sync stay in core. The line budget test is set when the last move lands.
