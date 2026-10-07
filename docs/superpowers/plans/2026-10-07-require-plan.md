# Require a Superpowers Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every pull request to `kferran/Foundry` (and later `kferran/minutes`) carries a committed `superpowers:writing-plans` plan: a required pull-request check enforces it, and the Nightshift names its plan in every pull request it opens.

**Architecture:** One bash checker, `.github/require_plan.sh` (git and grep only), judges a pull request's commits against its base. A `pull_request_target` workflow runs the default branch's copy of it, with `HEAD` pointed at the pull request's commit as data, so a pull request cannot weaken the check that judges it. The workflow does nothing unless the repository variable `REQUIRE_PLANS` is exactly `true`, so vaults made from the template carry the files and never run them. The Nightshift writes a runner-owned `Plan:` line first in its pull request body and refuses at queue time a plan the check would refuse. Nothing checks commits locally (spec R1).

**Tech Stack:** bash (3.2 compatible), git 2.39, grep, GitHub Actions (`pull_request_target`, `actions/checkout@v4`), Python 3.11 (`vaultlib`), bats 1.8.2, pytest, `gh` (rollout only).

**Spec:** `docs/superpowers/specs/2026-10-07-require-plan-design.md` (rev 5, approved: the smaller scope chosen after the quorum)

## Global Constraints

- Work on branch `feat/require-plan` of `kferran/Foundry` (spec rev 5 at commit `aebb49d`). Every task commits there. Tasks 1 to 3 never push, never open a pull request, and never touch repository variables or branch protection; those are Task 4, attended.
- Tool floor: jq 1.6, bats 1.8.2, Python 3.11, git 2.39.
- The checker must run on bash 3.2 (the `minutes` repository runs on macOS): no `mapfile`, `readarray`, `${x,,}`, `${x^^}`, `declare -A`, `[[ -v`. It uses `git` and `grep` only.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. Read verdicts from exit codes (`run` then `[ "$status" -eq N ]`), never through a pipe.
- Template rule: never commit a hostname, user path, remote URL or distro choice. The workflow does not name the repository.
- The header marker is `REQUIRED SUB-SKILL: Use superpowers:` (superpowers 6.4.1). It appears once in the checker, as the line `MARKER='REQUIRED SUB-SKILL: Use superpowers:'`, and once in `nightshift_check.py` as `MARKER`; a test keeps them equal.
- Checker exit codes: 0 allowed, 1 blocked (one line on stderr starting `require_plan:`), 2 usage error.
- Run one suite as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh` from the repository root.
- Bound tools: bats (`system/tests/require_plan.bats`), pytest (`system/tests/python/test_nightshift_check.py`, `test_nightshift_deliver.py`, `test_nightshift_run.py`), the gate, and the live checks in Task 4.
- Commits use `git commit -F .scratch/<file>`; every message ends with the line `Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm`.

## Review Focus

- Deleting or renaming code beside a new spec must not pass as the plan step: the plan-step test reads `--no-renames` paths with deletions, the plan search reads `--diff-filter=ACMR`. Pinned by the two `deletions:` tests (Task 1).
- A pull request must not carry a `pull_request` workflow that reports a passing `require-plan` check. Pinned by `workflows: editing require-plan.yml or adding a workflow naming it is blocked` (Task 1).
- A `Plan:` line edited on GitHub may carry trailing spaces, and a hostile one may use `..` to point outside `plans/`: trailing spaces pass, `docs/superpowers/plans/../notes.md` fails (git refuses `..` in a tree path). Pinned by the `plan line:` tests (Task 1).
- A switched-off repository (every vault) must end the job green before the fetch, which would fail without credentials on a private repository. Pinned by `workflow: the check step ends green before the fetch when switched off` (Task 2).

---

## File Structure

| File | Responsibility |
|---|---|
| `.github/require_plan.sh` | the checker (spec §3) |
| `.github/workflows/require-plan.yml` | the `require-plan` pull-request check (spec §4) |
| `system/tests/require_plan.bats` | checker and workflow tests (spec §8) |
| `system/scripts/vaultlib/nightshift_check.py` (modify) | `MARKER`; `_plan` refuses a plan without it |
| `system/scripts/vaultlib/nightshift_run.py` (modify) | `_deliver` writes `Plan: <plan>` first and drops the session's `Plan:` lines |
| `system/tests/python/test_nightshift_check.py`, `test_nightshift_run.py` (modify) | Nightshift tests |
| `.claude/skills/nightshift/SKILL.md` (modify) | the `add` step names `--pr-base main` and the `workflow` scope (spec §5) |
| `README.md` (modify) | the `workflow` scope line and "When require-plan blocks a pull request" (spec §6) |
| `CLAUDE.local.md` (untracked, Task 4 only) | the one instruction line per clone |

---

### Task 1: The checker

**Files:**
- Create: `.github/require_plan.sh`
- Test: `system/tests/require_plan.bats`

**Interfaces:**
- Produces: `bash .github/require_plan.sh --base <ref> [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]`, run with `HEAD` at the pull request's commit, exit 0/1/2. Block messages, verbatim:
  - `require_plan: no merge base between <base> and HEAD (unrelated history)`
  - `require_plan: this pull request changes or adds a require-plan workflow; only the owner can merge it`
  - `require_plan: no superpowers plan in this pull request; add a plan made with superpowers:writing-plans (its header has "REQUIRED SUB-SKILL: Use superpowers:") under docs/superpowers/plans/`
- Produces: the checker line `MARKER='REQUIRED SUB-SKILL: Use superpowers:'` (Task 3's test reads it).
- Produces for Task 2: the bats `setup` (a clone `$C` of a bare `$ORIGIN` built from `$SEED`, branch `feat/x`) and helpers `plan_file <path>`, `spec_file`, `code [path]`, `pr <args>` (runs the checker against `refs/remotes/origin/master`), plus `$REPO`, `$CHECK`, `$B`.

- [ ] **Step 1: Write the failing tests**

Create `system/tests/require_plan.bats` with exactly:

```bash
#!/usr/bin/env bats
# require_plan.sh (require-plan spec §3, §8). Every repository here is a temporary clone of a temporary bare origin;
# HOME is temporary and the system and XDG configs are off, so no host git setting reaches the tests.

setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  CHECK="$REPO/.github/require_plan.sh"
  export HOME="$BATS_TEST_TMPDIR/home" GIT_CONFIG_NOSYSTEM=1
  export XDG_CONFIG_HOME="$HOME/.config"
  mkdir -p "$HOME"
  export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
  HEADER='> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan.'
  NOPLAN='require_plan: no superpowers plan in this pull request; add a plan made with superpowers:writing-plans'
  B="$BATS_TEST_TMPDIR/body.md"
  SEED="$BATS_TEST_TMPDIR/seed"
  ORIGIN="$BATS_TEST_TMPDIR/origin.git"
  C="$BATS_TEST_TMPDIR/clone"
  git init -q -b master "$SEED"
  echo base > "$SEED/README.md"
  plan_file "$SEED/docs/superpowers/plans/merged.md"
  echo 'no header here' > "$SEED/docs/superpowers/plans/no-header.md"
  printf '%s\n' "$HEADER" > "$SEED/docs/notes.md"  # the marker, outside plans/
  mkdir -p "$SEED/.github/workflows"
  printf 'name: require-plan\n' > "$SEED/.github/workflows/require-plan.yml"
  printf 'name: other\n' > "$SEED/.github/workflows/other.yml"
  git -C "$SEED" add -A
  git -C "$SEED" commit -qm base
  git clone -q --bare "$SEED" "$ORIGIN"
  git clone -q "$ORIGIN" "$C"
  cd "$C"
  git checkout -q -b feat/x
}

plan_file() { mkdir -p "$(dirname "$1")"; printf '# Plan\n\n%s\n' "$HEADER" > "$1"; }
spec_file() { mkdir -p docs/superpowers/specs; echo spec > docs/superpowers/specs/s.md; git add docs; }
code() { echo "${2:-code}" > "${1:-app.sh}"; git add -- "${1:-app.sh}"; git commit -qm code; }
pr() { run bash "$CHECK" --base refs/remotes/origin/master "$@"; }

