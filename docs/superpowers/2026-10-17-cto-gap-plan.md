# The Foundry: CTO gap plan

**Date:** 2026-10-17
**Inputs:** `docs/reviews/2026-10-17-cto-assessment.md`, `2026-10-15-next-phase-plan.md`, `roadmap.md`, open issues and PRs on this repository, the live vault snapshot of 2026-10-15.
**Status:** draft for the owner's review. Supersedes the order of phases 2–5 in the 2026-10-15 plan once approved; its phase 0 and 1 records stand.

## 1. Goal and order

Make the brief and Now page readable, give model output a quality baseline, finish the step 4 budgets, then add the CTO-facing work the system lacks: capture and intraday updates, people, and planning and communications.

The order follows three rules:
1. **Fix the interface first.** The brief (34.7 KB, target 8 KB) and the Now page (101 KB, 88 open lines, target 25 KB) are what the owner reads daily, and both are growing.
2. **Measure before adding inputs.** Ingest evals land before office-file drops (#257), Slack captures, or any new Workcell.
3. **Shrink before building.** Step 3 is done (all three extensions moved, core budget pinned at 13,200 lines and 14 schemas). The step 4 budgets finish before new features add code to core.

| Phase | What | Lane | Size | Depends on |
|---|---|---|---|---|
| 0 | Records and queue | fast lane | half a day | none |
| A | One-screen brief and lean Now page | feature: grill, spec, plan | about a week | 0 |
| B | Ingest evals | feature: grill, existing spec and plan | 2–3 days | 0 |
| C | Step 4 budgets | feature: existing prune spec, revised | about a week | A, B |
| D | Capture and the intraday picture | feature: grill, spec, plan | about 2 weeks | C, research findings, decision 3 |
| E | People Workcell | feature: grill, spec, plan | 1–2 weeks | B, D |
| F | Planning and communications Workcell | feature: grill, spec, plan | 1–2 weeks | E |
| G | Work Orders on the work codebase (#243) | feature: grill first | unsized | C; runs alongside D |
| — | Plan 5 (preferences), Plan 7 (style lint) | existing roadmap rows | — | early November |

Parked until phase F is done: #236 (market watch), #263 (overnight loop), Foreman v2, #159.

## 2. Process for every phase

The superpowers workflow (`FOUNDRY.md`, Development), with the skill named at each step:

| Step | Skill | Output |
|---|---|---|
| Grill | `superpowers:brainstorming`, with the owner | Decisions recorded in the spec |
| Spec | (brainstorming output) | `docs/superpowers/specs/<date>-<topic>-design.md` |
| Plan | `superpowers:writing-plans` | `docs/superpowers/plans/<date>-<topic>.md` with `### Task N:` lines, Global Constraints, Review Focus |
| Build | `superpowers:subagent-driven-development` in session, or `/order add` as a Work Order | Small commits, one task each |
| Tests | `superpowers:test-driven-development` | A failing bats or pytest case first for each task |
| Review | `superpowers:requesting-code-review` | Findings fixed before merge |
| Close | `superpowers:verification-before-completion` | Gate green, outcomes file, roadmap row updated |

A fix (one sentence, one failing test, no safety surface) takes the fast lane: no grill, spec or plan.

**The gate for every task:** `system/scripts/verify_setup.sh` (every bats suite except `system_health.bats`, then `python3 -m pytest system/tests/python -q`), read from its exit code. CI runs it on every PR. Any change to `brief.md`, `debrief.md`, `ingest.md`, `run_headless.sh` or `system/headless.settings.json` also re-runs the live acceptance steps before merge.

## 3. Phases

### Phase 0: records and queue

Fast lane and owner actions. No code.

- [ ] Roadmap: step 3 (all three moves, the core budget test), Tagging, CLAUDE.md prune, connector health, quarantine in brief, telemetry escalation, recall ranking, chat triage (#222) and parallel Work Orders (#229) marked built, with their PRs.
- [ ] Spec status lines: `connector-health`, `quarantine-in-brief`, `alert-tags`, `note-tags` set to built.
- [ ] Owner: queue the semantic-recall and chat-gateway research briefs with `/order add` in the vault. Phase D's grill needs the chat-gateway findings.
- [ ] Owner: merge #259 (write-cap ratchet). Hold #257 until phase B is done. Review #258 and #262.
- [ ] Owner, in the vault: run `now.py review --partition work` and close every line its evidence closes.
- [ ] Owner, in the vault: confirm the brief's quarantine line and the Sources line on a live brief.

**Done when:** the roadmap and spec statuses match the code, and both research orders are queued.

### Phase A: one-screen brief and lean Now page

The rest of the 2026-10-15 plan's phase 2. The sections are right; their contents have no limit.

**Grill questions** (`superpowers:brainstorming`):
1. Caps: "Waiting on" at 5 people plus a count, handoffs older than 90 days collapsed to one line, Active Projects at 3 next actions each. Recommended as written.
2. Where caps live: in the prep scripts, so the model only sees capped input. Recommended.
3. Now line form: one `since` stamp, a 300-character cap, update history moved to the line's evidence note. Where the history goes when a line has no evidence note.
4. Whether `now.py review` closes lines on its own in the brief prep, or lists them for the owner. Recommended: close lines whose evidence is a merged PR or closed issue, and list the rest.

**Expected tasks** (`superpowers:writing-plans` writes them):
1. Prep caps for "Waiting on" (`meeting_actions.py`), handoffs (`extensions/handoffs/brief/`), Active Projects (`active_projects.py`). pytest per cap.
2. A fixture vault at the live vault's size and a bats test that renders the brief prep and fails above 8 KB of model input.
3. A CI word count of the headless brief prompt, failing above 2,500 words.
4. `now.py add` and `set` refuse a line over 300 characters; lint warns on existing ones; pytest.
5. `now.py review` closes evidence-closed lines during brief prep; pytest with a stub `gh`.
6. `brief.md` trimmed to the section files the extensions mechanism already supports; live acceptance re-run.

**Validation:** bats (`prep.bats`, `commands.bats`, new size test), pytest (`test_now*.py`, `test_meeting_actions.py`), live acceptance of the brief.

**Done when:** for 5 weekdays the live brief is under 8 KB, the Now page under 25 KB, and the headless brief prompt under 2,500 words.

### Phase B: ingest evals (#218)

Spec and plan exist (`specs/2026-10-11-ingest-evals-design.md`, `plans/2026-10-11-ingest-evals.md`).

**Grill questions:** 3 runs per case, a $5 budget stop, a 0.67 floor. Recommended as written. Add a case from the 10-14 poisoned digest (a correction against a long note) for the shrink guard, and one case per input format #257 adds.

**Rule carried forward:** every new Workcell (phases E and F) ships with at least one eval case.

**Validation:** `evals.bats`, `test_eval_check.py`, and the first real run recorded under `system/logs/evals/`.

**Done when:** the first real run is recorded and its pass rate is in the outcomes file. Then #257 can merge.

### Phase C: step 4 budgets

Step 3 is complete on master: DTCC moved to a vault-only `extensions/dtcc/` (`9e3d45c`), and `vault_integrity.bats` pins core at 13,200 script lines and 14 schemas (`f2a99d7`). What remains is step 4. Spec: `specs/2026-10-11-claude-md-prune-design.md`, revised for the 45-line target.

- `CLAUDE.md` to about 45 lines (77 today); the Agents block moves to the `order` skill, per the prune spec.
- Schemas in core to 12 (14 today), and the budget test lowered to match.
- The core line budget lowered by what phase A removes from `brief.md` and the prep scripts.

**Validation:** the gate with every extension off and with every extension on; the budget test in `vault_integrity.bats`; the `CLAUDE.md` line test; live acceptance of the brief.

**Done when:** schemas at 12 or fewer, `CLAUDE.md` at or under 50 lines, and both budget tests lowered and green.

### Phase D: capture and the intraday picture

Chat triage (#222) already turns Slack messages that need the owner into `owed` lines. This phase adds the rest. One grill for #135 (leadership channels read in full, calendar diff), the Slack captures (`specs/2026-10-11-slack-bridge-design.md`, captures half) and the intraday update #94 asked for. They answer one question: what changed since the morning brief. Starting points: the specs on `feat/intraday-brief-94` and the chat-gateway findings from phase 0.

**Before the grill:** the owner settles the work-data boundary (decision 3). Chat content brings more work data into the vault than anything so far.

**Grill questions:**
1. Capture: a Slack channel or DM whose messages land in `raw/inbox/` for the intake. Smallest version first.
2. Intraday: a midday and a late-afternoon delta (calendar changes, new `now` alerts, new owed lines, leadership-channel items) appended to the day's brief, or sent as a Slack notice only.
3. Which channels count as leadership channels, and how a channel is added.
4. Whether an uncertainty keyword in a captured message ("stuck", "waiting on approval") becomes a Blockers line.

**Validation:** bats for the new confined fetches (stub `claude`, as `triage.bats`), pytest for the delta builder, `connector.bats` for the runner, smoke entries for each new fetch, an eval case for captured messages.

**Done when:** for 5 weekdays the owner adds no hand annotations to the brief (11 on 10-14), and every captured message reaches the wiki or the Now page within one intake tick.

### Phase E: people Workcell

From #112 (owner page, people-page contract, confidence, open questions). Input already exists: 111 entity notes and 100 meeting notes in the live vault.

**Grill questions:**
1. People-page contract: role, team, reports-to, last 1:1, open asks in each direction, recent decisions. Which fields a script fills and which the owner writes.
2. 1:1 prep: a section in the brief for each 1:1 on today's calendar, from the person's page, Now lines, meeting actions and Jira handoffs. Or a separate prep note linked from the brief.
3. Waiting-on lines sourced from meeting actions and triaged mail as well as Jira, each with its evidence.
4. A team roll-up (per direct report: open asks, overdue items), weekly in Friday's debrief.

**Build shape:** a `person` schema (new note type, so feature lane), a `people` capability on a new Workcell file, prep scripts that read pages and never write them, one eval case for the page contract.

**Validation:** schema tests in `vault_integrity.bats`, pytest for prep, an eval case, live acceptance of the brief.

**Done when:** every 1:1 on the calendar for two weeks had a prep section, and the owner rates it useful in the debrief.

### Phase F: planning and communications Workcell

**Grill questions:**
1. Decision register: a `decision` note type for CTO decisions (context, choice, owner, review date), fed from meeting notes and the Notes block.
2. Objectives: the quarter's OKRs or goals as notes, with Active Projects linked to them and a monthly roll-up.
3. Drafts: weekly status update, exec summary and board-prep pack drafted as files and recorded as `draft` Now lines. Nothing is sent; sending stays the owner's action.

**Build shape:** schemas for `decision` and `objective`, `planning` and `comms` capabilities on one new Workcell, an eval case each.

**Validation:** as phase E.

**Done when:** a weekly status draft is ready each Friday for three weeks and the owner sends it with light edits.

### Phase G: Work Orders on the work codebase (#243)

Today Work Orders cannot reach the main work codebase, whose pull requests are on Bitbucket. Grill first: whether Work Orders should run there at all, how a ticket becomes an order, the gate policy, and the push target. Runs alongside phase D once phase C is done, because it touches Work Order code that the core budget counts.

## 4. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| 1 | Approve this order (A and B before C, C before new features) | Approve |
| 2 | Phase A runs before the step 4 budgets | Yes: the brief is the daily interface and is 4x its target, and phase A shrinks `brief.md` first |
| 3 | Work-data boundary (#218): all partitions push to one private origin on a personal host | Decide before phase D; recommend a separate work origin if chat captures are wanted |
| 4 | Phase G: Work Orders on the Bitbucket codebase | Grill it; skip if the work codebase's own tooling covers it |
| 5 | #236, #263, Foreman v2 parked until after phase F | Park |

## 5. Tracking

Each phase gets a roadmap row when its grill starts, and an outcomes file when it closes. The assessment's measures (brief size, Now size, prompt words, core lines, schemas, `CLAUDE.md` lines, eval pass rate, hand annotations per brief) are rechecked at the end of each phase and recorded in its outcomes file.
