# Always-on agent team: article review against the Foundry

**Date:** 2026-10-29. Template at master.
**Source:** an X post by @sprytixl (status 2107763347097534680), pasted by the owner; the host was not reachable from this session, so the text reviewed is the owner's paste.
**Question (owner):** the article describes what the Foundry is striving for; which of its features could the Foundry use, with the Foreman in place of OpenAI's Dots?

## What the article proposes

An unattended dev team: a Dot (always-on manager on its own cloud computer) watches a project, writes GitHub issues and reports to the owner; Claude Code (Sonnet 5.5 first, Opus 5.5 when stuck) fixes each issue on a branch, tests judge the result, a pull request waits for the owner. It adds a CLAUDE.md rulebook, a scored model router, an attempt ladder (Sonnet, Sonnet, Opus, human), a permission ladder, per-task money and network limits, and a morning report that ends in "Waiting for: your approval".

## What the Foundry already has

| Article piece | Foundry today | Gap |
|---|---|---|
| Dot as manager, the one role you talk to | The Foreman (`system/agents/foreman.md`), the only role the user addresses | The Foreman only queues plans you approved; it does not find work itself |
| "You own this project" job description | Brief, debrief, triage, intraday watch, telemetry fetch all run on timers | Watchers produce Now lines and alerts, not Work Orders |
| `claude -p` worker per task | Work Orders: a confined `claude -p` per item, private clone, sealed verify, branch, pull request (`nightshift_run.py`) | none |
| Tests are the judge | Verify commands run in a sealed sandbox before push; the item never merges or deploys | Nothing reads CI on the pull request after it opens |
| Sonnet does most work | `model` on each Work Order, default `sonnet` (`nightshift_run.py:72`, `:385`) | Chosen once at queue time; no escalation |
| Retry limit | 3 attempts, but only for a session that did not start or a crashed tick (`nightshift_run.py:626`, `:672`) | A failed verify ends the item `blocked` with a Needs-you line; it is never retried with more help |
| Turn and money limits | `--max-turns` 400 / 300 (`nightshift_session.py:9`), a time budget (4h / 1h), the 5-hour usage ceiling `order_max_five_hour` | No per-item cost cap |
| Permission ladder, no secrets, limited network | Session sees eight env vars, denies vault and credential paths, verify is offline, only `order_install` gets network, daily sandbox self-test | Already stricter than the article's |
| Shared memory in GitHub | Queue notes in `raw/<partition>/nightshift/`, run ledger, `Foundry-*` commit trailers, the wiki | none |
| Morning report | 🛠 Work Orders and Needs you in the brief, Slack notices per finished Work Order | none |
| Opus plans, Sonnet types | Design sessions (brainstorm, spec, plan) with the owner, then a Work Order | The split exists only with a human in the design step |

The Foundry covers the article's safety and record-keeping parts more strictly than the article does. The difference is direction: the Dot starts work, while every Foundry Work Order starts from a plan the owner approved.

## Features worth taking

Ranked by value for the stated goal (the brief and Now page alone run the day).

1. **Escalation ladder on a blocked plan item.** When verify fails, requeue the same item once on the same model with the failing check's output appended, then once on `opus` with the diff so far and both failures, then stop with the existing Needs-you line. Touches `nightshift_run.py` (`_deliver_plan` outcome, `attempts`, `model`) and the queue schema. Small; reuses resume and the kept workspace. The article's point that Opus should start from Sonnet's diff and errors maps onto the kept clone and `run.log`.
2. **Pull request CI watch.** After `_deliver` opens a pull request, a later tick reads its checks (`gh pr checks`, already a dependency for the debrief). Red CI becomes one more escalation step (rule 1) or a Needs-you line; green moves the Work Order to "ready for your approval" in the brief and the Slack notice, in the article's report format (tests passed, packages added, migrations touched). Without this, the Foundry's "done" means the sealed verify passed, which can differ from the repo's CI.
3. **Foreman-proposed Work Orders (the Dot's job).** Give the Foreman a standing job in `foreman.md`: at the brief, turn qualifying signals into drafted Work Orders. Candidates are an escalated telemetry group with an `/rca` note, a GitHub issue labelled for the Foundry in a registered codebase, a failed CI run on a default branch. Keep the binding rule that queuing is the owner's approval: a draft becomes a Now line with `[rec::]`, and ticking it queues the order, as `/rca --file` already does for tickets. This is the 3 AM billing-sync scenario with one tick from the owner in place of a merge click.
4. **Scored model choice at queue time.** `/order add` sets `model` from a few plan features (touches a schema or migration, security path, more than one service, an earlier blocked attempt) and prints the reason. Lower value than 1, because Work Orders are already refined plans; the escalation ladder catches most cases the score would.
5. **Per-item cost cap.** The stream already reports usage (`rep.record_usage`). A `cost_cap` per item, checked as the stream arrives, stops a looping session before the time budget does. The 5-hour ceiling protects the account, not a single runaway item.

## Not worth taking

- **Dots or any second vendor's agent as manager.** The Foreman already holds the role, and adding a GPT agent with 4,000 app connectors widens the attack surface the Work Order sandbox was built to close.
- **Managed Agents for 24/7.** The server role and systemd timers already run with the laptop closed. Revisit only if the server goes away.
- **GitHub issues as the only task store.** The Foundry's queue notes carry readiness checks, partition and repo rules that an issue does not; an issue can be an input (item 3), not the queue.
- **The article's CLAUDE.md rules.** Each one already exists in `CLAUDE.md`, the coding Workcell or the Work Order profile ("never merge", "verify before done", "stop and ask" as Needs you).

## Claims to check before building on them

The benchmark table, prices and dates come from the article. The fetch failed, and this review did not check them against Anthropic's or OpenAI's pages. The cost math (80/20 split saving 40%) follows from the stated list prices only.

## Next step

Grill items 1 to 3 (`/grilling`) as roadmap candidates. Item 1 and item 2 are each one spec and one plan; item 3 depends on item 2, so that a proposed order's report can say CI passed.
