# Require a superpowers plan for every change

**Date:** 2026-10-07
**Status:** Rev 5, the smaller scope the owner chose after a four-agent quorum (2026-10-07). Rev 4 was approved; rev 5 drops the local layer.
**Applies to:** the development repositories `kferran/Foundry` (default branch `master`) and `kferran/minutes` (`main`). Vaults made from the template carry the files but never run them.

## 1. Problem and decisions

The owner's rule: every change is built from a written plan made with superpowers (`superpowers:writing-plans`). PR #53 shipped from an in-chat design with no plan. A count of merged pull requests found 8 of the 14 since the vault went live had no plan, 7 of them code changes, all merged by the owner; review at merge did not catch them. #58 and #60 then merged without a plan after the rule was written down. Memory does not carry the rule everywhere either: it is keyed by project path, so Nightshift sessions, the `minutes` repository and a renamed clone never see it.

| Topic | Decision |
|---|---|
| Layers | A required GitHub check on every pull request (authoritative). A Plan line and a queue-time check for the Nightshift. One instruction line in an untracked `CLAUDE.local.md` per clone. No local git hooks. |
| Exemptions | No change ships without a plan. The plan step itself is allowed: a pull request that touches only `docs/superpowers/specs/` and `docs/superpowers/plans/`. Small fixes get no exemption; the owner's admin override is the escape hatch. |
| What counts | A plan file with the `writing-plans` header. The check does not look for the spec. |
| Who judges | The default branch's copy of the checker, run by a `pull_request_target` workflow, so a pull request cannot weaken the check that judges it. |
| Vault safety | The workflow does nothing unless the repository variable `REQUIRE_PLANS` is exactly `true`, so a vault that merges the template is unaffected. |

**History.** Rev 1 checked commits from a Claude Code `PreToolUse` hook, which saw an empty or stale index (review C1). Rev 2 moved commits to a git hook and kept a Claude Code hook for the rest; the re-review found that hook ran repository code outside the sandbox (N4) and that git has more bypass spellings than a text match can list (N5). Rev 3 dropped the Claude Code hook after a for/against debate, and the owner added logging of `--no-verify` commits. Rev 4 folded in the plan review. A four-agent quorum on the need then voted 2 to build smaller, 1 as planned, 1 with changes; all four kept the pull-request check, the Nightshift changes and `CLAUDE.local.md`. Rev 5 is the owner's choice of the smaller scope: the commit-mode checker, both git shims and the `--no-verify` log are dropped (they drew about 21 of 55 review findings and 29 of 45 tests for a layer the spec called non-authoritative), as is the Nightshift push-command log line. It adds the operator's recovery notes, a block message that names the header, and a dated re-check of the GitHub event policy.

## 2. Components

| Unit | Purpose |
|---|---|
| `.github/require_plan.sh` | The checker (§3). `git` and `grep` only. |
| `.github/workflows/require-plan.yml` | The pull-request check (§4). |
| `system/scripts/vaultlib/nightshift_run.py` (`_deliver`) | Puts a `Plan:` line first in the pull request body the Nightshift builds (§5). |
| `system/scripts/vaultlib/nightshift_check.py` (`_plan`) | Refuses to queue a plan without the header (§5). |
| `README.md` | The `workflow` scope line and a short "When require-plan blocks a pull request" section (§6). |
| `CLAUDE.local.md` (untracked, per clone) | One instruction line (§7). |
| `system/tests/require_plan.bats` | Tests (§8). The gate picks up every `system/tests/*.bats`. |

## 3. The checker

Usage: `require_plan.sh --base <ref> [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]`, run inside the repository with `HEAD` at the pull request's commit. Exit 0 allowed, 1 blocked (one line on stderr starting `require_plan:` and saying why), 2 usage error (including a missing `--base`). It has no switch of its own; the workflow decides whether it runs.

- **Plan.** A path under `docs/superpowers/plans/` whose text at `HEAD` contains the header marker `REQUIRED SUB-SKILL: Use superpowers:` (the `writing-plans` header, superpowers 6.4.1). The literal lives in one place. Outcomes documents lack it and do not count.
- **Plan step.** A set of paths that is non-empty and lies entirely under `docs/superpowers/specs/` or `docs/superpowers/plans/`.
- **Reading.** The branch's changes are the paths changed between `git merge-base <base> HEAD` and `HEAD`. The plan-step test reads every changed path, deletions and both sides of a rename included (`git diff -z --name-only --no-renames`), so deleting code beside a new spec, or renaming code into `specs/`, is a code change. The plan search reads `git diff -z --name-only --diff-filter=ACMR` (renames count as the new path; a deleted plan does not count). Paths reach git after `--` or as `HEAD:<path>`, never as options. No merge base (unrelated history) blocks with the reason.
- **Workflows.** Before anything else, the checker blocks when `.github/workflows/require-plan.yml` at `HEAD` differs from its copy at the merge base, or when any other file under `.github/workflows/` at `HEAD` contains `require-plan`: a `pull_request` workflow from the pull request could otherwise report a passing check under the same name. Message: `require_plan: this pull request changes or adds a require-plan workflow; only the owner can merge it`.
- **Verdict.** Allowed when the branch's changes are a plan step, or include a plan. A body line `Plan: <path>` also passes when all of these hold (review C2, M1, M2): `--head-ref` starts with `nightshift/`; `--same-repo` is `true`; the path starts with `docs/superpowers/plans/`; and that path is a plan at `HEAD`. Carriage returns are stripped from the body first. A missing body file counts as no body. Otherwise: `require_plan: no superpowers plan in this pull request; add a plan made with superpowers:writing-plans (its header has "REQUIRED SUB-SKILL: Use superpowers:") under docs/superpowers/plans/`.

