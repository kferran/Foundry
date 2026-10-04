# Plan 8c acceptance

**Date:** 2026-10-04 · **Branch:** `feat/plan-8c` · **Commit:** bd2ea00 (Tasks 1–6 plus the final-review fixes) · **Debian host:** Debian 12.15 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2, git 2.39.5, bash 5.2.15, Claude Code 2.1.289. Executed subagent-driven on the Debian host. The host name is kept out of this record (template rule).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Debian host | 6665dec (plan only) | 0 | 15/15 PASS | baseline |
| Debian host | 1372f82 (Task 6) | 0 | 16/16 PASS | `sync.bats` added; lint 0 errors |
| Debian host | bd2ea00 (final-review fixes) | 0 | 16/16 PASS | lint 0 errors, 4 warnings (README directory links and the example codebase path, both older than this plan) |

## Live run (spec §8.1, 8c)

Throwaway clones under `~/.cache/jarvis-accept/`, removed afterwards: a local bare repo as `origin`, a server clone of `feat/plan-8c` (`machine_role: server`, `remote_mode: private`, `core.hooksPath .githooks`, the template remote renamed to `template`, `commit_runs.py --init-cutover`), and a client clone (`machine_role: client`). No units were installed: each step calls the scripts a unit would run, with `claude` on `PATH`.

The bare repo's `HEAD` pointed at `master`, which it did not have, so the first client clone checked out nothing. The run set `HEAD` to the plan branch (`git symbolic-ref`) and checked it out. A real private origin created by `/setup` phase 4 publishes the vault's own branch, so this only affects the acceptance setup.

| Step | Commands and exits | Result |
|---|---|---|
| 1. Server brief | `vault_sync.sh --pre` 0, `brief_prep.sh` 0, `run_headless.sh brief` 0, `vault_sync.sh --post` 0 | origin's log holds the `brief 2026-10-04` commit |
| 2. Client block reaches the server | client pull, block appended to today's briefing, commit (hook: 0 errors) and push 0; server `vault_sync.sh` 0, `INTAKE_NOW_OFFSET=120 intake.py` 0, `vault_sync.sh` 0 | `ingest(personal): create NightlyExport` committed and pushed; the server's briefing is byte-identical before and after intake (`cmp`); the client pulls the note |
| 3. Forced conflict | both clones change the block's line; client pushes first; server `vault_sync.sh` 3, `--pre` 3 | `refs/heads/jarvis/server-pending` on origin; `sync-blocked` names `briefings/2026-10-04.md` and `pending branch: jarvis/server-pending`; one `sync blocked` alert |
| 3. Resolution from the client | `git fetch`, `git merge origin/jarvis/server-pending` (conflict, exit 1), resolved, commit and push 0; server `vault_sync.sh` 0 | marker gone, no `jarvis/*` branch on origin, one `sync unblocked` alert, the resolved line on the server. No brief or debrief was started: the brief had run today and 17:00 had not passed |
| 4. Network failure | `chmod 000` on the bare repo, then step 1's sequence: `--pre` 0, prep 0, brief 0, `--post` 0 | the briefing published and committed locally; exactly one `sync failed (fetch)` alert across both sync calls |
| 4. Recovery | `chmod 755`, `vault_sync.sh` 0 | one `sync recovered (was failing: fetch)` alert; `sync-state.json` removed; origin has the second brief commit |

The commits, each through the pre-commit hook:

```
brief 2026-10-04: briefings/2026-10-04.md

published briefings/2026-10-04.md

Jarvis-Command: brief
Jarvis-Run: 20261004T151259-brief-208d
Jarvis-Role: server
```

```
ingest(personal): create NightlyExport

create wiki/personal/concepts/NightlyExport.md <- raw/inbox/.staging/daily_note_drop_1791148475.md

Jarvis-Command: ingest
Jarvis-Run: 20261004T151435-ingest-e996
Jarvis-Role: server
```

The `[sync]` alerts, in order: `sync blocked: merge conflict with origin/<branch>; resolve it by merging origin/jarvis/server-pending (README: Sync conflicts); intake, brief and debrief are skipped until it is resolved`, `sync unblocked`, `sync failed (fetch): git fetch origin failed`, `sync recovered (was failing: fetch)`.

## Cost

| Run | Cost | Notes |
|---|---|---|
| calendar fetch (step 1) | $0.10 | exit 0, 0 events, 4 turns, 0 denials, no unexpected tools |
| brief (step 1) | $0.26 | exit 0, 0 denials |
| ingest (step 2) | $0.20 or $0.22 | exit 0, 0 denials |
| calendar fetch (step 4) | $0.06 | exit 0, 0 events |
| brief (step 4) | $0.22 or $0.20 | exit 0, 0 denials; the two session logs were read by file, not by run, before the clones were removed, so which of the two costs belongs to which run is not recorded |
| **Total** | **$0.84** | |

## Verdict

**PASS.** A server syncs around every run and on demand, a client's briefing block reaches the server and is compiled without the briefing being rewritten, a conflict blocks the runs behind `jarvis/server-pending` until it is resolved from the client, and a broken origin never stops a run and alerts once. The gate passes 16/16 on the tool floor.
