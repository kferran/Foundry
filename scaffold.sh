#!/bin/bash
# Universal Scaffold Script for Linux Omarchy AI Wiki Compiler
# Run this from the root of your Obsidian Vault (e.g. ~/Documents/ObsidianVault)
# after `git init`. Then launch `claude` in the vault and run /setup.
set -euo pipefail

VAULT_ROOT="$(pwd)"
BRAIN_TZ="${BRAIN_TZ:-America/Denver}"   # /setup confirms or rewrites this

if [ ! -d ".git" ]; then
  echo "⚠️  $VAULT_ROOT is not a git repo. Run 'git init' first (Step 1), then re-run this script."
  exit 1
fi

missing=()
for dep in claude git jq bats gcalcli systemctl; do
  command -v "$dep" >/dev/null 2>&1 || missing+=("$dep")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "⚠️  Missing tools (install before /setup): ${missing[*]}"
fi

echo "🏗️  Scaffolding Second Brain Multi-Agent Framework in $VAULT_ROOT ..."

# ---------------------------------------------------------------------------
# 1. System Directory Enclosures
# ---------------------------------------------------------------------------
mkdir -p .claude/commands
mkdir -p raw/archive
mkdir -p wiki
mkdir -p briefings
mkdir -p system/templates
mkdir -p system/agents
mkdir -p system/logs
mkdir -p system/scripts
mkdir -p system/tests
mkdir -p system/quarantine
mkdir -p system/systemd

