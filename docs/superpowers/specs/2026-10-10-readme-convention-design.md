# Every vault owns its README

**Date:** 2026-10-10
**Status:** Draft for the owner's review.
**Issue:** #90. The direction changed on 2026-10-09: PR #97 (`README.local.md`) was closed. The 2026-10-10 grill settled the details below; the owner accepted every recommendation.

## 1. Problem

A vault made from the template carries the template's `README.md`, which describes the template. The owner wants the vault's README to describe that vault: its machines, codebases, partitions and what runs where. Editing it today makes every template update that touches the README conflict, and the daily update (#87) aborts on a conflict.

## 2. Decisions

- **The manual moves to `FOUNDRY.md`** at the root, unchanged in substance. Every test, script and command file that cites the README's sections points at `FOUNDRY.md` instead (for example, `vault_sync.sh`'s "README: Sync conflicts").
- **The template's `README.md` becomes a short landing page** of about 30 lines:
  - what the Foundry is;
  - the quick start, linking to the setup prompt in `FOUNDRY.md` (Getting started). The prompt stays in the manual because a client clones the private vault, whose README is the vault's own (a refinement of the grill's answer, made while planning);
  - a link to `FOUNDRY.md`;
  - a marker line, `<!-- foundry:landing -->`.
- **`.gitattributes` holds `README.md merge=ours`.** Git has no built-in `ours` driver, so `update_template.sh` merges with `git -c merge.ours.driver=true merge …`. The driver is defined only for the template merge:
  - in a template update, a README the vault has changed keeps the vault's version;
  - in `vault_sync.sh`'s merges between machines, no driver is defined, so git merges the README normally, and an edit on both machines conflicts the usual way and loses nothing.

  This refines the grill's answer that both `/setup` and `update_template.sh` set the driver in config: config would apply to every merge, sync included, and drop one machine's edits.
- **`/setup` writes a stub README** while `README.md` still carries the landing marker:
  - vault name, machine role, partitions, registered codebases and enabled timers, plus a link to `FOUNDRY.md`;
  - a README without the marker is the owner's, and setup never touches it.
- **Existing vaults need no migration.** A vault that never edited its README takes the new landing page on its first update. The owner then writes the vault's README (or re-runs `/setup`), and from then on updates keep it.

## 3. Changes

- `README.md` → `FOUNDRY.md` (`git mv`), then a new `README.md` landing page.
- `FOUNDRY.md`: a line near the top saying a vault's README is its own and this file is the manual. "Tracked in your vault, never in the template" gains `README.md`. "Updating" explains the `merge=ours` rule.
- `.gitattributes`: `README.md merge=ours`.
- `update_template.sh`: `-c merge.ours.driver=true` on the merge.
- `.claude/commands/setup.md`: a new step after 9 (Hand-off) that writes the stub README. Line 5's "the README's setup prompt" becomes "the setup prompt in `FOUNDRY.md`, Getting started".
- References to README sections move to `FOUNDRY.md`: `vault_sync.sh`, `backup.md`, `check_deps.sh`, `CLAUDE.md` if it cites one, and the tests.
- `vault_integrity.bats`: the link check covers both `README.md` and `FOUNDRY.md`.

## 4. Tests

- **bats (`remote.bats`):**
  - a vault whose `README.md` changed keeps it through `update_template.sh` while the template's README also changed;
  - an unedited README takes the template's new one;
  - the vault's git config holds no `merge.ours.driver` afterwards.
- **bats (`remote.bats`):** without the driver, a README changed on both sides still conflicts in a plain `git merge`, which is what `vault_sync.sh` sees (no driver outside the template merge).
- **bats (`commands.bats`, `vault_integrity.bats`):**
  - every existing README text check moves to `FOUNDRY.md`;
  - the landing page has the marker, the setup prompt and the link;
  - `.gitattributes` has the rule;
  - `setup.md` has the stub step and its marker condition.

Bound tools: bats (`remote.bats`, `commands.bats`, `vault_integrity.bats`), pytest for any test that reads the README, and the gate.

## 5. Rollout

After merge and the vault's next update, the vault's README is the landing page. feOS writes the vault's own README (PorchOS#1), or the owner re-runs `/setup` for the stub.
