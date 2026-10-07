# Fresh-Template Lint Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A freshly set-up vault lints with no warnings the user cannot act on (issue #19 on `kferran/jarvis`).

**Architecture:**
- `links.Resolver` also records every directory that holds a walked file, so a Markdown link to a folder (`docs/superpowers/specs/`) resolves. Only Markdown links change; wikilinks stay file-only.
- `schema.validate_note` skips `path` fields in a file named `example.md` (the shipped `system/codebases/example.md`), the same convention `index.py`, `telemetry.py`, `scope.py` and `lib_config.sh` already use for examples.
- `/setup` phase 9 links each onboarding note from its codebase file (`system/codebases/<name>.md`: indexed, and tracked in the vault, never in the template, per README "Security model"). `wiki/Index.md` is template-owned, so editing it per vault would conflict on every `update_template.sh`.

**Tech Stack:** Python 3.11, SQLite FTS5 index, bats 1.8.

**Spec:** issue #19 (`gh issue view 19 --repo kferran/jarvis`) and the triage `docs/superpowers/plans/2026-10-07-template-issue-triage.md`. Main spec `docs/superpowers/specs/2026-09-30-vault-template-design.md` §6.8 (lint) and §11 (setup phase 9).

## Global Constraints

- **Where:** a worktree of the template repository on its own branch, for example `git -C ~/Foundry fetch -q template && git -C ~/Foundry worktree add ~/Foundry-worktrees/lint-fixes -b fix/fresh-lint template/master`. Never on a vault's `master`; never push or merge from the plan.
- **No `system/config.md`** in the worktree. `system/index.db` is gitignored; rebuilding it in the worktree is fine.
- **Tool floor:** bats 1.8, Python 3.11, SQLite 3.40.
- **Verify (no network, sandbox-safe):** `python3 -m pytest system/tests/python -q` and `bats system/tests/commands.bats system/tests/vault_integrity.bats`.
- **Edits:** each "replace" block quotes the current text exactly and must match once; if not, stop and compare with `template/master` at fb81fca.

## Review Focus

1. **A link to a folder that holds no file (or only dotfiles).** Expected: still a dead link; the walk skips dotfiles, so `.gitkeep` alone does not make a folder resolvable. Pinned by Task 1 (`docs/superpowers/spikes/` with no file, `docs/nothing/`).
2. **A wikilink written as a folder (`[[docs/specs/]]`).** Expected: unchanged (dead); only Markdown links resolve to folders. No test: the `wiki` branch of `Resolver.resolve` is untouched.
3. **A user's own codebase file whose `path` is missing.** Expected: still a warning. Pinned by Task 2 (`things/mine.md`).
4. **A wiki note linking `[x](../../personal/)` from `wiki/work/`.** Expected: now resolves to the folder and the partition wall reports it as an error, as it would for a note there. No test; it follows from `wall_blocked` on the folder's partition.
5. **Re-running `/setup` phase 9.** Expected: the `Onboarding:` line is added once per codebase ("for each registered codebase without one"). Prompt-level; pinned only by Task 3's wording test.

---

### Task 1: Markdown links to folders resolve

**Files:**
- Modify: `system/scripts/vaultlib/links.py:64-82`
- Test: `system/tests/python/test_links.py`, `system/tests/python/test_index_rules.py`

**Interfaces:**
- Produces: `Resolver.dirs: dict[str, str]` (lowercased folder path to its spelling). `Resolver.resolve(target, src, "md", prefer)` returns a folder path (no trailing slash) when no file matches and the folder holds a file. `links.target_path` can now hold a folder; nothing joins it to `notes`.

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/python/test_links.py`:

```python


def test_markdown_link_to_a_folder_resolves_when_the_folder_holds_a_file():
    r = links.Resolver(["docs/superpowers/specs/a.md"])
    assert r.resolve("docs/superpowers/specs/", "README.md", "md", prefer_none) == ("docs/superpowers/specs", False)
    assert r.resolve("docs/", "README.md", "md", prefer_none)[0] == "docs"
    assert r.resolve("docs/superpowers/spikes/", "README.md", "md", prefer_none)[0] is None
```

Append to `system/tests/python/test_index_rules.py`:

```python


def test_a_markdown_link_to_a_folder_is_not_dead(vault):
    write(vault, "README.md", "Specs in [specs](docs/specs/), none in [x](docs/nothing/).\n")
    write(vault, "docs/specs/a.md", "# A\n")
    assert issue_messages(build(vault), "dead-link") == [
        ("README.md", "warning", "dead-link", "dead link docs/nothing/")]
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python3 -m pytest system/tests/python/test_links.py system/tests/python/test_index_rules.py -q`
Expected: 2 failed (`(None, False) == ('docs/superpowers/specs', False)`; two dead links instead of one).

- [ ] **Step 3: Record folders.** In `system/scripts/vaultlib/links.py`, replace:

```python
            if base.endswith(".md"):
                self.by_name.setdefault(base[:-3], []).append(path)
```

with:

```python
            if base.endswith(".md"):
                self.by_name.setdefault(base[:-3], []).append(path)
        # Every directory that holds a file, so a Markdown link to a folder ("docs/specs/") resolves (#19).
        self.dirs = {}
        for path in files:
            d = posixpath.dirname(path)
            while d and d.lower() not in self.dirs:
                self.dirs[d.lower()] = d
                d = posixpath.dirname(d)
