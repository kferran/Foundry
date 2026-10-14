# Transcript Drops Redacted Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The pre-commit hook rewrites a staged meeting transcript drop through the import's full `redact()` (working file and index blob) in place of the `--kinds` refusal, so the blob pushed to `origin` holds nothing the published transcript does not.

**Architecture:** `redact.py --drop` decodes stdin as the import does (`meetings.decode`, today `_decode`) and writes redacted UTF-8; the hook pipes each staged drop blob through it, writes the result to the working file and re-adds it, and refuses a drop the decoder rejects. `named_kinds` and `--kinds` go.

**Tech Stack:** bash, Python 3, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-audit-transcript-drops-pushed-design.md` (audit S6, issue #136)

## Global Constraints

- Work on branch `feat/transcript-drops-redacted` in worktree `.scratch/drops`. Commit there; do not push or open a pull request.
- Run the suites from the worktree root through `system/scripts/test.sh <suite.bats | pytest path> [args…]`. The gate (`verify_setup.sh`) is the main session's.
- Bound tools: pytest (`test_redact.py`, `test_meetings.py`), bats (`meetings.bats`, `scripts.bats`, `commands.bats`), the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- The hook never writes an empty or partial file: the working file is overwritten only after `redact.py --drop` exits 0, and a decode failure refuses the commit with the import's own reason.
- The redacted text goes to the index too (`git add` after the write), so the commit carries it; a blob-only rewrite would leave Obsidian Git re-staging the raw file.
- A UTF-16 drop with no secret still lands as UTF-8 (the rewrite happens on every success; only the message is conditional on the count).
- The default `redact.py` path (surrogateescape round trip for digests) is unchanged: `test_cli_non_utf8_round_trip` feeds bytes starting with a UTF-16 mark.
- `.gitkeep` and files outside `meetings/drop/` are never piped through the redactor.

---

### Task 1: `meetings.decode` and `redact.py --drop`

**Files:**
- Modify: `system/scripts/vaultlib/meetings.py` (`_decode` becomes `decode`), `system/scripts/vaultlib/redact.py` (`named_kinds`, `ASSIGNMENT_EQUALS` removed), `system/scripts/redact.py` (`--drop`)
- Test: `system/tests/python/test_redact.py` (the `--drop` cases beside `test_cli_non_utf8_round_trip`; the four `named_kinds`/`--kinds` cases removed)

**Interfaces:**
- Produces: `meetings.decode(data: bytes) -> str` (same body as `_decode`); `redact.py --drop`: stdin bytes → redacted UTF-8 on stdout, `redactions: N` on stderr, exit 0; a drop `decode` rejects → its `ParseError` text on stderr, exit 1, nothing on stdout.

- [ ] **Step 1: Write the tests:** `test_cli_drop_decodes_as_the_import_does` (spec §4): the same UTF-8 text with a secret, as plain UTF-8, UTF-8 with a byte-order mark and UTF-16 with one, each through `--drop`, all give identical UTF-8 stdout with `[REDACTED:assignment]` and no mark, and `redactions: 1` on stderr; `test_cli_drop_refuses_what_the_import_quarantines`: eight NUL bytes exit 1 with `not UTF-8 text` on stderr and empty stdout. Remove `test_named_kinds_lists_the_named_detectors_that_fire`, `test_named_kinds_ignores_high_entropy_cue_ids`, `test_cli_kinds`, `test_named_kinds_takes_only_the_key_equals_value_form` and the `named_kinds` import (a removal has no red step).
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/python/test_redact.py -k drop`. Expected: FAIL (`--drop` is read as text today: the UTF-16 bytes are not decoded).
- [ ] **Step 3: Implement:** rename `_decode` to `decode` in `meetings.py`; in `redact.py` branch on `sys.argv[1:] == ["--drop"]` before the surrogateescape path, decode with `meetings.decode`, catch `meetings.ParseError`, write `text.encode("utf-8")`; delete `named_kinds` and `ASSIGNMENT_EQUALS` from `vaultlib/redact.py`.
- [ ] **Step 4: Run the suites.** `test_redact.py`, `test_meetings.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(redact): redact.py --drop decodes a transcript drop as the import does`.

### Task 2: The hook rewrites the drop

**Files:**
- Modify: `.githooks/pre-commit`
- Test: `system/tests/meetings.bats` (the three `pre-commit:` cases flip in place)

**Interfaces:**
- Consumes: `redact.py --drop` (Task 1).
- Produces: for each staged `meetings/drop/**` transcript: the working file and the index blob hold the redacted UTF-8 text; stdout `pre-commit: redacted N in <file>` when N is above zero; a decode failure prints `pre-commit: <file>: <reason>; save the transcript as UTF-8 or remove it from meetings/drop/` to stderr and exits 1. The extension refusal and `.gitkeep` acceptance stay.

- [ ] **Step 1: Write the tests** (spec §4): `slides.pdf` is still refused; `call.txt` with an AWS key and `token = hunter2` commits with exit 0, the output names `redacted 2 in meetings/drop/personal/call.txt`, and both the working file and `git cat-file blob HEAD:<file>` read `[REDACTED:aws_key]` and `[REDACTED:assignment]` with the secrets gone; the Teams-style VTT (dated name) commits with its cue ID as `[REDACTED:high_entropy]` and the intake tick then imports it with `Avery Sample` as the attendee; `.gitkeep` commits without a redaction line; a UTF-16 drop with a byte-order mark (`iconv -t UTF-16`) commits as UTF-8 text with its secret redacted and no mark in the blob; eight NUL bytes in `notes.txt` are refused with `not UTF-8 text` and the file still holds its bytes; `password: it expired` commits as `password: [REDACTED:assignment] expired`, `api_key = …` commits redacted.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/meetings.bats -f 'pre-commit'`. Expected: FAIL (the hook refuses the secret cases today).
- [ ] **Step 3: Implement:** replace the `--kinds` block: skip `.gitkeep`; `git cat-file blob ":$f" | python3 redact.py --drop > "$tmp" 2> "$err"` with the exit code captured; on success `cat "$tmp" > "$root/$f"` (keeps the file mode), `git add -- "$root/$f"`, print the count line when above zero; on failure print the reason from `$err`, set `drops=1`.
- [ ] **Step 4: Run the suites.** `meetings.bats`, `scripts.bats` (it copies the hook into a fixture). Expected: PASS.
- [ ] **Step 5: Commit.** `feat(hooks): pre-commit redacts a staged transcript drop in place of refusing it`.

### Task 3: Documents

**Files:**
- Modify: `FOUNDRY.md` (the layout lines for `.githooks/pre-commit` and `meetings/drop/`, the Client paragraph under Machine roles, the Security model's "Data, not instructions" bullet), `docs/superpowers/specs/2026-10-05-meetings-design.md` (§2.2 hook bullet, §6 test sentence, the risk table's secrets row)
- Test: `system/tests/commands.bats` (beside the meetings `/setup` test)

- [ ] **Step 1: Write the test:** `FOUNDRY.md` contains `redacted by the pre-commit hook when it is committed` and the layout line names `redact.py --drop`.
- [ ] **Step 2: Verify it fails.** `system/scripts/test.sh system/tests/commands.bats -f 'meetings'`.
- [ ] **Step 3: Write the sentences;** the meetings spec's three places get a dated note pointing to the audit spec.
- [ ] **Step 4: Run `commands.bats`.**
- [ ] **Step 5: Commit.** `docs(meetings): the hook redacts a committed drop, in the manual and the meetings spec`.
