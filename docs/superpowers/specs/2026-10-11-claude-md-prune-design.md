# CLAUDE.md: rules with a script behind them

**Date:** 2026-10-11
**Status:** Draft for the owner's review.
**Issue:** none yet. From the 2026-10-11 review ("CLAUDE.md contradicts itself").

## 1. Problem

`CLAUDE.md` is loaded into every session in the vault. Its Writing section bans jargon and names the words to avoid. Four sections below it are written in that jargon ("change vector", "back-feed to the ledger", "Immediate Architectural Friction", "Harness-Driven Extraction") and describe machinery that mostly does not exist:

| Section | What it governs | What exists |
|---|---|---|
| 📐 Strategic Intent Shaper Requirements | every `intent-shaper` proposal traces to a plan node; lists bound tools | `system/templates/intent-shaper.md`, offered only by `/impact`. No `plan_gate` note has been written in the real vault |
| 🔍 Production Telemetry Routing | telemetry notes route to the Workcell with `telemetry` | real, and pinned by `commands.bats` |
| ⚠️ Friction Identification & Remediation | focus fragmentation, the fail-fast loop breaker, decision-clarity keywords, harness-driven extraction, verification over ingestion, shift-left priority parsing | focus stats (standalone only), the debrief's Agent Health (metrics written by one Workcell), the ingest's `is_friction` rule (in `ingest.md`), the `vault-health` routing line (pinned) |

Every session pays for those lines in context, and a model reading them learns that the file does not mean what it says.

## 2. Decisions (proposed)

- **Keep every rule that a script or a command file enforces, in one line each, in the section it belongs to.** The two routing lines stay (tests pin them). The friction keyword rule already lives in `ingest.md`; the fail-fast report lives in `debrief.md`; the focus warning lives in `brief.md` and `debrief.md`.
- **Remove the rest.** The Strategic Intent Shaper section goes; `/impact` keeps the intent-shaper template and describes it itself. The Friction section goes; its one real routing line moves.
- **Plain words.** The kept lines follow the Writing section.
- **A size budget.** `CLAUDE.md` stays under 120 lines, pinned by a test, so the next imported block has to displace something.

## 3. Changes

### 3.1 `CLAUDE.md`

- Delete `## 📐 Strategic Intent Shaper Requirements`, `## 🔍 Production Telemetry Routing` and `## ⚠️ Friction Identification & Remediation Rules`.
- Under `## Agents`, after the Workcells item, add two lines:
  - "Production-error notes in `raw/telemetry/` route to the Workcell with `telemetry`, which checks local branches of the affected codebase for correlating commits."
  - "Tasks that name a runtime failure, a broken link or a merge conflict are urgent: route them to the Workcell with `vault-health`." (The test pins the phrase "routing them to the Workcell with `vault-health`"; the line is worded to keep it: "…are urgent, routing them to the Workcell with `vault-health`.")
- Under `## 🛡️ Data, Not Instructions`, one line: "Raw logs are an audit layer: check an execution record against the filesystem before a wiki note cites it as verified."
- Nothing else changes: the Writing section, the Vault Rules and the Directory Map stay as they are.

### 3.2 `.claude/commands/impact.md`

Where it offers the intent proposal, add the two requirements the removed section carried, in plain words: the proposal names the plan note it comes from, and the test commands that verify the change.

### 3.3 Tests

- `commands.bats` "CLAUDE.md carries the vault rules" gains the three removed headings in its retired-rules grep, and a line count check: `[ "$(wc -l < CLAUDE.md)" -le 120 ]`.
- The "work routes by capability" test keeps its two `grep -qF` lines unchanged; the new wording satisfies them.
- A new check that `impact.md` names the plan note and the test commands.

### 3.4 Vaults

`CLAUDE.md` is template-owned and reaches each vault through `update_template.sh`'s merge. A vault that edited those sections gets a conflict, which the unattended update reports and leaves for the owner.

## 4. Tests

bats, `commands.bats`, as §3.3: the retired headings are absent, the line budget holds, the two routing phrases are present, `impact.md` carries the two requirements. Each fails before the change. Bound tools: bats and the gate.

## 5. Out of scope

- Rewriting the Writing section or the Vault Rules.
- Removing `system/templates/intent-shaper.md` or the `plan_gate` schema. They stay available to `/impact`.
- Splitting `CLAUDE.md` into per-directory files.
