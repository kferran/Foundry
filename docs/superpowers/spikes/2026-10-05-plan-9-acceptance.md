# Plan 9 acceptance

**Date:** 2026-10-05 · **Branch:** `feat/plan-9` · **Commit:** 5b2d6db (Tasks 1–3) · **Debian host:** Debian 12.15 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2, Claude Code 2.1.289. Executed natively on the Debian host. The host name is kept out of this record (template rule).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Debian host | 9c42524 (Task 1) | 0 | 16/16 PASS | lint 0 errors |
| Debian host | d6e7182 (Task 2) | 0 | 16/16 PASS | lint 0 errors |
| Debian host | 5b2d6db (Task 3) | 0 | 16/16 PASS | lint 0 errors, 4 warnings (older than this plan) |

## Live run (spec §7)

A throwaway clone under `~/.cache/jarvis-accept/`, removed afterwards: `system/config.md` from the example (`machine_role: standalone`), `core.hooksPath .githooks`, `commit_runs.py --init-cutover` (exit 0). `claude` on `PATH`. No units were installed and no prep script ran.

| Step | Result |
|---|---|
| `install_units.sh --dry-run`, standalone | exit 0; `foundry-brief`, `foundry-debrief`, `foundry-focus`, `foundry-intake` services and the brief, debrief and intake timers; 7 `Description=The Foundry: …` lines |
| `install_units.sh --dry-run`, server | exit 0; the intake, brief and debrief units, `foundry-sync.service` and `.timer`, and the three `foundry-sync.conf` drop-ins; 8 `Description=` lines; no old name in any header or description; nothing written to the unit directory |
| Ingest of an inbox note that assigns work (`intake_daemon.sh`) | exit 0; published `wiki/personal/concepts/NightlyExportRetry.md` with `capability: code`; no note has `agent_owner` |
| `run_headless.sh brief`, then `debrief` | both exit 0; published `briefings/2026-10-05.md` and `briefings/2026-10-05.debrief.md`; lint 0 errors |
| `commit_runs.py` | exit 0; three commits, ingest first, each with `Foundry-Command`, `Foundry-Run` and `Foundry-Role: standalone`; no `Jarvis-` trailer; no `[wheeljack]` or `[soundwave]` alert tag |

```
ingest(personal): create NightlyExportRetry

create wiki/personal/concepts/NightlyExportRetry.md <- raw/inbox/.staging/export retry.md

Foundry-Command: ingest
Foundry-Run: 20261005T095450-ingest-3f6a
Foundry-Role: standalone
```

## Cost

Three live runs: $0.18, $0.23 and $0.23 (the session logs were read by file, not matched to runs), **$0.63** in total.

## Verdict

**PASS.** Units render only under `foundry-*`, a headless ingest assigns work by `capability` from the concept schema, and every run commits with `Foundry-*` trailers. The gate passes 16/16 on the tool floor.
