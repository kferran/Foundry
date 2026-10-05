# The Foundry: Product Rename and Capability Seam (Plan 9)

**Date:** 2026-10-05
**Status:** Approved in brainstorming (2026-10-05); revised after an independent review and its re-review (rev 3)
**Extends:** `2026-09-30-vault-template-design.md` §15 (naming) and §16 (reserved extension points); applies to every spec's vocabulary
**Roadmap:** Plan 9 (product rename), moved ahead of Plans 5 and 7 by the user (2026-10-05)

## 1. Problem and decisions

The template is named Jarvis, with Transformers names for its parts (Optimus, Wheeljack, Ultra Magnus, Soundwave, Teletraan, The Ark, Autobots, Bumblebees) and plain persona names for its workers (CodingAgent, SystemMaintenance). The user chose new names on 2026-10-05 and one architectural rule to protect from day one.

| Topic | Decision |
|---|---|
| Product | **The Foundry** |
| Primary orchestrator | **The Foreman**: the only role the user addresses |
| Persistent knowledge layer | **The Core**: the compiled wiki, the index and session memory (capture and recall) |
| Specialist agents | **Workcells**, discovered and dispatched by capability, never by name |
| Work units | a multi-step assignment is a **Production Job**; each of its tasks is a **Work Order** |
| Other themed names | plain descriptive names (intake compiler, publish gate, memory, watcher, index) |
| Timing | no vault is installed anywhere yet; the user sets up the real server and client after Plan 9 merges, so there is **no migration** of installed units, notes or branches |
| History | under `docs/superpowers/`, plans, outcomes and acceptance records stay as written; specs get one names line each, the main spec's §15 and §16 are rewritten, and the roadmap's rows are updated (§5) |
| Capability seam | built now; the orchestrator that dispatches on it is Sub-project 2 |

## 2. Name map

Applies to every live file (everything outside `docs/superpowers/`). §4 says which rows the rename script applies and which are written by hand.

| Today | After Plan 9 |
|---|---|
| Jarvis (product, prose) | The Foundry |
| Optimus, "Chief of Staff"; `system/agents/Optimus.md` | the Foreman; `system/agents/foreman.md` ("Chief of Staff" is dropped: the Foreman is the title) |
| CodingAgent; `system/agents/CodingAgent.md` | the Coding Workcell; `system/agents/workcells/coding.md` |
| SystemMaintenance; `system/agents/SystemMaintenance.md` | the Maintenance Workcell; `system/agents/workcells/maintenance.md` |
| The Ark | the index (part of The Core) |
| Soundwave | memory (part of The Core) |
| Wheeljack | the intake compiler |
| Ultra Magnus | the publish gate |
| Teletraan | the watcher (reserved) |
| Autobots, Bumblebees, crewmates | Workcell sessions; "ship" and "scout" are session kinds reserved for Sub-project 2, not capabilities |
| reserved `system/fleet/tasks/<id>/` | reserved `system/jobs/` (layout settled in Sub-project 2) |
| units `jarvis-intake`, `jarvis-brief`, `jarvis-debrief`, `jarvis-focus`, `jarvis-sync`, reserved `jarvis-watcher`; templates `system/systemd/jarvis-*.in` and `system/systemd/dropins/jarvis-sync.conf.in`; drop-ins `<unit>.service.d/jarvis-sync.conf` | `foundry-…` throughout (templates are moved with `git mv`) |
| unit `Description=Jarvis <Name>: <role>` (e.g. `Jarvis Wheeljack: intake compiler`, `Jarvis Optimus: morning brief`) | `Description=The Foundry: <role>` (e.g. `The Foundry: intake compiler`, `The Foundry: morning brief`) |
| `JARVIS_HEADLESS` | `FOUNDRY_HEADLESS` |
| `JARVIS_CREW` (flag, `1`) | `FOUNDRY_WORKCELL_SESSION` (flag, `1`) |
| `JARVIS_TASK_ID`; digest field `task_id` (schema and `memory_capture.sh`) | `FOUNDRY_WORK_ORDER`; digest field `work_order` |
| `JARVIS_ORIGINAL_SHA256` | `FOUNDRY_ORIGINAL_SHA256` |
| `JARVIS_MANAGED_SETTINGS`, `JARVIS_MANAGED_SETTINGS_DIR` | `FOUNDRY_MANAGED_SETTINGS`, `FOUNDRY_MANAGED_SETTINGS_DIR` |
| commit trailers `Jarvis-Command`, `Jarvis-Run`, `Jarvis-Role` | `Foundry-Command`, `Foundry-Run`, `Foundry-Role` |
| pending branches `jarvis/<role>-pending` | `foundry/<role>-pending` |
| log and alert tags `[wheeljack]`, `[soundwave]` | `[intake]`, `[memory]` (`[sync]` and the rest stay; the publish path writes no tag) |
| code identifiers built on "crew" (`recall.crew_env`, `build(…, crew=…)`, test fixtures named `crew-…`) | built on "workcell" (`workcell_session_env`, `workcell_session=`, `workcell-…`) |
| the digest request line `Jarvis memory (not an error): …` | `Foundry memory (not an error): …` (the rest of the line unchanged) |
| the recall header `## Jarvis vault recall` | `## Foundry vault recall` |
| `/tmp/jarvis-verify-…` (`verify_on_host.sh`) | `/tmp/foundry-verify-…` |

