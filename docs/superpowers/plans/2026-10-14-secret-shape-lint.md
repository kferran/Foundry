# Secret-Shape Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `system/scripts/secret_scan.py` reports `secret shape: <path>:<line>: <shape>` over the staged blobs (the pre-commit hook refuses on any) and over the tree (`lint_vault.sh` reports), with the shapes taken from `vaultlib/redact.py` and an SSN shape added there.

**Architecture:** One Python script importing `PATTERNS` and `PEM_BEGIN` from `vaultlib/redact.py`; `--staged` reads `git cat-file blob :<path>`, the default mode reads `git ls-files --cached --others --exclude-standard`. The hook calls it after the drop rewrite; `lint_vault.sh` calls it when not `--staged`. `vaultlib/cli.py` and `index.py` are untouched (another branch changes the `--staged` lint path).

**Tech Stack:** Python 3 standard library, bash, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-14-secret-shape-lint-design.md`

## Global Constraints

- Work on branch `feat/secret-shape-lint` in worktree `.scratch/secrets`. Commit there; do not push or open a pull request.
- Run suites through `system/scripts/test.sh <suite.bats | pytest path>`, outside a sandbox. Never run the gate.
- Bound tools: bats (`scripts.bats`, `meetings.bats`, `sync.bats`, `remote.bats`, `vault_integrity.bats`, `commands.bats`), pytest (`test_redact.py`, `test_meetings.py`, `test_intake*.py`, `test_telemetry_*.py`, `test_commit_runs.py`).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Fixture tokens in new tests are built by concatenation, so the test files hold no literal shape.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- The matched value never appears in any output line.
- Unscanned (empty or unreadable shape list, git failure) exits 2 and the hook refuses; it is never read as clean.
- The hook reads staged blobs: a secret only in the working tree does not block, a staged one fixed on disk still does.
- The scan runs before the hook's lintable-path early exit and after the drop rewrite.
- The SSN shape leaves every existing redaction test green.

---

### Task 1: SSN shape in the shared list

**Files:**
- Modify: `system/scripts/vaultlib/redact.py` (`PATTERNS`, last entry)
- Test: `system/tests/python/test_redact.py` (after `test_known_patterns`)

**Interfaces:** `PATTERNS` gains `("ssn", re.compile(r"\b(?!000|666|9)(?!123-45-6789)\d{3}-\d{2}-\d{4}\b"))`.

- [ ] Write `test_ssn_shape_redacts_and_skips_invalid_areas_and_the_run` `(#166)`: a valid SSN redacts to `[REDACTED:ssn]`; `000-`, `666-`, `9xx-` areas, `123-45-6789` and a date stay.
- [ ] Run it red; add the entry; run `test_redact.py`, `test_meetings.py`, `test_intake*.py`, `test_telemetry_*.py` green; commit.

### Task 2: `secret_scan.py` and the hook

**Files:**
- Create: `system/scripts/secret_scan.py` (executable)
- Modify: `.githooks/pre-commit`, `system/tests/scripts.bats` (setup copies the script; tests after "hook checks the staged content, not the working tree"), `system/tests/vault_integrity.bats` (executable list)

**Interfaces:** `secret_scan.py [--staged]` → stdout lines `secret shape: <path>:<line>: <shape>` or `secret shape: unscanned (<reason>)`; exit 0, 1 or 2.

- [ ] Write the hook tests `(#166)`: a staged token is refused, naming path, line and shape and not the value; a clean commit passes; an unstaged working-tree token does not block; an empty `PATTERNS` refuses as unscanned.
- [ ] Run them red; write the script and the hook call; run `scripts.bats` green; commit.

### Task 3: lint report and the manual

**Files:**
- Modify: `system/scripts/lint_vault.sh`, `system/tests/scripts.bats` (after "lint warns on a client …"), `FOUNDRY.md` (layout line for the hook; the security paragraph)

- [ ] Write `lint reports a secret shape in the tree without failing, and never with --staged (#166)`.
- [ ] Run it red; add the scan to `lint_vault.sh`; run `scripts.bats` green; update `FOUNDRY.md`; run the scanner over the worktree (expect no finding), then `meetings.bats`, `sync.bats`, `remote.bats`, `test_commit_runs.py`, `vault_integrity.bats`, `commands.bats`; commit.
