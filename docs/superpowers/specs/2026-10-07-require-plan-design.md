# Require a superpowers plan for every change

**Date:** 2026-10-07
**Status:** Rev 2: the independent review's findings folded in (C1–C2, I1–I9, M1–M13); awaiting re-review and the owner's review
**Applies to:** the development repositories `kferran/jarvis` (default branch `master`) and `kferran/minutes` (`main`). Vaults made from the template carry the files but never run them.

## 1. Problem and decisions

The owner's rule: every change is built from a written plan made with superpowers (`superpowers:writing-plans`). PR #53 shipped from an in-chat design with no plan, because nothing checked the rule. Memory and instructions can be skipped; this design adds checks that block the work instead.

| Topic | Decision |
|---|---|
| Layers | A git `pre-commit` hook blocks a commit without a plan. A Claude Code `PreToolUse` hook (user level) blocks `gh pr create` without a plan and blocks attempts to skip the git hook. A required GitHub check runs on every pull request. |
| Exemptions | None. A README fix needs a plan too. |
| What counts | A plan file with the `writing-plans` header. The check does not look for the spec. |
| Logic | One checker script per repository, tested there. The git hook, the Claude Code hook and the pull-request check all call it. The pull-request check and the Claude Code hook run the default branch's copy, so a branch cannot weaken the check that judges it. |
| Vault safety | The checker does nothing unless the clone's local git config or the CI job switches it on, so a vault that merges the template is unaffected. |

Rev 1 checked commits from the Claude Code hook. That hook runs before the command, so with `git add … && git commit` or `git commit -a` it saw an empty or stale index and let code through (review C1). A git `pre-commit` hook sees the final index, covers commits typed outside Claude Code, and checks the repository the commit actually runs in.

## 2. Components

| Unit | Purpose |
|---|---|
| `.github/require_plan.sh` | The checker (§3). `git` and `grep` only. |
| `.github/hooks/pre-commit` | The development clone's git hook: runs `require_plan.sh commit`. Wired by `core.hooksPath` (§7). Vaults use `.githooks/` and never point at this folder. |
| `.github/claude-hook-require-plan.sh` | The Claude Code hook's source (§4), kept in the repository so it is tested; installed by copying it to `~/.claude/hooks/require-plan.sh`. |
| `.github/workflows/require-plan.yml` | The pull-request check (§5). |
| `system/scripts/vaultlib/nightshift_run.py` (`_deliver`) | Puts a `Plan:` line first in the pull request body the Nightshift builds (§6). |
| `system/scripts/vaultlib/nightshift_check.py` (`_plan`) | Refuses to queue a plan without the header (§6). |
| `system/tests/require_plan.bats`, `system/tests/require_plan_hook.bats` | Tests (§8). The gate picks up every `system/tests/*.bats`. |

## 3. The checker

Usage: `require_plan.sh commit` or `require_plan.sh pr [--base <ref>] [--head-ref <branch>] [--body-file <file>]`, run inside the repository. Exit 0 allowed, 1 blocked (one line on stderr starting `require_plan:` and saying why), 2 usage error.

