# Secret-shape lint: a tree report and a commit that refuses

**Date:** 2026-10-14
**Status:** Draft for the owner's review.
**Issue:** #166, line "Secret-shape lint over the tree, and a commit that refuses over it".

## 1. Problem

`system/scripts/vaultlib/redact.py` holds the credential shapes that redact digests, inbox copies and transcript drops. Nothing scans the tree with them, so a token pasted into a wiki note, a briefing or any other tracked file commits and is pushed as typed.

## 2. Decisions

- **One shape list.** A new script, `system/scripts/secret_scan.py`, imports `PATTERNS` and `PEM_BEGIN` from `vaultlib/redact.py` and reports a `PEM_BEGIN` match as `pem`. There is no copy of a pattern anywhere else. `ASSIGNMENT`, `BEARER` and the high-entropy guess stay redaction-only: they match prose ("password: see the manual", "the bearer of bad news") and long identifiers, so they would refuse ordinary commits.
- **Output.** One line per match: `secret shape: <path>:<line>: <shape name>`. The matched text is never printed, so the line is safe in a terminal, a hook refusal and the `[commit_runs]` alert that carries it.
- **Exit codes.** 0 clean, 1 findings, 2 unscanned. Unscanned means the shape list could not be read (the import fails) or is empty, or git could not list or read the files; the script prints `secret shape: unscanned (<reason>)`. Unscanned is never read as clean.
- **Two modes.**
  - `secret_scan.py --staged` reads the staged blobs (`git cat-file blob :<path>`) of every added, copied, modified or renamed path, so a secret fixed on disk but still staged is refused, and one only in the working tree is not.
  - `secret_scan.py` with no argument reads the working copy of every tracked and untracked file (`git ls-files --cached --others --exclude-standard`); gitignored paths (`raw/` contents, `wiki/.staging/`, `system/index.db`) are not listed.
- **Skipped.** `.scratch/` and binary files (a NUL byte in the first 8 KiB, git's own test) in both modes. The tree report also skips the template's own test and design material, `system/tests/` and `docs/superpowers/`, which hold fake tokens by design (fixtures of the redaction tests) and would otherwise be reported in every vault on every lint. The hook still scans a staged file there: a token pasted into `docs/` is refused, and a hand-resolved template update conflict that stages those fixtures needs `--no-verify`. Text is decoded as UTF-8 with `surrogateescape`, as `redact.py` decodes it.
- **Pre-commit hook.** `.githooks/pre-commit` runs `secret_scan.py --staged` after the transcript-drop rewrite (so a drop is scanned as its redacted text) and before the lintable-path check (so a secret in any staged file refuses, not only in a lintable note). Any non-zero exit refuses the commit: the scanner's lines, then `pre-commit: a staged file holds a secret shape; remove it, or commit with --no-verify if it is not a secret`. A missing scanner refuses too.
- **Lint.** `lint_vault.sh` runs the tree scan before the index issues and prints its lines as a report; findings do not change its exit status (a fixture or a documented example is the owner's call). An unscanned result exits 2. `lint_vault.sh --staged` (what the hook ran before this change) does not scan: the hook already has.
- **Escape hatch.** None beyond `git commit --no-verify`. Obsidian mobile runs no hooks, so a secret committed from a phone is found only by the next `/lint`.
- **SSN shape.** `PATTERNS` gains `ssn`: `\b(?!000|666|9)(?!123-45-6789)\d{3}-\d{2}-\d{4}\b` (no 000, 666 or 9xx area number, and not the 123-45-6789 run). Because the list is shared, digests, inbox copies, drops and telemetry text redact it as `[REDACTED:ssn]` too; it is added only with the redaction tests passing.

## 3. Tests (cite `(#166)`)

- `scripts.bats`, beside the hook tests: a staged note with a token shape is refused and the output names path, line and shape but not the value; a clean commit passes; a working-tree secret that is not staged does not block the commit; the lint report lists it; an empty shape list refuses the commit as unscanned.
- `test_redact.py`: the SSN shape redacts and its excluded forms do not.

## 4. Out of scope

A per-file allow-list or inline marker; scanning history; the assignment and high-entropy shapes in the scan.
