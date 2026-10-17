# The Foundry for a busy CTO: completeness and feature assessment

**Date:** 2026-10-17
**Read:** the template at `31edc92` (master, 2026-10-17) (roadmap, next-phase plan of 2026-10-15, specs, plans, `system/`, `extensions/`, `.claude/`), open issues and PRs on `kferran/foundry`, and the live vault snapshot in `porchos/` (last sync 2026-10-15, so live figures are two days old).
**Builds on:** `docs/reviews/2026-10-11-system-assessment.md` (comparison set and scorecard) and `docs/superpowers/2026-10-15-next-phase-plan.md`. This note does not repeat their market comparison.

## 1. Verdict

- **Roadmap:** the build is far ahead of the plan. Every numbered plan except 5, 7 and Foreman v2 is complete, and 10-15/10-16 shipped most of next-phase phase 1, half of phase 2, all three extension moves, chat triage and parallel Work Orders. The roadmap and several spec status lines now lag the code.
- **Simplification program:** step 3 is done and core has a pinned budget (13,200 script lines, 14 schemas). Step 4 is behind: `CLAUDE.md`, schemas and the brief prompt are above target, and the live brief and Now page grew after the targets were set.
- **As a CTO's agent team:** strong on engineering operations (production errors, RCA, Work Orders to PRs, handoffs, DTCC) and on safety. Weak on the parts of the job that are about people and time: no org model or 1:1 prep, no capture channel, no intraday update, no delegation tracking beyond Jira, and a brief too long to read in the five minutes a CTO has.

## 2. Roadmap completeness

