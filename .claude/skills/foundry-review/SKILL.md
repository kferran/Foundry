---
name: foundry-review
description: |
  Use when a branch is ready for its pull request, after superpowers:requesting-code-review and its fixes, and before
  gh pr create; also when reviewing a Work Order's pull request branch. Use for /foundry-review.
---
# Foundry review

Spec: `docs/superpowers/specs/2026-10-23-factory-f4-line-skills-design.md` §3.3. The script runs nine checks for past defect classes that tests miss. Its hits are candidates for you to read. It never gates CI.

**1. Run it** from the root of the repository under review, on the branch:

```sh
python3 .claude/skills/foundry-review/review_diff.py [--base <ref>]
```

It reads the lines the branch adds since its merge base with `--base` (default `origin/master`, else `master`). It prints `<check>: <path>:<line>: <text>` per hit, then `<check>: pass` for each check with none. Exit 0 no hits, 1 hits, 2 could not run (no git, an unknown base): on 2, fix the cause and run it again.

**2. Settle each hit.** Read the hunk around it, then fix the line or keep it with a one-line reason. Commit a fix before running the script again: it reads HEAD only.
- A `fix/` branch always exits 1 with a `changelog-label` line asking for its `defect:` label (the script never reads PR labels). Keep that line, and put the label on `gh pr create --label`.
- A hit in a test file that seeds a check (a test of the checks themselves, or a fixture holding the bad shape on purpose) is expected noise: keep it with that reason.

**3. Read past the checks.** They are regexes and a floor: a writer called through a helper, or a path built across lines, passes them. Read every hunk that adds a Now or Slack writer, an alert line or a test, whatever the script printed.

| Check | Class | Flags |
|---|---|---|
| `now-redaction` | C7 | a Slack writer in a file that calls neither `redact_credentials(` nor `redact(` (every Now write redacts inside `now.py`) |
| `gate-escape` | C14 | a write on a line naming `wiki/` or `briefings/` outside the publish gate and `now.py`; an `Edit(`/`Write(` allow rule on those paths |
| `alert-text` | C5, C7 | an alert or failure reason that interpolates a value other than an exit code, a count or a reason variable |
| `sleep-race` | C6, C10 | `sleep` added in a test file, except a stub's `STUB_SLEEP=` knob |
| `skip-reason` | C10 | a bats `skip` or a pytest skip with no reason |
| `changelog-label` | C13, C12 | a vault-visible path changed with no `- … (#N)` line in `CHANGELOG.md` (skipped in a vault); any `fix/` branch |
| `read-source-check` | C4 | a new script that calls `connector_run` and accepts no `--check` |
| `computed-session` | C4 | `-p` or `--print` passed to a command named by a variable, outside the three runners |
| `computed-config` | part home | a `.py` line that builds a `config.md` path from parts, outside `vaultlib/config.py` |

**4. Write the PR body's `## Foundry review` section**, one line per check in the order above: `pass`, `fixed: <path:line>` or `kept: <path:line>: <reason>`.

**5. A fix branch** passes its one `defect:<class>` label (FOUNDRY.md, Two lanes) to `gh pr create --label`.

**Work Order pull requests:** the runner does not run this skill. Whoever reviews a Work Order's pull request runs it on that branch.
