# Unattended update: a standalone vault commits before it merges

**Date:** 2026-10-13
**Status:** Accepted 2026-10-14 (owner: "accept all", #136). Built in PR #165 (plan `docs/superpowers/plans/2026-10-14-sync-update-commit.md`).
**Issue:** #136 (C4). From the 2026-10-13 audit (`docs/superpowers/2026-10-13-audit.md` on the audit branch).

## 1. Problem

`update_template.sh --unattended` dies on a dirty working tree ("working tree is not clean"). On a server, `foundry-sync.conf.in` runs `vault_sync.sh --pre` first, which commits every change, so the tree is clean. On a standalone machine nothing commits between `/backup` runs: the day's published runs, Now page writes and briefing archive moves stay in the working tree, so the morning update alerts "template update failed: working tree is not clean" every day and never merges. `vault_sync.sh` is not the fix there: it exits with `fail config` unless `remote_mode` is `private`.

## 2. Decisions

- **The unattended run commits the way the sync does, then merges.** The sync's commit step (`commit_runs.py`, `git add -A`, the scripted `sync(<role>): N file(s)` message with its `Foundry-Command: sync` and `Foundry-Role` trailers, a reset on refusal) moves from `vault_sync.sh` into `lib_git.sh` as `git_sync_commit <role>`, and both scripts call it. One copy of the message, and the update's commit is the commit a server's `--pre` sync would have made.
- **A refusal stops the update before the fetch.** A `commit_runs.py` failure or a pre-commit hook refusal dies with the hook's first line in the alert ("template update failed: the sync commit was refused: <line>"), so the alert names the file. The vault stays as it was, uncommitted changes included. With the C7 spec built (2026-10-14), a published run the hook refuses no longer fails `commit_runs.py`: the other runs and the sync commit land first, then the update stops with an alert naming the refused paths, before the fetch.
- **Interactive mode is unchanged:** it still refuses a dirty tree and tells the owner to commit or stash; the owner is there to decide.
- **Owner decision:** the unattended update may commit the owner's uncommitted edits on a standalone machine, half-written notes included, as the sync does every cycle on a server or client. Recommendation: yes; the other outcome is today's, where a standalone vault never updates.

## 3. Changes

- `system/scripts/lib_git.sh`: `git_sync_commit <role>` (moved from `vault_sync.sh`; sets `GIT_SYNC_ERROR` and returns 1 on a refusal). Its own `git` calls close fd 9 (`9>&-`), as `vault_sync.sh`'s `git()` wrapper and `update_template.sh`'s `g()` do, so neither `git add`, `git commit` nor the hook they spawn inherits `run.lock`.
- `system/scripts/vault_sync.sh`: calls it; exits and alerts unchanged.
- `system/scripts/update_template.sh`: in `--unattended`, the clean-tree `die` becomes the commit call, under `run.lock` and before the fetch.
- `FOUNDRY.md` Updating: "refuses uncommitted changes" becomes "commits them first, as the sync does", and the sentence "the clean-tree check matters only on a standalone machine" goes.
- `system/systemd/foundry-update.service.in`: the comment names the commit; `TimeoutStartSec` stays 20 minutes (the commit takes seconds).

**Existing vault:** no config or unit change; the next morning's update commits and merges.

## 4. Tests

bats `remote.bats`: the case "--unattended fails with an alert on uncommitted changes and never commits them (#87)" flips: a new note and a pending published run give a `commit_runs` commit, a `sync(standalone): 1 file(s)` commit and the merge, exit 0 and the update alert; a note the hook refuses gives exit 1, an alert with the hook's line, no fetch (no `refs/remotes/template`) and the note still uncommitted; interactive mode still refuses a dirty tree before fetching (the existing case); no git child of the unattended commit inherits `run.lock`'s fd 9 (the `sync.bats` case, mirrored). `sync.bats`: the commit cases pass unchanged after the move. Each fails before the change. Bound tools: bats and the gate.

## 5. Out of scope

- A client: it has no update unit and gets updates through sync.
- Signing or opt-in for the merge itself (S1, owner decision pending).
