# The fast lane: fixes without a spec

**Date:** 2026-10-11
**Status:** Approved by the owner (2026-10-11) with broader criteria: a fix may touch anything except the safety surfaces in §2. A process change, no code.
**Issue:** none yet. Came out of the 2026-10-11 review of the template ("process cost is high for one person").

## 1. Problem

Every change follows brainstorm, grill, spec, plan, three-reviewer check, pull request. Between 2026-09-30 and 2026-10-10 that produced 29 specs, 59 plan files (44 plans and 15 outcome records) and about 110 pull requests. The rigor is what lets a Work Order run unattended from a plan. It costs the same for a one-line fix: the brief listing focus as unavailable every day on a server has waited since the server went live on 2026-10-05 because it has no spec.

The roadmap already has one exception: "Briefing notes and archive: no spec or plan (shipped from an in-chat design)". It happened once and was not written down as a rule.

## 2. Decisions (proposed)

- **Two lanes** (owner, 2026-10-11: "broad, guard safety"). A **fix** is a change whose scope is clear from one sentence and that a failing test can pin, and that touches none of the safety surfaces: permissions and settings files (`.claude/settings.json`, `system/headless.settings.json`, the Work Order settings), the sandbox, the publish gate, redaction, and new note types. A fix that edits the `ingest`, `brief` or `debrief` command text also re-runs the live acceptance steps. Everything else is a **feature** and keeps the full process.
- **A fix needs:** a GitHub issue or a line in a review that states the wrong behaviour, one failing test that passes after the change, the gate green, and a pull request whose body is the issue line and the test name. No spec, no grill, and no plan unless it runs as a Work Order (below).
- **A fix may run as a Work Order.** The readiness check reads the plan from a file committed at the Work Order's base (`nightshift_check._plan_at` runs `git show <base>:<plan>`), so a pull request description cannot be the plan. A fix that runs as a Work Order needs a short plan file with its task list in the `### Task N:` form, committed at that base. The check's rules (no protected branch, no deploy) apply unchanged.
- **Promotion rule.** A fix that grows past its one sentence, or that a reviewer asks a design question about, stops and becomes a feature. The owner decides; the default when in doubt is the feature lane.
- **The roadmap tracks fixes in one row** ("Fixes from live use"), as it does today, by pull request number.

## 3. Changes

- `FOUNDRY.md` Development: a paragraph after the workflow sentence that defines the two lanes, the fix criteria and the promotion rule.
- `docs/superpowers/roadmap.md`: the process paragraph ("A new idea, or a row not yet specified, gets a grilling session…") gains one sentence: a fix as defined in Development skips the grill, the spec and the plan. `FOUNDRY.md` adds that a fix run as a Work Order still carries a short plan file (§2).
- `.github/` has no templates today; none is added. The pull request body convention is text in `FOUNDRY.md`.
- The first fixes through the lane are the small changes inside each step of #122 (simplify the template). The server brief noise needs no fix: the focus tracker's deletion removes it. The `~/.config/foundry/**` deny rule is a settings file change, so it stays in the feature lane.

## 4. Tests

bats, `commands.bats`: `FOUNDRY.md` names both lanes, the fix criteria and the safety surfaces (one `grep -qF` each), and the promotion rule. The roadmap sentence ships with the roadmap update (#121), which owns that file today. Each fails before the change. Bound tools: bats and the gate.

## 5. Out of scope

- A label or a bot that classifies pull requests. The owner classifies.
- Changing how features flow.
