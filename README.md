# The Foundry

An Obsidian + Claude Code "second brain" vault template.

> **Status:** built and tested on one machine. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)) and passed again with the humanizer self-edit step ([record](docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md)). Memory capture and recall passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md)) and stay off until you install their hooks, which `/setup` offers. A full `/setup` with installed systemd units has not yet been run end to end; that happens after Plan 8 (laptop plus server).

## What The Foundry is

The Foundry is a template repository that becomes your vault. You clone it (or create a repo from it), run `claude` inside it, and run `/setup`. Setup configures the vault for your machine, your schedule and your codebases. Nothing specific to a machine or a user is committed. Per-user state is generated at setup time and gitignored.

The vault compiles itself. Raw inputs (files you drop in, plus short digests of your Claude Code sessions) are compiled in batches into a wiki of concepts, entities, summaries and preferences. The wiki is split into `work`, `personal` and `shared` partitions, and links are not allowed to cross between `work` and `personal`. A derived SQLite FTS5 index lets agents ask the index for the notes they need before reading anything, so a lookup reads only the notes that answer it rather than the whole wiki.

Agents follow the writing rules in `CLAUDE.md`: chat replies are sized by type (quick answer, one-screen task report, or a linked document), and notes avoid common AI writing tells. The headless intake, brief and debrief runs edit their own prose against the vendored [humanizer](#acknowledgements) skill before they publish, and `/humanizer` runs it interactively.

Automation runs as isolated headless `claude -p` jobs on systemd user timers: intake, a morning brief and an evening debrief. Headless jobs never write to the vault directly. They write to a staging area, and a deterministic gate validates and publishes their output. Anything that has to be exact (parsing, validation, indexing, unit rendering, git remote handling) is done by a script. The model handles conversation and synthesis.

## Status

| Plan | Scope | Status |
|---|---|---|
| 0. Spike gate | Check headless isolation and hook behavior against the real `claude` binary (spec §7.4) | Complete: [plan](docs/superpowers/plans/2026-09-30-plan-0-spike.md), [results](docs/superpowers/spikes/2026-09-30-headless-and-hooks.md) |
| 1. Foundation | Baseline commit, `vaultlib`, schemas, linter, pre-commit hook, index | Complete: [plan](docs/superpowers/plans/2026-09-30-plan-1-foundation.md) |
| 2a. Headless core | Staged publish, `run_headless.sh`, intake daemon, redaction, settings files | Complete: [plan](docs/superpowers/plans/2026-10-01-plan-2a-headless-core.md) |
| 2b. Operations | Prep scripts, focus stats, unit templates and installer, remotes, codebase discovery | Complete: [plan](docs/superpowers/plans/2026-10-01-plan-2b-operations.md) |
| 4a. Commands and setup | `CLAUDE.md`, commands, personas, `/setup` (without memory), health suite | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-4a-commands-setup.md) |
| 3. Memory | Capture/recall hooks, hook installer, `/digest` | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-3-memory.md), [acceptance](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md) |
| 4b. Memory integration, renames | `/setup` memory step, README memory sections, final renames | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-4b-memory-integration.md), [live check](docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md) |
| 6. Communication | `CLAUDE.md` Writing section, vendored humanizer skill, headless self-edit pass | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-6-communication.md), [acceptance](docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md) |
| 8a. Machine roles and Debian | `machine_role` (standalone, server, client), `check_deps --role` with apt hints, units by role, Debian proven natively | Complete: [plan](docs/superpowers/plans/2026-10-03-plan-8a-roles-debian.md), [acceptance](docs/superpowers/spikes/2026-10-03-plan-8a-acceptance.md) |
| 8d. Calendar from the connector | Brief calendar from the installed Google Calendar connector | Complete: [plan](docs/superpowers/plans/2026-10-04-plan-8d-calendar-connector.md), [acceptance](docs/superpowers/spikes/2026-10-04-plan-8d-acceptance.md) |
| 8b. Commit history | Scripted commit messages, one commit per headless run | Complete: [plan](docs/superpowers/plans/2026-10-04-plan-8b-commit-history.md), [acceptance](docs/superpowers/spikes/2026-10-04-plan-8b-acceptance.md) |
| 8c. Sync | `vault_sync.sh`, server sync units, conflicts, client setup. The real vault is set up after this plan | Complete: [plan](docs/superpowers/plans/2026-10-04-plan-8c-sync.md), [acceptance](docs/superpowers/spikes/2026-10-04-plan-8c-acceptance.md) |
| 8e. Real-use fixes | Brief and debrief wait out an ingest backlog; `/debrief` reads the ledger's publish fields | Complete: [plan](docs/superpowers/plans/2026-10-05-plan-8e-real-use-fixes.md), [acceptance](docs/superpowers/spikes/2026-10-05-plan-8e-acceptance.md) |
| 9. Product rename | The Foundry names and the capability seam | Complete: [plan](docs/superpowers/plans/2026-10-05-plan-9-foundry-rename.md), [spec](docs/superpowers/specs/2026-10-05-foundry-rename-design.md), [acceptance](docs/superpowers/spikes/2026-10-05-plan-9-acceptance.md) |
| 11. Meetings | Gemini notes fetched from Google Drive and dropped transcripts become meeting notes, tracked actions and searchable transcripts | Complete: [plan](docs/superpowers/plans/2026-10-05-plan-11-meetings.md), [spec](docs/superpowers/specs/2026-10-05-meetings-design.md), [acceptance](docs/superpowers/spikes/2026-10-06-plan-11-acceptance.md) |
| 12. minutes plugin | Meeting notes and the confined connector fetch as a public Claude Code plugin (its own repo), then vendored here like humanizer | In progress: spec revised after two reviews; plan next |
| 7. Style lint | Warning-only `style-*` checks for wiki and briefing notes | After the real vault has run a few weeks |
| 5. Preferences | Preference status derivation, acceptance in `/brief`, recall slot | After the real vault has run a few weeks |
| Sub-project 2 | the Foreman orchestrator | Separate spec, after Plans 7 and 5 |
| 10. Migrate Cerebro and Wong | Import both older systems, then decommission them (Sub-project 3) | Last |

