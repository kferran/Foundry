# The Foundry: factory plan

**Date:** 2026-10-21. **Status:** grilled (2026-10-21, below); the owner's merge of the pull request that carries this plan and its F0 and F1 specs approves them.
**Decisions (owner, 2026-10-21):** move existing features onto the shared parts; enforce the line with CI conformance tests, with a review skill for what a test cannot check; development skills ship in the template's `.claude/skills/`. Every principle departure (D1–D5) gets a fix on the roadmap.
**Inputs:** `docs/reviews/2026-10-21-architecture.md` (architecture, principles P1–P10, departures D1–D5), `docs/reviews/2026-10-21-development-pattern-survey.md` (feature matrix, defect classes C1–C13), `docs/reviews/2026-10-21-live-usage-survey.md`, the 2026-10-20 audit (#298–#302).
**Specs:** F0 `specs/2026-10-21-factory-f0-records-ratchet-design.md`; F1 `specs/2026-10-21-factory-f1-standard-parts-design.md` with plan `plans/2026-10-21-factory-f1-standard-parts.md`. F2–F5 get theirs when the phase before them is done, because each phase's results feed the next.

## Grill

Owner's idea; grilled 2026-10-21 with the `grilling` skill, one round, every recommendation taken:
1. **Problem:** inconsistency that brings defect classes back, two of them caught only in live use in one week (#289, #294); the owner's review load second.
2. **Who feels it:** the owner and the build agents. Other vault owners get the skills with the template but do not shape the design.
3. **Without it:** not acceptable; each new source would copy the checker again and reopen classes only live use catches.
4. **Smallest version:** F0 + F1 + F3 are the core (one way to build each part, enforced by CI), then F4's `new-source` and `foundry-review`. F2 shrinks to the departure fixes D3 and D4 (extension names out of core, a named extension API); the core-manifest rewrite waits until a ratchet shows a need. F4's `connector-probe` and `live-acceptance` follow the first new feature built on the line. F5 stays grill-first.
5. **What it displaces:** the factory ranks first; the two high-severity #298 findings build alongside it, since no factory phase touches their code.
6. **Scope:** the Source shape (7 of 9 features) gets the parts work. Compile runs and Work Orders get a written blueprint (required parts, where each is enforced) and no refactor until a defect shows the need.
7. **Measured by:** pass or fail at F4's end: no defect class recurs after its gate exists, and a feature built with `new-source` passes CI with no hand wiring. Tracked through `defect:` labels: "final review fixes" commits per PR and live regressions.

## 1. Goal and order

Every Foundry feature is built from the same parts, on the same line, and CI rejects one that is not. Measured by: no re-implemented stream walker, alert-once, cursor or stub left in a feature; every source passes the conformance tests; a defect class that recurs after its gate exists is a gate bug.

Order rules:
1. **Stop new copies first.** A ratchet test (the known violators listed, the list may only shrink) lands before any library, so nothing new copies a part while the parts are built.
2. **Parts before gates before skills.** Conformance tests check for the parts; the scaffold and review skills generate and check against them.
3. **Extract, don't invent.** Each library is lifted from the best existing copy (named below), so it holds no behaviour a feature does not already use. Retrofits are net negative in lines and give core budget back.
4. **Safety runs alongside.** The audit's safety items (#298, #299) do not wait for the factory.

The gap plan's phases E–G (people, planning and communications, Work Orders on the work codebase) follow F4 and are built on the line, with `new-source` where they add a source.

| Phase | What | Lane | PRs | Merge | Depends on |
|---|---|---|---|---|---|
| F0 | Records and the ratchet | small feature | 3 | owner (FOUNDRY.md rules, hook) / auto (records, ratchets) | none |
| F1 | Standard parts and retrofits | feature: spec, plan | 8 (1 library, 7 retrofits) | owner (connector confinement) | F0 |
| F2 | Extension boundary (D3, D4) | feature: spec, plan | 2 | owner (alerts, intake) | F1 |
| F3 | Conformance gates | small feature | 1–2 | auto | F1, F2 |
| F4 | The line's skills | small feature each | 2, then 2 after the first new feature | auto | F1–F3 |
| F5 | Gate every model write (D1, D2) | feature: grill first | set by the grill | owner (publish gate) | F1; #288 |
| S | Safety track: #298 high, #299, #298 medium | fast lane / feature | 4–6 | owner | none (parallel) |

What paces the work is the owner's merges and live checks, not build effort: phases run as agents with subagents, and independent PRs (the F1 retrofits, track S) build in parallel.

## 2. Process

Each phase follows FOUNDRY.md Development: F1, F2 and F5 get a spec and plan; F0, F3 and F4 are small features (task list in the spec). Each retrofit is its own PR, so a broken feature is one revert. Each phase ends with its outcomes line on the roadmap and, for F1 and F2, a live acceptance on the server (`--check` for each touched source, then a read-only log audit 24 h after the update).

## 3. Phases

### F0: records and the ratchet
- [ ] FOUNDRY.md gains an **Architecture** section (the name, the diagram, principles P1–P10 with where each is enforced). Owner merges. CLAUDE.md is at its 50-line cap, so no pointer line there; FOUNDRY.md's Development section links it.
- [ ] The documents land generic: this plan as `docs/superpowers/2026-10-21-factory-plan.md`, the architecture note and both surveys under `docs/reviews/`, with "the live vault" for the vault's name and no `.scratch/` paths.
- [ ] Roadmap row "The factory" pointing here; a row "Hardening after the 2026-10-20 audit" (#298–#302).
- [ ] **The pipeline is required** (owner, 2026-10-21): FOUNDRY.md Development names the station and skill for each step (grill an owner's idea with `grilling`; spec with `superpowers:brainstorming` and its builder check; plan with `superpowers:writing-plans`; build, review and close with the superpowers skills). Specs carry `**Grill:**`, `**Builder check:**` and `**Blueprint:**` lines and plans the writing-plans header; a pipeline test in `conformance.bats` fails a new spec or plan without them. The `grilling` skill is vendored into `.claude/skills/` so every vault has it.
- [ ] `.gitattributes`: `CHANGELOG.md merge=union` (C13), plus a CHANGELOG test line that fails on a duplicated date heading (two same-day PRs can each add one).
- [ ] Defect-class labels `defect:<class>` (C1–C13) on the repository; FOUNDRY.md's fix lane says a fix PR carries one.
- [ ] **Ratchet test** `system/tests/conformance.bats`: lists today's re-implementations (stream walkers, `alert_once`, `logline`, `class Fail`, stub files, private imports from extensions) and fails on any new one. Known violators sit in an allowlist that each F1 retrofit shrinks.
- [ ] **Timing ratchet** in the same file: reads each unit's `TimeoutStartSec` and its sessions' timeouts (from the unit files and the fetch scripts' `CONNECTOR_TIMEOUT` defaults) and fails when the sum plus 10 s grace each passes the unit limit, or a `--check` passes the smoke timeout. Seeded from today's values, so every F1 retrofit that changes a session's time is checked (C3).
- [ ] D5 docs fix: the gap plan's stale budget numbers (the gap plan belongs to another session's phases; coordinate the edit with it).

**Done when:** both ratchets are green on master and the Architecture section is merged.

### F1: standard parts and retrofits
Libraries (one PR, with tests ported from their source):
- [ ] `vaultlib/connector.py`: a low-level `walk`, `too_large(content)` and `Fail` for every caller, and `check_stream` on top for the read sessions. From `extensions/intraday/scripts/watchlib/check.py:31-90`. Notify (a write session) and calendar (structured output) use `walk` directly. Closes C1 and C4 for every caller.
- [ ] `system/scripts/lib_fetch.sh`: `logline`, `alert_once`, `fail`, `skip`, `--check` parsing, the work-dir trap, and `fetch_others` (the deny list per connector, as bash arrays). From `triage_fetch.sh:50-69`. The ticket-tracker deny list stays in its extensions, since core may not name the vendor.
- [ ] Cursor and ledger helpers: from `watchlib/common.py` state and the triage ledger (the one with atomic writes; no copy has a prune, so none is added).
- [ ] Test doubles: one `system/tests/stub_claude_connector` dispatching on `--allowedTools` (from `stub_claude_watch`; `stub_claude` stays the headless stub), one `stream()` builder in the pytest helpers.

Retrofits, one PR each, in order of the live vault's use:
1. [ ] **Inbox and chat triage.** Triage mail asks for pages of 50 with no too-large check (`triage_fetch.sh:111`), the setup that lost mail in #289. If the live logs show a tick with many threads and no rows, the page fix moves to track S now; otherwise it rides this retrofit (pages of 10 with token paging, as #297 did).
2. [ ] Meetings fetch (rising use, 13 search failures in the live vault).
3. [ ] Intraday watch (the libraries' source; mostly import changes).
4. [ ] Notify.
5. [ ] Calendar.
6. [ ] Handoffs.
7. [ ] RCA filer.

**Done when:** the ratchet allowlist is empty for walkers, `alert_once`, `logline`, `Fail` and stubs; each retrofitted source passed `--check` live. Core lines: four of the seven walkers are in core and the new libraries move into core from an extension, so core may not shrink; the F1 spec measures it first, and any raise above 13,950 goes to the owner with the measurement.

### F2: extension boundary (D3, D4)
Cut by the grill: a core manifest for core features (units, smoke rows and tags read from a manifest instead of `install_units.sh:94-118`, `smoke_check.sh:120-128` and `alerts.py`) waits until a ratchet shows the hard-coded blocks drifting.
- [ ] Extension tags, routes and lint rules leave core: `alerts.py` (`incident`, `rca`, `handoffs`, `telemetry` and the telemetry regex), `intake.py:357` (`production_error` routing becomes an extension `importer`), `index.py:26, 69-80`, `schema.py:19`. The core-clean test learns those words.
- [ ] Extension API: `vaultlib/api.py` re-exports what extensions may use (`connector`, `now.add`, `alerts`, `redact`, `cli`, the cursor helpers); the ratchet bans other `vaultlib` imports from `extensions/`.
- [ ] `config_keys` stated once: the loader reads them from the extension's schema (today they are written twice, and `handoffs_site` is missing from one).

**Done when:** no extension name appears in core outside the allowlist, no extension imports a `vaultlib` name outside `vaultlib/api.py`, and each extension states its config keys once.

### F3: conformance gates
- [ ] `conformance.bats` turns from ratchet into rule: every source's fetch script sources `lib_fetch.sh` and runs `connector_run`; its checker calls `connector.walk` or `connector.check_stream`; it has a smoke row, a unit and its alert tags (an extension in its manifest; a core source in the test's own table, since F2 keeps core's blocks); its config keys match its schema.
- [ ] **Timing budget rule:** F0's timing ratchet loses its known-overrun list once #299 fixes intake and smoke; an extension's session timeouts move from script comments into its manifest, and core's stay in the test's table (C3).
- [ ] **Budget scope (D5):** the core budget counts `system/hooks` and `.claude/commands` too, at a measured cap.

**Done when:** each rule has a test that failed on a seeded violation before it passed.

### F4: the line's skills (in `.claude/skills/`, written with `superpowers:writing-skills`)
Grill: `new-source` and `foundry-review` first (with the spec template's blueprint checklist); `connector-probe` and `live-acceptance` after the first new feature is built on the line, so they are written from a real use.
- [ ] `connector-probe` (second): one real `connector_run` from `.scratch` for a named tool, page size and view; records the stream shape, characters per result against the 25,000-token limit, and `structuredContent` against text; writes `docs/superpowers/spikes/<date>-<topic>-probe.md` with a recommended page size. Prevents C1, C4.
- [ ] `new-source` (first): scaffolds a Source from the blueprint (fetch script on `lib_fetch.sh`, checker on `connector.py`, manifest entries with timeouts, unit files, failing tests for exits 1, 3, 6, 7 and too-large, a CHANGELOG line). Template: the handoffs extension, the smallest complete one. The scaffold passes `conformance.bats` before any feature code is written.
- [ ] `foundry-review` (first): diff checks per defect class that a test cannot make (a Now or Slack writer without redaction of outside text, a model write outside the gate, an outside-text alert, a race test with `sleep`, a skip without its reason, a missing CHANGELOG line or defect label). Runs before a PR opens; output goes in the PR body.
- [ ] `live-acceptance` (second): `--check` in a scratch vault for each source a change touches, then, 24 h after the server updates, a read-only audit of that feature's logs (ticks, rows kept, failures). Writes `docs/superpowers/spikes/<date>-<topic>-acceptance.md`.
- [ ] The spec template (brainstorming output) gains the blueprint checklist: which shape, which parts, which defect classes apply.

**Done when:** a throwaway feature built with `new-source` in `.scratch` passes CI with no hand wiring, and `foundry-review` flags a seeded violation for each of its checks.

### F5: gate every model write (D1, D2)
Grill first. Questions for the grill:
- **D1, interactive wiki edits:** route `Edit(/wiki/**)` through staging and the gate (a hook that stages and publishes on save), or limit interactive writes to notes the owner opens, or a post-edit lint that reverts a gate failure.
- **D2, machine writers:** triage, the watch and `today_log.py` write Now and the today file through their own scripts. Route them through `publish.py` as a `machine` caller, or give `now.add` and the today writer the gate's checks (redaction, cap, walls) as a shared validator.
- Depends on #288 (redaction of watch and triage lines).

**Done when:** every model-derived write to `wiki/` or `briefings/` passes the same checks, with a test per writer.

### S: safety track (parallel)
1. [ ] #298 high: publish through a symlinked folder (realpath under `wiki/<p>/`, never `private/`).
2. [ ] #298 high: the Work Order tick re-runs the full add-time screen; research context skips `private/`.
3. [ ] #299: a brief is never lost to one bad line or a conflict (cut to fit, one retry, a `now` alert); #107 closes with it.
4. [ ] #298 medium: commit-hook bypass denied, redaction gaps (with #288), research publish under `run.lock`.
5. [ ] #302 medium and small, #298 low, #122 minors: fast lane as capacity allows.

## 4. Order across the roadmap (owner, 2026-10-21)
The factory line ranks first, for consistency: F0 → F4, with the two high-severity #298 findings building alongside (grill Q5), then the rest of the safety track on the line, then the Now page work, then F5 and the rest of the audit, then what is unused, then gap plan E–G. The F1 retrofit order follows the live vault's use: triage, then meetings (rising use, 13 search failures), then the watch, notify, calendar, handoffs and the RCA filer.

## 5. Tracking
One GitHub issue per phase (F0–F5) with its checklist; the roadmap's "The factory" row names them. Each PR says "Part of #N" and carries its `defect:` label when it is a fix.
