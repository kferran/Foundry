# Release Notes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `CHANGELOG.md` page in the template (What's next, then dated changes). Each template update shows the lines it brought in the next brief, as **What changed**.

**Architecture:**
- **The page:** a plain Markdown file at the repository root. Pull requests add its lines.
- **After a merge:** `update_template.sh` reads the lines the merge added to it (`git diff HEAD^1 HEAD`) into `system/logs/inputs/<date>/updates.md`. Offline: no `gh`.
- **The brief** prints that file under 🌅 Morning Alignment.

**Tech stack:** bash, bats.

**Spec:** `docs/superpowers/specs/2026-10-16-release-notes-design.md` (approved by the owner, 2026-10-16).

## Global Constraints

- Template rule: no hostname, user path, remote URL, distro, account ID, or employer, client, codebase or person names. The page is public, and the forbidden-names check scans it.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing.
- No new config keys, units, note types or dependencies.
- Writing rules (CLAUDE.md): plain words, user terms, no sales language.

## Review Focus

1. **A merge that adds no changelog lines:** `updates.md` is empty, the alert has no suffix, and the brief shows no section. Pinned in task 1.
2. **A changelog line edited (not added) by the merge:** only `+` lines count, so a reworded old line shows again. It shows once, and nothing breaks. Accepted. Pinned in task 1 by an edit case.
3. **A manual update** (`update_template.sh` without `--unattended`) writes `updates.md` too, so a by-hand update still reaches the next brief. Pinned in task 1.
4. **Two updates on one day** (by hand, then the timer): the second overwrites `updates.md` with only its own lines. Accepted: the first update's lines were already in that day's alerts. Not pinned.
5. **The `+++ b/CHANGELOG.md` diff header:** it never matches the line patterns, so it never shows. Pinned in task 1.

---

### Task 1: the update writes what changed

**Files:** `system/scripts/update_template.sh` (after `update_extensions`, before the index rebuild; and the final alert), `system/tests/remote.bats`.

- [ ] **Step 1: failing tests** in `remote.bats`, beside the extension update tests:
  ```bash
  @test "an update writes the changelog lines it merged to today's updates.md and points the alert at the brief (release notes spec §2.4)" {
    template_setup
    printf '# Changelog\n\n## Changes\n\n## 2026-10-01\n- Old line (#1)\n' > "$W/CHANGELOG.md"
    upstream_commit base.txt base
    run "$UT" --unattended
    [ "$status" -eq 0 ]
    printf '# Changelog\n\n## Changes\n\n## 2026-10-16\n- New line (#9)\n  - Action: run install_units.sh\n\n## 2026-10-01\n- Old line, reworded (#1)\n' > "$W/CHANGELOG.md"
    upstream_commit CHANGELOG.md "$(cat "$W/CHANGELOG.md")"
    run "$UT" --unattended
    [ "$status" -eq 0 ]
    f="system/logs/inputs/$(date +%F)/updates.md"
    [ "$(cat "$f")" = "$(printf '%s\n' '- New line (#9)' '  - Action: run install_units.sh' '- Old line, reworded (#1)')" ]
    grep -q '\[update\] template updated: .*; notes in today'"'"'s brief' "system/logs/alerts_$(date +%F).md"
  }

  @test "an update that adds no changelog line writes an empty updates.md and no brief pointer (release notes spec §2.4)" {
    template_setup
    upstream_commit new.txt hello
    run "$UT"
    [ "$status" -eq 0 ]
    f="system/logs/inputs/$(date +%F)/updates.md"
    [ -e "$f" ]
    [ ! -s "$f" ]
    run grep -c "notes in today's brief" "system/logs/alerts_$(date +%F).md"
    [ "$output" = 0 ]
  }
  ```
  The second test runs without `--unattended` (Review Focus 3).
- [ ] **Step 2: run red.** `system/scripts/test.sh system/tests/remote.bats -f "changelog"` fails: there is no `updates.md`.
- [ ] **Step 3: implement**, after `update_extensions`:
  ```bash
  # What changed (release notes spec §2.4): the lines this merge added to CHANGELOG.md, change and Action lines only,
  # for the next brief. Written on every merge, empty when it added none.
  notes="system/logs/inputs/$(date +%F)/updates.md"
  mkdir -p "$(dirname "$notes")"
  g diff --no-color -U0 HEAD^1 HEAD -- CHANGELOG.md 2>/dev/null | sed -n 's/^+\(- .*\|  - Action: .*\)$/\1/p' > "$notes.tmp" || true
  mv -f -- "$notes.tmp" "$notes"
  ```
  In the final unattended alert, append `${notes_suffix}`, where `notes_suffix="; notes in today's brief"` when `[[ -s "$notes" ]]`.
