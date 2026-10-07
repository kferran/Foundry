# Roadmap and README update

**Date:** 2026-10-07
**Status:** Approved in brainstorming (2026-10-07), awaiting written-spec review

## 1. Problem and decisions

The roadmap still carries the old product name in its path (`docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`) and title, and it stops before the Nightshift, the DTCC watcher, the briefing archive and Active Projects. The README never mentions those four features: `/nightshift` and `/dtcc-watch` are missing from Daily use, their skills and units are missing from the layout, and the status banner says the system runs on one machine and that the migration is still to come (it runs on a server and a client, and the migration is done). The README and the roadmap also hold two copies of the same status table, so every plan updates both.

| Topic | Decision |
|---|---|
| Where status lives | The roadmap holds the one detailed table. The README gets a short "works today / next" summary and links to it. |
| Roadmap path | `docs/superpowers/roadmap.md`: undated (a living document), next to `specs/` and `plans/`, moved with `git mv` so its history follows. |
| Granularity | One roadmap row per feature. Small work shares one "Fixes from live use" row that links its issues and pull requests. A short "Next, in order" list under the table shows the agreed queue. |
| README coverage | A Daily use row and a short paragraph for each new feature, layout and units lines, and a Requirements line where a feature needs something. |
| History | Dated documents that cite the old roadmap path or the old name stay as they are. |

## 2. The roadmap

- `git mv docs/superpowers/plans/2026-09-30-jarvis-roadmap.md docs/superpowers/roadmap.md`. The title becomes `# The Foundry: Roadmap`.
- Existing rows keep their text, except:
  - **Plan 12 (minutes):** spec rev 2 after two reviews; rev 3, the owner's review and the plan next; the work runs in its own session in the `minutes` repository.
  - **Sub-project 2:** it absorbs the Nightshift as its unattended execution layer (queue items become Work Orders; the runner becomes the watcher's unattended mode).
- New feature rows, each linking its spec, plan and pull requests:
  - **The Nightshift:** unattended plan and research runs (#49, #50, #52). Complete.
  - **DTCC change watcher, phase 1:** scripted fetch, `dtcc_change` notes, the brief block (#51). Complete. Phase 2 (a model impact assessment) is later.
  - **Briefing notes and archive** (#53). Complete.
  - **Active Projects in the brief** (#66, issue #65). Complete.
  - **RCA-to-Jira, phase 1:** attended `/rca`, a `jira_draft` note type and a filer. Next: design sections with the owner.
  - **Require-plan:** parked by the owner on 2026-10-07; spec rev 5 and a proven plan on branch `feat/require-plan`.
  - **Reorganization** (#62): `vault/`, feature folders and `core/`. After the Sub-project 2 brainstorm.
- One **Fixes from live use** row:
  - merged: #32, #34, #36, #45, #50, #58, #60;
  - in review when this lands: the Nightshift pull requests of 2026-10-08 (template issue fixes, telemetry identifiers), listed by number once opened, and as merged if they merge before this does;
  - next: fewer prompts (seven read-only allow rules and the `CLAUDE.md` Bash line, byte for byte as in the vault), the Nightshift source fix (a `template` item resolves to the development clone or the remote, not the vault), and the `/ingest` preference gap (spec §6.21: digest Corrections never become `preference` notes).
- A **Next, in order** list under the table: fewer prompts; the Nightshift source fix; RCA-to-Jira phase 1; `/ingest` preference notes; the Sub-project 2 brainstorm; then #62. Plans 5 and 7 stay "after a few weeks of real use".
- The README's "Plans are numbered in the order they were defined…" paragraph moves here, under the table.

## 3. The README

- **Status banner** (the quote under the title): the vault runs on one Debian server and a laptop client, live since 2026-10-05, with links to the live acceptance records. Next: preferences, style lint and the Foreman orchestrator. Nothing about the migration.
- **`## Status`:** the table is replaced by:
  - **Works today:** one line per area: the headless intake, brief and debrief; memory; two machines and sync; the calendar; error telemetry; meetings; the Nightshift; the DTCC watcher; Active Projects; the briefing archive.
  - **Next:** the same order as the roadmap's list.
  - Two links: the design spec and `docs/superpowers/roadmap.md`.
- **`## Daily use`:**
  - New rows: `/nightshift add|ask|list|cancel|status` and `/dtcc-watch [check|status|accept]`.
  - The `/brief` row mentions the 🎯 Active Projects section and the DTCC changes block.
- New paragraphs beside **Error telemetry**:
  - **The Nightshift.** Queued items run unattended on a 15-minute timer (`foundry-nightshift.timer`, standalone and server only), in the nightly window (`nightshift_window`, default `22:00-05:00`, waiting while you are active), at a set time, or now. A plan item runs in a private clone, is verified, pushed and ends in a pull request, never a merge. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report `system/logs/nightshift/<date>.md` leads with health, then "Needs you"; the brief carries those items forward. Queue notes live in `raw/<partition>/nightshift/` (tracked in your vault); clones go under `nightshift_workspace`.
  - **DTCC change watcher.** `foundry-dtcc-watch.timer` runs `dtcc_watch.py` daily, 30 minutes before the brief. No model runs. It reads DTCC's public I&RS pages, notices and API catalog, writes one `dtcc_change` note per change to `wiki/<partition>/changes/` with the codebase paths it touches, and the brief lists each as a checkbox that carries forward until ticked. It is inert until the vault has `system/dtcc/map.yaml` (start from `system/dtcc/map.example.yaml`).
  - **Active Projects.** An optional `wiki/<partition>/ActiveProjects.md` lists project pages in priority order under `## Active`. The brief shows each active project's next 3 open checkboxes and the open items under its "Decisions…" heading, as plain bullets; you tick them on the project page.
- **Repository layout:** adds the `nightshift` and `dtcc-watch` skills, `system/nightshift/` (session profiles), `system/dtcc/map.example.yaml`, `nightshift.py`, `dtcc_watch.py` and `active_projects.py` among the scripts, and `nightshift` and `dtcc-watch` in the unit list.
- **Requirements:** only what `check_deps.sh` actually checks for these features (verified when the plan is written).
- **The roadmap link** points at `docs/superpowers/roadmap.md`.
- Every other section is unchanged.

## 4. Tests

- `system/tests/vault_integrity.bats`, "no retired names remain in template content": the `road=` exception for the old roadmap filename is removed, because nothing the template owns names it any more.
- A new test in `system/tests/vault_integrity.bats`: every relative Markdown link target in `README.md` (not `http(s):`, `mailto:` or a bare `#anchor`; any `#anchor` suffix stripped) is a tracked file or directory. It fails when the roadmap moves before the README link changes.
- Bound tools: bats, the gate (`system/scripts/verify_setup.sh`).

## 5. Out of scope

- Renaming "Jarvis" in dated history documents.
- Changes to `CLAUDE.md`, commands or skills.
- Any feature work; this change is documentation and one test.
