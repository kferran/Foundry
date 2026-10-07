# Fewer Permission Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The template's interactive settings allow seven read-only status commands, and `CLAUDE.md` carries the Bash rule, both byte for byte as in the owner's vault.

**Architecture:** Two edits and one test. The seven rules end `permissions.allow` in `.claude/settings.json`, right after the recall rule; the Bash line follows the **Configuration:** line in `CLAUDE.md`. A bats test pins the last eight allow entries, the block vaults merge against.

**Tech Stack:** JSON, Markdown, bats 1.8.2, jq 1.6.

**Spec:** `docs/superpowers/specs/2026-10-07-fewer-prompts-design.md`

## Global Constraints

- Work on branch `chore/fewer-prompts` of `kferran/Foundry`. Commit there; do not push or open a pull request.
- Byte for byte: the seven rules and the Bash line are copied exactly as below, in this order and position.
- `system/headless.settings.json` is not touched.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains. Read verdicts from exit codes.
- Run one suite as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/vault_integrity.bats` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`.
- Bound tools: bats (`system/tests/vault_integrity.bats`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file.

## Review Focus

- A vault that merges this must get no conflict: the rules end the array with no trailing comma, as in the vault (simulated in the spec, §4). Pinned by the new test's exact eight-entry match.
- A rule with a typo (an extra space, a missing `*`) would allow nothing and still look right. The test compares the exact strings.
- `telemetry_fetch.py --check` writes nothing (it returns before the lock, state, logs and alerts: `vaultlib/telemetry_run.py` `main`), so allowing it cannot change the vault.

---

### Task 1: The rules, the Bash line and their test

**Files:**
- Modify: `.claude/settings.json`, `CLAUDE.md`
- Test: `system/tests/vault_integrity.bats`

**Interfaces:**
- Produces: the bats test `interactive settings end with the read-only status rules a vault merges against, in order`.

- [ ] **Step 1: Write the failing test**

Edit 1 in `system/tests/vault_integrity.bats`. Find:

````text
  [ "$(jq '.hooks // {} | length' "$f")" = "0" ]
````

Replace with:

````text
  [ "$(jq '.hooks // {} | length' "$f")" = "0" ]
}

@test "interactive settings end with the read-only status rules a vault merges against, in order" {
  want='["Bash(system/scripts/vault_index.py recall:*)","Bash(system/scripts/verify_setup.sh)","Bash(system/scripts/verify_setup.sh --health)","Bash(system/scripts/nightshift.py list)","Bash(system/scripts/telemetry_fetch.py --list)","Bash(system/scripts/telemetry_fetch.py --check *)","Bash(system/scripts/dtcc_watch.py --check)","Bash(systemctl --user list-timers *)"]'
  run jq -c '.permissions.allow[-8:]' .claude/settings.json
  [ "$output" = "$want" ]
````


- [ ] **Step 2: Run it to verify it fails**

Run: `mkdir -p .scratch/tmp && TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/vault_integrity.bats`
Expected: FAIL, 1 of 20: `interactive settings end with the read-only status rules a vault merges against, in order`.

- [ ] **Step 3: Add the rules**

Edit 1 in `.claude/settings.json`. Find:

````text
      "Bash(system/scripts/vault_index.py recall:*)"
````

Replace with:

````text
      "Bash(system/scripts/vault_index.py recall:*)",
      "Bash(system/scripts/verify_setup.sh)",
      "Bash(system/scripts/verify_setup.sh --health)",
      "Bash(system/scripts/nightshift.py list)",
      "Bash(system/scripts/telemetry_fetch.py --list)",
      "Bash(system/scripts/telemetry_fetch.py --check *)",
      "Bash(system/scripts/dtcc_watch.py --check)",
      "Bash(systemctl --user list-timers *)"
````


- [ ] **Step 4: Add the Bash line**

Edit 1 in `CLAUDE.md`. Find:

````text
- **Configuration:** Read configuration with `system/scripts/vault_index.py field system/config.md <key>`; headless runs do not expand `@`-imports.
````

Replace with:

````text
- **Configuration:** Read configuration with `system/scripts/vault_index.py field system/config.md <key>`; headless runs do not expand `@`-imports.
- **Bash:** Never chain bash commands with `&&`, `;`, or `||`; run each as its own tool call. Use absolute paths instead of `cd` (a `cd` persists and breaks `system/scripts/` invocation from the vault root). No `for`/`while` loops or inline `python3` heredocs: use Read, Grep and Edit, or write one script to the scratchpad and run it once. Create files with Write, not `>` redirects (capturing a test's exit code is the exception). Pipe only into read-only filters (`grep`, `head`, `sort`, `jq`). Batch remote work into one `ssh` call per task.
````


- [ ] **Step 5: Run the suite to verify it passes**

Run: the suite command from Step 2.
Expected: PASS, `1..20`, no `not ok`.

- [ ] **Step 6: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 7: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(settings): read-only status rules and the Bash line

Seven read-only allow rules (the gate, the Nightshift list, the
telemetry and DTCC checks, the timer list) and the CLAUDE.md Bash line,
byte for byte as in the owner's vault, so a vault's template merge is
clean. A test pins the end of the allow list.
```

Run: `git add .claude/settings.json CLAUDE.md system/tests/vault_integrity.bats && git commit -q -F .scratch/msg-1.txt`
