# Nightshift: template items come from the template remote

**Date:** 2026-10-08
**Status:** Design approved by the owner in chat (2026-10-08: option A, the remote), awaiting written-spec review
**Changes:** `2026-10-06-nightshift-design.md` §3.1 (readiness) and the runner's clone step

## 1. Problem and decision

A Nightshift item with `repo: template` reads its base branch and plan from the vault itself (`nightshift_check.source` returns the vault for `template`) and the runner fetches the base from the vault into the item's clone. So template work has to live as branches in the vault repository: on 2026-10-07 the vault held `fix/template-issues`, `fix/nightshift-minors` and `fix/telemetry-identifiers` and three worktrees only for this. The work split (2026-10-07) moves template branches to the development clone and the template remote.

**Decision (owner, option A):** a template item's source is the `template_remote` URL from the vault's config. The base branch must be pushed there before the item is queued. Rejected: a local development-clone path (option B), because every vault would need to configure it and unpushed branches would be run.

## 2. Changes

- `vaultlib/nightshift_check.py`:
  - `_plan` for `repo: template`: fetch `refs/heads/<base>` from `template_remote` into a temporary bare repository (`git init --bare` in a `tempfile.TemporaryDirectory`, then `git fetch --depth 1 --no-tags <url> refs/heads/<base>:refs/heads/<base>`), and run the existing checks (base resolves, plan committed at base, tasks exist, no protected-branch or deploy task) against it. The temporary repository is removed afterwards.
  - A failed fetch gives `base <base> is not on the template remote <url> (push it first)`.
  - `source(vault, "template")` returns `None`: no caller may read a template item from the vault any more. Callers that need the template's location use `template_remote`.
  - The existing `config has no template_remote` error stays and is checked before any fetch.
- `vaultlib/nightshift_run.py` (`_clone`), for `repo: template`: `git init` the item's clone, `git fetch --no-tags <template_remote> refs/heads/<base>:refs/remotes/base` (full depth, so the pull request branch shares history with the remote), and check out `nightshift/<id>` from it. The comment about the vault's private object store goes; nothing is fetched from the vault.
- Credentials for both fetches follow the push (`nightshift_deliver.push`): a `https://github.com/` URL gets the `gh` credential helper (`-c credential.helper= -c credential.helper=!gh auth git-credential`), and SSH runs with `GIT_SSH_COMMAND="ssh -o BatchMode=yes"`. The shared command prefix moves into one helper used by the check, the clone and the push.
- `.claude/skills/nightshift/SKILL.md`, the `add` step: for `template`, push the branch that holds the plan to the template remote before queuing; `--base` names that branch.
- `docs/superpowers/specs/2026-10-06-nightshift-design.md` §3.1: "`repo` is … or `template` (resolved through the config key `template_remote`)" gains "; the base and plan are read from that remote". A line under its Status records the change and points here.
- `docs/superpowers/roadmap.md`, the "Fixes from live use" row: fewer prompts (#68), the inactivity gate (#69) and this fix move to merged; "Next" keeps the `/ingest` preference gap.

## 3. Tests (pytest)

A local bare repository stands in for the template remote, as `test_nightshift_run.py` already does.

- `test_nightshift_check.py`:
  - a template item whose base and plan are on the remote passes;
  - a template item whose base exists only in the vault fails with the "push it first" message;
  - a template item with no `template_remote` fails as today, with no fetch;
  - `source(vault, "template")` is `None`.
  - Existing template-item fixtures that relied on the vault as the source move their base and plan to a local bare remote.
- `test_nightshift_run.py`: `_clone` for a template item builds from the remote's base: a commit made only in the vault is absent from the clone, and the remote's base commit is its parent.

Each new test fails before the change.

Bound tools: pytest (`test_nightshift_check.py`, `test_nightshift_run.py`, `test_nightshift_deliver.py`), the gate.

## 4. Rollout

None in this repository. After the vault merges this through `update_template.sh`, feOS pushes any template branch still in its queue to `kferran/Foundry` and removes its worktrees and branches; until then an already-queued template item whose base is not on the remote fails its readiness check and is reported.

## 5. Out of scope

- Codebase items (`repo: <codebase>`): unchanged, they read their registered clone.
- Changing `template_remote` or its default.
