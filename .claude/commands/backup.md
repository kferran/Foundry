---
description: Verifies the vault, commits everything, and pushes according to remote_mode.
---

Back up the vault.

1. **Verify.** Run `system/scripts/verify_setup.sh`. On a client (`machine_role: client`), run `system/scripts/lint_vault.sh` instead: a client has no bats or pytest. If it exits non-zero, stop: report the failures and do not commit.
2. **Health (report only).** Run `bats system/tests/system_health.bats` and summarize failures as warnings. They never block the backup. Skip this step on a client.
3. **Run commits.** In every role and every `remote_mode`, run `system/scripts/commit_runs.py`. It commits each headless run that published files, one commit per run with a message built from the run's records, and prints one line per run. If it exits 1, stop: report its `commit_runs:` line (a run's files failed the pre-commit hook; fix them, then run `/backup` again) and do not commit.
4. **Changes.** Run `git status --porcelain`. If nothing changed, check for commits not yet pushed (`git status -sb` shows `ahead`, or the branch has no upstream): if there are some, go to step 6; otherwise say the vault is up to date and stop.
5. **Commit.** Stage everything (`git add -A`; the gitignore keeps raw inputs, logs and config out). Write one Conventional Commits message from the changed paths, and commit. The pre-commit hook lints staged notes; if it blocks the commit, report the errors and stop.
6. **Push.** Read `system/scripts/vault_index.py field system/config.md remote_mode`:
   - `none`: skip the push and say so.
   - `private`: if the `origin` URL is the template repository (`system/template_source`), refuse and say why. Otherwise `git push`, or `git push -u origin HEAD` when the branch has no upstream.
   - `keep`: push `origin` as configured.
7. **Report** each run commit from step 3, then the commit hash, its message, the files committed and the push result.
