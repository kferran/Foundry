# README.local.md Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The template README tells a vault to describe itself in `README.local.md`, a file the template never ships and template updates never touch (#90).

**Architecture:** Documentation only. `update_template.sh` merges the template branch, and a file the template never has is never part of that merge, so no script changes. The README names the file without linking it, because README links must name tracked files.

**Tech Stack:** Markdown, bats 1.8.2.

**Spec:** `docs/superpowers/specs/2026-10-09-readme-local-design.md`

## Global Constraints

- Work on branch `docs/readme-local`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Template rule: no machine, employer or people names.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`; run it outside a sandbox. Never run two gates at once.
- Bound tools: bats (`commands.bats`, `vault_integrity.bats`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- The README's relative-link check still passes: the new sentence names `README.local.md` in code formatting, not as a link.
- The template itself tracks no `README.local.md`: the test checks `git ls-files`.

---

### Task 1: Name README.local.md in the README

**Files:**
- Modify: `README.md`
- Test: `system/tests/commands.bats`

- [ ] **Step 1: Write the test**

Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'the connector returns no change history' README.md
}
````

Replace with:

````text
  grep -qF 'the connector returns no change history' README.md
}

@test "the README names README.local.md as the vault's own notes, which the template never ships (#90)" {
  head -n 12 README.md | grep -qF "Describe your own vault in \`README.local.md\`"
  grep -qF -- "- **Tracked in your vault, never in the template.** \`README.local.md\` (your vault's own notes)," README.md
  run git ls-files --error-unmatch README.local.md
  [ "$status" -ne 0 ]
}
````


- [ ] **Step 2: Run it to verify it fails**

Run: `bats system/tests/commands.bats`
Expected: FAIL, 1 `not ok`.

- [ ] **Step 3: Implement**

Edit 1 in `README.md`. Find:

````text
The Foundry is a template repository that becomes your vault. You clone it (or create a repo from it), run `claude` inside it, and run `/setup`. Setup configures the vault for your machine, your schedule and your codebases. Nothing specific to a machine or a user is committed. Per-user state is generated at setup time and gitignored.
````

Replace with:

````text
The Foundry is a template repository that becomes your vault. You clone it (or create a repo from it), run `claude` inside it, and run `/setup`. Setup configures the vault for your machine, your schedule and your codebases. Nothing specific to a machine or a user is committed. Per-user state is generated at setup time and gitignored. Describe your own vault in `README.local.md` at the vault root (its machines, codebases and what runs where): this README describes the template and changes with each template update, and template updates never touch `README.local.md`.
````

Edit 2 in `README.md`. Find:

````text
- **Tracked in your vault, never in the template.** `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Work Order queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).
````

Replace with:

````text
- **Tracked in your vault, never in the template.** `README.local.md` (your vault's own notes), `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Work Order queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).
````


- [ ] **Step 4: Run the tests and the gate**

Run: `bats system/tests/commands.bats system/tests/vault_integrity.bats`
Expected: PASS, no `not ok`.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
docs(readme): a vault's own README.local.md (#90)

The README names README.local.md at the vault root for the vault's own
notes (its machines, codebases and what runs where) and lists it among
the files tracked in the vault and never in the template. Template
updates merge the template branch, which never has that file, so they
never touch it.

Closes #90
```

Run: `git add README.md system/tests/commands.bats`

Run: `git commit -q -F .scratch/msg-1.txt`
