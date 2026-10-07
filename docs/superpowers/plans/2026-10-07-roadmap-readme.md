# Roadmap and README Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The roadmap moves to `docs/superpowers/roadmap.md` and covers the work since Plan 11 and the agreed order; the README summarizes status, links to the roadmap, and documents the Nightshift, the DTCC watcher and Active Projects.

**Architecture:** Documentation plus one test. The roadmap is the one detailed status table; the README keeps a short summary and links to it. A new bats test checks that every relative link in the README names a tracked file, so a moved file cannot leave a dead README link.

**Tech Stack:** Markdown, bats 1.8.2, git.

**Spec:** `docs/superpowers/specs/2026-10-07-roadmap-readme-design.md`

## Global Constraints

- Work on branch `docs/roadmap-readme` of `kferran/Foundry` (spec at its first commit). Every task commits there. No task pushes or opens a pull request.
- Dated documents that cite the old roadmap path or the old product name stay as they are.
- New prose follows the Writing rules in `CLAUDE.md` (condensed humanizer rules).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. Read verdicts from exit codes, never through a pipe.
- Template rule: never commit a hostname, user path, remote URL or distro choice.
- Run one suite as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/vault_integrity.bats` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh` from the repository root.
- Bound tools: bats (`system/tests/vault_integrity.bats`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step; replace it with the "Replace with" text exactly.

## Review Focus

- A README link to a file that a later change moves or deletes must fail the gate. Pinned by `every relative link in README.md names a tracked file or folder` (Task 1), shown red by the move itself.
- A README link with a `#anchor` suffix must be checked against its file, without the anchor. The test strips `#…` before the lookup (Task 1).
- External links (`http(s):`, `mailto:`) and in-page anchors (`#status`) must not fail the test. They are skipped (Task 1).
- The retired-name test must still catch the old product name in the README once its exception is gone. Task 1 removes the `road=` exception; the README no longer names the old path.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/superpowers/roadmap.md` (moved from `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`) | the one detailed status table and the agreed order |
| `README.md` (modify) | status summary, Daily use, feature notes, layout, Requirements |
| `system/tests/vault_integrity.bats` (modify) | the README-link test; the retired-name test without its roadmap exception |

---

### Task 1: Move the roadmap and guard README links

**Files:**
- Move: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` → `docs/superpowers/roadmap.md`
- Modify: `README.md` (the roadmap link), `system/tests/vault_integrity.bats`

**Interfaces:**
- Produces: the bats test `every relative link in README.md names a tracked file or folder`, which Task 3 relies on.

- [ ] **Step 1: Add the link test and drop the old-name exception**

Edit 1 in `system/tests/vault_integrity.bats`. Find:

````text
  [ "$(sort <<< "$caps")" = "$enum" ]
}

````

Replace with:

````text
  [ "$(sort <<< "$caps")" = "$enum" ]
}

@test "every relative link in README.md names a tracked file or folder" {
  bad=""
  for t in $(grep -oE '\]\([^) ]+\)' README.md | sed -E 's/^\]\(//; s/\)$//; s/#.*//'); do
    case $t in ''|http://*|https://*|mailto:*) continue ;; esac
    if [ -z "$(git ls-files -- "$t" | head -n 1)" ]; then bad="$bad $t"; fi
  done
  printf 'unresolved:%s\n' "$bad"
  [ -z "$bad" ]
}

````

Edit 2 in `system/tests/vault_integrity.bats`. Find:

````text
  road="2026-09-30-jar""vis-roadmap\.md"
  url="$(head -n 1 system/template_source | sed 's/[.[\*^$#]/\\&/g')"  # read at run time; never written in a test
  out="$( { git grep -h -i -E "$OLD" -- "${OWN[@]}"; git grep -h -i -E "$OLD" -- system/codebases/example.md; } \
    | sed -e "s#$road##g" -e "s#$url##g" | grep -i -E "$OLD" || true)"
````

Replace with:

````text
  url="$(head -n 1 system/template_source | sed 's/[.[\*^$#]/\\&/g')"  # read at run time; never written in a test
  out="$( { git grep -h -i -E "$OLD" -- "${OWN[@]}"; git grep -h -i -E "$OLD" -- system/codebases/example.md; } \
    | sed -e "s#$url##g" | grep -i -E "$OLD" || true)"
