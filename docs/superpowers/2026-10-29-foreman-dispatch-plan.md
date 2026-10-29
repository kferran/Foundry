# Foreman dispatch: program plan

**Date:** 2026-10-29
**Source:** `docs/reviews/2026-10-29-always-on-agents-article.md` (items 1 to 3), from an article on always-on agent teams the owner pasted.
**Grill:** 2026-10-29, owner, Q1 to Q36 in [Grill](#grill) below. Each phase's spec names this file in its `**Program:**` line.

## 1. What it is

The Foreman starts work on its own, the way OpenAI's Dots do: each night it turns issues you labelled into planned Work Orders, and one tick from you queues each. Two Work Order changes come first: a blocked plan item retries on a stronger model before it reaches you, and a Work Order is done only when the pull request's CI agrees.

## 2. Phases

| Phase | What ships | Depends on | Spec and plan | State |
|---|---|---|---|---|
| D1 | Escalation ladder: a plan item blocked by `verify` or `no commits` retries on Sonnet with the error, then on Opus, then becomes a Needs-you line | none | to write | grilled |
| D2 | CI watch: a new `checking` state between delivering and done; red CI goes into the D1 ladder | D1 | to write | grilled |
| D3 | Foreman proposals: a nightly `propose` Work Order turns each `foundry:auto` issue into a plan on a proposal branch and a Now line; ticking it queues the Work Order | D1, D2; after the audit track's Work Order findings (#317 to #321) | to write | grilled |

## 3. Order in the roadmap

After the audit track's Work Order findings (#317 to #321), before the small fixes (Q5). #332 (a finished Work Order adds a Now line) folds into D3.

## Grill

Recommendations taken as answered unless a line says otherwise.

### D3: Foreman proposals (Q1 to Q21)

1. **Worth building:** yes, for small fixes whose evidence is already in the vault; not open-ended feature work.
2. **For whom:** the owner only; no one else starts work through the Foreman.
3. **Without it:** acceptable for now, but it is the step between the vault knowing and the work being done that the goal sentence asks for.
4. **Smallest version:** once a day, the Foreman drafts a plan per qualifying signal and adds a Now line with `[rec::]`; ticking the line queues the Work Order. No auto-queue and no continuous watcher until the drafts prove good enough.
5. **Displaces:** placed after #317 to #321 so the fence gaps close first; #332 folds in.
6. **Signals:** GitHub issues with the label, and `/rca` notes (narrowed to issues for v1 by Q10). Red default-branch CI waits for D2; triage and watch lines are too noisy; failed Work Orders belong to D1.
7. **Plan writer:** one confined planning session per signal on Opus, sandboxed like a Work Order; its plan must pass the readiness check before any Now line appears. The Work Order then runs on Sonnet.
8. **Codebases:** the template repository only; the work codebase follows #243's grill.
9. **Cap:** at most 3 proposals a day, none while the 5-hour ceiling holds; a signal with an open proposal, a queued order or an open pull request is skipped; a dropped proposal is never proposed again for the same issue.
10. **RCA signals:** telemetry sources are per registered codebase and the template has none, so v1 takes labelled issues only; RCA proposals come with #243.
11. **Runner:** a new Work Order kind, `propose`, in the existing runner (sandbox, ceiling, 3-slot pool, reports, notices).
12. **Plan location:** the session writes `docs/superpowers/plans/<date>-<slug>.md` in its clone; the runner commits it and pushes `foundry/proposal/<issue>` to `template_remote`; the Work Order uses that branch as `base`, so the pull request shows the plan with the fix.
13. **Issue intake:** a deterministic `gh` script, no model. An issue counts only when the owner's account applied the `foundry:auto` label (read from the issue's events). The issue text reaches the planning session as untrusted data.
14. **Timing:** the fetch runs at 04:00 and the planning sessions run overnight; the brief lists ready proposals under 🛠 Work Orders and adds one Now line each (`[rec:: queue: <reason>]`).
15. **The tick:** `now.py check` sees a ticked proposal line, runs `nightshift.py add` with the stored arguments (model `sonnet`, base the proposal branch, `Fixes #N` in the pull request body) and stamps `_(closed: queued <id> <date>)_`. A drop (`[-]`) deletes nothing and blocks that issue from returning.
16. **Planning failure:** one `[orders]` alert naming the issue and the reason, no Now line; proposed again only after the issue's `updated_at` moves. No comment on the issue in v1.
17. **Planning limits:** `opus`, 1 hour, 200 turns; counts against the daily cap whether it succeeds or not.
18. **Opt-in:** `propose_enabled: "false"` by default, `propose_label: "foundry:auto"`, `propose_max_per_day: 3`; `/setup` asks after Work Orders.
19. **Verify commands:** from the codebase file, never from the planning session.
20. **Learning from drops:** not in v1; revisit when the health scorecard shows the drop rate.
21. **Success (owner: one week, not two):** a live acceptance run on one real labelled issue to a merged pull request, and a health metric (proposals made, queued, dropped, merged). After one week, at least half of proposals are queued and at least half of queued ones merge with no follow-up commit from the owner.

### D1: Escalation ladder (Q22 to Q28)

22. **Validation:** worth building; the owner alone feels it; without it D3 would bring more blocked items; the smallest version is one retry with the error, then one on Opus; it ships before D3.
23. **What escalates:** blocks for `verify` and `no commits`. Not `session` (the owner's questions), `protected` (a fence) or a failed `order_install` (the environment).
24. **The ladder:** Sonnet with the error, then Opus, then the owner. Rungs count apart from the 3 start attempts; the Needs-you line names each rung tried and its last error.
25. **Session:** a fresh session in the kept clone with a handoff: the failing check's last 200 lines, `git diff` against base and the previous session's final message. No resume.
26. **Opus's job:** it fixes the code itself; plan-then-hand-back waits for a measured need.
27. **Budget:** half the item's budget per rung, the same turn limit; the 5-hour ceiling holds a rung as it holds a new start.
28. **Default:** on for every plan item; `/order add --escalate off` opts out.

### D2: CI watch (Q29 to Q36)

29. **Validation:** worth building; "done" today means the sealed verify passed, which can differ from the repository's CI; the owner alone feels it; D1 and D3 need it; order D1, D2, D3.
30. **Reading CI:** each nightshift tick, for each plan item with an open pull request, `gh pr checks --json` on its head commit, no model; stops once every check has finished.
31. **State:** a new state, `checking`, between `delivering` and `done`. It counts as open in reports and `/order status` and holds no running slot; `now.py check` closes a line on `done`, which now means CI agreed.
32. **Red CI:** goes into the D1 ladder: a fresh session on the same branch with the failed job's log (`gh run view --log-failed`, last 200 lines, redacted, untrusted data) as the handoff, pushing to the same pull request. Past the ladder, the Needs-you line names the check and links the run.
33. **Red on base too:** no escalation; the tick reads the same check on the base branch's latest commit, and when it is red there the Needs-you line says `<check> is red on <base> too` and the item ends `done` with a note.
34. **Which checks:** the required checks (`gh pr checks --required`) when branch protection names any, else every check on the head commit.
35. **No CI or stuck CI:** no check within 30 minutes of the push ends `done` with "no CI"; a check pending after 6 hours ends `done` with "CI stalled" and one `[orders]` alert.
36. **Green report:** `PR #N ready: <n> of <n> checks green, <files> files changed, lockfile <changed|unchanged>`, plus the ladder rungs used. Migration detection waits for a codebase key. One Slack notice on green and one on the final red.