- **Switch.** It exits 0 at once unless `git config --local --type=bool --get superpowers.requirePlans` prints `true`, or the environment has exactly `REQUIRE_PLANS=true` (the CI job sets it for the one command). `--local` keeps a global setting from switching vaults on; `--type=bool` reads `yes`, `1` and `True` as on.
- **Plan.** A path under `docs/superpowers/plans/` whose text contains the header marker `REQUIRED SUB-SKILL: Use superpowers:` (the `writing-plans` header, superpowers 6.4.1). The literal lives in one place in the checker. Outcomes documents lack it and do not count.
- **Reading.** Paths come from `git diff -z --name-only --diff-filter=ACMR` (renames count as the new path; a deleted plan does not count). A staged plan's text is read from the index (`git cat-file blob :<path>`), a committed plan's from `HEAD`, never from the working tree.
- **Base.** `--base`, else the remote default branch (`git symbolic-ref refs/remotes/origin/HEAD`), else `origin/master`, else `origin/main`; none of these, or no merge-base (unborn `HEAD`, unrelated history), blocks with the reason. The branch's changes are the paths changed between `git merge-base <base> HEAD` and `HEAD`.
- **`commit` mode** (from the git hook, which sees the final index):
  - a merge in progress (`$(git rev-parse --git-path MERGE_HEAD)` exists, which also works in a worktree) is allowed;
  - on the default branch (current branch equals the base's branch name), only a non-empty staged set that lies entirely under `docs/superpowers/specs/` or `docs/superpowers/plans/` is allowed;
  - on any other branch, the commit is allowed when the staged set is non-empty and lies entirely under those two folders, or when a plan is among the branch's changes or the staged paths.

  Otherwise: `require_plan: no superpowers plan on this branch; commit one under docs/superpowers/plans/ first`.
- **`pr` mode** allows when a plan is among the branch's changes. A body line `Plan: <path>` naming a plan that exists at `HEAD` also passes, but only when `--head-ref` starts with `nightshift/` (review C2: on any other branch one line naming an old plan would pass any change). A missing body file counts as no body.

## 4. The Claude Code hook

Registered in `~/.claude/settings.json` as a `PreToolUse` hook with matcher `Bash`, on the machine where coding sessions run (the server). It reads the hook input from stdin.

- **Fast exit.** If the raw input contains neither `gh pr create` nor `git` followed by `commit`, it exits 0 before needing `jq`, so a missing `jq` cannot block unrelated commands in other projects.
- **Matching.** It parses `tool_input.command` and `cwd` with `jq`, then matches a command only at a command start: the start of a line, or after `&&`, `||`, `;`, `|`, `(` or `$(`. Text inside a commit message or a `grep` pattern does not match. `git commit-tree` and `git commit-graph` do not match.
- **`git commit`** (also `git -C <dir> commit`): the git hook does the checking. This hook blocks only the ways around it: `--no-verify`, `-n`, `-c core.hooksPath=…` or `--config core.hooksPath=…`, and `git -c core.hooksPath=…`. In a repository with the switch on, it also blocks when `git config core.hooksPath` is not `.github/hooks`, since the check would then never run.
- **`gh pr create`**: it runs the default branch's checker, `git show origin/HEAD:.github/require_plan.sh`, through `bash` in `pr` mode, without a body (only the Nightshift uses the `Plan:` line, and it does not go through this hook). No checker at `origin/HEAD` means the repository is off.
- **Repository.** The `-C` directory, else a leading `cd <dir> &&` resolved against `cwd`, else `cwd`. When the command changes directory in any other way before the match, it blocks with `run gh pr create from the repository directory`.
- **Result.** Checker exit 1: the hook exits 2 with the checker's line on stderr, which blocks the call and shows the reason. `jq` missing once a trigger matched, or a checker exit other than 0 or 1: exit 2 with a message (fails closed).

## 5. The pull-request check

`.github/workflows/require-plan.yml`, on `pull_request_target` (`opened`, `synchronize`, `reopened`, `edited`), job `require-plan`, `permissions: contents: read`. `pull_request_target` runs the workflow file from the base branch, so a pull request cannot edit the check that judges it; no code from the pull request is executed.

1. Read `vars.REQUIRE_PLANS` through `env:`. When it is not exactly `true`, print `::notice::require-plan is switched off (REQUIRE_PLANS=<value>)` and exit 0. The job always runs: a job skipped by `if:` reports success and would satisfy a required check silently (review I1).
2. `actions/checkout` of the base branch with `fetch-depth: 0` and `persist-credentials: false`, then `git fetch origin refs/pull/<number>/head` and check out that commit detached, as data.
3. Copy the base branch's checker out first (`git show origin/<base>:.github/require_plan.sh > "$RUNNER_TEMP/require_plan.sh"`), then run `REQUIRE_PLANS=true bash "$RUNNER_TEMP/require_plan.sh" pr --base origin/<base> --head-ref <head branch> --body-file <file>` in the pull request's checkout.
4. Every value from the event (base ref, head ref, number, body) reaches the script through `env:`, never by `${{ }}` inside `run:`. The body is written to a file from its environment variable.

Re-running a job reuses the original event, so a corrected `Plan:` line is seen only through an edit of the pull request body (the `edited` trigger).

Branch protection on `master` (`jarvis`) and `main` (`minutes`) makes `require-plan` a required check. Both repositories are public, so the free plan allows it. The owner can still override as an admin.

## 6. The Nightshift

- `nightshift_run._deliver` builds the pull request body for a plan item. Its first line becomes `Plan: <the item's plan path>`, taken from the queue note (runner-owned), and any `Plan:` line in the session's own text is removed. The plan path exists at the branch head, because readiness requires it committed at `base` and the branch starts there.
- Bitbucket codebases get no body (the runner only records a create-PR link) and are not under this check.
- `nightshift_check._plan` also requires the header marker, the same literal as the checker, so a plan that would fail the pull-request check is refused at queue time instead of after a night's run. A test keeps the two literals equal.
- A Nightshift plan that edits `.github/workflows/` needs an SSH remote or a token with the `workflow` scope to push.

## 7. Rollout

The last task of the plan, attended, with the owner's OK at each step:

1. In the `jarvis` clone: `git config --local superpowers.requirePlans true` and `git config --local core.hooksPath .github/hooks`.
2. Copy the hook to `~/.claude/hooks/require-plan.sh` and register it in `~/.claude/settings.json` on the server.
3. Set the repository variable `REQUIRE_PLANS=true` on `kferran/jarvis`.
4. Branch protection: `require-plan` required on `master`.
5. Live proof: a code commit on a scratch branch without a plan is blocked, from Claude Code and from a plain terminal; a draft pull request without a plan shows the check failing; both are then deleted.

`minutes` gets the checker, git hook, hook source and workflow through its own small plan after this one is merged; steps 1, 3 and 4 for `minutes` wait for it. The README gains one line under the template-update section: a vault whose `origin` uses HTTPS with a `gh` token needs the `workflow` scope to push after this update, because the update adds `.github/workflows/`.

## 8. Testing

Bound tools: **bats**, **pytest**, the gate (`system/scripts/verify_setup.sh`), one live check (§7 step 5).

- `require_plan.bats`, against temporary repositories with a local bare `origin`:
  - the switch: off by default; `--local` true switches on; a global true does not; `REQUIRE_PLANS=true` switches on; `yes` reads as on;
  - commit mode through the real git hook (`core.hooksPath`), so the final index is checked: `git add` then `git commit`; `git commit -a`; an empty index; only specs or plans staged; code staged with no plan; a plan with the header changed on the branch; a plan without the header; a deleted plan; a staged plan read from the index while the working tree differs; a non-ASCII path; a merge in progress, in the main checkout and in a worktree; on the default branch, code alone and code staged with a plan are both blocked;
  - pr mode: plan on the branch; neither plan nor line; a valid `Plan:` line on a `nightshift/` head; the same line on another head; a line naming a missing path; a missing body file;
  - failures: no origin default branch, unborn `HEAD`, a bad mode (exit 2);
  - `.github/require_plan.sh` and `.github/hooks/pre-commit` are mode 100755 in git; the checker contains none of `mapfile`, `${x,,}`, `declare -A`, `[[ -v` (bash 3.2 for `minutes`).
- `require_plan_hook.bats`, with stub checkers at `origin/HEAD`:
  - unrelated input exits 0 without `jq` on `PATH`;
  - `gh pr create` at a command start reaches the checker; inside a quoted message, a `grep` pattern or `git commit-tree`, it does not;
  - `cd <dir> && gh pr create` checks `<dir>`'s repository; another directory change before it blocks;
  - `git commit --no-verify`, `-n`, `-c core.hooksPath=x`, and a switched-on repository with a different `core.hooksPath` are blocked; a plain `git commit` passes the hook (the git hook decides);
  - no checker at `origin/HEAD` passes; checker exit 1 gives exit 2 with its line; `jq` missing after a match gives exit 2.
- pytest: the Nightshift pull request body's first line is `Plan: <plan path>` and a session-written `Plan:` line is removed; `nightshift_check` refuses a plan without the marker; the marker literal in `nightshift_check.py` equals the one in `require_plan.sh`.

## 9. Rulings (cost if wrong)

- R1. The Claude Code hook matches command text at command starts. An alias or a `git` from a variable slips past it. Cost: the git hook still checks the commit; the pull-request check catches a pull request.
- R2. A fix pass on a merged plan must change the plan on its branch (for example, a fix-pass section) before its first code commit. Cost: one small plan edit per fix branch.
- R3. The checker, git hook and hook source ship to vaults but stay off. Cost: four unused files in every vault.
- R4. A merge commit is allowed whatever it stages. Cost: code added by hand while resolving a merge is not checked until the pull request.
- R5. The commit check compares against the local `origin/<default>` ref, which can be stale. Cost: a wrong local answer; the pull-request check is authoritative.
- R6. The marker is superpowers 6.4.1 wording. Cost: if a later plugin version changes it, new plans fail closed until the one literal is updated.
- R7. Only the server gets the Claude Code hook. Cost: a coding session on another machine has only the git hook (if its clone is switched on) and the pull-request check.

## 10. Out of scope

- Checking that a plan has an approved spec, or that it was reviewed.
- Repositories other than `jarvis` and `minutes`.
- Bitbucket codebases served by the Nightshift.
