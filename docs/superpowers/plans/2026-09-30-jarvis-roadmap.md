# Jarvis Vault Template: Implementation Roadmap

**Spec:** `docs/superpowers/specs/2026-09-30-vault-template-design.md` (branch `feat/vault-template`)

The spec covers several subsystems that depend on each other in a strict order (§4). Each phase below gets its own plan and produces working, tested software on its own. A phase's detailed plan is written only after the previous phase is complete, because results feed forward: the Plan 0 spike can change §7 and therefore everything in Plans 2–4.

| Plan | Scope (spec sections) | Deliverable | Status |
|---|---|---|---|
| **0. Spike gate** | §7.4 items 1–18 | `docs/superpowers/spikes/2026-09-30-headless-and-hooks.md` with a pass/fail record per item and any required spec edits applied | Complete (2026-09-30) |
| **1. Foundation** | §4 steps 1–2, §6.1 (Python side), §6.8, §6.9, §6.15, §6.16 (excluding `stage`, `recall`), §10, §12 (pytest + lint/hook bats) | Baseline commit; `vaultlib` (YAML loader, frontmatter, schemas, links, index, query guard, caller scope, CLI); schema notes; templates with drift guard; `lint_vault.sh`; `.githooks/pre-commit`; `wiki/Index.md`; new `.gitignore`; `vault_integrity.bats` | Complete (2026-09-30) |
| **2a. Headless core** | §6 (shell, args), §6.1, §6.3, §6.4, §6.18, §6.20, §7.1, §7.2, §7.4 final-form gate | `lib_args.sh`/`lib_config.sh`; settings files; `redact.py`; `publish_staged.py` + `stage` (journal, recovery, fault-injection tests); `run_headless.sh` (ledger, cap, final flags); intake daemon (manifest, retries, digest batching) | Complete (2026-10-01): `2026-10-01-plan-2a-headless-core.md` |
| **2b. Operations** | §6.2, §6.5–§6.7, §6.10–§6.14, §7.3 | `check_deps.sh`; prep scripts; `focus_stats.sh`; `track_obsidian.sh`; unit templates + `install_units.sh`; `setup_remote.sh`; `update_template.sh`; discovery/inspection; `verify_setup.sh` | Complete (2026-10-02): `2026-10-01-plan-2b-operations.md` |
| **4a. Commands and setup** | §8, §9 (except `/digest`), §11 (except step 5a), `system_health.bats`, README core | Rewritten `CLAUDE.md`, `ingest`/`brief`/`debrief`/`query`/`lint`/`backup`/`impact`/`setup` commands, personas, `config.example.md`, `codebases/example.md`, `/setup` flow without memory hooks, live headless acceptance runs; lifts the unit gate | Complete (2026-10-02): `2026-10-02-plan-4a-commands-setup.md`; acceptance `docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md` |
| **3. Memory (Soundwave)** | §6.17, §6.18, §6.19, §7.3a, `recall` subcommand | Hooks (`lib_memory.sh`, recall, capture, activity) reusing Plan 2a's `redact.py`, `install_hooks.sh`, user-level `/digest` | Complete (2026-10-02): `2026-10-02-plan-3-memory.md`; acceptance `docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md` |
| **4b. Memory integration, renames** | §11 step 5a, §15, `/digest` wiring, README memory sections | `/setup` memory-hooks step, README memory and recall sections, final §15 renames commit | After Plan 3 |
| **5. Preferences phase** | §6.21 derivation, `/brief` acceptance, recall slot | `v_preference.status`, acceptance flow, quoted recall rendering, `preferences_enabled` switch | After the core has run for a few weeks |
| **6. Communication** | `2026-10-02-communication-design.md` §3–§4 | `CLAUDE.md` Writing section (reply tiers, condensed humanizer wording rules); vendored humanizer skill (`.claude/skills/humanizer/`, MIT); headless `ingest`/`brief`/`debrief` self-edit pass; acceptance re-run | After Plan 3 |
| **7. Style lint** | `2026-10-02-communication-design.md` §5 | Warning-only `style-*` issue codes in `vault_index.py issues` for wiki and briefing notes, thresholds tuned on real notes | After Plan 6 has run a few weeks |
| **Sub-project 2** | §16 | Separate brainstorm → spec → plan (Optimus orchestrator) | After Plan 4b |

**Gate lifted** by Plan 4a's live acceptance (`docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md`): the commands follow the headless staging contract, so units may be installed with `/setup`. Re-run the acceptance steps after any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands.

**Gating suites** (green at the end of every task): `system/scripts/verify_setup.sh`, which runs every `system/tests/*.bats` except `system_health.bats`, then `python3 -m pytest system/tests/python -q`, and exits non-zero if any fails. Read its verdict from the exit code, never through a pipe.
