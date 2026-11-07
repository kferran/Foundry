# Release notes: one changelog page in the template

**Date:** 2026-10-16
**Status:** Draft from the owner's answers (2026-10-16); awaiting the owner's approval.
**Request (owner):** "I'd like to have release notes with each update … a changelog that can be reviewed and shared with each update." Then: "audience is me for now, but as I begin sharing the Foundry it will be useful for others to see what is being updated along with a roadmap of changes. A page in the repo would be perfect."

## 1. Today

- `update_template.sh --unattended` merges the template at 05:30.
- It writes one `[update]` alert, `merged N change(s): #<pr> <title>; …`, from the pull request titles. Those are developer text, and docs and test PRs show beside real changes.
- Nothing says what changed for the vault, or what to run.
- The roadmap (`docs/superpowers/roadmap.md`) is a long table written for the maintainer.

## 2. Decisions

1. **One page:** `CHANGELOG.md` at the repository root. It renders on GitHub, so it is the page to share. It has two parts:
   - **What's next:** three to six lines, each a planned change in plain words. It links to `docs/superpowers/roadmap.md` for detail. The owner edits it when the roadmap moves.
   - **Changes:** dated sections, newest first. Each is `## <YYYY-MM-DD>` (the merge date) with one `- ` line per change, in user terms, ending with its pull request link `(#<n>)`. An optional indented `  - Action: <what to run>` line follows when a vault must do something.
2. **Audience:** the owner now, and people the owner shares the Foundry with later. So no internal jargon, and no owner names (the template rule; the forbidden-names check scans the file).
3. **Who writes:** the pull request that makes the change adds its line, in the same PR. That covers an interactive session (the FOUNDRY.md Development rule) and a Work Order (its plan's last task).
   - Docs, test and CI changes nobody using a vault would notice add nothing.
   - No CI check: a missing line is a miss in the page, not a broken update. The update's `[update]` alert still lists every merged PR, so nothing is lost. Revisit after two weeks.
4. **Shown with each update:** after the merge, the update reads the lines the merge added to `CHANGELOG.md` (`git diff HEAD^1 HEAD -- CHANGELOG.md`, added lines only, `- ` lines with their `Action:` sub-lines). It writes them to `system/logs/inputs/<date>/updates.md`. The brief prints them under 🌅 Morning Alignment as **What changed**, actions first, and omits the section when the file is empty. The `[update]` alert line adds `; notes in today's brief` when there are lines, so Slack points at the brief.
5. **Merge cost:** vaults never edit `CHANGELOG.md`, so the template merge is clean. Two open template branches can both add lines under the same date. That conflict is resolved like any other, keeping both lines.
6. **Backfill:** the first version seeds the Changes part with the user-visible changes of the past two weeks (from the merged PRs, rewritten in plain words), so the page starts useful.

## 3. Files (first version)

- New `CHANGELOG.md`, with What's next, plus the backfill and this change's own line.
- `system/scripts/update_template.sh`: after a merge, write `updates.md` and add the alert suffix. Offline: no `gh`, no network.
- `.claude/commands/brief.md`: the **What changed** section reads `updates.md`. `system/templates/daily-briefing.md` gets no heading, because the section is omitted when empty.
- `FOUNDRY.md`: the rule in Development, and the brief's What changed in the brief row.
- Tests:
  - `remote.bats`: an update writes `updates.md` from the added lines only, keeps the Action lines and adds the suffix; an update that adds none writes an empty file and no suffix.
  - `commands.bats`: pins the brief rule and the Development rule.
- No new config keys, units, note types or dependencies.

## 4. Not in this version

- A GitHub release or a page beyond the repository file.
- Generating notes from PR bodies.
- A CI check that each PR adds a line.
- A What changed section in the debrief.

## 5. Acceptance

The brief command changes, so the live acceptance steps re-run: one headless `/brief` after an update that added two lines shows them under What changed. One with none shows no section.
