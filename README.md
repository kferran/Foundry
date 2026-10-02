# Jarvis

An Obsidian + Claude Code "second brain" vault template.

> **Status:** built and tested. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)); `/setup` and the installed systemd units have not yet been run end to end. Memory capture and recall (Plan 3) are not built yet; `/setup` skips that step for now.

## What Jarvis is

Jarvis is a template repository that becomes your vault. You clone it (or create a repo from it), run `claude` inside it, and run `/setup`. Setup configures the vault for your machine, your schedule and your codebases. Nothing specific to a machine or a user is committed. Per-user state is generated at setup time and gitignored.

The vault compiles itself. Raw inputs (files you drop in, plus short digests of your Claude Code sessions) are compiled in batches into a wiki of concepts, entities, summaries and preferences. The wiki is split into `work`, `personal` and `shared` partitions, and links are not allowed to cross between `work` and `personal`. A derived SQLite FTS5 index lets agents ask the index for the notes they need before reading anything, so a lookup reads only the notes that answer it rather than the whole wiki.

Automation runs as isolated headless `claude -p` jobs on systemd user timers: intake, a morning brief and an evening debrief. Headless jobs never write to the vault directly. They write to a staging area, and a deterministic gate validates and publishes their output. Anything that has to be exact (parsing, validation, indexing, unit rendering, git remote handling) is done by a script. The model handles conversation and synthesis.

## Status

| Plan | Scope | Status |
|---|---|---|
| 0. Spike gate | Check headless isolation and hook behavior against the real `claude` binary (spec §7.4) | Complete: [plan](docs/superpowers/plans/2026-09-30-plan-0-spike.md), [results](docs/superpowers/spikes/2026-09-30-headless-and-hooks.md) |
| 1. Foundation | Baseline commit, `vaultlib`, schemas, linter, pre-commit hook, index | Complete: [plan](docs/superpowers/plans/2026-09-30-plan-1-foundation.md) |
| 2a. Headless core | Staged publish, `run_headless.sh`, intake daemon, redaction, settings files | Complete: [plan](docs/superpowers/plans/2026-10-01-plan-2a-headless-core.md) |
| 2b. Operations | Prep scripts, focus stats, unit templates and installer, remotes, codebase discovery | Complete: [plan](docs/superpowers/plans/2026-10-01-plan-2b-operations.md) |
| 4a. Commands and setup | `CLAUDE.md`, commands, personas, `/setup` (without memory), health suite | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-4a-commands-setup.md) |
| 3. Memory (Soundwave) | Capture/recall hooks, hook installer, `/digest` | Pending |
| 4b. Memory integration, renames | `/setup` memory step, README memory sections, final renames | Pending (after Plan 3) |
| 5. Preferences | Preference status derivation, acceptance in `/brief`, recall slot | Pending (after the core has run for a few weeks) |
| Sub-project 2 | Optimus orchestrator | Separate spec, after Plan 4b |

- Design spec: [docs/superpowers/specs/2026-09-30-vault-template-design.md](docs/superpowers/specs/2026-09-30-vault-template-design.md)
- Roadmap: [docs/superpowers/plans/2026-09-30-jarvis-roadmap.md](docs/superpowers/plans/2026-09-30-jarvis-roadmap.md)

Each plan is written only after the previous one is finished, because results carry forward. For example, the spike can change the permission model (spec §7), and that affects Plans 2–4.

## How it works

The intended loop is **capture → compile → index → recall → correct**:

1. **Capture.** Files you drop in go to `raw/inbox/`. In the vault and in registered codebases, a `Stop` hook asks for a short session digest once enough work has happened (default: 5 tool events and 20 minutes). The hook writes the digest, redacted, to `raw/<partition>/notes/`. `/digest` writes one on demand. Claude Code shows a Stop hook's request under the label "Stop hook error:"; for Jarvis that line starts with "Jarvis memory (not an error)" and simply asks for the digest.
2. **Compile.** The intake timer batches up to 5 inputs from one partition into an isolated headless `/ingest` run. For each fact, the run records an explicit noop, patch or create decision and writes its output to `wiki/.staging/<run_id>/`.
3. **Publish.** The publish gate validates schemas and partition walls and rejects changes that shrink existing notes. It also checks each target against a snapshot taken at the start of the run. If every check passes, it publishes everything at once. If any check fails, it publishes nothing and the run is quarantined. If you edited a note while the run was going, your edit is kept.
4. **Index.** Markdown is the source of truth. `system/index.db` is a gitignored SQLite FTS5 index that can be rebuilt at any time. Agents run `related`, `query`, `show` and `backlinks` against it before reading any notes.
5. **Recall.** A `SessionStart` hook adds up to about 9,500 characters of vault data to new sessions in scope: the latest digests for the codebase or partition and, once enabled, preferences you have confirmed. Recalled text is marked as data, not instructions.
6. **Correct.** Each digest has a Corrections section. Ingest turns these into `preference` notes with linked evidence. A preference's status is calculated in the index, and it becomes confirmed only after you accept it in `/brief`.

