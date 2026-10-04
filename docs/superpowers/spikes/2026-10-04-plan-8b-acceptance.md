# Plan 8b acceptance

**Date:** 2026-10-04 · **Branch:** `feat/plan-8b` · **Commit:** 0d0c890 (Tasks 1–3 plus the final-review fixes) · **Debian host:** Debian 12.15 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2, Claude Code 2.1.289. Work ran natively on the Debian host. The host name is kept out of this record (template rule).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Debian host | e4b9ea1 (Task 3) | 0 | 15/15 PASS | lint 0 errors |
| Debian host | 0d0c890 (final-review fixes) | 0 | 15/15 PASS | lint 0 errors |

## Live run (spec §8.1, 8b)

A throwaway clone under `~/.cache/jarvis-accept/`, removed afterwards. `system/config.md` from the example (`machine_role: standalone`), `core.hooksPath` set to `.githooks`, and `commit_runs.py --init-cutover` run before any headless run.

| Run | Exit | Published | Cost | Turns | Denials |
|---|---|---|---|---|---|
| headless ingest of one work digest | 0 | `wiki/work/concepts/NightlyExportJob.md` | $0.19 | 7 | 0 |
| headless brief (calendar fetch: exit 0, 0 events, $0.10) | 0 | `briefings/2026-10-04.md` | $0.23 | 20 | 0 |

`commit_runs.py` then exited 0 and printed two lines, ingest first. The commits, each through the pre-commit hook:

```
ingest(work): create NightlyExportJob

create wiki/work/concepts/NightlyExportJob.md <- raw/work/notes/accept-8b.md

Jarvis-Command: ingest
Jarvis-Run: 20261004T085910-ingest-4084
Jarvis-Role: standalone
```

```
brief 2026-10-04: briefings/2026-10-04.md

published briefings/2026-10-04.md

Jarvis-Command: brief
Jarvis-Run: 20261004T085952-brief-e53b
Jarvis-Role: standalone
```

- Each commit holds only its run's path (`git show --name-only`).
- `git log --grep 'Jarvis-Command: ingest'` returns the ingest commit.
- A second `commit_runs.py` call printed nothing and exited 0; the working tree was clean.
- The ingest run's id equals the cutover to the second and was committed: the cutover comparison includes equal times, as spec §4.2 says ("at or after").
- `run_headless.sh` and the headless commands did not change, so the Plan 4a acceptance steps were not re-run.

## Verdict

**PASS.** Each published headless run gets one commit with the spec §4.1 subject, body and trailers, through the pre-commit hook, and the gate passes 15/15 on the tool floor.
