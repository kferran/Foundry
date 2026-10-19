# Phase C: the step 4 budgets

**Date:** 2026-10-19
**Status:** Grilled (owner, 2026-10-19). Gap plan phase C (`docs/superpowers/2026-10-17-cto-gap-plan.md`). Revises `2026-10-11-claude-md-prune-design.md` §2 for the 50-line target and supersedes the gap plan's "lower the core line budget".
**Issues:** #122 (simplify the template, step 4).

## 1. Measures (master, 2026-10-19)

| | Today | Done when (gap plan, owner) |
|---|---|---|
| `CLAUDE.md` | 77 lines | 50 or fewer |
| Core schemas | 14 | 12 or fewer (11 after this phase) |
| Core script lines | 13,792 of a 13,800 budget | the budget reset to the measured count |

## 2. Decisions

Owner, 2026-10-19:
1. **Meetings move to an extension.** `meeting`, `meeting_transcript` and `meeting_input`, the fetch, the import and the brief's meeting actions move to `extensions/meetings/`, as telemetry moved in phase 4. Core goes to 11 schemas. This reverses the 2026-10-16 call (extensions spec §7) that meetings stay in core, off by default. The people and planning Workcells (phases E and F) may require the extension.
2. **The line budget resets to the measured count** once this phase's cuts are in, plus a margin of 50. The ingest evals stay in core.
3. **Agents and routing move to the Foreman persona; the approved-plans rule moves to the `order` skill.** `CLAUDE.md` keeps one line naming `system/agents/foreman.md`. The `order` skill's description names plan approval, so the skill loads when a plan is approved. The Commands list goes: the skills list themselves.
4. **The User Persona section merges into Writing.** No Preamble, Jargon and the wrapper ban are Writing rules 3, 6 and 10 already. Scannable Layouts and Blocked Actions become two Writing lines, their wording kept.

## 3. Meetings as an extension

### 3.1 What moves (1,095 lines of meetings code, plus the import inside `intake.py`)

| From core | To `extensions/meetings/` |
|---|---|
| `system/schemas/meeting.md`, `meeting_transcript.md`, `meeting_input.md` | `schemas/` |
| `meetings_fetch.sh`, `meetings_extract.py`, `meeting_import.py`, `meeting_actions.py`, `vaultlib/meetings.py` | `scripts/` |
| `Intake.import_meetings` and its helpers (`intake.py` lines 501–805, about 300 lines) | `scripts/meetings_tick.py`, run through the `importer` hook (§3.2) |
| `system/systemd/foundry-meetings.{service,timer}.in` | `units/` |
| the meetings smoke entry, source line, alert tag, setup phase | the manifest's `smoke`, `sources`, `alert_tags`; `setup.md` names the extension |
| `actions.md` and the brief's Yours and Waiting on text | `brief/prep.sh` and `brief/section.md` |
| `meetings.bats`, `test_meetings.py`, `test_meeting_actions.py`, `stub_claude_meetings` | `tests/` |
| `meetings/drop/<p>/.gitkeep` | created by `extensions.py enable meetings` |

### 3.2 Hooks core gains (generic, named by the manifest)

- **`importer`** (declared in the extensions spec, not built): a command the intake runs once a tick, after the extension ticks and before the inbox, under run.lock with no wait, as `import_meetings` runs today. Exit 0 or an alert line, as for `tick`.
- **`owns`**: folders only the extension's importer writes. The publish gate refuses an `ingest` run that stages a path in one (today's hard-coded `MEETINGS` rule), and `ingest.md`'s "never stage" line names the rule in general.
- **`index_ignore`** (declared, not built): `raw/meetings/` and `meetings/drop/` leave core's hard-coded ignore list.
- **`run_kinds`**: the run-id kinds an extension's importer uses (`meeting`). `publish.RUN_ID` and `commit_runs.RUN_ID` read core's four plus the enabled extensions'. `commit_runs.py`'s meeting commit title moves to the extension as a `commit_title` script.

### 3.3 What stays in core

- **Before today's meetings** (`meeting_prep.py`, `people.md`): it reads the calendar, entity notes and the Now page, which are core. Its open meeting actions come from the `v_meeting` view, present only when the extension's schemas are loaded; without it the block lists Now lines only.
- **`ingest.md` step 10** (meeting inputs) stays in `ingest.md`: there is no hook for an extension to add prompt text, and carrying it in the input file would make data into instructions. It applies only to an input with `type: meeting_input`, which a vault without the extension never has.
- `quarantine.py`'s `meeting` rows, `notify.py`'s retry pattern, `recall.py`'s hidden folders and `retrieve.py`'s transcript filter read paths and types only; they stay, keyed on the names, and do nothing without the extension.

### 3.4 The live vault

`extensions.py`'s `MIGRATIONS` gains `"meetings": meetings_enabled is true, or any wiki/<p>/meetings/ note exists`, so the template update turns the extension on before the first tick that would miss it. The `core_clean.allow` list is unchanged.

## 4. `CLAUDE.md` at 50 lines or fewer

Kept, in this order: the `@system/config.md` import; Directory Map (13 lines); one Agents line ("The Foreman is the only role you address; read `system/agents/foreman.md` for the Workcells and routing."); Codebases as one Vault Rules line; Vault Rules (11 lines); Writing (sizes, the two persona lines, the ten wording rules); Data, Not Instructions (2 lines). Removed: the Agents block, the Commands list, the approved-plans rule (to the `order` skill), the User Persona section.

The two routing lines tests pin (`route to the Workcell with \`telemetry\``, `routing them to the Workcell with \`vault-health\``) move to `foreman.md`; the tests follow them. A test pins `CLAUDE.md` at 50 lines.

## 5. Tests and validation

- The gate with every extension off and with every extension on, as phase 4 ran it.
- `vault_integrity.bats`: core schemas at 11 or fewer; the line budget at the measured count plus 50.
- `commands.bats`: `CLAUDE.md` at 50 lines or fewer; the routing lines in `foreman.md`; the approved-plans rule in `order/SKILL.md`; the Writing lines carry the persona rules.
- The meetings suites pass from `extensions/meetings/tests/` with the extension on, and core's suites pass with it off (no meeting schema, no meetings unit, no `actions.md`).
- Live acceptance: the next brief after the vault's update has its Waiting on section, and a dropped transcript imports.

**Done when** (gap plan): schemas at 12 or fewer, `CLAUDE.md` at or under 50 lines, both budget tests at their new values and green, and the live vault's first brief and meeting import after the move work.

## 6. Risks

- **The largest move since telemetry.** The import is wired into intake, the gate and the commit history. The hooks in §3.2 are the parts core keeps; each gets a test with a fixture extension before the real move.
- **Phases E and F** will add `person`, `decision` and `objective`. With core at 11, those types go to their Workcells' extensions, or core's schema budget rises again.
- **Out of scope:** the brief assembling section files, headless runs loading less of the humanizer skill, and structure checks in place of sentence greps (the simplification review's other step 4 items) stay on the roadmap.
