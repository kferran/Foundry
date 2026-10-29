# Brief live status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The brief never calls a GitHub pull request, issue or Work Order open when it has merged, closed or finished: the prep checks each reference and writes the state inline.

**Architecture:** A new core script, `status_refs.py`, reads the prep inputs the brief copies status from, checks up to 20 references (one `gh api` call each, or the order list), and writes each non-open state inline in place; it prints the Sources line's `status:` counts. `brief_prep.sh` runs it last, and `brief.md` gains one rule.

**Tech Stack:** Python 3.11 standard library, `gh`, bash, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-brief-live-status-design.md` (approved by the owner's merge of #420, 2026-10-29)

## Global Constraints

- The headless brief makes no network call; only the prep calls `gh`.
- `brief.md` stays at most 2,500 words (`prep.bats`); the new rule replaces wording, and the strings `commands.bats` checks stay.
- `brief.md` changes, so the live acceptance steps re-run.
- bats ruling R1.

## Rulings against the spec

- **Ruling 1, only non-open states are written** (spec §3.1 listed `(open)` too): an open reference stays as written, so the inputs carry no `(open)` mark on every Now line with a pull request; the counts still cover every reference checked. Cost if wrong: the brief cannot tell a checked open reference from an unchecked one past the 20th.
- **Ruling 2, a Work Order id is matched only against the order list**: a date followed by a slug (`2026-10-21-notes`) is not an order unless `nightshift.py list --json` names it. Cost if wrong: none found.
- **Ruling 3, the order list is a file**: `brief_prep.sh` writes `orders.json` from `nightshift.py list --json` and passes its path, so the script needs no runner and its tests no queue.

## Review Focus

1. A markdown link `[PR](https://github.com/o/r/pull/1)`: the mark goes after the link's `)`, never inside the URL.
2. A reference repeated in two files: one check, both marked.
3. A `gh` that hangs: the per-call timeout ends it, and the reference reads `(unverified: timeout)`.
4. A merge time in UTC: written in the vault's timezone.
5. A second prep run the same day: the files are rewritten fresh, and an already-marked reference is not marked twice.

---

### Task 1: `status_refs.py`

**Files:** Create `system/scripts/status_refs.py`; Test `system/tests/python/test_status_refs.py`.

**Interfaces:** `status_refs.py <prep dir> <orders.json> [owner/repo…]` exits 0 and prints `status: N checked, M closed, K unverified`; exit 2 on a usage error.

- [ ] **Step 1: Failing tests** (a stub `gh` on `PATH` answering `repos/o/r/issues/N` from fixtures):
  - a merged pull request URL in `yesterday.md` becomes `… (merged 2026-10-21 08:16)` in local time;
  - a closed issue URL becomes `(closed 2026-10-20)`;
  - an open one is left as written and counted;
  - `o/r#3` resolves; a bare `#296` resolves with one repository and reads `(unverified: ambiguous)` with two;
  - a known order id with state `done` becomes `(done)`, and an unknown date-slug is left alone;
  - a `gh` failure reads `(unverified: gh failed)`, and a timeout `(unverified: timeout)`;
  - the 21st reference is left as written;
  - a markdown link is marked after its `)`;
  - an already-marked reference is not marked twice;
  - the printed counts match.
- [ ] **Step 2-4:** Fail, implement, pass.
- [ ] **Step 5:** Commit.

### Task 2: The prep, the brief rule, the timing table

**Files:** Modify `system/scripts/brief_prep.sh` (write `orders.json`, run the script after `away.md`, append its line to `sources.md`), `.claude/commands/brief.md` (the rule, within the cap), `system/tests/conformance.bats` (`status.max`, `status.timeout`, the brief step); Test `system/tests/prep.bats`, `system/tests/commands.bats`.

- [ ] **Step 1: Failing tests:** `prep.bats`, where a stubbed `gh` and a reference in `yesterday.md` give a marked `yesterday.md` and a `status:` line in `sources.md`, and `brief.md` is still at most 2,500 words; `commands.bats`, where `brief.md` names the marks rule.
- [ ] **Step 2-4:** Fail, implement, pass.
- [ ] **Step 5:** Change file, FOUNDRY.md's brief line, the changed suites, the live acceptance re-run, commit, PR.
