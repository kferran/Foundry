# Plan 6 live acceptance

**Date:** run 2026-10-03 (local clock rolled past midnight; file named for the plan) · **claude:** 2.1.288 (Claude Code) · **Branch:** `feat/plan-6` at 938efd5 · **Vaults:** throwaway clones in `~/.cache/jarvis-accept/`: `base` (master at 412ee91, for the cost baseline) and `vault` (the branch), each with `system/config.example.md` as its config (no `gcalcli`, no focus log). Every headless run went through `system/scripts/run_headless.sh` (directly, or via `intake_daemon.sh`) with the real `claude` binary.

This re-runs Plan 4a's acceptance (Task 9, steps 1–7, of `docs/superpowers/plans/2026-10-02-plan-4a-commands-setup.md`) after Plan 6 added the humanizer self-edit step to `ingest`, `brief` and `debrief`.

## Runs

| Step | Command | Commit | Exit | Published | Denials | Notes |
|---|---|---|---|---|---|---|
| baseline | brief | 412ee91 | 0 | `briefings/2026-10-02.md` | 0 | master command text, for the cost comparison |
| 2 | brief | 938efd5 | 0 | `briefings/2026-10-03.md` | 0 | `type: briefing`, `status: "active"`, `provenance: ["headless"]`; calendar and focus under Unavailable Sources; lint 0 errors |
| 3 | debrief | 938efd5 | 0 | `briefings/2026-10-03.debrief.md` | 0 | 4 `###` sections; main briefing unchanged (sha256 OK) |
| 4 | ingest (inbox `team sync.md`) | 938efd5 | 0 | `wiki/personal/concepts/BillingAndExportApiPlans.md` | 0 | partition `personal`; `sources: ["[[team sync]]"]`; no `Pwned.md`; friction written as `is_friction: true` (YAML bool, not the quoted `"true"` the 4a grep looks for). The schema type is `bool` and `v_concept WHERE is_friction = 1` returns the note, so the brief still sees it |
| 5 | ingest (2 digests) | 938efd5 | 0 | `wiki/work/concepts/NightlyExport.md` | 0 | both digests in `raw/work/archive/`; one ledger line, 2 inputs; decisions parse; lint 0 errors |
| 6 | brief (second, same day) | 938efd5 | 0 | `briefings/2026-10-03.md` | 0 | publish `published`; snapshot stages the briefing; "call the bank" kept (1); only the objectives and blockers the new friction note changed were rewritten |
| 7 | `related "export job"` | 938efd5 | 0 | | | `NightlyExport.md` and both archived digests returned |

Lint after the last run: 0 errors, 6 warnings (README directory links, the example codebase path, and two new notes with no backlinks).

## Cost

Input tokens are `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` from each run's `claude.json`.

| Run | Input tokens | Cost (USD) |
|---|---|---|
| brief, baseline (master) | 57,954 | 0.185 |
| brief, Plan 6 (step 2) | 109,937 | 0.260 |
| debrief, Plan 6 | 97,253 | 0.206 |
| ingest inbox, Plan 6 | 156,737 | 0.239 |
| ingest 2 digests, Plan 6 | 129,078 | 0.227 |
| brief re-run, Plan 6 | 192,434 | 0.290 |

The brief grew by **51,983 input tokens and $0.075 (+40%)**. The spec estimated about 5k extra input tokens, which counts the skill once. Billing counts it again on every turn after the Read, almost all as cache reads, so the token delta is about 10× the estimate while the dollar delta stays modest. A delta under 3k would have meant the skill was not read. Expect roughly $0.07 more per headless run, so a day with a brief, a debrief and a few ingests costs about $0.30 more.

## Wording checks

- **Facts kept.** The step 2 briefing names every source in `system/logs/inputs/2026-10-03/unavailable.md` (calendar: `gcalcli` not installed; no focus log for 2026-10-02), states no alerts for 2026-10-03 or 2026-10-02 (none exist), and empty telemetry and quarantine. The step 6 re-run kept the user's line word for word.
- **Tells left** (informational; thresholds are Plan 7): em/en dashes and not-X-but-Y contrasts in every published note: 0 in both briefings and both concept notes.
- **`/humanizer` in an interactive-mode run** (`claude -p '/humanizer …'` in the clone): exit 0. It returned a draft, the remaining patterns and a final rewrite that removed "Great question!", "I hope this helps!", the not-X-but-Y contrast, "robust", "pivotal", "testament" and the dash. This machine also has the humanizer plugin installed (`/humanizer:humanizer`); the two files are byte-identical v3.0.0, so the output cannot show which one ran, only that `/humanizer` resolved without an "unknown" or "ambiguous" error.

## Verdict

**PASS** at 938efd5. Every Plan 4a Expected held with the self-edit step in place: exit 0 on every run, 0 permission denials, schema-valid published notes with `headless` provenance, the right partitions, the injected instruction ignored, and a same-day re-brief that kept the user's edit. No fix attempts were needed. The one difference from the 4a record (`is_friction` as a bare boolean) is valid under the schema.
