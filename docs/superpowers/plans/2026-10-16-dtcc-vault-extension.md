# DTCC Watcher as a Vault-Only Extension: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The DTCC change watcher leaves the template. It runs on in the owner's vault as `extensions/dtcc/`, tracked only there, and no DTCC name is left in core.

**Architecture:**
- **One branch, `feat/dtcc-out`, for the template PR.**
  - Task 1 makes two shared hooks generic: a pre-brief unit time, and migration rules that can read vault files.
  - Task 2 moves the watcher into `extensions/dtcc/` with `git mv` and clears every DTCC mention from core. On that commit the gate passes both with no extension listed and with `extensions: ["dtcc"]`.
  - Task 3 exports the folder as a tarball, then removes it in a final commit, so the template ships no DTCC.
- **A cutover** (task 4, the vault's Foreman session, on the owner's OK). The template update and the extension commit land together in the vault, so the `dtcc_change` schema is never defined twice and never missing.

**Tech stack:** Python 3.11 (PyYAML), bash, bats, pytest, systemd user units.

**Spec:** `docs/superpowers/specs/2026-10-15-extensions-design.md` §2.6, §3, §4, §7, §8. The watcher's own spec is `docs/superpowers/specs/2026-10-06-dtcc-change-watcher-design.md` (its behaviour does not change).

## Global Constraints

- Template rule: no hostname, user path, remote URL, distro choice, account ID, or employer, client, codebase or person names in any tracked file.
- After task 2, the core-clean test (`vault_integrity.bats`, "core names no vendor or customer outside its allowlist") passes with every `:dtcc` and `:dtcclearning.com` line removed from `system/tests/core_clean.allow`.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- An extension's python test basenames must not collide with core's. `test_dtcc_*.py` is safe once core's copies have moved.
- The watcher's behaviour, exit codes, note format, state files and the vault's data paths stay as they are: `system/dtcc/map.yaml`, `wiki/<partition>/changes/` and its logs under `system/logs/`.
- The unit names stay `foundry-dtcc-watch.service` and `.timer`, so the vault's installed units are re-rendered in place.
- The gate (`verify_setup.sh`) is green at the end of every task.

## Review Focus

1. **The schema is defined twice:** while core still ships `dtcc_change`, an `extensions/dtcc/` folder in the vault makes schema loading fail. Task 4's order prevents it. Task 2 pins that the extension's schema is the only `dtcc_change` once core's has moved.
2. **A vault with a map that never turned the extension on:** the update's migration lists `dtcc` once. An owner who turns it off later stays off. Pinned in task 1.
3. **The timer renders with no core variable named after DTCC:** `{{PRE_BRIEF_TIME}}` is 30 minutes before the brief, and an extension unit may use it. Pinned in task 1, with the old `{{DTCC_TIME}}` gone.
4. **Brief lines become Now lines:** each `DTCC:` brief line is still added to the Now page of the partition that holds its note. That text moves from `brief.md` to the extension's `brief/section.md`. Pinned in task 2.
5. **An update that lists `dtcc` before the folder exists:** one `[extensions]` alert a day, nothing fails, the rest of the brief runs. Pinned in task 1 for a map-only vault.

---

### Task 1: generic hooks in core

**Files:**
- Modify: `system/scripts/install_units.sh` (the `dtcc_time` lines near 203 and the `render` sed list).
- Modify: `system/systemd/foundry-dtcc-watch.timer.in` (uses `{{PRE_BRIEF_TIME}}`; task 2 moves it).
- Modify: `system/scripts/vaultlib/extensions.py` (`MIGRATIONS`, `migrate`).
- Test: `system/tests/units.bats`, `system/tests/python/test_extensions.py`.

**Interfaces:**
- Produces:
  - the unit placeholder `{{PRE_BRIEF_TIME}}`, "HH:MM", brief_time minus 30 minutes;
  - `MIGRATIONS: dict[str, Callable[[Path, dict], bool]]`, called as `used(vault, cfg)`;
  - `MIGRATIONS["dtcc"] = lambda vault, cfg: (vault / "system" / "dtcc" / "map.yaml").is_file()`.
- The telemetry PR adds its own entry with the same `(vault, cfg)` signature. Whichever merges second resolves that dict.

