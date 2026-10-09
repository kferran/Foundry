# Protected-File Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plan Work Order that edits `.claude/` delivers those files: the session writes them to a path it is allowed to write (#92).

**Architecture:** The plan prompt names `.nightshift/protected/claude/<path under .claude/>` (no `.claude` segment), and `nightshift_deliver.protected_files` reads `claude/<path>` as `.claude/<path>` before its existing checks. The old `.claude/` form is still read.

**Tech Stack:** Python 3 (`vaultlib`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-protected-path-design.md`

## Global Constraints

- Work on branch `fix/protected-path`. Commit there; do not push or open a pull request.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once), outside a sandbox (the end-to-end test needs `bwrap`). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_session.py`, `test_nightshift_run.py`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- A proposal under `claude/` goes through the same folder, symlink and size checks as one under `.claude/`: `claude/settings.json` is refused.
- An order queued before the update, whose session wrote the old `.claude/` form, still delivers: `test_protected_files_are_committed_by_the_runner` keeps that form.
- The prompt never names a path with a `.claude` segment for the session to write.

---

### Task 1: The protected-file path without a .claude segment

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_deliver.py`, `system/scripts/vaultlib/nightshift_session.py`
- Test: `system/tests/python/test_nightshift_deliver.py`, `system/tests/python/test_nightshift_session.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `protected_files(clone)` returns `.claude/<path>` for a proposal at `.nightshift/protected/claude/<path>`; the plan prompt names that path.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/python/test_nightshift_deliver.py`. Find:

````text
    assert files == [] and len(problems) == 3


````

Replace with:

````text
    assert files == [] and len(problems) == 3


def test_protected_files_under_claude_without_the_dot_land_in_dot_claude(tmp_path):
    clone = tmp_path / "c"   # a session cannot write a path with a .claude segment (#92)
    _protected(clone, "claude/commands/x.md", "x")
    _protected(clone, "claude/settings.json", "{}")
    files, problems = nd.protected_files(clone)
    assert files == [(".claude/commands/x.md", b"x")]
    assert problems == [".claude/settings.json: only .claude/skills/, .claude/commands/, .claude/agents/ may be proposed"]


````


Edit 1 in `system/tests/python/test_nightshift_session.py`. Find:

````text
    assert ".nightshift/protected/" in ss.plan_prompt({"plan": "docs/p.md", "tasks": "1-2"})
````

Replace with:

````text
    p = ss.plan_prompt({"plan": "docs/p.md", "tasks": "1-2"})
    assert ".nightshift/protected/claude/<path under .claude/>" in p   # no .claude segment: a session can write it (#92)
    assert ".nightshift/protected/.claude" not in p
````


Edit 1 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    writes.write_text(f"done.txt=yes\n.nightshift/protected/.claude/skills/demo/SKILL.md=hello\\n\n"
````

Replace with:

````text
    writes.write_text(f"done.txt=yes\n.nightshift/protected/claude/skills/demo/SKILL.md=hello\\n\n"
````


- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_session.py system/tests/python/test_nightshift_run.py`
Expected: FAIL, 3 failed.

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
    Returns ([(path, bytes)], [problem]); only regular files under PROTECTED_DIRS are accepted."""
````

Replace with:

````text
    Returns ([(path, bytes)], [problem]); only regular files under PROTECTED_DIRS are accepted. A session cannot
    write a path with a .claude segment either, so it proposes claude/<path>, read as .claude/<path> (#92)."""
````

Edit 2 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
        rel = p.relative_to(root).as_posix()
````

Replace with:

````text
        rel = p.relative_to(root).as_posix()
        rel = "." + rel if rel.startswith("claude/") else rel
````


Edit 1 in `system/scripts/vaultlib/nightshift_session.py`. Find:

````text
            "You cannot write under .claude/: for a file the plan puts in .claude/skills/, .claude/commands/ or "
            ".claude/agents/, write its full content to .nightshift/protected/<that same path> instead; the runner "
            "adds it to the branch. "
````

Replace with:

````text
            "You cannot write under .claude/, nor any path with a .claude folder in it: for a file the plan puts in "
            ".claude/skills/, .claude/commands/ or .claude/agents/, write its full content to "
            ".nightshift/protected/claude/<path under .claude/> instead (no leading dot, for example "
            ".nightshift/protected/claude/commands/brief.md); the runner adds it to the branch as .claude/<path>. "
````


- [ ] **Step 4: Run the tests and the gate**

Run: the command from Step 2.
Expected: PASS, 0 failed.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(orders): a protected-file path the session can write (#92)

A restricted plan session refuses file-tool writes to any path with a
.claude segment, including the old fallback
.nightshift/protected/.claude/<path>, so a plan that edits .claude/
failed with "no result". The prompt now names
.nightshift/protected/claude/<path under .claude/>, and protected_files
reads it as .claude/<path> through the same checks. Proposals under
the old form are still read.

Closes #92
```

Run: `git add system/scripts/vaultlib/nightshift_deliver.py system/scripts/vaultlib/nightshift_session.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_session.py system/tests/python/test_nightshift_run.py`

Run: `git commit -q -F .scratch/msg-1.txt`