## 4. The pull-request check

`.github/workflows/require-plan.yml`, on `pull_request_target` (`opened`, `synchronize`, `reopened`, `edited`), job `require-plan`, `permissions: contents: read`. `pull_request_target` takes the workflow file and the checked-out commit from the repository's default branch, so a pull request cannot edit the check that judges it; no code from the pull request is executed.

1. A step prints `::notice::require-plan is switched off (REQUIRE_PLANS=<value>)` when `vars.REQUIRE_PLANS` is not exactly `true`. It is informational only.
2. `actions/checkout` of the default branch with `fetch-depth: 0` and `persist-credentials: false`.
3. One last step does the rest, and its first line is `[ "$REQUIRE_PLANS" = true ] || exit 0`, so a switched-off repository ends green before the fetch (a private vault's fetch would fail without credentials). It copies the default branch's checker to `$RUNNER_TEMP`, runs `git fetch origin refs/pull/<number>/head`, fails unless `FETCH_HEAD` equals the event's `head.sha`, points `HEAD` at that commit with `git update-ref --no-deref HEAD <sha>` (the working tree stays the default branch's; no file from the pull request is written), writes the body to a file, and runs `bash "$RUNNER_TEMP/require_plan.sh" --base refs/remotes/origin/<base> --head-ref <head branch> --same-repo <head repo == base repo> --body-file <file>`.
4. Every value from the event (default branch, base ref, head ref, head sha, head and base repository names, number, body) and `vars.REQUIRE_PLANS` reach the step through `env:`, never by `${{ }}` inside `run:`.

The job always runs: a job skipped by `if:` reports success and would satisfy a required check silently. Re-running a job reuses the original event, so a corrected `Plan:` line is seen only through an edit of the pull request body (the `edited` trigger).

Branch protection on `master` (`Foundry`) and `main` (`minutes`) makes `require-plan` a required check. Both repositories are public, so the free plan allows it. The owner can still override as an admin.

## 5. The Nightshift

- `nightshift_run._deliver` builds the pull request body for a plan item. Its first line becomes `Plan: <the item's plan path>`, taken from the queue note (runner-owned), and any `Plan:` line in the session's own text is removed. The plan path exists at the branch head, because readiness requires it committed at `base` and the branch starts there. Nightshift branches are pushed to the base repository, so `--same-repo` is true.
- `nightshift_check._plan` also requires the header marker, the same literal as the checker, so a plan that would fail the pull-request check is refused at queue time instead of after a night's run. This applies to every codebase the Nightshift serves, Bitbucket ones included. A test keeps the two literals equal.
- The Nightshift skill's `add` step states two facts a user queuing an item needs: `--pr-base` defaults to `master`, so a `main` repository needs `--pr-base main`; and a plan that edits `.github/workflows/` needs an SSH remote or a token with the `workflow` scope to push.
- Bitbucket codebases get no body (the runner only records a create-PR link) and no pull-request check.

## 6. README

