# Nightshift: template items come from the template remote

**Date:** 2026-10-08
**Status:** Rev 2, approved by the owner (2026-10-08). Rev 1 (option A, the remote) was approved; rev 2 folds in a three-reviewer quorum on its plan.
**Changes:** `2026-10-06-nightshift-design.md` §3.1 (readiness) and the runner's clone step

## 1. Problem and decision

A Nightshift item with `repo: template` reads its base branch and plan from the vault itself (`nightshift_check.source` returns the vault for `template`) and the runner fetches the base from the vault into the item's clone. So template work has to live as branches, and often worktrees, in the vault repository, mixed with the vault's own history. Template work belongs in the template's development clone and on the template remote.

**Decision (owner, option A):** a template item's source is the `template_remote` URL from the vault's config. The base branch must be pushed there before the item is queued. Rejected: a local development-clone path (option B), because every vault would need to configure it and unpushed branches would be run.

## 2. Changes

### 2.1 Reading the remote (`vaultlib/nightshift_check.py`)

- `remote_git(url) -> (opts, env)`: git `-c` options and environment for a remote. No prompts (`GIT_TERMINAL_PROMPT=0`), `GIT_CONFIG_NOSYSTEM=1`, `GIT_SSH_COMMAND="ssh -o BatchMode=yes"`, and for a `https://github.com/` URL the `gh` credential helper (`-c credential.helper= -c credential.helper=!gh auth git-credential`). The check, the clone and the push all use it.
- `fetch_base(repo, url, base, dest, depth=None, timeout=…)`: fetch `refs/heads/<base>` from `url` into `repo` as `dest`, with a timeout (120 seconds in the check, 600 in the clone). A URL that starts with `-` is refused before git runs, because git would read it as an option (`--upload-pack=…` runs a command).
- `shown(url)`: the URL with any `user:password@` part removed, for every message that names it.
- `source(vault, "template")` returns `None`: no caller may read a template item from the vault.
- `_plan` for `repo: template`:
  - `config has no template_remote` stays and is checked before any fetch;
  - a `template_remote` starting with `-` gives `template_remote must be a URL or a path`;
  - fetch the base one commit deep into a temporary bare repository and run the existing checks (base resolves, plan committed at base, tasks exist, no protected-branch or deploy task) there;
  - a failed fetch whose git error says the ref is missing (`couldn't find remote ref`) gives `base <base> is not on the template remote <url> (push it first)`; any other failure gives `cannot read the template remote <url>: <last line of git's error>`.

### 2.2 The run (`vaultlib/nightshift_run.py`, `vaultlib/nightshift_deliver.py`)

- `_clone`, template item: `git init` the clone, fetch `refs/heads/<base>` from `template_remote` as `refs/remotes/base` (full depth, so the pull request branch shares history with the remote), check out `nightshift/<id>`. Nothing is fetched from the vault. An existing clone is reused only when it has `refs/remotes/base`; a clone left half-built (a killed tick, a failed fetch) is removed and rebuilt.
- A clone failure ends the item at once: `run_item` catches it and finishes the item `failed` with reason `base` and one "Needs you" line: `Push <base> to the template remote, then queue <id> again (<reason>)`. The item gets an outcome, a report row and the brief's carry-forward, and the queue moves on at the next tick.
- `_before`, template item: `base_sha` is read from the clone (`refs/remotes/base`), the commit the session starts from. The "no commits" guard (`sha == base_sha`) works for template items again. Codebase items are unchanged.
- `nightshift_deliver.push` uses `remote_git` and refuses a URL that starts with `-`.

### 2.3 Text

- `.claude/skills/nightshift/SKILL.md`, the `add` steps: for `template`, the branch that holds the plan must be pushed to the template remote first; `--base` is a branch name on the remote; read the plan with `git fetch -q template <branch>` and `git show FETCH_HEAD:<plan>` (the vault's `template` remote is the one `update_template.sh` uses).
- `README.md`, the Nightshift paragraph: one sentence that a plan item for this template is read from `template_remote`, so its branch is pushed there before queuing, and that queuing checks the remote (network and the remote's credentials). The Status section's **Next** line follows the roadmap's.
- `docs/superpowers/specs/2026-10-06-nightshift-design.md` §3.1: "`template` (resolved through the config key `template_remote`)" gains "; the base and plan are read from that remote". A line under its Status records the change and points here.
- `docs/superpowers/roadmap.md`, the "Fixes from live use" row: fewer prompts (#68), the inactivity gate (#69), and the Nightshift minors (#70) and setup and update fixes (#71) under merged; this change under in review, with #72 and #73; "Next" keeps the `/ingest` preference gap. The "Next, in order" line drops the finished items.

## 3. Tests (pytest)

A local bare repository stands in for the template remote, as `test_nightshift_run.py` already does. Each new or changed test below fails before the change.

- `test_nightshift_check.py`:
  - the fixture pushes the base to the bare remote and keeps no base branch in the vault, so the existing ready-plan tests prove the check reads the remote;
  - a base that exists only in the vault fails with "push it first"; `source(vault, "template")` is `None`;
  - a missing `template_remote` gives only that error and never fetches (`fetch_base` is replaced by one that fails the test);
  - an unreadable remote (a missing path) gives "cannot read the template remote", never "push it first";
  - a `template_remote` starting with `-` is refused;
  - `remote_git` adds the `gh` helper for a GitHub HTTPS URL and nothing for a path;
  - `test_plan_errors` matches the missing-task message exactly, not any "9" in the text.
- `test_nightshift_run.py`:
  - `_clone` builds from the remote's base: a commit made only in the vault is absent, and the clone holds only `nightshift/<id>` and `refs/remotes/base`;
  - a failed fetch leaves no clone directory, and a half-built clone (no `refs/remotes/base`) is rebuilt;
  - a template item whose base is gone from the remote ends `failed` with reason `base` and a "Needs you" line on its first tick;
  - `_before`'s `base_sha` for a template item is the remote's base commit;
  - a template session that commits nothing ends `blocked` with reason `no commits` and pushes nothing (the bwrap-gated verify test asserts this exactly);
  - the delivery-retry test makes the remote refuse pushes with a `pre-receive` hook, so the check and the clone can still read it.

Bound tools: pytest (`test_nightshift_check.py`, `test_nightshift_run.py`, `test_nightshift_deliver.py`, `test_nightshift_report.py`), the gate.

## 4. Rollout (in each vault that queues template items, with its owner's OK)

1. Before `update_template.sh`: `system/scripts/nightshift.py list`; for each queued template item, push its base to the template remote under the same name, or cancel the item.
2. Run `update_template.sh`.
3. For each queued template item, `system/scripts/nightshift.py check raw/<partition>/nightshift/<id>.md` passes.
4. Remove the vault's template worktrees, then each template branch only after `git ls-remote template <branch>` shows it on the remote (use `git branch -d`, which refuses unmerged work).

An item missed in step 1 fails on its first tick with reason `base` and a "Needs you" line (§2.2): push the base, then queue it again.

## 5. Out of scope

- Codebase items (`repo: <codebase>`): unchanged, they read their registered clone.
- Changing `template_remote` or its default.
