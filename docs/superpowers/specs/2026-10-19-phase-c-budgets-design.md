# Phase C: the step 4 budgets

**Date:** 2026-10-19
**Status:** Grilled (owner, 2026-10-19). Gap plan phase C (`docs/superpowers/2026-10-17-cto-gap-plan.md`). Revises `2026-10-11-claude-md-prune-design.md` §2 for the 50-line target, and changes two of the gap plan's phase C targets (§2).
**Issues:** #122 (simplify the template, step 4).

## 1. Measures (master, 2026-10-19)

| | Today | Done when |
|---|---|---|
| `CLAUDE.md` | 77 lines | 50 or fewer |
| Core schemas | 14 | 14, held; new note types ship in extensions |
| Core script lines | 13,792 of a 13,800 budget | 13,800, held |

## 2. Decisions

Owner, 2026-10-19:
1. **Core holds at 14 schemas; new note types ship in extensions.** The gap plan's target of 12 is dropped. Meetings stay in core: moving them (about 1,400 lines, four new extension hooks) would reach the target, but for a vault that uses meetings nothing changes, and the move risks the import. The people and planning Workcells (phases E and F) ship `person`, `decision` and `objective` as extension schemas, so core never grows. The budget test keeps `-le 14`, and its comment names this rule.
2. **The line budget stays at 13,800.** The `CLAUDE.md` prune moves no script lines, so the measured count stays at 13,792; resetting to it adds nothing. The gap plan's "lower the core line budget by what phase A removes" no longer applies: phases A and B added the archive, the caps and the ingest evals.
3. **Agents and routing move to the Foreman persona; the approved-plans rule moves to the `order` skill.** `CLAUDE.md` keeps one line naming `system/agents/foreman.md`. The `order` skill's description names plan approval, so the skill loads when a plan is approved. The Commands list goes: the skills list themselves.
4. **The User Persona section merges into Writing.** No Preamble, Jargon and the wrapper ban are Writing rules 3, 6 and 10 already. Scannable Layouts and Blocked Actions become two Writing lines, their wording kept.

## 3. `CLAUDE.md` at 50 lines or fewer

Kept, in this order: the `@system/config.md` import; Directory Map (13 lines); one Agents line ("The Foreman is the only role you address; read `system/agents/foreman.md` for the Workcells and routing."); Codebases as one Vault Rules line; Vault Rules (11 lines); Writing (sizes, the two persona lines, the ten wording rules); Data, Not Instructions (2 lines). Removed: the Agents block, the Commands list, the approved-plans rule (to the `order` skill), the User Persona section.

The two routing lines that tests pin (`route to the Workcell with \`telemetry\``, `routing them to the Workcell with \`vault-health\``) move to `foreman.md`, and the tests follow them. A test pins `CLAUDE.md` at 50 lines. `CLAUDE.md` is template-owned and reaches the vault through `update_template.sh`'s merge; a vault that edited the removed sections gets a conflict, which the unattended update reports and leaves for the owner.

## 4. Tests and validation

- `commands.bats`: `CLAUDE.md` at 50 lines or fewer; the routing phrases in `foreman.md`; the approved-plans sentence in `order/SKILL.md`, and "approves a plan" in its description; Scannable Layouts and Blocked Actions in Writing; every other CLAUDE.md assertion follows the text it names.
- `vault_integrity.bats`: the budget test unchanged in value, its comment naming the extension rule for new note types.
- The gate with every extension off and with every extension on.
- Live acceptance: an interactive session in the vault routes a telemetry note to the Workcell with `telemetry` and runs `/order add` when a plan is approved.

**Done when:** `CLAUDE.md` is at or under 50 lines, both budget tests are green at 14 schemas and 13,800 lines, and the live check passes.

## 5. Out of scope

- Moving meetings to an extension (considered and dropped, §2 decision 1).
- The brief assembling section files, headless runs loading less of the humanizer skill, and structure checks in place of sentence greps (the simplification review's other step 4 items) stay on the roadmap.