@test "verdict: a plan on the branch passes; neither plan nor plan step fails with the header named" {
  code
  pr
  [ "$status" -eq 1 ]
  [[ "$output" == *"$NOPLAN"* ]]
  [[ "$output" == *'REQUIRED SUB-SKILL: Use superpowers:'* ]]
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  pr
  [ "$status" -eq 0 ]
}

@test "verdict: a branch of only specs and plans passes (the plan step)" {
  spec_file
  git commit -qm spec
  pr
  [ "$status" -eq 0 ]
}

@test "verdict: a plan without the header does not count" {
  mkdir -p docs/superpowers/plans
  echo 'no header' > docs/superpowers/plans/q.md
  git add docs
  git commit -qm plan
  code
  pr
  [ "$status" -eq 1 ]
}

@test "verdict: a plan deleted on the branch does not count" {
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  git rm -q docs/superpowers/plans/p.md
  git commit -qm drop
  code
  pr
  [ "$status" -eq 1 ]
}

@test "verdict: non-ASCII paths with spaces are read correctly" {
  plan_file "docs/superpowers/plans/plän ü.md"
  git add docs
  git commit -qm plan
  code "skript ä.sh"
  pr
  [ "$status" -eq 0 ]
}

@test "deletions: removing code beside a new spec is a code change" {
  git rm -q README.md
  spec_file
  git commit -qm drop
  pr
  [ "$status" -eq 1 ]
}

@test "deletions: renaming code into specs/ is a code change" {
  mkdir -p docs/superpowers/specs
  git mv README.md docs/superpowers/specs/r.md
  git commit -qm move
  pr
  [ "$status" -eq 1 ]
}

@test "workflows: editing require-plan.yml or adding a workflow naming it is blocked" {
  plan_file docs/superpowers/plans/p.md
  git add docs
  git commit -qm plan
  echo 'on: push' >> .github/workflows/other.yml
  git commit -qam other
  pr
  [ "$status" -eq 0 ]
  echo '# edited' >> .github/workflows/require-plan.yml
  git commit -qam edit
  pr
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: this pull request changes or adds a require-plan workflow; only the owner can merge it"* ]]
  git reset -q --hard HEAD~1
  printf 'jobs:\n  require-plan:\n' > .github/workflows/x.yml
  git add .github
  git commit -qm forged
  pr
  [ "$status" -eq 1 ]
}

