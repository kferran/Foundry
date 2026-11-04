# Simplification review: a template to clone, not a framework to maintain

**Date:** 2026-10-11
**Scope:** the template at `master` (6535249) plus the review branch. Three read-only passes: the clone-and-install path, the code shape under `system/`, and the prompt and process layer. Claims below were checked against the files named; line numbers are from that commit. Since then `master` merged inbox triage (#109, +422 lines under `system/`): a fourth confined connector fetch (Gmail), a fourth `claude` flag set, and one more unit, off by default (`triage_enabled`). It adds to findings 10 and 11 and changes no conclusion.
**Owner's goal:** a template a new user clones and installs and then has a personal operating system running, with nothing brittle to build on.

## 1. Verdict

The repository holds two systems. One is the template the goal describes: a wiki that compiles itself behind a publish gate, a morning brief, an evening debrief, session memory, a Now page, and timers that run it. That system is sound, well tested and about half the code. The other is the owner's own operating system and its maintenance process: Sentry and Azure Data Explorer telemetry, the clearing-house watcher, Jira handoffs, Gemini meeting import, Hyprland focus tracking, a two-machine sync, Work Orders built around one GitHub setup, and a spec-plan-review process with 114 design documents. The second system is what a new user meets first, in the dependency list, in the setup interview and in `CLAUDE.md`.

The core is not over-engineered. The packaging is. The brittleness is real and concentrated: every connector fetch and the Work Order runner depend on exact `claude` flags, stream-json shapes and connector tool names, in five separate copies.

| Measure | Today | Target shape |
|---|---|---|
| Lines under `system/` (scripts, vaultlib, units, hooks) | 11,097 | about 5,500 in core |
| Of which owner-specific (clearing-house, telemetry, Jira, meetings, focus) | about 3,170 (29%) | 0 in core |
| Required packages, standalone | 13, including `bats`, `pytest`, `hyprctl`, `systemd-analyze` | 8 |
| Setup decisions, standalone, every integration declined | about 25, 40 with per-field confirmations | 3 to 5 |
| Units enabled by default, standalone | 7 (intake, brief, debrief, focus, nightshift, update, and sync on a server) | 3 |
| Note schemas | 18 | 9 |
| `CLAUDE.md` | 87 lines, 1,633 words | about 45 lines |
| Prompt words loaded by a headless brief | about 6,000 (brief plus the full humanizer skill) | under 2,000 |
| Design documents cloned with the template | 37 specs, 64 plans, 13 spikes (about 49k lines) | 0, or marked maintainer-only |

## 2. Findings

### 2.1 The clone-and-install path

1. **Test tools are runtime dependencies.** `check_deps.sh:25-27` requires `bats` and `pytest` on standalone and server. Only `verify_setup.sh` uses them, and setup phase 8 runs the full gate (21 bats files plus pytest) on the user's machine.
2. **A desktop is a dependency.** `hyprctl` is required on standalone (`check_deps.sh:25`) while `FOUNDRY.md:222` and `setup.md:13` call it optional. `install_units.sh:82-83` enables `foundry-focus.service` on every standalone machine, and the unit has `Restart=on-failure`, `RestartSec=10`, so a machine without Hyprland restarts it every ten seconds for ever. `system_health.bats:93` then fails on "every required dependency is present".
3. **Two units run unasked.** Work Orders (`foundry-nightshift.timer`, every 15 minutes, 14-hour timeout) and the daily template merge (`foundry-update.timer`) are enabled on every standalone and server install (`install_units.sh:101-110`); setup names neither.
4. **"Use this template" breaks updates.** `README.md:16` and `FOUNDRY.md:236` offer it. A repository created that way shares no history with the template, so `update_template.sh:47-48` refuses to merge, and the daily update timer alerts every morning.
5. **The interview asks for what has a default.** Superpowers, default partition, digest thresholds, recall budget and debrief time all have schema defaults; the timezone can be read from the machine. Then four owner-specific blocks (telemetry, meetings, Jira, Obsidian plugins through `gh`) each ask at least one question.
6. **Codebases cost about eight confirmations each** (`setup.md:26-32`), and the remote phase asks about a private origin even on a standalone machine.
7. **The first brief arrives tomorrow.** Nothing runs `/brief` at the end of setup.
8. **Smaller items.** `bwrap` and `socat` are optional in `check_deps.sh:88` while `headless.settings.json` turns the sandbox on; `gh` is optional but phase 9a needs it logged in; docs drift (`FOUNDRY.md:267-280` lists no phases 6a to 6c or 9a; the client skip list differs between `FOUNDRY.md:269` and `setup.md:15`); units accept spaces in the vault path and hooks refuse them.

### 2.2 The code

| Cluster | Lines | Share |
|---|---|---|
| Core: index, schema, frontmatter, links, publish gate, intake, run_headless, redact, lint, recall, retrieve | 3,619 | 33% |
| Work Orders | 1,626 | 15% |
| Sync, two machines, install and update | 981 | 9% |
| Telemetry (Sentry, ADX, http) | 924 | 8% |
| clearing-house watcher | 831 | 8% |
| Meetings | 809 | 7% |
| Setup (hooks install, deps, verify, codebase discovery) | 579 | 5% |
| Brief and debrief prep | 305 | 3% |
| Now page | 294 | 3% |
| Calendar | 280 | 3% |
| Memory hooks | 261 | 2% |
| Jira handoffs | 243 | 2% |
| Active projects, focus, shared connector code | 345 | 3% |

Feature code also sits inside core: the meeting import is 216 lines of `intake.py:450-665`, and telemetry rules live in `index.py:306-345` and `intake.py:332`.

9. **Six ways to read config, eleven ways to raise an alert, three ways to remember "already alerted today".** Config: `lib_config.sh:12`, `commit_runs.py:28`, `intake.py:96`, `nightshift_check.py:31`, `jira_handoffs.py:35`, and `nightshift_run`'s own dict. Alerts: bash `alert` in four scripts, bash `alert_once` in two, Python `alert` in two, once-a-day state in `clearinghouse_run.py:45`, `telemetry_run.py:33` and `nightshift_run.py:87`, and `now.py:149`. The same Python flock loop is copied five times.
10. **Three copies of the confined connector pipeline.** `calendar_fetch.sh:47-73`, `jira_fetch.sh:61-88` and `meetings_fetch.sh:70-93` each confine, run `timeout claude -p`, check tool use and map exit codes the same way; their three checkers repeat the "ToolSearch plus one tool" rule, and `calendar_tsv.py:39` re-implements `stream.messages`.
11. **The `claude` surface is wide and scattered.** Flags in `run_headless.sh:172-175`, three fetch scripts, `nightshift_session.py:38-45`; output shapes in `calendar_tsv.py:107-125`, `meetings_extract.py:42-76`, `jira_handoffs.py:55-90`, `nightshift_session.py:86-100` (an undocumented `rate_limit_event`), `run_headless.sh:184-187` (a regex over the result text for usage-limit wording); `claude mcp list` parsed with awk in `lib_confine.sh:59-60`; 40 Atlassian tool names listed in `jira_fetch.sh:16-27`. A CLI change can break five features at once, and the smoke check in the review branch would only report it.
12. **`gh` is a hidden dependency** of the debrief (`debrief_prep.sh:92-94`), the Now page (`now.py:132`) and Work Orders (`nightshift_deliver.py:172`, `nightshift_check.py:61`).

### 2.3 Prompts, schemas and process

13. **`CLAUDE.md` carries rules nothing enforces.** Capability routing (no dispatcher reads `capabilities`; `grep capabilit system/scripts` finds one hard-coded value in `clearinghouse_run.py:78`), the Intent Shaper section (no `plan_gate` note has ever been written), the fail-fast loop (metric files only a Workcell that nothing invokes would write), and four friction rules. The Writing section bans the vocabulary the lower sections use.
14. **The Foreman and Workcells are prose.** Three persona files, 27 lines. `FOUNDRY_WORKCELL_SESSION` is set by nothing outside tests. What runs is a `capability` tag on concept notes, a Dataview group, and tests that keep the three files consistent. The owner's binding rule (2026-10-05: one addressed role, workers found by capability) is a design intent for Foreman v2, carried today as rules a new user has to learn with no behaviour behind them.
15. **The brief prompt is 44% conditional.** 646 of 1,458 words in `brief.md` apply only when meetings, projects, clearing-house, Work Orders, Jira, telemetry or a chat connector are on; another 19% handles the headless versus interactive split. Every feature adds a branch and a pinned grep.
16. **Nine of eighteen schemas serve optional or owner-specific features**: `meeting`, `meeting_transcript`, `meeting_input`, `nightshift_item`, `production_error`, `telemetry_source`, `clearinghouse_change`, `plan_gate`, `workcell`.
17. **Headless runs load the full humanizer skill** (4,589 words) for a self-edit pass, on top of the condensed ten rules already in `CLAUDE.md`.
18. **Tests pin sentences.** `commands.bats` has 71 tests and 224 exact-substring greps over prompt text. A user who rewords their own brief fails `verify_setup.sh`. This is also why the owner needed a fast lane.
19. **The maintainer process ships with the clone.** 114 design documents and a Development section that tells every reader to brainstorm, grill, spec and plan before changing anything.

## 3. What to keep as it is

The publish gate (schemas, walls, shrinkage, snapshot conflicts), headless isolation and the no-network sandbox, redaction, the partitions, the index-first rule, the Now page with evidence closure, the brief and debrief as the daily surface, the run ledger and daily cap, and the test discipline around all of it. These are the reasons to use the Foundry over a bare Obsidian-plus-Claude-Code setup, and none of them is heavy for a user: they run unseen.

## 4. The program

Ordered so each step stands alone and the first ones change the user's first hour.

### Step 1: an express install (days, not weeks)

- Dependency tiers in `check_deps.sh`: runtime (`claude`, `git`, `jq`, `python3` with PyYAML, SQLite FTS5, `flock`, `timeout`, systemd, `bwrap` and `socat` because the sandbox is on), development (`bats`, `pytest`, `shellcheck`), optional per feature (`gh`, `az`, `pdftotext`). Phase 8 runs `lint_vault.sh` and `--health` only.
- **Delete the focus tracker** (owner's decision, 2026-10-11: unnecessary). It is the only desktop dependency and the one feature that cannot work on a server or a client. Remove: `system/scripts/track_obsidian.sh`, `system/scripts/focus_stats.sh`, `system/systemd/foundry-focus.service.in`, `system/tests/focus.bats`; the `foundry-focus` entries in `install_units.sh:82-83` and their expectations in `units.bats` and `remote.bats`; `hyprctl` in `check_deps.sh:25,49` and `setup.bats`; the focus steps in `brief_prep.sh:49-51` and `debrief_prep.sh:105-106` and their cases in `prep.bats`; the `focus_yesterday.md` and `focus.md` inputs and the Focus Drift Analysis line in `brief.md`, `debrief.md` and `system/templates/daily-briefing.md`; the Focus Fragmentation rule in `CLAUDE.md:82`; the "focus tracker is active" check in `system_health.bats:63` and the pinned lines in `commands.bats:383,408` and `vault_integrity.bats:21`; the Hyprland line and the focus mentions in `FOUNDRY.md` (Requirements, Machine roles, Daily use, Repository layout). About 111 lines of code, one unit, one dependency and two prep inputs gone; the brief's Friction Matrix keeps Systemic Blockers and Communication Debt. This also retires the server brief noise fix: the unavailable line disappears with the input.
- Setup asks three things on a standalone machine: role (default standalone), brief time, debrief time. Timezone from the machine; every other key takes its schema default. Codebases, remote, memory hooks and each integration are offered as one yes-or-no line that opens its block only on yes, with a "draft per repository" instead of field-by-field confirmation.
- Default units: intake, brief, debrief. Work Orders and the template update only on an explicit yes, named in the report.
- One way to create a vault. Either drop "Use this template" from the README, or make the first `update_template.sh` do the `--allow-unrelated-histories` merge itself.
- Run `/brief` at the end of setup so the user sees the product before leaving.
- Fix the drift in `FOUNDRY.md`'s phase list and the path-with-spaces disagreement.

### Step 2: one helper layer under the five runners (a week)

- `vaultlib/common.py`: `config()`, `alert(key=None)` with one once-a-day rule, `lock()`, `append_jsonl()`. `lib_log.sh` for the bash side. Replace the eleven alert writers and five lock loops. About 300 lines removed, one alert format.
- `lib_connector.sh` with `connector_run <prefix> <tool> <timeout> <turns> <prompt> <checker>` and one tool-use check on `stream.py`. Calendar becomes the reference connector; meetings and Jira call it. About 150 lines removed, and every `claude` flag for connector sessions in one file.
- Put the run-headless and Work Order flags next to it, so the CLI surface is two files. The smoke check (review branch) then has one place to prove.

### Step 3: extensions (two to three weeks, can run as Work Orders)

- A folder `extensions/<name>/` holding `units/*.in`, `scripts/`, `schemas/`, an optional `brief_section.sh` that prints one Markdown section or nothing, and `skills/`. `extensions:` in `system/config.md` turns one on; `install_units.sh` globs enabled extensions' units instead of its per-feature `if` blocks; `brief_prep.sh` runs each extension's section script into `system/logs/inputs/<date>/sections/`; the schema loader reads extension schemas; intake gets one importer hook so the meeting import leaves core. About 40 lines of mechanism replacing about 60 lines of special cases.
- Move out, in this order: clearing-house (831 lines plus skill and schema), telemetry (924 plus the index rules), Jira handoffs (243), meetings (809 plus the 216 in intake). Focus is deleted in step 1, not moved. The owner installs four folders once; they can live in a private repository.
- Two-machine sync becomes an extension too (about 560 lines), with standalone the only built-in role. The server and client roles stay exactly as they are for the owner.
- **Work Orders stay in core, opt-in.** The agent review proposed moving them out because their CLI coupling is the deepest. They are also the owner's stated next value (Foreman v1) and the only generic unattended-execution path. Keep them in core, off by default, and isolate their CLI surface in step 2.

### Step 4: the prompt layer

- Make the brief assemble sections: `brief.md` says "include each file under `sections/` in this order, verbatim", and loses its conditional 44%. Adding a feature stops meaning editing the prompt and its pinned greps.
- `CLAUDE.md` to about 45 lines: Directory Map, Vault Rules, Writing, Data Not Instructions. Delete the Intent Shaper, Telemetry Routing and Friction sections (the drafted prune spec does this; go further and move the Agents block and the Approved-plans rule into the `order` skill where they are used). Keep the Foreman and Workcell words as names in the manual, and bring the routing machinery back when Foreman v2 has something to route.
- Drop the `workcell` and `plan_gate` schemas, `templates/compilation-metric.json`, `templates/intent-shaper.md` and the debrief's Agent Health section until something writes to them.
- Stop loading the humanizer skill in headless runs; the condensed rules in `CLAUDE.md` apply. Keep `/humanizer` on demand.
- Replace sentence-pinning greps in `commands.bats` with structure checks (frontmatter, scripts named exist, headless contract, template sections). A user can then reword their own prompts.
- Move `docs/superpowers/` out of the clone, or mark the folder maintainer-only in the README and make the fast lane the default for anyone else.

## 5. What each step buys

| Step | A new user gets | The owner gives up |
|---|---|---|
| 1 | A working vault in one sitting, a brief the same day, no Hyprland, no test tools, no surprise timers | Nothing; every feature is still one yes away |
| 2 | One alert format, one lock, connectors that break in one place | A week of refactoring with the suites green at each commit |
| 3 | A core that never names clearing-house, Sentry, Jira or Gemini; a template half its size | Five extension folders to install; sync switched on as an extension |
| 4 | A prompt layer they can edit without failing the gate; sessions that load a third of the words | Some drift detection; the humanizer polish in headless notes |

## 6. Where this changes the review branch (#116)

- `2026-10-11-claude-md-prune-design.md`: the target is 45 lines, not 120, and the Agents block moves to the `order` skill.
- `2026-10-11-smoke-check-design.md`: unchanged in purpose; after step 2 it checks two files of `claude` flags, which is the point.
- `2026-10-11-usage-ceiling-design.md`: unchanged; it is core behaviour.
- `2026-10-11-slack-bridge-design.md`: build it as the first extension under step 3's mechanism, so the mechanism is proven by a feature the owner wants.
- The fast lane: still the first thing to ship.
- Add to the roadmap: "Express install" (step 1) ahead of everything else dated 2026-10-11, and "Extensions" (step 3) as the row that absorbs the clearing-house, telemetry, meetings and handoffs rows.

## 7. Facts checked during the review

- `--restricted` is a real `claude` flag (the spike record quotes its help text: `docs/superpowers/spikes/2026-09-30-headless-and-hooks.md:5`).
- `update_template.sh:47-48` dies when `template/<branch>` shares no history with the vault, and the unattended timer runs that path daily.
- `foundry-focus.service.in:14-15` has `Restart=on-failure` and `RestartSec=10`; `track_obsidian.sh:17` fails when `hyprctl` is absent.
- `check_deps.sh:25` lists `hyprctl`, `bats` and `pytest` as required for standalone.
- No script reads a Workcell's `capabilities` at run time.