- Design spec: [docs/superpowers/specs/2026-09-30-vault-template-design.md](docs/superpowers/specs/2026-09-30-vault-template-design.md)
- Roadmap: [docs/superpowers/plans/2026-09-30-jarvis-roadmap.md](docs/superpowers/plans/2026-09-30-jarvis-roadmap.md)

Plans are numbered in the order they were defined, not the order they run; the table is in run order. Each plan is written only after the previous one is finished, because results carry forward. For example, the spike can change the permission model (spec §7), and that affects Plans 2–4.

## How it works

The intended loop is **capture → compile → index → recall → correct**:

1. **Capture.** Files you drop in go to `raw/inbox/`, and meeting transcripts to `meetings/drop/<partition>/` (a server with `meetings_enabled` also fetches Gemini notes from Google Drive); each meeting becomes a meeting note with tracked action items and a searchable transcript. Once the memory hooks are installed, sessions in the vault and in registered codebases also leave short, redacted session digests in `raw/<partition>/notes/` (see [Memory](#memory) below).
2. **Compile.** The intake timer batches up to 5 inputs from one partition into an isolated headless `/ingest` run. For each fact, the run records an explicit noop, patch or create decision and writes its output to `wiki/.staging/<run_id>/`.
3. **Publish.** The publish gate validates schemas and partition walls and rejects changes that shrink existing notes. It also checks each target against a snapshot taken at the start of the run. If every check passes, it publishes everything at once. If any check fails, it publishes nothing and the run is quarantined. If you edited a note while the run was going, your edit is kept.
4. **Index.** Markdown is the source of truth. `system/index.db` is a gitignored SQLite FTS5 index that can be rebuilt at any time. Agents run `related`, `query`, `show` and `backlinks` against it before reading any notes.
5. **Recall.** With the memory hooks installed, a `SessionStart` hook adds up to `recall_budget_chars` of vault data (default 9,000 characters, never more than 9,500) to new sessions in scope: the latest digests for the codebase or partition and, once enabled, preferences you have confirmed. Recalled text is marked as data, not instructions.
6. **Correct.** Each digest has a Corrections section. Ingest turns these into `preference` notes with linked evidence. A preference's status is calculated in the index, and it becomes confirmed only after you accept it in `/brief`.

**History.** `/backup` first commits each headless run that published files, one commit per run, with a message `commit_runs.py` builds from the run's records (no model writes it). Each carries `Foundry-Command`, `Foundry-Run` and `Foundry-Role` trailers, so `git log` reads as a handoff log: `git log --grep 'Foundry-Command: ingest'` lists the ingest runs.

| Name | Role | Concrete artifacts |
|---|---|---|
| **The Foundry** | The vault / product | this repo, `foundry-*` systemd units |
| **The Foreman** | The only role you address: briefings, debriefs and the agenda; the orchestrator in Sub-project 2 | `system/agents/foreman.md`, `/brief`, `/debrief` |
| **Workcells** | Specialist agents, each dispatched by the capabilities it lists | `system/agents/workcells/*.md` (each lists its `capabilities`), `capability` on concept notes |
| **The Core** | The compiled wiki, the index and memory | `wiki/`, plus the index and memory rows below |
| index | Search and views over the wiki | `system/index.db`, `vault_index.py` |
| memory | Session digest capture and recall | `system/hooks/memory_*.sh`, `/digest`, `vault_index.py recall` |
| intake compiler | Headless compile of raw inputs | `foundry-intake.service`/`.timer`, `intake_daemon.sh`, `run_headless.sh ingest` |
| publish gate | Validate, conflict-check, publish | `publish_staged.py`, `vaultlib/publish.py` |
| watcher | Zero-token watcher of Workcell sessions (reserved, Sub-project 2) | `foundry-watcher.service` (reserved) |
| Workcell sessions | Ship and scout sessions of a Workcell (reserved, Sub-project 2); scout reports land in `raw/inbox/` | `system/jobs/` (reserved), `FOUNDRY_WORKCELL_SESSION` |
| Production Job, Work Order | A multi-step assignment and each of its tasks (Sub-project 2) | `FOUNDRY_WORK_ORDER`, the digest field `work_order` |

Script and module filenames stay descriptive so they are easy to grep. Unit `Description=` lines read `The Foundry: <role>`, and log and alert tags use plain names (`[intake]`, `[memory]`, `[sync]`).

## Memory

Memory is part of The Core. It is optional and off until you install its hooks. `/setup` offers them in its memory step: it shows the change `system/scripts/install_hooks.sh --dry-run` would make to your user-level `~/.claude/settings.json`, explains each entry, and installs only after an explicit yes. Declining leaves memory off; re-run `/setup` to turn it on later.

| Entry | What it does |
|---|---|
| `memory_recall.sh` (`SessionStart`) | Adds recent digests for the codebase or partition to a new session, up to `recall_budget_chars` (default 9,000 characters), marked as vault data, not instructions |
| `memory_capture.sh` (`Stop`) | After enough work (`digest_min_events` tool events and `digest_min_minutes` minutes since the last digest, default 5 and 20), asks for a short digest once, then redacts it and writes it to `raw/<partition>/notes/` |
| `memory_activity.sh` (`PostToolUse`) | Counts edits and Bash calls toward that threshold |
| three `permissions.allow` rules | Let codebase sessions run `vault_index.py related`, `show` and `backlinks`, which return only that codebase's partition plus `shared` |
| `~/.claude/commands/digest.md` | The `/digest` command, written only if you have no `digest.md` of your own |

The hooks run in every Claude Code session on the machine but act only inside the vault and registered codebases. Headless runs, subagents and `claude -p` scripts are skipped.

**"Stop hook error" is not an error.** Claude Code labels every request from a `Stop` hook "Stop hook error:". When the vault asks for a digest, you see `Stop hook error: Foundry memory (not an error): please reply with a short session digest. …`; Claude replies with the digest and the session carries on. The hook never asks twice in a row, and not when Claude's last reply ended with a question to you.

**`/digest`** writes a digest of the work since the last one whenever you want, in any session in scope. The `Stop` hook captures it from the reply; no script or session id is needed.

## Repository layout

The layout, abbreviated from spec §5. `/digest` is not in the repo: it is a user-level command that `install_hooks.sh` writes to `~/.claude/commands/digest.md`, so it works in codebase sessions too.

```
CLAUDE.md                     generic rules; imports @system/config.md
.claude/settings.json         interactive permissions
.claude/commands/             setup brief debrief ingest query lint backup impact
.claude/skills/humanizer/     vendored humanizer v3.0.0 (MIT): /humanizer, headless self-edit
.githooks/pre-commit          deterministic linter (lint_vault.sh --staged)
.scratch/                     throwaway clones, worktrees and temp files (ignored; the gate's temp files go here)
raw/                          contents gitignored
  inbox/ archive/ telemetry/  manual drops, compiled drops, production-error notes
  <partition>/notes|archive/  session digests and meeting inputs (created on demand)
  meetings/                   fetched Gemini notes awaiting import
meetings/drop/work|personal/  dropped meeting transcripts (committed and synced; imported, then removed)
wiki/
  Index.md                    cross-partition index, Dataview dashboards
  work/ personal/ shared/     concepts/ entities/ summaries/ preferences/
  work/ personal/meetings/    meeting notes and their transcripts
  .staging/                   headless output awaiting publish (gitignored)
briefings/                    daily brief and debrief notes
system/
  config.example.md           example global config (real config.md is gitignored)
  codebases/example.md        example codebase file
  headless.settings.json      headless permissions
  template_source             canonical template URL
  schemas/                    one schema note per note type
  hooks/                      user-level memory hooks
  templates/                  note templates
  agents/                     foreman.md (the Foreman persona)
    workcells/                one file per Workcell, with its capabilities
  scripts/                    vault_index.py, vaultlib/, publish_staged.py, run_headless.sh,
                              intake_daemon.sh, install_units.sh, install_hooks.sh,
                              setup_remote.sh, update_template.sh, check_deps.sh, ...
  systemd/                    foundry-{intake,brief,debrief,focus,meetings} unit templates (*.in)
  tests/                      *.bats per area (system_health.bats is advisory), python/ for pytest
  jobs/                       reserved for Sub-project 2 (gitignored)
docs/superpowers/             specs, plans, spike results
```

## Machine roles

Each machine that holds the vault has a `machine_role` in its own `system/config.md`, chosen in `/setup`:

| Role | Runs | Use it for |
|---|---|---|
| `standalone` (default) | intake, brief, debrief and focus units, and the meetings fetch when enabled; memory hooks; codebases | one machine that does everything |
| `server` | intake, brief and debrief units, and the meetings fetch when enabled; memory hooks; codebases | an always-on machine that runs the automation and your coding sessions |
| `client` | nothing automated | reading and editing the vault in Obsidian on another machine |

A server and its clients share the vault through a private `origin` (`remote_mode: private`):

- **Server.** `vault_sync.sh` runs every `sync_interval_minutes` (`foundry-sync.timer`) and before and after every run: it commits headless runs and other changes with scripted messages, merges `origin` and pushes. Network and credential failures never stop the runs; they are alerted once a day until sync works again.
- **Client.** The Obsidian Git plugin commits and syncs every few minutes; `/setup` prints its settings. Write notes in today's briefing between `#wiki-ingest-start` and `#wiki-ingest-end`: the server compiles each new block and leaves the briefing as it is (on every role, blocks stay in the briefing after compiling). Files in `raw/inbox/` on a client are not synced. Meeting transcripts dropped into `meetings/drop/<partition>/` are synced, and the server imports them; move a finished file in (an empty one is quarantined).

### Sync conflicts

A conflict is never resolved automatically. The server aborts the merge, pushes its side to `foundry/server-pending` on `origin`, writes `system/logs/sync-blocked`, alerts once, and skips intake, brief and debrief until it is resolved. Resolve it on the other machine (for `foundry/server-pending`, a client):

```sh
git fetch origin
git merge origin/foundry/server-pending   # a client's own conflict uses origin/foundry/client-pending
# fix the conflicted files, then
git commit
git push
```

On the machine that pushed the pending branch, its side is already checked out: run `git merge origin/<branch>` there instead (`<branch>` is the vault's branch), then resolve, commit and push.

The next server sync clears the marker, deletes the pending branch and starts a brief or debrief that was skipped today. The pre-commit hook rejects any file that still holds conflict markers; if a client note that bypassed the hook blocks your commit, the hook names it: fix it, or commit with `--no-verify` knowingly.

## Requirements

The Foundry runs on Arch / Omarchy and on Debian. `system/scripts/check_deps.sh --role <role>` checks what that role needs and prints `pacman` or `apt` install hints:

- `claude` (Claude Code), `git`, `jq`, `bats`, `flock`, `timeout`
- `python3` with PyYAML and pytest (`sudo pacman -S python-yaml python-pytest`). Missing PyYAML blocks setup.
- `sqlite3` built with FTS5
- systemd user units (`systemctl --user`, `systemd-analyze`). If you want timers to run while you are logged out, enable lingering.
- A Google Calendar connector on the Claude account the brief machine is logged in with, for calendar input to the brief. Without it the brief lists the calendar under Unavailable Sources. Each morning fetch costs about $0.20.
- Hyprland (`hyprctl`) for the Obsidian focus tracker, on a standalone machine only. Without it only focus stats are lost.
- A client needs only `claude`, `git`, `jq`, `python3` with PyYAML, and SQLite with FTS5.
- Optional: `herdr` or `tmux` as session backends for sub-project 2
- Obsidian, with the **Dataview** plugin recommended (`wiki/Index.md` dashboards are plain code blocks without it). **[Vault Curate](https://github.com/notoriouslab/vault-curate)** is an optional plugin for link suggestions. It is not a dependency.

## Getting started

Before you start, install what [Requirements](#requirements) lists and sign in to Claude Code (`claude`, then `/login`). For a server or a client, also create an **empty private repository** for your vault on your git host: that is your private `origin`, and every machine syncs through it.

**First machine (standalone or server).** Clone the template, start Claude Code in it, and paste the prompt below with your answers filled in:

```sh
git clone <template-url> my-vault    # or "Use this template" on the hosting site
cd my-vault
claude
```

**A client.** Set up the first machine first. Then clone your private vault (not the template) and paste the same prompt with `client` as the role:

```sh
git clone <private origin> my-vault
cd my-vault
claude
```

The prompt:

```text
Set up this clone as a new Foundry vault. Run /setup and use these answers; ask me only for what is missing:
- Machine role: <standalone | server | client>
- Timezone: <Area/City>; brief at <HH:MM>; debrief at <HH:MM>
- Default partition: <work | personal>
- Remote: private, origin <private origin URL>   (or: none, standalone only)
- Codebases to register: <paths, or none>          (not used on a client)
- Memory hooks: <yes | no>                         (not used on a client)
Never push to the template repository. Before installing units or memory hooks,
show me what will change and wait for my yes. Run any command that needs sudo
(linger) only by giving it to me. When you finish, show the /setup report table
and list what I still have to do by hand.
```

You can also type `/setup` and answer its questions one at a time; the prompt only gives it the answers up front. On a server, `/setup` stops at the units phase until linger is on (`sudo loginctl enable-linger $USER`, which you run yourself). On a client it ends with the Obsidian Git settings to enter and asks you to make one test edit.

`/setup` is idempotent and can be re-run at any time. Its phases (spec §11):

- **0. Role and preflight:** you choose the machine role, then `check_deps.sh --role <role>` lists missing items with install hints. A client skips phases 3, 6 and 9; on a client, phases 5 and 5a only remove units and hooks left from an earlier role.
- **1. Existing config:** if `system/config.md` already exists, it is shown and edited, not overwritten.
- **2. Interview:** timezone, brief and debrief times, superpowers, default partition, digest thresholds and recall budget.
- **3. Codebases:** you choose repos from a directory scan. Each one is inspected, written to `system/codebases/<name>.md` with a partition, and confirmed with you field by field.
- **4. Remote:** a `template` remote is added for updates, and you choose a private `origin`, no remote, or keep (maintainer mode). A server or client must use a private `origin`; setup checks that git can reach it without a prompt and publishes the branch.
- **5. Units:** the role's systemd units are rendered and enabled, and you are offered linger (required on a server).
- **5a. Memory hooks** (optional): you are shown the diff to `~/.claude/settings.json` and what each hook does, and it is applied only after an explicit yes. Declining leaves memory off (see [Memory](#memory)).
- **6. Calendar:** one fetch from the Google Calendar connector checks that the brief can read today's events.
- **7. Index:** the index is rebuilt.
- **8. Verify:** `verify_setup.sh --health` runs.
- **9. Hand-off:** an onboarding assignment note is created for each codebase.
- **10. Report:** a status table of everything that was set up.

Once the units are installed, the timers run real headless `claude -p` jobs. They use your Claude subscription and are capped at 60 runs a day (`HEADLESS_MAX_RUNS_PER_DAY`).

## Security model

- **Headless isolation.** `run_headless.sh` is the only way automation calls `claude`. It runs in restricted mode with a dedicated settings file, no user settings, no user hooks, no MCP servers, no session persistence, a tool list per command, a timeout and a daily run cap. Reads are limited to the vault, writes are limited to the run's staging directory, and Bash runs in Claude Code's sandbox (no network) with sandbox auto-allow turned off, so only allowlisted commands run.
- **Staged publish.** Headless output reaches the wiki only through the publish gate, which checks targets, schemas, partition walls, protected fields, shrinkage and conflicts. Every headless-written note gets `headless` added to its `provenance`.
- **Partition walls.** Links from `work` to `personal` (and the other way) are lint errors. A headless run writes to one partition plus `shared`. From a codebase session, the index CLI returns only that codebase's partition plus `shared`, and those sessions get no general read access to the vault. Walls control links and recall, not storage: all partitions are pushed to the same private `origin`.
- **Data, not instructions.** `CLAUDE.md` tells agents to treat note bodies, raw files, recall blocks and tool output as data. Digests and inbox copies are passed through `redact.py`, and `<private>…</private>` spans are removed.
- **User-level changes.** `install_hooks.sh` changes only its own entries in `~/.claude/settings.json` and `~/.claude/commands/digest.md`. It takes a backup first, shows a diff during `/setup`, applies nothing without confirmation, and can be fully reversed with `--uninstall`.
- **Trust dialog.** The first time you open the vault, Claude Code asks whether to trust the folder and lists the permissions `.claude/settings.json` pre-approves: edits under `wiki/` and `briefings/`, the brief and debrief prep scripts, `lint_vault.sh`, and the `vault_index.py` query, index-rebuild and recall commands. Those apply to your interactive sessions only; headless runs ignore project settings entirely.
- **Gitignored.** `raw/**` contents, `system/quarantine/*`, `system/logs/*`, `system/config.md`, `system/codebases/*.md` (except `example.md`), `.claude/settings.local.json`, `system/index.db*`, `system/*.lock`, `wiki/.staging/`, `system/jobs/` and Obsidian workspace files.

## Updating and uninstalling

- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders the units, but only if this vault installed them. It never runs automatically.
- **Update the humanizer skill:** `.claude/skills/humanizer/` is humanizer v3.0.0, copied unchanged with its MIT license. To move to a newer version, copy the new `SKILL.md` and `LICENSE` over it by hand in the template repo, then update the version and checksum in `system/tests/vault_integrity.bats` and the version in this README. Vaults receive it through `update_template.sh`.
- **Remove systemd units:** `system/scripts/install_units.sh --uninstall` removes only units whose header names this vault.
- **Remove memory hooks:** `system/scripts/install_hooks.sh --uninstall` removes only the entries owned by this vault, any container the install had to create, and the owned `/digest` command. It still works if the hook files are gone.

Both installers also accept `--dry-run`.

## Development

Work follows the superpowers workflow: brainstorm → spec in [`docs/superpowers/specs/`](docs/superpowers/specs/) → plan in [`docs/superpowers/plans/`](docs/superpowers/plans/) → test-driven implementation in small, focused commits. Spike results go in [`docs/superpowers/spikes/`](docs/superpowers/spikes/). Every finding from the design reviews is traced in spec §13.

The gating suites must pass at the end of every task. One command runs them all and exits non-zero if any fails:

```sh
system/scripts/verify_setup.sh            # every system/tests/*.bats except system_health.bats, then pytest
system/scripts/verify_setup.sh --health   # also the advisory live-state suite
```

`system/tests/system_health.bats` checks live service state and is advisory only. To prove the suite on Debian, run `system/tests/verify_on_host.sh <ssh-host>`: it copies the committed tree to a temporary directory on that host, runs the gate there, and exits with its code. The host needs the `apt` packages `check_deps.sh` lists. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand. After any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands, re-run the live acceptance steps (Plan 4a, Task 9) in a throwaway clone.

## Acknowledgements

- Yonatan Karp, [The self-compiling second brain](https://yonatankarp.com/blog/self-compiling-second-brain/): the capture → compile → recall model.
- [firstmate](https://github.com/kunchenguid/firstmate): the model for the Foreman orchestrator (Sub-project 2).
- [humanizer](https://github.com/blader/humanizer) by Siqi Chen (MIT): vendored in `.claude/skills/humanizer/`; its wording rules are condensed in `CLAUDE.md` and applied by the headless commands before they write.
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
