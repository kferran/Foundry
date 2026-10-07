# Setup and Update Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `update_template.sh` never installs a unit the vault did not install, `/setup` catches an `origin` with its own history and an HTTPS origin that needs a prompt, `setup.bats` passes on every role, and codebase inspection stays small on large monorepos (issues #35, #15, #16, #17, #18, #20 on `kferran/jarvis`).

**Architecture:**
- `install_units.sh` gains `--update`: the unit list for the role is cut to the units this vault already owns (drop-ins follow their service); every other unit is printed as `new unit available: <unit> …`. `update_template.sh` calls it.
- `setup_remote.sh` probes the SSH form of an unreachable `https://` origin on github.com, gitlab.com or bitbucket.org and prints a `hint:` line; `/setup` phase 4 offers it, then stops on an `origin` with unrelated history before setting the upstream.
- `inspect_repo` takes `per_kind`; the CLI shows at most 5 manifests per kind plus `manifest_counts` and `notable` over all of them; `--all-manifests` lifts the cap.
- `setup.bats` runs a copy of `check_deps.sh` outside any vault, so the role default is always `standalone`.
- `/setup` prompt text: up-front answers, `<…>` placeholders, and a notice when a scanned worktree is not the registered path.

**Tech Stack:** bash 5, git, jq 1.6, bats 1.8, Python 3.11, systemd user units (stubbed in tests).

**Spec:** issues #35, #15, #16, #17, #18, #20 (`gh issue view <n> --repo kferran/jarvis`) and the triage `docs/superpowers/plans/2026-10-07-template-issue-triage.md`. Main spec `docs/superpowers/specs/2026-09-30-vault-template-design.md` §6.10 (units), §6.11 (remotes), §6.12 (template updates), §6.13 (codebase inspection), §11 (setup).

## Global Constraints

- **Where:** a worktree of the template repository on its own branch, for example `git -C ~/Foundry fetch -q template && git -C ~/Foundry worktree add ~/Foundry-worktrees/setup-fixes -b fix/setup-update template/master`. Never on a vault's `master`; never push or merge from the plan.
- **Never** run `install_units.sh`, `install_hooks.sh`, `setup_remote.sh`, `update_template.sh` or `/setup` against the real user session or a real vault; tests use `$BATS_TEST_TMPDIR` vaults with a stubbed `systemctl` and `SYSTEMD_USER_DIR` in the temp dir.
- **No `system/config.md`** in the worktree, except the temporary one Task 1 Step 2 writes and removes.
- **Tool floor:** jq 1.6, bats 1.8 (no `run -N`), Python 3.11. No mid-test `!`, no `&&` assertion chains.
- **Verify (no network, sandbox-safe):** `python3 -m pytest system/tests/python -q` and `bats system/tests/remote.bats system/tests/setup.bats system/tests/codebases.bats system/tests/commands.bats`. Not `units.bats` (needs systemd). Without a user session (`XDG_RUNTIME_DIR` unset), `remote.bats` test "update_template merges a clean update, then rebuilds the index and re-renders installed units" fails before and after this plan alike, because it runs the real `systemd-analyze --user verify`; the new tests stub it.
- **Wording:** American English; no hostname, user path or remote URL committed.
- **Edits:** each "replace" block below quotes the current text exactly; it must match once. If it does not, the tree differs from `template/master` at fb81fca: stop and compare.

## Review Focus

1. **A vault that installed its units before a unit existed (Nightshift, telemetry, DTCC, meetings) runs `update_template.sh`.** Expected: owned units re-rendered, each new one listed as `new unit available`, nothing new written or enabled. Pinned by Task 2's first test.
2. **A server vault with sync drop-ins runs `update_template.sh`.** Expected: the drop-ins of owned services are re-rendered, never dropped as stale. Pinned by Task 2's server test.
3. **A vault that owns only a drop-in (no unit) runs `update_template.sh`.** Expected: exit 0, nothing to verify, no `systemctl enable` with an empty list. Pinned by the existing "re-renders units when only an owned drop-in is installed" test, which Task 2 keeps green (it now renders nothing).
4. **An HTTPS origin whose SSH form also fails, or on an unknown host.** Expected: the warning only, no `hint:`. Pinned by Task 3's test (second and third runs).
5. **A monorepo whose only Vue `package.json` is past the per-kind cap.** Expected: `notable` still lists `vue`. Pinned by Task 5's Python test (`per_kind=1`).

