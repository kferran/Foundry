# Jarvis Vault Template: Implementation Roadmap

**Spec:** `docs/superpowers/specs/2026-09-30-vault-template-design.md` (branch `feat/vault-template`)

The spec covers several subsystems that depend on each other in a strict order (§4). Each phase below gets its own plan and produces working, tested software on its own. A phase's detailed plan is written only after the previous phase is complete, because results feed forward: the Plan 0 spike can change §7 and therefore everything in Plans 2–4.

| Plan | Scope (spec sections) | Deliverable | Status |
|---|---|---|---|
| **0. Spike gate** | §7.4 items 1–18 | `docs/superpowers/spikes/2026-09-30-headless-and-hooks.md` with a pass/fail record per item and any required spec edits applied | Complete (2026-09-30) |
| **1. Foundation** | §4 steps 1–2, §6.1 (Python side), §6.8, §6.9, §6.15, §6.16 (excluding `stage`, `recall`), §10, §12 (pytest + lint/hook bats) | Baseline commit; `vaultlib` (YAML loader, frontmatter, schemas, links, index, query guard, caller scope, CLI); schema notes; templates with drift guard; `lint_vault.sh`; `.githooks/pre-commit`; `wiki/Index.md`; new `.gitignore`; `vault_integrity.bats` | Written: `2026-09-30-plan-1-foundation.md` |
| **2. Headless pipeline** | §6.2–§6.7, §6.10–§6.14, §6.18 (intake use), §6.20, §7.1–§7.3 | `publish_staged.py` + `stage` (journal, recovery, fault-injection tests); `run_headless.sh` (ledger, cap, flags from Plan 0); `intake_daemon.sh`; prep scripts; `focus_stats.sh`; `track_obsidian.sh`; unit templates + `install_units.sh`; `setup_remote.sh`; `update_template.sh`; discovery/inspection; `check_deps.sh`; `lib_config.sh`/`lib_args.sh`; settings files; `verify_setup.sh` | After Plan 1 |
| **3. Memory (Soundwave)** | §6.17, §6.18, §6.19, §7.3a, `recall` subcommand | Hooks (`lib_memory.sh`, recall, capture, activity), `redact.py`, `install_hooks.sh`, user-level `/digest` | After Plan 2 |
| **4. Prompts, setup, docs** | §8, §9, §11, §15, `system_health.bats`, README | Rewritten `CLAUDE.md`, commands, personas, `config.example.md`, `codebases/example.md`, `/setup` flow, README, final §15 renames commit | After Plan 3 |
| **5. Preferences phase** | §6.21 derivation, `/brief` acceptance, recall slot | `v_preference.status`, acceptance flow, quoted recall rendering, `preferences_enabled` switch | After the core has run for a few weeks |
| **Sub-project 2** | §16 | Separate brainstorm → spec → plan (Optimus orchestrator) | After Plan 4 |

**Gating suites** (green at the end of every task once they exist): `python3 -m pytest system/tests/python -q`, `bats system/tests/vault_integrity.bats system/tests/scripts.bats`.
