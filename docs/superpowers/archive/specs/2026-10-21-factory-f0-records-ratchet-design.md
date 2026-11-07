# Factory F0: records and the ratchet

**Date:** 2026-10-21
**Status:** approved and built (#312, #313, #315, #322, #325)
**Program:** `docs/superpowers/2026-10-21-factory-plan.md` (phase F0)
**Grill:** 2026-10-21, recorded in the program plan's `## Grill` section (the factory is the owner's idea).
**Builder check:** 2026-10-21, five questions: sources and audit version, usage hook scope, timing ratchet scope, PR layout (settled in §3.2, §3.6, §3.7 and §4 as the builder's calls), tracking issues (the program plan's §5 covers them).
**Blueprint:** none: development process and tests, no feature shape.
**Lane:** small feature (task list below, no separate plan). Task 1 changes FOUNDRY.md's rules and Task 5 adds a hook, so the owner merges those two PRs; the rest auto-merge.

## 1. Goal

Write down the architecture and its principles where every session reads them, and stop new copies of shared parts and new timing overruns before F1 builds the parts. Nothing in F0 changes how a feature behaves.

## 2. Decisions it builds on

- Owner, 2026-10-21: the factory line ranks first; existing features move onto shared parts; CI conformance tests enforce the line; development skills ship in `.claude/skills/`; every principle departure (D1–D5) is a roadmap fix; no human-time estimates.
- The name: a **gated LLM-wiki compiler** (owner, 2026-10-21).
- CLAUDE.md is at its 50-line cap (phase C test), so F0 adds no line there.

## 3. What F0 adds

### 3.1 FOUNDRY.md Architecture section (Task 1, owner merges)
A new `## Architecture` section before `## Development`:
- One paragraph: the name and what it composes (an LLM-compiled markdown wiki; fixed workflows with a check after each model step; the model treated as untrusted, with policy in code), and the three ways it extends the LLM wiki (a deterministic publish gate, partition walls, scheduled headless runs with an operations layer).
- The data-flow diagram (sources → confined fetch → `raw/` → intake → staging → gate → wiki, Now, briefings → index → query, brief, recall, notices).
- The four blueprints (Source, Poller, Compile run, Work Order) and their required parts.
- Principles P1–P10, each with where it is enforced; a principle held only by prose says so.
- The known departures (D1–D5) with their roadmap phase.
Development gains one line: a feature names its blueprint in its spec and is built from the standard parts.
A docs test checks the section's heading and the ten principle names (names, not wording).

### 3.2 Records (Task 2, auto-merge)
- `docs/superpowers/2026-10-21-factory-plan.md`: the program.
- `docs/reviews/2026-10-21-architecture.md` (prior art and the as-built survey, condensed), `docs/reviews/2026-10-21-development-pattern-survey.md`, `docs/reviews/2026-10-21-live-usage-survey.md`, `docs/reviews/2026-10-20-audit.md`. Generic: "the live vault", no user paths, no `.scratch/` paths.
  - Sources: the session's working drafts (architecture and roadmap, prior art, development pattern survey, usage survey, the audit and its verification pass). They are not in the repository; the builder receives them with this spec.
  - The audit record is the audit with its "unlogged problems" section replaced by the verification pass (verdict, severity and source per item), so no claim the verification dropped is recorded.
  - The architecture note keeps §1 (architecture) and §2 (principles); its departures table records the owner's decision (every departure D1–D5 is a roadmap fix, phase named), not the draft's options. Its roadmap section is left out: the roadmap is the program plan and `roadmap.md`.
