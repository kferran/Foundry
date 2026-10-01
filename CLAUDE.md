# AI Wiki Compiler Rules & Agentic Workflow Manual

## Directory Map
- `raw/`: Unstructured incoming streams (drafts, clippings, dump receipts).
- `wiki/`: Evergreen, atomic knowledge graph entries.
- `system/agents/`: Persona prompt boundaries for individual agents.
- `briefings/`: Chronological briefing ledger notes.

## Multi-Agent Operational Hierarchy
1. **Chief of Staff (CoS)**: Owns the briefings/ timeline, agenda generation, and overall task delegation loops.
2. **Technical Execution Agents**: Own individual node updates within wiki/ and perform software refactoring tasks.

## Build, Maintenance & Integration Scripts
- Ingest Source: `/ingest <file-path>` -> Formulates node updates using `system/templates/wiki-concept.md`.
- Daily Brief Run: `/brief` -> Triggers CoS to calculate the current calendar/email delta and create today's briefing file.
- Daily Debrief Run: `/debrief` -> Evaluates all modifications made across the repo and finalizes today's ledger.
- Integrity Audit: `/lint` -> Automatically executed by the Git pre-commit script.
- Impact Analysis: `/impact <component>` -> Maps downstream blast radius across Vue views and .NET endpoints before a refactor.
- Knowledge Query: `/query <question>` -> Answers from compiled `wiki/` nodes only.
- Backup: `/backup` -> Runs validation tests, commits, and pushes.
- Onboarding: `/setup` -> Interactive interview, systemd install, Ultron hand-off.

## Codebase Map
- **Codebase Root**: `~/code/worktrees/main` (confirmed by `/setup`, stored in `system/config.md`).
- **Frontend**: `ultron-ui/` — Vue 3 components, views, stores.
- **Backend**: `Ultron.Api/` — .NET Core WebAPI controllers, services, DTOs.
- **Telemetry Index**: `wiki/UltronLogEventMap.md` — structured Log Event IDs, telemetry definitions, error namespaces.
- **Filenames**: `wiki/` nodes use `PascalCaseName.md` or `lowercase-slug.md`.

## 🗣️ User Persona & Communication Rules
- **No Preamble**: Never start responses with conversational filler. Dive directly into the answer or execution output in the very first sentence.
- **Jargon Prohibition**: Avoid abstract, high-level AI industry buzzwords and verbose technical padding unless explicitly initiated or requested by the user. Use punchy, universal terminology.
- **Scannable Layouts**: Prioritize short, active-voice sentences. Group operational data using visual anchors (bolding key variables and system entities) and clean markdown tables/bullet fragments.
- **Anti-Refusal Stance**: Never include generic meta-commentary explaining why an action cannot be performed due to security or design constraints. State what is done or request missing keys neutrally.

## 📐 Strategic Intent Shaper Requirements
- **Plan Rigor Rule**: Coding agents must shift engineering rigor to the planning stage. Every `intent-shaper` proposal must trace its technical lineage back to an active brainstorming or written plan node in `wiki/` before the proposal can be submitted for review.
- **Tool-Bound Validation**: Agents must explicitly list which automated execution tools and testing frameworks (e.g., BATS harnesses) are bound to the change vector, guaranteeing that validation metrics back-feed to the ledger cleanly upon completion.

## 🔍 Production Telemetry & Intent Gate Routing Rules
- **Kusto Intake Hook**: Automated production error files generated from Kusto alert pipelines are treated as critical, high-friction items. The CoS must automatically bypass normal queues and route these exceptions to the **System Maintenance Agent** to immediately inspect local repository branches for correlating code commits.
- **Intent Gate Audit**: The /lint tool will flag an active compilation run as invalid if any files inside code subdirectories have been altered without a matching `status: APPROVED` entry inside the `system/logs/` tracking paths.

## ⚠️ Friction Identification & Remediation Rules
- **Focus Fragmentation Threshold**: If the active focus log reveals more than 4 distinct `wiki/` file swaps within a 15-minute window, log a **Focus Fragmentation Warning** in the evening debriefing sheet.
- **Fail-Fast Loop Breaker**: If a specific Coding Agent sub-task generates 3 consecutive `test_suite_passed: false` results, the CoS must instantly revoke the agent's write access to that file branch and flag the blocking test trace for your immediate review.
- **Decision Clarity Ingestion**: Flag any incoming email or Slack items containing uncertainty keywords (e.g., "not sure," "waiting on approval," "stuck") as **Immediate Architectural Friction**, moving them to the top of the action queue to bypass meeting delays.
- **Harness-Driven Extraction**: When processing external event text or raw chat-driven interface logs, do not swallow formatting blocks. Extract raw text components explicitly using regex or JSON keys, mapping updates safely to markdown nodes without corrupting metadata headers.
- **Verification Over Ingestion**: Treat raw logs as an immutable audit layer. The CoS must check the factual validity of an execution record against physical filesystem deltas before linking it as a verified asset in `wiki/`.
- **Shift-Left Priority Parsing**: Flag all tasks matching terms like "runtime failure," "broken link," or "merge conflict" with immediate critical priority, routing them instantly to the System Maintenance directives.