---

### Task 1: `setup.bats` no longer depends on the running vault's role (#17)

**Files:**
- Modify: `system/tests/setup.bats:4-6`

**Interfaces:** none.

- [ ] **Step 1: Show the failure.** It appears only when the vault running the tests has a non-standalone role.

```bash
[ ! -e system/config.md ] || { echo "system/config.md exists: stop"; exit 1; }
printf -- '---\ntype: config\nmachine_role: "server"\n---\n' > system/config.md
bats system/tests/setup.bats; echo "exit=$?"
rm system/config.md
```

Expected: `not ok 1 check_deps: every item present reports ok and --strict passes`, `exit=1`.

- [ ] **Step 2: Pin the role.** In `system/tests/setup.bats`, replace:

```bash
setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  CD="$REPO/system/scripts/check_deps.sh"
```

with:

```bash
setup() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  # A copy outside any vault: with no system/config.md beside it the role is standalone, whatever role the
  # vault running these tests has (#17).
  mkdir -p "$BATS_TEST_TMPDIR/v/system/scripts"
  cp "$REPO/system/scripts/check_deps.sh" "$BATS_TEST_TMPDIR/v/system/scripts/"
  CD="$BATS_TEST_TMPDIR/v/system/scripts/check_deps.sh"
```

- [ ] **Step 3: Run it under both roles and with no config.**

```bash
for r in server client; do
  printf -- '---\ntype: config\nmachine_role: "%s"\n---\n' "$r" > system/config.md
  bats system/tests/setup.bats > /dev/null; echo "$r exit=$?"
done
rm system/config.md
bats system/tests/setup.bats; echo "exit=$?"
```

Expected: `server exit=0`, `client exit=0`, then 25 `ok` lines and `exit=0`.

- [ ] **Step 4: Commit.**

```bash
git add system/tests/setup.bats
git commit -m "test(setup): run check_deps outside the vault so its role does not leak in (#17)"
```

---

### Task 2: `update_template.sh` re-renders only installed units (#35)

**Files:**
- Modify: `system/scripts/install_units.sh:15-22`, `:117` (after the `DROPIN_PREP` declaration), `:186`, `:240`
- Modify: `system/scripts/update_template.sh:42`
- Modify: `README.md:287`
- Test: `system/tests/remote.bats`, `system/tests/commands.bats`

**Interfaces:**
- Produces: `install_units.sh --update`. Output lines: `new unit available: <unit> (install it with system/scripts/install_units.sh)` for each unit the role selects that this vault does not own, then the usual `new|changed|unchanged|removed <file>` lines for owned files. Enables only owned units from the role's enable list; skips `systemctl enable` when that list is empty.

- [ ] **Step 1: Write the failing tests.** In `system/tests/remote.bats`, insert before `@test "update_template leaves units alone in a vault that never installed them" {`:

```bash
@test "update_template reports a unit the new template adds and never installs or enables it" {
  template_setup
  printf '#!/bin/bash\n' > "$STUBS/systemd-analyze"  # verify needs a user session; this test is about the unit list
  chmod +x "$STUBS/systemd-analyze"
  system/scripts/install_units.sh > /dev/null
  rm "$SYSTEMD_USER_DIR"/foundry-nightshift.service "$SYSTEMD_USER_DIR"/foundry-nightshift.timer
  : > "$STUB_SYSTEMCTL_LOG"
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  grep -qx 'new unit available: foundry-nightshift.timer (install it with system/scripts/install_units.sh)' <<< "$output"
  grep -qx 'unchanged foundry-brief.service' <<< "$output"
  [ ! -e "$SYSTEMD_USER_DIR/foundry-nightshift.timer" ]
  [ ! -e "$SYSTEMD_USER_DIR/foundry-nightshift.service" ]
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service' "$STUB_SYSTEMCTL_LOG"
}

@test "update_template on a server re-renders the sync drop-ins of the services it installed" {
  template_setup
  printf '#!/bin/bash\n' > "$STUBS/systemd-analyze"
  chmod +x "$STUBS/systemd-analyze"
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  system/scripts/install_units.sh > /dev/null
  rm "$SYSTEMD_USER_DIR"/foundry-nightshift.service "$SYSTEMD_USER_DIR"/foundry-nightshift.timer
  upstream_commit new.txt hello
  run "$UT"
  [ "$status" -eq 0 ]
  grep -qx 'unchanged foundry-brief.service.d/foundry-sync.conf' <<< "$output"
  grep -qx 'unchanged foundry-sync.timer' <<< "$output"
  grep -qx 'new unit available: foundry-nightshift.service (install it with system/scripts/install_units.sh)' <<< "$output"
}

```