- [ ] **Step 1: failing tests.**
  - In `units.bats`, rename the DTCC timer test to `"a unit template's {{PRE_BRIEF_TIME}} is 30 minutes before the brief (extensions spec §3)"`. Keep its assertions (`OnCalendar=*-*-* 05:30:00` for a 06:00 brief), and add:
    ```bash
      run grep -c 'DTCC_TIME' "$REPO/system/scripts/install_units.sh"
      [ "$output" = 0 ]
    ```
  - In `test_extensions.py`, beside the migrate tests:
    ```python
    def test_migrate_lists_dtcc_once_when_the_vault_has_a_map(vault):
        write(vault, "system/config.md", "---\ntype: config\n---\n")
        write(vault, "system/dtcc/map.yaml", "partition: work\n")
        assert run(vault, "migrate").stdout == "enabled dtcc\n"
        write(vault, "system/config.md", "---\ntype: config\nextensions: []\n---\n")
        assert run(vault, "migrate").stdout == ""
        assert extensions.listed(vault) == []


    def test_migrate_does_not_list_dtcc_without_a_map(vault):
        write(vault, "system/config.md", "---\ntype: config\n---\n")
        assert run(vault, "migrate").stdout == ""
    ```
  - In `remote.bats` (Review Focus 5):
    ```bash
    @test "an update in a vault with a DTCC map lists dtcc, and a missing extension folder is one alert (extensions spec §4, §8)" {
      template_setup
      mkdir -p system/dtcc
      printf 'partition: work\n' > system/dtcc/map.yaml
      upstream_commit new.txt hello
      run "$UT"
      [ "$status" -eq 0 ]
      grep -qx 'extensions: \["dtcc"\]' system/config.md
      run grep -c '\[extensions\] dtcc: listed in extensions but extensions/dtcc/ does not exist' "system/logs/alerts_$(date +%F).md"
      [ "$output" = 1 ]
    }
    ```
- [ ] **Step 2: run them.**
  - `system/scripts/test.sh system/tests/units.bats -f PRE_BRIEF` → FAIL: the count is 2.
  - `system/scripts/test.sh system/tests/python/test_extensions.py -k dtcc` → FAIL: `migrate` prints nothing.
  - `system/scripts/test.sh system/tests/remote.bats -f "DTCC map lists dtcc"` → FAIL: `config.md` has no `extensions:` line.
- [ ] **Step 3: implement.**
  - In `install_units.sh`:
    - rename `dtcc_time` to `pre_brief_time`;
    - its comment reads "30 minutes before the brief, after the template update";
    - the sed list maps `{{PRE_BRIEF_TIME}}`;
    - the update-time comment says "ahead of the pre-brief units (#117)".
  - In the timer template, use `{{PRE_BRIEF_TIME}}` in `Description` and `OnCalendar`.
  - In `extensions.py`:
    ```python
    MIGRATIONS = {
        "handoffs": lambda vault, cfg: bool(cfg.get("handoffs_projects")),
        "dtcc": lambda vault, cfg: (vault / "system" / "dtcc" / "map.yaml").is_file(),
    }
    ```
    and in `migrate`: `if name in done or not used(vault, cfg):`.
- [ ] **Step 4: run green.** `units.bats`, `test_extensions.py`, `remote.bats`.
- [ ] **Step 5: commit.** `feat(extensions): a pre-brief unit time and vault-aware migrations (extensions spec §4, §8)`

### Task 2: DTCC moves into `extensions/dtcc/` and leaves core

**Moved with `git mv`** (history follows):

| From | To (under `extensions/dtcc/`) | Change |
|---|---|---|
| `system/scripts/dtcc_watch.py` | `scripts/dtcc_watch.py` | `sys.path` takes its own folder, then the vault's `system/scripts`; it imports `from dtcclib import dtcc_run` |
| `system/scripts/vaultlib/dtcc_{diff,fetch,map,notes,parse,run}.py` | `scripts/dtcclib/` (plus an empty `__init__.py`) | Relative imports between them stay; imports of core modules become `from vaultlib import frontmatter, schema` |
| `system/schemas/dtcc_change.md` | `schemas/dtcc_change.md` | none |
| `.claude/skills/dtcc-watch/SKILL.md` | `skills/dtcc-watch/SKILL.md` | command paths become `extensions/dtcc/scripts/dtcc_watch.py` |
| `system/systemd/foundry-dtcc-watch.{service,timer}.in` | `units/` | `ExecStart="{{VAULT_ROOT}}/extensions/dtcc/scripts/dtcc_watch.py"` |
| `system/dtcc/map.example.yaml` | `map.example.yaml` | none |
| `system/tests/dtcc_watch.bats` | `tests/dtcc_watch.bats` | loads the core helpers as `extensions/handoffs/tests/handoffs.bats` does; `use_extension dtcc` after `make_vault`; runs `extensions/dtcc/scripts/dtcc_watch.py` |
| `system/tests/python/test_dtcc_*.py` (six) | `tests/python/` | `from vaultlib import dtcc_x` becomes `from dtcclib import dtcc_x`; `REPO / "system/tests/fixtures/dtcc"` becomes `Path(__file__).resolve().parents[1] / "fixtures"` |
| `system/tests/fixtures/dtcc/` | `tests/fixtures/` | none |

