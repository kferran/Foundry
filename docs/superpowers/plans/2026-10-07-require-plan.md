# Require a Superpowers Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every change to `kferran/Foundry` (and later `kferran/minutes`) is built from a committed `superpowers:writing-plans` plan: a required pull-request check enforces it, a git shim stops a code commit early and logs `--no-verify`, and the Nightshift names its plan in every pull request it opens.

**Architecture:** One bash checker, `.github/require_plan.sh` (git and grep only), judges a commit (`commit` mode) or a pull request (`pr` mode). The judge is always the default branch's copy: the `pre-commit` shim reads it with `git show refs/remotes/origin/<default>:…`, and the `pull_request_target` workflow copies it out, then points `HEAD` at the pull request's commit as data without writing its files. Everything is off unless the clone's `--local` git config or the repository variable switches it on, so vaults made from the template carry the files and never run them. The Nightshift writes a runner-owned `Plan:` line first in its pull request body and refuses at queue time a plan the check would refuse.

**Tech Stack:** bash (3.2 compatible), git 2.39, grep, GitHub Actions (`pull_request_target`, `actions/checkout@v4`), Python 3.11 (`vaultlib`), bats 1.8.2, pytest, `gh` (rollout only).

**Spec:** `docs/superpowers/specs/2026-10-07-require-plan-design.md` (rev 4, approved: rev 3 plus the plan review's fixes)

## Global Constraints

- Work on branch `feat/require-plan` of `kferran/Foundry` (spec rev 4 at commit `4c44ad4`). Every task commits there. Tasks 1 to 4 never push, never open a pull request, never install a shim or set `superpowers.requirePlans` in the development clone, and never touch repository variables or branch protection; those are Task 5, attended.
- Tool floor: jq 1.6, bats 1.8.2, Python 3.11, git 2.39.
- The checker and both shims must run on bash 3.2 (the `minutes` repository runs on macOS): no `mapfile`, `readarray`, `${x,,}`, `${x^^}`, `declare -A`, `[[ -v`. The checker uses `git` and `grep` only.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. Read verdicts from exit codes (`run` then `[ "$status" -eq N ]`), never through a pipe.
- Template rule: never commit a hostname, user path, remote URL or distro choice. The workflow does not name the repository.
- The header marker is `REQUIRED SUB-SKILL: Use superpowers:` (superpowers 6.4.1). It appears once in the checker, as the line `MARKER='REQUIRED SUB-SKILL: Use superpowers:'`, and once in `nightshift_check.py` as `MARKER`; a test keeps them equal.
- The switch: `git config --local --type=bool --get superpowers.requirePlans` prints `true`, or the environment has exactly `REQUIRE_PLANS=true`. The shims honour only the git setting.
- Checker exit codes: 0 allowed, 1 blocked (one line on stderr starting `require_plan:`), 2 usage error.
- Run one suite as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh` from the repository root.
- Bound tools: bats (`system/tests/require_plan.bats`), pytest (`system/tests/python/test_nightshift_check.py`, `test_nightshift_deliver.py`, `test_nightshift_run.py`), the gate, and the live check in Task 5.
- Commits use `git commit -F .scratch/<file>`; every message ends with the line `Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm`.

## Review Focus

- `git commit <path>` while other code is staged commits only that path; the verdict must follow what is committed (git hands the hook a temporary index), so a spec committed this way is allowed and the code left staged is still blocked later. Pinned by `commit: git commit <path> is judged on what it commits, not on other staged code` (Task 1).
- A default-branch checker that cannot run (a syntax error, a bad merge) must block every commit, never allow. Pinned by `judge: a default-branch checker that cannot run blocks every commit` (Task 1).
- The `minutes` repository has `main` and a clone may lack `origin/HEAD`; the checker must find `origin/main` and treat `main` as the default branch. Pinned by `base: a repository whose default branch is main resolves origin/main` (Task 1).
- A `Plan:` line edited on GitHub may carry trailing spaces, and a hostile one may use `..` to point outside `plans/`: trailing spaces pass, `docs/superpowers/plans/../notes.md` fails (git refuses `..` in a tree path). Pinned by `pr: a CRLF body passes, trailing spaces pass, a missing body file fails` and `pr: a Plan: line must name a plan with the header under docs/superpowers/plans/ at HEAD` (Task 1).
- `git rebase --quit` leaves `REBASE_HEAD` behind; it must not read as a rebase in progress. Pinned by `in progress: a REBASE_HEAD left behind by git rebase --quit does not count` (Task 1).
- Deleting or renaming code beside a new spec must not pass as the plan step: the plan-step test reads `--no-renames` paths with deletions, the plan search reads `--diff-filter=ACMR`. Pinned by `deletions: removing or renaming code beside a new spec is a code change` (Task 1).
- A tag named `origin/master` must not stand in for the branch when `origin/HEAD` is missing: the base chain uses `refs/remotes/origin/…`. Pinned by `base: a tag named origin/master does not replace the branch` (Task 1).
- A pull request must not carry a `pull_request` workflow that reports a passing `require-plan` check. Pinned by `pr: a branch that changes require-plan.yml or adds a workflow naming require-plan is blocked` (Task 1).
- A `--no-verify` commit in a linked worktree must land in the clone's one log with the worktree's branch, and a `--no-verify` amend that keeps the tree must still be logged (the allow marker is used once). Pinned by `no-verify: a --no-verify commit in a worktree logs to the clone's common log with the worktree's branch` and `no-verify: the marker is used once, so a --no-verify amend that keeps the tree is logged` (Task 2).

---

## File Structure

| File | Responsibility |
|---|---|
| `.github/require_plan.sh` | the checker: switch, base chain, `commit` and `pr` modes (spec §3) |
| `.github/hooks/pre-commit` | tracked source of the shim that runs the default branch's checker and records the allowed tree (spec §4, §4.1) |
| `.github/hooks/post-commit` | tracked source of the shim that logs a `git commit` that skipped `pre-commit` (spec §4.1) |
| `.github/workflows/require-plan.yml` | the `require-plan` pull-request check (spec §5) |
| `system/tests/require_plan.bats` | checker, shim and workflow tests (spec §8) |
| `system/scripts/vaultlib/nightshift_check.py` (modify) | `MARKER`; `_plan` refuses a plan without it |
| `system/scripts/vaultlib/nightshift_deliver.py` (modify) | `push()` log starts with the push command |
| `system/scripts/vaultlib/nightshift_run.py` (modify) | `_deliver` writes `Plan: <plan>` first and drops the session's `Plan:` lines |
| `system/tests/python/test_nightshift_check.py`, `test_nightshift_deliver.py`, `test_nightshift_run.py` (modify) | Nightshift tests |
| `.claude/skills/nightshift/SKILL.md` (modify) | the `add` step names `--pr-base main` and the `workflow` scope (spec §6) |
| `README.md` (modify) | one line on the `workflow` scope an HTTPS push needs after this update |
| `CLAUDE.local.md` (untracked, Task 5 only) | the one instruction line per clone |

---

### Task 1: The checker and the `pre-commit` shim

**Files:**
- Create: `.github/require_plan.sh`, `.github/hooks/pre-commit`
- Test: `system/tests/require_plan.bats`

**Interfaces:**
- Produces: `bash .github/require_plan.sh commit` and `bash .github/require_plan.sh pr [--base <ref>] [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]`, exit 0/1/2. Block messages, verbatim:
  - `require_plan: no default branch for origin; run git remote set-head origin -a`
  - `require_plan: on <default> only docs/superpowers/specs/ and docs/superpowers/plans/ may be committed; work on a branch`
  - `require_plan: no merge base between <base> and HEAD (unborn HEAD or unrelated history)`
  - `require_plan: no superpowers plan on this branch; commit one under docs/superpowers/plans/ first`
  - `require_plan: no superpowers plan in this pull request; add one under docs/superpowers/plans/`
  - `require_plan: this pull request changes or adds a require-plan workflow; only the owner can merge it`
- Produces: the checker line `MARKER='REQUIRED SUB-SKILL: Use superpowers:'` (Task 4's test reads it).
- Produces for Tasks 2 and 3: the bats `setup` (a clone `$C` of a bare `$ORIGIN` built from `$SEED`, every file in `.github/hooks/` installed, switch on, branch `feat/x`) and helpers `plan_file <path>`, `spec_file`, `stage_code [path]`, `unchecked <commit args>` (a commit no hook sees), `pr <args>` (runs the checker in `pr` mode against `origin/master`), plus `$REPO`, `$CHECK`, `$SEED`, `$B`.

- [ ] **Step 1: Write the failing tests**

Create `system/tests/require_plan.bats` with exactly:

```bash
#!/usr/bin/env bats
# require_plan.sh and the git shims (require-plan spec §3, §4, §8). Every repository here is a temporary clone of
# a temporary bare origin whose master carries this branch's checker; HOME is temporary and the system and XDG
# configs are off, so no host git setting reaches the tests.

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  CHECK="$REPO/.github/require_plan.sh"
  export HOME="$BATS_TEST_TMPDIR/home" GIT_CONFIG_NOSYSTEM=1
  export XDG_CONFIG_HOME="$HOME/.config"
  mkdir -p "$HOME"
  export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
  unset REQUIRE_PLANS
  HEADER='> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan.'
  NOPLAN='require_plan: no superpowers plan on this branch; commit one under docs/superpowers/plans/ first'
  B="$BATS_TEST_TMPDIR/body.md"
  SEED="$BATS_TEST_TMPDIR/seed"
  ORIGIN="$BATS_TEST_TMPDIR/origin.git"
  C="$BATS_TEST_TMPDIR/clone"
  git init -q -b master "$SEED"
  echo base > "$SEED/README.md"
  git -C "$SEED" add README.md
  git -C "$SEED" commit -qm base
  git -C "$SEED" branch old                        # cut before the checker landed
  cp -R "$REPO/.github" "$SEED/.github"
  plan_file "$SEED/docs/superpowers/plans/merged.md"
  echo 'no header here' > "$SEED/docs/superpowers/plans/no-header.md"
  printf '%s\n' "$HEADER" > "$SEED/docs/notes.md"  # the marker, outside plans/
  git -C "$SEED" add -A
  git -C "$SEED" commit -qm checker
  git clone -q --bare "$SEED" "$ORIGIN"
  git -C "$SEED" remote add origin "$ORIGIN"
  git clone -q "$ORIGIN" "$C"
  git -C "$C" config superpowers.requirePlans true
  cp "$REPO"/.github/hooks/* "$C/.git/hooks/"
  cd "$C"
  git checkout -q -b feat/x
}

plan_file() { mkdir -p "$(dirname "$1")"; printf '# Plan\n\n%s\n' "$HEADER" > "$1"; }
spec_file() { mkdir -p docs/superpowers/specs; echo spec > docs/superpowers/specs/s.md; git add docs; }
stage_code() { echo "${2:-code}" > "${1:-app.sh}"; git add -- "${1:-app.sh}"; }
unchecked() { git -c core.hooksPath=/dev/null commit -q "$@"; }   # test setup only: no hook sees this commit
pr() { run bash "$CHECK" pr --base origin/master "$@"; }

@test "switch: off by default, on with a --local true or yes, never from a global setting" {
  stage_code
  unchecked -m code
  pr
  [ "$status" -eq 1 ]
  git config --unset superpowers.requirePlans
  pr
  [ "$status" -eq 0 ]
  git config --global superpowers.requirePlans true
  pr
  [ "$status" -eq 0 ]
  git config superpowers.requirePlans yes
  pr
  [ "$status" -eq 1 ]
}

@test "switch: REQUIRE_PLANS=true switches on; empty, false or True does not" {
  stage_code
  unchecked -m code
  git config --unset superpowers.requirePlans
  REQUIRE_PLANS=true pr
  [ "$status" -eq 1 ]
  for v in '' false True; do
    REQUIRE_PLANS="$v" pr
    [ "$status" -eq 0 ]
  done
}

@test "commit: code staged with no plan on the branch is blocked with the reason" {
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
  [ -z "$(git log --oneline origin/master..HEAD)" ]
}

@test "commit: only specs and plans staged is allowed (the plan step)" {
  spec_file
  plan_file docs/superpowers/plans/p.md
  git add docs
  run git commit -qm plan
  [ "$status" -eq 0 ]
}

@test "commit: git commit -a picks up code beside a staged spec and is blocked" {
  spec_file
  echo changed > README.md
  run git commit -aqm both
  [ "$status" -eq 1 ]
  run git commit -qm spec
  [ "$status" -eq 0 ]
}

@test "commit: git commit <path> is judged on what it commits, not on other staged code" {
  stage_code
  spec_file
  run git commit -qm spec -- docs/superpowers/specs/s.md
  [ "$status" -eq 0 ]
  run git commit -qm code
  [ "$status" -eq 1 ]
}

@test "commit: an empty commit on a branch without a plan is blocked" {
  run git commit -q --allow-empty -m empty
  [ "$status" -eq 1 ]
}

@test "commit: a plan with the header on the branch allows code; a plan without it does not" {
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  stage_code
  run git commit -qm code
  [ "$status" -eq 0 ]
  git checkout -q -b feat/y origin/master
  echo 'no header' > docs/superpowers/plans/q.md
  git add docs
  git commit -qm plan
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
}

@test "commit: a plan deleted on the branch no longer counts" {
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  git rm -q docs/superpowers/plans/p.md
  unchecked -m drop
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
}

@test "commit: a staged plan is read from the index, not the working tree" {
  mkdir -p docs/superpowers/plans
  echo 'no header yet' > docs/superpowers/plans/p.md
  git add docs
  plan_file docs/superpowers/plans/p.md            # the working tree has the header; the index does not
  stage_code
  run git commit -qm both
  [ "$status" -eq 1 ]
  git add docs
  run git commit -qm both
  [ "$status" -eq 0 ]
}

@test "commit: non-ASCII paths with spaces are read correctly" {
  plan_file "docs/superpowers/plans/plän ü.md"
  git add docs
  stage_code "skript ä.sh"
  run git commit -qm both
  [ "$status" -eq 0 ]
}

@test "default branch: a spec-only commit is allowed; code alone or with a plan is blocked" {
  git checkout -q master
  spec_file
  run git commit -qm spec
  [ "$status" -eq 0 ]
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: on master only docs/superpowers/specs/ and docs/superpowers/plans/ may be committed"* ]]
  plan_file docs/superpowers/plans/p.md
  git add docs
  run git commit -qm code
  [ "$status" -eq 1 ]
}

@test "deletions: removing or renaming code beside a new spec is a code change" {
  git rm -q README.md
  spec_file
  run git commit -qm drop
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
  unchecked -m drop
  pr
  [ "$status" -eq 1 ]
  git checkout -q -b moved origin/master
  mkdir -p docs/superpowers/specs
  git mv README.md docs/superpowers/specs/r.md
  run git commit -qm move
  [ "$status" -eq 1 ]
  git checkout -q -f master
  git rm -q README.md
  spec_file
  run git commit -qm drop
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: on master only"* ]]
}

conflict_branches() {  # branches b and c from origin/master, both changing README.md; neither has a plan
  git checkout -q -b b origin/master
  echo b > README.md
  unchecked -am b
  git checkout -q -b c origin/master
  echo c > README.md
  unchecked -am c
  git checkout -q --detach                         # frees c for a worktree
}

in_progress_cases() {  # run in a checkout of c: each operation stops on a conflict, then a plain git commit
  c0="$(git rev-parse HEAD)"
  run git merge -q b
  [ "$status" -eq 1 ]
  echo resolved > README.md
  git add README.md
  run git commit -q --no-edit
  [ "$status" -eq 0 ]
  git reset -q --hard "$c0"
  run git rebase -q b
  [ "$status" -eq 1 ]
  echo resolved > README.md
  git add README.md
  run git commit -qm resolved
  [ "$status" -eq 0 ]
  git rebase --abort
  run git cherry-pick b
  [ "$status" -eq 1 ]
  echo resolved > README.md
  git add README.md
  run git commit -q --no-edit
  [ "$status" -eq 0 ]
  git reset -q --hard "$c0"
  echo resolved > README.md                        # the same change with nothing in progress
  git add README.md
  run git commit -qm plain
  [ "$status" -eq 1 ]
}

@test "in progress: a conflicted merge, rebase or cherry-pick is allowed in the main checkout" {
  conflict_branches
  git checkout -q c
  in_progress_cases
}

@test "in progress: the same three are allowed in a worktree" {
  conflict_branches
  git worktree add -q "$BATS_TEST_TMPDIR/wt" c
  cd "$BATS_TEST_TMPDIR/wt"
  in_progress_cases
}

@test "in progress: a REBASE_HEAD left behind by git rebase --quit does not count" {
  conflict_branches
  git checkout -q c
  run git rebase -q b
  [ "$status" -eq 1 ]
  git rebase --quit
  git reset -q --hard
  [ -e "$(git rev-parse --git-path REBASE_HEAD)" ]
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
}

@test "detached HEAD: allowed with a plan on its history, blocked without" {
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  git checkout -q --detach
  stage_code
  run git commit -qm code
  [ "$status" -eq 0 ]
  git checkout -q --detach origin/master
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
}

@test "judge: a worktree of a branch cut before the checker landed is still blocked" {
  git worktree add -q -b old-work "$BATS_TEST_TMPDIR/old" origin/old
  cd "$BATS_TEST_TMPDIR/old"
  run test -e .github
  [ "$status" -eq 1 ]
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
}

@test "judge: a branch that guts its own checker is still blocked" {
  echo 'exit 0' > .github/require_plan.sh
  git add .github
  unchecked -m gut
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
}

@test "judge: a default branch without the checker allows" {
  git -C "$SEED" rm -q .github/require_plan.sh
  git -C "$SEED" commit -qm drop
  git -C "$SEED" push -q origin master
  git fetch -q origin
  stage_code
  run git commit -qm code
  [ "$status" -eq 0 ]
}

@test "judge: a default-branch checker that cannot run blocks every commit" {
  echo 'if then' > "$SEED/.github/require_plan.sh"
  git -C "$SEED" commit -qam broken
  git -C "$SEED" push -q origin master
  git fetch -q origin
  spec_file
  run git commit -qm spec
  [ "$status" -eq 1 ]
}

@test "base: without origin/HEAD the checker falls back to origin/master" {
  git remote set-head origin -d
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
  run bash "$CHECK" commit
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
}

@test "base: no default branch at all blocks with the set-head message" {
  git remote set-head origin -d
  git update-ref -d refs/remotes/origin/master
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: no default branch for origin; run git remote set-head origin -a"* ]]
  run bash "$CHECK" commit
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: no default branch for origin; run git remote set-head origin -a"* ]]
}

@test "base: a repository whose default branch is main resolves origin/main" {
  git remote set-head origin -d
  git update-ref refs/remotes/origin/main refs/remotes/origin/master
  git update-ref -d refs/remotes/origin/master
  git checkout -q -b main origin/main
  spec_file
  run git commit -qm spec
  [ "$status" -eq 0 ]
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: on main only"* ]]
}

@test "base: a tag named origin/master does not replace the branch" {
  git remote set-head origin -d                    # the fallback names origin/master
  git tag origin/master origin/old
  stage_code
  run git commit -qm code
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
  run bash "$CHECK" commit
  [ "$status" -eq 1 ]
}

@test "base: an unborn HEAD blocks" {
  git checkout -q --orphan fresh
  run git commit -qm first
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: no merge base"* ]]
}

@test "pr: a plan on the branch passes, a plan-step-only branch passes, neither fails" {
  stage_code
  unchecked -m code
  pr
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: no superpowers plan in this pull request"* ]]
  plan_file docs/superpowers/plans/p.md
  git add docs
  unchecked -m plan
  pr
  [ "$status" -eq 0 ]
  git checkout -q -b spec-only origin/master
  spec_file
  unchecked -m spec
  pr
  [ "$status" -eq 0 ]
}

@test "pr: a Plan: line passes only on a nightshift/ head from the same repository" {
  stage_code
  unchecked -m code
  printf 'Plan: docs/superpowers/plans/merged.md\n\nDid the work.\n' > "$B"
  pr --head-ref nightshift/x --same-repo true --body-file "$B"
  [ "$status" -eq 0 ]
  pr --head-ref nightshift/x --same-repo false --body-file "$B"
  [ "$status" -eq 1 ]
  pr --head-ref feat/x --same-repo true --body-file "$B"
  [ "$status" -eq 1 ]
  pr --head-ref nightshift/x --body-file "$B"
  [ "$status" -eq 1 ]
}

@test "pr: a Plan: line must name a plan with the header under docs/superpowers/plans/ at HEAD" {
  stage_code
  unchecked -m code
  for p in docs/notes.md --output=x docs/superpowers/plans/missing.md docs/superpowers/plans/no-header.md \
           docs/superpowers/plans/../notes.md; do
    printf 'Plan: %s\n' "$p" > "$B"
    pr --head-ref nightshift/x --same-repo true --body-file "$B"
    [ "$status" -eq 1 ]
  done
}

@test "pr: a CRLF body passes, trailing spaces pass, a missing body file fails" {
  stage_code
  unchecked -m code
  printf 'Plan: docs/superpowers/plans/merged.md\r\nDid it.\r\n' > "$B"
  pr --head-ref nightshift/x --same-repo true --body-file "$B"
  [ "$status" -eq 0 ]
  printf 'Plan: docs/superpowers/plans/merged.md  \n' > "$B"
  pr --head-ref nightshift/x --same-repo true --body-file "$B"
  [ "$status" -eq 0 ]
  pr --head-ref nightshift/x --same-repo true --body-file "$BATS_TEST_TMPDIR/none.md"
  [ "$status" -eq 1 ]
}

@test "pr: a branch that changes require-plan.yml or adds a workflow naming require-plan is blocked" {
  W=.github/workflows
  mkdir -p "$SEED/$W"
  printf 'name: require-plan\n' > "$SEED/$W/require-plan.yml"
  printf 'name: other\n' > "$SEED/$W/other.yml"
  git -C "$SEED" add -A
  git -C "$SEED" commit -qm workflows
  git -C "$SEED" push -q origin master
  git fetch -q origin
  git reset -q --hard origin/master
  plan_file docs/superpowers/plans/p.md
  git add docs
  unchecked -m plan
  echo 'on: push' >> "$W/other.yml"
  unchecked -am other
  pr
  [ "$status" -eq 0 ]
  echo '# edited' >> "$W/require-plan.yml"
  unchecked -am edit
  pr
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: this pull request changes or adds a require-plan workflow; only the owner can merge it"* ]]
  git reset -q --hard HEAD~1
  printf 'jobs:\n  require-plan:\n' > "$W/x.yml"
  git add "$W"
  unchecked -m forged
  pr
  [ "$status" -eq 1 ]
}

@test "usage: a bad mode or option exits 2" {
  run bash "$CHECK"
  [ "$status" -eq 2 ]
  run bash "$CHECK" push
  [ "$status" -eq 2 ]
  run bash "$CHECK" pr --same-repo maybe
  [ "$status" -eq 2 ]
  run bash "$CHECK" pr --base
  [ "$status" -eq 2 ]
  run bash "$CHECK" commit extra
  [ "$status" -eq 2 ]
}

@test "files: the checker and shims are mode 100755 in git and avoid bash 4 constructs" {
  for f in "$REPO"/.github/require_plan.sh "$REPO"/.github/hooks/*; do
    run git -C "$REPO" ls-files -s -- "${f#"$REPO"/}"
    [[ "$output" == 100755* ]]
    run grep -nE 'mapfile|readarray|\$\{[A-Za-z_][A-Za-z0-9_]*(,,|\^\^)|declare -A|\[\[ -v' "$f"
    [ "$status" -eq 1 ]
  done
}
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `mkdir -p .scratch/tmp && TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: FAIL, all 33 tests, each in `setup` with `cp: cannot stat '<repo>/.github/hooks/*': No such file or directory`.

- [ ] **Step 3: Write the checker**

Create `.github/require_plan.sh` with exactly:

```bash
#!/usr/bin/env bash
# Allows a change only when it carries a superpowers plan (require-plan spec §3).
# Usage: require_plan.sh commit
#        require_plan.sh pr [--base <ref>] [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]
# Exit 0 allowed, 1 blocked (one "require_plan:" line on stderr), 2 usage error. git and grep only; bash 3.2 safe.
MARKER='REQUIRED SUB-SKILL: Use superpowers:'
PLANS='docs/superpowers/plans/'
SPECS='docs/superpowers/specs/'

block() { printf 'require_plan: %s\n' "$1" >&2; exit 1; }
usage() {
  printf 'usage: require_plan.sh commit | pr [--base <ref>] [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]\n' >&2
  exit 2
}

# The switch: a --local git setting or exactly REQUIRE_PLANS=true; anything else allows at once.
if [ "$(git config --local --type=bool --get superpowers.requirePlans 2>/dev/null)" != true ] &&
   [ "${REQUIRE_PLANS-}" != true ]; then
  exit 0
fi

mode=${1-}
shift
base='' head_ref='' same=false body=''
case $mode in
  commit) [ $# -eq 0 ] || usage ;;
  pr)
    while [ $# -gt 0 ]; do
      [ $# -ge 2 ] || usage
      case $1 in
        --base) base=$2 ;;
        --head-ref) head_ref=$2 ;;
        --same-repo) case $2 in true|false) same=$2 ;; *) usage ;; esac ;;
        --body-file) body=$2 ;;
        *) usage ;;
      esac
      shift 2
    done ;;
  *) usage ;;
esac

# is_plan <rev> <path>: the path is under plans/ and its text at <rev> (":" is the index) has the marker.
is_plan() {
  case $2 in "$PLANS"*) ;; *) return 1 ;; esac
  git cat-file blob "$1$2" 2>/dev/null | grep -qF -- "$MARKER"
}

# plan_step: the NUL-separated paths on stdin are non-empty and all under specs/ or plans/.
plan_step() {
  local p seen=''
  while IFS= read -r -d '' p; do
    case $p in "$SPECS"*|"$PLANS"*) seen=1 ;; *) return 1 ;; esac
  done
  [ -n "$seen" ]
}

# has_plan <rev>: one of the NUL-separated paths on stdin is a plan at <rev>.
has_plan() {
  local p
  while IFS= read -r -d '' p; do
    if is_plan "$1" "$p"; then return 0; fi
  done
  return 1
}

# The plan-step test reads every changed path (deletions, and both sides of a rename); the plan search reads only
# paths that exist after the change, so a deleted plan does not count.
staged_all() { git diff --cached -z --name-only --no-renames; }
staged() { git diff --cached -z --name-only --diff-filter=ACMR; }
branch_all() { git diff -z --name-only --no-renames "$mb" HEAD; }
branch_changes() { git diff -z --name-only --diff-filter=ACMR "$mb" HEAD; }

# The base: --base, else origin/HEAD, else origin/master, else origin/main, by full name (a tag cannot stand in).
if [ -z "$base" ]; then
  base=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
  for b in "$base" refs/remotes/origin/master refs/remotes/origin/main; do
    if [ -n "$b" ] && git rev-parse --verify --quiet "$b^{commit}" >/dev/null; then base=$b; break; fi
    base=''
  done
  [ -n "$base" ] || block 'no default branch for origin; run git remote set-head origin -a'
fi

if [ "$mode" = commit ]; then
  # A merge, rebase, cherry-pick or revert in progress is left to the pull-request check. Not REBASE_HEAD:
  # git rebase --quit leaves it behind, and a real rebase always has one of the two folders.
  for f in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
    if [ -e "$(git rev-parse --git-path "$f")" ]; then exit 0; fi
  done
  if staged_all | plan_step; then exit 0; fi
  default=${base#refs/remotes/origin/}
  if [ "$(git symbolic-ref --quiet --short HEAD)" = "$default" ]; then
    block "on $default only $SPECS and $PLANS may be committed; work on a branch"
  fi
fi

mb=$(git merge-base "$base" HEAD 2>/dev/null) ||
  block "no merge base between $base and HEAD (unborn HEAD or unrelated history)"

if [ "$mode" = commit ]; then
  if branch_changes | has_plan HEAD: || staged | has_plan :; then exit 0; fi
  block "no superpowers plan on this branch; commit one under $PLANS first"
fi

# A pull_request workflow from the pull request could report a passing check under the same name.
wf=.github/workflows/
if ! git diff --quiet "$mb" HEAD -- "${wf}require-plan.yml" ||
   git grep -qF require-plan HEAD -- "$wf" ":(exclude)${wf}require-plan.yml"; then
  block 'this pull request changes or adds a require-plan workflow; only the owner can merge it'
fi
if branch_all | plan_step || branch_changes | has_plan HEAD:; then exit 0; fi
# A Nightshift pull request names its plan on a "Plan: <path>" line instead (spec §3, pr mode).
case $head_ref in
  nightshift/*)
    if [ "$same" = true ] && [ -n "$body" ] && [ -f "$body" ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case $line in
          'Plan: '*)
            path=${line#Plan: }
            path=${path%% *}
            if is_plan HEAD: "$path"; then exit 0; fi
            break ;;
        esac
      done <"$body"
    fi ;;
esac
block "no superpowers plan in this pull request; add one under $PLANS"
```

- [ ] **Step 4: Write the `pre-commit` shim**

Create `.github/hooks/pre-commit` with exactly:

```bash
#!/usr/bin/env bash
# git pre-commit shim (require-plan spec §4): runs the default branch's copy of .github/require_plan.sh, so a branch
# cannot weaken the check that judges it. Install by copying into "$(git rev-parse --git-common-dir)/hooks/".
[ "$(git config --local --type=bool --get superpowers.requirePlans 2>/dev/null)" = true ] || exit 0
base=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
for b in "$base" refs/remotes/origin/master refs/remotes/origin/main; do
  if [ -n "$b" ] && git rev-parse --verify --quiet "$b^{commit}" >/dev/null; then base=$b; break; fi
  base=''
done
if [ -z "$base" ]; then
  echo 'require_plan: no default branch for origin; run git remote set-head origin -a' >&2
  exit 1
fi
checker=$(mktemp) || exit 1
trap 'rm -f "$checker"' EXIT
git show "$base:.github/require_plan.sh" >"$checker" 2>/dev/null || exit 0
bash "$checker" commit
```

- [ ] **Step 5: Make both executable and stage them** (the `files:` test reads the mode from the index)

Run: `chmod +x .github/require_plan.sh .github/hooks/pre-commit && git add .github/require_plan.sh .github/hooks/pre-commit system/tests/require_plan.bats`

- [ ] **Step 6: Run the suite to verify it passes**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: PASS, `1..33`, no `not ok`.

- [ ] **Step 7: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(require-plan): checker and pre-commit shim

.github/require_plan.sh allows a commit or pull request only when it
carries a superpowers plan; .github/hooks/pre-commit runs the default
branch's copy of it. Both stay off unless the clone switches them on.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git commit -q -F .scratch/msg-1.txt`

---

### Task 2: Log every `git commit --no-verify` (spec §4.1)

**Files:**
- Create: `.github/hooks/post-commit`
- Modify: `.github/hooks/pre-commit` (whole file below)
- Test: `system/tests/require_plan.bats` (append)

**Interfaces:**
- Consumes: Task 1's bats `setup` and helpers; the checker's exit status.
- Produces: the allow marker `$(git rev-parse --git-path require-plan-checked)` (one line, the `git write-tree` of the allowed index; written by `pre-commit` on allow, also when the default branch has no checker; removed by `post-commit` after every `git commit`), and the log `$(git rev-parse --git-common-dir)/require-plan.log`, one line per skipped commit: `<UTC time, YYYY-MM-DDTHH:MM:SSZ>\t<branch or detached>\t<commit sha>\tpre-commit skipped (--no-verify)`.

- [ ] **Step 1: Write the failing tests**

Append to the end of `system/tests/require_plan.bats`, after one blank line:

```bash

# --no-verify logging (spec §4.1)
log_file() { echo "$(git rev-parse --git-common-dir)/require-plan.log"; }

@test "no-verify: a git commit --no-verify adds one line naming the commit" {
  stage_code
  git commit -q --no-verify -m skipped
  [ "$(wc -l < "$(log_file)")" -eq 1 ]
  IFS=$'\t' read -r when branch sha what < "$(log_file)"
  [[ "$when" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
  [ "$branch" = feat/x ]
  [ "$sha" = "$(git rev-parse HEAD)" ]
  [ "$what" = 'pre-commit skipped (--no-verify)' ]
}

@test "no-verify: a normal commit and an amend that ran pre-commit add no line" {
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  stage_code
  git commit -q --amend -m 'plan and code'
  run test -e "$(log_file)"
  [ "$status" -eq 1 ]
}

@test "no-verify: a cherry-pick and a rebase add no line" {
  git checkout -q -b other origin/master
  echo other > other.txt
  git add other.txt
  unchecked -m other
  git checkout -q feat/x
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  git cherry-pick other
  git rebase -q other
  run test -e "$(log_file)"
  [ "$status" -eq 1 ]
}

@test "no-verify: with the switch off nothing is logged" {
  git config --unset superpowers.requirePlans
  stage_code
  git commit -q --no-verify -m skipped
  run test -e "$(log_file)"
  [ "$status" -eq 1 ]
}

@test "no-verify: a stale marker from an aborted commit does not hide a later --no-verify commit" {
  spec_file
  run git commit -q -m ''
  [ "$status" -eq 1 ]
  [ -s "$(git rev-parse --git-path require-plan-checked)" ]
  stage_code
  git commit -q --no-verify -m code
  [ "$(wc -l < "$(log_file)")" -eq 1 ]
}

@test "no-verify: the marker is used once, so a --no-verify amend that keeps the tree is logged" {
  spec_file
  git commit -qm spec
  git commit -q --amend --no-verify -m 'spec, reworded'
  [ "$(wc -l < "$(log_file)")" -eq 1 ]
}

@test "no-verify: a --no-verify commit in a worktree logs to the clone's common log with the worktree's branch" {
  git worktree add -q -b wt-branch "$BATS_TEST_TMPDIR/wt" origin/master
  cd "$BATS_TEST_TMPDIR/wt"
  stage_code
  git commit -q --no-verify -m skipped
  IFS=$'\t' read -r when branch sha what < "$C/.git/require-plan.log"
  [ "$branch" = wt-branch ]
  [ "$sha" = "$(git rev-parse HEAD)" ]
}
```

- [ ] **Step 2: Run the suite to verify the new tests fail**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: FAIL, 4 of 40: `no-verify: a git commit --no-verify adds one line naming the commit` (`.git/require-plan.log: No such file or directory`), `no-verify: a stale marker from an aborted commit does not hide a later --no-verify commit` (the `[ -s … require-plan-checked ]` line), `no-verify: the marker is used once, …` and `no-verify: a --no-verify commit in a worktree …`. The three "add no line" tests pass already (nothing logs yet); they guard against over-logging once Step 4 lands.

- [ ] **Step 3: Replace `.github/hooks/pre-commit`** with exactly:

```bash
#!/usr/bin/env bash
# git pre-commit shim (require-plan spec §4): runs the default branch's copy of .github/require_plan.sh, so a branch
# cannot weaken the check that judges it. Install by copying into "$(git rev-parse --git-common-dir)/hooks/".
[ "$(git config --local --type=bool --get superpowers.requirePlans 2>/dev/null)" = true ] || exit 0
base=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
for b in "$base" refs/remotes/origin/master refs/remotes/origin/main; do
  if [ -n "$b" ] && git rev-parse --verify --quiet "$b^{commit}" >/dev/null; then base=$b; break; fi
  base=''
done
if [ -z "$base" ]; then
  echo 'require_plan: no default branch for origin; run git remote set-head origin -a' >&2
  exit 1
fi
checker=$(mktemp) || exit 1
trap 'rm -f "$checker"' EXIT
if git show "$base:.github/require_plan.sh" >"$checker" 2>/dev/null; then
  bash "$checker" commit || exit
fi
# Allowed: record the tree, so post-commit can tell this commit from one made with --no-verify (spec §4.1).
git write-tree >"$(git rev-parse --git-path require-plan-checked)" 2>/dev/null
exit 0
```

- [ ] **Step 4: Write `.github/hooks/post-commit`** with exactly:

```bash
#!/usr/bin/env bash
# git post-commit shim (require-plan spec §4.1): logs a git commit that skipped pre-commit (--no-verify) to
# "$(git rev-parse --git-common-dir)/require-plan.log". Never fails the commit. Install beside pre-commit.
[ "$(git config --local --type=bool --get superpowers.requirePlans 2>/dev/null)" = true ] || exit 0
marker=$(git rev-parse --git-path require-plan-checked)
case $(git reflog -1 --format=%gs HEAD 2>/dev/null) in
  commit*)
    if [ "$(cat "$marker" 2>/dev/null)" != "$(git rev-parse 'HEAD^{tree}')" ]; then
      printf '%s\t%s\t%s\tpre-commit skipped (--no-verify)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$(git symbolic-ref --quiet --short HEAD || echo detached)" "$(git rev-parse HEAD)" \
        >>"$(git rev-parse --git-common-dir)/require-plan.log"
    fi
    rm -f "$marker" ;;
esac
exit 0
```

- [ ] **Step 5: Make it executable and stage**

Run: `chmod +x .github/hooks/post-commit && git add .github/hooks/pre-commit .github/hooks/post-commit system/tests/require_plan.bats`

- [ ] **Step 6: Run the suite to verify it passes**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: PASS, `1..40`, no `not ok`.

- [ ] **Step 7: Commit**

Write `.scratch/msg-2.txt`:

```text
feat(require-plan): log every git commit made with --no-verify

pre-commit records the tree it allowed; .github/hooks/post-commit appends
a line to the clone's require-plan.log for a git commit whose tree pre-commit
never saw.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git commit -q -F .scratch/msg-2.txt`

---

### Task 3: The pull-request check workflow and the README line

**Files:**
- Create: `.github/workflows/require-plan.yml`
- Modify: `README.md` (section "Updating and uninstalling")
- Test: `system/tests/require_plan.bats` (append)

**Interfaces:**
- Consumes: Task 1's checker `pr` mode and its options; `$REPO` from the bats `setup`.
- Produces: the workflow `require-plan` with job id `require-plan`, which is the check name Task 5 makes required. Its last step returns at once unless `REQUIRE_PLANS` is exactly `true`, then runs `bash "$RUNNER_TEMP/require_plan.sh" pr --base "refs/remotes/origin/$BASE_REF" --head-ref "$HEAD_REF" --same-repo <true|false> --body-file "$RUNNER_TEMP/body.md"` with `REQUIRE_PLANS` from `vars.REQUIRE_PLANS`.

- [ ] **Step 1: Write the failing tests**

Append to the end of `system/tests/require_plan.bats`, after one blank line:

```bash
# The pull-request workflow, by text (spec §5)
@test "workflow: pull_request_target only, contents read, checkout keeps no credentials" {
  W="$REPO/.github/workflows/require-plan.yml"
  grep -qxF '  pull_request_target:' "$W"
  grep -qxF '    types: [opened, synchronize, reopened, edited]' "$W"
  run grep -nE '^  (pull_request|push|workflow_run|workflow_dispatch):' "$W"
  [ "$status" -eq 1 ]
  grep -qxF '  contents: read' "$W"
  run grep -nE 'write' "$W"
  [ "$status" -eq 1 ]
  grep -qxF '          persist-credentials: false' "$W"
}

@test "workflow: every expression sets a listed env name, so none reaches a run block" {
  W="$REPO/.github/workflows/require-plan.yml"
  run grep -nF '${{' "$W"
  [ "${#lines[@]}" -ge 2 ]
  names='REQUIRE_PLANS|DEFAULT_BRANCH|BASE_REF|HEAD_REF|HEAD_SHA|HEAD_REPO|BASE_REPO|PR_NUMBER|PR_BODY'
  for l in "${lines[@]}"; do
    [[ "$l" =~ ^[0-9]+:\ +($names):\ \$\{\{\ [A-Za-z0-9_.]+\ \}\}$ ]]
  done
}

@test "workflow: REQUIRE_PLANS is never a literal true and nothing is skipped by if:" {
  W="$REPO/.github/workflows/require-plan.yml"
  run grep -nE "REQUIRE_PLANS: *['\"]?true" "$W"
  [ "$status" -eq 1 ]
  run grep -nE '^ *if:' "$W"
  [ "$status" -eq 1 ]
  grep -qF 'REQUIRE_PLANS: ${{ vars.REQUIRE_PLANS }}' "$W"
}

@test "workflow: the check step ends green before the fetch when switched off" {
  W="$REPO/.github/workflows/require-plan.yml"
  run awk '/^        run: \|$/ { getline; first = $0 } END { print first }' "$W"
  [ "$output" = '          [ "$REQUIRE_PLANS" = true ] || exit 0' ]
}

@test "workflow: the head is pinned to the event's sha and no pull request file is checked out" {
  W="$REPO/.github/workflows/require-plan.yml"
  grep -qxF '          HEAD_SHA: ${{ github.event.pull_request.head.sha }}' "$W"
  grep -qF '[ "$(git rev-parse FETCH_HEAD)" = "$HEAD_SHA" ]' "$W"
  grep -qxF '          git update-ref --no-deref HEAD "$HEAD_SHA"' "$W"
  run grep -nE '^ +git .*(checkout|switch)' "$W"
  [ "$status" -eq 1 ]
}
```

- [ ] **Step 2: Run the suite to verify the new tests fail**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: FAIL, the 5 `workflow:` tests (`grep: …/.github/workflows/require-plan.yml: No such file or directory`); the other 40 pass.

- [ ] **Step 3: Write the workflow**

Create `.github/workflows/require-plan.yml` with exactly:

```yaml
# The pull-request check (require-plan spec §5): fails a pull request that carries no superpowers plan.
# It runs the default branch's .github/require_plan.sh on the pull request's commits, read as data; nothing from
# the pull request is executed or written to disk. Off unless the repository variable REQUIRE_PLANS is exactly true.
name: require-plan

on:
  pull_request_target:
    types: [opened, synchronize, reopened, edited]

permissions:
  contents: read

jobs:
  require-plan:
    runs-on: ubuntu-latest
    steps:
      - name: Report the switch
        env:
          REQUIRE_PLANS: ${{ vars.REQUIRE_PLANS }}
        run: |
          if [ "$REQUIRE_PLANS" != true ]; then
            echo "::notice::require-plan is switched off (REQUIRE_PLANS=$REQUIRE_PLANS)"
          fi
      - name: Check out the default branch
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - name: Check the pull request
        env:
          REQUIRE_PLANS: ${{ vars.REQUIRE_PLANS }}
          DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}
          BASE_REF: ${{ github.event.pull_request.base.ref }}
          HEAD_REF: ${{ github.event.pull_request.head.ref }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
          HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}
          BASE_REPO: ${{ github.event.pull_request.base.repo.full_name }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          PR_BODY: ${{ github.event.pull_request.body }}
        run: |
          [ "$REQUIRE_PLANS" = true ] || exit 0
          git show "refs/remotes/origin/$DEFAULT_BRANCH:.github/require_plan.sh" > "$RUNNER_TEMP/require_plan.sh"
          git fetch -q --no-tags origin "refs/pull/$PR_NUMBER/head"
          if [ "$(git rev-parse FETCH_HEAD)" = "$HEAD_SHA" ]; then :; else
            echo "::error::the pull request moved since this event; the newer push gets its own run"
            exit 1
          fi
          # HEAD names the pull request's commit, read as data; the working tree stays the default branch's.
          git update-ref --no-deref HEAD "$HEAD_SHA"
          printf '%s\n' "$PR_BODY" > "$RUNNER_TEMP/body.md"
          same=false
          if [ "$HEAD_REPO" = "$BASE_REPO" ]; then same=true; fi
          bash "$RUNNER_TEMP/require_plan.sh" pr --base "refs/remotes/origin/$BASE_REF" --head-ref "$HEAD_REF" \
            --same-repo "$same" --body-file "$RUNNER_TEMP/body.md"
```

Notes for the reviewer: `pull_request_target` runs this file and checks out the commit from the default branch, so a pull request cannot edit its own check. The pull request's commit is fetched as data (`refs/pull/<n>/head`, public repository, no credentials kept), compared with the event's `head.sha`, and named by `HEAD` through `git update-ref`; no file from it is written and only the default branch's checker runs. A step's `exit 0` does not end a job, so the switch guard is the first line of the last step (a switched-off repository, such as a private vault whose fetch would fail, ends green before the fetch) and the checker keeps its own switch; no step or job has an `if:`.

- [ ] **Step 4: Add the README line**

In `README.md`, section `## Updating and uninstalling`, insert this bullet directly after the `- **Pull template updates:** …` bullet:

```markdown
- **Pushing after the update that adds `.github/workflows/`:** a vault whose `origin` uses HTTPS with a `gh` token needs the token's `workflow` scope to push (`gh auth refresh -s workflow`). The workflow and the plan checker stay off in a vault.
```

- [ ] **Step 5: Run the suite to verify it passes**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: PASS, `1..45`, no `not ok`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-3.txt`:

```text
feat(require-plan): pull-request check workflow

.github/workflows/require-plan.yml runs the default branch's checker on
every pull request (pull_request_target, contents: read, the pull request
read as data). The README notes the workflow scope a vault's HTTPS push
needs after this update.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git add .github/workflows/require-plan.yml system/tests/require_plan.bats README.md && git commit -q -F .scratch/msg-3.txt`

---

### Task 4: The Nightshift names its plan, checks the header and records its push

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py` (constants; `_plan`), `system/scripts/vaultlib/nightshift_deliver.py` (`push`), `system/scripts/vaultlib/nightshift_run.py` (imports; `_deliver`), `.claude/skills/nightshift/SKILL.md` (the `add` step)
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_deliver.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: the checker line `MARKER='REQUIRED SUB-SKILL: Use superpowers:'` (Task 1).
- Produces: `nightshift_check.MARKER: str`; `_plan` adds the error `plan <path> lacks the writing-plans header ('REQUIRED SUB-SKILL: Use superpowers:'); the pull-request check would refuse it`; `nightshift_deliver.push(runner_repo, sha, branch, url) -> (ok, log)` whose log's first line is `git push --no-verify <url> <sha>:refs/heads/<branch>`, with any `//user:token@` in the URL reduced to `//`; `_deliver` writes `pr_body.md` as `Plan: <fm["plan"]>`, a blank line, the session's body with every line matching `^[ \t]*plan:` (any case) removed, then the existing "Queued as" line.

Every edit below is a find-and-replace of exact text; each "Find" text occurs once in its file.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_nightshift_check.py`, find:

```python
from helpers import write
```

Replace with:

```python
from helpers import REPO, write
```

Find:

```python
PLAN = """# P
### Task 1: Schema
```

Replace with (the fixture plan gains the `writing-plans` header, so the existing ready-plan tests stay green):

```python
PLAN = """# P
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan.
### Task 1: Schema
```

Append to the end of the file, after two blank lines:

```python
def test_plan_without_the_writing_plans_header_is_refused(vault_repo):
    write(vault_repo, "docs/q.md", PLAN.replace(nc.MARKER, "Use the plan"))
    git(vault_repo, "add", "docs/q.md")
    git(vault_repo, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "q")
    errs = nc.check(vault_repo, plan_fm(base="master", plan="docs/q.md", tasks="1-2"), "")
    assert any("writing-plans header" in e for e in errs)
    assert nc.check(vault_repo, plan_fm(base="master", tasks="1-2"), "") == []


def test_marker_is_the_checkers_literal():
    assert f"\nMARKER='{nc.MARKER}'\n" in (REPO / ".github" / "require_plan.sh").read_text()
```

In `system/tests/python/test_nightshift_deliver.py`, inside `test_fetch_push_and_github_pr`, find:

```python
    ok, log = nd.push(runner, sha, "nightshift/x", str(remote))
    assert ok, log
```

Replace with:

```python
    ok, log = nd.push(runner, sha, "nightshift/x", str(remote))
    assert ok, log
    assert log.splitlines()[0] == f"git push --no-verify {remote} {sha}:refs/heads/nightshift/x"
```

Append to the end of `system/tests/python/test_nightshift_deliver.py`, after two blank lines:

```python
def test_push_log_drops_credentials_from_the_url(tmp_path, monkeypatch):
    monkeypatch.setattr(nd.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    ok, log = nd.push(tmp_path / "runner.git", "abc", "nightshift/x", "https://user:tok@example.com/o/r.git")
    assert ok
    assert log.splitlines()[0] == "git push --no-verify https://example.com/o/r.git abc:refs/heads/nightshift/x"
```

Append to the end of `system/tests/python/test_nightshift_run.py`, after two blank lines:

```python
def test_pr_body_starts_with_the_plan_line_and_drops_the_sessions(vault: Path, tmp_path: Path, monkeypatch):
    idir = tmp_path / "item"
    idir.mkdir()
    (idir / "delivery.json").write_text(json.dumps({
        "sha": "abc", "branch": "nightshift/a", "title": "T", "summary": "s", "tries": 0,
        "body": "Plan: docs/superpowers/plans/other.md\r\nDid it.\n  plan: also this\nPlanned more.\n"}))
    monkeypatch.setattr(nr.nd, "push_target", lambda vault, fm: ("u", "github:o/r"))
    monkeypatch.setattr(nr.nd, "push", lambda *a: (True, "git push --no-verify u abc:refs/heads/nightshift/a\n"))
    seen = {}

    def open_pr(pr, branch, base, title, body_file, push_log):
        seen["body"] = Path(body_file).read_text()
        return True, "https://github.com/o/r/pull/1"
    monkeypatch.setattr(nr.nd, "open_pr", open_pr)
    out = nr._deliver(nr.Ctx(vault, NOW), {"id": "a", "plan": "docs/superpowers/plans/p.md"}, idir)
    assert out["state"] == "done"
    lines = seen["body"].splitlines()
    assert lines[0] == "Plan: docs/superpowers/plans/p.md"
    assert [ln for ln in lines if ln.strip().lower().startswith("plan:")] == [lines[0]]
    assert "Did it." in lines and "Planned more." in lines
    assert (idir / "push.log").read_text().startswith("git push --no-verify u abc:refs/heads/nightshift/a\n")

```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch python3 -m pytest system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py -q`
Expected: FAIL, `5 failed, 52 passed`: `test_plan_without_the_writing_plans_header_is_refused` and `test_marker_is_the_checkers_literal` (`AttributeError: module 'vaultlib.nightshift_check' has no attribute 'MARKER'`), `test_fetch_push_and_github_pr` and `test_push_log_drops_credentials_from_the_url` (the first log line is the push output), `test_pr_body_starts_with_the_plan_line_and_drops_the_sessions` (`assert 'Plan: docs/s...lans/other.md' == 'Plan: docs/s...rs/plans/p.md'`).

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/nightshift_check.py`, find:

```python
HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
```

Replace with:

```python
HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
MARKER = "REQUIRED SUB-SKILL: Use superpowers:"   # the writing-plans header; equal to MARKER in .github/require_plan.sh
```

Find (in `_plan`):

```python
    blocks = task_blocks(shown.stdout)
    if not blocks:
```

Replace with:

```python
    if MARKER not in shown.stdout:
        errs.append(f"plan {plan} lacks the writing-plans header ({MARKER!r}); the pull-request check would refuse it")
    blocks = task_blocks(shown.stdout)
    if not blocks:
```

In `system/scripts/vaultlib/nightshift_deliver.py`, find (the end of `push`):

```python
    p = subprocess.run(cmd + ["push", "--no-verify", url, f"{sha}:refs/heads/{branch}"],
                       capture_output=True, text=True, env=env)
    return p.returncode == 0, p.stdout + p.stderr
```

Replace with:

```python
    args = ["push", "--no-verify", url, f"{sha}:refs/heads/{branch}"]
    p = subprocess.run(cmd + args, capture_output=True, text=True, env=env)
    shown = re.sub(r"//[^/@]+@", "//", " ".join(args))   # no credentials in the log (spec §6)
    return p.returncode == 0, f"git {shown}\n" + p.stdout + p.stderr   # the log names every --no-verify push
```

In `system/scripts/vaultlib/nightshift_run.py`, find:

```python
import os
import shutil
```

Replace with:

```python
import os
import re
import shutil
```

Find (in `_deliver`):

```python
        body.write_text(f"{d['body']}\n\nQueued as Nightshift item `{fm['id']}`.\n")
```

Replace with:

```python
        text = re.sub(r"(?im)^[ \t]*plan:.*\n?", "", d["body"])   # the runner's Plan: line is the only one (spec §6)
        body.write_text(f"Plan: {fm['plan']}\n\n{text}\n\nQueued as Nightshift item `{fm['id']}`.\n")
```

In `.claude/skills/nightshift/SKILL.md`, find (the `add` step's run line):

```markdown
--verify "<cmd>" … [--now | --at HH:MM] [--budget] [--model]`. Exit 2 lists what is not ready: report it and stop.
```

Replace with:

```markdown
--verify "<cmd>" … [--now | --at HH:MM] [--budget] [--model]`. Exit 2 lists what is not ready: report it and stop.
   - `--pr-base` defaults to `master`; a repository whose default branch is `main` needs `--pr-base main`.
   - A plan that edits `.github/workflows/` needs an SSH remote or a token with the `workflow` scope, or the push is refused.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch python3 -m pytest system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py -q`
Expected: PASS, `57 passed`.

- [ ] **Step 5: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0; the summary lists `PASS system/tests/require_plan.bats` and `PASS pytest system/tests/python`, and no `FAIL`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-4.txt`:

```text
feat(nightshift): Plan: line, plan header check, push command on record

The pull request body for a plan item starts with the runner's Plan: line
and drops any the session wrote; queueing refuses a plan without the
writing-plans header; push.log starts with the git push --no-verify
command, with credentials removed from the URL. The skill's add step
names --pr-base main and the workflow scope a push may need.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_deliver.py system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py .claude/skills/nightshift/SKILL.md && git commit -q -F .scratch/msg-4.txt`

---

### Task 5: Rollout on `kferran/Foundry` (attended; owner only)

**Not runnable by an executor, a subagent or the Nightshift.** Every step changes the owner's clone, the GitHub repository or its settings, and each one needs the owner's explicit OK before it runs. Each step lists its undo. Stop and report at the first surprise. The Nightshift's readiness check refuses this task (it works on `master`); queue Tasks 1 to 4 only.

**Files:** none tracked. Untracked: `CLAUDE.local.md` in the clone root, the installed shims under `$(git rev-parse --git-common-dir)/hooks/`, an `info/exclude` line.

**Interfaces:**
- Consumes: Tasks 1 to 4 merged to `master` through a pull request the owner reviewed and merged (before this lands nothing enforces it, so this one pull request is judged by the owner alone).

- [ ] **Step 1: Preconditions (owner's OK)**

In the development clone of `kferran/Foundry`:

```bash
git fetch origin
git remote set-head origin -a
git cat-file -e refs/remotes/origin/master:.github/require_plan.sh && echo checker-on-master
git config --get core.hooksPath; echo "hooksPath exit $?"
```

Expected: `checker-on-master`, and `hooksPath exit 1` with nothing printed before it (unset). If `core.hooksPath` is set, stop: the shim would never run.

The owner then opens the repository's **Settings → Actions → General** page in a browser and reads its workflow event policy. GitHub reportedly turns `pull_request_target` off by default for public repositories from 2026-11-02 (in evaluate mode before that); the REST API does not show this policy. If the page shows a policy that blocks or will block `pull_request_target`, the owner allows it for this repository and notes the old value (undo: set it back). If the page has no such policy, nothing changes.

- [ ] **Step 2: Switch the clone on and install the shims (owner's OK)**

```bash
git config --local superpowers.requirePlans true
hooks="$(git rev-parse --git-common-dir)/hooks"
for h in pre-commit post-commit; do
  git show "refs/remotes/origin/master:.github/hooks/$h" > "$hooks/$h"
  chmod 755 "$hooks/$h"
done
ls -l "$hooks/pre-commit" "$hooks/post-commit"
```

Expected: both files present with mode `-rwxr-xr-x`.

Undo: `git config --local --unset superpowers.requirePlans && rm "$(git rev-parse --git-common-dir)/hooks/pre-commit" "$(git rev-parse --git-common-dir)/hooks/post-commit"`.

- [ ] **Step 3: Write `CLAUDE.local.md` and exclude it (owner's OK)**

```bash
printf '%s\n' 'Every change in this repository is built from a written plan made with superpowers:writing-plans, committed before any code. Never take brainstorming'"'"'s in-chat (bounded) path to skip it, never commit with --no-verify, and never push to the default branch.' > CLAUDE.local.md
exclude="$(git rev-parse --git-common-dir)/info/exclude"
grep -qxF CLAUDE.local.md "$exclude" || echo CLAUDE.local.md >> "$exclude"
git status --short CLAUDE.local.md
```

Expected: `git status` prints nothing (the file is ignored). Then start a new Claude Code session in the clone and run `/memory`: `CLAUDE.local.md` is listed among the loaded memory files. If it is not, stop and report; the spec relies on it.

Undo: `rm CLAUDE.local.md && sed -i '/^CLAUDE\.local\.md$/d' "$(git rev-parse --git-common-dir)/info/exclude"`.

- [ ] **Step 4: Set the repository variable (owner's OK)**

```bash
gh variable set REQUIRE_PLANS --body true --repo kferran/Foundry
gh variable list --repo kferran/Foundry
```

Expected: `REQUIRE_PLANS  true`.

Undo: `gh variable delete REQUIRE_PLANS --repo kferran/Foundry`.

- [ ] **Step 5: Live proof, local (owner's OK)**

From Claude Code:

```bash
git switch -c scratch/rp-noplan refs/remotes/origin/master
echo proof > rp-proof.txt
git add rp-proof.txt
git commit -m 'rp proof'; echo "exit $?"
```

Expected: `require_plan: no superpowers plan on this branch; commit one under docs/superpowers/plans/ first` and `exit 1`. `rp-proof.txt` stays staged.

Then the owner, in a plain terminal in the same clone:

```bash
git switch scratch/rp-noplan
git commit -m 'rp proof'; echo "exit $?"
```

Expected: the same message and `exit 1`.

In a worktree of a branch cut before this landed:

```bash
old="$(git rev-parse 'refs/remotes/origin/master^1')"
git cat-file -e "$old:.github/require_plan.sh"; echo "checker in old: exit $?"
git worktree add -b scratch/rp-old .scratch/rp-old "$old"
cd .scratch/rp-old && echo proof > rp-proof.txt && git add rp-proof.txt && git commit -m 'rp proof'; echo "exit $?"; cd -
```

Expected: `checker in old: exit 128` (the commit predates the checker; if it prints `exit 0`, pick an older commit), then the same block message and `exit 1`.

The `--no-verify` log (owner, plain terminal, on `scratch/rp-noplan`):

```bash
git commit --no-verify -m 'rp proof'
tail -n 1 "$(git rev-parse --git-common-dir)/require-plan.log"
```

Expected: one line ending in `scratch/rp-noplan`, the new commit's sha and `pre-commit skipped (--no-verify)`.

Undo: Step 8 removes the branches and the worktree.

- [ ] **Step 6: Live proof, pull requests, before the check is required (owner's OK)**

```bash
git push -u origin scratch/rp-noplan
gh pr create --draft --base master --head scratch/rp-noplan --title 'rp proof: no plan' --body 'Require-plan live proof; closed after the check runs.'
git switch -c scratch/rp-plan refs/remotes/origin/master
mkdir -p docs/superpowers/plans
printf '# RP proof\n\n> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan.\n' > docs/superpowers/plans/rp-proof.md
git add docs/superpowers/plans/rp-proof.md
git commit -m 'rp proof: plan'
echo proof > rp-proof.txt
git add rp-proof.txt
git commit -m 'rp proof: code'
git push -u origin scratch/rp-plan
gh pr create --draft --base master --head scratch/rp-plan --title 'rp proof: plan' --body 'Require-plan live proof; closed after the check runs.'
gh pr checks scratch/rp-noplan --watch; gh pr checks scratch/rp-plan --watch
for b in scratch/rp-noplan scratch/rp-plan; do
  sha="$(git rev-parse "$b")"
  echo "$b $(gh api "repos/kferran/Foundry/commits/$sha/check-runs" --jq '.check_runs[] | select(.name=="require-plan") | .conclusion')"
done
```

Expected: both plan-branch commits allowed; the loop prints `scratch/rp-noplan failure` and `scratch/rp-plan success`, so each run reported on its pull request's head commit. If a line has no conclusion, the check did not attach to the head commit: stop, and do not run Step 7.

Undo: Step 8 closes the pull requests and deletes the branches.

- [ ] **Step 7: Make `require-plan` a required check on `master`, then confirm it blocks (owner's OK)**

Show the current protection first; the owner chooses the branch below from what it prints:

```bash
gh api repos/kferran/Foundry/branches/master/protection
```

If it prints protection that already has `required_status_checks`, add the context without touching the rest:

```bash
gh api -X POST repos/kferran/Foundry/branches/master/protection/required_status_checks/contexts -f 'contexts[]=require-plan'
```

Undo: `gh api -X DELETE repos/kferran/Foundry/branches/master/protection/required_status_checks/contexts -f 'contexts[]=require-plan'`.

If it prints `Branch not protected` (404), create protection with only this check, admins exempt (the owner can still override):

```bash
printf '%s' '{"required_status_checks":{"strict":false,"contexts":["require-plan"]},"enforce_admins":false,"required_pull_request_reviews":null,"restrictions":null}' > .scratch/protection.json
gh api -X PUT repos/kferran/Foundry/branches/master/protection --input .scratch/protection.json
```

Undo: `gh api -X DELETE repos/kferran/Foundry/branches/master/protection`.

Then:

```bash
gh api repos/kferran/Foundry/branches/master/protection --jq .required_status_checks.contexts
gh pr ready scratch/rp-noplan
gh pr ready scratch/rp-plan
gh pr view scratch/rp-noplan --json mergeStateStatus --jq .mergeStateStatus
gh pr view scratch/rp-plan --json mergeStateStatus --jq .mergeStateStatus
```

Expected: the contexts list `require-plan`; `BLOCKED` for `scratch/rp-noplan` and `CLEAN` for `scratch/rp-plan` (GitHub may print `UNKNOWN` for a few seconds after `ready`; repeat the view until it settles). Anything else: run this step's undo before anything else merges, and report.

- [ ] **Step 8: Clean up (owner's OK)**

```bash
gh pr close scratch/rp-noplan --delete-branch
gh pr close scratch/rp-plan --delete-branch
git switch master
git worktree remove --force .scratch/rp-old
git branch -D scratch/rp-noplan scratch/rp-plan scratch/rp-old
```

Expected: no `scratch/rp-*` branches left locally or on `origin`, no open proof pull requests.

`minutes` gets the checker, shims and workflow through its own small plan after this one is merged; Steps 1 to 7 for `minutes` (default branch `main`) wait for it.
