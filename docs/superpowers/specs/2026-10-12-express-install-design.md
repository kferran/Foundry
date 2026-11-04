# Express install: clone, answer three questions, read a brief

**Date:** 2026-10-12
**Status:** Approved for build. The scope is `2026-10-11-simplification-review.md` §4 step 1; the owner's decisions of 2026-10-11 and 2026-10-12 are in §2.
**Issue:** Part of #122 (step 1). Includes #117.

## 1. Problem

A new user today installs test tools and a desktop dependency, answers about 25 setup questions, gets two units nobody named (Work Orders and the daily template update), may create the vault in a way the daily update cannot merge, and sees the first brief the next morning. The review (§2.1) lists each item with its line numbers.

## 2. Decisions

- **The focus tracker is deleted** (owner, 2026-10-11). It is the only desktop dependency and the one feature that cannot run on a server or a client.
- **Clone only** (owner, 2026-10-12). `README.md` and `FOUNDRY.md` stop offering "Use this template"; `update_template.sh` keeps refusing unrelated histories with its current message. If the GitHub repository is flagged as a template repository, the button still shows: unflagging it is the owner's setting.
- **Test tools are development tools** (owner, 2026-10-12). `bats`, `pytest` and `shellcheck` are no longer required. `verify_setup.sh` runs `lint_vault.sh` first, then the suites when `bats` and `pytest` are installed, and prints `SKIP suites: bats or pytest is not installed (development tools)` in its summary when they are not. `/backup` and setup's verify phase inherit that rule. The `SKIP` line stays in the summary, so a development machine missing a tool shows it on every gate run.
- **Work Orders and the template update are opt-in, without touching existing vaults.** Two config keys, `orders_enabled` and `update_enabled`, both `bool` with **schema default `"true"`**: a vault whose config lacks them keeps both units, including through its next unattended `update_template.sh`. `config.example.md` sets both to `"false"`, so a vault created from now on starts with them off, and setup asks.
- **Setup asks three questions on a standalone machine**: role, brief time, debrief time. The timezone is read from the machine (`timedatectl show -p Timezone --value`, falling back to `/etc/timezone`) and shown, not asked. `default_partition` is written as `personal` without asking. Superpowers, digest thresholds and the recall budget are not asked: the brief ties objectives to a superpower only "where one fits", and the others have schema defaults. The report says how to change each.
- **One features list.** After the interview, setup shows every optional block in one list with its current state (codebases, private remote, memory hooks, calendar, telemetry, meetings, inbox triage, Jira handoffs and RCA filing, Slack notices, Work Orders, daily template update) and asks once which to set up. Only chosen blocks run. A block not chosen is left as it is. On a server or a client the private remote is required and is not offered.
- **A codebase is one confirmation.** Setup drafts `system/codebases/<name>.md` from the inspection and shows the whole draft once; the user accepts it or names the fields to change.
- **The first brief runs at the end of setup** on a standalone machine or a server (a client gets the server's brief through sync).
- **A vault path with spaces is refused in phase 0**, before anything is written: the memory hooks refuse such a path, and the units accept it. `install_units.sh` keeps accepting spaces, so an existing vault at such a path is not broken by its next update.
- **#117: the template update runs at `brief_time` minus 45 minutes** (05:15 for a 06:00 brief), rendered like the clearing-house watcher's time (`brief_time` minus 30). A fixed 05:15 would run after the watcher, or after the brief, for an early `brief_time`.
- **`bwrap` is a runtime dependency** on a standalone machine and a server: `headless.settings.json` turns the sandbox on.

## 3. Changes

Five pull requests, each standing alone, in this order.

### 3.1 Delete the focus tracker

Remove `system/scripts/track_obsidian.sh`, `system/scripts/focus_stats.sh`, `system/systemd/foundry-focus.service.in` and `system/tests/focus.bats`. Remove the focus parts of `install_units.sh`, `check_deps.sh` (`hyprctl` and its hint), `brief_prep.sh`, `debrief_prep.sh`, `brief.md` (the `focus_yesterday` input and the Focus Drift part of 🛑 Blockers), `debrief.md`, `setup.md` (phases 0 and 5), the Focus Fragmentation line in `CLAUDE.md`, and `FOUNDRY.md` (the debrief row, Brief inputs, debrief inputs, the "Friction and focus" paragraph, which keeps its friction sentences, the units list, the machine roles table and Requirements). Update the tests that expect them: `prep.bats`, `units.bats`, `remote.bats`, `setup.bats`, `commands.bats`, `vault_integrity.bats`, `system_health.bats`.

**Existing vault:** the next `update_template.sh` merge removes the scripts. `install_units.sh --update` keeps only owned units still in its list, so it disables and removes `foundry-focus.service` (`removed foundry-focus.service`). Briefs and debriefs stop listing focus.

### 3.2 Stagger the template update (#117)

`foundry-update.timer.in` uses a new `{{UPDATE_TIME}}` placeholder, `brief_time` minus 45 minutes, computed beside `clearinghouse_time`. `units.bats`, `FOUNDRY.md` and `setup.md` stop saying 05:30.

**Existing vault:** the next update re-renders the timer at the new time.

### 3.3 Dependency tiers and the gate

- `check_deps.sh`: standalone and server require `claude git jq systemctl python3 flock timeout pyyaml fts5 systemd-analyze bwrap`; the client list is unchanged. `bats`, `pytest` and `shellcheck` print as `dev <item> <hint>`, a new status that never fails `--strict`.
- `verify_setup.sh`: lint first, the suites when the tools are present, the `SKIP` summary line otherwise. `--health` runs `system_health.bats` only when `bats` is present.
- `/backup` step 1 runs `verify_setup.sh` on every role (the client special case goes), step 2 only when `bats` is present. Setup's verify phase runs `verify_setup.sh --health` and `list-timers` on every role, and reports a `SKIP` line as "test tools not installed, lint passed".
- `FOUNDRY.md` Development lists `bats`, `pytest` and `shellcheck` as what a template developer installs.

**Existing vault:** none until bats or pytest is uninstalled; then `/backup` lints instead of failing.

### 3.4 Opt-in units

- Schema keys `orders_enabled` and `update_enabled` (default `"true"`); `config.example.md` sets both `"false"`.
- `install_units.sh` adds the Work Orders units and the update units only when their key is true, in every mode.
- `remote.bats` (or `units.bats`): a config with neither key keeps both units through `--update` and a plain run; a config with `false` installs neither; `true` installs both.

**Existing vault:** none. Its config lacks both keys, so both units stay.

### 3.5 The setup flow and the docs

- `setup.md`: phase 0 refuses a path with spaces; phase 2 asks brief and debrief times, reads the timezone, writes `default_partition`; a new phase 2a is the features list, which writes `orders_enabled`, `update_enabled`, `meetings_enabled` and `triage_enabled` from the answers before phase 5 so the unit dry run already reflects them; phases 3 to 6d each start with "only when chosen in 2a" (phase 4 always runs on a server or a client); phase 3 shows one draft per codebase; the later "re-run the dry run" steps stay only where a key is written after phase 5 (telemetry sources, the Slack channel); a final phase runs `/brief` on a standalone machine or a server.
- `README.md` and `FOUNDRY.md`: clone only; `FOUNDRY.md`'s phase list matches `setup.md`, including 2a, 6a to 6d and 9a, with one client skip list; Requirements list the three tiers.
- `commands.bats`: the pins that name changed text, kept beside their current tests.

**Existing vault:** re-running `/setup` shows the features list with the vault's current state; nothing changes until the owner picks a block.

## 4. Tests

Each change has a test that fails before it:
- 3.1: `vault_integrity.bats` no longer lists the deleted scripts; `units.bats` expects no `foundry-focus` and a `removed foundry-focus.service` line from `--update` on a vault that owns it; `prep.bats` expects no focus file.
- 3.2: `units.bats` checks the update timer at 05:15 for a 06:00 brief and at 07:15 for an 08:00 brief.
- 3.3: `setup.bats` checks the `dev` lines and that `--strict` passes without bats; `scripts.bats` checks the `SKIP` line and exit 0 with a PATH that lacks bats, and exit 1 when lint fails.
- 3.4: the migration test above.
- 3.5: `commands.bats` pins the features list, the timezone read, the space refusal and the final `/brief`.

Bound tools: bats, pytest, `verify_setup.sh`.

## 5. Out of scope

- The helper layer, extensions and the prompt layer (steps 2 to 4).
- Whether Claude Code's sandbox on Linux also needs `socat`: checked on a clean host before it becomes a requirement (a checklist line on #122).
- A dependency installer: `check_deps.sh` keeps printing hints.