| Name | Role | Concrete artifacts (planned) |
|---|---|---|
| **Jarvis** | The vault / product | this repo, `jarvis-*` systemd units |
| **Optimus** | Chief of Staff persona; orchestrator in sub-project 2 | `system/agents/Optimus.md`, `agent_owner: Optimus` |
| **Wheeljack** | Headless intake compiler | `jarvis-intake.service`/`.timer`, `intake_daemon.sh`, `run_headless.sh ingest` |
| **Ultra Magnus** | Publish gate: validate, conflict-check, publish | `publish_staged.py`, `vaultlib/publish.py` |
| **Soundwave** | Memory capture and recall | `system/hooks/memory_*.sh`, `/digest`, `vault_index.py recall` |
| **The Ark** | The index | `system/index.db`, `vault_index.py` |
| **Teletraan** | Zero-token fleet watcher (reserved, sub-project 2) | `jarvis-watcher.service` (reserved) |
| **Autobots** | Ship-task crewmates (reserved, sub-project 2) | seeded from `CodingAgent.md`, `SystemMaintenance.md` |
| **Bumblebee** | Scout crewmates producing "recon" reports (reserved, sub-project 2) | reports land in `raw/inbox/` |

Script and module filenames stay descriptive so they are easy to grep. The themed names appear in unit `Description=` lines, log headers and documentation.

## Repository layout

The layout, abbreviated from spec §5. `system/hooks/`, `install_hooks.sh` and `/digest` arrive with Plan 3.

```
CLAUDE.md                     generic rules; imports @system/config.md
.claude/settings.json         interactive permissions
.claude/commands/             setup brief debrief ingest query lint backup impact digest
.githooks/pre-commit          deterministic linter (lint_vault.sh --staged)
raw/                          contents gitignored
  inbox/ archive/ telemetry/  manual drops, compiled drops, production-error notes
  <partition>/notes|archive/  session digests (created on demand)
wiki/
  Index.md                    cross-partition index, Dataview dashboards
  work/ personal/ shared/     concepts/ entities/ summaries/ preferences/
  .staging/                   headless output awaiting publish (gitignored)
briefings/                    daily brief and debrief notes
system/
  config.example.md           example global config (real config.md is gitignored)
  codebases/example.md        example codebase file
  headless.settings.json      headless permissions
  template_source             canonical template URL
  schemas/                    one schema note per note type
  hooks/                      user-level memory hooks (Soundwave)
  templates/ agents/          note templates, personas
  scripts/                    vault_index.py, vaultlib/, publish_staged.py, run_headless.sh,
                              intake_daemon.sh, install_units.sh, install_hooks.sh,
                              setup_remote.sh, update_template.sh, check_deps.sh, ...
  systemd/                    jarvis-{intake,brief,debrief,focus} unit templates (*.in)
  tests/                      vault_integrity.bats, scripts.bats, system_health.bats, python/
  fleet/                      reserved for sub-project 2 (gitignored)
docs/superpowers/             specs, plans, spike results
```

## Requirements

Jarvis targets Arch / Omarchy Linux. `system/scripts/check_deps.sh` checks for:

