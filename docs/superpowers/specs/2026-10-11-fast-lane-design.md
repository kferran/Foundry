# The fast lane: fixes without a spec

**Date:** 2026-10-11
**Status:** Draft for the owner's review. A process change, no code.
**Issue:** none yet. Came out of the 2026-10-11 review of the template ("process cost is high for one person").

## 1. Problem

Every change follows brainstorm, grill, spec, plan, three-reviewer check, pull request. Between 2026-09-30 and 2026-10-10 that produced 28 specs, 55 plans and about 110 pull requests. The rigor is what lets a Work Order run unattended from a plan. It costs the same for a one-line fix: the brief listing focus as unavailable every day on a server has waited since the server went live on 2026-10-05 because it has no spec.

The roadmap already has one exception: "Briefing notes and archive: no spec or plan (shipped from an in-chat design)". It happened once and was not written down as a rule.

## 2. Decisions (proposed)

- **Two lanes.** A **fix** is a change whose scope is clear from one sentence, that touches no schema, no settings file, no unit template and no headless command text, and that a failing test can pin. Everything else is a **feature** and keeps the full process.
- **A fix needs:** a GitHub issue or a line in a review that states the wrong behaviour, one failing test that passes after the change, the gate green, and a pull request whose body is the issue line and the test name. No spec, no plan, no grill.
- **A fix may run as a Work Order.** The Work Order's plan is the pull request description's task list, written in the `### Task N:` form the readiness check reads. The check's rules (no protected branch, no deploy) apply unchanged.
- **Promotion rule.** A fix that grows past its one sentence, or that a reviewer asks a design question about, stops and becomes a feature. The owner decides; the default when in doubt is the feature lane.
- **The roadmap tracks fixes in one row** ("Fixes from live use"), as it does today, by pull request number.

## 3. Changes

- `FOUNDRY.md` Development: a paragraph after the workflow sentence that defines the two lanes, the fix criteria and the promotion rule.
- `docs/superpowers/roadmap.md`: the process paragraph ("A new idea, or a row not yet specified, gets a grilling session…") gains one sentence: a fix as defined in Development skips the grill, the spec and the plan.
- `.github/` has no templates today; none is added. The pull request body convention is text in `FOUNDRY.md`.
- The first fixes through the lane: the server brief noise (`2026-10-11-server-brief-noise-design.md` is written as the one-page record it needs, no plan), and the `~/.config/foundry/**` deny rule when the Slack bridge does not ship first.

## 4. Tests

bats, `commands.bats`: `FOUNDRY.md` names both lanes and the four fix criteria (one `grep -qF` per criterion), and the roadmap's process paragraph names the fast lane. Each fails before the change. Bound tools: bats and the gate.

## 5. Out of scope

- A label or a bot that classifies pull requests. The owner classifies.
- Changing how features flow.
