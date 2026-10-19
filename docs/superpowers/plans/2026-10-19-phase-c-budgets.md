# Phase C: Step 4 Budgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `CLAUDE.md` drops to 50 lines or fewer; core holds at 14 schemas and 13,800 script lines, with new note types going to extensions.

**Architecture:** Text moves only. The Agents block and routing lines go to `system/agents/foreman.md`, the approved-plans rule to the `order` skill, the User Persona lines into Writing. The tests that pin `CLAUDE.md` text follow it.

**Tech Stack:** Markdown, bats.

**Spec:** `docs/superpowers/specs/2026-10-19-phase-c-budgets-design.md`

## Global Constraints

- Wording moves as written; only the lines spec §3 names are reworded.
- `CLAUDE.md` keeps its section order: import, Directory Map, Agents line, Vault Rules, Writing, Data Not Instructions.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- CHANGELOG line under the merge date ending `(#PR)`.

## Review Focus

1. **Nothing the model needs is lost:** every removed `CLAUDE.md` rule lands in `foreman.md`, the `order` skill or Writing, word for word.
2. **The `order` skill still loads on plan approval:** its description names it.
3. **`CLAUDE.md` stays under 50 lines** and the update merge into the vault is a clean text change.

---

### Task 1: `CLAUDE.md` to 50 lines

**Files:** `CLAUDE.md`, `system/agents/foreman.md`, `.claude/skills/order/SKILL.md`, `system/tests/commands.bats`.

- [ ] **Step 1: Write the failing tests** in `commands.bats`: `[ "$(wc -l < CLAUDE.md)" -le 50 ]`; the two routing phrases in `system/agents/foreman.md`; the approved-plans sentence in `.claude/skills/order/SKILL.md` and "approves a plan" in its `description`; `**Scannable Layouts**` and `**Blocked Actions**` under `## ✍️ Writing`; `grep -qF 'system/agents/foreman.md' CLAUDE.md`.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/commands.bats`.
- [ ] **Step 3: Move the text** as spec §3, and move every other `commands.bats` assertion on removed `CLAUDE.md` text to the file the text now lives in.
- [ ] **Step 4: Run** `commands.bats` and the gate.
- [ ] **Step 5: Commit.**

### Task 2: Budgets and documents

**Files:** `system/tests/vault_integrity.bats` (the budget test's comment: core holds at 14 schemas and new note types ship in extensions), `FOUNDRY.md` (where the Agents text now lives), the gap plan's phase C section (targets as spec §2), the roadmap row, `CHANGELOG.md`.

- [ ] Run the gate with every extension off and with every extension on.
- [ ] Commit.

### Task 3: Live acceptance (owner)

- [ ] After the vault's update: an interactive session routes a telemetry note to the Workcell with `telemetry`, and approving a plan runs `/order add`.