**Not renamed** (protected strings, §4): the template URL in `system/template_source` (the user renames the GitHub repository on the host if wanted; GitHub redirects the old URL to the new one, never the reverse), and the roadmap's path `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` wherever it is linked. Also not renamed: script and module file names (already descriptive) and the `# Managed by vault: <root>` unit header (it names no product).

## 3. The capability seam

### 3.1 Workcell files

Each file in `system/agents/workcells/` is one Workcell. Its frontmatter is validated by a new schema note `system/schemas/workcell.md`, folder `system/agents/workcells/`, with existing schema kinds:

```yaml
fields:
  type: {kind: const, value: workcell, required: true}
  capabilities: {kind: list, of: string, required: true}
```

| File | Frontmatter `capabilities` |
|---|---|
| `workcells/coding.md` | `[code, tests, refactor]` |
| `workcells/maintenance.md` | `[vault-health, dependencies, telemetry, alerts]` |

The display name is the body's first heading (the index already uses it as the title): exactly `# Coding Workcell` and `# Maintenance Workcell`, and `system/agents/foreman.md` starts with `# The Foreman`. `commands.bats` pins the three headings with `grep -qx`. The body keeps the persona text of today's `CodingAgent.md` and `SystemMaintenance.md`, reworded for the new names. The index creates a `v_workcell` view from the schema, which is the lookup Sub-project 2 queries.

Two rules have no schema kind, so the gated tests enforce them (§6): capability names match `^[a-z]+(-[a-z]+)*$`, and no capability is declared by two Workcells.

`system/agents/foreman.md` holds the Foreman persona (today's `Optimus.md`, reworded). It has no frontmatter and declares no capabilities: the Foreman is addressed, not dispatched. No schema covers `system/agents/foreman.md`, and the validator reports nothing for a path no schema covers (today's personas pass the same way), so `CLAUDE.md`'s schema rule applies to schema-covered folders, as it already does in practice.

`system/agents/` joins the index's `NAME_EXCLUDED` list, so `coding.md` and `maintenance.md` never answer a bare `[[Coding]]` or `[[Maintenance]]` wiki link.

**Metrics:** a metric file's `agent` value is the Workcell's file stem (`coding`, `maintenance`), and the file is `system/logs/metrics/<stem>-<epoch>.json`. The template `system/templates/compilation-metric.json` uses `"agent": "{{workcell}}"` (was `{{agent_name}}`). `/debrief` keeps grouping by the `agent` value, which now equals the stem.

### 3.2 Notes ask for a capability

- **Concept notes:** the schema's `agent_owner` (enum `CodingAgent`, `SystemMaintenance`, `Optimus`) is replaced by `capability`, an enum of every capability any Workcell declares. Work for the Foreman itself needs no field.
- **Production errors:** `assigned_agent` is dropped from `production_error.md`; the schema's body says these notes route to the Workcell with `telemetry`.
- **Where the values live:** the enum is written once, in `system/schemas/concept.md`. `/ingest` sets `capability` only when a note assigns work, choosing a value listed there (the command points to that file, which a headless run can Read, and does not repeat the list). `/setup`'s onboarding note sets `capability: code`.
- **Template:** `system/templates/wiki-concept.md` writes `capability: "{{capability}}"`; the schema-notes test fills it with `code`.
- **Dashboard:** `wiki/Index.md`'s "By owner" query becomes "By capability" (`WHERE capability`, `GROUP BY capability`).