Append to `system/tests/commands.bats`:

```bash

@test "the README says update_template.sh lists new units and never installs them (#35)" {
  grep -qF 'A unit the update adds is listed as `new unit available: <unit>` and left out' README.md
}
```

- [ ] **Step 2: Run them to see them fail.**

Run: `bats -f 'new template adds|server re-renders' system/tests/remote.bats; bats -f '#35' system/tests/commands.bats`
Expected: three `not ok`; the remote ones fail on the `new unit available` grep (today's output is `new foundry-nightshift.timer`).

- [ ] **Step 3: Add `--update` to `install_units.sh`.** Replace:

```bash
usage() { die 2 "usage: install_units.sh [--dry-run | --uninstall]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  *) usage ;;
esac
```

with:

```bash
usage() { die 2 "usage: install_units.sh [--dry-run | --uninstall | --update]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  --update) mode=update ;;
  *) usage ;;
esac
```

Replace:

```bash
                        [foundry-debrief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"')
```

with:

```bash
                        [foundry-debrief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"')
# --update (update_template.sh) re-renders only what this vault installed: a unit a new template adds is
# reported, never installed or enabled, so /setup's ask-before-installing holds (#35). Drop-ins follow their
# service.
if [[ "$mode" == update ]]; then
  mapfile -t have < <(owned_units)
  keep=() keep_enable=() keep_dropins=()
  for n in "${UNITS[@]}"; do
    if [[ " ${have[*]} " == *" $n "* ]]; then keep+=("$n"); else echo "new unit available: $n (install it with system/scripts/install_units.sh)"; fi
  done
  for n in "${ENABLE[@]}"; do [[ " ${keep[*]} " != *" $n "* ]] || keep_enable+=("$n"); done
  for d in "${DROPINS[@]}"; do [[ " ${keep[*]} " != *" ${d%%.d/*} "* ]] || keep_dropins+=("$d"); done
  UNITS=("${keep[@]}") ENABLE=("${keep_enable[@]}") DROPINS=("${keep_dropins[@]}")
fi
```

Replace:

```bash
if ! out="$(systemd-analyze --user verify "${rendered[@]}" 2>&1)"; then
```

with:

```bash
out=""
if (( ${#rendered[@]} )) && ! out="$(systemd-analyze --user verify "${rendered[@]}" 2>&1)"; then
```

Replace the last line:

```bash
"$SYSTEMCTL" --user enable --now "${ENABLE[@]}"
```

with:

```bash
(( ${#ENABLE[@]} == 0 )) || "$SYSTEMCTL" --user enable --now "${ENABLE[@]}"
```

- [ ] **Step 4: Call it from `update_template.sh`.** Replace:

```bash
if (( owned )); then
  system/scripts/install_units.sh
else
```

with:

```bash
if (( owned )); then
  system/scripts/install_units.sh --update
else
```

- [ ] **Step 5: Say so in the README.** In `README.md`, replace:

```text
Afterwards it rebuilds the index and re-renders the units, but only if this vault installed them. It never runs automatically.
```

with:

```text
Afterwards it rebuilds the index and re-renders only the units this vault installed. A unit the update adds is listed as `new unit available: <unit>` and left out; read `system/scripts/install_units.sh --dry-run`, then run `system/scripts/install_units.sh` to add it. It never runs automatically.
```

- [ ] **Step 6: Run the tests.**

Run: `bats system/tests/remote.bats; bats -f '#35' system/tests/commands.bats`
Expected: all `ok` (23 in `remote.bats`; see Global Constraints for the one test that needs a user session).

- [ ] **Step 7: Commit.**

```bash
git add system/scripts/install_units.sh system/scripts/update_template.sh README.md system/tests/remote.bats system/tests/commands.bats
git commit -m "fix(update): re-render only installed units and list new ones (#35)"
```

---

### Task 3: an HTTPS origin that needs a prompt gets its SSH form offered (#16)

**Files:**
- Modify: `system/scripts/setup_remote.sh:85-87`
- Modify: `.claude/commands/setup.md:40` (phase 4, check 2)
- Test: `system/tests/remote.bats`, `system/tests/commands.bats`

**Interfaces:**
- Produces: on stderr, `hint: git@<host>:<owner>/<repo>.git works without a prompt; to use it, run system/scripts/setup_remote.sh git@<host>:<owner>/<repo>.git`, printed after the existing `warning: origin … is not reachable yet` only when the SSH probe succeeds.

- [ ] **Step 1: Write the failing tests.** In `system/tests/remote.bats`, insert before `@test "<url> that is reachable sets origin without a warning" {`:

```bash
@test "<url> over https on a known host suggests its SSH form when that works without a prompt" {
  git init -q --bare "$BATS_TEST_TMPDIR/ssh/me/vault.git"
  git config url."$BATS_TEST_TMPDIR/ssh/".insteadOf git@github.com:  # the SSH form, served locally
  run "$SR" https://github.com/me/vault
  [ "$status" -eq 0 ]
  [ "$(git remote get-url origin)" = https://github.com/me/vault ]
  [[ "$output" == *"not reachable"* ]]
  [[ "$output" == *"hint: git@github.com:me/vault.git works without a prompt; to use it, run system/scripts/setup_remote.sh git@github.com:me/vault.git"* ]]
  run "$SR" https://github.com/me/other
  [ "$status" -eq 0 ]
  [[ "$output" != *"hint:"* ]]
  run "$SR" https://example.com/me/vault
  [ "$status" -eq 0 ]
  [[ "$output" != *"hint:"* ]]
}

```

Append to `system/tests/commands.bats`:

```bash

@test "/setup phase 4 offers setup_remote.sh's SSH hint before asking for credentials (#16)" {
  sec="$(setup_section '4. Remote')"
  [[ "$sec" == *'printed a `hint:` line with an SSH URL, offer that URL first'* ]]
}
```

- [ ] **Step 2: Run them to see them fail.**

Run: `bats -f 'known host' system/tests/remote.bats; bats -f '#16' system/tests/commands.bats`
Expected: two `not ok` (no `hint:` line; no phase 4 text).

- [ ] **Step 3: Probe the SSH form.** In `system/scripts/setup_remote.sh`, replace:

```bash
    echo "warning: origin $url is not reachable yet; it is set anyway" >&2
  fi
```

with:

```bash
    echo "warning: origin $url is not reachable yet; it is set anyway" >&2
    # An https URL needs a credential prompt that automation cannot answer; on a known host, offer the SSH
    # form when it works without one (#16).
    n="$(git_url_normalize "$url")"
    case "$url" in https://github.com/*|https://gitlab.com/*|https://bitbucket.org/*)
      ssh_url="git@${n%%/*}:${n#*/}.git"
      if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh} -o BatchMode=yes" \
          timeout 20 git ls-remote --heads "$ssh_url" >/dev/null 2>&1; then
        echo "hint: $ssh_url works without a prompt; to use it, run system/scripts/setup_remote.sh $ssh_url" >&2
      fi ;;
    esac
  fi
```

- [ ] **Step 4: Offer it in `/setup`.** In `.claude/commands/setup.md`, replace:

```text
2. `GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote origin > /dev/null` succeeds. If not, explain
```

with:

```text
2. `GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote origin > /dev/null` succeeds. If not, and `setup_remote.sh` printed a `hint:` line with an SSH URL, offer that URL first: on yes, run `system/scripts/setup_remote.sh <that URL>` and re-check. Otherwise explain
```

- [ ] **Step 5: Run the tests.**

Run: `bats system/tests/remote.bats; bats -f '#16' system/tests/commands.bats`
Expected: all `ok`.

- [ ] **Step 6: Commit.**

```bash
git add system/scripts/setup_remote.sh .claude/commands/setup.md system/tests/remote.bats system/tests/commands.bats
git commit -m "feat(remote): offer the SSH form of an https origin that needs a prompt (#16)"
```

---

### Task 4: `/setup` stops on an origin with unrelated history (#15)

**Files:**
- Modify: `.claude/commands/setup.md:41` (phase 4, check 3)
- Test: `system/tests/commands.bats`

**Interfaces:** none.

- [ ] **Step 1: Write the failing test.** Append to `system/tests/commands.bats`:

```bash

@test "/setup phase 4 stops on an origin with unrelated history before setting the upstream (#15)" {
  sec="$(setup_section '4. Remote')"
  for s in 'git merge-base HEAD "origin/<branch>"' 'git log --oneline "origin/<branch>"' \
      'git push --force-with-lease="<branch>:<that commit>" -u origin HEAD' \
      'git merge --allow-unrelated-histories "origin/<branch>"' 'Run either only on an explicit yes.'; do
    [[ "$sec" == *"$s"* ]]
  done
  check="${sec%%git merge-base HEAD*}"
  upstream="${sec%%git branch -u*}"
  [ "${#check}" -lt "${#upstream}" ]
}
```

- [ ] **Step 2: Run it to see it fail.**

Run: `bats -f '#15' system/tests/commands.bats`
Expected: `not ok 1`.

- [ ] **Step 3: Add the check.** In `.claude/commands/setup.md`, replace:

```text
Otherwise, if `git rev-parse --abbrev-ref '@{u}'` is not `origin/<branch>` (`setup_remote.sh` moves the upstream to `template` when it renames a plain clone's `origin`), run `git fetch origin` and `git branch -u "origin/$(git branch --show-current)"`. Report the result.
```

with:

```text
Otherwise run `git fetch origin` and `git merge-base HEAD "origin/<branch>"`. If that prints nothing, `origin` holds a history of its own (often the README commit a hosting site offers to create), and the first sync would fail: stop and show `git log --oneline "origin/<branch>"`. When it is one commit, offer to replace it with `git push --force-with-lease="<branch>:<that commit>" -u origin HEAD`; otherwise offer `git merge --allow-unrelated-histories "origin/<branch>"`. Run either only on an explicit yes. Then, if `git rev-parse --abbrev-ref '@{u}'` is not `origin/<branch>` (`setup_remote.sh` moves the upstream to `template` when it renames a plain clone's `origin`), run `git branch -u "origin/$(git branch --show-current)"`. Report the result.
```

- [ ] **Step 4: Run the setup tests.**

Run: `bats system/tests/commands.bats`
Expected: all `ok` (the existing "/setup phase 4 checks every private vault and sets the upstream to origin" still finds `git branch -u "origin/$(git branch --show-current)"`).

- [ ] **Step 5: Commit.**

```bash
git add .claude/commands/setup.md system/tests/commands.bats
git commit -m "fix(setup): stop on a private origin with unrelated history (#15)"
```

---

### Task 5: codebase inspection caps manifests per kind (#18)

**Files:**
- Modify: `system/scripts/vaultlib/codebase_inspect.py:100-137`
- Modify: `system/scripts/inspect_codebase.py:10-17`
- Modify: `.claude/commands/setup.md:29` (phase 3, `stack`)
- Test: `system/tests/python/test_codebase_inspect.py`, `system/tests/codebases.bats`, `system/tests/commands.bats`

**Interfaces:**
- Produces: `inspect_repo(path: Path, per_kind: int | None = None) -> dict`. `None` keeps every manifest (the default, so existing callers and tests are unchanged). The result gains `manifest_counts: {kind: count}` and `notable: [sorted names]`, both over every manifest. CLI: `inspect_codebase.sh [--all-manifests] <path>`; without the flag `per_kind=5`.

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/python/test_codebase_inspect.py`:

```python


def test_per_kind_keeps_the_shallowest_manifests_and_counts_every_one(tmp_path):
    files = {f"src/P{i}/P{i}.csproj": "<Project/>" for i in range(7)}
    files.update({"App.csproj": "<Project/>", "web/package.json": '{"dependencies": {"vue": "3"}}',
                  "tools/admin/package.json": '{"dependencies": {"react": "18"}}'})
    repo = make_repo(tmp_path / "r", files)
    result = inspect_repo(repo, per_kind=3)
    assert [m["file"] for m in result["manifests"]] == [
        "App.csproj", "src/P0/P0.csproj", "src/P1/P1.csproj", "tools/admin/package.json", "web/package.json"]
    assert result["manifest_counts"] == {"dotnet": 8, "npm": 2}
    one = inspect_repo(repo, per_kind=1)
    assert [m["file"] for m in one["manifests"]] == ["App.csproj", "web/package.json"]
    assert one["notable"] == ["react", "vue"]  # the dropped tools/admin manifest still counts
    assert len(inspect_repo(repo)["manifests"]) == 10
```

Append to `system/tests/codebases.bats`:

```bash

@test "inspect: at most 5 manifests of a kind unless --all-manifests, with every one counted" {
  mkrepo "$R/app"
  for i in 1 2 3 4 5 6 7; do mkdir -p "$R/app/P$i"; printf '<Project/>' > "$R/app/P$i/P$i.csproj"; done
  git -C "$R/app" add -A
  run "$IC" "$R/app"
  [ "$status" -eq 0 ]
  [ "$(jq '.manifests | length' <<< "$output")" -eq 5 ]
  [ "$(jq -c .manifest_counts <<< "$output")" = '{"dotnet":7}' ]
  run "$IC" --all-manifests "$R/app"
  [ "$status" -eq 0 ]
  [ "$(jq '.manifests | length' <<< "$output")" -eq 7 ]
  run "$IC" --all-manifests
  [ "$status" -eq 2 ]
}
```

Append to `system/tests/commands.bats`:

```bash

@test "/setup phase 3 drafts the stack from the manifest counts (#18)" {
  sec="$(setup_section '3. Codebases')"
  [[ "$sec" == *'`manifest_counts`'* ]]
  [[ "$sec" == *'inspect_codebase.sh --all-manifests <path>'* ]]
}
```

- [ ] **Step 2: Run them to see them fail.**

Run: `python3 -m pytest system/tests/python/test_codebase_inspect.py -q; bats -f 'at most 5' system/tests/codebases.bats; bats -f '#18' system/tests/commands.bats`
Expected: `TypeError: inspect_repo() got an unexpected keyword argument 'per_kind'`; two `not ok`.

- [ ] **Step 3: Cap in `inspect_repo`.** In `system/scripts/vaultlib/codebase_inspect.py`, replace:

```python
def inspect_repo(path: Path) -> dict:
    top
```

with:

```python
def inspect_repo(path: Path, per_kind: int | None = None) -> dict:
    """per_kind: keep at most that many manifests of each kind, the shallowest first; manifest_counts and
    notable still cover every manifest (a large monorepo lists hundreds of .csproj files, #18)."""
    top
```

Replace:

```python
    branch = _git(repo, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD").strip().removeprefix("origin/")
```

with:

```python
    counts = Counter(m["kind"] for m in manifests)
    notable = sorted({n for m in manifests for n in m["details"].get("notable", [])})
    if per_kind is not None:
        keep = set()
        for kind in counts:
            same = sorted((m for m in manifests if m["kind"] == kind), key=lambda m: (m["file"].count("/"), m["file"]))
            keep.update(m["file"] for m in same[:per_kind])
        manifests = [m for m in manifests if m["file"] in keep]
    branch = _git(repo, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD").strip().removeprefix("origin/")
```

Replace:

```python
        "manifests": manifests,
```

with:

```python
        "manifests": manifests,
        "manifest_counts": dict(sorted(counts.items())),
        "notable": notable,
```

- [ ] **Step 4: Add the flag.** In `system/scripts/inspect_codebase.py`, replace:

```python
if len(sys.argv) != 2:
    print("usage: inspect_codebase.sh <path>", file=sys.stderr)
    sys.exit(2)
try:
    print(json.dumps(inspect_repo(Path(sys.argv[1]).resolve())))
except NotARepo:
    print(f"inspect_codebase: not a git work tree: {sys.argv[1]}", file=sys.stderr)
    sys.exit(2)
```

with:

```python
PER_KIND = 5  # manifests shown per kind; --all-manifests lists every one
args = sys.argv[1:]
every = args[:1] == ["--all-manifests"]
if every:
    args = args[1:]
if len(args) != 1:
    print("usage: inspect_codebase.sh [--all-manifests] <path>", file=sys.stderr)
    sys.exit(2)
try:
    print(json.dumps(inspect_repo(Path(args[0]).resolve(), per_kind=None if every else PER_KIND)))
except NotARepo:
    print(f"inspect_codebase: not a git work tree: {args[0]}", file=sys.stderr)
    sys.exit(2)
```

- [ ] **Step 5: Point `/setup` at the new fields.** In `.claude/commands/setup.md`, replace:

```text
`stack` (from manifest kinds and notable dependencies)
```

with:

```text
`stack` (from `manifest_counts` and `notable`; `manifests` shows at most 5 of each kind, and `inspect_codebase.sh --all-manifests <path>` lists every one)
```

- [ ] **Step 6: Run the tests.**

Run: `python3 -m pytest system/tests/python/test_codebase_inspect.py -q; bats system/tests/codebases.bats; bats -f '#18' system/tests/commands.bats`
Expected: `16 passed`; all `ok`.

- [ ] **Step 7: Commit.**

```bash
git add system/scripts/vaultlib/codebase_inspect.py system/scripts/inspect_codebase.py .claude/commands/setup.md \
  system/tests/python/test_codebase_inspect.py system/tests/codebases.bats system/tests/commands.bats
git commit -m "fix(inspect): show at most 5 manifests per kind, count them all (#18)"
```

---

### Task 6: `/setup` uses up-front answers and names a scanned worktree (#20)

**Files:**
- Modify: `.claude/commands/setup.md:5`, `:27`
- Modify: `README.md:239` ("The prompt:")
- Test: `system/tests/commands.bats`

**Interfaces:** none.

- [ ] **Step 1: Write the failing test.** Append to `system/tests/commands.bats`:

```bash

@test "/setup uses answers given up front and says when a scanned worktree is not the registered path (#20)" {
  grep -qF 'use them and ask only for what is missing; an answer still written as `<…>` is missing' .claude/commands/setup.md
  sec="$(setup_section '3. Codebases')"
  [[ "$sec" == *'If the directory you scanned is one of a repo'"'"'s `worktrees` but not its `path`'* ]]
  grep -qF 'replace every `<…>` first' README.md
}
```

- [ ] **Step 2: Run it to see it fail.**

Run: `bats -f '#20' system/tests/commands.bats`
Expected: `not ok 1`.

- [ ] **Step 3: Edit the prompt.** In `.claude/commands/setup.md`, replace:

```text
Every phase is idempotent: show what exists and edit it, never overwrite blindly. Ask one question at a time, show the default, and wait for the answer.
```

with:

```text
Every phase is idempotent: show what exists and edit it, never overwrite blindly. When the user gave answers up front (the README's setup prompt), use them and ask only for what is missing; an answer still written as `<…>` is missing. Ask one question at a time, show the default, and wait for the answer.
```

Replace:

```text
Run `system/scripts/discover_codebases.sh <dir>` and show the repos it prints (path, worktrees, remote). Ask which to register.
```

with:

```text
Run `system/scripts/discover_codebases.sh <dir>` and show the repos it prints (path, worktrees, remote). If the directory you scanned is one of a repo's `worktrees` but not its `path`, say that `path` is the repo's main checkout and ask which of the two to register. Ask which to register.
```

- [ ] **Step 4: Edit the README.** In `README.md`, replace:

````text
The prompt:

```text
````

with:

````text
The prompt (replace every `<…>` first; `/setup` asks for any answer still written as `<…>`):

```text
````

- [ ] **Step 5: Run the tests.**

Run: `bats system/tests/commands.bats`
Expected: all `ok`.

- [ ] **Step 6: Commit.**

```bash
git add .claude/commands/setup.md README.md system/tests/commands.bats
git commit -m "docs(setup): use up-front answers and name a scanned worktree (#20)"
```

---

### Task 7: Verify the branch

- [ ] **Step 1: Run the suites.**

```bash
python3 -m pytest system/tests/python -q; echo "pytest exit=$?"
bats system/tests/remote.bats system/tests/setup.bats system/tests/codebases.bats system/tests/commands.bats system/tests/vault_integrity.bats; echo "bats exit=$?"
```

Expected: `pytest exit=0`; `bats exit=0` on a host with a user session (in a sandbox, only the one `remote.bats` test named in Global Constraints fails).

- [ ] **Step 2: Lint.** `system/scripts/vault_index.py rebuild > /dev/null && system/scripts/vault_index.py issues | tail -n 1`
Expected: `0 errors` (the warnings #19 removes may remain if the lint plan has not landed).
