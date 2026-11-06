# Market watch, PR 1 (extension commands and extra timer times) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An enabled extension can declare a headless command in its manifest, which `run_headless.sh <name>` runs and the publish gate accepts, and an extension timer can take extra run times from a config key.

**Architecture:** `vaultlib/extensions.py` gains a `commands` manifest field, its validation, and `command(vault, name)`, which resolves the declared command of an enabled extension with its model and timeout read from config. `run_headless.sh` asks `system/scripts/extensions.py command <name>` for any name that is not a core command and takes its prompt, targets, model and timeout from the answer. The gate's run-id pattern checks shape only; `validate_run` refuses a command that is neither core nor declared. `install_units.sh` expands a `{{EXTRA_TIMES:<key>}}` line into extra `OnCalendar=` lines before its sed pass.

**Tech Stack:** bash, Python 3 (`system/scripts/vaultlib/`), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-31-market-watch-design.md` §3.3 ("A generic headless command for extensions"), §3.6 and §7 item 1 (approved by the owner's merge of #451)

## Global Constraints

- The harness (`run_headless.sh`) and the publish gate are safety surfaces: the owner merges this PR (FOUNDRY.md:505).
- Core code never names an extension or the word `market` (factory F2 §3.2; the vendor scan in `vault_integrity.bats:607-628`). Tests use the `demo` fixture extension.
- Core commands: `ingest`, `brief`, `debrief`, `meeting`, `nightshift`, `digest-backfill`. An extension command may not take one of these names.
- `headless.settings.json` does not change. An extension command gets the brief's tools (`Read,Glob,Grep,Edit,Write,Bash`, the staging Edit rule and the `vault_index.py` read subcommands).
- The `TIMEOUT="${HEADLESS_TIMEOUT:-15m}"` line stays as it is, and no new `{HEADLESS_TIMEOUT` use is added (`conformance.bats:233,407`).
- `market_runs_per_day`-style keys take 1 to 4 (spec §3.6). The first run stays at `{{PRE_BRIEF_TIME}}`, and the last extra run falls at 18:00.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Run only the changed files' suites locally (`system/scripts/test.sh <paths>`); CI is the gate.
- Template rule: no hostname, user path, remote URL, or employer, client, codebase, vendor or people names in any committed file.
- The core cap rises by the measured count, with a reason line (`vault_integrity.bats:521`). One change file: `changes/2026-11-06-extension-commands.md`.

## Rulings against the spec

- **Ruling 1, targets take `<date>` only.** §3.3 allows targets under `wiki/<partition>/` with `<partition>` "filled in at run time", but it names no source for the value, and the market command needs only `briefings/market/<date>.md`. PR 1 accepts targets under `briefings/<command name>/` with a `<date>` placeholder. A `wiki/` target waits for an extension that needs one, and that extension names where its partition comes from. Cost if wrong: a later extension adds one validation branch and one substitution.
- **Ruling 2, model and timeout defaults come from the config schema.** Config readers do not apply schema defaults (`vaultlib/config.py:7`). `extensions.command()` reads `model_key` and `timeout_key` from config and falls back to the key's `default` in the extension's `schemas/config.md`. `run_headless.sh` passes `--model` only when a value results, and uses the smaller of the timeout and `HEADLESS_TIMEOUT`.
- **Ruling 3, one run-id pattern.** `publish.RUN_ID` and `commit_runs.RUN_ID` already differ (`digest-backfill` is in one only). `commit_runs` imports `publish.RUN_ID`, and it skips `digest-backfill` runs by name to keep today's behavior.
- **Ruling 4, the spec's timeout default.** §3.3 says `market_timeout_minutes` defaults to 15, while §3.1 and the #236 decision say 20. Task 5 corrects §3.3 to 20, capped by `HEADLESS_TIMEOUT` (15 minutes today).

## Review Focus

1. A command name shaped like a path or a core command (`../x`, `Brief`, `ingest`, `digest-backfill`): the manifest check gives a reason, `command()` returns `None`, and `run_headless.sh` exits 2 before any ledger line. (Task 1, Task 2 tests.)
2. A command declared by an extension that is present but not listed in `extensions:`: `run_headless.sh` exits 2, and the gate's `validate_run` refuses a staged run with that command. (Task 2, Task 3 tests.)
3. Two enabled extensions declare the same command name: neither runs, and the check names both. (Task 1 test.)
4. A target that escapes its folder (`briefings/demo/../../CLAUDE.md`, `wiki/work/**`, `briefings/other/<date>.md`): a reason, and the command is not runnable. (Task 1 test.)
5. A runs-per-day key set to `0`, `5` or `two`, or a brief time whose first run falls at or after 18:00: the install refuses with a message naming the key. Unset means 1 run. (Task 4 test.)

---

### Task 1: The `commands` manifest field and `command()` (§3.3)

**Files:**
- Modify: `system/scripts/vaultlib/extensions.py` (`FIELDS`, `_field_reasons`, new `CORE_COMMANDS`, `COMMAND`, `command`)
- Modify: `system/scripts/extensions.py` (new `command <name>` subcommand)
- Modify: `system/tests/fixtures/extensions/demo/extension.md` (declares `commands`), new `system/tests/fixtures/extensions/demo/commands/demo.md`, `system/tests/fixtures/extensions/demo/schemas/config.md` (adds `demo_model`, default `"sonnet"`, and `demo_timeout_minutes`, int, default `"20"`; create the file if the fixture has none)
- Test: `system/tests/python/test_extensions.py`

**Interfaces:**
- Produces:
  - `extensions.CORE_COMMANDS: frozenset[str]`, the six names in Global Constraints.
  - `extensions.COMMAND = re.compile(r"[a-z][a-z-]*[a-z]")`.
  - `extensions.command(vault: Path, name: str) -> dict | None`: for a name declared by exactly one enabled extension with a valid entry, `{"ext": str, "name": str, "targets": list[str], "model": str, "timeout_minutes": int | None}`. `targets` keep `<date>` unfilled. `model` is `""` when neither config nor schema default sets it. `timeout_minutes` is `None` when the value is not a positive integer.
  - CLI `system/scripts/extensions.py command <name>`: prints that dict as one JSON line, exit 0, or prints nothing and exits 1.
- Manifest form: `commands: [{name: demo, targets: ["briefings/demo/<date>.md"], model_key: demo_model, timeout_key: demo_timeout_minutes}]`.

- [ ] **Step 1: Write the failing tests** in `test_extensions.py`, using the existing `manifest(vault, name, **fields)` and `config(vault, *names)` helpers:
  - `test_a_declared_command_resolves_with_schema_defaults`: the demo extension enabled, no config keys set → `command(vault, "demo") == {"ext": "demo", "name": "demo", "targets": ["briefings/demo/<date>.md"], "model": "sonnet", "timeout_minutes": 20}`.
  - `test_config_values_override_the_defaults`: config `demo_model: haiku`, `demo_timeout_minutes: 7` → `model == "haiku"`, `timeout_minutes == 7`.
  - `test_a_listed_but_absent_or_unlisted_command_is_none`: `command(vault, "nope") is None`; the demo extension present but not in `extensions:` → `command(vault, "demo") is None`.
  - `test_bad_command_entries_are_reasons_and_not_runnable`: parametrized over the name `ingest`, `digest-backfill`, `Brief`, `../x`, `x`; the targets `["wiki/work/**"]`, `["briefings/other/<date>.md"]`, `["briefings/demo/../../CLAUDE.md"]`, `[]`; and a missing `model_key`. Each gives exactly one reason from `check(vault)` starting `demo: command` and `command(vault, <name>) is None`.
  - `test_a_name_two_extensions_declare_runs_in_neither`: two enabled fixtures declare `demo` → `command(vault, "demo") is None` and `check(vault)` has one reason naming both extensions.
  - `test_the_cli_prints_one_json_line_or_exits_1`: through `subprocess.run([sys.executable, "system/scripts/extensions.py", "command", "demo"], cwd=vault)`.
- [ ] **Step 2: Run them.** `system/scripts/test.sh system/tests/python/test_extensions.py` → the new tests FAIL (`commands` is an unknown field, `command` is not defined).
- [ ] **Step 3: Implement.** Add `"commands"` to `FIELDS`. A valid entry is a map whose `name` matches `COMMAND`, is not in `CORE_COMMANDS`, and whose `targets` is a non-empty list where each target starts with `briefings/<name>/` and has no `..` segment, `*` or `<` other than `<date>`, plus string `model_key` and `timeout_key`. `_field_reasons` gives one reason per invalid entry. `check` adds one reason per name that two loaded extensions declare. Read the schema default through the extension's `schemas/config.md` with the loader `vaultlib.schema` already uses for config schemas (`schema.py:159-176`); do not parse YAML by hand.
- [ ] **Step 4: Run the suite** → PASS.
- [ ] **Step 5: Commit** `feat(extensions): a commands manifest field for extension headless runs (#236)`.

### Task 2: `run_headless.sh` runs a declared command (§3.3)

**Files:**
- Modify: `system/scripts/run_headless.sh:35-38` (dispatch), `:69-71` (no arguments), `:117-121` (prompt file), `:159-165` (targets), `:191-195` (`--model`, timeout)
- Modify: `system/tests/stub_claude` (new `STUB_MODE=demo_page`: writes `briefings/demo/$(date +%F).md` into staging with frontmatter valid for the demo fixture's `memo` or `thing` schema, whichever allows the `briefings/demo/` folder; widen that fixture schema's folders if neither does)
- Test: `system/tests/headless.bats`

**Interfaces:**
- Consumes: `system/scripts/extensions.py command <name>` (Task 1).
- Produces: `run_headless.sh <ext command>`, which runs with run id `<RUN_TS>-<name>-<hex4>`, snapshot targets with `<date>` replaced by `$TODAY`, and the prompt from `extensions/<ext>/commands/<name>.md`.

- [ ] **Step 1: Write the failing tests** in `headless.bats`, each with `use_extension demo` (from `helpers.bash:73`) unless stated:
  - `an enabled extension's command runs with its prompt, targets, model and timeout`: `STUB_ARGS` shows `--model sonnet` and the demo prompt's text; the snapshot (`system/logs/runs/<id>/snapshot.json` or what `publish_staged.py snapshot` writes) lists `briefings/demo/<TODAY>.md`; the run id matches `-demo-`.
  - `an extension command with a staged page publishes it`: `STUB_MODE=demo_page` → exit 0 and `briefings/demo/<TODAY>.md` exists in the vault.
  - `an unknown, unlisted or core-shaped extension command exits 2 with no ledger line`: three runs: `nope`, `demo` with the extension not listed, `../x`. Each has status 2, and the ledger has no new line.
  - `an extension command refuses arguments`: `run "$RH" demo extra` → status 2.
  - `an extension command's timeout is the smaller of its key and HEADLESS_TIMEOUT`: with `demo_timeout_minutes: 7` and `HEADLESS_TIMEOUT` unset, the headless log (`system/logs/headless/demo_<TODAY>.log`) has the line `timeout 7m`; with `HEADLESS_TIMEOUT=1 STUB_MODE=sleep` the run exits 124 (a key of 20 never lengthens the harness limit).
- [ ] **Step 2: Run them.** `system/scripts/test.sh system/tests/headless.bats` → the new tests FAIL with "unknown command: demo".
- [ ] **Step 3: Implement.** At the dispatch, a core name passes as today. Any other name must match `^[a-z][a-z-]*[a-z]$`, then `ext_json="$(system/scripts/extensions.py command "$cmd")"` must succeed, or `die 2 "unknown command: …"`. Read `ext`, `targets`, `model` and `timeout_minutes` with `jq`. The prompt file is `extensions/$ext/commands/$cmd.md`. The targets replace `<date>` with `$TODAY`. Add `--model "$model"` to the `claude` call only when it is non-empty. When `timeout_minutes` is set and `$TIMEOUT` has the form `<n>m` with `n` above it, `TIMEOUT="${timeout_minutes}m"`. An extension command writes `timeout $TIMEOUT` to `$LOG` before the `claude` call. Lock, recovery, ledger, tools and publish follow the brief's path.
- [ ] **Step 4: Run the suite** → PASS, including every existing `headless.bats` test.
- [ ] **Step 5: Commit** `feat(headless): run_headless.sh runs an enabled extension's declared command (#236)`.

### Task 3: The gate accepts a declared command's run id (§3.3)

**Files:**
- Modify: `system/scripts/vaultlib/publish.py:17` (`RUN_ID`), `:46-50` (`check_run_id`), `validate_run` (`:430`)
- Modify: `system/scripts/commit_runs.py:24,73` (use `publish.RUN_ID`, skip `digest-backfill`)
- Test: `system/tests/python/test_publish.py`, `system/tests/python/test_commit_runs.py`

**Interfaces:**
- Consumes: `extensions.CORE_COMMANDS`, `extensions.command(vault, name)` (Task 1).
- Produces: `publish.RUN_ID = re.compile(r"^(\d{8}T\d{6})-([a-z][a-z-]*[a-z])-([0-9a-f]{4})$")`; `check_run_id(run_id) -> str` returns group 2 (the command), signature unchanged.

- [ ] **Step 1: Write the failing tests.**
  - In `test_publish.py`, extend `test_check_run_id` (`:39`): `20261106T053000-demo-ab12` → `"demo"`; `20261106T053000-Demo-ab12`, `20261106T053000-../x-ab12` and `20261106T053000--ab12` raise `PublishError`.
  - `test_validate_run_refuses_an_undeclared_command`: a staged run `…-nope-ab12` with a valid snapshot → one `Problem` whose text names `unknown command: nope`.
  - `test_validate_run_accepts_a_declared_extension_command`: the demo extension enabled, a run `…-demo-ab12` staging `briefings/demo/2026-11-06.md` against the target `briefings/demo/2026-11-06.md` → no problems.
  - In `test_commit_runs.py`, `test_pending_takes_an_extension_command_and_skips_digest_backfill`: run folders `…-demo-ab12` and `…-digest-backfill-ab12`, each with a `publish.json` → `pending` returns only the demo run.
- [ ] **Step 2: Run them.** `system/scripts/test.sh system/tests/python/test_publish.py system/tests/python/test_commit_runs.py` → the new tests FAIL.
- [ ] **Step 3: Implement.** Change `RUN_ID` and `check_run_id` as above. In `validate_run`, after `check_run_id`, add a `Problem` when `command not in CORE_COMMANDS and extensions.command(vault, command) is None`. `commit_runs.RUN_ID` becomes `publish.RUN_ID`; `pending` uses `match.group(1)` for the time as today and skips `match.group(2) == "digest-backfill"`. Check that `prune.py:24,65,82` still behave the same (both patterns now have the same groups).
- [ ] **Step 4: Run the changed suites, plus `test_nightshift_item.py` and `test_now.py`** (they call `check_run_id`) → PASS.
- [ ] **Step 5: Commit** `feat(publish): the gate takes a declared extension command's run id (#236)`.

### Task 4: `{{EXTRA_TIMES:<key>}}` in unit templates (§3.6)

**Files:**
- Modify: `system/scripts/install_units.sh` (`render()`, `:213-228`, plus a pre-pass)
- Modify: `system/tests/fixtures/extensions/demo/units/foundry-demo.timer.in` (adds the line `{{EXTRA_TIMES:demo_runs_per_day}}` after its `OnCalendar=` line), `system/tests/fixtures/extensions/demo/schemas/config.md` (declares `demo_runs_per_day`, int, min 1, max 4, default `"1"`)
- Test: `system/tests/units.bats`

**Interfaces:**
- Produces: a template line that is exactly `{{EXTRA_TIMES:<key>}}` becomes `n - 1` lines `OnCalendar=*-*-* HH:MM:00 {{TZ}}`, where `n` is the key's config value (unset → 1). With `p` the `{{PRE_BRIEF_TIME}}` minute of the day and `step = (1080 - p) / (n - 1)` (integer division), extra run `i` (1 to `n - 1`) is at minute `p + i * step`. The `{{TZ}}` in each line is then rendered by the existing sed pass.

- [ ] **Step 1: Write the failing tests** in `units.bats`, next to the `{{PRE_BRIEF_TIME}}` test (`:441`), each with `use_extension demo` and a brief at 06:00 (so `p` = 05:30):
  - `an EXTRA_TIMES line adds nothing when its key is unset`: the rendered timer has exactly one `OnCalendar=` line.
  - `a runs-per-day of 2 adds one run at 18:00`: `demo_runs_per_day: 2` → `grep -c '^OnCalendar=' = 2`, and one line is `OnCalendar=*-*-* 18:00:00 <tz>`.
  - `a runs-per-day of 4 spaces the extra runs evenly until 18:00`: → the extra lines are at 09:40, 13:50 and 18:00.
  - `a runs-per-day outside 1-4 or not a number refuses the install`: `0`, `5`, `two` → non-zero exit, and the output names `demo_runs_per_day`.
  - `extra runs need a first run before 18:00`: a brief at 18:30 with `demo_runs_per_day: 2` → non-zero exit naming the key.
- [ ] **Step 2: Run them.** `system/scripts/test.sh system/tests/units.bats` → the new tests FAIL with "unreplaced placeholder".
- [ ] **Step 3: Implement** a pre-pass in `render()` that replaces each whole-line `{{EXTRA_TIMES:<key>}}` before the sed chain (read the key with `config_get`, check it with a `^[1-4]$` match, then compute the times as above). Every other use of `{{EXTRA_TIMES` still meets the existing unreplaced-placeholder refusal.
- [ ] **Step 4: Run the suite** → PASS, including the existing placeholder tests.
- [ ] **Step 5: Commit** `feat(units): {{EXTRA_TIMES:<key>}} adds a timer's extra runs from a config key (#236)`.

### Task 5: Docs, spec correction, cap, change file, roadmap

**Files:**
- Modify: `FOUNDRY.md:119` (one sentence on `commands`)
- Modify: `docs/superpowers/specs/2026-10-31-market-watch-design.md` §3.3 (Ruling 1 and Ruling 4)
- Modify: `system/tests/vault_integrity.bats:9` and the reason comments at `:521`
- Create: `changes/2026-11-06-extension-commands.md`
- Modify: `docs/superpowers/roadmap.md:104` (item 6 in progress)

- [ ] **Step 1: FOUNDRY.md.** After the `budget` sentence on line 119, add: an extension's `commands: [{name, targets, model_key, timeout_key}]` declares a headless run that `system/scripts/run_headless.sh <name>` starts when the extension is enabled, with its prompt in `extensions/<name>/commands/<command>.md`, targets under `briefings/<command>/` (`<date>` is today), and its model and time limit read from the two config keys (the limit is at most the harness's own).
- [ ] **Step 2: Spec.** In §3.3, the `targets` bullet reads "path patterns under `briefings/<name>/`, with `<date>` filled in at run time (a `wiki/` target waits for an extension that needs one; PR 1 Ruling 1)", and "default 15" in "It is capped" reads "default 20".
- [ ] **Step 3: Measure the cap.** Run `system/scripts/test.sh system/tests/vault_integrity.bats`. If the core test fails, set `CORE_CAP` to the measured count and add the reason comment in the existing form: `16,920 -> <n> (#236, market watch spec §3.3 and §3.6, owner to approve at merge): extension commands in run_headless.sh, publish.py, commit_runs.py, extensions.py and install_units.sh, measured from 16,916 to <n>`.
- [ ] **Step 4: Change file** `changes/2026-11-06-extension-commands.md`: `- Added: an extension can declare a headless command (\`commands\` in its manifest) that \`run_headless.sh <name>\` runs and the publish gate accepts, and a unit template's \`{{EXTRA_TIMES:<key>}}\` adds extra timer runs from a config key (#<PR number>)`.
- [ ] **Step 5: Roadmap.** Item 6's last sentence becomes: "In progress (owner, 2026-11-06: build this morning): PR 1, extension commands, is #<PR number>."
- [ ] **Step 6: Run** `system/scripts/test.sh system/tests/vault_integrity.bats system/tests/conformance.bats system/tests/commands.bats` → PASS.
- [ ] **Step 7: Commit** `docs(market): extension commands in FOUNDRY.md, spec rulings, cap and change file (#236)`.