````


- [ ] **Step 2: Run the suite to verify the retired-name test fails**

Run: `mkdir -p .scratch/tmp && TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/vault_integrity.bats`
Expected: FAIL, 1 of 19: `no retired names remain in template content`, printing the README's `Roadmap:` line (it names the old filename, which no longer has an exception). The new README-link test passes on today's README.

- [ ] **Step 3: Move the roadmap**

Run: `git mv docs/superpowers/plans/2026-09-30-jarvis-roadmap.md docs/superpowers/roadmap.md`

Run the suite again (command as in Step 2).
Expected: FAIL, 2 of 19: `every relative link in README.md names a tracked file or folder` prints `unresolved: docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`, and the retired-name test still fails on the same README line.

- [ ] **Step 4: Point the README at the new path**

Edit 1 in `README.md`. Find:

````text
- Roadmap: [docs/superpowers/plans/2026-09-30-jarvis-roadmap.md](docs/superpowers/plans/2026-09-30-jarvis-roadmap.md)
````

Replace with:

````text
- Roadmap: [docs/superpowers/roadmap.md](docs/superpowers/roadmap.md)
````


- [ ] **Step 5: Run the suite to verify it passes**

Run: `git add README.md system/tests/vault_integrity.bats`, then the suite (command as in Step 2).
Expected: PASS, `1..19`, no `not ok`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-1.txt`:

```text
docs: move the roadmap to docs/superpowers/roadmap.md

