# Express Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new user clones the template, answers three setup questions, picks features from one list, and reads a brief before setup ends; nothing in an existing vault changes on its next update except the focus tracker's removal and the update timer's new time.

**Architecture:** Five pull requests, each branched from master and merged before the next starts: delete the focus tracker, stagger the update timer, tier the dependencies and the gate, make Work Orders and the update opt-in through config keys whose schema default keeps existing vaults as they are, and rewrite the setup flow and the docs.

**Tech Stack:** bash, systemd user units, Python 3 (`vault_index.py`), bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-12-express-install-design.md`

## Global Constraints

- Template rule: no hostname, user path, remote URL, distro choice, account ID, or employer, client, codebase or people names in any file.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- New tests go beside the related tests, never appended at the end of `commands.bats`.
- Per-suite runs: `system/scripts/test.sh <suite.bats | pytest path>`. The full gate: `system/scripts/verify_setup.sh`, outside the sandbox, one at a time.
- Each PR body says "Part of #122" and lists what changes for an existing vault.
- `orders_enabled` and `update_enabled`: `bool`, schema default `"true"`; `config.example.md` sets `"false"`.
- Update time: `brief_time` minus 45 minutes, modulo a day.

## Review Focus

1. A vault whose `config.md` has neither `orders_enabled` nor `update_enabled` runs `install_units.sh --update`: both timers stay installed and enabled (Task 4 test).
2. A vault that owns `foundry-focus.service` runs `--update`: the unit is disabled and removed, nothing else changes (Task 1 test).
3. `brief_time` 00:30: the update timer renders at 23:45, a valid `OnCalendar` (Task 2 test).
4. `verify_setup.sh` with lint failing and no bats: exit 1, not a skip (Task 3 test).
5. A server with no `bwrap`: `check_deps.sh --strict` fails with an install hint (Task 3 test).

---

### Task 1: Delete the focus tracker (PR 1)

**Files:**
- Delete: `system/scripts/track_obsidian.sh`, `system/scripts/focus_stats.sh`, `system/systemd/foundry-focus.service.in`, `system/tests/focus.bats`
- Modify: `system/scripts/install_units.sh:80-83`, `system/scripts/check_deps.sh:25,49`, `system/scripts/brief_prep.sh:2,48-55`, `system/scripts/debrief_prep.sh:2,105-109`, `.claude/commands/brief.md:2,24,68`, `.claude/commands/debrief.md:2,24,40`, `.claude/commands/setup.md:13,44`, `CLAUDE.md:84`, `FOUNDRY.md:69,83,103,114,180,193,229`
- Test: `system/tests/units.bats`, `prep.bats`, `remote.bats:231`, `setup.bats`, `commands.bats:392,417,530,546,549`, `vault_integrity.bats:21`, `system_health.bats:63-66`

**Interfaces:** Produces: standalone `UNITS`/`ENABLE` without `foundry-focus.service`; `check_deps.sh` standalone and server lists identical.

- [ ] **Step 1: Change the tests first.** In `units.bats`, drop `foundry-focus.service` from `UNITS` (line 6) and from the services loop (line 45); rename the enable test to "installing reloads systemd and enables the three timers" and expect `--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-nightshift.timer foundry-update.timer`; in the server test drop the focus skip and the `[ ! -e … focus ]` line and rename it "machine_role server installs the run units and the sync timer"; rewrite the role-change test to check `removed foundry-sync.timer` when going from server back to standalone; in the `--update` test (line 456) drop `foundry-focus.service`. Add beside the `--update` test:

```bash
@test "--update removes a focus tracker an older template installed" {
  "$IU" > /dev/null
  printf '# Managed by vault: %s\n[Service]\nExecStart=/bin/true\n' "$VP" > "$UD/foundry-focus.service"
  : > "$STUB_SYSTEMCTL_LOG"
  run "$IU" --update
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-focus.service' <<< "$output"
  [ ! -e "$UD/foundry-focus.service" ]
  grep -qx -- '--user disable --now foundry-focus.service' "$STUB_SYSTEMCTL_LOG"
}
```

In `setup.bats`, remove `hyprctl` from the stub list and every expectation; rename "--role server needs everything except hyprctl" to "check_deps: --role server needs what standalone needs" and keep its bats-missing assertion; in "the role defaults to the config's machine_role" use `rm "$BIN/jq"` and `missing jq` in place of hyprctl. Delete `system_health.bats:63-66`, the focus lines in `commands.bats`, `vault_integrity.bats:21`'s two script names, `remote.bats:231`'s focus expectation, and the `prep.bats` focus cases (keep each test whose subject is something else; remove only its focus lines). Add to `prep.bats` beside the first `brief_prep` test:

```bash
@test "brief_prep and debrief_prep write no focus inputs" {
  run system/scripts/brief_prep.sh
  [ ! -e system/logs/prep/focus_yesterday.md ]
  run system/scripts/debrief_prep.sh
  [ ! -e system/logs/prep/focus.md ]
}
```

(Use the prep directory the neighbouring tests use; read them first.)

- [ ] **Step 2: Run** `system/scripts/test.sh system/tests/units.bats` and `system/tests/prep.bats`. Expected: the new tests and the changed enable lines FAIL.
- [ ] **Step 3: Remove the code.** `git rm` the four files. In `install_units.sh` drop `foundry-focus.service` from both standalone arrays. In `check_deps.sh` drop `hyprctl` from the standalone list and its `hint` case. Remove the focus blocks and header words in both prep scripts. In `brief.md` remove the `focus_yesterday` input and the Focus Drift part; in `debrief.md` the focus input and the "Omit the Focus paragraph" sentence; in `setup.md` the hyprctl note in phase 0 and `foundry-focus` in phase 5; the Focus Fragmentation line in `CLAUDE.md`; in `FOUNDRY.md` every focus mention listed above (the "Friction and focus." paragraph keeps its friction sentences and becomes "**Friction.**").
- [ ] **Step 4: Run** `grep -rn -i 'focus_stats\|track_obsidian\|foundry-focus\|hyprctl\|hyprland\|focus drift\|focus fragmentation' --exclude-dir=.scratch --exclude-dir=superpowers .`. Expected: no output. Then `system/scripts/test.sh` on `units.bats`, `prep.bats`, `setup.bats`, `commands.bats`, `vault_integrity.bats`, `remote.bats`. Expected: PASS.
- [ ] **Step 5: Full gate**, then commit `feat(setup): delete the focus tracker (#122 step 1)` and open the PR (existing vault: the next update removes `foundry-focus.service`; briefs stop listing focus).

### Task 2: Stagger the template update (PR 2, #117)

**Files:**
- Modify: `system/systemd/foundry-update.timer.in:5`, `system/scripts/install_units.sh:179-182,201-202`, `.claude/commands/setup.md` (phase 5), `FOUNDRY.md:305`
- Test: `system/tests/units.bats:432-448`

**Interfaces:** Produces: placeholder `{{UPDATE_TIME}}`, `HH:MM`.

- [ ] **Step 1: Failing test.** Rename the test at line 432 to "standalone and server get the template update 45 minutes before the brief, a server with its sync drop-in (#87, #117)" and change its `OnCalendar` line to `05:15:00`. Add beside it:

```bash
@test "the update time follows brief_time and wraps past midnight (#117)" {
  system/scripts/vault_index.py set system/config.md brief_time 08:00 > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'OnCalendar=\*-\*-\* 07:15:00 America/Denver' "$UD/foundry-update.timer"
  system/scripts/vault_index.py set system/config.md brief_time 00:30 > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'OnCalendar=\*-\*-\* 23:45:00 America/Denver' "$UD/foundry-update.timer"
}
```

- [ ] **Step 2: Run** `system/scripts/test.sh system/tests/units.bats`. Expected: both FAIL (05:30 rendered).
- [ ] **Step 3: Implement.** In `install_units.sh` after `clearinghouse_time`:

```bash
t=$(( (10#$bh * 60 + 10#$bm + 1395) % 1440 ))
update_time="$(printf '%02d:%02d' $(( t / 60 )) $(( t % 60 )))"
```

add `-e "s|{{UPDATE_TIME}}|$(esc "$update_time")|g"` to `render`, and set the timer line to `OnCalendar=*-*-* {{UPDATE_TIME}}:00 {{TZ}}`. Replace "at 05:30" in `setup.md` phase 5 and `FOUNDRY.md:305` with "45 minutes before the brief".
- [ ] **Step 4: Run** `units.bats` and `commands.bats`. Expected: PASS.
- [ ] **Step 5: Full gate**, commit `fix(update): run the template update 45 minutes before the brief (#117)`, PR "Closes #117. Part of #122."

### Task 3: Dependency tiers and the gate (PR 3)

**Files:**
- Modify: `system/scripts/check_deps.sh`, `system/scripts/verify_setup.sh`, `.claude/commands/backup.md:7-8`, `.claude/commands/setup.md` (phase 8), `FOUNDRY.md` (Requirements, Development, `/backup` row)
- Test: `system/tests/setup.bats`, `system/tests/commands.bats:395-398` and the phase 8 pin at `:377-378`

**Interfaces:** Produces: `check_deps.sh` status word `dev`; `verify_setup.sh` summary lines `PASS lint`, `FAIL lint (exit N)`, `SKIP suites: bats or pytest is not installed (development tools)`.

- [ ] **Step 1: Failing tests** in `setup.bats`. Add `bwrap` to the linked/stubbed tools in `setup()` (stub it like `claude`). Change "every item present" to expect `ok bwrap` and `ok bats`/`ok pytest`. Add beside it:

```bash
@test "check_deps: test tools are development tools and never fail --strict" {
  rm "$BIN/bats"
  run env PATH="$BIN" "$CD" --strict
  [ "$status" -eq 0 ]
  grep -qx 'dev bats sudo pacman -S bash-bats' <<< "$output"
  run env PATH="$BIN" "$CD" --strict --role server
  [ "$status" -eq 0 ]
}

@test "check_deps: bwrap is required on standalone and server, not on a client" {
  rm "$BIN/bwrap"
  run env PATH="$BIN" "$CD" --strict --role server
  [ "$status" -eq 1 ]
  grep -qx 'missing bwrap sudo pacman -S bubblewrap' <<< "$output"
  run env PATH="$BIN" "$CD" --strict --role client
  [ "$status" -eq 0 ]
}
```

Change the server test's `rm "$BIN/bats"` assertion to `rm "$BIN/jq"`. In `mini_vault()` add a lint stub: `printf '#!/bin/bash\nexit "${FAKE_LINT_RC:-0}"\n' > "$M/system/scripts/lint_vault.sh"; chmod +x "$M/system/scripts/lint_vault.sh"`. Add beside the verify tests:

```bash
@test "verify_setup: lint runs first and the suites are skipped, loudly, without bats" {
  mini_vault
  BIN2="$BATS_TEST_TMPDIR/bin2"
  mkdir -p "$BIN2"
  for c in bash env mkdir python3; do ln -s "$(command -v "$c")" "$BIN2/$c"; done
  run env PATH="$BIN2" "$VS"
  [ "$status" -eq 0 ]
  grep -qx 'PASS lint' <<< "$output"
  grep -qx 'SKIP suites: bats or pytest is not installed (development tools)' <<< "$output"
}

@test "verify_setup: a lint failure fails the run with or without the suites" {
  mini_vault
  FAKE_LINT_RC=3 run "$VS"
  [ "$status" -eq 1 ]
  grep -qx 'FAIL lint (exit 3)' <<< "$output"
  grep -qx 'PASS system/tests/a.bats' <<< "$output"
}
```

(If `python3` on the host has pytest, `BIN2` still lacks `bats`, which is enough for the skip.)
- [ ] **Step 2: Run** `system/scripts/test.sh system/tests/setup.bats`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** `check_deps.sh`: standalone and server `REQUIRED=(claude git jq systemctl python3 flock timeout pyyaml fts5 systemd-analyze bwrap)`; after the required loop, `if [[ "$role" != client ]]; then for item in bats pytest shellcheck; do report "$item" "$(present "$item")" dev; done; fi`; `report` prints `dev $1 $(hint "$1")` for a third argument of `dev`; drop the `bwrap` optional report; add `shellcheck) pkg_pacman=shellcheck pkg_apt=shellcheck ;;` to `hint`; update the header comment to name the `dev` status. `verify_setup.sh`, before the suites:

```bash
gate lint system/scripts/lint_vault.sh
if command -v bats >/dev/null 2>&1 && python3 -m pytest --version >/dev/null 2>&1; then
  # (existing suite discovery, the bats loop and the pytest gate move inside this branch)
else
  results+=("SKIP suites: bats or pytest is not installed (development tools)")
fi
```

and wrap the `--health` block in the same `command -v bats` check, else `results+=("HEALTH skipped: bats is not installed")`. Update the header comment. `backup.md` step 1: "Run `system/scripts/verify_setup.sh` on every role: it lints, then runs the suites when bats and pytest are installed." Step 2: "Skip this step on a client or when `bats` is not installed." `setup.md` phase 8: run `verify_setup.sh --health` on every role and `list-timers` except on a client; report a `SKIP` line as "test tools not installed; lint passed". `FOUNDRY.md`: Requirements lists runtime, development and optional tiers; Development says a template developer installs `bats`, `pytest` and `shellcheck`.
- [ ] **Step 4: Run** `setup.bats`, `commands.bats` (fix the backup and phase 8 pins in place), then the full gate. Expected: PASS, with `PASS lint` in the summary.
- [ ] **Step 5: Commit** `feat(setup): test tools are development tools; the gate lints first (#122 step 1)`, PR.

### Task 4: Opt-in Work Orders and template update (PR 4)

**Files:**
- Modify: `system/schemas/config.md`, `system/config.example.md`, `system/scripts/install_units.sh:113-122`
- Test: `system/tests/units.bats` (beside the nightshift and update tests), `system/tests/python/test_schema_notes.py` only if it pins the key list

**Interfaces:** Produces: config keys `orders_enabled`, `update_enabled` (`bool`, default `"true"`).

- [ ] **Step 1: Failing tests** in `units.bats`, beside "standalone and server get the nightshift timer":

```bash
@test "Work Orders and the update are installed when their keys are absent, so existing vaults keep them" {
  run "$IU"
  [ "$status" -eq 0 ]
  [ -e "$UD/foundry-nightshift.timer" ]
  [ -e "$UD/foundry-update.timer" ]
  : > "$STUB_SYSTEMCTL_LOG"
  run "$IU" --update
  [ "$status" -eq 0 ]
  [ -e "$UD/foundry-nightshift.timer" ]
  [ -e "$UD/foundry-update.timer" ]
  grep -q 'enable --now .*foundry-nightshift.timer.*foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "orders_enabled and update_enabled false install neither, and remove them when they were installed" {
  run "$IU"
  system/scripts/vault_index.py set system/config.md orders_enabled false > /dev/null
  system/scripts/vault_index.py set system/config.md update_enabled false > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'removed foundry-nightshift.timer' <<< "$output"
  grep -qx 'removed foundry-update.timer' <<< "$output"
  [ ! -e "$UD/foundry-nightshift.timer" ]
  [ ! -e "$UD/foundry-update.timer" ]
}

@test "the committed example starts a new vault with Work Orders and the update off" {
  grep -qx 'orders_enabled: "false"' "$REPO/system/config.example.md"
  grep -qx 'update_enabled: "false"' "$REPO/system/config.example.md"
}
```

- [ ] **Step 2: Run** `units.bats`. Expected: the second and third FAIL (`vault_index.py set` rejects an unknown key, or the units stay).
- [ ] **Step 3: Implement.** Schema: `orders_enabled: {kind: bool, default: "true"}` and `update_enabled: {kind: bool, default: "true"}`, with one body paragraph: "`orders_enabled` and `update_enabled` turn on the Work Orders tick and the daily template update on a standalone machine or a server. Absent means on, so vaults made before 2026-10-12 keep both; the example config sets both to `false`, and `/setup` asks." Example: add both as `"false"` beside `triage_enabled`. `install_units.sh`: wrap the two blocks in `[[ "$(config_get orders_enabled true)" == true ]]` and `[[ "$(config_get update_enabled true)" == true ]]`.
- [ ] **Step 4: Run** `units.bats`, `remote.bats`, `vault_integrity.bats`, the schema pytest, then the full gate. Expected: PASS.
- [ ] **Step 5: Commit** `feat(units): Work Orders and the template update are opt-in for new vaults (#122 step 1)`, PR (existing vault: nothing changes; its config lacks both keys).

### Task 5: The setup flow and the docs (PR 5)

**Files:**
- Modify: `.claude/commands/setup.md`, `README.md:16`, `FOUNDRY.md:9,243,274-287`
- Test: `system/tests/commands.bats` (the setup and README tests, in place)

**Interfaces:** Consumes: `orders_enabled`, `update_enabled` (Task 4), `dev` status and the `SKIP` line (Task 3).

- [ ] **Step 1: Failing tests** in `commands.bats`, beside "/setup asks the machine role first":

```bash
@test "express install: three questions, one features list, the first brief (#122 step 1)" {
  sec="$(setup_section '0. Role and preflight')"
  [[ "$sec" == *'contains a space'* ]]
  sec="$(setup_section '2. Interview')"
  [[ "$sec" == *'timedatectl show -p Timezone --value'* ]]
  [[ "$sec" == *'default_partition personal'* ]]
  [[ "$sec" != *'superpowers (strategic anchors'* ]]
  sec="$(setup_section '2a. Features')"
  for k in orders_enabled update_enabled meetings_enabled triage_enabled; do [[ "$sec" == *"$k"* ]]; done
  [[ "$sec" == *'Ask once'* ]]
  sec="$(setup_section '3. Codebases')"
  [[ "$sec" == *'show the whole draft once'* ]]
  sec="$(setup_section '11. First brief')"
  [[ "$sec" == *'/brief'* ]]
  run grep -c 'Use this template' README.md FOUNDRY.md
  [[ "$output" == *'README.md:0'* ]]
  [[ "$output" == *'FOUNDRY.md:0'* ]]
}
```

- [ ] **Step 2: Run** `commands.bats`. Expected: FAIL.
- [ ] **Step 3: Rewrite `setup.md`.**
  - Phase 0, before `check_deps.sh`: "If the vault path (`pwd -P`) contains a space, stop: the memory hooks cannot run from such a path. Ask the user to move the vault to a path without spaces and run `/setup` again there."
  - Phase 2, whole text: "Read the machine's timezone with `timedatectl show -p Timezone --value` (if that prints nothing, `cat /etc/timezone`) and show it; ask only if both print nothing, or if the user says it is wrong. Ask the brief time (`HH:MM`, default `06:00`) and the debrief time (`HH:MM`, default `17:00`). Write `timezone`, `brief_time` and `debrief_time` with `system/scripts/vault_index.py set system/config.md <key> <value>`, and run `system/scripts/vault_index.py set system/config.md default_partition personal` when `default_partition` is empty. On a client, write only the timezone and the default partition. Superpowers, digest thresholds and the recall budget keep their defaults; the report says how to change them. Then run `system/scripts/vault_index.py validate system/config.md`; on an error, show it, ask again for that value, and re-validate."
  - New phase 2a "Features": "Show one numbered list of the optional blocks with each one's current state, read from config and the files that hold it: 1 codebases (phase 3), 2 a private remote for backups (phase 4; on a server or a client it is required and not listed), 3 memory hooks (5a), 4 the calendar in the brief (6), 5 error telemetry (6a), 6 meetings from Google Drive (6b), 7 inbox triage (6b), 8 Jira handoffs and RCA filing (6c), 9 Slack notices (6d), 10 Work Orders (`orders_enabled`), 11 the daily template update (`update_enabled`). A client gets no list: phase 4 runs there as required, and the other blocks do not run on a client. Ask once which numbers to set up or change; an empty answer changes nothing. Write `orders_enabled`, `update_enabled`, `meetings_enabled` and `triage_enabled` now (`true` for a chosen 6, 7, 10 or 11; leave the others as they are), so phase 5's dry run already shows their units. A block not chosen is skipped and reported as unchanged."
  - Phases 3, 5a, 6, 6a, 6b (each half), 6c and 6d start with "Only when chosen in 2a." Phase 4 starts "On a standalone machine, only when chosen in 2a; when it is not chosen and `remote_mode` is empty, run `system/scripts/setup_remote.sh --none`."
  - Phase 3 step 3: replace "Confirm each field with the user" with "Show the whole draft once and ask the user to accept it or name the fields to change".
  - Phase 5: list Work Orders (`orders_enabled`) and the template update (`update_enabled`) as following their keys; drop 6b's "re-run the dry run" for meetings and triage (2a wrote their keys); keep 6a's and 6d's.
  - New phase 11 "First brief": "On a standalone machine or a server, run `/brief` now so the user sees the product before leaving setup. On a client, say the server writes the brief and sync brings it here."
  - Phase 10's report table lists superpowers, thresholds and the recall budget as "defaults; change with `system/scripts/vault_index.py set`".
- [ ] **Step 4: Docs.** `README.md:16` and `FOUNDRY.md:243`: `git clone <template-url> my-vault` with no comment. `FOUNDRY.md:9`: "You clone it". `FOUNDRY.md:274-287`: rewrite the phase list to match `setup.md` (0, 1, 2, 2a, 3, 4, 5, 5a, 6, 6a, 6b, 6c, 6d, 7, 8, 9, 9a, 10, 11), with the client skips once.
- [ ] **Step 5: Run** `commands.bats` (update the pins whose text changed, in place), then the full gate. Expected: PASS.
- [ ] **Step 6: Commit** `feat(setup): three questions, one features list, the first brief (#122 step 1)`, PR (existing vault: nothing changes until `/setup` is re-run).

## After the five PRs

- Roadmap: step 1 complete; the server brief noise row closed.
- #122: tick step 1; add the `socat` check line.
