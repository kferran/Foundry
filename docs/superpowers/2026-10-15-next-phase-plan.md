# The Foundry: next-phase plan

**Date:** 2026-10-15
**Inputs:** `roadmap.md` (owner's order of 2026-10-11 and 2026-10-13), `2026-10-11-simplification-review.md`, `docs/reviews/2026-10-11-system-assessment.md`, the 2026-10-13 audit (PR #130, tracker #136), open issues and PRs on this repository, and ten days of the live vault (briefs and debriefs 10-05 to 10-14, the Now page, 31 Work Order notes).
**Status:** order approved by the owner (2026-10-15: live-use fixes first, start phase 0). Each phase follows the usual process (fast lane for fixes, grill, spec and plan for features).

## 1. Where things stand

**Built since the 2026-10-11 review:** the express install (#128), Slack notices (#125), RCA (#120), the usage ceiling (#134), the connector runner (#144), the smoke check (#146, #147), the research Workcell (#172), `now.py review` (#174), the CI gate on every PR (#177), and the audit's fixes (PRs #139, #141, #153–#155, #165). The owner ruled on the rest in #136: S1 stays opt-in with no signing until a second user exists, C3 is documented (the check writes only when evidence closes a line, on purpose), C9 is declined (three timeouts then quarantine is the safer failure). Open: S8–S11, C13, C14, and the follow-up that lets the daily update merge past a refused run (owner, 2026-10-15).

**The simplification targets have moved the wrong way.** Steps 1 and 2 are merged. Steps 3 and 4 have not started, and the features added since the review grew the code.

| Measure | 2026-10-11 | Target | Today |
|---|---|---|---|
| Lines under `system/` (no tests) | 11,097 | ~5,500 core | 13,331 |
| Owner-specific lines (DTCC, telemetry, Jira, meetings) | ~3,170 | 0 in core | ~3,700 (~5,950 with sync and Work Orders) |
| Required packages | 13 | 8 | 11 |
| Setup decisions | ~25 | 3–5 | 5–7 |
| Units on by default (standalone) | 7 | 3 | 4 (intake, brief, debrief, smoke) |
| Schemas | 18 | 9 | 19 |
| `CLAUDE.md` | 87 lines | ~45 | 88 |
| Headless brief prompt | ~6,000 words | <2,000 | ~6,270 (`brief.md` 1,682 + humanizer 4,589), ~8,000 with `CLAUDE.md` |

**Drafted and not built:** ingest evals (#28), alert tags and note tags (#158), DTCC sources (#140), telemetry escalation (#171, spec merged in #186), the Now clock (spec merged in #187), Slack captures, the `CLAUDE.md` prune.

**Open PRs:** #184 (smoke liveness and unit drift; touches `install_units.sh` and `update_template.sh`, so the owner merges it) and #130 (the audit document, draft).

## 2. What the live vault shows

The live vault runs almost every feature: Work Orders, meetings, triage, preferences (since 10-14), the unattended update, Slack notices, handoffs, RCA filing, DTCC, five telemetry sources, and a server plus a client. The personal partition is empty.

| # | Finding | Evidence |
|---|---|---|
| L1 | **Connectors break and recovery is manual.** | Calendar fetch failed in the brief prep on 10-13 and 10-14 (fixed in #176, not yet confirmed live). Jira token expiry on 10-13. Slack notify exit 3 on 10-13. Drive "no files list" on 10-12 and 10-13. A lapsed network key caused 23 failed telemetry runs on 10-13. "Mail and chat skipped" in every brief from 10-10 to 10-13. |
| L2 | **The brief is five times its size target.** | The 10-13 brief is 27.9 KB and 10-14 is 31.8 KB (303 lines) against the review's 8 KB. Debriefs grew from 5–7 KB to 15–17 KB. "Waiting on" has 21 person headings. "Handoffs to chase" repeats tickets untouched since 2025. |
| L3 | **The owner keeps the day current by hand.** | 11 hand-added "inbound sweep" and "review HH:MM" annotations in the 10-14 brief; in-session crons stand in for #135; a day-ahead pack ran as a Work Order. |
| L4 | **The Now page outgrew its form.** | 53 open lines in 93.6 KB (about 1.8 KB a line), 173 `since` stamps, update paragraphs appended to lines. Lines for #157 and #162 stay open after both merged. |
| L5 | **Work Orders do not deliver on outside codebases.** | 15 done, 5 failed, 3 blocked, 6 cancelled. All 3 blocked orders stopped at `verify` (`pnpm install`, exit 127, then corepack downloading inside the sealed verify, #189); one plan took 4 orders and a hand run. No order has targeted the main work codebase, whose PRs are on Bitbucket. Every order has `started_at` equal to `finished_at`, so the brief shows "07:00–07:00". |
| L6 | **Failures need a human to unstick them.** | A digest poisoned on 10-14 after 3 shrink-guard rejections was patched by hand and never requeued (`intake.py --retry` exists, and since #183 the alert names it). Quarantine read "empty" on 10-11 and listed two inputs on 10-12. The RCA filer hit a required Jira field (exit 6) and then its own `.attempt` marker (exit 5) (#175). An empty `.srt` summary replaced and deprecated a populated meeting note (#188). |
| L7 | **Some features never get input.** | `system/logs/metrics/` never had a file, so the Fail-Fast Loop Breaker in `CLAUDE.md` has never fired. One telemetry source reported 0/0/0 every day. The focus tracker printed "no focus log" until #128 removed it. |
| L8 | **Notes typed on the client get lost.** | `Untitled.md` and `Untitled 1.md` sit at the vault root 4+ days after the review flagged them. |
| L9 | **The vault holds side projects.** | `docs/` in the vault carries 9 work plans and specs and a Python tool with tests (`docs/gmail-cleanup/`), none of them registered codebases. |
| L10 | **One vault-local schema change belongs upstream.** | The vault's `production_error` schema makes `operation_id` optional, because scheduled jobs have no trace. |

## 3. The recommendation

Keep "simplify the template" as the program, but put two short phases in front of step 3. The live vault's top problems are reliability (L1, L5, L6) and a brief nobody can read on one screen (L2, L4). Step 3 moves the code those problems live in, so fixing them first means fixing them once, while the code is still where the tests expect it. Phase 2 is also the first half of step 4, so the program loses no ground.

| Phase | What | Size | Process |
|---|---|---|---|
| 0 | Housekeeping | under a day | fast lane and tracker edits |
| 1 | Reliability from live use | about a week | mostly fast lane, two short specs |
| 2 | One-screen brief and a lean Now page (step 4, part 1) | about a week | one grill, one spec |
| 3 | Ingest evals | 2–3 days | grill, then the existing plan |
| 4 | Simplify step 3: extensions | 2–3 weeks | grill, spec, one plan per extension |
| 5 | Intraday picture (#94, #135) and Slack captures | after phase 4 | grill informed by the research orders |
| — | Step 4, part 2: `CLAUDE.md` to 45 lines, schemas to 9 | after phase 4 | existing prune spec, revised |

The two research briefs (semantic recall, chat gateway) cost no attended time. Queue them as Work Orders now so their findings are ready for phase 5.

## 4. Phases

### Phase 0: housekeeping

Trackers and docs that lag behind merged work, so the next reader is not misled.

- [x] Close #138: the toolchain and install phase shipped in #151 and #156; what is left is #189.
- [ ] #157 stays open until the owner's Slack tap test of an `obsidian://` link (PR #183's last done-when). #106 stays open: it holds the deferred RCA entries, phase 2 and the review minors from #120.
- [x] Tick the merged lines on #136 (S3+S7, S6, C1+C2, C4, C7), #122 (the fast lane, step 1, step 2's connector runner) and #166 (staged-blob lint, git environment strip, secret-shape lint, owner-leak test, refusal list, allow-list lint, `.gitattributes`).
- [x] Set the status lines of the sync-refused-commit and update-dirty-tree specs to built (PR #165), and the headless-hardening spec to built (PR #141).
- [x] Correct the roadmap: standalone enables 4 units (smoke included), the usage ceiling is complete (#134), and the order above is recorded.
- [x] Take the vault's `production_error` change upstream: `operation_id` optional (L10). Fast lane, PR #194.
- [ ] Delete stale remote branches (old plan branches, `feat/slack-bridge`, `docs/findings-specs`) once the owner agrees. `feat/intraday-brief-94` holds unmerged specs for #94: merge them as docs or close them in phase 5.
- [ ] In the vault: close the Now line for #162 (merged in #183). The #157 line waits for the tap test.

### Phase 1: reliability from live use

**Fast lane** (one failing test, one PR each):

1. [x] Work Order timestamps: `finished_at` is read after the session (L5). PR #195.
2. [x] The daily update merges past a refused run and its alert names the refused or left-out paths (owner, 2026-10-15, on #136). PR #193.
3. [x] Audit C13: `check_deps.sh` fails clearly below Python 3.11. PR #196.
4. [x] A test that needs a user systemd, `bwrap` or a non-root user skips with `environment:`, and `--require-suites` (CI) fails it (audit C16). PR #199.
5. [x] #188: the replaced note was empty by #142's rule, so no restore was needed; the import now keeps its attendees and `/ingest` compiles a drop from its transcript. PR #190.
6. [ ] #175: the RCA filer clears its `.attempt` marker on a rejected create, and reads required custom fields from `rca_extra_fields`. Feature lane: spec #198 (merged), build PR #200 for the owner.
7. [x] #189: one corepack home per item, written by install and read-only in the sealed verify. PR #192.
8. [x] Lint warns on any `.md` file at the vault root other than the four root documents (L8). PR #197.

**Short specs** (features, because they touch the publish gate or alerting):

9. **Connector health (L1).** Spec: `specs/2026-10-15-connector-health-design.md`. #184 is merged (timer liveness and unit drift). Then each fetch reports an auth failure as its own reason (expired token or key), separate from a network error, and the smoke check sends one `now` alert per expired credential, naming the command that renews it. The brief shows one "Sources" line listing what was skipped and why, in place of a skipped line per section. Confirm #176 on the live calendar.
10. **Quarantine you can recover from (L6).** Spec: `specs/2026-10-15-quarantine-in-brief-design.md`. `intake.py --retry` exists; the brief's Blockers section lists each poisoned input with that command, and the brief and debrief read quarantine from one function, so they always agree.
11. **Telemetry escalation (#171).** Build the merged spec. A source with zero activity for 7 days gets one alert asking whether to turn it off (L7).

**Done when:** 5 weekdays of live briefs with no manual connector recovery that went unalerted, and no Work Order blocked at `verify` on an install step.

### Phase 2: one-screen brief and a lean Now page

The brief-one-screen work (#115) set the shape. Live use shows the sections are right and their contents grow without limit. This phase is the first half of simplification step 4.

- **Caps in the prep scripts.** The model gets capped input: "Waiting on" groups by person with at most 5 people and a count of the rest; "Handoffs to chase" drops tickets with no change in 90 days into a monthly line; Active Projects shows the next 3 actions each.
- **Brief assembled from section files.** Each section is a small prompt file the brief includes only when its source is on, which removes the conditional text in `brief.md`.
- **No humanizer in headless runs.** The condensed wording rules in `CLAUDE.md` stay, and the 4,589-word skill is no longer read. Recheck the wording by hand once against the Plan 6 acceptance notes.
- **Yesterday in one paragraph (#179).** The brief links the previous debrief and states where yesterday landed.
- **The Now clock (spec in #187)** plus a line form that holds: one `since` stamp, a 300-character cap, update history moved to the line's evidence note. `now.py review` closes lines whose evidence is a merged PR or a closed issue.
- **Measure:** a test renders the brief from a fixture vault at the live vault's size and fails above 8 KB. Prompt words are counted in CI.

**Done when:** the live brief stays under 8 KB and the Now page under 25 KB for 5 weekdays; the headless brief prompt is under 2,500 words.

### Phase 3: ingest evals

The roadmap puts this before step 3 because step 3 moves ingest's neighbours and any new input source needs a quality baseline. The spec and plan exist (`2026-10-11-ingest-evals.md`); the grill settles 3 runs, the $5 budget and the 0.67 floor. Add one case from L6's poisoned digest (a correction against a long note), so the shrink guard has a regression case.

### Phase 4: simplify step 3, extensions

**Grilled 2026-10-15.** Decisions and the contract are in `specs/2026-10-15-extensions-design.md`. In short:
- Three vendor-specific extensions go to one extensions repository: Jira handoffs, DTCC, and telemetry with RCA (narrowed by the owner, 2026-10-16, spec §7). Meetings, inbox triage, Slack notices, two-machine sync and Work Orders stay in core.
- Jira handoffs move first. The loader merged as #226.
- One `extensions:` list turns them on.
- The "done when" below is revised there: no vendor names in core (the core-clean test), 14 schemas or fewer, a line budget set after the three moves.

The questions the grill answered:

- The `extensions/<name>/` contract: units, scripts, schemas, a brief section file (from phase 2), skills, and an alert tag.
- Order: DTCC (to a private repository), telemetry, Jira handoffs, meetings, then sync. Work Orders stay in core, off by default. Meetings carries the most core code: about 250 lines of meeting import inside `vaultlib/intake.py` and the `telemetry_source` lint rules inside `index.py`.
- **Alert tags (#158)** land with the first extension, since each extension declares its tags. Note tags wait.
- What leaves without a home: the `workcell` and `plan_gate` schemas, the Agent Health metrics and the Fail-Fast Loop Breaker rule, which no script feeds (L7). Either a script writes `system/logs/metrics/` or the rule and its debrief section go.
- The #62 leftovers (the `vault/` move, Nightshift file renames): in or out.

**Done when:** core is under 7,500 lines with no owner-specific code, schemas are at 12 or fewer, and the gate is green with every extension off and with every extension on.

### Phase 5: the intraday picture

L3 is the largest gap between what the owner needs and what the system does: the brief is written at 06:00 and the owner annotates it 11 times by hand. #94 (intraday brief), #135 (server-side channel watch, calendar diff) and the Slack captures are the same need: what changed since this morning. Grill them as one, after phase 4 and with the chat-gateway findings in hand. The specs on `feat/intraday-brief-94` are the starting point.

### Later or parked

- **Plan 5 (preferences):** `preferences_enabled` went on 10-14. Start the grill after a few weeks of real use, around early November.
- **Plan 7 (style lint), Foreman v2, require-plan (#63, #64), #62, #89, #91, #101, #112, #159:** stay parked. Close #63 and #64 if require-plan is dropped.
- **Work Orders on Bitbucket (L5):** only if the owner wants Work Orders on the main work codebase. Needs its own grill.
- **Audit S8 (redaction gaps), S9, S10, C14:** S8 is a short spec (the publish gate's redaction is a safety surface) and fits after phase 1.

## 5. Decisions for the owner

1. ~~Order~~: decided 2026-10-15 (phases 1 and 2 before step 3).
2. ~~Audit S1~~: decided 2026-10-14 (opt-in, no signing until a second user exists).
3. ~~#184~~: merged 2026-10-15.
4. **Side projects in the vault (L9):** register `docs/gmail-cleanup` and similar as codebases with their own repositories, or accept the vault as their home. Recommended: own repositories.
5. ~~Unfed features (L7)~~: decided 2026-10-15 in the extensions grill. Delete the Agent Health section and the metrics writer instruction in phase 4. The Fail-Fast rule had already left `CLAUDE.md`.
6. **The work-data boundary (#28):** all partitions push to one private origin on a personal host. Still undecided; no phase depends on it.
7. **The empty personal partition:** keep investing in partition walls for a partition with no notes, or simplify. Recommended: keep the walls (they are built and tested) and build nothing new for `personal` until it has content.

## 6. Validation bound to each phase

The gate (`system/scripts/verify_setup.sh`: every bats suite and pytest) is green at the end of every task, and CI runs it on every PR. Phase 1 changes to settings or `run_headless.sh` re-run the live acceptance steps (`FOUNDRY.md`, Development). Phase 2 adds the brief-size fixture test and the prompt word count. Phase 3 adds `evals.bats` and `test_eval_check.py`, and records its first real run. Phase 4 adds a gate run with all extensions off and one with all on. Each phase's "done when" line is checked against the live vault's briefs, and the result goes into its outcomes file.