- Under the template-update section, one line: a vault whose `origin` uses HTTPS with a `gh` token needs the `workflow` scope to push after this update, because the update adds `.github/workflows/`.
- A short section, "When require-plan blocks a pull request", for the development repositories:
  - no plan: commit a `writing-plans` plan on the branch (a plan file without its header does not count);
  - a revert or an urgent fix: write a short plan, or the owner merges with the admin override;
  - a pull request that changes the check itself: the owner merges with the admin override (§3, Workflows);
  - the check is broken on the default branch, so every pull request fails, including the fix: the owner sets `REQUIRE_PLANS` to `false` (`gh variable set REQUIRE_PLANS --body false`), merges the fix, and sets it back;
  - the check never reports (GitHub's event policy blocks `pull_request_target`): the owner allows the event on the repository's Actions settings page, or removes the required check until it is fixed.

## 7. Rollout

The last task of the plan, attended, with the owner's OK at each step. Every step lists its undo.

1. Precondition: the owner checks the repository's Actions settings page for an event policy that blocks `pull_request_target` (GitHub reportedly turns it off by default for public repositories from 2026-11-02; the REST API does not show it). When it would block, the owner allows the event for this repository.
2. Write `CLAUDE.local.md` in the clone root with one line: "Every change in this repository is built from a written plan made with superpowers:writing-plans, committed before any code. Never take brainstorming's in-chat (bounded) path to skip it, and never push to the default branch." Add `CLAUDE.local.md` to `.git/info/exclude` once, so nothing is committed. Confirm a new Claude Code session loads it.
3. Set the repository variable `REQUIRE_PLANS=true` on `kferran/Foundry`.
4. Live proof, before the check is required: a pull request without a plan and one with a plan each get a `require-plan` check run on their head commit (`gh api repos/<repo>/commits/<head sha>/check-runs`), concluding `failure` and `success`.
5. Branch protection: `require-plan` required on `master`. Then, with both pull requests marked ready, `gh pr view --json mergeStateStatus` prints `BLOCKED` for the one without a plan and `CLEAN` for the one with a plan.
6. The scratch branches and pull requests are deleted.
7. On or after 2026-11-03, the owner re-checks the Actions settings page and opens one scratch pull request to confirm `require-plan` still reports. Recorded as a dated item in the template work queue.

`minutes` gets the checker and workflow through its own small plan after this one is merged; steps 1–5 for `minutes` wait for it.

## 8. Testing

Bound tools: **bats**, **pytest**, the gate (`system/scripts/verify_setup.sh`), the live checks (§7 steps 4–5).

- `require_plan.bats`, against temporary repositories with a local bare `origin`; the test repositories ignore the host's system and XDG git config:
  - verdict: a plan on the branch passes; a plan-step-only branch passes; neither fails with the message that names the header; a plan without the header fails; a deleted plan does not count; a non-ASCII path with spaces is read correctly;
  - deletions: `git rm` of code plus a new spec fails; `git mv` of code into `specs/` fails;
  - workflows: a branch that edits `require-plan.yml` fails; a branch that adds another workflow naming `require-plan` fails; a branch whose other workflows do not name it is judged as usual;
  - the `Plan:` line: valid on a `nightshift/` head from the same repository; refused from a fork (`--same-repo false`), on another head, and with no `--same-repo`; refused for a path outside `plans/`, a path starting with `-`, a `..` path, a missing path and a file without the marker; a CRLF body and trailing spaces pass; a missing body file fails;
  - unrelated history fails with the no-merge-base message; a missing `--base` or a bad option exits 2;
  - the files: `.github/require_plan.sh` is mode 100755 in git and contains none of `mapfile`, `readarray`, `${x,,}`, `${x^^}`, `declare -A`, `[[ -v` (bash 3.2 for `minutes`);
  - the workflow, by text: the trigger is `pull_request_target`; `permissions` is `contents: read`; checkout sets `persist-credentials: false`; no `run:` block contains `${{`, and every `${{` line sets an `env:` name from a fixed list; `REQUIRE_PLANS` is never set to a literal `true`; the job has no `if:`; the last step starts with the `REQUIRE_PLANS` guard; the head is pinned to `head.sha` and set with `update-ref`, with no checkout of the pull request.
- pytest: the Nightshift pull request body's first line is `Plan: <plan path>` and a session-written `Plan:` line is removed; `nightshift_check` refuses a plan without the marker; the marker literal in `nightshift_check.py` equals the one in `require_plan.sh`.

## 9. Rulings (cost if wrong)

- R1. Nothing checks commits locally. Cost: work without a plan is caught at the pull request, after it was written; `CLAUDE.local.md` is the only nudge before that. This drops the owner's rev 3 addition (logging `--no-verify` commits), by the owner's choice of the smaller scope.
- R2. A fix pass on a merged plan must change the plan on its branch (for example, a fix-pass section). Cost: one small plan edit per fix branch.
- R3. The checker and workflow ship to vaults but stay off. Cost: two unused files in every vault, and a notice line on any vault pull request on GitHub.
- R4. The marker is superpowers 6.4.1 wording. Cost: if a later plugin version changes it, new plans fail closed until the one literal is updated.
- R5. A branch in the base repository named `nightshift/<x>` with a `Plan:` line naming any merged plan passes. Cost: anyone with push access can use it on purpose; `CLAUDE.local.md` and the owner's merge review are the guard.
- R6. Every Nightshift plan must carry the marker, Bitbucket codebases included. Cost: a plan written another way is refused at queue time.
- R7. A pull request that changes `require-plan.yml` (compared at the merge base) or adds a workflow naming `require-plan` always fails the check, so it merges only by the owner's admin override. Cost: a deliberate change to the check, by hand or by a Nightshift plan, needs that override; the owner's merge review is the only guard for it. A pull request that adds a passing check under another name is not covered, because only `require-plan` is required.
- R8. Branch protection leaves `enforce_admins` off, so any session running with the owner's credentials can push straight to `master`. Cost: such a push skips the check; `CLAUDE.local.md` tells sessions never to push to the default branch.
- R9. Small fixes (like #58 and #60) get no exemption. Cost: each needs a short plan or one admin-override click.

## 10. Out of scope

- Checking that a plan has an approved spec, that it was reviewed, or that it was written before the code.
- Local git hooks and `--no-verify` logging (dropped in rev 5).
- Repositories other than `Foundry` and `minutes`.
- Bitbucket pull requests.
- A Claude Code hook (dropped in rev 3).
