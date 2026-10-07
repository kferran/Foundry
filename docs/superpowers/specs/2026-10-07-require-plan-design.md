# Require a superpowers plan for every change

**Date:** 2026-10-07
**Status:** Rev 4, from the plan review (2026-10-07); rev 3 was approved by the owner with one addition: every `--no-verify` commit or push is logged (§4.1, §6)
**Applies to:** the development repositories `kferran/Foundry` (default branch `master`) and `kferran/minutes` (`main`). Vaults made from the template carry the files but never run them.

## 1. Problem and decisions

The owner's rule: every change is built from a written plan made with superpowers (`superpowers:writing-plans`). PR #53 shipped from an in-chat design with no plan. A count of merged pull requests found 8 of the 14 since the vault went live had no plan, 7 of them code changes, all merged by the owner; review at merge did not catch them. Memory does not carry the rule everywhere either: it is keyed by project path, so Nightshift sessions and the `minutes` repository never see it.

| Topic | Decision |
|---|---|
| Layers | A required GitHub check on every pull request (authoritative; nothing local can skip it). A git `pre-commit` shim that stops a code commit early, and a `post-commit` shim that logs a commit made with `--no-verify`. A Plan line and a queue-time check for the Nightshift. One instruction line in an untracked `CLAUDE.local.md` per clone. |
| Exemptions | No change ships without a plan. The plan step itself is allowed: a commit or pull request that touches only `docs/superpowers/specs/` and `docs/superpowers/plans/`. |
| What counts | A plan file with the `writing-plans` header. The check does not look for the spec. |
| Who judges | The default branch's copy of the checker, in CI and in the git shim, so a branch cannot weaken the check that judges it. |
| Vault safety | The checker does nothing unless the clone's local git config or the repository variable switches it on, so a vault that merges the template is unaffected. |

**History.** Rev 1 checked commits from a Claude Code `PreToolUse` hook, which runs before the command and saw an empty or stale index (review C1). Rev 2 moved commits to a git hook and kept the Claude Code hook for `gh pr create` and for blocking ways around the git hook. The re-review found that hook ran repository code outside the sandbox in any repository (N4) and that git accepts more spellings of each bypass than a text match can list (N5). Two advocates then argued for and against the whole design; the ruling kept the required check, the git shim and the Nightshift changes, added `CLAUDE.local.md`, and dropped the Claude Code hook. Rev 4 folds in the plan review: a stale `REBASE_HEAD` no longer counts as a rebase in progress, deletions count toward the plan step, the base refs use full names, a pull request cannot carry its own `require-plan` workflow, the pull-request check is a no-op when switched off, and the rollout proves the check before making it required.

## 2. Components

| Unit | Purpose |
|---|---|
| `.github/require_plan.sh` | The checker (§3). `git` and `grep` only. |
| `.github/hooks/pre-commit`, `.github/hooks/post-commit` | Tracked sources of the git shims (§4). Installed by copying them into the clone's shared hooks folder; no branch carries the installed copies. |
| `.github/workflows/require-plan.yml` | The pull-request check (§5). |
| `system/scripts/vaultlib/nightshift_run.py` (`_deliver`) | Puts a `Plan:` line first in the pull request body the Nightshift builds (§6). |
| `system/scripts/vaultlib/nightshift_check.py` (`_plan`) | Refuses to queue a plan without the header (§6). |
| `CLAUDE.local.md` (untracked, per clone) | One instruction line (§7). |
| `system/tests/require_plan.bats` | Tests (§8). The gate picks up every `system/tests/*.bats`. |

## 3. The checker

Usage: `require_plan.sh commit` or `require_plan.sh pr [--base <ref>] [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]`, run inside the repository. Exit 0 allowed, 1 blocked (one line on stderr starting `require_plan:` and saying why), 2 usage error.