- Roadmap rows: "The factory" (this program, phases F0–F5) and "Hardening after the 2026-10-20 audit" (#298–#302).
- The gap plan's stale core budget figures corrected (D5, docs half). The gap plan's phases belong to another session; this edit changes numbers only.

### 3.3 Release-note merges (Task 3, auto-merge)
- `.gitattributes`: `CHANGELOG.md merge=union` (defect class C13: every merge re-conflicts the CHANGELOG of each open PR).
- A CHANGELOG test fails on a date heading that appears twice (union can keep two same-day headings).

### 3.4 Defect labels (Task 3)
- Labels `defect:<class>` for C1–C13 on the repository (`gh label create`).
- FOUNDRY.md's fast-lane paragraph: a fix PR carries one `defect:` label. A class that recurs after its gate exists means the gate is wrong.

### 3.5 The copy ratchet (Task 4, auto-merge)
`system/tests/conformance.bats`, test "no new copy of a shared part":
- Finds, in `system/scripts` and `extensions/*/scripts` (tests excluded):
  - stream walkers: Python files that read `"tool_result"` or `tool_use_id` themselves;
  - shell helpers defined at top level: `logline()`, `alert_once()`, `fail()`, `skip()`;
  - Python `class Fail` and module-level `def config(`;
  - extension imports of a private `vaultlib` name (`from vaultlib.<m> import _<name>`);
  - test doubles: `stub_claude_*` files (the headless `stub_claude` and the Work Order `stub_claude_nightshift` are listed as other shapes, with that reason), and pytest modules that define their own `stream(` builder.
- Each allowlist entry is one line, `<kind> <path>[:<name>]  # <reason or the F1 retrofit that removes it>`, so a PR's diff shows exactly which entries it removes.
- Compares the hits with an allowlist in the test (today's 8 walker files, the helper copies, the `Fail`/`config` copies, the private imports), and fails on any hit not in the list. A second assertion fails when an allowlisted entry no longer exists, so each F1 retrofit must shrink the list in the same PR.
- `vaultlib/nightshift_session.py` reads the stream for the Work Order runner; it stays on the list until F1 decides whether it shares the walker.

### 3.6 The timing ratchet (Task 4)
Test "every unit's sessions fit its time limit", in `conformance.bats`:
- A table in the test names each unit and what one run of it can wait on: the unit's `TimeoutStartSec` (read from `system/systemd/*.service.in` and `extensions/*/units/*.service.in`), and each bounded step with the file and default it reads and how many times one run can call it (fixed, or the script's own cap).
- **What counts:** every `claude` session (connector sessions through `lib_connector.sh`, `CONNECTOR_TIMEOUT="${X:-N}"`; headless sessions through `run_headless.sh`, `HEADLESS_TIMEOUT`), including sessions a script runs through another script (the watch's calendar calls count toward the watch unit), plus the other bounded waits in the same unit (`gh` calls in debrief prep, `git fetch` in update, lock waits). Each step's kill grace is its own (`timeout -k`: 10 s in `lib_connector.sh`, 30 s in `run_headless.sh`).
- **Out of the table:** the Work Order unit (per-order sessions under a 14 h limit, budgeted in Python by the runner) and telemetry's HTTP poller (no session; its calls carry their own 60 s limits). The table says so in a comment.
- For each unit, the sum of count × (timeout + grace) must be at most the limit. For each smoke row, the row's timeout must cover its script's `--check` steps, and the smoke unit's limit must cover the sum of its rows.
- The test reads the numbers from the files, so changing a default without the table fails, and changing the table past a limit fails.
- Seeded from today. Units that already fail (intake and smoke, audit item 10, tracked in #299) sit in a known-overrun list with their issue number; the list may only shrink. *Builder's call:* any other unit found over its limit at seeding joins that list under #299 and is named in the PR body for the owner.

### 3.7 Usage logging (Task 5, owner merges: a hook)
The live vault's usage survey could not measure `/query`, `/lint`, `/impact` or `/rca`. A `UserPromptSubmit` hook appends `{ts, command}` to `system/logs/usage-YYYY-MM.jsonl` when a prompt starts with `/<name>`, and a `PreToolUse` hook on the `Skill` tool appends `{ts, skill}`. No prompt text is logged. Both fail open and resolve their root from `BASH_SOURCE` (FOUNDRY.md working rule).
*Builder's call (scope):* `install_hooks.sh` writes user-level settings, so the hooks fire in every project. They log only what the owner does in the vault: they reuse the memory hooks' gates in `lib_memory.sh` (skip `FOUNDRY_HEADLESS=1`, unattended sessions and non-CLI entrypoints) and log only when the session's cwd is the vault root, never a registered codebase. Headless commands are already counted in the run ledger. `install_hooks.sh` installs them with the existing hooks; a bats test feeds each hook a sample event and checks the one line written.

### 3.8 The pipeline is required (Task 6, owner merges: rules and a vendored skill)
Owner, 2026-10-21: every spec and plan goes through the superpowers pipeline, and a new idea the owner proposes is grilled to validate it before any spec. F0 makes both concrete:

**The stations, in FOUNDRY.md Development** (replacing the prose workflow line):
| Station | Skill | Record |
|---|---|---|
| Grill (an idea the owner proposes) | `grilling` (vendored, below): is it worth building, for whom, what happens without it, its smallest version, what it displaces | the grill's decisions on the idea's issue, or a `## Grill` section in the spec |
| Spec | `superpowers:brainstorming`, ending with its builder check (`builder-check-prompt.md`) | `docs/superpowers/specs/<date>-<topic>-design.md` |
| Plan | `superpowers:writing-plans` | `docs/superpowers/plans/<date>-<topic>.md` |
| Build | `superpowers:subagent-driven-development` or `superpowers:executing-plans`, with `superpowers:test-driven-development` | commits, one task each |
| Review | `superpowers:requesting-code-review` (and `foundry-review` once F4 ships it) | findings fixed before merge |
| Close | `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch` | gate green, roadmap row updated |
The fast lane (a fix) still skips grill, spec and plan. An idea that comes from an audit finding, an issue a live vault logs, or a review is not an owner idea; its spec names that source on its Grill line instead.

**Required header lines**, checked by CI:
- A spec: `**Grill:**` (the date and where the grill's decisions are recorded, or `not an owner idea: <source>`), `**Builder check:**` (the date and the outcome: questions found and how each was settled), `**Blueprint:**` (Source, Poller, Compile run, Work Order, or `none: <why>`).
- A plan: the writing-plans header (`REQUIRED SUB-SKILL`), `## Global Constraints`, `## Review Focus`, and a `**Spec:**` line naming its spec.

**The pipeline test** in `conformance.bats`: every spec and plan dated on or after the day F0's PR A merges carries those lines; a spec's Grill line that names an issue points at an issue that exists (`gh` is not called in CI: the line holds an issue URL or a `## Grill` section, checked by pattern); a plan's `**Spec:**` file exists. Older documents are grandfathered by date, so the test needs no allowlist.

**The grill skill ships with the template.** `grilling` today lives in a user-level plugin (MIT, by Matt Pocock), so a fresh vault does not have it. Task 6 vendors it into `.claude/skills/grilling/` at a pinned version with its license and a checksum test, as `humanizer` is, and adds the Foundry's validation questions (worth building, for whom, what happens without it, smallest version, what it displaces) to its opening round. The superpowers plugin is a development requirement: `check_deps.sh`'s development tier and FOUNDRY.md Requirements name it.

## 4. Tasks

| Task | Files | Test first | Merge |
|---|---|---|---|
| 1 | FOUNDRY.md | docs test: Architecture heading, P1–P10 names, Development's blueprint line | owner |
| 2 | docs/superpowers/2026-10-21-factory-plan.md, docs/reviews/*, roadmap.md, gap plan figures | none (docs) | auto |
| 3 | .gitattributes, CHANGELOG test, FOUNDRY.md fast-lane line, labels | duplicate-heading test fails on a seeded duplicate | owner (with Task 1) |
| 4 | system/tests/conformance.bats | each assertion fails on a seeded violation (a new `alert_once()`, a removed allowlist file, a raised session timeout) | auto |
| 5 | system/hooks/usage_log.sh, install_hooks.sh, a hooks bats test | the sample event writes one line; a prompt with no slash writes none | owner |
| 6 | FOUNDRY.md Development stations, `.claude/skills/grilling/`, check_deps development tier, the pipeline test in conformance.bats | a seeded spec without `**Grill:**` and a seeded plan without `## Review Focus`, both dated today, fail; a 2026-10-01 spec without them passes; a changed vendored file fails the checksum | owner (with Task 1, PR A) |

**PRs (builder's call):** three, merged in this order.
1. **PR A, owner merges:** Tasks 1, 3 and 6 (every FOUNDRY.md rule change, the pipeline test and the grill skill, `merge=union`, the labels). First, so later PRs get the union merge and the pipeline test.
2. **PR B, auto-merge:** Tasks 2 and 4 (records and both ratchets).
3. **PR C, owner merges:** Task 5 (the hook).
PR B and PR C build alongside PR A and rebase after it merges.

## 5. Out of scope
The libraries and retrofits (F1), manifests and the extension API (F2), turning the ratchets into rules and timeouts into manifests (F3), the skills (F4), gating every write (F5).

## 6. Done when
Both ratchets are green on master; the Architecture section is merged; the usage log has lines from the live vault after its next update.