**New** under `extensions/dtcc/`:
- `tests/python/conftest.py`: handoffs' conftest plus the core tests' python folder (`VAULT / "system" / "tests" / "python"`), so the moved tests keep `from helpers import REPO, concept, write`.
- `extension.md`:
  ```markdown
  ---
  name: dtcc
  contract: 1
  description: "DTCC Insurance & Retirement Services changes that touch a registered codebase"
  requires: []
  config_keys: {}
  sources:
    - {name: dtcc, credential: "none (public pages)", renew: "check the map with /dtcc-watch check"}
  smoke:
    - {source: dtcc, timeout: 60, connector: false, run: "scripts/dtcc_watch.py --check"}
  brief: true
  units: [{name: foundry-dtcc-watch, roles: [standalone, server]}]
  alert_tags: [dtcc]
  allow: ["Bash(extensions/dtcc/scripts/dtcc_watch.py --check)", "Bash(extensions/dtcc/scripts/dtcc_watch.py)", "Bash(extensions/dtcc/scripts/dtcc_watch.py --status)"]
  deps: [pdftotext]
  index_ignore: []
  ---
  **DTCC change watcher.** Watches DTCC Insurance & Retirement Services (Learning Center documents, release dates, Important Notices, the API Marketplace) for changes that touch a registered codebase, and writes a `dtcc_change` note for each. It runs from `system/dtcc/map.yaml`; start from `extensions/dtcc/map.example.yaml`. Run `extensions/dtcc/scripts/dtcc_watch.py --check` and report its lines.
  ```
- `brief/prep.sh`:
  ```bash
  # New DTCC changes since the latest earlier briefing (DTCC watcher spec §7). Sourced by brief_prep.sh in a subshell,
  # from the vault root, with PREP_DATE, PREP_DIR and the prep_* functions (extensions spec §3). Empty without a map.
  : > "$PREP_DIR/sections/dtcc.md"
  if [[ ! -f system/dtcc/map.yaml ]]; then
    prep_source dtcc off
    exit 0
  fi
  rc=0
  prep_write sections/dtcc.md extensions/dtcc/scripts/dtcc_watch.py --brief "$PREP_DATE" || rc=$?
  if (( rc == 0 )); then prep_source dtcc ok; else prep_source dtcc failed "dtcc_watch.py --brief exit $rc"; fi
  (( rc == 0 )) || prep_unavailable "dtcc: dtcc_watch.py --brief failed (see $PREP_DIR/prep_errors.log)"
  exit 0
  ```
- `brief/section.md`: `brief.md`'s DTCC text, copied verbatim from master (the `dtcc.md` input line near 33 and its Now rule near 58), with `dtcc.md` renamed to "the data file". It keeps the sentence that adds every line, without its `- [ ] `, to the Now page of the partition whose `wiki/<partition>/changes/` holds its note.

**Core files edited** (every DTCC mention goes):
- `brief_prep.sh`: the dtcc block (lines 77–79) and the dtcc mention in the comment near 125.
- `install_units.sh`: the map-gated DTCC block (130–134).
- `smoke_check.sh`: lines 158–160.
- `vaultlib/sources.py`: the dtcc entries in `order` and `off`.
- `vaultlib/alerts.py`: the `dtcc` tag. The extension's lines then fall into the brief group like any unlisted tag, which is what `dtcc` already was.
- `vaultlib/index.py`: `system/dtcc/` in the config-folder tuple. The map is YAML and never indexed, so it goes.
- `.claude/settings.json`: the three `dtcc_watch.py` allow rules. `/setup` phase 6e writes the extension's rules from its manifest.
- `.claude/commands/brief.md`: lines 28 (`dtcc` in the source list), 33 (the `dtcc.md` input) and 58 (its Now rule).
- `CLAUDE.md`: the Directory Map's "(`dtcc_change` notes from the DTCC watcher)".
- `FOUNDRY.md`, lines 27, 77, 95, 111 (the `dtcc` alert tag), 170, 188, 201–202 and 254. One sentence under Extensions says a vault may keep its own extensions under `extensions/`, tracked only in the vault.
- `system/systemd/foundry-smoke.service.in`: the "60 for the DTCC map" comment.
- `system/tests/core_clean.allow`: every `:dtcc` and `:dtcclearning.com` line.
- Tests that name DTCC as a feature:
  - `prep.bats`: the `dtcc.md` test, which now runs from the extension's suite;
  - `smoke.bats`: the dtcc stub and its cases, near lines 19, 76, 82, 107–113, 150–159 and 231;
  - `units.bats`: the map-gated DTCC assertions (task 1 made the time generic);
  - `test_sources.py`: `- dtcc: off`, using `demo` for the order check;
  - `test_alerts.py`, `test_notify.py` and `commands.bats:1133` (the tag lists);
  - `test_schema_notes.py`: `EXPECTED` without `dtcc_change`.
