# Recall Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recall keeps carrying context when the Now page is long: ranked and capped Now lines, a third of the room for digests, and a way to keep Now lines short (#211 items 1 to 4).

**Architecture:** `vaultlib/recall.py` builds the digests first within a third of the room, then the Now block from ranked, capped lines in the rest. `vaultlib/now.py` gains `set_statement` and two review groups; `now.py` gains `set`.

**Tech Stack:** Python 3 stdlib, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-15-recall-ranking-design.md`

## Global Constraints

- Recall never passes its budget (`HARD_CAP` 9500). Line cap 240 characters. Long-line review threshold 240; page size threshold 32 KB.
- `now.py set` keeps kind, who, since, evidence, `[rec::]` and `[due::]`; takes run.lock.
- Settings change (one allow rule) and a SessionStart hook change: feature lane, live acceptance before merge.

## Review Focus

1. A Now line with `[rec::]` and `[due::]` and a long statement: the cut keeps the due field and parenthesis (Task 1 test).
2. A budget too small for the header: recall stays empty, never over budget (existing test).
3. `now.py set --match` matching two lines: exit 2, page unchanged (Task 2 test).
4. A replaced statement that itself holds a `[due::]` field: the line keeps one due field (Task 2 test).
5. A codebase session (partition from its codebase file): ranking applies the same (shared code path).

---

### Task 1: Rank, cap, budget split (`vaultlib/recall.py`, `test_recall.py`) — tests for ranking, cap, the third, Open questions, the "…and N more" line; the old "Now whole first" test updated to the new rule.

### Task 2: `now.py set` and the review groups (`vaultlib/now.py`, `system/scripts/now.py`, `test_now.py`)

- `set_statement(vault, partition, match, statement, today) -> str` (the new line); ValueError on zero or several open matches, on an invalid statement, or a statement holding a clock field.
- `review` gains `long` (open lines over 240 characters) and `page_bytes`; the CLI prints `## Long lines (over 240 characters): rewrite with now.py set` and `## Page size: <n> KB (over 32 KB): close or rewrite lines`.

### Task 3: Documents and the allow rule (`CLAUDE.md` Now rule, `FOUNDRY.md`, `.claude/settings.json`, `commands.bats`, `vault_integrity.bats`)

### Task 4: Gate, review, live acceptance (recall in a throwaway clone with a 95-line seeded Now page and two digests), PR "Part of #211".