- `claude` (Claude Code), `git`, `jq`, `bats`, `flock`, `timeout`
- `python3` with PyYAML and pytest (`sudo pacman -S python-yaml python-pytest`). Missing PyYAML blocks setup.
- `sqlite3` built with FTS5
- systemd user units (`systemctl --user`, `systemd-analyze`). If you want timers to run while you are logged out, enable lingering.
- `gcalcli` for calendar input to the brief
- Hyprland (`hyprctl`) for the Obsidian focus tracker. It is optional, and only focus stats are lost without it.
- Optional: `herdr` or `tmux` as session backends for sub-project 2
- Obsidian, with the **Dataview** plugin recommended (`wiki/Index.md` dashboards are plain code blocks without it). **[Vault Curate](https://github.com/notoriouslab/vault-curate)** is an optional plugin for link suggestions. It is not a dependency.

## Getting started

```sh
git clone <template-url> my-vault    # or "Use this template" on the hosting site
cd my-vault
claude
> /setup
```

`/setup` is idempotent and can be re-run at any time. Its phases (spec §11):

0. **Preflight:** `check_deps.sh`. Missing items are listed with install hints.
1. **Existing config:** if `system/config.md` already exists, it is shown and edited, not overwritten.
2. **Interview:** timezone, brief and debrief times, superpowers, default partition, digest thresholds and recall budget.
3. **Codebases:** you choose repos from a directory scan. Each one is inspected, written to `system/codebases/<name>.md` with a partition, and confirmed with you field by field.
4. **Remote:** a `template` remote is added for updates, and you choose a private `origin`, no remote, or keep (maintainer mode).
5. **Units:** systemd timers are rendered and enabled, and you are offered linger.
6. **Memory hooks** (optional, arrives with Plan 3): you will be shown the diff to `~/.claude/settings.json`, and it will be applied only after an explicit yes. Setup skips this step for now.
7. **Calendar:** `gcalcli` auth is checked.
8. **Index and verify:** the index is rebuilt and `verify_setup.sh --health` runs.
9. **Hand-off:** an onboarding assignment note is created for each codebase.
10. **Report:** a status table of everything that was set up.

Once the units are installed, the timers run real headless `claude -p` jobs. They use your Claude subscription and are capped at 60 runs a day (`HEADLESS_MAX_RUNS_PER_DAY`).

## Security model

- **Headless isolation.** `run_headless.sh` is the only way automation calls `claude`. It runs in restricted mode with a dedicated settings file, no user settings, no user hooks, no MCP servers, no session persistence, a tool list per command, a timeout and a daily run cap. Reads are limited to the vault, writes are limited to the run's staging directory, and Bash runs in Claude Code's sandbox (no network) with sandbox auto-allow turned off, so only allowlisted commands run.
- **Staged publish.** Headless output reaches the wiki only through Ultra Magnus, which checks targets, schemas, partition walls, protected fields, shrinkage and conflicts. Every headless-written note gets `headless` added to its `provenance`.
- **Partition walls.** Links from `work` to `personal` (and the other way) are lint errors. A headless run writes to one partition plus `shared`. From a codebase session, the index CLI returns only that codebase's partition plus `shared`, and those sessions get no general read access to the vault. Walls control links and recall, not storage: all partitions are pushed to the same private `origin`.
- **Data, not instructions.** `CLAUDE.md` tells agents to treat note bodies, raw files, recall blocks and tool output as data. Digests and inbox copies are passed through `redact.py`, and `<private>…</private>` spans are removed.
- **User-level changes.** `install_hooks.sh` changes only its own entries in `~/.claude/settings.json` and `~/.claude/commands/digest.md`. It takes a backup first, shows a diff during `/setup`, applies nothing without confirmation, and can be fully reversed with `--uninstall`.
- **Trust dialog.** The first time you open the vault, Claude Code asks whether to trust the folder and lists the permissions `.claude/settings.json` pre-approves (wiki and briefing edits and the read-only `vault_index.py` commands). Those apply to your interactive sessions only; headless runs ignore project settings entirely.
- **Gitignored.** `raw/**` contents, `system/quarantine/*`, `system/logs/*`, `system/config.md`, `system/codebases/*.md` (except `example.md`), `.claude/settings.local.json`, `system/index.db*`, `wiki/.staging/`, `system/fleet/` and Obsidian workspace files.

## Updating and uninstalling

- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders the units, but only if this vault installed them. It never runs automatically.
- **Remove systemd units:** `system/scripts/install_units.sh --uninstall` removes only units whose header names this vault.
- **Remove memory hooks** (after Plan 3): `system/scripts/install_hooks.sh --uninstall` removes only the entries owned by this vault and the owned `/digest` command.

Both installers also accept `--dry-run`.

## Development

Work follows the superpowers workflow: brainstorm → spec in [`docs/superpowers/specs/`](docs/superpowers/specs/) → plan in [`docs/superpowers/plans/`](docs/superpowers/plans/) → test-driven implementation in small, focused commits. Spike results go in [`docs/superpowers/spikes/`](docs/superpowers/spikes/). Every finding from the design reviews is traced in spec §13.

The gating suites must pass at the end of every task. One command runs them all and exits non-zero if any fails:

```sh
system/scripts/verify_setup.sh            # every system/tests/*.bats except system_health.bats, then pytest
system/scripts/verify_setup.sh --health   # also the advisory live-state suite
```

`system/tests/system_health.bats` checks live service state and is advisory only. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand.

## Acknowledgements

- Yonatan Karp, [The self-compiling second brain](https://yonatankarp.com/blog/self-compiling-second-brain/): the capture → compile → recall model.
- [firstmate](https://github.com/kunchenguid/firstmate): the model for the Optimus orchestrator (sub-project 2).
- Projects from the ecosystem survey (spec §13.5). Each one contributed a design pattern; none is a dependency:
  - [open-second-brain](https://github.com/itechmeat/open-second-brain): corrections → preference notes with evidence
  - [DocMason](https://github.com/JetXu-LLM/DocMason), [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian): stage → validate → atomic publish
  - [second-brain-cloudflare](https://github.com/rahilp/second-brain-cloudflare), [agentmemory](https://github.com/rohitg00/agentmemory), [sage-wiki](https://github.com/xoai/sage-wiki): note lifecycle fields, `<private>` redaction, per-source caps
  - [chubbyskills](https://github.com/chubbyguan/chubbyskills): content-hash duplicate skip, run ledger, retry
  - [memU](https://github.com/NevaMind-AI/memU): explicit noop / patch / create decisions
  - [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory): recall item caps and timeout
  - [makerskills](https://github.com/coreyhaines31/makerskills): contradiction, staleness and topic-gap lint checks
  - [agent-second-brain](https://github.com/smixs/agent-second-brain): daily headless run cap
  - [Vault Curate](https://github.com/notoriouslab/vault-curate): optional link-suggestion plugin
