# The Foundry: Product Rename and Capability Seam (Plan 9)

**Date:** 2026-10-05
**Status:** Approved in brainstorming (2026-10-05); pending independent review
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
| History | everything under `docs/superpowers/` stays as written, except the roadmap's rows and one header line per spec (§5) |
| Capability seam | built now; the orchestrator that dispatches on it is Sub-project 2 |

## 2. Name map

Applies to every live file (everything outside `docs/superpowers/`).

| Today | After Plan 9 |
|---|---|
| Jarvis (product, prose) | The Foundry |
| Optimus; `system/agents/Optimus.md` | the Foreman; `system/agents/foreman.md` |
| CodingAgent; `system/agents/CodingAgent.md` | the Coding Workcell; `system/agents/workcells/coding.md` |
| SystemMaintenance; `system/agents/SystemMaintenance.md` | the Maintenance Workcell; `system/agents/workcells/maintenance.md` |
| The Ark | the index (part of The Core) |
| Soundwave | memory (part of The Core) |
| Wheeljack | the intake compiler |
| Ultra Magnus | the publish gate |
| Teletraan | the watcher (reserved) |
| Autobots, Bumblebees, crewmates | Workcell sessions, by capability (ship, scout) |
| reserved `system/fleet/tasks/<id>/` | reserved `system/jobs/` (layout settled in Sub-project 2) |
| units `jarvis-intake`, `jarvis-brief`, `jarvis-debrief`, `jarvis-focus`, `jarvis-sync` (`.service`, `.timer`, `.service.d/jarvis-sync.conf`) | `foundry-intake`, `foundry-brief`, `foundry-debrief`, `foundry-focus`, `foundry-sync` (`.service.d/foundry-sync.conf`); reserved `jarvis-watcher.service` becomes `foundry-watcher.service` |
| unit `Description=Jarvis …` (e.g. `Jarvis Wheeljack: intake compiler`) | `Description=The Foundry: …` (e.g. `The Foundry: intake compiler`) |
| `JARVIS_HEADLESS` | `FOUNDRY_HEADLESS` |
| `JARVIS_CREW` | `FOUNDRY_WORKCELL` |
| `JARVIS_TASK_ID`; digest field `task_id` | `FOUNDRY_WORK_ORDER`; digest field `work_order` |
| `JARVIS_ORIGINAL_SHA256` | `FOUNDRY_ORIGINAL_SHA256` |
| `JARVIS_MANAGED_SETTINGS`, `JARVIS_MANAGED_SETTINGS_DIR` | `FOUNDRY_MANAGED_SETTINGS`, `FOUNDRY_MANAGED_SETTINGS_DIR` |
| commit trailers `Jarvis-Command`, `Jarvis-Run`, `Jarvis-Role` | `Foundry-Command`, `Foundry-Run`, `Foundry-Role` |
| pending branches `jarvis/<role>-pending` | `foundry/<role>-pending` |
| log and alert tags `[wheeljack]`, `[ultra-magnus]` | `[intake]`, `[publish]` (`[sync]` and the rest stay) |
| code identifiers built on "crew" (`recall.crew_env`, `build(…, crew=…)`) | built on "workcell" (`workcell_env`, `workcell=`) |

**Not renamed:** script and module file names (already descriptive); the `# Managed by vault: <root>` unit header (it names no product); the GitHub repository name and URL (the user renames it on the host if wanted; GitHub redirects the old URL); the roadmap's file name `2026-09-30-jarvis-roadmap.md` (it lives under `docs/superpowers/`).

## 3. The capability seam

### 3.1 Workcell files

Each file in `system/agents/workcells/` is one Workcell. Its frontmatter is validated by a new schema note `system/schemas/workcell.md` (folder `system/agents/workcells/`):

```yaml
---
type: workcell
name: Coding                         # display name, used in prose only
capabilities: [code, tests, refactor]
---
```

| File | `capabilities` |
|---|---|
| `workcells/coding.md` | `code`, `tests`, `refactor` |
| `workcells/maintenance.md` | `vault-health`, `dependencies`, `telemetry`, `alerts` |

The body keeps the persona text of today's `CodingAgent.md` and `SystemMaintenance.md`, reworded for the new names. Metric files keep their shape; the metric's `agent` value becomes the Workcell's file stem (`coding`, `maintenance`), and metric files are named `system/logs/metrics/<stem>-<epoch>.json`.