The roadmap is a living document, so it drops the dated, old-name path.
A new test checks that every relative link in the README names a
tracked file, and the retired-name test no longer needs its exception
for the old roadmap filename.
```

Run: `git commit -q -F .scratch/msg-1.txt`

---

### Task 2: Bring the roadmap up to date

**Files:**
- Modify: `docs/superpowers/roadmap.md`

**Interfaces:**
- Consumes: the moved file from Task 1.

- [ ] **Step 1: Edit the roadmap**

Edit 1 in `docs/superpowers/roadmap.md`. Find:

````text
# Jarvis Vault Template: Implementation Roadmap
````

Replace with:

````text
# The Foundry: Roadmap
````

Edit 2 in `docs/superpowers/roadmap.md`. Find:

````text
| **Sub-project 2** | §16 | Separate brainstorm → spec → plan (the Foreman orchestrator). **Binding rule (user, 2026-10-05):** the Foreman is the only role the user addresses; every other worker is discovered and dispatched by capability, never by name, so workers can be added, removed, renamed or replaced without changing how the user works with the system | After Plans 7 and 5 (user order, 2026-10-02) |
````

Replace with:

````text
| **Sub-project 2** | §16 | Separate brainstorm → spec → plan (the Foreman orchestrator). **Binding rule (user, 2026-10-05):** the Foreman is the only role the user addresses; every other worker is discovered and dispatched by capability, never by name, so workers can be added, removed, renamed or replaced without changing how the user works with the system. It absorbs the Nightshift as its unattended execution layer: queue items become Work Orders (plan items ship, research items scout) and the Nightshift runner becomes the watcher's unattended mode (user, 2026-10-07) | Next brainstorm after RCA-to-Jira phase 1 and the `/ingest` preference notes (user order, 2026-10-07) |
````

Edit 3 in `docs/superpowers/roadmap.md`. Find:

````text
| **12. minutes plugin** | Separate public repo `kferran/minutes`, spec `docs/superpowers/specs/2026-10-06-minutes-design.md` there | The parts of Plan 11 not tied to the vault, as a Claude Code plugin with two skills: `meeting-notes` (Gemini Docs and `.vtt`/`.srt`/`.txt`/`.md` transcripts to a meeting note and a transcript note, with the safety cleaning; Python 3.9 standard library) and `confined-fetch` (one locked-down `claude -p` session allowed one MCP tool, its structured result on stdout; bash 3.2 and jq 1.6). Built in its own repo under this repo's process. Then a small plan here vendors both skills into `.claude/skills/` at a pinned tag with a checksum test, as for `humanizer`; the Foundry's own meeting code stays as it is | In progress: spec rev 2 after an independent review and a re-review (approve with changes); rev 3, the owner's review and the plan next |
````

Replace with:

````text
| **12. minutes plugin** | Separate public repo `kferran/minutes`, spec `docs/superpowers/specs/2026-10-06-minutes-design.md` there | The parts of Plan 11 not tied to the vault, as a Claude Code plugin with two skills: `meeting-notes` (Gemini Docs and `.vtt`/`.srt`/`.txt`/`.md` transcripts to a meeting note and a transcript note, with the safety cleaning; Python 3.9 standard library) and `confined-fetch` (one locked-down `claude -p` session allowed one MCP tool, its structured result on stdout; bash 3.2 and jq 1.6). Built in its own repo under this repo's process. Then a small plan here vendors both skills into `.claude/skills/` at a pinned tag with a checksum test, as for `humanizer`; the Foundry's own meeting code stays as it is | In progress in its own session in the `minutes` repository: spec rev 2 after an independent review and a re-review (approve with changes); rev 3, the owner's review and the plan next |
| **The Nightshift** | `2026-10-06-nightshift-design.md` | Unattended runs of refined work: an approved plan (or a task range of one) ends in a pull request, a written research brief ends in a findings note. A deterministic runner on a 15-minute timer owns the queue, windows, budgets, verification, push and the morning report; each item runs in a fresh, confined `claude -p` session with no credential | Complete (2026-10-07): `2026-10-06-nightshift.md`; PRs #49, #50, #52 |
| **DTCC change watcher, phase 1** | `2026-10-06-dtcc-change-watcher-design.md` | A daily, model-free fetch of DTCC I&RS pages, notices and the API catalog; one `dtcc_change` note per change, tied to the codebase paths it touches; a carried-forward checkbox block in the brief. Phase 2 (a model impact assessment) is later | Complete (2026-10-07): `2026-10-06-dtcc-change-watcher.md`; PR #51 |
| **Briefing notes and archive** | No spec or plan (shipped from an in-chat design) | A 📝 Notes section the brief never edits; each brief moves earlier days to `briefings/archive/<YYYY-MM>/` | Complete (2026-10-07): PR #53; minors #54–#57 |
| **Active Projects in the brief** | `2026-10-07-active-projects-design.md` | Optional `wiki/<partition>/ActiveProjects.md` lists; the brief shows each active project's next open actions and the decisions waiting, read by a script from the project page | Complete (2026-10-07): `2026-10-07-active-projects.md`; PR #66, issue #65 |
| **Fixes from live use** | Issues the live vault logs on this repository | Small fixes found by running the real vault. Merged: #32, #34, #36, #45, #50, #58, #60. In review: the Nightshift pull requests opened 2026-10-08 (template issue fixes, telemetry identifiers). Next: fewer prompts (seven read-only allow rules in `.claude/settings.json` and the `CLAUDE.md` Bash line, byte for byte as in the vault); the Nightshift source fix (a `template` item resolves to the development clone or the remote, not the vault); the `/ingest` preference gap (design spec §6.21: digest Corrections never become `preference` notes) | Ongoing |
| **RCA-to-Jira, phase 1** | Own brainstorm → spec → plan | An attended `/rca` procedure with three entries (an error-group note, an existing Jira key, a described symptom), a `jira_draft` note the user approves, and a filer that is the only Jira writer. Vault-specific values (project, assignee) are settings. Phase 2 runs investigations unattended inside Sub-project 2 | Next: design sections with the user |
| **Require-plan** | `2026-10-07-require-plan-design.md` (rev 5) | A required pull-request check that a change carries a `writing-plans` plan, plus a Nightshift `Plan:` line | Parked by the user (2026-10-07); spec rev 5 and a proven plan on branch `feat/require-plan` |
| **Reorganization** | Issue #62 | Move what Obsidian opens (`wiki/`, `raw/`, `briefings/`) under `vault/`, group each feature's files into a feature folder, shared code into `core/`; any Nightshift rename uses Sub-project 2's vocabulary | After the Sub-project 2 brainstorm |

**Next, in order** (user, 2026-10-07): fewer prompts; the Nightshift source fix; RCA-to-Jira phase 1; `/ingest` preference notes; the Sub-project 2 brainstorm; then the reorganization (#62). Plans 5 and 7 wait for a few weeks of real use. Plan 12 runs in its own session.

Plans are numbered in the order they were defined, not the order they run. Each plan is written only after the previous one is finished, because results carry forward. For example, the spike can change the permission model (spec §7), and that affects Plans 2–4.
````


- [ ] **Step 2: Name the Nightshift pull requests if they exist**

Run: `gh pr list --repo kferran/Foundry --state all --search 'head:nightshift/ created:>=2026-10-08' --json number,title,state`
If it lists pull requests, replace `the Nightshift pull requests opened 2026-10-08 (template issue fixes, telemetry identifiers)` in the roadmap's "Fixes from live use" row with their numbers and titles (for example `#67 template issue fixes, #68 telemetry identifiers`), and move any whose `state` is `MERGED` into that row's "Merged:" list. If it lists none, leave the text as it is.

