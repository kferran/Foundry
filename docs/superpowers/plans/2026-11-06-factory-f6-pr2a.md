# Factory F6, PR 2a: extension nodes, the diagram and /new-source (#477) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every extension unit a node, let an extension's steps that run inside core units join those nodes, draw the graph in FOUNDRY.md from the manifests, and have `/new-source` write the pipeline entry (spec G3, G4, G5).

**Architecture:**
- `extensions/<name>/pipeline.yml`: data only. `nodes:` holds the extension's own units, in the core node shape. `extends: {<core node>: {scripts, reads, writes, locks}}` adds the extension's steps to a core node.
- `system/tests/pipeline_graph.py`:
  - `--extensions` loads every `extensions/*/pipeline.yml` in the tree and every `extensions/*/units/foundry-*.service.in` as a unit. Without it, the run is core alone, as today.
  - `--mermaid` prints the diagram instead of problems.
- `system/tests/pipeline.bats`: the repository check runs twice, core alone and with `--extensions`. The diagram check compares FOUNDRY.md's block with `--mermaid --extensions`.

No script, unit or hook changes.

**Tech Stack:** Python 3 stdlib, PyYAML, bats.

**Spec:** `docs/superpowers/specs/2026-11-04-factory-f6-pr2-design.md` (G3, G4, G5, G6). P9, P10 and G7 are PR 2b.

## Builder check (2026-11-06, master `1861636`)

- **Extension units:**
  - `foundry-console` runs `serve.sh` with `Restart=on-failure` and has no crash handler and no alert tag.
  - `foundry-watch` runs `watch_fetch.sh`, which calls `crash_trap foundry-watch`.
  - `foundry-telemetry` runs `telemetry_fetch.py`, which calls `guard(..., "telemetry")`.
- **Steps inside core units:**
  - Brief prep: `jira_fetch.sh` (handoffs), `health.py` (health) and `brief_fetch.sh` (telemetry).
  - Intake tick: `today_log.py tick` (intraday) and `rca.py tick` (telemetry).
- **G4 runs both modes in both jobs.** The decision said core alone in `gate` and core plus extensions in `gate-all-extensions`. The extension files are in the tree in both jobs, so the bats file runs both modes everywhere. Core alone still proves that core stands without its extensions.
- **Core manifest fix:** intake writes and reads `system/logs/meetings-*.jsonl` (`vaultlib/intake.py:655,663`), which `today_log.py` also reads. PR 1's intake node left it out.
- **Not a graph path:** `system/index.db` (the console reads it) is a cache that any reader rebuilds (`vaultlib/index.py`), so no node writes it.
- **New edge kind `restart`.** The console's catch-all is systemd restarting it. `restart` is valid only when the unit file has `Restart=on-failure` or `Restart=always` (P5, next to the timer check). Without it, the console would need `none` and a gap line for a behaviour the unit does have.

## Global Constraints

- No runtime change: nothing under `system/scripts`, `system/hooks`, `system/systemd`, `extensions/*/scripts`, `extensions/*/units` or `.claude/commands` is edited. Core cap and schema count unchanged.
- The checker reads files only.
- Problem lines keep the `<subject>: <problem>` form. New lines:
  - `<ext>: extends no node <name>` (P1).
  - `<node>: restart on a unit with no Restart=` (P5).
- **Bats ruling R1:** no mid-test `!`, no `&&` assertion chains, and no wall-clock assertions.
- **Template rule:** no hostname, user path, employer or people name in the manifests or the fixtures.
- **Change file:** one line: `/new-source` writes a new file, which a vault user sees. FOUNDRY.md's factory line names the extension file and the diagram.
- **Delivery:** branch `feat/f6-pr2a`; the owner merges.

## Review Focus

1. Every extension node and `extends` entry matches the code: the unit file, the entry script's handler, the locks its scripts name, and what it reads and writes.
2. A `restart` edge is backed by the unit file, never by the declaration alone.
3. The diagram is generated, never hand-edited. The test fails when it differs.

## Task 1: load extension files (`--extensions`)

**Files:** `system/tests/pipeline_graph.py`, `system/tests/pipeline.bats`.

- [ ] Parse argv: `<root> [gaps-file] [--extensions] [--mermaid]`.
- [ ] With `--extensions`:
  - Add units from `extensions/*/units/foundry-*.service.in`, remembering each unit's directory for P5.
  - Merge each extension's `nodes` (a name already used is a P1 problem) and apply `extends` (scripts, reads, writes and locks appended; an unknown node is `<ext>: extends no node <name>`).
- [ ] Fixture tests: an extension unit with no node fails P1, and an `extends` naming no node fails P1.

## Task 2: the `restart` edge

- [ ] Add `restart` to `EDGE_RE`. P5: `restart` needs `Restart=on-failure` or `Restart=always` in the unit file.
- [ ] Fixture test: a unit without `Restart=` fails P5 with the exact line.

## Task 3: the extension manifests

- [ ] Write `extensions/console/pipeline.yml`, `intraday/pipeline.yml`, `telemetry/pipeline.yml`, `handoffs/pipeline.yml` and `health/pipeline.yml` from a fresh read of each script (reads, writes, locks and failure exits).
- [ ] `pipeline.bats`: the repository test runs core alone and with `--extensions`, both against `PIPELINE_GAPS`. Any real gap gets a line naming an issue.

## Task 4: the diagram (`--mermaid`)

- [ ] `--mermaid` prints `flowchart LR`:
  - Each node is a box.
  - Each declared path is a folder shape: an arrow from each writer and an arrow to each reader.
  - An `outside` node points to each source and receives each sink.
  - The output is sorted so it is stable.
- [ ] FOUNDRY.md "The factory line" holds the block between `<!-- pipeline:begin -->` and `<!-- pipeline:end -->`. The bats test compares it with `--mermaid --extensions`, and on a difference prints the command that regenerates it.

## Task 5: `/new-source` and docs

- [ ] `.claude/skills/new-source/SKILL.md`: the Source writes `extensions/<name>/pipeline.yml` with `extends: {brief: …}` for its fetch script, and its checks include `bats system/tests/pipeline.bats`.
- [ ] FOUNDRY.md factory line: one sentence on extension files, `restart` and the diagram.
- [ ] Run `pipeline.bats`, `conformance.bats`, `vault_integrity.bats` and the new-source tests, then `review_diff.py`, then open the PR.