```

Replace:

```python
            return self.by_lower.get(joined.lower()), False
```

with:

```python
            return self.by_lower.get(joined.lower()) or self.dirs.get(joined.lower()), False
```

- [ ] **Step 4: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_links.py system/tests/python/test_index_rules.py -q`
Expected: all passed.

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/vaultlib/links.py system/tests/python/test_links.py system/tests/python/test_index_rules.py
git commit -m "fix(lint): resolve Markdown links to folders that hold files (#19)"
```

---

### Task 2: the shipped example codebase skips the path check

**Files:**
- Modify: `system/scripts/vaultlib/schema.py:289-290` (in `validate_note`)
- Test: `system/tests/python/test_schema.py`

**Interfaces:** none (behavior of `validate_note` for files named `example.md`).

- [ ] **Step 1: Write the failing test.** In `system/tests/python/test_schema.py`, insert before `def test_unknown_field_warns(schemas):`:

```python
def test_a_shipped_example_skips_the_path_check(schemas):
    _, issues = check(schemas, "things/example.md", "type: thing\nname: A\nwhere: /no/such/path")
    assert issues == []
    _, issues = check(schemas, "things/mine.md", "type: thing\nname: A\nwhere: /no/such/path")
    assert codes(issues, "warning") == ["field"]


```

- [ ] **Step 2: Run it to see it fail.**

Run: `python3 -m pytest system/tests/python/test_schema.py -q -k shipped_example`
Expected: FAIL, `assert [Issue(... path does not exist: /no/such/path)] == []`.

- [ ] **Step 3: Skip it.** In `system/scripts/vaultlib/schema.py`, replace:

```python
        for severity, message in check_value(spec, value, ctx, name):
            issues.append(Issue(rel, line, severity, "field", message))
```

with:

```python
        if spec.kind == "path" and rel.endswith("/example.md"):
            continue  # a shipped example (system/codebases/example.md) names a path no vault has (#19)
        for severity, message in check_value(spec, value, ctx, name):
            issues.append(Issue(rel, line, severity, "field", message))
```

- [ ] **Step 4: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_schema.py system/tests/python/test_index_rules.py -q`
Expected: all passed.

- [ ] **Step 5: Commit.**

```bash
git add system/scripts/vaultlib/schema.py system/tests/python/test_schema.py
git commit -m "fix(lint): skip the path check in shipped example files (#19)"
```

---

### Task 3: `/setup` phase 9 links the onboarding note from its codebase file

**Files:**
- Modify: `.claude/commands/setup.md:96` (phase 9)
- Test: `system/tests/commands.bats`, `system/tests/python/test_index_rules.py`

**Interfaces:** none.

- [ ] **Step 1: Write the tests.** Append to `system/tests/commands.bats`:

```bash

@test "/setup phase 9 links each onboarding note from its codebase file, never from wiki/Index.md (#19)" {
  sec="$(setup_section '9. Hand-off')"
  [[ "$sec" == *'add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`'* ]]
}
```

Append to `system/tests/python/test_index_rules.py` (a guard: it passes before the prompt change and pins the index behavior the prompt relies on):

```python


def test_a_link_from_a_codebase_file_keeps_the_onboarding_note_from_being_an_orphan(vault):
    write(vault, "wiki/work/concepts/AppOnboardingAssignment.md", concept("work", "AppOnboardingAssignment", "[[Index]]"))
    write(vault, "system/codebases/app.md", '---\ntype: codebase\nname: app\npath: "/"\npartition: work\n'
          'search_globs: ["*"]\n---\nOnboarding: [[AppOnboardingAssignment]]\n')
    assert issues(build(vault), "orphan") == []
```

- [ ] **Step 2: Run them.**

Run: `bats -f '#19' system/tests/commands.bats; python3 -m pytest system/tests/python/test_index_rules.py -q -k onboarding`
Expected: the bats test `not ok 1`; the Python guard passes.

- [ ] **Step 3: Edit phase 9.** In `.claude/commands/setup.md`, replace:

```text
link `[[Index]]` and name each superpower the work serves. Run `system/scripts/lint_vault.sh` afterwards.
```

with:

```text
link `[[Index]]` and name each superpower the work serves. Then add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`, so the note is not an orphan (`wiki/Index.md` belongs to the template; never edit it here). Run `system/scripts/lint_vault.sh` afterwards.
```

- [ ] **Step 4: Run the tests.**

Run: `bats system/tests/commands.bats`
Expected: all `ok`.

- [ ] **Step 5: Commit.**

```bash
git add .claude/commands/setup.md system/tests/commands.bats system/tests/python/test_index_rules.py
git commit -m "fix(setup): link the onboarding note from its codebase file (#19)"
```

---

### Task 4: Verify the branch

- [ ] **Step 1: Run the suites.**

```bash
python3 -m pytest system/tests/python -q; echo "pytest exit=$?"
bats system/tests/commands.bats system/tests/vault_integrity.bats; echo "bats exit=$?"
```

Expected: both `exit=0`.

- [ ] **Step 2: Lint the template itself.**

```bash
system/scripts/vault_index.py rebuild > /dev/null
system/scripts/vault_index.py issues | tail -n 1
```

Expected: `0 errors, 0 warnings` (before this plan: `0 errors, 4 warnings`).