`system/agents/foreman.md` holds the Foreman persona (today's `Optimus.md`, reworded). It has no frontmatter and declares no capabilities: the Foreman is addressed, not dispatched.

Capability names are lowercase words joined by hyphens (`^[a-z]+(-[a-z]+)*$`); no two Workcells declare the same capability.

### 3.2 Notes ask for a capability

The concept schema's `agent_owner` (enum `CodingAgent`, `SystemMaintenance`, `Optimus`) is replaced by `capability`: an enum of every capability any Workcell declares. Work for the Foreman itself needs no field. `/ingest` sets `capability` only when a note assigns work, choosing from the enum; `/setup`'s onboarding note sets `capability: code`.

The enum is written in the schema note (the validator stays static). A gated test checks that the schema's `capability` values equal the union of the Workcells' `capabilities`, so adding, removing or renaming a Workcell is a change to its file and that one list, and nothing the user types changes.

### 3.3 Routing by capability

Every place that routes work names a capability, never a Workcell:

- `CLAUDE.md`: the Agents section describes the Foreman and Workcells and says work is routed to the Workcell whose `capabilities` include the one needed, found by reading `system/agents/workcells/*.md`. Production telemetry routes to the Workcell with `telemetry`; runtime failures, broken links and merge conflicts to the one with `vault-health`.
- `/brief`: telemetry notes route to `telemetry`; objectives hand slices to a capability.
- `/debrief`: Agent Health reads metric files by Workcell stem.
- `/setup`: the onboarding note asks for `code`.

No orchestrator, dispatch loop or capability lookup code is built here. Sub-project 2 builds dispatch on this seam and owns Production Jobs and Work Orders beyond their names.

## 4. Mechanics

- **One pass, two kinds of change.**
  - A deterministic rename script applies §2's token map (exact, case-sensitive tokens, longest first) to every tracked file outside `docs/superpowers/`, and does the file moves with `git mv`. The script lives in the plan workspace, is run once, and is not committed.
  - Hand-written patches cover the capability seam (§3), the new schema, the persona bodies, and prose that needs rewording rather than token replacement (README, `CLAUDE.md`, command files).
- **README:** "What Jarvis is" becomes "What The Foundry is"; the naming table lists the Foreman, Workcells, The Core and its parts with plain names; "Memory (Soundwave)" becomes "Memory" under The Core; the getting-started prompt says "a new Foundry vault".
- **`.gitignore`** reserves `system/jobs/` instead of `system/fleet/`; the index's `NOT_INDEXED` list follows.

## 5. Docs under `docs/superpowers/`

- Plans, outcomes, spikes and acceptance records are not edited.
- Each spec gets one line under its status: `**Names (Plan 9, 2026-10-05):** Jarvis is The Foundry and Optimus the Foreman; CodingAgent and SystemMaintenance are the Coding and Maintenance Workcells; jarvis-* units, JARVIS_* variables and Jarvis-* trailers are foundry-*, FOUNDRY_* and Foundry-* (see 2026-10-05-foundry-rename-design.md §2).`
- The main spec's §15 naming table is replaced by §2's map, and §16's reserved extension points are restated in the new names (`system/jobs/`, `FOUNDRY_WORKCELL`, `FOUNDRY_WORK_ORDER`, the watcher, Workcell sessions by capability).
- The roadmap's Plan 9 row is marked complete when the plan lands.

## 6. Tests

- **No old names:** `git grep -n -E` for `Jarvis|jarvis|JARVIS|Optimus|Wheeljack|Ultra Magnus|ultra-magnus|Soundwave|Teletraan|The Ark|Autobot|Bumblebee|CodingAgent|SystemMaintenance|crewmate` over every tracked file outside `docs/superpowers/` finds nothing, except lines whose only match is the roadmap path `2026-09-30-jarvis-roadmap.md`.
- **Capabilities:** the concept schema's `capability` values equal the union of `capabilities` in `system/agents/workcells/*.md`; no capability appears twice; every Workcell file passes the `workcell` schema; `system/agents/foreman.md` exists.
- **Existing tests** are updated in place to the new unit names, variables, trailers, branch names, tags and paths. No test is removed.
- Gate: `verify_setup.sh` exit 0, 16/16; lint 0 errors.

## 7. Live acceptance

In a throwaway clone (about $0.70):
1. `install_units.sh --dry-run` for `standalone` and for `server` renders only `foundry-*` units and drop-ins (no install).
2. A headless ingest, a brief and a debrief (the Plan 4a steps, since every command file changes): each exits 0 and publishes; `commit_runs.py` makes one commit per run with `Foundry-Command`, `Foundry-Run` and `Foundry-Role` trailers; alerts and logs use the new tags; an ingest note that assigns work uses `capability`.

## 8. Out of scope

- Any orchestrator, dispatch or capability lookup code (Sub-project 2).
- Migrating installed vaults (none exist).
- Renaming the GitHub repository, local checkout directories or script file names.