- [ ] **Step 4: run green.** `remote.bats` (whole suite).
- [ ] **Step 5: commit.** `feat(update): each merge writes the changelog lines it brought for the brief (release notes spec §2.4)`

### Task 2: the brief and the manual

**Files:** `.claude/commands/brief.md`, `FOUNDRY.md`, `system/tests/commands.bats`.

- [ ] **Step 1: failing test** in `commands.bats`, beside the brief tests:
  ```bash
  @test "release notes: the brief prints What changed from updates.md; the manual has the changelog rule (release notes spec §2)" {
    f=.claude/commands/brief.md
    grep -qF 'system/logs/inputs/<date>/updates.md' "$f"
    grep -qF '**What changed**' "$f"
    grep -qF 'Omit What changed when `updates.md` is missing or empty.' "$f"
    grep -qF 'A pull request that changes something a vault user would notice adds its line to `CHANGELOG.md`' FOUNDRY.md
  }
  ```
- [ ] **Step 2: run red.**
- [ ] **Step 3: implement.**
  - `brief.md`, in the inputs list: "`system/logs/inputs/<date>/updates.md`: the changelog lines the template update merged today, `- ` change lines with indented `  - Action:` lines (empty when the update merged none or did not run)."
  - `brief.md`, under 🌅 Morning Alignment after Where yesterday landed: "**What changed:** under `### What changed`, print the `Action:` lines first, each with its change line, then the other change lines, verbatim. Link `CHANGELOG.md` once at the end. Omit What changed when `updates.md` is missing or empty."
  - `FOUNDRY.md`:
    - in the `/brief` row, add "What changed (the changelog lines the morning's template update merged)";
    - in Development, add: "A pull request that changes something a vault user would notice adds its line to `CHANGELOG.md`, under today's date, in plain words with its PR number; add an indented `Action:` line when a vault must do something. Docs, test and CI changes add none."
- [ ] **Step 4: run green.** `commands.bats`.
- [ ] **Step 5: commit.** `feat(brief): What changed from the morning's update (release notes spec §2.4)`

### Task 3: the page

**Files:** `CHANGELOG.md` (new), `system/tests/commands.bats`.

- [ ] **Step 1: failing test:**
  ```bash
  @test "CHANGELOG.md has What's next and dated changes with PR numbers (release notes spec §2.1)" {
    grep -qx '## What'"'"'s next' CHANGELOG.md
    grep -qx '## Changes' CHANGELOG.md
    grep -qE '^## [0-9]{4}-[0-9]{2}-[0-9]{2}$' CHANGELOG.md
    grep -qE '^- .*\(#[0-9]+\)$' CHANGELOG.md
  }
  ```
- [ ] **Step 2: write the page.**
  - **What's next:** three to six lines from the roadmap (the extension moves finishing, release notes, the intraday brief, parallel Work Orders), with a link to `docs/superpowers/roadmap.md`.
  - **Changes:** the backfill of user-visible changes merged from 2026-10-02 to today, one plain line each with its PR number, newest date first. Use `gh pr list --state merged` for titles and bodies, and keep only what a vault user would notice.
  - **This change's own line:** under today's date.
  - The forbidden-names check must pass with the owner's list (`FOUNDRY_FORBIDDEN_NAMES` pointing at a list outside the repository).
- [ ] **Step 3: run green**, then the full gate.
- [ ] **Step 4: commit.** `docs: CHANGELOG.md, the release notes page (release notes spec §2.1, §2.6)`

### Final review and acceptance

- **Fresh reviewer** on the whole branch.
- **Live acceptance**, since the brief text changed. In a `.scratch` clone, make two template commits, the second adding two changelog lines. Run `update_template.sh` against a local template remote, then one headless `/brief`. Expected: What changed shows the two lines, actions first. Then run an update that adds none: no section.