@test "plan line: passes only on a nightshift/ head from the same repository" {
  code
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

@test "plan line: must name a plan with the header under docs/superpowers/plans/ at HEAD" {
  code
  for p in docs/notes.md --output=x docs/superpowers/plans/missing.md docs/superpowers/plans/no-header.md \
           docs/superpowers/plans/../notes.md; do
    printf 'Plan: %s\n' "$p" > "$B"
    pr --head-ref nightshift/x --same-repo true --body-file "$B"
    [ "$status" -eq 1 ]
  done
}

@test "plan line: a CRLF body passes, trailing spaces pass, a missing body file fails" {
  code
  printf 'Plan: docs/superpowers/plans/merged.md\r\nDid it.\r\n' > "$B"
  pr --head-ref nightshift/x --same-repo true --body-file "$B"
  [ "$status" -eq 0 ]
  printf 'Plan: docs/superpowers/plans/merged.md  \n' > "$B"
  pr --head-ref nightshift/x --same-repo true --body-file "$B"
  [ "$status" -eq 0 ]
  pr --head-ref nightshift/x --same-repo true --body-file "$BATS_TEST_TMPDIR/none.md"
  [ "$status" -eq 1 ]
}

@test "base: unrelated history fails with the reason" {
  git checkout -q --orphan fresh
  git commit -qm first
  pr
  [ "$status" -eq 1 ]
  [[ "$output" == *"require_plan: no merge base"* ]]
}

@test "usage: a missing --base or a bad option exits 2" {
  run bash "$CHECK"
  [ "$status" -eq 2 ]
  run bash "$CHECK" --head-ref x
  [ "$status" -eq 2 ]
  run bash "$CHECK" --base refs/remotes/origin/master --same-repo maybe
  [ "$status" -eq 2 ]
  run bash "$CHECK" --base
  [ "$status" -eq 2 ]
  run bash "$CHECK" --base refs/remotes/origin/master extra
  [ "$status" -eq 2 ]
}

@test "files: the checker is mode 100755 in git and avoids bash 4 constructs" {
  run git -C "$REPO" ls-files -s -- .github/require_plan.sh
  [[ "$output" == 100755* ]]
  run grep -nE 'mapfile|readarray|\$\{[A-Za-z_][A-Za-z0-9_]*(,,|\^\^)|declare -A|\[\[ -v' "$CHECK"
  [ "$status" -eq 1 ]
}
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `mkdir -p .scratch/tmp && TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: FAIL, all 14 tests (`bash: <repo>/.github/require_plan.sh: No such file or directory`, status 127).

- [ ] **Step 3: Write the checker**

Create `.github/require_plan.sh` with exactly:

```bash
#!/usr/bin/env bash
# Allows a pull request only when it carries a superpowers plan (require-plan spec §3). Run with HEAD at the pull
# request's commit; the workflow decides whether it runs.
# Usage: require_plan.sh --base <ref> [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]
# Exit 0 allowed, 1 blocked (one "require_plan:" line on stderr), 2 usage error. git and grep only; bash 3.2 safe.
MARKER='REQUIRED SUB-SKILL: Use superpowers:'
PLANS='docs/superpowers/plans/'
SPECS='docs/superpowers/specs/'
WF='.github/workflows/'

block() { printf 'require_plan: %s\n' "$1" >&2; exit 1; }
usage() {
  printf 'usage: require_plan.sh --base <ref> [--head-ref <branch>] [--same-repo true|false] [--body-file <file>]\n' >&2
  exit 2
}

base='' head_ref='' same=false body=''
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
done
[ -n "$base" ] || usage

# is_plan <path>: the path is under plans/ and its text at HEAD has the marker.
is_plan() {
  case $1 in "$PLANS"*) ;; *) return 1 ;; esac
  git cat-file blob "HEAD:$1" 2>/dev/null | grep -qF -- "$MARKER"
}

# plan_step: the NUL-separated paths on stdin are non-empty and all under specs/ or plans/.
plan_step() {
  local p seen=''
  while IFS= read -r -d '' p; do
    case $p in "$SPECS"*|"$PLANS"*) seen=1 ;; *) return 1 ;; esac
  done
  [ -n "$seen" ]
}

# has_plan: one of the NUL-separated paths on stdin is a plan at HEAD.
has_plan() {
  local p
  while IFS= read -r -d '' p; do
    if is_plan "$p"; then return 0; fi
  done
  return 1
}

mb=$(git merge-base "$base" HEAD 2>/dev/null) ||
  block "no merge base between $base and HEAD (unrelated history)"

# The plan-step test reads every changed path (deletions, and both sides of a rename); the plan search reads only
# paths that exist at HEAD, so a deleted plan does not count.
all_changes() { git diff -z --name-only --no-renames "$mb" HEAD; }
kept_changes() { git diff -z --name-only --diff-filter=ACMR "$mb" HEAD; }

# A pull_request workflow from the pull request could report a passing check under the same name.
if ! git diff --quiet "$mb" HEAD -- "${WF}require-plan.yml" ||
   git grep -qF require-plan HEAD -- "$WF" ":(exclude)${WF}require-plan.yml"; then
  block 'this pull request changes or adds a require-plan workflow; only the owner can merge it'
fi

if all_changes | plan_step || kept_changes | has_plan; then exit 0; fi