A gated test checks that the concept schema's `capability` values equal the union of the Workcells' `capabilities`. Adding, removing or renaming a Workcell is then a change to its file and that one list, and nothing the user types changes.

### 3.3 Routing by capability

Every place that routes work names a capability, never a Workcell:

- `CLAUDE.md`: the Agents section describes the Foreman and the Workcells, and says work goes to the Workcell whose `capabilities` include the one needed, found by reading `system/agents/workcells/*.md`. Production telemetry routes to `telemetry`; runtime failures, broken links and merge conflicts to `vault-health`.
- `/brief`: telemetry notes route to `telemetry`; objectives hand slices to a capability.
- `/setup`: the onboarding note asks for `code`.

No orchestrator, dispatch loop or capability lookup code is built here. Sub-project 2 builds dispatch on this seam and owns Production Jobs and Work Orders beyond their names.

### 3.4 Lint coverage

`.githooks/pre-commit`'s staged-path pattern gains `system/agents/`, so a commit that changes only a Workcell file is linted.

## 4. Mechanics

- **Protected strings** are masked before the script runs and restored after: the `system/template_source` URL and the roadmap path `2026-09-30-jarvis-roadmap.md`.
- **The rename script** (in the plan workspace, run once, not committed) changes tokens only, case-sensitive, longest first, in every tracked file outside `docs/superpowers/`:
  - prefixes `jarvis-` → `foundry-` and `jarvis/` → `foundry/` (unit names in any form, including `jarvis-$cmd.service`, `'jarvis-*'`, `jarvis-{intake,…}`; branch names, including `jarvis/$role-pending`, `refs/heads/jarvis/`, `origin/jarvis/*-pending`);
  - `JARVIS_MANAGED_SETTINGS_DIR`, `JARVIS_MANAGED_SETTINGS`, `JARVIS_ORIGINAL_SHA256`, `JARVIS_HEADLESS`, `JARVIS_CREW`, `JARVIS_TASK_ID` → their §2 names;
  - `Jarvis-Command`, `Jarvis-Run`, `Jarvis-Role` → `Foundry-…`;
  - `[wheeljack]` → `[intake]`, `[soundwave]` → `[memory]`;
  - the `git mv` moves of the unit templates and personas.
- **Hand-written patches** cover everything else (after the script, about 117 lines in 45 files, measured on 2026-10-05; the largest are `README.md` 27, `memory.bats` and `commands.bats` 8 each, `recall.py` 6, `CLAUDE.md` 5), including the test fixtures that pin old wording (`focus.bats`'s window-title fixture `"… - Jarvis - Obsidian …"`, `commands.bats`'s `agent_owner` wording check for `ingest.md` and its `CodingAgent-<epoch>.json` and `{{agent_name}}` checks): the capability seam (§3); every remaining old name in prose and identifiers (Jarvis as a product name, Optimus, CodingAgent, SystemMaintenance, Wheeljack, Ultra Magnus, Soundwave, The Ark, Teletraan, Autobots, Bumblebees, crewmates, `crew` identifiers, `task_id`, `fleet`, the unit `Description=` lines, the digest request line, the recall header), each reworded so the sentence still reads correctly. The §6 test finds any that remain.
- **README:** "What Jarvis is" becomes "What The Foundry is"; the naming table lists the Foreman, the Workcells, The Core and its parts with plain names; "Memory (Soundwave)" becomes "Memory" under The Core; the Status table's roadmap rows are reworded ("3. Memory (Soundwave)" → "3. Memory", "Optimus orchestrator" → "the Foreman orchestrator", and the Plan 9 row reads `9. Product rename | The Foundry names and the capability seam | Complete` with links, placed after the 8e row, its order of execution); the naming table's "Zero-token fleet watcher" row becomes the watcher; the repository layout shows `system/agents/workcells/` and `jobs/`; the getting-started prompt says "a new Foundry vault".
- **`.gitignore`** reserves `system/jobs/` instead of `system/fleet/`; the index's `NOT_INDEXED` list follows.

