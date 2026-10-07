# Require a superpowers plan for every change

**Date:** 2026-10-07
**Status:** Approved in brainstorming (2026-10-07), awaiting written-spec review
**Applies to:** the development repositories `kferran/jarvis` (default branch `master`) and `kferran/minutes` (`main`). Vaults made from the template carry the files but never run them.

## 1. Problem and decisions

The owner's rule: every change is built from a written plan made with superpowers (`superpowers:writing-plans`). PR #53 shipped from an in-chat design with no plan, because nothing checked the rule. Memory and instructions can be skipped; this design adds checks that block the work instead.

| Topic | Decision |
|---|---|
| Layers | A Claude Code `PreToolUse` hook (user level) blocks a commit or a `gh pr create` without a plan; a GitHub workflow runs the same check on every pull request, and branch protection makes it required. |
| Exemptions | None. A README fix needs a plan too. |
| What counts | A plan file with the `writing-plans` header. The check does not look for the spec. |
| Logic | One checker script per repository, tested there; the hook and the workflow both call it. |
| Vault safety | The checker does nothing unless the clone or the CI job switches it on, so a vault that merges the template is unaffected. |

## 2. Components

| Unit | Purpose |
|---|---|
| `.github/require_plan.sh` | The checker (§3). `git` and `grep` only; bash 3.2 compatible. |
| `.github/claude-hook-require-plan.sh` | The hook's source (§4), kept in the repository so it is tested; installed by copying it to `~/.claude/hooks/require-plan.sh`. |
| `.github/workflows/require-plan.yml` | The pull-request check (§5). |
| `system/scripts/vaultlib/nightshift_deliver.py` | Adds a `Plan:` line to the pull request body the Nightshift builds (§6). |
| `system/tests/require_plan.bats`, `system/tests/require_plan_hook.bats` | Tests (§8). The gate picks up every `system/tests/*.bats`. |

## 3. The checker

Usage: `require_plan.sh commit` or `require_plan.sh pr [--base <ref>] [--body-file <file>]`, run inside the repository. Exit 0 allowed, 1 blocked (one line on stderr saying why), 2 usage error.

- **Switch.** It exits 0 at once unless `git config --get superpowers.requirePlans` prints `true` or the environment has `REQUIRE_PLANS=true`.
- **Plan.** A file under `docs/superpowers/plans/` whose text contains `REQUIRED SUB-SKILL: Use superpowers:` (the header `writing-plans` writes). Outcomes documents lack it and do not count.
- **Base.** `--base`, else the remote default branch (`git symbolic-ref refs/remotes/origin/HEAD`), else `origin/master`, else `origin/main`. The branch's changes are the files changed between `git merge-base <base> HEAD` and `HEAD`.
- **`commit` mode** allows when any of these holds:
  - a merge is in progress (`.git/MERGE_HEAD` exists);
  - every staged path is under `docs/superpowers/specs/` or `docs/superpowers/plans/`;
  - a plan is among the branch's changes or the staged paths.

  Otherwise: `require_plan: no superpowers plan on this branch; commit one under docs/superpowers/plans/ first`. A commit on the default branch has no branch changes, so only specs and plans can be committed there.
- **`pr` mode** allows when a plan is among the branch's changes, or when the body file has a line `Plan: <path>` naming a plan that exists at `HEAD`. The body line serves a branch whose plan is already merged (a Nightshift run, a fix pass).

## 4. The hook

Registered in `~/.claude/settings.json` as a `PreToolUse` hook with matcher `Bash`. It reads the hook input with `jq` and takes `tool_input.command` and `cwd`.

- It acts when the command contains `git commit` (also `git -C <dir> commit`) or `gh pr create`, anywhere in a compound command. The repository is the `-C` directory, else `cwd`.
- It runs `<repo top level>/.github/require_plan.sh commit`, or `pr` with `--body-file <f>` when the command passes one. A repository without the checker, or any other command, exits 0.
- Checker exit 1: the hook exits 2 with the checker's line on stderr, which blocks the call and shows the reason. `jq` missing or a checker exit other than 0 or 1: exit 2 with a message (fails closed).
- Not covered: commits typed outside Claude Code. The pull-request check catches them.

## 5. The workflow

On `pull_request` (`opened`, `synchronize`, `reopened`, `edited`), job `require-plan`, only when the repository variable `REQUIRE_PLANS` is `true`:

1. `actions/checkout` with `fetch-depth: 0`.
2. Write the pull request body to a file from an environment variable (`PR_BODY: ${{ github.event.pull_request.body }}`), never by expanding it inside the script.
3. `REQUIRE_PLANS=true .github/require_plan.sh pr --base origin/${{ github.base_ref }} --body-file <file>`.

Branch protection on `master` (`jarvis`) and `main` (`minutes`) makes `require-plan` a required check. Both repositories are public, so the free plan allows it. The owner can still override as an admin.

## 6. The Nightshift

The runner opens its own pull requests, outside the hook. `nightshift_deliver.py` adds `Plan: <the item's plan path>` as the first line of the body it builds for a plan item, for both `gh pr create` and the Bitbucket link text.

## 7. Rollout

The last task of the plan, attended, with the owner's OK at each step:

1. `git config superpowers.requirePlans true` in the `jarvis` and `minutes` clones.
2. Copy the hook to `~/.claude/hooks/require-plan.sh` and register it in `~/.claude/settings.json`.
3. Set the repository variable `REQUIRE_PLANS=true` on both repositories.
4. Branch protection: `require-plan` required on `master` and `main`.
5. Live proof: a code commit on a scratch branch without a plan is blocked; a draft pull request without a plan shows the check failing; both are then deleted.

`minutes` gets the checker, hook source and workflow through its own small plan after this one is merged; steps 1, 3 and 4 for `minutes` wait for it.

## 8. Testing

Bound tools: **bats**, **pytest**, the gate (`system/scripts/verify_setup.sh`), one live check (§7 step 5).

- `require_plan.bats`, against temporary repositories with a local bare `origin`: switched off; `REQUIRE_PLANS=true` switches on; merge in progress; only specs or plans staged; code staged with no plan; a plan with the header changed on the branch; a plan without the header; a code commit on the default branch; `pr` with a valid `Plan:` line, with a missing path, and with neither; a bad mode exits 2.
- `require_plan_hook.bats`, with a stub checker on the repository path: `git commit`, `git -C <dir> commit` and `cd <dir> && git commit` reach the checker; `gh pr create --body-file f` passes the file; another command never runs it; a repository without the checker passes; checker exit 1 gives exit 2 with its line; `jq` missing gives exit 2.
- pytest: the Nightshift pull request body starts with `Plan: <path>`.

## 9. Rulings (cost if wrong)

- R1. The hook matches command text, so an unusual spelling (an alias, `git` from a variable) slips past it. Cost: the pull-request check catches it later.
- R2. A fix pass on a merged plan must change the plan on its branch (or use the `Plan:` line at pull-request time) before its first code commit. Cost: one small plan edit per fix branch.
- R3. The checker ships to vaults but stays off. Cost: two unused files in every vault.

## 10. Out of scope

- Checking that a plan has an approved spec, or that it was reviewed.
- Repositories other than `jarvis` and `minutes`.
- Commits outside Claude Code before the pull request.