# ---------------------------------------------------------------------------
# 2. Base Configurations
# ---------------------------------------------------------------------------
cat << 'EOF' > .gitignore
.obsidian/workspace.json
.obsidian/graph.json
.claude/config.json
.claude/sessions/
.claude/history/
.claude/logs/
!.claude/commands/
!.claude/commands/*.md
EOF

cat << 'EOF' > CLAUDE.md
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
EOF

# ---------------------------------------------------------------------------
# 3. Custom Slash Commands
# ---------------------------------------------------------------------------
cat << 'EOF' > .claude/commands/setup.md
---
description: Interactive onboarding — interviews you for codebase path, timezone and strategic anchors, installs systemd timers, and hands off the Ultron codebase audit.
---

You are the System Architecture Provisioning Tool. Your job is to onboard this second brain and activate its systemd service tier safely.

`scaffold.sh` has already written every file. Verify files; only write one if it is missing. Never overwrite existing notes.

## Phase 1 — Onboarding Interview
Ask these one at a time. Show the default and wait for the answer before moving on.
1. **Codebase Target Path** — default `~/code/worktrees/main`.
   - Verify the path exists and contains `ultron-ui/` and `Ultron.Api/`. Report anything missing.
2. **Timezone Location** — default `America/Denver` (MDT/MST).
   - Validate it against `timedatectl list-timezones`.
3. **Corporate Milestones / Superpowers** — free-text list of strategic value anchors (e.g. "Ultron Annuity Engine Stability", "Core Compliance Velocity").

Write the answers to `system/config.md`:
```yaml
---
type: config
codebase_path: <answer 1>
frontend_dir: ultron-ui/
backend_dir: Ultron.Api/
timezone: <answer 2>
superpowers:
  - <answer 3, one item per line>
---
```
If the codebase path differs from the default, update the **Codebase Map** in `CLAUDE.md`.

## Phase 2 — Verify Scaffold
1. Confirm these directories exist: `raw/`, `raw/archive/`, `wiki/`, `briefings/`, `system/templates/`, `system/agents/`, `system/logs/`, `system/scripts/`, `system/tests/`, `system/quarantine/`, `system/systemd/`.
2. Confirm `CLAUDE.md`, `.gitignore`, all templates, all three agent personas, all scripts, and `system/tests/vault_integrity.bats` exist.
3. Check dependencies with `command -v`: `claude`, `git`, `jq`, `bats`, `gcalcli`, `hyprctl`. List anything missing with its install command (`sudo pacman -S <pkg>` or `yay -S <pkg>` on Omarchy).

## Phase 3 — Install Systemd User Units
The unit files live in `system/systemd/` so they stay under version control.
1. If the timezone from Phase 1 is not `America/Denver`, replace it in `system/systemd/brain-brief.timer` and `system/systemd/brain-debrief.timer`.
2. Run `mkdir -p ~/.config/systemd/user && cp system/systemd/*.service system/systemd/*.timer ~/.config/systemd/user/`.
3. Run `systemctl --user daemon-reload`.
4. Run `systemctl --user enable --now brain-intake.timer ultron-telemetry.timer brain-brief.timer brain-debrief.timer brain-focus-tracker.service`.
5. If `brain-focus-tracker.service` fails because it can't see the compositor, run `systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE` and restart it.

## Phase 4 — Verification Matrix
1. Run `system/scripts/verify_setup.sh` and report each test result.
2. Run `systemctl --user list-timers` and confirm the next run time of all four timers.

## Phase 5 — Ultron Codebase Analysis Hand-Off
1. Create `wiki/UltronOnboardingAssignment.md` using the `system/templates/wiki-concept.md` frontmatter (`agent_owner: CodingAgent`).
2. In it, direct the **Coding Agent** to:
   - Map the codebase at `codebase_path`, separating Vue 3 UI components (`ultron-ui/`) from .NET Core WebAPI modules (`Ultron.Api/`).
   - Catalog structured Log Event IDs, custom telemetry definitions, log categories and error-handling namespaces.
   - Compile the findings into `wiki/UltronLogEventMap.md`.
3. Link each superpower from `system/config.md` to the assignment as its strategic anchor.

Present a markdown matrix mapping every provisioned entity and its status.
EOF

cat << 'EOF' > .claude/commands/brief.md
---
description: Instructs the Chief of Staff to pull real-time data from localized terminal tool definitions to build the morning alignment matrix.
---

You are the Chief of Staff (CoS) Agent. Your task is to query local platform interfaces to compile today's operational landscape.

Execute these data compilation steps:
0. **Load Context**: Read `system/config.md` for the timezone, codebase path and superpowers. If it is missing, tell the user to run `/setup` first.
1. **Calendar Intake Protocol**:
   - Execute `gcalcli agenda "$(date +%Y-%m-%d)T00:00" "$(date +%Y-%m-%d)T23:59" --tsv` using your terminal execution tool.
   - Filter rows to identify hard time commitments, operational standups, or strategic review slots.
2. **Gmail Intake Protocol**:
   - Parse local mail files or pull unread headers matching labels like `[Action Required]` or transaction flags from upstream registries.
   - Isolate message blocks detailing infrastructure alerts or critical partner escalations.
3. **Raw Intake Check**:
   - List any files still waiting in `raw/` (not `raw/archive/`) and in `system/quarantine/`.
   - Treat any file with `type: production_error` as critical and route it to **SystemMaintenance** per `CLAUDE.md`.
4. **Focus Log Parse**:
   - Read `system/logs/obsidian_focus_$(date +%Y-%m-%d).log` (written by `track_obsidian.sh`). If it's missing, use yesterday's log and say so.
   - Summarize the most-focused notes and flag any **Focus Fragmentation Warning** per `CLAUDE.md`.
5. **Open Project Ingestion**:
   - Scan the `wiki/` catalog for active architectural milestones (such as active **Ultron .NET WebAPI migrations** or **Vue state architecture refactoring tasks**) and any node with `is_friction: true`.
6. **Synthesize Alignment Matrix**:
   - If `briefings/YYYY-MM-DD.md` does not exist, create it from `system/templates/daily-briefing.md` exactly, filling `{{date}}` and setting `status: active`. Never overwrite an existing briefing.
   - Write the aggregated frames into its `🌅 Morning Alignment` section and friction items into the `🛑 Real-Time Workflow Friction Matrix`.
   - Tie each objective to a superpower from `system/config.md` where one fits.
   - Distribute actionable execution slices directly to the sub-agent directives (`CodingAgent` or `SystemMaintenance`).

Begin morning initialization loops.
EOF

cat << 'EOF' > .claude/commands/debrief.md
---
description: Feeds local git diff logs into the CoS and reviews end-of-day Slack/Gmail traffic for outstanding items.
---

You are the Chief of Staff (CoS) Agent running the evening synchronization loop.

Execute these sequence steps:
1. **Collect Physical Code State (Git Diffs)**:
   - Run `git log @{u}..HEAD --oneline` or check active branch diffs across the main code base and your vault repository.
   - Use these logs to reconstruct a precise chronological record of changes made by the Coding Agents.
2. **Skim Digital Traffic (Slack & Email)**:
   - Poll your end-of-day email and Slack incoming data layers for messages received during focus blocks.
   - Isolate mentions, direct messages, or priority threads that might contain missed dependencies or immediate roadblocks.
3. **Calculate Workspace Focus Metrics**:
   - Locate today's interaction file inside `system/logs/obsidian_focus_YYYY-MM-DD.log`.
   - If the file exists, compile the raw rows to determine the top 3 most-opened files.
   - Inject a punchy summary into the `🌌 Evening Debriefing` section detailing focus distributions.
4. **Aggregate Code Base Compilation Metrics**:
   - Scan `system/logs/` for new `compilation-metric.json` updates generated during today's session.
   - Aggregate telemetry numbers into an executive summary chart within the evening briefing ledger (tracking tests executed, green suite verifications, and coverage changes).
   - Quarantine and flag any agent work cycles where `test_suite_passed` returns false.
5. **Analyze Daily Operational Friction**:
   - Parse `system/logs/` files for repeated failures or rapid focus changes.
   - Summarize performance bottlenecks clearly inside the `Real-Time Workflow Friction Matrix` section of today's file.
   - Propose an automated architectural standard change or a simplified decision path to eliminate the recurring roadblock tomorrow morning.
6. **Harvest Conversation Session Logs**:
   - Claude Code stores session transcripts as `.jsonl` files under `~/.claude/projects/`, in a folder named after this vault's path (slashes and dots become dashes, e.g. `-home-kyle-Documents-ObsidianVault`).
   - Read today's most recent transcript there. Parse it as JSON lines and only use the user and assistant message text.
   - Extract statements where the user explicitly set formatting choices, design overrides, or project goals.
   - Compile these into atomic notes in `wiki/`, or append them as verified goals to tomorrow's morning brief layout. Never copy secrets, tokens, or credentials out of a transcript.

Begin evening debrief consolidation.
EOF

cat << 'EOF' > .claude/commands/ingest.md
---
description: Compiles raw documents into atomic, interlinked evergreen wiki pages.
argument-hint: <file-path>
---

You are the Ingestion Workflow Agent for this Second Brain. Your job is to process the raw input file passed via $ARGUMENTS.

Follow these strict operational steps:
1. **Analyze Input**: Read the file specified in $ARGUMENTS (e.g., inside the `raw/` directory).
2. **Context Discovery**: Use your file search tools to scan the `wiki/` directory. Look for existing notes that share concepts, keywords, or topics with the new input.
3. **Draft Wiki Node**:
   - Create a clean, structural note in `wiki/` using PascalCaseName or lowercase-slug for the filename.
   - Include valid frontmatter at the top:
     ```yaml
     ---
     type: concept
     tags: []
     compiled_at: $CURRENT_DATE
     ---
     ```
   - Transform the chaotic raw text into highly synthesized, evergreen markdown.
4. **Compile Connections**:
   - Add bidirectional wikilinks `[[Note Name]]` between this new page and the existing pages you discovered in Step 2.
   - Edit the parent or index notes in `wiki/` to thread this new node into the active brain ecosystem.
5. **Execute Uncertainty Regex Scan**:
   - Parse raw content body against the following friction footprint regex:
     `\b(not\s+sure|waiting\s+on|stuck|blocked|fails?|error|verify|review|tbd|double-check)\b/i`
   - If a match is found, append an `is_friction: true` key to the frontmatter of the compiled `wiki/` target.
   - Insert an explicit notification block into the active `briefings/` ledger alerting the CoS to surface this point in the morning status alignment.
6. **Version Control**: Once the files are successfully written, use your terminal execution tool to stage the changes (`git add raw/ wiki/`) and present a summary of the updates to the user.

Execute the compilation for: $ARGUMENTS
EOF

cat << 'EOF' > .claude/commands/query.md
---
description: Queries compiled wiki nodes to synthesize an architectural or systemic answer.
argument-hint: <question>
---

You are the Search & Synthesis Agent for this Second Brain.

Your task is to answer the user's prompt using ONLY the compiled knowledge present in the `wiki/` and `system/` directories. Do not rely on generic pre-trained knowledge if a conflict arises with local notes.

Steps:
1. Parse the user's core query: "$ARGUMENTS"
2. Search and read through relevant `wiki/` markdown files matching these concepts.
3. Synthesize a comprehensive response.
4. Include an explicit "Sources Compiled" section at the bottom of your response, listing the exact internal files you read using `[[Note Name]]` syntax.

Begin processing query: $ARGUMENTS
EOF

cat << 'EOF' > .claude/commands/lint.md
---
description: Audits the vault for broken wiki-links, missing metadata, and orphan notes.
---

You are the Vault Integrity Agent. Scan the files inside the `wiki/` directory to ensure system health.

Perform the following diagnostics:
1. **Dead Links**: Search for any `[[Note Name]]` internal links where the corresponding file does not exist in `wiki/`.
2. **Orphan Pages**: Identify any markdown files in `wiki/` that are not linked to by any other file in the vault.
3. **Metadata Check**: Verify that all files in `wiki/` contain the mandatory `type:`, `tags:`, and `compiled_at:` YAML frontmatter.

Provide a scannable markdown report of your findings. If errors are found, ask if you should proceed to fix them automatically.
EOF

cat << 'EOF' > .claude/commands/backup.md
---
description: Bundles compiled wiki nodes, writes a semantic commit message, and pushes to git.
---

You are the Git Sync Agent for this Second Brain. Your job is to cleanly version control and back up all modified text layers.

Follow these strict operational steps:
1. **Verify Integrity Gates**:
   - Check `system/logs/compilation-metric.json` telemetry.
   - **Quarantine Condition**: If the last 3 consecutive logs for an agent target display `test_suite_passed: false` or `warnings_generated > 5`, invoke the quarantine routine.
   - **Isolation Actions**:
     - Halt staging procedures for that specific subdirectory.
     - Move the agent configuration context out of the executable layer: `mv system/agents/CodingAgent.md system/quarantine/CodingAgent.stalled`.
     - Log a critical break indicator trace directly into the evening briefing output: "⚠️ CRITICAL WRAPPER TRIGGERED: Coding Agent quarantined due to automated runtime loop failures."
2. **Run Validation Tests**: Run `system/scripts/verify_setup.sh`. If any test fails, stop — do not stage or commit — and report the failing tests.
3. **Check Workspace State**: Run `git status --porcelain` using your terminal execution tool to find out what files in `raw/`, `wiki/`, or `system/` have been modified, added, or deleted.
4. **Evaluate Scope**:
   - If no files are modified, stop and inform the user that the brain is already up to date.
   - If files are modified, stage all outstanding structural changes by running `git add raw/ wiki/ briefings/ system/ CLAUDE.md .claude/commands/`.
5. **Draft Semantic Commit Message**:
   - Analyze the exact names of the files that changed to understand what was ingested or modified.
   - Construct a highly precise, clean commit message following Conventional Commits format.
6. **Execute Commit**: Commit the staged changes with your generated message via `git commit -m "<message>"`.
7. **Push to Remote**: Run `git push` to sync the state to your upstream server. If no remote is configured, say so and stop after the commit.
8. **Report Summary**: Present a clean markdown block showing the commit hash, the exact message used, and a list of files successfully backed up.

Begin backing up the second brain repository.
EOF

cat << 'EOF' > .claude/commands/impact.md
---
description: Analyzes downstream architectural impacts and structural code blast radii across Vue/.NET trees before a refactor.
argument-hint: <component>
---

You are the Change-Impact Mapping Agent for this platform workspace. Your task is to calculate the precise downstream code dependency blast radius for: $ARGUMENTS

Read `codebase_path` from `system/config.md` (default `~/code/worktrees/main`). This is read-only analysis — do not modify any code.

Execute these boundary discovery sequences:
1. **Frontend Code Search (Vue 3)**:
   - Search `<codebase_path>/ultron-ui` for occurrences of `$ARGUMENTS` across all `.vue`, `.js`, and `.ts` files to capture Pinia stores, component injections, router entries and API client calls.
2. **Backend Domain Search (.NET 10)**:
   - Search `<codebase_path>` for occurrences of `$ARGUMENTS` inside all `.cs` and `.csproj` files to locate entity models, DI registrations, services and API route controllers.
   - Match API routes found here to the UI client calls from step 1, so a change on one side shows every consumer on the other.
3. **Internal Wiki Synthesis**:
   - Cross-reference `wiki/` for strategy documents or architectural plan notes mapping to this entity, including Log Event IDs in `wiki/UltronLogEventMap.md`.
4. **Compile Boundary Blast Matrix**:
   - A scannable table: `File | Layer (UI/API) | Relationship | Blast Radius (High/Med/Low)`, categorized by dependency complexity.
   - List affected files with no test coverage.
   - Offer to draft an intent proposal from `system/templates/intent-shaper.md` with the **Downstream Impact & Risk Radii** section filled in.

Begin analyzing boundary impacts for: $ARGUMENTS
EOF

# ---------------------------------------------------------------------------
# 4. System Blueprints & Templates
# ---------------------------------------------------------------------------
cat << 'EOF' > system/templates/wiki-concept.md
---
type: concept
tags: []
compiled_at: {{date}}
agent_owner: {{agent_name}}
---

# {{title}}

## Executive Summary

## Core Architecture & Context

## Interlinked Concepts
- [[IndexNote]]

## Audit Trail
- Source Material: [[raw/{{source_file}}]]
EOF

cat << 'EOF' > system/templates/daily-briefing.md
---
type: briefing
date: {{date}}
status: {{status}}
---

# Daily Briefing & Operational Ledger: {{date}}

## 🌅 Morning Alignment (08:00)

### 1. Active Objectives & Context Boundaries

## 🛑 Real-Time Workflow Friction Matrix
- **Systemic Blockers**:
- **Focus Drift Analysis**:
- **Communication Debt**:

## 🌌 Evening Debriefing (17:00)

### 1. Execution Logs & Results

### 2. System State Deltas
EOF

cat << 'EOF' > system/templates/intent-shaper.md
---
type: plan_gate
target_branch: {{branch_name}}
status: PENDING_REVIEW
created_at: {{date}}
superpower_alignment: {{strategic_focus}}
---

# Intent Proposal: {{short_feature_description}}

## ⚡ Superpowers & Strategic Framework Alignment
- **Core Alignment**: {{Identify the specific high-leverage objective being unblocked}}
- **Business Value Anchor**:

## 🧠 Brainstorming Architecture & Written Plans
- **Upstream Strategy Node**: [[wiki/{{StrategicPlanningNote}}]]
- **Architectural Constraints**:

## 🛠️ Proposed File Mutations & Execution Tools
- **Execution Vectors**:

| File Path | Action (Modify/Create/Delete) | Reason for Change |
|-----------|-------------------------------|-------------------|
| {{path_1}} | Modify | |

## 🧪 Verification Strategy (Second Brain Integrity & Telemetry Gates)
- **Second Brain BATS Harness**: `system/tests/vault_integrity.bats`
- **Metric Verification Hook**: `system/templates/compilation-metric.json`
- **Planned Coverage Target**:

## 🛑 Downstream Impact & Risk Radii
EOF

cat << 'EOF' > system/templates/compilation-metric.json
{
  "timestamp": "{{timestamp}}",
  "branch": "{{git_branch}}",
  "target_feature_slice": "{{vertical_slice_name}}",
  "artifacts": {
    "files_mutated": [],
    "tests_discovered": 0
  },
  "verification_gates": {
    "test_suite_passed": false,
    "linter_passed": false,
    "test_coverage_delta": "+0.00%"
  },
  "system_telemetry": {
    "build_duration_ms": 0,
    "warnings_generated": 0
  }
}
EOF

# ---------------------------------------------------------------------------
# 5. Sub-Agent Personas
# ---------------------------------------------------------------------------
cat << 'EOF' > system/agents/ChiefOfStaff.md
# Role Profile: Chief of Staff (CoS) Agent

You manage the coordination layer of the second brain. Your goal is to synthesize task statuses, surface critical data dependencies, and prevent information overload.
EOF

cat << 'EOF' > system/agents/CodingAgent.md
# Role Profile: Coding Agent

- **Operational Paradigm**: You operate under a delegated-contributor model within an established test harness environment.
- **Core Domain**: You own functional features, code refactoring, and automated test writing inside the code base directory.
- **Automated Metric Dispatch**: Before signaling task completion, you must output a completed instance of `system/templates/compilation-metric.json` into the `system/logs/` path.
- **Verification Priority**: The `test_suite_passed` parameter must verify as true against actual local execution runtimes before data compilation is considered valid.
EOF

cat << 'EOF' > system/agents/SystemMaintenance.md
# Role Profile: System Maintenance Agent

- **Operational Paradigm**: You act as an autonomous extension monitoring repository health, dependency configurations, and infrastructure parameters.
- **Core Domain**: You own environmental integrity, executing background operations like automated linting, system updates, and repository optimization.
EOF

# ---------------------------------------------------------------------------
# 6. Automation Scripts
#    Scripts locate the vault relative to themselves (system/scripts/ -> ../..),
#    so no hardcoded vault path is needed.
# ---------------------------------------------------------------------------
cat << 'EOF' > system/scripts/intake_daemon.sh
#!/bin/bash
VAULT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$VAULT_PATH" || exit 1

CURRENT_DAILY="briefings/$(date +%Y-%m-%d).md"

# Pull any #wiki-ingest-start ... #wiki-ingest-end block out of today's briefing into raw/
if [ -f "$CURRENT_DAILY" ]; then
  AWK_EXTRACT=$(awk '/#wiki-ingest-start/,/#wiki-ingest-end/ {if ($0 !~ /#wiki-ingest/) print}' "$CURRENT_DAILY")
  if [ -n "$AWK_EXTRACT" ]; then
    TMP_DROP="raw/daily_note_drop_$(date +%s).md"
    echo "$AWK_EXTRACT" > "$TMP_DROP"
    sed -i '/#wiki-ingest-start/,/#wiki-ingest-end/ d' "$CURRENT_DAILY"
  fi
fi

mkdir -p raw/archive system/quarantine system/logs

for file in raw/*; do
  [ -f "$file" ] || continue
  FILENAME=$(basename "$file")
  LOG_FILE="system/logs/intake_$(date +%Y-%m-%d).log"

  # -p = headless (print) mode; -c would try to resume an interactive session
  if claude -p "/ingest $file" >> "$LOG_FILE" 2>&1; then
    mv "$file" raw/archive/
  else
    mv "$file" "system/quarantine/$FILENAME"
    echo "- [ ] CRITICAL FAULT: Raw file \`$FILENAME\` failed compilation." >> "briefings/$(date +%Y-%m-%d).md" 2>/dev/null
  fi
done
EOF

cat << 'EOF' > system/scripts/track_obsidian.sh
#!/bin/bash
LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../logs" && pwd)"
mkdir -p "$LOG_DIR"

while true; do
  CURRENT_DATE=$(date +%Y-%m-%d)
  TIMESTAMP=$(date +%H:%M:%S)
  WINDOW_TITLE=""

  if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    if command -v hyprctl &> /dev/null; then
      WINDOW_TITLE=$(hyprctl activewindow -j | jq -r '.title // empty')
    elif command -v swaymsg &> /dev/null; then
      WINDOW_TITLE=$(swaymsg -t get_tree | jq -r '.. | select(.focused? == true) | .name // empty')
    fi
  fi

  # Obsidian titles look like "Note Name - Vault Name - Obsidian v1.x.x"
  if [[ "$WINDOW_TITLE" == *"Obsidian"* ]]; then
    NOTE_NAME=$(echo "$WINDOW_TITLE" | awk -F ' - ' '{print $1}')
    echo "[$TIMESTAMP] $NOTE_NAME" >> "$LOG_DIR/obsidian_focus_$CURRENT_DATE.log"
  fi

  sleep 30
done
EOF

cat << 'EOF' > system/scripts/telemetry_enricher.sh
#!/bin/bash
# Context-Driven Telemetry Ingestion Engine for Ultron Production Errors
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ULTRON_REPO="${ULTRON_REPO:-$HOME/code/worktrees/main}"
RAW_DIR="$VAULT_ROOT/raw"
mkdir -p "$RAW_DIR"

# Simulation of incoming Kusto telemetry row data (swap for a real Kusto query later)
MOCK_EXCEPTION="System.NullReferenceException"
MOCK_MSG="Object reference not set to an instance of an object at Ultron.Core.Services.WithdrawalParsingService.MapDelta"
MOCK_OP_ID="ERR-$(date +%s)"
TARGET_FILE="$RAW_DIR/kusto_enriched_${MOCK_OP_ID}.md"

echo "🔍 Enriching incoming error telemetry string against code repository history..."

# Extract the class name from the stack frame footprint:
# "at Namespace.Class.Method" -> "Class" (second-to-last dotted segment)
FRAME=$(echo "$MOCK_MSG" | grep -oE 'at [A-Za-z0-9_.]+' | head -n 1 | cut -d' ' -f2)
TARGET_CLASS=$(echo "$FRAME" | awk -F. 'NF>=2 {print $(NF-1)}')

FILE_PATH="Unknown (class matching footprint not found in active workspace branches)"
LAST_COMMIT="N/A"
AUTHOR="Unknown"
COMMIT_DATE="N/A"
COMMIT_MSG="N/A"

if [ -n "$TARGET_CLASS" ] && git -C "$ULTRON_REPO" rev-parse --git-dir >/dev/null 2>&1; then
  # git ls-files is fast and skips node_modules/bin/obj automatically
  FOUND=$(git -C "$ULTRON_REPO" ls-files -- "*${TARGET_CLASS}.cs" | head -n 1)
  if [ -n "$FOUND" ]; then
    FILE_PATH="$FOUND"
    # Last commit that touched the whole file (a stronger signal than blaming lines 1-10)
    LAST_COMMIT=$(git -C "$ULTRON_REPO" log -1 --format="%h" -- "$FOUND")
    AUTHOR=$(git -C "$ULTRON_REPO" log -1 --format="%an" -- "$FOUND")
    COMMIT_DATE=$(git -C "$ULTRON_REPO" log -1 --format="%ad" --date=short -- "$FOUND")
    COMMIT_MSG=$(git -C "$ULTRON_REPO" log -1 --format="%s" -- "$FOUND")
  fi
else
  FILE_PATH="Repository path unreachable during background compilation pass"
fi

cat << TELEMETRY > "$TARGET_FILE"
---
type: production_error
service: UltronWebApi
exception: ${MOCK_EXCEPTION}
operation_id: ${MOCK_OP_ID}
detected_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
is_friction: true
assigned_agent: SystemMaintenance
---

# 🚨 Enriched Production Exception: ${MOCK_EXCEPTION}

## Telemetry Context
- Service Source: \`UltronWebApi\`
- Operation ID: \`${MOCK_OP_ID}\`

## 🧠 Codebase Attribution Layer
- Suspect Target File: \`${FILE_PATH}\`
- Last Commit Touching File: \`${LAST_COMMIT}\`
- Last Modifying Developer: \`${AUTHOR}\` (${COMMIT_DATE})
- Commit Message Footprint: "${COMMIT_MSG}"

## Exception Message
\`\`\`text
${MOCK_MSG}
\`\`\`
TELEMETRY

echo "✅ Telemetry context node synthesized at $TARGET_FILE"
EOF

cat << 'EOF' > system/scripts/verify_setup.sh
#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
echo "🚀 Invoking BATS Test Architecture Suite..."
bats system/tests/vault_integrity.bats
EOF

# ---------------------------------------------------------------------------
# 7. Systemd User Units (installed into ~/.config/systemd/user by /setup)
#    Unquoted heredocs: $VAULT_ROOT and $BRAIN_TZ are filled in now.
#    %h is a systemd specifier for your home directory.
# ---------------------------------------------------------------------------
UNIT_PATH="PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin"

cat << EOF > system/systemd/brain-intake.service
[Unit]
Description=Second Brain: compile raw/ into wiki/

[Service]
Type=oneshot
WorkingDirectory=$VAULT_ROOT
Environment=$UNIT_PATH
ExecStart=$VAULT_ROOT/system/scripts/intake_daemon.sh
EOF

cat << EOF > system/systemd/brain-intake.timer
[Unit]
Description=Second Brain: raw/ intake every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

cat << EOF > system/systemd/ultron-telemetry.service
[Unit]
Description=Ultron: context-driven telemetry enricher

[Service]
Type=oneshot
WorkingDirectory=$VAULT_ROOT
Environment=$UNIT_PATH
ExecStart=$VAULT_ROOT/system/scripts/telemetry_enricher.sh
EOF

cat << EOF > system/systemd/ultron-telemetry.timer
[Unit]
Description=Ultron: telemetry enricher every 15 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF

cat << EOF > system/systemd/brain-brief.service
[Unit]
Description=Second Brain: Chief of Staff morning brief

[Service]
Type=oneshot
WorkingDirectory=$VAULT_ROOT
Environment=$UNIT_PATH
ExecStart=/usr/bin/env claude -p "/brief"
StandardOutput=append:$VAULT_ROOT/system/logs/brief.log
StandardError=append:$VAULT_ROOT/system/logs/brief.log
EOF

cat << EOF > system/systemd/brain-brief.timer
[Unit]
Description=Second Brain: morning brief at 06:00

[Timer]
OnCalendar=*-*-* 06:00:00 $BRAIN_TZ
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat << EOF > system/systemd/brain-debrief.service
[Unit]
Description=Second Brain: Chief of Staff evening debrief

[Service]
Type=oneshot
WorkingDirectory=$VAULT_ROOT
Environment=$UNIT_PATH
ExecStart=/usr/bin/env claude -p "/debrief"
StandardOutput=append:$VAULT_ROOT/system/logs/debrief.log
StandardError=append:$VAULT_ROOT/system/logs/debrief.log
EOF

cat << EOF > system/systemd/brain-debrief.timer
[Unit]
Description=Second Brain: evening debrief at 17:00

[Timer]
OnCalendar=*-*-* 17:00:00 $BRAIN_TZ
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat << EOF > system/systemd/brain-focus-tracker.service
[Unit]
Description=Second Brain: Obsidian focus tracker
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart=$VAULT_ROOT/system/scripts/track_obsidian.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical-session.target
EOF

# ---------------------------------------------------------------------------
# 8. BATS Infrastructure Testing Layout
# ---------------------------------------------------------------------------
cat << 'EOF' > system/tests/vault_integrity.bats
#!/usr/bin/env bats

setup() {
  VAULT_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  cd "$VAULT_ROOT" || exit 1
}

@test "Verify required directory structural enclosures exist" {
  [ -d "raw/archive" ]
  [ -d "wiki" ]
  [ -d "briefings" ]
  [ -d "system/agents" ]
}

@test "Verify mandatory configuration manual blueprints are present" {
  [ -f "CLAUDE.md" ]
  [ -f "system/templates/wiki-concept.md" ]
  [ -f "system/templates/daily-briefing.md" ]
}

@test "Verify context-driven telemetry engine scripts are flagged as executable" {
  [ -x "system/scripts/telemetry_enricher.sh" ]
}

@test "Verify telemetry enricher runs cleanly and produces output files" {
  rm -f raw/kusto_enriched_*.md
  run system/scripts/telemetry_enricher.sh
  [ "$status" -eq 0 ]
  run bash -c "ls raw/kusto_enriched_*.md"
  [ "$status" -eq 0 ]
  rm -f raw/kusto_enriched_*.md
}

@test "Verify active 15-minute systemd telemetry unit timer state" {
  run systemctl --user is-active ultron-telemetry.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify underlying systemd telemetry background service unit loads cleanly" {
  run systemctl --user list-units --type=service --all
  [[ "$output" == *"ultron-telemetry.service"* ]]
}

@test "Verify 6am MT morning briefing systemd user timer is active" {
  run systemctl --user is-active brain-brief.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify 5pm MT evening debriefing systemd user timer is active" {
  run systemctl --user is-active brain-debrief.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify raw/ intake systemd user timer is active" {
  run systemctl --user is-active brain-intake.timer
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify Obsidian focus tracker service is running" {
  run systemctl --user is-active brain-focus-tracker.service
  [ "$status" -eq 0 ]
  [ "$output" = "active" ]
}

@test "Verify /setup onboarding config exists" {
  [ -f "system/config.md" ]
}
EOF

# ---------------------------------------------------------------------------
# 9. Git Pre-Commit Hook Integration Layer
# ---------------------------------------------------------------------------
if [ -d .git ]; then
  cat << 'EOF' > .git/hooks/pre-commit
#!/bin/bash
echo "🚀 Running System Integrity Linter via Claude Code Engine..."
if ! claude -p "/lint"; then
  echo "❌ Validation failed: Vault metadata anomalies discovered. Aborting commit."
  exit 1
fi
echo "✅ System validation passed. Proceeding with backup serialization."
exit 0
EOF
  chmod +x .git/hooks/pre-commit
fi

# ---------------------------------------------------------------------------
# 10. Execution Controls
# ---------------------------------------------------------------------------
chmod +x system/scripts/*.sh

cat << EOF
✅ Scaffolding complete in $VAULT_ROOT

Next steps:
  1. rm scaffold.sh
  2. herdr
  3. claude            (from this directory)
  4. /setup            (confirm codebase path, timezone $BRAIN_TZ, superpowers)
  5. systemctl --user list-timers
     systemctl --user status brain-focus-tracker
EOF
