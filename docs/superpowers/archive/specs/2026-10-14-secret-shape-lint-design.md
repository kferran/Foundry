# Secret-shape lint: a tree report and a commit that refuses

**Date:** 2026-10-14
**Status:** Draft for the owner's review.
**Issue:** #166, line "Secret-shape lint over the tree, and a commit that refuses over it".

## 1. Problem

`system/scripts/vaultlib/redact.py` holds the credential shapes that redact digests, inbox copies and transcript drops. Nothing scans the tree with them, so a token pasted into a wiki note, a briefing or any other tracked file commits and is pushed as typed.

## 2. Decisions

- **One shape list.** A new script, `system/scripts/secret_scan.py`, imports `PATTERNS` and `PEM_BEGIN` from `vaultlib/redact.py` and reports a `PEM_BEGIN` match as `pem`. There is no copy of a pattern anywhere else. `ASSIGNMENT`, `BEARER` and the high-entropy guess stay redaction-only: they match prose ("password: see the manual", "the bearer of bad news") and long identifiers, so they would refuse ordinary commits.
- **Output.** One line per match: `secret shape: <path>:<line>: <shape name>`, the path JSON-quoted when it holds a newline. The matched text is never printed, so the line is safe in a terminal, a hook refusal and the `[sync]`, `[update]` and `[commit_runs]` alerts that carry it.
- **Exit codes.** 0 clean, 1 findings, 2 unscanned. Unscanned means the shape list could not be read (the import fails) or is empty, or git could not list or read the files; the script prints `secret shape: unscanned (<reason>)`. Unscanned is never read as clean.
- **Two modes.**
  - `secret_scan.py --staged` reads only the lines a commit adds. The entries come from `git diff --cached --raw -z -M --diff-filter=ACMRT` (added, copied, modified, renamed, type-changed), the blobs from one `git cat-file --batch`. A line of the staged blob counts as old when the HEAD blob holds it or, during a merge, the `MERGE_HEAD` blob holds it; every other line is scanned. So a move, a rename or an archive of old text commits, a hand-resolved template update commits the fixtures it brings, a token typed during the resolution is refused, a secret fixed on disk but still staged is refused, and one only in the working tree is not.
  - `secret_scan.py` with no argument reads the working copy of every tracked and untracked file (`git ls-files --cached --others --exclude-standard`); gitignored paths (`raw/` contents, `wiki/.staging/`, `system/index.db`) are not listed.
- **Skipped.** `.scratch/`, binary files (a NUL byte in the first 8 KiB, git's own test) and nested repositories (mode 160000, which have no blob) in both modes. A file starting with a UTF-16 byte-order mark is read as UTF-16 text, as the drop import reads it; other text as UTF-8 with `surrogateescape`, as `redact.py` decodes it. The tree report also skips the template's own test and design material, `system/tests/` and `docs/superpowers/`, which hold fake tokens by design (fixtures of the redaction tests) and would otherwise be reported in every vault on every lint. The hook still scans a staged file there, so a token pasted into `docs/` is refused.
- **Pre-commit hook.** `.githooks/pre-commit` runs `secret_scan.py --staged` after the transcript-drop rewrite (so a drop is scanned as its redacted text) and before the lintable-path check (so a secret in any staged file refuses, not only in a lintable note). Any non-zero exit refuses the commit. The first line is the refusal, `pre-commit: a staged file adds a secret shape; remove it, or commit with --no-verify if it is not a secret` (or `pre-commit: the secret scan could not run, so nothing was committed`), then the scanner's lines, then any drop's `redacted N` line; the first line is what a sync or update alert quotes. A missing scanner refuses too.
- **Unattended commits.** `git_sync_commit` (`lib_git.sh`), shared by the sync and the daily template update, runs the staged scan after `git add -A` and leaves each path with a finding out of the commit, with the literal-exclude pathspec it already uses for refused runs (audit C7); the rest commits. The sync then fetches, merges and pushes as usual and raises one `[sync]` alert a day per path: `left out of the sync commit: secret shape: <path>:<line>: <shape>`. The update leaves the path uncommitted and fetches and merges as usual, as it does for a refused run (owner decision, #136 2026-10-15), and its `[update]` line names the scanner lines beside the commits and the merge result. An unscanned result is left to the hook, which refuses the commit as before. An interactive commit still refuses.
- **Merged-in content.** A clean `git merge` runs `pre-merge-commit`, not `pre-commit`, and the template ships no `pre-merge-commit` hook, so content merged from a machine that skipped the hook (Obsidian mobile, `--no-verify`) arrives unscanned. The tree report in `/lint` is what catches it.
- **Lint.** `lint_vault.sh` runs the tree scan before the index issues and prints its lines as a report; findings do not change its exit status (a fixture or a documented example is the owner's call). An unscanned result exits 2. `lint_vault.sh --staged` (what the hook ran before this change) does not scan: the hook already has. `/lint` lists the `secret shape:` lines first, as errors.
- **Escape hatch.** None beyond `git commit --no-verify`. Obsidian mobile runs no hooks, so a secret committed from a phone is found only by the next `/lint`.
- **SSN shape.** `PATTERNS` gains `ssn`, ASCII digits only (`re.ASCII`): `(?<![\d-])(?!000|666|9)(?!123-45-6789)(?!\d{3}-00-)(?!\d{3}-\d{2}-0000)\d{3}-\d{2}-\d{4}(?![\d-])`. That excludes a 000, 666 or 9xx area, a 00 group, a 0000 serial, the 123-45-6789 run, and a match inside a longer hyphen chain (a work-order number, a phone number, an ISBN). Because the list is shared, digests, inbox copies, drops and telemetry text redact it as `[REDACTED:ssn]` too; it is added only with the redaction tests passing.

## 3. Tests (cite `(#166)`)

- `scripts.bats`, beside the hook tests: a staged token is refused, the refusal first, naming path, line and shape but not the value; only added lines are scanned (a move keeps old text, a new line is refused); a hand-resolved merge commits fixture tokens and refuses one typed during the resolution; a nested repository is skipped, a symlink turned file and a UTF-16 file are scanned; a newline path is quoted; a clean commit passes and a working-tree secret does not block it; an empty or unreadable shape list or a missing scanner refuses as unscanned; the lint report lists a tree secret and skips the fixture folders.
- `meetings.bats`: the refusal comes before a drop's `redacted` line.
- `sync.bats`: a file that adds a shape is left out of the sync commit, alerted once a day, and the cycle goes on. `remote.bats`: the unattended update leaves it uncommitted, merges and names it without the value.
- `test_redact.py`: the SSN shape redacts and its excluded forms do not.
- `commands.bats`: `/lint` lists `secret shape:` lines first; the manual describes the hook and the sync behaviour.

## 4. Out of scope

A per-file allow-list or inline marker; scanning history; the assignment and high-entropy shapes in the scan.