## 5. Docs under `docs/superpowers/`

- Plans, outcomes, spikes and acceptance records are not edited.
- Each spec gets one line under its status: `**Names (Plan 9, 2026-10-05):** Jarvis is The Foundry and Optimus the Foreman; CodingAgent and SystemMaintenance are the Coding and Maintenance Workcells; jarvis-* units, JARVIS_* variables and Jarvis-* trailers are foundry-*, FOUNDRY_* and Foundry-* (see 2026-10-05-foundry-rename-design.md §2).`
- The main spec's §15 naming table is replaced by §2's map, and §16's reserved extension points are restated in the new names (`system/jobs/`, `FOUNDRY_WORKCELL_SESSION`, `FOUNDRY_WORK_ORDER`, the watcher, Workcell sessions by capability).
- The roadmap's Plan 9 row is marked complete when the plan lands.

## 6. Tests

New tests go into existing files (`vault_integrity.bats`, `commands.bats`), so the gate stays at 16 suites. Under bats 1.8 and ruling R1 (no mid-test `!`, no `&&` assertion chains):

- **Scope:** both checks cover only the files the template owns, never the user's notes (a compiled note may say "fleet" or "crew"):
  `OWN=(CLAUDE.md README.md .gitignore .claude .githooks system wiki/Index.md ':!system/codebases')`. `system/codebases/example.md` is checked by name in the same test.
- **No old names in content:** every token and both protected strings are split into pieces, so the test file, which lies inside `system/`, does not match itself:
  ```
  re="jar""vis|opt""imus|wheel""jack|ultra[ -]mag""nus|sound""wave|tele""traan|the a""rk|auto""bot|bumble""bee|coding""agent|system""maintenance|(^|[^a-z])cr""ew|fl""eet|task""_id|agent""_owner|assigned""_agent|agent""_name|chief of st""aff"
  road="2026-09-30-jar""vis-roadmap\.md"
  url="https://github\.com/kferran/jar""vis\.git"
  out="$(git grep -h -i -E "$re" -- "${OWN[@]}" system/codebases/example.md | sed -e "s#$road##g" -e "s#$url##g" | grep -i -E "$re" || true)"
  printf '%s\n' "$out"
  [ -z "$out" ]
  ```
  A line that holds a protected string and a real leftover still fails, and so does a bare `kferran/jarvis` without `.git`. (Measured on 2026-10-05: 281 lines in 60 files before Plan 9; 0 false positives; `(^|[^a-z])crew` catches `test_crew_…` and skips `screw` and `aircrew`.)
- **No old names in paths:** `out="$(git ls-files -- "${OWN[@]}" | grep -i -E "$re" || true)"`, printed, then `[ -z "$out" ]`.
- **Capabilities:** the concept schema's `capability` values equal the union of `capabilities` in `system/agents/workcells/*.md`; no capability is declared twice; every capability matches `^[a-z]+(-[a-z]+)*$`; every Workcell file passes the `workcell` schema; `system/agents/foreman.md` exists.
- **Pre-commit:** a staged change to a Workcell file with invalid frontmatter is rejected by the hook.
- **Existing tests** are updated in place to the new unit names, variables, trailers, branch names, tags, paths, the digest request line and the recall header (for example `commands.bats`'s `ls system/agents` value becomes `foreman.md workcells`, and its persona-script-reference check globs `system/agents/workcells/*.md` too; `test_schema_notes.py` expects the `workcell` schema). No test is removed.
- Gate: `verify_setup.sh` exit 0, 16/16; lint 0 errors.

## 7. Live acceptance

In a throwaway clone (about $0.70):
1. `install_units.sh --dry-run` for `standalone` and for `server` renders only `foundry-*` units and drop-ins (no install).
2. A headless ingest, a brief and a debrief (the Plan 4a steps, since every command file changes): each exits 0 and publishes; `commit_runs.py` makes one commit per run with `Foundry-Command`, `Foundry-Run` and `Foundry-Role` trailers; alerts and logs use the new tags; an ingest note that assigns work uses `capability`.

## 8. Out of scope

- Any orchestrator, dispatch or capability lookup code (Sub-project 2).
- Migrating installed vaults (none exist).
- Renaming the GitHub repository, local checkout directories or script file names.