# A Nightshift pull request names its plan on a "Plan: <path>" line instead (spec §3).
case $head_ref in
  nightshift/*)
    if [ "$same" = true ] && [ -n "$body" ] && [ -f "$body" ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        case $line in
          'Plan: '*)
            path=${line#Plan: }
            path=${path%% *}
            if is_plan "$path"; then exit 0; fi
            break ;;
        esac
      done <"$body"
    fi ;;
esac
block "no superpowers plan in this pull request; add a plan made with superpowers:writing-plans (its header has \"$MARKER\") under $PLANS"
```

- [ ] **Step 4: Make it executable and stage it** (the `files:` test reads the mode from the index)

Run: `chmod +x .github/require_plan.sh && git add .github/require_plan.sh system/tests/require_plan.bats`

- [ ] **Step 5: Run the suite to verify it passes**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: PASS, `1..14`, no `not ok`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(require-plan): pull-request plan checker

.github/require_plan.sh allows a pull request only when its changes
carry a superpowers plan, or are only specs and plans, or (for a
Nightshift branch) its body names a plan on a Plan: line. It blocks a
pull request that carries its own require-plan workflow.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git commit -q -F .scratch/msg-1.txt`

---

### Task 2: The pull-request check workflow and the README

**Files:**
- Create: `.github/workflows/require-plan.yml`
- Modify: `README.md` (sections "Updating and uninstalling" and "Development")
- Test: `system/tests/require_plan.bats` (append)

**Interfaces:**
- Consumes: Task 1's checker and its options; `$REPO` from the bats `setup`.
- Produces: the workflow `require-plan` with job id `require-plan`, which is the check name Task 4 makes required. Its last step returns at once unless `REQUIRE_PLANS` is exactly `true`, then runs `bash "$RUNNER_TEMP/require_plan.sh" --base "refs/remotes/origin/$BASE_REF" --head-ref "$HEAD_REF" --same-repo <true|false> --body-file "$RUNNER_TEMP/body.md"`.

- [ ] **Step 1: Write the failing tests**

Append to the end of `system/tests/require_plan.bats`, after one blank line:

```bash
# The pull-request workflow, by text (spec §4)
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
Expected: FAIL, the 5 `workflow:` tests (`grep: …/.github/workflows/require-plan.yml: No such file or directory`); the other 14 pass.

- [ ] **Step 3: Write the workflow**

Create `.github/workflows/require-plan.yml` with exactly:

```yaml
# The pull-request check (require-plan spec §4): fails a pull request that carries no superpowers plan.
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
          bash "$RUNNER_TEMP/require_plan.sh" --base "refs/remotes/origin/$BASE_REF" --head-ref "$HEAD_REF" \
            --same-repo "$same" --body-file "$RUNNER_TEMP/body.md"
```

Notes for the reviewer: `pull_request_target` runs this file and checks out the commit from the default branch, so a pull request cannot edit its own check. The pull request's commit is fetched as data (`refs/pull/<n>/head`, public repository, no credentials kept), compared with the event's `head.sha`, and named by `HEAD` through `git update-ref`; no file from it is written and only the default branch's checker runs. The switch guard is the first line of the last step, so a switched-off repository (such as a private vault, whose fetch would fail) ends green before the fetch; no step or job has an `if:`, because a skipped job reports success to a required check.

- [ ] **Step 4: Update the README**

In `README.md`, find (section `## Updating and uninstalling`):

```markdown
- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders the units, but only if this vault installed them. It never runs automatically.
```

Replace with:

```markdown
- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders the units, but only if this vault installed them. It never runs automatically.
- **Pushing after the update that adds `.github/workflows/`:** a vault whose `origin` uses HTTPS with a `gh` token needs the token's `workflow` scope to push (`gh auth refresh -s workflow`). The workflow and the plan checker stay off in a vault.
```

Find (the last paragraph of section `## Development`):

```markdown
`system/tests/system_health.bats` checks live service state and is advisory only. To prove the suite on Debian, run `system/tests/verify_on_host.sh <ssh-host>`: it copies the committed tree to a temporary directory on that host, runs the gate there, and exits with its code. The host needs the `apt` packages `check_deps.sh` lists. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand. After any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands, re-run the live acceptance steps (Plan 4a, Task 9) in a throwaway clone.
```

Replace with:

```markdown
`system/tests/system_health.bats` checks live service state and is advisory only. To prove the suite on Debian, run `system/tests/verify_on_host.sh <ssh-host>`: it copies the committed tree to a temporary directory on that host, runs the gate there, and exits with its code. The host needs the `apt` packages `check_deps.sh` lists. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand. After any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands, re-run the live acceptance steps (Plan 4a, Task 9) in a throwaway clone.

### When require-plan blocks a pull request

In the development repositories, the required `require-plan` check fails a pull request that carries no plan made with `superpowers:writing-plans` (it runs only where the repository variable `REQUIRE_PLANS` is `true`):

- **No plan:** commit the plan under `docs/superpowers/plans/` on the branch. A plan file without its `REQUIRED SUB-SKILL: Use superpowers:` header does not count.
- **A revert or an urgent fix:** write a short plan, or the owner merges with the admin override.
- **A change to the check itself** (`require-plan.yml`, or a workflow naming `require-plan`): always fails; the owner merges with the admin override.
- **The check is broken on the default branch,** so every pull request fails, including the fix: the owner runs `gh variable set REQUIRE_PLANS --body false`, merges the fix, then sets it back to `true`.
- **The check never reports:** GitHub's Actions event policy may block `pull_request_target`. The owner allows the event on the repository's Actions settings page, or removes the required check until it is fixed.
```

- [ ] **Step 5: Run the suite to verify it passes**

Run: `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/require_plan.bats`
Expected: PASS, `1..19`, no `not ok`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-2.txt`:

```text
feat(require-plan): pull-request check workflow and recovery notes

.github/workflows/require-plan.yml runs the default branch's checker on
every pull request (pull_request_target, contents: read, the pull
request's commit read as data). The README notes the workflow scope a
vault's HTTPS push needs after this update, and what to do when the
check blocks a pull request.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git add .github/workflows/require-plan.yml system/tests/require_plan.bats README.md && git commit -q -F .scratch/msg-2.txt`

---

### Task 3: The Nightshift names its plan and checks the header

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py` (constants; `_plan`), `system/scripts/vaultlib/nightshift_run.py` (imports; `_deliver`), `.claude/skills/nightshift/SKILL.md` (the `add` step)
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: the checker line `MARKER='REQUIRED SUB-SKILL: Use superpowers:'` (Task 1).
- Produces: `nightshift_check.MARKER: str`; `_plan` adds the error `plan <path> lacks the writing-plans header ('REQUIRED SUB-SKILL: Use superpowers:'); the pull-request check would refuse it`; `_deliver` writes `pr_body.md` as `Plan: <fm["plan"]>`, a blank line, the session's body with every line matching `^[ \t]*plan:` (any case) removed, then the existing "Queued as" line.

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
Expected: FAIL, `3 failed, 53 passed`: `test_plan_without_the_writing_plans_header_is_refused` and `test_marker_is_the_checkers_literal` (`AttributeError: module 'vaultlib.nightshift_check' has no attribute 'MARKER'`), `test_pr_body_starts_with_the_plan_line_and_drops_the_sessions` (`assert 'Plan: docs/s...lans/other.md' == 'Plan: docs/s...rs/plans/p.md'`).

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
        text = re.sub(r"(?im)^[ \t]*plan:.*\n?", "", d["body"])   # the runner's Plan: line is the only one (require-plan spec §5)
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
Expected: PASS, `56 passed`.

- [ ] **Step 5: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0; the summary lists `PASS system/tests/require_plan.bats` and `PASS pytest system/tests/python`, and no `FAIL`.

- [ ] **Step 6: Commit**

Write `.scratch/msg-3.txt`:

```text
feat(nightshift): Plan: line and plan header check

The pull request body for a plan item starts with the runner's Plan:
line and drops any the session wrote; queueing refuses a plan without
the writing-plans header. The skill's add step names --pr-base main and
the workflow scope a push may need.

Claude-Session: https://claude.ai/code/session_0199FzGq2D5cGY9jt9zXX5zm
```

Run: `git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py .claude/skills/nightshift/SKILL.md && git commit -q -F .scratch/msg-3.txt`

---

### Task 4: Rollout on `kferran/Foundry` (attended; owner only)

**Not runnable by an executor, a subagent or the Nightshift.** Every step changes the owner's clone, the GitHub repository or its settings, and each one needs the owner's explicit OK before it runs. Each step lists its undo. Stop and report at the first surprise. The Nightshift's readiness check refuses this task (it works on `master`); queue Tasks 1 to 3 only.

**Files:** none tracked. Untracked: `CLAUDE.local.md` in the clone root and an `info/exclude` line.

**Interfaces:**
- Consumes: Tasks 1 to 3 merged to `master` through a pull request the owner reviewed and merged (before this lands nothing enforces it, so this one pull request is judged by the owner alone).

- [ ] **Step 1: Preconditions (owner's OK)**

In the development clone of `kferran/Foundry`:

```bash
git fetch origin
git cat-file -e refs/remotes/origin/master:.github/require_plan.sh && echo checker-on-master
git cat-file -e refs/remotes/origin/master:.github/workflows/require-plan.yml && echo workflow-on-master
```

Expected: `checker-on-master` and `workflow-on-master`.

The owner then opens the repository's **Settings → Actions → General** page in a browser and reads its workflow event policy. GitHub reportedly turns `pull_request_target` off by default for public repositories from 2026-11-02 (in evaluate mode before that); the REST API does not show this policy. If the page shows a policy that blocks or will block `pull_request_target`, the owner allows it for this repository and notes the old value (undo: set it back). If the page has no such policy, nothing changes.

- [ ] **Step 2: Write `CLAUDE.local.md` and exclude it (owner's OK)**

```bash
printf '%s\n' 'Every change in this repository is built from a written plan made with superpowers:writing-plans, committed before any code. Never take brainstorming'"'"'s in-chat (bounded) path to skip it, and never push to the default branch.' > CLAUDE.local.md
exclude="$(git rev-parse --git-common-dir)/info/exclude"
grep -qxF CLAUDE.local.md "$exclude" || echo CLAUDE.local.md >> "$exclude"
git status --short CLAUDE.local.md
```

Expected: `git status` prints nothing (the file is ignored). Then start a new Claude Code session in the clone and run `/memory`: `CLAUDE.local.md` is listed among the loaded memory files. If it is not, stop and report; the spec relies on it.

Undo: `rm CLAUDE.local.md && sed -i '/^CLAUDE\.local\.md$/d' "$(git rev-parse --git-common-dir)/info/exclude"`.

- [ ] **Step 3: Set the repository variable (owner's OK)**

```bash
gh variable set REQUIRE_PLANS --body true --repo kferran/Foundry
gh variable list --repo kferran/Foundry
```

Expected: `REQUIRE_PLANS  true`.

Undo: `gh variable delete REQUIRE_PLANS --repo kferran/Foundry`.

- [ ] **Step 4: Live proof, pull requests, before the check is required (owner's OK)**

```bash
git switch -c scratch/rp-noplan refs/remotes/origin/master
echo proof > rp-proof.txt
git add rp-proof.txt
git commit -m 'rp proof: code'
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

Expected: the loop prints `scratch/rp-noplan failure` and `scratch/rp-plan success`, so each run reported on its pull request's head commit, and the failing run's log has the `no superpowers plan in this pull request` line. If a line has no conclusion, the check did not attach to the head commit: stop, and do not run Step 5.

Undo: Step 6 closes the pull requests and deletes the branches.

- [ ] **Step 5: Make `require-plan` a required check on `master`, then confirm it blocks (owner's OK)**

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

- [ ] **Step 6: Clean up (owner's OK)**

```bash
gh pr close scratch/rp-noplan --delete-branch
gh pr close scratch/rp-plan --delete-branch
git switch master
git branch -D scratch/rp-noplan scratch/rp-plan
```

Expected: no `scratch/rp-*` branches left locally or on `origin`, no open proof pull requests.

- [ ] **Step 7: Re-check after GitHub's policy change (owner, on or after 2026-11-03)**

Recorded as a dated item in the template work queue. The owner re-reads the Actions settings page as in Step 1, then repeats Step 4 with one scratch pull request (with a plan) and confirms its `require-plan` run concludes `success`; Step 6 cleans up. If no run appears, follow the README section "When require-plan blocks a pull request" (the check never reports).

`minutes` gets the checker and workflow through its own small plan after this one is merged; Steps 1 to 5 for `minutes` (default branch `main`) wait for it.