| Area | Status (verified) | Evidence |
|---|---|---|
| Plans 0–4b, 6, 8a–e, 9, 10, 11a, 11b | Complete | Plans, outcomes and acceptance files present |
| Nightshift, Foreman v1 (Work Orders) | Complete | `nightshift.py`, `/order` skill |
| DTCC phase 1, Active Projects, Notes to wiki, preference notes | Complete | Code and roadmap rows |
| Now page phase 1, Now clock, recall ranking | Complete | `now.py overdue/set/review`, commits 10-15 (#211) |
| Inbox triage (Gmail) and chat triage (Slack, #222) | Complete | `triage.py`: each tick searches mail and every Slack channel the owner is in; tickets phase not started |
| Parallel Work Orders (#229), release notes in the brief, While you were away | Complete | Commits on 10-16 |
| Slack notices, connector runner, smoke check, usage ceiling | Complete | #125, #144, #146, #134 |
| RCA phase 1 | Complete; phase 2 open (#219) | Now in `extensions/telemetry` |
| Tagging (alert tags and note tags, #158) | **Built 10-15**; roadmap still says "Specs drafted, owner's review" | `alert.py` tags, `vault_index.py tags`, lint rules |
| Connector health (phase 1 item 9) | **Built 10-15**; spec says "Draft" | Commits "every connector failure reason leads with its class", one Sources line |
| Quarantine in brief (item 10) | Shared reader built (`vaultlib/quarantine.py`); spec says "Draft" | Confirm the brief's Blockers line live |
| Telemetry escalation (item 11, #171) | Built; dependency half held (#217) | `telemetry_store.py`, `brief/prep.sh` |
| Yesterday in the brief (#179) | Built | `yesterday.md` prep |
| CLAUDE.md prune (120-line step) | Built 10-15; roadmap says "owner's review" | `CLAUDE.md` is 77 lines |
| Simplify step 3: extensions | **Complete** (roadmap row still says in progress) | `extensions/handoffs`, `extensions/telemetry`; DTCC moved to a vault-only `extensions/dtcc/` (`9e3d45c`); core budget test (`f2a99d7`) |
| Phase 2: brief caps, size test, word count in CI | **Not built** | No caps in prep, no 8 KB fixture test |
| Ingest evals (#218) | **Not built** | No `system/logs/evals/`, no `evals.bats` |
| Simplify step 4 remainder | Not started | `brief.md` 2,478 words (1,682 on 10-11) |
| Slack captures, intraday picture (#135) | Not started | Phase 5, after extensions |
| Research Work Orders (semantic recall, chat gateway) | **Not run** | No `wiki/shared/summaries/*Options.md` in the vault |
| Plan 5 (preferences), Plan 7 (style lint), Foreman v2 | Waiting by design | Roadmap |
| Minutes plugin (12) | In its own repo | Not checked here |
| Require-plan, reorganization (#62) | Parked / closed as won't-do | Roadmap |

**Open PRs needing the owner:** #257 (office/PDF drops to text), #258 (read-denied `wiki/*/private/`), #259 (write-cap ratchet on CLAUDE.md, Now, Index), #262 (transcript copy on PreCompact/SessionEnd). New ideas filed: #236 market watch, #243 and #263 Work Order loops.

### Simplification targets

| Measure | Target | 10-15 | Today |
|---|---|---|---|
| Lines under `system/` (py + sh, no tests) | ~5,500 core (budget now 13,200) | 13,331 | 13,110 (three extensions moved out, new features offset it) |
| Schemas in core | 9 (≤12 after step 3; budget now 14) | 19 | 14 |
| `CLAUDE.md` | ~45 lines | 88 | 77 |
| Headless brief prompt | <2,000 words | ~6,270 | `brief.md` alone 2,478; humanizer no longer referenced by commands |
| Live brief | <8 KB | 31.8 KB | 34.7 KB (10-15) |
| Live Now page | <25 KB | 93.6 KB, 53 open | 101 KB, 88 open lines (10-15) |

The two live numbers moved the wrong way since the plan set them. Phase 2's caps are the only planned fix, and they are the unbuilt part of phase 2.

## 3. Feature richness for a busy CTO

What a CTO's support team does, against what The Foundry has today.

| Job | Foundry today | Rating |
|---|---|---|
| Morning brief | Calendar, Now, alerts, telemetry, handoffs, DTCC, Active Projects, yesterday | Rich content, unreadable size |
| Reach the CTO | Slack notices for brief, debrief, failures, `now` alerts, incidents | Good (one-way) |
| Capture from the CTO on the go | None (Slack captures not built; Notes block only at 05:00) | **Gap** |
| Mail | Gmail triage: threads that need a reply become `owed` lines | Partial (no waiting-on, no drafts) |
| Chat (Slack) | Chat triage: owed lines from every channel the owner is in (#222); no full read of leadership channels (#135) | Partial |
| Meetings | Gemini notes and dropped transcripts to notes, action items, meeting prep from entity notes | Good |
| People and org model | 111 entity notes, used for meeting prep; no people-page contract, owner page, teams, 1:1 history (#112 parked) | **Gap** |
| 1:1 and staff-meeting prep | Meeting prep lists an entity's open Now lines and actions | Thin |
| Delegation and follow-up | Now page `waiting` lines; Jira handoffs untouched 7 days | Partial (nothing for asks made in Slack, mail or meetings outside Jira) |
| Decision log | `decisions` file for system decisions; no CTO decision register | **Gap** |
| Strategy, OKRs, roadmap health | Active Projects lists; no OKR or portfolio roll-up (#112) | **Gap** |
| Engineering health | Sentry/ADX errors, escalation, RCA to Jira, DTCC changes | Strong |
| Delivery (PRs, releases, DORA-style signals) | Debrief lists your PRs and reviews from `gh`; main work codebase is on Bitbucket and not covered | Partial |
| Coding agents | Work Orders: plan to PR unattended, verified, usage ceiling | Strong on GitHub repos; none on the Bitbucket codebase |
| Research | Research Workcell, research Work Orders to findings notes | Good, unused for the two queued briefs |
| Hiring, vendors, budget, board prep | Nothing | **Gap** |
| Knowledge recall | FTS5 keyword index, ranked recall of Now plus 3 digests | Adequate; no semantic search |
| Quality of model output | Not measured (ingest evals not built) | **Gap** |
| Safety and audit | Publish gate, confined connectors, partitions, redaction, run ledger, CI on every PR | Strongest part |

### Agent team shape

Three Workcells (`coding`, `maintenance`, `research`) under the Foreman, dispatched by capability. All three serve the system or the codebase. None serves the CTO's management work: there is no Workcell with capabilities like `people`, `comms` (draft replies, status updates, exec summaries) or `planning` (OKRs, roadmap, board prep). The persona layer is in place; the CTO-facing roles are missing.

## 4. Recommendations, in order

1. **Ship phase 2's caps and the 8 KB brief test** before the DTCC move. The brief and Now page are the main interface and both grew 10% in the last snapshot. Cap "Waiting on" (5 people), handoffs (90-day cutoff) and Active Projects (3 actions); run `now.py review` closures; enforce the 300-character Now line.
2. **Update the roadmap rows that lag the code** (step 3, Tagging, CLAUDE.md prune, chat triage) and the connector health, quarantine and tag spec status lines.
3. **Queue the two research Work Orders now.** They cost no attended time and phase 5 waits on the chat-gateway findings.
4. **Build ingest evals (#218)** before #257 adds four new input formats to intake.
5. **Phase 5 as the first CTO feature:** Slack captures plus the #135 leadership-channel watch and calendar diff, as one grill. This closes the capture gap and the 11-annotations-a-day intraday gap at once.
6. **Then grill #112 as a people Workcell:** a people-page contract (role, team, last 1:1, open asks both ways), 1:1 prep from it, and `waiting` lines sourced from meetings and mail as well as Jira. The 111 entity notes and 100 meeting notes are the input; little new collection is needed.
7. **Defer** market watch (#236), new Work Order loop shapes (#243, #263) and Plan 7. They add surface while the simplification targets are unmet.

## 5. Decisions for the owner

| Decision | Recommendation |
|---|---|
| Phase 2 caps before step 4's remaining budgets | Yes: the live brief is 4x its target |
| Merge order for #257–#262 | #259 (write caps) first; #257 after ingest evals |
| Work Orders on the Bitbucket work codebase | Grill it with #243; today the system's strongest agent cannot reach the CTO's main codebase |
| Empty `personal` partition | Unchanged from 10-15: keep the walls, build nothing new for it |
| Work-data boundary (#218) | Still open; decide before Slack captures bring chat content into the vault |
