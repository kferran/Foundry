# A vault's own README: README.local.md

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #90.

## 1. Problem

A vault made from the template carries the template's README.md, which describes the template. The owner wants the vault to describe itself (its machines, codebases, partitions, what runs where). Editing README.md in the vault would conflict with every template README change that `update_template.sh` merges, and with a daily auto-update (#87).

## 2. Change

- A vault's own notes go in `README.local.md` at the vault root. It is tracked in the vault and never in the template.
- `update_template.sh` merges the template branch (`git merge`), and a file the template never has is never touched by that merge, so no script change is needed.
- The template README says so near the top, in one sentence that names the file without linking it (the template has no such file, and README links must name tracked files). The "Tracked in your vault, never in the template" list gains it.

Not done: an include of README.local.md into README.md (GitHub and Obsidian show the two files separately), and a `/setup` stub.

## 3. Tests

bats (`commands.bats`): the README names `README.local.md` near the top and in the vault-owned list, and the template tracks no `README.local.md`. Fails before the change. Bound tools: bats and the gate.
