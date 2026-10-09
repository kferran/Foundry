# Work Orders on codebases that use Git LFS

**Date:** 2026-10-09
**Status:** Draft for the owner's review (trimmed after a three-reviewer check the same day).
**Issue:** #83.

## 1. Problem

Work Orders fail on a codebase that keeps files in Git LFS. Measured on a local LFS repository (git 2.39.5, git-lfs 3.3.0):

| Step | Today | Why |
|---|---|---|
| Research copy (`_research_code`: `git init`, fetch one commit from the live clone, checkout) | fails: `smudge filter lfs failed` | the new repository has no remote, so git-lfs has nowhere to read the objects from |
| Plan clone (`_clone`: `git clone --shared` from the live clone) | works | `origin` is the live clone's path, which git-lfs reads |
| Verify checkout (`verify_sha`: a clone of the runner's bare repository) | fails: `remote missing object` | the runner fetched the branch's commits; LFS objects never travel with a fetch |

Two research items on such a codebase failed with reason `base` on the night of 2026-10-08. A manual clone never hits this: it has a remote and runs hooks. The runner keeps its copies away from the live clone on purpose (#77).

## 2. Change

Both failing checkouts read LFS objects from the live clone's store, given for that one command: `git -c lfs.storage=<store> checkout …`, where `<store>` is `<git common dir>/lfs` of the codebase's registered path (`nightshift_check.lfs_store(src)`). Nothing is written to the copy's config, so it keeps no link to the live clone.

- **Research copy:** `_research_code`'s checkouts (the first one and a resumed attempt's `checkout -f`) for a registered codebase. A template copy is unchanged.
- **Verify checkout:** `verify_sha` takes the store as an optional argument; `_deliver_plan` passes it for a registered codebase.

A plan that adds or changes an LFS file finds no object for it in the live clone's store, so its verify checkout fails and the item blocks with git-lfs's error. Uploading new LFS objects is left out until a Work Order needs it.

## 3. Tests

pytest, skipped when git-lfs is not installed. Each test builds an LFS codebase under a temporary `HOME` (`git lfs install --skip-repo`), so the user's git config is never read or changed:
- a research copy of an LFS codebase holds the file's content, also after a resumed attempt, and its config has no `lfs` key;
- a verify command that reads an LFS file sees its content.

Both fail before the change. Bound tools: pytest (`test_nightshift_run.py`, `test_nightshift_deliver.py`) and the gate.
