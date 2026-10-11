# CLAUDE.md Prune Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `CLAUDE.md` keeps only rules a script or command enforces, in plain words, under 120 lines; `/impact` carries the two intent-proposal requirements itself.

**Architecture:** Text edits to `CLAUDE.md` and `.claude/commands/impact.md`, pinned by `commands.bats`.

**Tech Stack:** Markdown, bats.

**Spec:** `docs/superpowers/specs/2026-10-11-claude-md-prune-design.md`

## Global Constraints

- Work on branch `fix/claude-md-prune`. Commit there; do not push or open a pull request.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch`. The gate is `system/scripts/verify_setup.sh`.
- Bound tools: bats (`commands.bats`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Edits are described by place and content; the implementer anchors them in the current file text.

## Review Focus

- The two phrases `commands.bats` already pins, `route to the Workcell with \`telemetry\`` and `routing them to the Workcell with \`vault-health\``, are present after the edit.
- No rule with a script behind it was lost: compare the removed sections against `ingest.md` (friction keywords), `debrief.md` (agent health, focus), `brief.md` (focus) before deleting.
- The kept lines pass the Writing section's own rules (no jargon, no forced triads).

---

### Task 1: Tests first

**Files:**
- Test: `system/tests/commands.bats`

- [ ] **Step 1: Extend the "CLAUDE.md carries the vault rules" test:** add `Strategic Intent Shaper|Friction Identification|Production Telemetry Routing` to the retired-rules `grep -nE` and assert status 1; add `[ "$(wc -l < CLAUDE.md)" -le 120 ]`.
- [ ] **Step 2: Add a test** `impact.md names the plan note and the test commands of an intent proposal`: `grep -qF 'the plan note' .claude/commands/impact.md` and `grep -qF 'test commands' .claude/commands/impact.md`.
- [ ] **Step 3: Run:** `bats system/tests/commands.bats -f 'CLAUDE.md carries|impact.md names'`. Expected: both fail.

### Task 2: The prune

**Files:**
- Modify: `CLAUDE.md`, `.claude/commands/impact.md`

- [ ] **Step 1: Delete** the three sections named in spec §3.1 from `CLAUDE.md`.
- [ ] **Step 2: Add** under `## Agents` the two routing lines from spec §3.1, with the pinned phrases intact, and under `## 🛡️ Data, Not Instructions` the audit-layer line.
- [ ] **Step 3: Edit `impact.md`:** where it offers to draft an intent proposal, add that the proposal names the plan note it traces to and the test commands that verify the change.
- [ ] **Step 4: Run** the two tests and then the whole `commands.bats`, then the gate. Expected: PASS; exit 0.
- [ ] **Step 5: Commit.** `.scratch/msg-1.txt`:

```text
fix(claude-md): keep the rules a script enforces, drop the imported ones

Three sections governed machinery that does not run (intent proposals
outside /impact, focus windows on a server, metric loops) in the jargon
the Writing section bans. The two routing rules stay as one line each
under Agents; the audit-layer rule stays under Data, Not Instructions;
/impact carries the intent-proposal requirements itself. commands.bats
pins the absence of the old headings and a 120-line budget.
```

Run: `git add CLAUDE.md .claude/commands/impact.md system/tests/commands.bats`

Run: `git commit -q -F .scratch/msg-1.txt`