- Tests that use "dtcc" as sample words (`test_nightshift_*.py`, `test_now.py`):
  - `www.dtcc.com` becomes `www.example.com`;
  - the "dtcc watcher" titles become "sample watcher";
  - statements like "DTCC: Release notes" become "Vendor: Release notes".

- [ ] **Step 1: failing tests.**
  - Delete the `:dtcc` and `:dtcclearning.com` lines from `core_clean.allow`. Run `system/scripts/test.sh system/tests/vault_integrity.bats -f "core names no vendor"`. Expected: FAIL, listing every core file that still names DTCC.
  - In the moved `tests/python/test_dtcc_notes.py`, add:
    ```python
    def test_the_extension_owns_the_dtcc_change_schema():
        from vaultlib import schema
        schemas = schema.load_schemas(REPO)
        assert schemas["dtcc_change"].source == "extensions/dtcc/schemas/dtcc_change.md"
    ```
  - In the moved `tests/dtcc_watch.bats`, add:
    ```bash
    @test "the brief section adds each DTCC line to the Now page of its note's partition (extensions spec §3)" {
      grep -qF 'wiki/<partition>/changes/' "$V/extensions/dtcc/brief/section.md"
      grep -qF 'Now page' "$V/extensions/dtcc/brief/section.md"
    }
    ```
- [ ] **Step 2: move and edit.** `git mv` the files in the table, write the new files, fix imports and paths, and edit the core files above until the core-clean test passes.
- [ ] **Step 3: green both ways.**
  - Run the full gate with no extension listed (`system/config.md` absent, as in CI's core job).
  - Run it again with `extensions: ["dtcc"]` in a scratch `system/config.md`, so the gate runs `extensions/dtcc/tests/`. Expected: green, with every moved test passing from its new place.
- [ ] **Step 4: commit.** `refactor(dtcc)!: the DTCC watcher moves into extensions/dtcc/ (extensions spec §7, §8)`

### Task 3: the folder leaves the template

- [ ] **Step 1: export.** `git archive --format=tar.gz -o <scratchpad>/dtcc-extension.tar.gz HEAD extensions/dtcc`. List its contents with `tar -tzf` and check that every moved file is there.
- [ ] **Step 2: remove.** `git rm -r extensions/dtcc`. Run the full gate with no extension listed, and the core-clean test.
- [ ] **Step 3: commit.** `chore(dtcc): the DTCC extension is vault-only; the template ships none (extensions spec §8)`
- [ ] **Step 4: review and PR.**
  - A fresh reviewer checks `feat/dtcc-out` against this plan and spec §8, with the tarball's file list.
  - The PR body carries task 4's cutover steps and says the folder travels separately.
  - The intermediate commit holds the folder in history. DTCC code is already in the template's public history, so this exposes nothing new.

### Task 4: cutover in the owner's vault (the vault's Foreman session, on the owner's OK)

Order matters (Review Focus 1). Do it in one sitting, between the PR's merge and the next 05:30 update:
1. Copy the tarball into the vault's scratch area. Do not extract it into `extensions/` yet.
2. Run `system/scripts/update_template.sh` by hand. It merges the template, which deletes core's DTCC, and `migrate` lists `dtcc` (one `[extensions]` alert, since there is no folder yet).
3. At once, extract the tarball at the vault root (`extensions/dtcc/`) and commit it.
4. Run:
   - `system/scripts/extensions.py check` (expect no output);
   - `extensions.py allow --write`;
   - `extensions.py link`;
   - `install_units.sh`. The re-rendered `foundry-dtcc-watch.service` now runs `extensions/dtcc/scripts/dtcc_watch.py`.
5. `extensions/dtcc/scripts/dtcc_watch.py --check` exits 0. `vault_index.py issues` shows 0 errors, with every existing `dtcc_change` note validating against the extension's schema.
6. The next morning's brief has its DTCC lines (or none when nothing changed), and the Sources line counts `dtcc`.

### Live acceptance (before the PR opens, in a throwaway clone)

Check out task 2's commit (the folder still present) in a `.scratch` clone. Copy the owner's `system/dtcc/map.yaml` and one `wiki/work/changes/` note in, read-only, and set `extensions: ["dtcc"]`. Then run:
- `extensions/dtcc/scripts/dtcc_watch.py --check` and `--status`;
- `brief_prep.sh` (expect `sections/dtcc.md`, and `dtcc: ok` in `sources.md`);
- one headless `/brief` (expect exit 0, published, 0 denials, and the DTCC section when the data file has lines);
- `install_units.sh --dry-run` (expect the timer 30 minutes before the brief).

Never copy map contents or note text into the report.