- [ ] **Step 3: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 4: Commit**

Write `.scratch/msg-2.txt`:

```text
docs(roadmap): the work since Plan 11 and the agreed order

Rows for the Nightshift, the DTCC watcher, the briefing archive, Active
Projects, the fixes from live use, RCA-to-Jira, require-plan (parked)
and the reorganization (#62); Sub-project 2 absorbs the Nightshift; a
"Next, in order" list; the plan-numbering note moves here from the
README.
```

Run: `git commit -q -F .scratch/msg-2.txt -- docs/superpowers/roadmap.md`

---

### Task 3: README status summary and the newer features

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the README-link test from Task 1 (every link the new text adds must resolve).

- [ ] **Step 1: Edit the README**

Edit 1 in `README.md`. Find:

````text
> **Status:** built and tested on one machine. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)) and passed again with the humanizer self-edit step ([record](docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md)). Memory capture and recall passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md)) and stay off until you install their hooks, which `/setup` offers. A full `/setup` on a Debian server (units, sync, memory hooks, calendar, one codebase) ran end to end on 2026-10-05. Style lint, preferences, the Foreman orchestrator and the migration are still to come (see [Status](#status)).
````

Replace with:

````text
> **Status:** in daily use since 2026-10-05 on one Debian server and a laptop client. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)), as did memory capture and recall ([record](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md)), two-machine sync ([record](docs/superpowers/spikes/2026-10-04-plan-8c-acceptance.md)) and meetings ([record](docs/superpowers/spikes/2026-10-06-plan-11-acceptance.md)). Preferences, style lint and the Foreman orchestrator are still to come (see [Status](#status)).
````

Edit 2 in `README.md`. Find:

````text
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
| 11a. Error monitoring | Hourly, model-free fetch of Sentry issues and ADX error groups into aggregate-only `production_error` notes; `/setup` phase 6a | Complete: [plan](docs/superpowers/plans/2026-10-05-plan-11-error-monitoring.md), [spec](docs/superpowers/specs/2026-10-05-error-monitoring-design.md), [spike](docs/superpowers/spikes/2026-10-05-plan-11-trace-coverage.md), [outcomes](docs/superpowers/plans/2026-10-05-plan-11-outcomes.md) |
| 11b. Meetings | Gemini notes fetched from Google Drive and dropped transcripts become meeting notes, tracked actions and searchable transcripts | Complete: [plan](docs/superpowers/plans/2026-10-05-plan-11-meetings.md), [spec](docs/superpowers/specs/2026-10-05-meetings-design.md), [acceptance](docs/superpowers/spikes/2026-10-06-plan-11-acceptance.md), [outcomes](docs/superpowers/plans/2026-10-06-plan-11-outcomes.md) |
| 12. minutes plugin | Meeting notes and the confined connector fetch as a public Claude Code plugin (its own repo), then vendored here like humanizer | In progress: spec revised after two reviews; plan next |
| 7. Style lint | Warning-only `style-*` checks for wiki and briefing notes | After the real vault has run a few weeks |
| 5. Preferences | Preference status derivation, acceptance in `/brief`, recall slot | After the real vault has run a few weeks |
| Sub-project 2 | the Foreman orchestrator | Separate spec, after Plans 7 and 5 |
| 10. Migrate Cerebro and Wong | Import both older systems, then decommission them (Sub-project 3) | Complete (2026-10-06): content migrated outside this repo's plans |

- Design spec: [docs/superpowers/specs/2026-09-30-vault-template-design.md](docs/superpowers/specs/2026-09-30-vault-template-design.md)
- Roadmap: [docs/superpowers/roadmap.md](docs/superpowers/roadmap.md)

Plans are numbered in the order they were defined, not the order they run; the table is in run order. Each plan is written only after the previous one is finished, because results carry forward. For example, the spike can change the permission model (spec §7), and that affects Plans 2–4.
````

Replace with:

````text
**Works today:**
- Headless intake, morning brief and evening debrief, published through a deterministic gate
- Memory: session digest capture and bounded recall (optional hooks)
- Two machines: a server runs the automation and syncs through a private `origin`; clients read and edit in Obsidian
- Calendar input to the brief from the Google Calendar connector
- Error telemetry from Sentry and Azure Data Explorer
- Meetings: Gemini notes and dropped transcripts become meeting notes, tracked actions and searchable transcripts
- The Nightshift: queued plans and research briefs run unattended overnight
- DTCC change watcher (phase 1)
- Active Projects in the brief, and an archive of past briefings

**Next:** fewer permission prompts, a Nightshift fix, RCA-to-Jira (phase 1), preference notes from `/ingest`, then the Foreman orchestrator (Sub-project 2). Preferences (Plan 5) and style lint (Plan 7) wait for a few weeks of real use.

- Roadmap, with every plan, its records and its status: [docs/superpowers/roadmap.md](docs/superpowers/roadmap.md)
- Design spec: [docs/superpowers/specs/2026-09-30-vault-template-design.md](docs/superpowers/specs/2026-09-30-vault-template-design.md)
````

Edit 3 in `README.md`. Find:

````text
| `/brief [date]` | The Foreman writes `briefings/<date>.md`: calendar commitments, 3–5 objectives tied to your superpowers and handed to a capability, and a friction matrix. A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Earlier days' briefings and debriefs move to `briefings/archive/<YYYY-MM>/` |
````

Replace with:

````text
| `/brief [date]` | The Foreman writes `briefings/<date>.md`: calendar commitments, 3–5 objectives tied to your superpowers and handed to a capability, 🎯 Active Projects, a DTCC changes block when the watcher is set up, and a friction matrix. A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Earlier days' briefings and debriefs move to `briefings/archive/<YYYY-MM>/` |
````

Edit 4 in `README.md`. Find:

````text
| `/backup` | Runs the gating suites (lint only on a client), commits each headless run on its own, then commits and pushes the rest according to `remote_mode` (through `vault_sync.sh` in `private`) |
````

Replace with:

````text
| `/backup` | Runs the gating suites (lint only on a client), commits each headless run on its own, then commits and pushes the rest according to `remote_mode` (through `vault_sync.sh` in `private`) |
| `/nightshift add\|ask\|list\|cancel\|status` | Queues an approved plan (or a task range of one) or a research brief for an unattended run; lists, cancels and reports on queued items |
| `/dtcc-watch [check\|status\|accept]` | Runs the DTCC change watcher by hand, checks its map, reports recent changes, or accepts held changes as the new baseline |
````

Edit 5 in `README.md`. Find:

````text
**Error telemetry.** `foundry-telemetry.timer` runs `telemetry_fetch.py` every hour, and `brief_prep.sh` runs it once more before the brief. Each source in `system/telemetry/<name>.md` (written by `/setup` phase 6a, gitignored) is a set of Sentry projects or one Azure Data Explorer database with a filter. Each error group becomes one `production_error` note in `raw/telemetry/` holding only group keys, counts, times, opaque IDs and links: no message text, titles or attribute values. Sentry needs a read-only token in `~/.config/foundry/sentry.token` (mode 0600); ADX uses your `az login`. `--check <name>` tests a source, `--dry-run` prints the groups without writing.
````

Replace with:

````text
**Error telemetry.** `foundry-telemetry.timer` runs `telemetry_fetch.py` every hour, and `brief_prep.sh` runs it once more before the brief. Each source in `system/telemetry/<name>.md` (written by `/setup` phase 6a, gitignored) is a set of Sentry projects or one Azure Data Explorer database with a filter. Each error group becomes one `production_error` note in `raw/telemetry/` holding only group keys, counts, times, opaque IDs and links: no message text, titles or attribute values. Sentry needs a read-only token in `~/.config/foundry/sentry.token` (mode 0600); ADX uses your `az login`. `--check <name>` tests a source, `--dry-run` prints the groups without writing.

**The Nightshift.** `/nightshift` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time: in the nightly window (`nightshift_window`, default `22:00-05:00`, waiting while you are active), at a set time, or now. A plan item runs in a private clone under `nightshift_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that holds no credential. The morning report, `system/logs/nightshift/<date>.md`, starts with a health banner, then "Needs you" (decisions only), which the brief carries forward. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server.

**DTCC change watcher.** It is for a codebase that integrates with DTCC Insurance & Retirement Services. `foundry-dtcc-watch.timer` runs `dtcc_watch.py` daily, 30 minutes before the brief. No model runs. It reads DTCC's public product pages, release dates, Important Notices and API catalog, and writes one `dtcc_change` note per change to `wiki/<partition>/changes/` with the codebase paths it touches. The brief lists each change as a checkbox that carries forward until you tick it. The watcher does nothing until your vault has `system/dtcc/map.yaml` (start from `system/dtcc/map.example.yaml`).

**Active Projects.** An optional `wiki/<partition>/ActiveProjects.md` lists your project pages in priority order under `## Active`. Each morning, `active_projects.py` reads those pages, and the brief shows each project's next 3 open checkboxes and the open items under its "Decisions…" heading, as plain bullets. You tick items on the project page, so nothing is tracked twice.
````

Edit 6 in `README.md`. Find:

````text
.claude/skills/humanizer/     vendored humanizer v3.0.0 (MIT): /humanizer, headless self-edit
````

Replace with:

````text
.claude/skills/humanizer/     vendored humanizer v3.0.0 (MIT): /humanizer, headless self-edit
.claude/skills/nightshift/    /nightshift: queue plans and research briefs for unattended runs
.claude/skills/dtcc-watch/    /dtcc-watch: the DTCC change watcher by hand
````

Edit 7 in `README.md`. Find:

````text
  telemetry/example.md        example error source (real sources are gitignored)
````

Replace with:

````text
  telemetry/example.md        example error source (real sources are gitignored)
  dtcc/map.example.yaml       example DTCC watch map (your map.yaml is tracked in your vault)
  nightshift/                 session profiles for Nightshift plan and research runs
````

Edit 8 in `README.md`. Find:

````text
                              vault_sync.sh, commit_runs.py, calendar_fetch.sh, meetings_fetch.sh, telemetry_fetch.py, ...
  systemd/                    foundry-{intake,brief,debrief,focus,sync,telemetry,meetings} unit templates (*.in)
````

Replace with:

````text
                              vault_sync.sh, commit_runs.py, calendar_fetch.sh, meetings_fetch.sh, telemetry_fetch.py,
                              nightshift.py, dtcc_watch.py, active_projects.py, ...
  systemd/                    foundry-{intake,brief,debrief,focus,sync,telemetry,meetings,nightshift,dtcc-watch} unit templates (*.in)
````

Edit 9 in `README.md`. Find:

````text
- Optional: the Azure CLI (`az`, logged in) for ADX error sources, and a read-only Sentry token for Sentry sources. Without them those sources stay off.
````

Replace with:

````text
- Optional: the Azure CLI (`az`, logged in) for ADX error sources, and a read-only Sentry token for Sentry sources. Without them those sources stay off.
- Optional: `pdftotext` (`poppler` on Arch, `poppler-utils` on Debian) for the DTCC change watcher, which reads the header of each notice's PDF.
````


- [ ] **Step 2: Run the suite**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/vault_integrity.bats`
Expected: PASS, `1..19`; the README-link test passes with the four acceptance-record links the banner now names.

- [ ] **Step 3: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 4: Commit**

Write `.scratch/msg-3.txt`:

```text
docs(readme): status summary and the newer features

The status table becomes a short "works today / next" summary that
links to the roadmap. Daily use, the feature notes, the repository
layout and Requirements cover the Nightshift, the DTCC watcher and
Active Projects. The banner says the vault runs on a server and a
client.
```

Run: `git commit -q -F .scratch/msg-3.txt -- README.md`