- **Switch.** It exits 0 at once unless `git config --local --type=bool --get superpowers.requirePlans` prints `true`, or the environment has exactly `REQUIRE_PLANS=true`. `--local` keeps a global setting from switching vaults on; `--type=bool` reads `yes`, `1` and `True` as on.
- **Plan.** A path under `docs/superpowers/plans/` whose text contains the header marker `REQUIRED SUB-SKILL: Use superpowers:` (the `writing-plans` header, superpowers 6.4.1). The literal lives in one place. Outcomes documents lack it and do not count.
- **Plan step.** A set of paths that is non-empty and lies entirely under `docs/superpowers/specs/` or `docs/superpowers/plans/`.
- **Reading.** Two path lists. The plan-step test reads every changed path, deletions included (`git diff -z --name-only`), so deleting code beside a new spec is a code change. The plan search reads `git diff -z --name-only --diff-filter=ACMR` (renames count as the new path; a deleted plan does not count). A staged plan's text is read from the index (`git cat-file blob :<path>`), a committed plan's from `HEAD`, never from the working tree. Paths reach git after `--` or as `HEAD:<path>`, never as options.
- **Base.** `--base`, else `origin/HEAD`, else `origin/master`, else `origin/main`, each resolved by its full name (`refs/remotes/origin/…`), so a tag named `origin/master` cannot stand in for the branch. When none resolves, it blocks with `require_plan: no default branch for origin; run git remote set-head origin -a`. No merge-base (unborn `HEAD`, unrelated history) blocks with the reason. The branch's changes are the paths changed between `git merge-base <base> HEAD` and `HEAD`.
- **`commit` mode** (from the git shim, which sees the final index):
  - a merge, rebase, cherry-pick or revert in progress is allowed (`MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `rebase-merge/` or `rebase-apply/` under `git rev-parse --git-path`, which also works in a worktree); the pull-request check decides. `REBASE_HEAD` is not on the list: `git rebase --quit` leaves it behind, and a real rebase always has one of the two folders;
  - on the default branch (current branch equals the base's branch name), only a plan-step staged set is allowed;
  - on any other branch or a detached `HEAD`, the commit is allowed when the staged set is a plan step, or when a plan is among the branch's changes or the staged paths.

  Otherwise: `require_plan: no superpowers plan on this branch; commit one under docs/superpowers/plans/ first`.
- **`pr` mode** allows when the branch's changes are a plan step, or include a plan. A body line `Plan: <path>` also passes when all of these hold (review C2, M1, M2): `--head-ref` starts with `nightshift/`; `--same-repo` is `true` (the head branch is in the base repository, not a fork); the path starts with `docs/superpowers/plans/`; and that path is a plan at `HEAD`. Carriage returns are stripped from the body first (bodies edited on GitHub use CRLF). A missing body file counts as no body.
- **`pr` mode, workflows.** Before anything else, `pr` mode blocks when `.github/workflows/require-plan.yml` at `HEAD` differs from the base's copy, or when any other file under `.github/workflows/` at `HEAD` contains `require-plan`: a `pull_request` workflow from the pull request could otherwise report a passing check under the same name. Message: `require_plan: this pull request changes or adds a require-plan workflow; only the owner can merge it`.

## 4. The git shim

`.github/hooks/pre-commit`, installed at `$(git rev-parse --git-common-dir)/hooks/pre-commit`. The common hooks folder is shared by every worktree of the clone and carried by no branch (re-review N1).

1. Exit 0 unless the local switch (§3) is on, so a foreign or third-party clone never runs anything.
2. Resolve the default branch with §3's chain; none resolves: block with the `set-head` message.
3. `git show <default>:.github/require_plan.sh` into a temporary file. Absent there (before this lands): exit 0. Otherwise run `bash <file> commit` and exit with its status (any status but 0 blocks the commit).

The shim does not run when `core.hooksPath` is set. The development clone leaves it unset; `/setup`, which sets it to `.githooks`, is never run in a development clone. `git commit --no-verify` and `git cherry-pick`, `git revert` and `git rebase` replays skip `pre-commit`; the pull-request check catches what they let through, and `CLAUDE.local.md` tells sessions never to use `--no-verify`.

### 4.1 Logging `--no-verify`

`git commit --no-verify` skips `pre-commit` but not `post-commit`, so a second shim records it.

- When the checker allows a commit, the `pre-commit` shim writes the staged tree (`git write-tree`) to `$(git rev-parse --git-path require-plan-checked)`.
- `.github/hooks/post-commit`, installed beside it, exits 0 unless the local switch is on. It reads the subject of `HEAD`'s reflog entry (`git reflog -1 --format=%gs HEAD`). Only a subject starting with `commit` is a `git commit` (`commit:`, `commit (amend):`, `commit (merge):`, `commit (initial):`); cherry-pick, revert and rebase replays have their own subjects and are not logged.
- For such a commit, when the marker is missing or names a tree other than `HEAD^{tree}`, it appends one line to `$(git rev-parse --git-common-dir)/require-plan.log`: `<ISO 8601 time>\t<branch or detached>\t<commit sha>\tpre-commit skipped (--no-verify)`. It then removes the marker. It never fails the commit.
- `git push --no-verify` skips only a `pre-push` hook, and the development clones have none, so it skips no check. The Nightshift's push is logged by the runner (§6).

## 5. The pull-request check

`.github/workflows/require-plan.yml`, on `pull_request_target` (`opened`, `synchronize`, `reopened`, `edited`), job `require-plan`, `permissions: contents: read`. `pull_request_target` takes the workflow file and the checked-out commit from the repository's default branch, whatever the base (GitHub behavior since 2025-12-08), so a pull request cannot edit the check that judges it; no code from the pull request is executed.

1. A step prints `::notice::require-plan is switched off (REQUIRE_PLANS=<value>)` when `vars.REQUIRE_PLANS` is not exactly `true`. It is informational only.
2. `actions/checkout` of the default branch with `fetch-depth: 0` and `persist-credentials: false`.
3. One step does the rest, and its first line is `[ "$REQUIRE_PLANS" = true ] || exit 0`. It is the job's last step, so a switched-off repository ends green before the fetch; a private vault's fetch would fail without credentials. Then `git fetch origin refs/pull/<number>/head`, fail unless `FETCH_HEAD` equals the event's `head.sha`, and point `HEAD` at that commit with `git update-ref --no-deref HEAD <sha>`. The working tree stays the default branch's; the checker reads only `HEAD:` and `git diff --name-only`, so no file from the pull request is written to disk.
4. Copy the default branch's checker out first (`git show origin/<default branch>:.github/require_plan.sh > "$RUNNER_TEMP/require_plan.sh"`), then run `bash "$RUNNER_TEMP/require_plan.sh" pr --base refs/remotes/origin/<base> --head-ref <head branch> --same-repo <head repo == base repo> --body-file <file>`, with `REQUIRE_PLANS` set from `vars.REQUIRE_PLANS`. The checker keeps its own switch as well (re-review N2).
5. Every value from the event (default branch, base ref, head ref, head sha, head and base repository names, number, body) and `vars.REQUIRE_PLANS` reach the scripts through `env:`, never by `${{ }}` inside `run:`. The body is written to a file from its environment variable.

The job always runs: a job skipped by `if:` reports success and would satisfy a required check silently. Re-running a job reuses the original event, so a corrected `Plan:` line is seen only through an edit of the pull request body (the `edited` trigger).

Branch protection on `master` (`Foundry`) and `main` (`minutes`) makes `require-plan` a required check. Both repositories are public, so the free plan allows it. The owner can still override as an admin.

## 6. The Nightshift

- `nightshift_run._deliver` builds the pull request body for a plan item. Its first line becomes `Plan: <the item's plan path>`, taken from the queue note (runner-owned), and any `Plan:` line in the session's own text is removed. The plan path exists at the branch head, because readiness requires it committed at `base` and the branch starts there. Nightshift branches are pushed to the base repository, so `--same-repo` is true.
- `nightshift_check._plan` also requires the header marker, the same literal as the checker, so a plan that would fail the pull-request check is refused at queue time instead of after a night's run. This applies to every codebase the Nightshift serves, Bitbucket ones included: every Nightshift plan comes from `writing-plans`. A test keeps the two literals equal.
- `_deliver` defaults the pull request base to `master`; a `minutes` item must be queued with `--pr-base main`.
- Bitbucket codebases get no body (the runner only records a create-PR link) and no pull-request check.
- The runner always pushes with `--no-verify` and `core.hooksPath=/dev/null`. `push.log` for the item gains a first line naming the command (`git push --no-verify <url> <sha>:refs/heads/<branch>`) before the push output, so every such push is on record. Credentials in the URL (`//user:token@`) are removed from that line.
- A Nightshift plan that edits `.github/workflows/` needs an SSH remote or a token with the `workflow` scope to push.
- The Nightshift skill's `add` section states the last two points, so a user queuing an item reads them.

## 7. Rollout

The last task of the plan, attended, with the owner's OK at each step. Every step lists its undo.

0. Precondition: the owner checks the repository's Actions settings page for an event policy that blocks `pull_request_target` (GitHub reportedly turns it off by default for public repositories from 2026-11-02; the REST API does not show it). When it would block, the owner allows the event for this repository, with its undo.
1. In the `Foundry` clone: `git config --local superpowers.requirePlans true`; copy `.github/hooks/pre-commit` and `.github/hooks/post-commit` to `$(git rev-parse --git-common-dir)/hooks/` with mode 755; confirm `core.hooksPath` is unset.
2. Write `CLAUDE.local.md` in the clone root with one line: "Every change in this repository is built from a written plan made with superpowers:writing-plans, committed before any code. Never take brainstorming's in-chat (bounded) path to skip it, never commit with --no-verify, and never push to the default branch." Add `CLAUDE.local.md` to `.git/info/exclude` once, so nothing is committed. Confirm a new Claude Code session loads it.
3. Set the repository variable `REQUIRE_PLANS=true` on `kferran/Foundry`.
4. Live proof of the commit check: a code commit on a scratch branch without a plan is blocked, from Claude Code and from a plain terminal, and in a worktree of a branch cut before this landed.
5. Live proof of the pull-request check, before it is required: a pull request without a plan and one with a plan each get a `require-plan` check run on their head commit (`gh api repos/<repo>/commits/<head sha>/check-runs`), concluding `failure` and `success`.
6. Branch protection: `require-plan` required on `master`. Then, with both pull requests marked ready, `gh pr view --json mergeStateStatus` prints `BLOCKED` for the one without a plan and `CLEAN` for the one with a plan.
7. The scratch branches and pull requests are deleted.

`minutes` gets the checker, shim and workflow through its own small plan after this one is merged; steps 1–4 for `minutes` wait for it. The README gains one line under the template-update section: a vault whose `origin` uses HTTPS with a `gh` token needs the `workflow` scope to push after this update, because the update adds `.github/workflows/`.

## 8. Testing

Bound tools: **bats**, **pytest**, the gate (`system/scripts/verify_setup.sh`), the live checks (§7 steps 4–6).

- `require_plan.bats`, against temporary repositories with a local bare `origin` whose default branch carries the checker:
  - the switch: off by default; `--local` true switches on; a global true does not; `REQUIRE_PLANS=true` switches on; `yes` reads as on; `REQUIRE_PLANS` empty or `false` is off;
  - commit mode through the installed shim, so the final index is checked: `git add` then `git commit`; `git commit -a`; an empty index; only specs or plans staged; code staged with no plan; a plan with the header changed on the branch; a plan without the header; a deleted plan; a staged plan read from the index while the working tree differs; a non-ASCII path;
  - the default branch: a spec-only commit is allowed; code alone and code staged with a plan are both blocked;
  - deletions: `git rm` of code plus a new spec on a branch with no plan is blocked; the same on the default branch is blocked; a pr-mode branch of that shape fails;
  - in progress: a merge, a stopped rebase and a conflicted cherry-pick are allowed, in the main checkout and in a worktree; after `git rebase --quit`, a code commit with no plan is blocked; a detached `HEAD` with a plan on its history is allowed and without one is blocked;
  - the judge: a worktree on a branch without `.github/` is still blocked; a branch whose `require_plan.sh` is `exit 0` is still blocked; a default branch without the checker allows;
  - the base chain: no `origin/HEAD` falls back to `origin/master`; none at all blocks with the `set-head` message; unborn `HEAD` blocks; a tag named `origin/master` does not replace the branch;
  - pr mode, workflows: a branch that edits `require-plan.yml` is blocked; a branch that adds another workflow naming `require-plan` is blocked; a branch whose other workflows do not name it is judged as usual;
  - pr mode: a plan on the branch; a plan-step-only branch; neither plan nor line; a valid `Plan:` line on a `nightshift/` head from the same repository; the same line from a fork (`--same-repo false`); the same line on another head; a line naming a path outside `plans/`, a path starting with `-`, a missing path, and a file without the marker; a CRLF body; a missing body file; a bad mode exits 2;
  - `--no-verify` logging: a `git commit --no-verify` with the switch on adds one line naming the commit; a normal commit, an amend that ran `pre-commit`, a cherry-pick and a rebase add none; the switch off adds none; a stale marker from an aborted commit does not hide a later `--no-verify` commit of a different tree;
  - the files: `.github/require_plan.sh`, `.github/hooks/pre-commit` and `.github/hooks/post-commit` are mode 100755 in git; the checker contains none of `mapfile`, `${x,,}`, `declare -A`, `[[ -v` (bash 3.2 for `minutes`);
  - the workflow, by text: the trigger is `pull_request_target`; `permissions` is `contents: read`; checkout sets `persist-credentials: false`; no `run:` block contains `${{`, and every `${{` line sets an `env:` name from a fixed list; `REQUIRE_PLANS` is never set to a literal `true`; the job has no `if:`; the check step starts with the `REQUIRE_PLANS` guard; the head is pinned to `head.sha` and set with `update-ref`, with no `checkout` of the pull request;
  - the test repositories ignore the host's system and XDG git config.
- pytest: the Nightshift `push.log` starts with the push command line, with credentials removed from the URL; the Nightshift pull request body's first line is `Plan: <plan path>` and a session-written `Plan:` line is removed; `nightshift_check` refuses a plan without the marker; the marker literal in `nightshift_check.py` equals the one in `require_plan.sh`.

## 9. Rulings (cost if wrong)

- R1. Commits that skip `pre-commit` (`--no-verify`, replays by cherry-pick, revert or rebase, a clone with `core.hooksPath` set, a clone not switched on) are not stopped locally. Cost: the work is caught at the pull request, after it was done. A `git commit --no-verify` is at least logged (§4.1); the other cases are not. The log is a record, not a control: setting `GIT_REFLOG_ACTION` hides a commit from it, and the file is writable by the user.
- R2. A fix pass on a merged plan must change the plan on its branch (for example, a fix-pass section) before its first code commit. Cost: one small plan edit per fix branch.
- R3. The checker, shim source and workflow ship to vaults but stay off. Cost: three unused files in every vault, and a notice line on any vault pull request on GitHub.
- R4. A merge, rebase, cherry-pick or revert in progress is allowed locally. Cost: code added by hand while resolving one is caught only at the pull request.
- R5. The commit check compares against the local `origin/<default>` ref, which can be stale. Cost: a wrong local answer; the pull-request check is authoritative.
- R6. The marker is superpowers 6.4.1 wording. Cost: if a later plugin version changes it, new plans fail closed until the one literal is updated.
- R7. A branch in the base repository named `nightshift/<x>` with a `Plan:` line naming any merged plan passes. Cost: anyone with push access can use it on purpose; `CLAUDE.local.md` and the owner's merge review are the guard.
- R8. Every Nightshift plan must carry the marker, Bitbucket codebases included. Cost: a plan written another way is refused at queue time.
- R9. A pull request that changes `require-plan.yml` or adds a workflow naming `require-plan` always fails the check (§3), so it merges only by the owner's admin override. Cost: a deliberate change to the check, by hand or by a Nightshift plan, needs that override; the owner's merge review is the only guard for it. A pull request that adds a passing check under another name is not covered, because only `require-plan` is required.
- R10. Branch protection leaves `enforce_admins` off, so any session running with the owner's credentials can push straight to `master`. Cost: such a push skips the check; `CLAUDE.local.md` tells sessions never to push to the default branch.

## 10. Out of scope

- Checking that a plan has an approved spec, or that it was reviewed.
- Repositories other than `Foundry` and `minutes`.
- Bitbucket pull requests.
- A Claude Code hook (dropped in rev 3; see §1).
