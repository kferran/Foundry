# Plan 2a: Headless Core (Wheeljack + Ultra Magnus) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the isolated headless pipeline: argument and config helpers, the committed permission files, secret redaction, Ultra Magnus (staged, validated, journaled, recoverable publish plus the `stage` subcommand), `run_headless.sh` (the only way automation calls `claude`), and the Wheeljack intake daemon with its retry and poisoning policy.

**Architecture:** Headless Claude writes only into `wiki/.staging/<run_id>/`. `run_headless.sh` snapshots the publishable targets, runs `claude -p` in `--restricted` mode with the command body inlined, then hands the staging tree to `publish_staged.py`, which validates every file (target, schema, partition walls, protected fields, shrink guard, conflicts) and publishes all-or-nothing through a journal that recovery can roll forward. The intake daemon (`vaultlib/intake.py` behind `intake_daemon.sh`) feeds inbox files and digest batches to `run_headless.sh`, leaving inputs in place until they succeed and poisoning them after three failures.

**Tech Stack:** bash 5, GNU coreutils (`flock`, `timeout`, `realpath`, `date`, `sha256sum`), `jq`, Python 3.14 (stdlib + PyYAML), pytest, bats, the `claude` CLI 2.1.x.

**Spec:** `docs/superpowers/specs/2026-09-30-vault-template-design.md` — this plan implements §6 (shell conventions, argument validation), §6.1, §6.3, §6.4, §6.18, §6.20, §7.1, §7.2, and the §7.4 final-form gate. It builds on Plan 1; read `docs/superpowers/plans/2026-09-30-plan-1-outcomes.md` for rulings that shaped the interfaces used here.

## Global Constraints

- Python: `#!/usr/bin/env python3`, stdlib + PyYAML only, no network; never crash on bad input notes (problems become reported records).
- Vault root: every script, shell or Python, derives the vault root **only** from its own location (`system/scripts/…` → two levels up; `vaultlib/…` → three); no `VAULT_ROOT` environment override. Tests copy `system/scripts/` into a temporary vault and run that copy.
- Invocation form: scripts are executable and invoked as `system/scripts/<name> …` from the vault root (§6).
- Argument validation (§6): dates `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` and a real date; file arguments resolve (realpath) inside the vault; raw filenames `^[A-Za-z0-9._ -]+$`; invalid → exit 2 with a message.
- Headless invocation (§6.3, spike-confirmed): `timeout "${HEADLESS_TIMEOUT:-15m}" "$CLAUDE_BIN" -p "$prompt" --append-system-prompt-file CLAUDE.md --restricted --settings system/headless.settings.json --strict-mcp-config --no-session-persistence --permission-mode dontAsk --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" --allowedTools … < /dev/null`; never `--setting-sources`.
- Headless writes only under `wiki/.staging/<run_id>/**`; nothing reaches the vault except through `publish_staged.py`.
- `run_headless.sh` exit codes: 0 success; claude's non-zero code; 124 timeout; 2 usage; 3 invalid settings; 4 daily cap (inputs untouched); 5 publish rejected or nothing published; 6 `run.lock` wait timed out (brief/debrief).
- Ledger: `system/logs/runs-<YYYY-MM>.jsonl`, one JSON line per invocation, written by `run_headless.sh`; daily cap `HEADLESS_MAX_RUNS_PER_DAY` default 60, counted in the configured timezone.
- Publish (§6.20): all-or-nothing validation; shrink guard keeps ≥ 60% of body, every frontmatter key and heading unless the decision is `deprecate`/`supersede`; conflict if the target changed since snapshot/stage, was created during the run, or was modified in the last 60 s; protected fields `accepted_at`, `rejected_at`; `headless` appended to `provenance`; journal + `fsync` before renames; recovery rolls forward under `run.lock`.
- Intake (§6.4): skip files modified < 60 s ago; at most `INTAKE_MAX_RUNS` (default 5) headless runs per daemon run; digest batches ≤ 5 per partition; poisoned after 3 failed attempts since the last retry.
- Settings files are exactly §7.1 and §7.2, including `"sandbox": {"enabled": true, "autoAllowBashIfSandboxed": false}` in `headless.settings.json`.
- Commit trailers name the model that authored the commit (Plan 1 ruling); work on branch `feat/vault-template`.

## Review Focus

1. **An inbox file with spaces and non-ASCII characters in its name (`Meeting – café notes.md`).** Users drag files in from anywhere; the raw-filename rule must sanitize it, not crash or skip it forever. Pinned in Task 8 (`test_unicode_name_sanitized`).
2. **A Claude run that writes a staged file through a symlink or a `..` path.** The staging tree is model-controlled; publish must reject it, never write outside the target. Pinned in Task 5 (`test_staged_symlink_rejected`, `test_unsafe_staged_path_rejected`).
3. **Two intake daemons started at once (a timer firing while a manual run is in progress).** They must not ingest the same file twice. Pinned in Task 8 (`test_concurrent_daemons_do_not_double_ingest`).
4. **Publishing a note the user is editing in Obsidian at the same moment.** The user's edit must win. Pinned in Task 6 (`test_target_changed_between_validation_and_rename_is_held_back`).
5. **A malformed line in the run ledger (a crash mid-write).** Cap counting and retry accounting must skip it, not abort every future run. Pinned in Task 7 (`@test "malformed ledger line is ignored"`) and Task 9 (`test_malformed_ledger_line_ignored`).

---

## File Structure

| File | Responsibility |
|---|---|
| `system/scripts/lib_args.sh` | Shared shell argument validators |
| `system/scripts/lib_config.sh` | Shell config/codebase helpers over `vault_index.py field/set/validate` |
| `.claude/settings.json` | Interactive permission allowlist and deny list (§7.1) |
| `system/headless.settings.json` | Headless deny list, read fence, sandbox (§7.2) |
| `system/scripts/vaultlib/redact.py`, `system/scripts/redact.py` | Secret redaction (§6.18) |
| `system/scripts/vaultlib/publish.py` | Snapshot, stage records, decisions, validation, journal, commit, recovery |
| `system/scripts/vaultlib/publish_cli.py`, `system/scripts/publish_staged.py` | Publish CLI |
| `system/scripts/vaultlib/cli.py` (modify) | `stage` subcommand |
| `system/scripts/run_headless.sh` | Headless harness (§6.3) |
| `system/scripts/vaultlib/intake.py`, `system/scripts/intake.py`, `system/scripts/intake_daemon.sh` | Intake daemon (§6.4) |
| `system/tests/lib.bats`, `system/tests/headless.bats` | Shell suites for the libraries and the harness |
| `system/tests/python/test_redact.py`, `test_publish.py`, `test_publish_commit.py`, `test_stage_cli.py`, `test_intake.py`, `test_intake_digests.py` | pytest suites |

Gating suites from now on: `python3 -m pytest system/tests/python -q` and `bats system/tests/vault_integrity.bats system/tests/scripts.bats system/tests/lib.bats system/tests/headless.bats`.

---

### Task 1: Final-form gate (spike items 4, 6, 18 with the real invocation)

**Files:**
- Modify: `docs/superpowers/spikes/2026-09-30-headless-and-hooks.md` (append a "Final-form gate" section)
- Throwaway (outside the repo): `${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-gate/`

**Interfaces:**
- Consumes: nothing from code; this validates the §6.3 invocation before Tasks 7–9 depend on it.
- Produces: a recorded PASS/FAIL for each check. A FAIL stops the plan: report it and ask for a spec ruling before continuing.

- [ ] **Step 1: Build the throwaway vault**

```bash
G="${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-gate"
rm -rf "$G" && mkdir -p "$G/vault" && cd "$G/vault" && git init -q
mkdir -p .claude/commands system/scripts wiki/work/concepts wiki/personal wiki/.staging
printf '# Gate vault\nGATE-CLAUDE-MD-MARKER\n' > CLAUDE.md
printf -- '---\ntype: concept\n---\nold\n' > wiki/work/concepts/Existing.md
echo secret > ../outside.txt
cat > system/scripts/vault_index.py <<'EOF'
#!/usr/bin/env python3
import shutil, sys
from pathlib import Path
print("STUB", sys.argv[1:])
if len(sys.argv) >= 4 and sys.argv[1] == "stage":
    dst = Path("wiki/.staging") / sys.argv[3] / sys.argv[2]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.argv[2], dst)
EOF
chmod +x system/scripts/vault_index.py
cat > system/headless.settings.json <<'EOF'
{
  "permissions": {
    "blockReadsOutsideWorkingDirectories": true,
    "deny": [
      "Read(~/.ssh/**)", "Read(~/.gnupg/**)",
      "Read(~/.claude/.credentials.json)", "Read(~/.claude.json)", "Read(~/.claude/settings*.json)",
      "Read(~/.config/gcalcli/**)", "Read(//**/.env)", "Read(//**/.env.*)"
    ]
  },
  "sandbox": {"enabled": true, "autoAllowBashIfSandboxed": false}
}
EOF
cat > .claude/commands/gate.md <<'EOF'
---
description: final-form gate
---
Quote the line of your system instructions that contains GATE-CLAUDE-MD-MARKER, then perform each action once, in order, even if you expect denial, reporting "ACTION <n>: ALLOWED" or "ACTION <n>: DENIED <reason>":
1. Write `wiki/.staging/$ARGUMENTS/wiki/work/concepts/New.md` with text `new`.
2. Write `wiki/personal/Leak.md` with text `leak`.
3. Run Bash: `system/scripts/vault_index.py query "SELECT 1"`
4. Run Bash: `python3 system/scripts/vault_index.py query "SELECT 1"`
5. Run Bash: `touch wiki/work/x.md`
6. Run Bash: `system/scripts/vault_index.py stage wiki/work/concepts/Existing.md $ARGUMENTS`, then Edit `wiki/.staging/$ARGUMENTS/wiki/work/concepts/Existing.md` replacing `old` with `new`.
7. Read `../outside.txt`.
EOF
git add -A && git commit -qm gate
```

- [ ] **Step 2: Run the final invocation exactly as `run_headless.sh` will**

```bash
cd "$G/vault"
RID=20261001T000000-ingest-abcd
body="$(awk 'NR==1 && $0=="---" {fm=1; next} fm && $0=="---" {fm=0; next} !fm' .claude/commands/gate.md)"
prompt="${body//\$ARGUMENTS/$RID}"
vi=system/scripts/vault_index.py
JARVIS_HEADLESS=1 timeout 15m claude -p "$prompt" --append-system-prompt-file CLAUDE.md \
  --restricted --settings system/headless.settings.json --strict-mcp-config --no-session-persistence \
  --permission-mode dontAsk --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" \
  --allowedTools "Edit(/wiki/.staging/$RID/**)" "Bash($vi query:*)" "Bash($vi stage:*)" < /dev/null > "$G/out.json"
echo "exit=$?"
jq -r '.result' "$G/out.json"
jq '.permission_denials | length' "$G/out.json"
find wiki -type f | sort; ls wiki/work/x.md 2>/dev/null || echo "no x.md"
cat "wiki/.staging/$RID/wiki/work/concepts/Existing.md"
```
Expected: the marker line is quoted (CLAUDE.md appended); ACTION 1 ALLOWED; 2 DENIED; 3 ALLOWED with `STUB`; 4 DENIED; 5 DENIED and `no x.md`; 6 ALLOWED and the staged copy contains `new`; 7 DENIED; `permission_denials` ≥ 4; `wiki/personal/` empty.

- [ ] **Step 3: Record the results**

Append to `docs/superpowers/spikes/2026-09-30-headless-and-hooks.md`:
```markdown
## Final-form gate (Plan 2a Task 1, <date>)

Invocation: §6.3 final form (restricted, inlined prompt, `--append-system-prompt-file CLAUDE.md`, sandbox with `autoAllowBashIfSandboxed: false`).

| Check | Observed (excerpt) | Result |
|---|---|---|
| CLAUDE.md appended | | |
| Staging write allowed | | |
| wiki/personal write denied | | |
| Allowlisted Bash runs | | |
| `python3 …` form denied | | |
| Unlisted `touch` denied under sandbox | | |
| `stage` → Edit on staged copy | | |
| Out-of-vault read denied | | |
| permission_denials count | | |
```
Fill every row from Step 2's output. If any row is FAIL, stop and report it.

- [ ] **Step 4: Commit and clean up**

```bash
cd /home/fe/Work/Jarvis
git add docs/superpowers/spikes/2026-09-30-headless-and-hooks.md
git commit -m "docs: record Plan 2a final-form headless gate"
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-gate"
```

---

### Task 2: `lib_args.sh`, shell test harness, spec amendments

**Files:**
- Create: `system/scripts/lib_args.sh`, `system/tests/lib.bats`, `system/tests/helpers.bash`
- Modify: `docs/superpowers/specs/2026-09-30-vault-template-design.md` (§6 shell conventions; §6.3 exit codes)

**Interfaces:**
- Produces (sourced after `VAULT_ROOT` is set and `cd "$VAULT_ROOT"`):
  - `args_date VALUE` → status 0 iff `YYYY-MM-DD` and a real calendar date
  - `args_vault_path ARG` → prints the vault-relative path of an existing regular file inside `VAULT_ROOT` (ARG resolved from cwd); status 1 otherwise
  - `args_raw_filename NAME` → status 0 iff `^[A-Za-z0-9._ -]+$` and not starting with `.`
  - `args_sanitize_filename NAME` → prints NAME with every disallowed character replaced by `_`, leading dots stripped, `file` if empty
- Produces for later bats files: `helpers.bash` with `make_vault` (sets `$V` to a fresh temp vault containing the fixture notes, real schemas, a copy of `system/scripts/`, `CLAUDE.md`, `.claude/commands/`, both settings files when they exist, and a minimal `system/config.md`).

- [ ] **Step 1: Write the shared bats helper**

`system/tests/helpers.bash`:
```bash
# Shared setup for shell suites. Usage: load helpers; make_vault
make_vault() {
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  V="$BATS_TEST_TMPDIR/vault"
  unset VAULT_ROOT
  cp -r "$REPO/system/tests/fixtures/vault" "$V"
  mkdir -p "$V/system" "$V/.claude"
  cp -r "$REPO/system/schemas" "$V/system/schemas"
  mkdir -p "$V/system/scripts"
  cp -r "$REPO/system/scripts/." "$V/system/scripts/"
  rm -rf "$V/system/scripts/__pycache__" "$V/system/scripts/vaultlib/__pycache__"
  cp "$REPO/CLAUDE.md" "$V/CLAUDE.md"
  cp -r "$REPO/.claude/commands" "$V/.claude/commands"
  [[ -f "$REPO/system/headless.settings.json" ]] && cp "$REPO/system/headless.settings.json" "$V/system/"
  [[ -f "$REPO/.claude/settings.json" ]] && cp "$REPO/.claude/settings.json" "$V/.claude/"
  cat > "$V/system/config.md" <<'EOF'
---
type: config
timezone: "America/Denver"
brief_time: "06:00"
debrief_time: "17:00"
remote_mode: "none"
default_partition: "personal"
---
EOF
  git -C "$V" init -q
  git -C "$V" config user.email test@example.com
  git -C "$V" config user.name test
}
```

- [ ] **Step 2: Write the failing tests**

`system/tests/lib.bats`:
```bash
#!/usr/bin/env bats
load helpers

setup() {
  make_vault
  cd "$V"
  VAULT_ROOT="$(pwd -P)"
  source system/scripts/lib_args.sh
}

@test "args_date accepts real dates only" {
  args_date 2026-10-01
  ! args_date 2026-02-30
  ! args_date 2026-1-01
  ! args_date "2026-10-01; rm -rf /"
  ! args_date ""
}

@test "args_vault_path resolves inside the vault" {
  run args_vault_path wiki/work/concepts/Kafka.md
  [ "$status" -eq 0 ] && [ "$output" = "wiki/work/concepts/Kafka.md" ]
  cd wiki
  run args_vault_path ../wiki/work/concepts/Kafka.md
  [ "$output" = "wiki/work/concepts/Kafka.md" ]
}

@test "args_vault_path rejects outside, missing, directories and escaping symlinks" {
  echo x > "$BATS_TEST_TMPDIR/out.md"
  ln -s "$BATS_TEST_TMPDIR/out.md" wiki/work/concepts/Link.md
  ! args_vault_path "$BATS_TEST_TMPDIR/out.md"
  ! args_vault_path ../out.md
  ! args_vault_path wiki/nope.md
  ! args_vault_path wiki
  ! args_vault_path wiki/work/concepts/Link.md
}

@test "args_raw_filename and sanitize" {
  args_raw_filename "Meeting notes 2026-10-01.md"
  ! args_raw_filename ".hidden.md"
  ! args_raw_filename "bad:name?.md"
  ! args_raw_filename "café.md"
  [ "$(args_sanitize_filename 'bad:name?.md')" = "bad_name_.md" ]
  [ "$(args_sanitize_filename '..hidden')" = "hidden" ]
  [ "$(args_sanitize_filename '???')" = "___" ]
  [ "$(args_sanitize_filename '')" = "file" ]
}
```

- [ ] **Step 3: Run to verify failure**

Run: `bats system/tests/lib.bats`
Expected: FAIL (`lib_args.sh: No such file or directory`).

- [ ] **Step 4: Implement**

`system/scripts/lib_args.sh`:
```bash
# shellcheck shell=bash
# Shared argument validators (spec §6). Source after VAULT_ROOT is set (physical path) and cd "$VAULT_ROOT".

args_date() {
  [[ "${1-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || return 1
  [[ "$(date -d "$1" +%F 2>/dev/null)" == "$1" ]]
}

args_vault_path() {
  local abs
  abs="$(realpath -e -- "${1-}" 2>/dev/null)" || return 1
  [[ -f "$abs" ]] || return 1
  case "$abs" in
    "$VAULT_ROOT"/*) printf '%s\n' "${abs#"$VAULT_ROOT"/}" ;;
    *) return 1 ;;
  esac
}

args_raw_filename() {
  [[ "${1-}" =~ ^[A-Za-z0-9._\ -]+$ && "${1-}" != .* ]]
}

args_sanitize_filename() {
  local s
  s="$(printf '%s' "${1-}" | LC_ALL=C sed 's/[^A-Za-z0-9._ -]/_/g')"
  while [[ "$s" == .* ]]; do s="${s#.}"; done
  printf '%s\n' "${s:-file}"
}
```
Note: `realpath -e` on `wiki/work/concepts/Link.md` resolves the symlink to the outside file, so the prefix check rejects it. `LC_ALL=C sed` treats each byte of a multi-byte character as disallowed, so `café` becomes `caf__`.

- [ ] **Step 5: Run to verify pass**

Run: `bats system/tests/lib.bats`
Expected: `4 tests, 0 failures`.

- [ ] **Step 6: Amend the spec**

In `docs/superpowers/specs/2026-09-30-vault-template-design.md` §6, replace the shell-scripts sentence "locate the vault as `VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`, and respect a `VAULT_ROOT` env override for tests." with "locate the vault as `VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"` and never read `VAULT_ROOT` from the environment (tests copy `system/scripts/` into the temporary vault)." In §6.3 **Exit code**, append "; 6 `run.lock` wait timed out (`brief`/`debrief`)".

- [ ] **Step 7: Commit**

```bash
git add system/scripts/lib_args.sh system/tests/lib.bats system/tests/helpers.bash docs/superpowers/specs/2026-09-30-vault-template-design.md
git commit -m "feat: add shell argument validators and shared bats vault helper"
```

---

### Task 3: `lib_config.sh`

**Files:**
- Create: `system/scripts/lib_config.sh`
- Modify: `system/tests/lib.bats` (append tests)

**Interfaces:**
- Consumes: `vault_index.py field|set|validate` (Plan 1), `VAULT_ROOT`.
- Produces (sourced): `config_get KEY [DEFAULT]`, `config_set KEY VALUE`, `codebases_list`, `codebase_get NAME KEY [DEFAULT]`, `codebase_default`, `config_validate` — semantics exactly as spec §6.1. Codebase NAME is the file stem of `system/codebases/<NAME>.md`.

- [ ] **Step 1: Write the failing tests (append to `system/tests/lib.bats`)**

```bash
lib_config_setup() {
  source system/scripts/lib_config.sh
  mkdir -p system/codebases
  mkdir -p "$BATS_TEST_TMPDIR/repo-a" "$BATS_TEST_TMPDIR/repo-b"
  git -C "$BATS_TEST_TMPDIR/repo-a" init -q
  git -C "$BATS_TEST_TMPDIR/repo-b" init -q
  printf -- '---\ntype: codebase\nname: "a"\npath: "%s"\npartition: work\ndefault: "true"\nstack: [vue3, dotnet]\nsearch_globs: ["*.ts"]\nlayers:\n  ui: "web/"\n---\n' "$BATS_TEST_TMPDIR/repo-a" > system/codebases/a.md
  printf -- '---\ntype: codebase\nname: "b"\npath: "%s"\npartition: personal\nsearch_globs: ["*.py"]\n---\n' "$BATS_TEST_TMPDIR/repo-b" > system/codebases/b.md
  printf -- '---\ntype: codebase\nname: "example"\npath: "~/code/example"\npartition: work\ndefault: "false"\nsearch_globs: ["*"]\n---\n' > system/codebases/example.md
}

@test "config_get returns values, defaults and expands ~" {
  lib_config_setup
  [ "$(config_get timezone)" = "America/Denver" ]
  [ "$(config_get missing fallback)" = "fallback" ]
  run "$V/system/scripts/vault_index.py" set system/config.md template_remote "~/x"
  [ "$(config_get template_remote)" = "$HOME/x" ]
}

@test "config_set writes a scalar" {
  lib_config_setup
  config_set remote_mode keep
  [ "$(config_get remote_mode)" = "keep" ]
}

@test "codebases_list excludes example and codebase_get reads nested and list keys" {
  lib_config_setup
  [ "$(codebases_list | tr '\n' ' ')" = "a b " ]
  [ "$(codebase_get a partition)" = "work" ]
  [ "$(codebase_get a layers.ui)" = "web/" ]
  [ "$(codebase_get a stack)" = "vue3,dotnet" ]
  [ "$(codebase_get b missing dflt)" = "dflt" ]
  run codebase_get "../config" timezone
  [ "$status" -ne 0 ]
}

@test "codebase_default picks default true, or the only codebase" {
  lib_config_setup
  [ "$(codebase_default)" = "a" ]
  rm system/codebases/a.md
  [ "$(codebase_default)" = "b" ]
}

@test "config_validate passes good config and fails a bad timezone" {
  lib_config_setup
  run config_validate
  [ "$status" -eq 0 ]
  "$V/system/scripts/vault_index.py" set system/config.md timezone "Mars/Olympus" || true
  sed -i 's#^timezone: .*#timezone: "Mars/Olympus"#' system/config.md
  run config_validate
  [ "$status" -eq 1 ]
}
```

- [ ] **Step 2: Run to verify failure**

Run: `bats system/tests/lib.bats`
Expected: the 5 new tests FAIL (`lib_config.sh: No such file or directory`).

- [ ] **Step 3: Implement**

`system/scripts/lib_config.sh`:
```bash
# shellcheck shell=bash
# Config and codebase helpers (spec §6.1). Source after VAULT_ROOT is set; all parsing via vault_index.py.

_vi() { (cd "$VAULT_ROOT" && system/scripts/vault_index.py "$@"); }

_expand_home() {
  local v="${1-}"
  if [[ "$v" == "~" || "$v" == "~/"* ]]; then v="$HOME${v:1}"; fi
  printf '%s\n' "$v"
}

config_get() {
  local v
  if v="$(_vi field system/config.md "$1" 2>/dev/null)" && [[ -n "$v" ]]; then
    _expand_home "$v"
  else
    printf '%s\n' "${2-}"
  fi
}

config_set() { _vi set system/config.md "$1" "$2"; }

codebases_list() {
  local f name
  for f in "$VAULT_ROOT"/system/codebases/*.md; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f" .md)"
    [[ "$name" == example ]] && continue
    printf '%s\n' "$name"
  done
}

codebase_get() {
  local name="$1" key="$2" v
  [[ "$name" =~ ^[A-Za-z0-9._-]+$ && "$name" != .* ]] || return 2
  if v="$(_vi field "system/codebases/$name.md" "$key" 2>/dev/null)" && [[ -n "$v" ]]; then
    _expand_home "$v"
  else
    printf '%s\n' "${3-}"
  fi
}

codebase_default() {
  local names=() n
  mapfile -t names < <(codebases_list)
  if (( ${#names[@]} == 1 )); then printf '%s\n' "${names[0]}"; return 0; fi
  for n in "${names[@]}"; do
    if [[ "$(codebase_get "$n" default false)" == "true" ]]; then printf '%s\n' "$n"; return 0; fi
  done
  return 1
}

config_validate() {
  local files=(system/config.md) f
  for f in "$VAULT_ROOT"/system/codebases/*.md; do [[ -f "$f" ]] && files+=("system/codebases/$(basename "$f")"); done
  _vi validate "${files[@]}"
}
```

- [ ] **Step 4: Run to verify pass**

Run: `bats system/tests/lib.bats`
Expected: `9 tests, 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/lib_config.sh system/tests/lib.bats
git commit -m "feat: add shell config and codebase helpers"
```

---

### Task 4: Permission files and integrity checks

**Files:**
- Create: `.claude/settings.json`, `system/headless.settings.json`
- Modify: `system/tests/vault_integrity.bats` (append tests)

**Interfaces:**
- Produces: the exact §7.1 and §7.2 files consumed by Task 7 (`--settings system/headless.settings.json`) and by interactive sessions.

- [ ] **Step 1: Write the failing integrity tests (append to `system/tests/vault_integrity.bats`)**

```bash
@test "settings files are valid JSON with the deny list and read fence" {
  for f in .claude/settings.json system/headless.settings.json; do
    jq empty "$f"
    [ "$(jq '.permissions.blockReadsOutsideWorkingDirectories' "$f")" = "true" ]
    for rule in 'Read(~/.ssh/**)' 'Read(~/.gnupg/**)' 'Read(~/.claude/.credentials.json)' 'Read(~/.claude.json)' 'Read(~/.claude/settings*.json)' 'Read(~/.config/gcalcli/**)' 'Read(//**/.env)' 'Read(//**/.env.*)'; do
      jq -e --arg r "$rule" '.permissions.deny | index($r)' "$f" >/dev/null
    done
  done
}

@test "headless settings have no allows, no /-anchored rules, and a strict sandbox" {
  f=system/headless.settings.json
  [ "$(jq '.permissions.allow // [] | length' "$f")" = "0" ]
  [ "$(jq '[.permissions.deny[] | select(test("^[A-Za-z]+\\(/[^/]"))] | length' "$f")" = "0" ]
  [ "$(jq '.sandbox.enabled' "$f")" = "true" ]
  [ "$(jq '.sandbox.autoAllowBashIfSandboxed' "$f")" = "false" ]
}

@test "interactive settings allow only staging-free vault edits and read-only index commands" {
  f=.claude/settings.json
  jq -e '.permissions.allow | index("Edit(/wiki/**)")' "$f" >/dev/null
  jq -e '.permissions.allow | index("Edit(/briefings/**)")' "$f" >/dev/null
  [ "$(jq '[.permissions.allow[] | select(test("vault_index.py set"))] | length' "$f")" = "0" ]
  [ "$(jq '.hooks // {} | length' "$f")" = "0" ]
}
```

- [ ] **Step 2: Run to verify failure**

Run: `bats system/tests/vault_integrity.bats`
Expected: the 3 new tests FAIL (`jq: error: Could not open file`).

- [ ] **Step 3: Create the files**

`.claude/settings.json`:
```json
{
  "permissions": {
    "blockReadsOutsideWorkingDirectories": true,
    "allow": [
      "Edit(/wiki/**)", "Edit(/briefings/**)",
      "Bash(system/scripts/brief_prep.sh:*)",
      "Bash(system/scripts/debrief_prep.sh:*)",
      "Bash(system/scripts/lint_vault.sh:*)",
      "Bash(system/scripts/vault_index.py query:*)",
      "Bash(system/scripts/vault_index.py related:*)",
      "Bash(system/scripts/vault_index.py show:*)",
      "Bash(system/scripts/vault_index.py backlinks:*)",
      "Bash(system/scripts/vault_index.py orphans:*)",
      "Bash(system/scripts/vault_index.py issues:*)",
      "Bash(system/scripts/vault_index.py validate:*)",
      "Bash(system/scripts/vault_index.py field:*)",
      "Bash(system/scripts/vault_index.py rebuild:*)",
      "Bash(system/scripts/vault_index.py recall:*)"
    ],
    "deny": [
      "Read(~/.ssh/**)", "Read(~/.gnupg/**)",
      "Read(~/.claude/.credentials.json)", "Read(~/.claude.json)", "Read(~/.claude/settings*.json)",
      "Read(~/.config/gcalcli/**)", "Read(//**/.env)", "Read(//**/.env.*)"
    ]
  }
}
```

`system/headless.settings.json`:
```json
{
  "permissions": {
    "blockReadsOutsideWorkingDirectories": true,
    "deny": [
      "Read(~/.ssh/**)", "Read(~/.gnupg/**)",
      "Read(~/.claude/.credentials.json)", "Read(~/.claude.json)", "Read(~/.claude/settings*.json)",
      "Read(~/.config/gcalcli/**)", "Read(//**/.env)", "Read(//**/.env.*)"
    ]
  },
  "sandbox": {"enabled": true, "autoAllowBashIfSandboxed": false}
}
```

- [ ] **Step 4: Run to verify pass**

Run: `bats system/tests/vault_integrity.bats`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add .claude/settings.json system/headless.settings.json system/tests/vault_integrity.bats
git commit -m "feat: add interactive and headless permission files"
```

---

### Task 5: Redaction (`redact.py`)

**Files:**
- Create: `system/scripts/vaultlib/redact.py`, `system/scripts/redact.py`
- Test: `system/tests/python/test_redact.py`

**Interfaces:**
- Produces: `redact.redact(text: str) -> tuple[str, int]` (redacted text, number of redactions); CLI `system/scripts/redact.py` reads stdin, writes the redacted text to stdout and the count to stderr as `redactions: N`.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_redact.py`:
```python
import subprocess
import sys

import pytest

from helpers import REPO
from vaultlib.redact import redact


@pytest.mark.parametrize("secret, kind", [
    ("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\ndef\n-----END OPENSSH PRIVATE KEY-----", "pem"),
    ("AKIAIOSFODNN7EXAMPLE", "aws_key"),
    ("ghp_" + "a1B2c3D4" * 5, "github_token"),
    ("github_pat_" + "A1b2" * 15, "github_token"),
    ("glpat-" + "x1Y2z3" * 4, "gitlab_token"),
    ("xoxb-1234567890-abcdefghij", "slack_token"),
    ("sk-ant-api03-" + "Ab1" * 10, "anthropic_key"),
    ("sk-proj-" + "Ab1" * 10, "openai_key"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", "jwt"),
])
def test_known_patterns(secret, kind):
    text, count = redact(f"before {secret} after")
    assert secret not in text and f"[REDACTED:{kind}]" in text and count == 1
    assert text.startswith("before ") and text.endswith(" after")


def test_bearer_keeps_prefix():
    text, count = redact("Authorization: Bearer abc.def.ghi")
    assert text == "Authorization: Bearer [REDACTED:bearer]" and count == 1


def test_assignment_keeps_key():
    text, count = redact("password = hunter2 and api_key: XYZ123")
    assert text == "password = [REDACTED:assignment] and api_key: [REDACTED:assignment]" and count == 2


def test_high_entropy_string():
    blob = "Zq8xT2mN7vB4kL9pR3wY6cH1jF5dS0aE"
    text, count = redact(f"token {blob}")
    assert "[REDACTED:high_entropy]" in text and count == 1


@pytest.mark.parametrize("safe", [
    "a" * 40, "0123456789abcdef" * 4, "9fceb02d0ae598e95dc970b74767f19372d61af8",
    "550e8400-e29b-41d4-a716-446655440000", "The quick brown fox jumps over the lazy dog",
    "deadbeef", "d41d8cd98f00b204e9800998ecf8427e",
])
def test_safe_text_untouched(safe):
    assert redact(safe) == (safe, 0)


def test_private_spans():
    text, count = redact("keep <private>my\nsecret</private> keep <PRIVATE>x</Private>")
    assert text == "keep [PRIVATE] keep [PRIVATE]" and count == 2


def test_cli_round_trip():
    res = subprocess.run([sys.executable, str(REPO / "system/scripts/redact.py")],
                         input="password=abc\n", capture_output=True, text=True)
    assert res.returncode == 0
    assert res.stdout == "password=[REDACTED:assignment]\n" and res.stderr.strip() == "redactions: 1"
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_redact.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'vaultlib.redact'`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/redact.py`:
```python
"""Secret redaction for digests and inbox copies (spec §6.18)."""
import math
import re
from collections import Counter

PRIVATE = re.compile(r"<private>.*?</private>", re.IGNORECASE | re.DOTALL)
PATTERNS = [
    ("pem", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL)),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]
BEARER = re.compile(r"(?i)(authorization:\s*bearer\s+)\S+")
ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)(\s*[:=]\s*)(?!\[REDACTED)(\S+)")
CANDIDATE = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
HEX = re.compile(r"[0-9a-fA-F]+")
ENTROPY_BITS = 4.0


def _entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def _high_entropy(match: re.Match) -> str:
    s = match.group(0)
    if "REDACTED" in s or (HEX.fullmatch(s) and len(s) in (40, 64)) or _entropy(s) < ENTROPY_BITS:
        return s
    return "[REDACTED:high_entropy]"


def redact(text: str) -> tuple:
    """Return (redacted_text, redaction_count)."""
    count = 0

    def sub(pattern, replacement, value):
        nonlocal count
        new, n = pattern.subn(replacement, value)
        count += n
        return new

    text = sub(PRIVATE, "[PRIVATE]", text)
    for kind, pattern in PATTERNS:
        text = sub(pattern, f"[REDACTED:{kind}]", text)
    text = sub(BEARER, r"\1[REDACTED:bearer]", text)
    text = sub(ASSIGNMENT, r"\1\2[REDACTED:assignment]", text)
    before = text
    text = CANDIDATE.sub(_high_entropy, text)
    count += text.count("[REDACTED:high_entropy]") - before.count("[REDACTED:high_entropy]")
    return text, count
```

`system/scripts/redact.py`:
```python
#!/usr/bin/env python3
"""Redact secrets from stdin to stdout; print the count to stderr (spec §6.18)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.redact import redact  # noqa: E402

text, count = redact(sys.stdin.read())
sys.stdout.write(text)
print(f"redactions: {count}", file=sys.stderr)
```
Run: `chmod +x system/scripts/redact.py`

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_redact.py -q`
Expected: all tests pass. If a `test_safe_text_untouched` case fails on entropy, report the measured entropy in the report rather than changing the threshold silently.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/redact.py system/scripts/redact.py system/tests/python/test_redact.py
git commit -m "feat: add secret redaction for digests and inbox copies"
```

---

### Task 6: Ultra Magnus — snapshot, stage, decisions, validation, commit, recovery

**Files:**
- Create: `system/scripts/vaultlib/publish.py`, `system/scripts/vaultlib/publish_cli.py`, `system/scripts/publish_staged.py`
- Modify: `system/scripts/vaultlib/cli.py` (add `stage`)
- Test: `system/tests/python/test_publish.py`, `system/tests/python/test_publish_commit.py`, `system/tests/python/test_stage_cli.py`

**Interfaces:**
- Consumes: `frontmatter.parse`, `schema.load_schemas/validate_note/path_partition/Context`, `links.extract/Resolver/code_free_lines`, `index.Index` (`walk`, `refresh`, `_frontmatter_links`), `index.wall_blocked`, `index.NAME_EXCLUDED`.
- Produces:
  - `publish.PublishError(Exception)`; `publish.Problem(path: str, reason: str)`
  - `publish.check_run_id(run_id) -> str` (returns the command; raises PublishError)
  - `publish.snapshot(vault, run_id, targets: list[str]) -> Path`
  - `publish.record_stage(vault, run_id, target) -> Path` (staged copy path)
  - `publish.validate_run(vault, run_id, now=None) -> tuple[list[str], list[dict], list[Problem]]`
  - `publish.commit_run(vault, run_id, now=None) -> dict` (report with `status` in `published|noop|empty|rejected|conflict`, `published`, `conflicts`, `problems`)
  - `publish.abort_run(vault, run_id) -> dict`; `publish.recover(vault) -> dict` (`recovered`, `aborted` run ids)
  - CLI `system/scripts/publish_staged.py snapshot <run_id> --targets T… | commit <run_id> | abort <run_id> | recover` printing the report JSON; exit 0 for `published`/`noop`/recover/snapshot/abort, 5 for `empty`/`rejected`/`conflict`, 2 for PublishError, 1 for SchemaError
  - `vault_index.py stage <target> <run_id>` (vault scope only) printing the staged path
  - Files: `system/logs/runs/<run_id>/{snapshot.json,publish.json,publish.journal,_decisions.jsonl}`, `wiki/.staging/<run_id>/<target>`, `system/quarantine/<run_id>/staged/`

- [ ] **Step 1: Write the failing validation tests**

`system/tests/python/test_publish.py`:
```python
import json
import os
import time

import pytest

from helpers import concept, write
from vaultlib import publish

RID = "20261001T120000-ingest-ab12"
LATER = time.time() + 3600


def stage_new(vault, rel, text, run_id=RID):
    return write(vault, f"wiki/.staging/{run_id}/{rel}", text)


def decide(vault, *records, run_id=RID):
    lines = [json.dumps(r) for r in records]
    write(vault, f"wiki/.staging/{run_id}/_decisions.jsonl", "\n".join(lines) + "\n")


def rec(target, decision="create"):
    return {"item": "i", "decision": decision, "target": target, "source": "s", "reason": "r"}


@pytest.fixture
def run(vault):
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    return vault


def reasons(problems):
    return [p.reason for p in problems]


def test_check_run_id():
    assert publish.check_run_id(RID) == "ingest"
    for bad in ("x", "20261001T120000-rm-ab12", "../20261001T120000-ingest-ab12"):
        with pytest.raises(publish.PublishError):
            publish.check_run_id(bad)


def test_snapshot_records_existing_targets(run):
    snap = json.loads((run / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert "wiki/work/concepts/Kafka.md" in snap["files"] and "wiki/shared/concepts/Git.md" in snap["files"]
    assert "wiki/personal/concepts/Gardening.md" not in snap["files"]
    assert (run / "wiki/.staging" / RID).is_dir()
    with pytest.raises(publish.PublishError):
        publish.snapshot(run, RID, ["wiki/work/**"])


def test_valid_new_note(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New", "[[Kafka]] [[Index]]"))
    decide(run, rec("wiki/work/concepts/New.md"))
    staged, decisions, problems = publish.validate_run(run, RID, now=LATER)
    assert staged == ["wiki/work/concepts/New.md"] and problems == []


def test_target_outside_targets_rejected(run):
    stage_new(run, "wiki/personal/concepts/P.md", concept("personal", "P"))
    decide(run, rec("wiki/personal/concepts/P.md"))
    assert "not a publishable target" in reasons(publish.validate_run(run, RID, now=LATER)[2])


def test_schema_error_rejected(run):
    stage_new(run, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad\n")
    decide(run, rec("wiki/work/concepts/Bad.md"))
    assert any(r.startswith("schema:") for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_partition_wall_rejected(run):
    stage_new(run, "wiki/work/concepts/W.md", concept("work", "W", "[[Gardening]]"))
    decide(run, rec("wiki/work/concepts/W.md"))
    assert any("partition wall" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_existing_target_must_be_staged_via_stage(run):
    stage_new(run, "wiki/work/concepts/Kafka.md", concept("work", "Kafka", "rewritten wholesale"))
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert any("not staged with vault_index.py stage" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_stage_then_patch_ok(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text(dst.read_text().replace("event streaming", "event streaming at scale"))
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert publish.validate_run(run, RID, now=LATER)[2] == []


def test_shrink_guard(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text("---\ntype: concept\ntags: []\ncompiled_at: \"2026-09-01\"\npartition: work\n---\nx\n")
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    rs = reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert any("headings removed" in r for r in rs) and any("below 60%" in r for r in rs)
    decide(run, rec("wiki/work/concepts/Kafka.md", "deprecate"))
    assert not any(r.startswith("shrink guard") for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_protected_fields(run):
    stage_new(run, "wiki/work/preferences/P.md",
              '---\ntype: preference\nstatement: "x"\npartition: work\naccepted_at: "2026-10-01"\n---\n# P\n')
    decide(run, rec("wiki/work/preferences/P.md"))
    assert any("protected field accepted_at" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_conflicts(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New"))
    decide(run, rec("wiki/work/concepts/New.md"))
    write(run, "wiki/work/concepts/New.md", concept("work", "New", "user created it meanwhile"))
    assert any("created during the run" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_recent_edit_is_conflict(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    dst.write_text(dst.read_text() + "\nmore\n")
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert any("last 60 s" in r for r in reasons(publish.validate_run(run, RID, now=time.time())[2]))


def test_decisions_required_and_validated(run):
    stage_new(run, "wiki/work/concepts/New.md", concept("work", "New"))
    assert any("_decisions.jsonl" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))
    write(run, f"wiki/.staging/{RID}/_decisions.jsonl", "not json\n{\"item\": 1}\n")
    rs = reasons(publish.validate_run(run, RID, now=LATER)[2])
    assert any("invalid JSON" in r for r in rs) and any("invalid decision record" in r for r in rs)


def test_noop_must_cite_existing_note(run):
    decide(run, rec("wiki/work/concepts/Ghost.md", "noop"))
    assert any("noop must cite an existing note" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_staged_symlink_rejected(run, tmp_path):
    outside = tmp_path / "evil.md"
    outside.write_text("x")
    link = run / "wiki/.staging" / RID / "wiki/work/concepts/Evil.md"
    link.parent.mkdir(parents=True)
    os.symlink(outside, link)
    decide(run, rec("wiki/work/concepts/Evil.md"))
    assert any("symlink" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_unsafe_staged_path_rejected(run):
    decide(run, rec("../../etc/passwd"))
    assert any("unsafe path" in r for r in reasons(publish.validate_run(run, RID, now=LATER)[2]))


def test_record_stage_refuses_non_targets_and_unknown_runs(run):
    with pytest.raises(publish.PublishError):
        publish.record_stage(run, RID, "wiki/personal/concepts/Gardening.md")
    with pytest.raises(publish.PublishError):
        publish.record_stage(run, "20261001T120000-ingest-ffff", "wiki/work/concepts/Kafka.md")
    with pytest.raises(publish.PublishError):
        publish.record_stage(run, RID, "../outside.md")
```

- [ ] **Step 2: Write the failing commit and recovery tests**

`system/tests/python/test_publish_commit.py`:
```python
import json
import time

import pytest

from helpers import concept, write
from vaultlib import frontmatter, publish

RID = "20261001T120000-ingest-ab12"
LATER = time.time() + 3600


def decide(vault, *records, run_id=RID):
    write(vault, f"wiki/.staging/{run_id}/_decisions.jsonl", "\n".join(json.dumps(r) for r in records) + "\n")


def rec(target, decision="create"):
    return {"item": "i", "decision": decision, "target": target, "source": "s", "reason": "r"}


@pytest.fixture
def run(vault):
    publish.snapshot(vault, RID, ["wiki/work/**", "wiki/shared/**"])
    return vault


def test_publish_new_note_with_provenance(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/New.md", concept("work", "New", "[[Index]]"))
    decide(run, rec("wiki/work/concepts/New.md"))
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "published" and report["published"] == ["wiki/work/concepts/New.md"]
    data = frontmatter.parse((run / "wiki/work/concepts/New.md").read_text()).data
    assert data["provenance"] == ["headless"]
    assert not (run / "wiki/.staging" / RID).exists()
    assert (run / "system/logs/runs" / RID / "_decisions.jsonl").is_file()
    journal = (run / "system/logs/runs" / RID / "publish.journal").read_text().splitlines()
    assert json.loads(journal[-1]) == {"committed": True}


def test_provenance_appended_not_replaced(run):
    dst = publish.record_stage(run, RID, "wiki/work/concepts/Kafka.md")
    text = dst.read_text().replace("partition: work", 'partition: work\nprovenance: ["interactive"]')
    dst.write_text(text + "\nmore\n")
    decide(run, rec("wiki/work/concepts/Kafka.md", "patch"))
    assert publish.commit_run(run, RID, now=LATER)["status"] == "published"
    data = frontmatter.parse((run / "wiki/work/concepts/Kafka.md").read_text()).data
    assert data["provenance"] == ["interactive", "headless"]


def test_rejected_run_publishes_nothing_and_quarantines(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/Good.md", concept("work", "Good"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad\n")
    decide(run, rec("wiki/work/concepts/Good.md"), rec("wiki/work/concepts/Bad.md"))
    report = publish.commit_run(run, RID, now=LATER)
    assert report["status"] == "rejected" and report["problems"]
    assert not (run / "wiki/work/concepts/Good.md").exists()
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/Good.md").is_file()


def test_noop_and_empty(run):
    decide(run, rec("wiki/work/concepts/Kafka.md", "noop"))
    assert publish.commit_run(run, RID, now=LATER)["status"] == "noop"
    rid2 = "20261001T120000-brief-ab12"
    publish.snapshot(run, rid2, ["briefings/2026-10-01.md"])
    assert publish.commit_run(run, rid2, now=LATER)["status"] == "empty"


def test_target_changed_between_validation_and_rename_is_held_back(run, monkeypatch):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real = publish._rename

    def racing_rename(src, dst):
        if dst.endswith("A.md"):
            write(run, "wiki/work/concepts/B.md", concept("work", "B", "user wrote this"))
        real(src, dst)

    monkeypatch.setattr(publish, "_rename", racing_rename)
    report = publish.commit_run(run, RID, now=LATER)
    assert report["published"] == ["wiki/work/concepts/A.md"] and report["conflicts"] == ["wiki/work/concepts/B.md"]
    assert "user wrote this" in (run / "wiki/work/concepts/B.md").read_text()


@pytest.mark.parametrize("crash_after", [0, 1])
def test_crash_mid_publish_rolls_forward(run, monkeypatch, crash_after):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/B.md", concept("work", "B"))
    decide(run, rec("wiki/work/concepts/A.md"), rec("wiki/work/concepts/B.md"))
    real, calls = publish._rename, []

    def crashing(src, dst):
        if len(calls) == crash_after:
            raise KeyboardInterrupt("simulated crash")
        calls.append(dst)
        real(src, dst)

    monkeypatch.setattr(publish, "_rename", crashing)
    with pytest.raises(KeyboardInterrupt):
        publish.commit_run(run, RID, now=LATER)
    monkeypatch.setattr(publish, "_rename", real)
    result = publish.recover(run)
    assert result["recovered"] == [RID]
    assert (run / "wiki/work/concepts/A.md").is_file() and (run / "wiki/work/concepts/B.md").is_file()
    assert json.loads((run / "system/logs/runs" / RID / "publish.journal").read_text().splitlines()[-1]) == {"committed": True}


def test_recover_quarantines_aborted_staging(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    result = publish.recover(run)
    assert result["aborted"] == [RID]
    assert (run / "system/quarantine" / RID / "staged/wiki/work/concepts/A.md").is_file()
    assert json.loads((run / "system/logs/runs" / RID / "publish.json").read_text())["status"] == "aborted"


def test_abort_run(run):
    write(run, f"wiki/.staging/{RID}/wiki/work/concepts/A.md", concept("work", "A"))
    assert publish.abort_run(run, RID)["status"] == "aborted"
    assert not (run / "wiki/.staging" / RID).exists()
```

`system/tests/python/test_stage_cli.py`:
```python
import json
import subprocess
import sys

from vaultlib import publish

RID = "20261001T120000-ingest-ab12"


def test_stage_subcommand(cli, vault):
    publish.snapshot(vault, RID, ["wiki/work/**"])
    res = cli("stage", "wiki/work/concepts/Kafka.md", RID)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"wiki/.staging/{RID}/wiki/work/concepts/Kafka.md"
    snap = json.loads((vault / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert "wiki/work/concepts/Kafka.md" in snap["staged"]


def test_stage_refuses_bad_input(cli, vault):
    publish.snapshot(vault, RID, ["wiki/work/**"])
    assert cli("stage", "wiki/personal/concepts/Gardening.md", RID).returncode == 2
    assert cli("stage", "wiki/work/concepts/Kafka.md", "not-a-run").returncode == 2


def test_publish_cli_exit_codes(vault):
    import shutil
    from helpers import REPO
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    script = vault / "system/scripts/publish_staged.py"
    snap = subprocess.run([sys.executable, str(script), "snapshot", RID, "--targets", "wiki/work/**"],
                          cwd=vault, capture_output=True, text=True)
    assert snap.returncode == 0, snap.stderr
    empty = subprocess.run([sys.executable, str(script), "commit", RID], cwd=vault, capture_output=True, text=True)
    assert empty.returncode == 5 and json.loads(empty.stdout)["status"] == "rejected"
    bad = subprocess.run([sys.executable, str(script), "commit", "nope"], cwd=vault, capture_output=True, text=True)
    assert bad.returncode == 2
```
(The ingest commit above is `rejected` because an ingest run with no `_decisions.jsonl` fails validation.)

- [ ] **Step 3: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_publish.py system/tests/python/test_publish_commit.py system/tests/python/test_stage_cli.py -q`
Expected: FAIL with `ImportError: cannot import name 'publish'`.

- [ ] **Step 4: Implement `publish.py`**

`system/scripts/vaultlib/publish.py`:
```python
"""Ultra Magnus: staged, validated, journaled publish of headless output (spec §6.20)."""
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import frontmatter, links as linkmod, schema as schemamod
from .index import NAME_EXCLUDED, Index, wall_blocked

RUN_ID = re.compile(r"^\d{8}T\d{6}-(ingest|brief|debrief)-[0-9a-f]{4}$")
DECISION_KINDS = {"noop", "patch", "create", "deprecate", "supersede"}
SHRINK_EXEMPT = {"deprecate", "supersede"}
PROTECTED = ("accepted_at", "rejected_at")
MIN_BODY_RATIO = 0.6
RECENT_SECONDS = 60
DECISIONS = "_decisions.jsonl"
HEADING = re.compile(r"^#{1,6}\s+\S")
_rename = os.replace  # indirection so tests can inject crashes and races


class PublishError(Exception):
    pass


@dataclass
class Problem:
    path: str
    reason: str


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_run_id(run_id: str) -> str:
    match = RUN_ID.match(run_id or "")
    if not match:
        raise PublishError(f"invalid run id: {run_id!r}")
    return match.group(1)


def run_dir(vault, run_id) -> Path:
    return Path(vault) / "system" / "logs" / "runs" / run_id


def staging_dir(vault, run_id) -> Path:
    return Path(vault) / "wiki" / ".staging" / run_id


def safe_rel(rel) -> str:
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel:
        raise PublishError(f"unsafe path: {rel!r}")
    parts = Path(rel).parts
    if ".." in parts or any(p.startswith(".") for p in parts):
        raise PublishError(f"unsafe path: {rel!r}")
    return Path(rel).as_posix()


def target_matches(target: str, targets) -> bool:
    for t in targets:
        if t.endswith("/**"):
            if target.startswith(t[:-2]):
                return True
        elif target == t:
            return True
    return False


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _target_files(vault: Path, targets):
    for t in targets:
        if t.endswith("/**"):
            base = vault / t[:-3]
            if not base.is_dir():
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in files:
                    path = Path(root) / name
                    if path.is_file() and not path.is_symlink():
                        yield path.relative_to(vault).as_posix()
        else:
            path = vault / t
            if path.is_file() and not path.is_symlink():
                yield t


def snapshot(vault, run_id, targets) -> Path:
    vault = Path(vault)
    check_run_id(run_id)
    for t in targets:
        safe_rel(t[:-3] if t.endswith("/**") else t)
    rd = run_dir(vault, run_id)
    if rd.exists() or staging_dir(vault, run_id).exists():
        raise PublishError(f"run already exists: {run_id}")
    files = {rel: sha256_file(vault / rel) for rel in _target_files(vault, targets)}
    _write_json(rd / "snapshot.json", {"targets": list(targets), "files": files, "staged": {}})
    staging_dir(vault, run_id).mkdir(parents=True)
    return rd / "snapshot.json"


def load_snapshot(vault, run_id) -> dict:
    check_run_id(run_id)
    path = run_dir(vault, run_id) / "snapshot.json"
    if not path.is_file():
        raise PublishError(f"unknown run: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def record_stage(vault, run_id, target) -> Path:
    vault = Path(vault)
    target = safe_rel(target)
    snap = load_snapshot(vault, run_id)
    if not staging_dir(vault, run_id).is_dir():
        raise PublishError(f"run is not open: {run_id}")
    if not target_matches(target, snap["targets"]):
        raise PublishError(f"not a publishable target for this run: {target}")
    src = vault / target
    if src.is_symlink() or not src.is_file():
        raise PublishError(f"no such note to stage: {target}")
    dst = staging_dir(vault, run_id) / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    snap["staged"][target] = sha256_file(dst)
    _write_json(run_dir(vault, run_id) / "snapshot.json", snap)
    return dst


def staged_targets(vault, run_id):
    sd = staging_dir(vault, run_id)
    staged, problems = [], []
    if not sd.is_dir():
        return staged, problems
    for path in sorted(sd.rglob("*")):
        rel = path.relative_to(sd).as_posix()
        if path.is_symlink():
            problems.append(Problem(rel, "staged path is a symlink"))
        elif path.is_file() and rel != DECISIONS:
            staged.append(rel)
    return staged, problems


def read_decisions(vault, run_id):
    path = staging_dir(vault, run_id) / DECISIONS
    if not path.is_file() or path.is_symlink():
        return None, []
    decisions, problems = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(Problem(DECISIONS, f"line {n}: invalid JSON: {exc.msg}"))
            continue
        if (not isinstance(record, dict) or record.get("decision") not in DECISION_KINDS
                or any(not isinstance(record.get(k), str) for k in ("item", "source", "reason"))
                or not (record.get("target") is None or isinstance(record.get("target"), str))):
            problems.append(Problem(DECISIONS, f"line {n}: invalid decision record"))
            continue
        target = record.get("target")
        try:
            if target is not None:
                safe_rel(target)
        except PublishError as exc:
            problems.append(Problem(DECISIONS, f"line {n}: {exc}"))
            continue
        if record["decision"] == "noop":
            if not target or not (Path(vault) / target).is_file():
                problems.append(Problem(DECISIONS, f"line {n}: noop must cite an existing note"))
                continue
        elif not target:
            problems.append(Problem(DECISIONS, f"line {n}: {record['decision']} needs a target"))
            continue
        decisions.append(record)
    return decisions, problems


def _headings(body: str) -> set:
    return {text.strip() for _, text in linkmod.code_free_lines(body, 1) if HEADING.match(text)}


def _protected(old, new, target) -> list:
    out, od, nd = [], old.data or {}, new.data or {}
    for key in PROTECTED:
        if od.get(key) != nd.get(key):
            out.append(Problem(target, f"protected field {key} changed"))
    oldp = od.get("provenance") if isinstance(od.get("provenance"), list) else []
    newp = nd.get("provenance") if isinstance(nd.get("provenance"), list) else []
    if any(p not in newp for p in oldp):
        out.append(Problem(target, "provenance entries removed"))
    return out


def _shrink(old, new, target) -> list:
    out = []
    missing = set(map(str, (old.data or {}).keys())) - set(map(str, (new.data or {}).keys()))
    if missing:
        out.append(Problem(target, f"shrink guard: frontmatter keys removed: {', '.join(sorted(missing))}"))
    lost = _headings(old.body) - _headings(new.body)
    if lost:
        out.append(Problem(target, f"shrink guard: headings removed: {', '.join(sorted(lost))}"))
    old_len, new_len = len(old.body.strip()), len(new.body.strip())
    if old_len and new_len < MIN_BODY_RATIO * old_len:
        out.append(Problem(target, "shrink guard: body shrank below 60% of the original"))
    return out


def _expected(snap, target):
    return snap["staged"].get(target, snap["files"].get(target))


def _conflict(vault: Path, target, snap, now) -> list:
    path, expected = vault / target, _expected(snap, target)
    if expected is None:
        return [Problem(target, "conflict: target was created during the run")] if path.exists() else []
    if not path.is_file():
        return [Problem(target, "conflict: target was removed during the run")]
    if sha256_file(path) != expected:
        return [Problem(target, "conflict: target changed during the run")]
    if now - path.stat().st_mtime < RECENT_SECONDS:
        return [Problem(target, "conflict: target modified in the last 60 s")]
    return []


def _walls(vault, target, note, schemas, resolver) -> list:
    if not target.startswith("wiki/") or (note.data or {}).get("type") == "index":
        return []
    src_part = schemamod.path_partition(target)
    body_links, _ = linkmod.extract(note.body, note.body_line)
    fm_links = Index(vault)._frontmatter_links(schemas.get((note.data or {}).get("type")), note)
    out = []
    for link in body_links + fm_links:
        hit, _ = resolver.resolve(link.target, target, "md" if link.kind == "md" else "wiki", lambda c: (len(c), c))
        part = schemamod.path_partition(hit) if hit else None
        if src_part and part and wall_blocked(src_part, part):
            out.append(Problem(target, f"partition wall: {src_part} note links to {hit}"))
    return out


def _check(vault: Path, run_id, target, snap, decided, command, schemas, ctx, resolver, now) -> list:
    try:
        safe_rel(target)
    except PublishError as exc:
        return [Problem(target, str(exc))]
    if not target_matches(target, snap["targets"]):
        return [Problem(target, "not a publishable target")]
    try:
        new_text = (staging_dir(vault, run_id) / target).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Problem(target, f"unreadable staged file: {exc}")]
    new = frontmatter.parse(new_text)
    out = [Problem(target, f"schema: {i.message}") for i in schemamod.validate_note(schemas, target, new, ctx)[1]
           if i.severity == "error"]
    out += _walls(vault, target, new, schemas, resolver)
    decision = decided.get(target)
    if command == "ingest" and decision is None:
        out.append(Problem(target, "no decision recorded for this file"))
    existed = target in snap["files"]
    if existed and target not in snap["staged"]:
        out.append(Problem(target, "existing note was not staged with vault_index.py stage"))
    target_path = vault / target
    if existed and target_path.is_file():
        try:
            old = frontmatter.parse(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            old = None
        if old is not None:
            out += _protected(old, new, target)
            if decision not in SHRINK_EXEMPT:
                out += _shrink(old, new, target)
    else:
        for key in PROTECTED:
            if key in (new.data or {}):
                out.append(Problem(target, f"protected field {key} cannot be set by a headless run"))
    out += _conflict(vault, target, snap, now)
    return out


def validate_run(vault, run_id, now=None):
    vault, now = Path(vault), time.time() if now is None else now
    command = check_run_id(run_id)
    snap = load_snapshot(vault, run_id)
    staged, problems = staged_targets(vault, run_id)
    decisions, decision_problems = read_decisions(vault, run_id)
    problems += decision_problems
    if command == "ingest" and decisions is None:
        problems.append(Problem(DECISIONS, "ingest runs must write _decisions.jsonl"))
    for record in decisions or []:
        target = record.get("target")
        if record["decision"] != "noop" and target and target not in staged:
            if not target_matches(target, snap["targets"]):
                problems.append(Problem(target, "not a publishable target"))
    decided = {r["target"]: r["decision"] for r in decisions or [] if r["decision"] != "noop" and r.get("target")}
    schemas, ctx = schemamod.load_schemas(vault), schemamod.Context(vault)
    files = {rel for rel, _, _ in Index(vault).walk()} | set(staged)
    resolver = linkmod.Resolver(files, name_exclude=NAME_EXCLUDED)
    for target in staged:
        problems += _check(vault, run_id, target, snap, decided, command, schemas, ctx, resolver, now)
    return staged, decisions or [], problems


def _set_provenance(text: str, values) -> str:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    new_line = "provenance: " + json.dumps(values, ensure_ascii=False)
    if not lines or lines[0] != "---":
        return f"---\n{new_line}\n---\n{text}"
    end = next((i for i in range(1, len(lines)) if lines[i] in ("---", "...")), None)
    if end is None:
        return text
    for i in range(1, end):
        if lines[i].startswith("provenance:"):
            j = i + 1
            while j < end and lines[j][:1] in (" ", "\t", "-"):
                j += 1
            lines[i:j] = [new_line]
            break
    else:
        lines.insert(end, new_line)
    return "\n".join(lines)


def _report(vault, run_id, status, problems=(), published=(), conflicts=()) -> dict:
    report = {"run_id": run_id, "status": status, "published": list(published), "conflicts": list(conflicts),
              "problems": [asdict(p) for p in problems]}
    _write_json(run_dir(vault, run_id) / "publish.json", report)
    return report


def _quarantine(vault: Path, run_id) -> None:
    src = staging_dir(vault, run_id)
    if not src.exists():
        return
    dst = vault / "system" / "quarantine" / run_id / "staged"
    if dst.exists():
        dst = dst.with_name(f"staged-{int(time.time())}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _committed(journal: Path) -> bool:
    lines = [ln for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return bool(lines) and json.loads(lines[-1]) == {"committed": True}


def _apply(vault: Path, journal: Path):
    published, conflicts = [], []
    entries = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for entry in entries:
        if "target" not in entry:
            continue
        staged, target = vault / entry["staged"], vault / entry["target"]
        if not staged.exists():
            published.append(entry["target"])  # renamed before a crash
            continue
        current = sha256_file(target) if target.is_file() else None
        if current != entry["expected"]:
            conflicts.append(entry["target"])
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _rename(str(staged), str(target))
        published.append(entry["target"])
    with open(journal, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"committed": True}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return published, conflicts


def _refresh_index(vault) -> None:
    try:
        Index(vault).refresh(timeout=60)
    except TimeoutError:
        pass  # the next index read refreshes


def commit_run(vault, run_id, now=None) -> dict:
    vault = Path(vault)
    command = check_run_id(run_id)
    rd, sd = run_dir(vault, run_id), staging_dir(vault, run_id)
    staged, decisions, problems = validate_run(vault, run_id, now)
    decisions_file = sd / DECISIONS
    if decisions_file.is_file() and not decisions_file.is_symlink():
        shutil.copyfile(decisions_file, rd / DECISIONS)
    if problems:
        _quarantine(vault, run_id)
        return _report(vault, run_id, "rejected", problems=problems)
    if not staged:
        noop = command == "ingest" and decisions and all(d["decision"] == "noop" for d in decisions)
        shutil.rmtree(sd, ignore_errors=True)
        return _report(vault, run_id, "noop" if noop else "empty")
    snap = load_snapshot(vault, run_id)
    entries = []
    for target in staged:
        path = sd / target
        text = path.read_text(encoding="utf-8")
        data = frontmatter.parse(text).data or {}
        prov = [v for v in data.get("provenance", []) if isinstance(v, str)] \
            if isinstance(data.get("provenance"), list) else []
        if "headless" not in prov:
            prov.append("headless")
        path.write_text(_set_provenance(text, prov), encoding="utf-8")
        entries.append({"staged": path.relative_to(vault).as_posix(), "target": target,
                        "expected": _expected(snap, target)})
    journal = rd / "publish.journal"
    with open(journal, "w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    published, conflicts = _apply(vault, journal)
    shutil.rmtree(sd, ignore_errors=True)
    _refresh_index(vault)
    status = "published" if published else "conflict"
    return _report(vault, run_id, status, published=published, conflicts=conflicts)


def abort_run(vault, run_id) -> dict:
    vault = Path(vault)
    check_run_id(run_id)
    _quarantine(vault, run_id)
    return _report(vault, run_id, "aborted")


def recover(vault) -> dict:
    """Roll forward interrupted publishes; quarantine aborted staging trees. Caller holds run.lock."""
    vault = Path(vault)
    recovered, aborted = [], []
    runs = vault / "system" / "logs" / "runs"
    if runs.is_dir():
        for rd in sorted(runs.iterdir()):
            journal = rd / "publish.journal"
            if RUN_ID.match(rd.name) and journal.is_file() and not _committed(journal):
                published, conflicts = _apply(vault, journal)
                shutil.rmtree(staging_dir(vault, rd.name), ignore_errors=True)
                _report(vault, rd.name, "recovered", published=published, conflicts=conflicts)
                recovered.append(rd.name)
    root = vault / "wiki" / ".staging"
    if root.is_dir():
        for sd in sorted(root.iterdir()):
            if not sd.is_dir() or not RUN_ID.match(sd.name):
                continue
            if (run_dir(vault, sd.name) / "publish.journal").is_file():
                shutil.rmtree(sd, ignore_errors=True)
                continue
            _quarantine(vault, sd.name)
            _report(vault, sd.name, "aborted")
            aborted.append(sd.name)
    if recovered:
        _refresh_index(vault)
    return {"recovered": recovered, "aborted": aborted}
```

- [ ] **Step 5: Implement the publish CLI and `stage`**

`system/scripts/vaultlib/publish_cli.py`:
```python
"""CLI for publish_staged.py (spec §6.20)."""
import argparse
import json
import sys
from pathlib import Path

from . import publish, schema as schemamod

OK_STATUSES = {"published", "noop", "aborted"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="publish_staged.py", description="Ultra Magnus: publish headless output")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot")
    p.add_argument("run_id")
    p.add_argument("--targets", nargs="+", required=True)
    p = sub.add_parser("commit")
    p.add_argument("run_id")
    p = sub.add_parser("abort")
    p.add_argument("run_id")
    sub.add_parser("recover")
    args = parser.parse_args(argv)
    vault = Path(__file__).resolve().parents[3]
    try:
        if args.command == "snapshot":
            print(json.dumps({"snapshot": str(publish.snapshot(vault, args.run_id, args.targets).relative_to(vault))}))
            return 0
        if args.command == "recover":
            print(json.dumps(publish.recover(vault)))
            return 0
        report = (publish.commit_run if args.command == "commit" else publish.abort_run)(vault, args.run_id)
        print(json.dumps(report))
        return 0 if report["status"] in OK_STATUSES else 5
    except publish.PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except schemamod.SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return 1
```

`system/scripts/publish_staged.py`:
```python
#!/usr/bin/env python3
"""Ultra Magnus: validate and publish a headless run's staged output (spec §6.20)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.publish_cli import main  # noqa: E402

sys.exit(main())
```
Run: `chmod +x system/scripts/publish_staged.py`

In `system/scripts/vaultlib/cli.py`, add `publish` to the `from . import …` line, add this command next to `cmd_rebuild`:
```python
def cmd_stage(args, vault, sc):
    require_vault_scope(sc)
    try:
        dst = publish.record_stage(vault, args.run_id, args.target)
    except publish.PublishError as exc:
        raise UsageError(str(exc))
    print(rel(vault, dst))
    return EXIT_OK
```
and register it in `build_parser()` before `rebuild`:
```python
    p = add("stage", cmd_stage, "copy a publishable note into a run's staging tree (headless runs)")
    p.add_argument("target")
    p.add_argument("run_id")
```

- [ ] **Step 6: Run to verify pass**

Run: `python3 -m pytest system/tests/python -q`
Expected: all tests pass.

- [ ] **Step 7: Amend the spec to the built interface**

In `docs/superpowers/specs/2026-09-30-vault-template-design.md`:
- Change the §6.20 heading to `### 6.20 publish_staged.py snapshot <run_id> --targets <path…> | commit <run_id> | abort <run_id> | recover (Ultra Magnus: staged, conflict-safe publish)` and add after its first paragraph: "`run_headless.sh` calls `snapshot` before invoking claude (writing `system/logs/runs/<run_id>/snapshot.json` and creating the staging directory), `commit` after a successful run, `abort` after a failed or timed-out one (staging → quarantine), and `recover` at start under `run.lock`."
- In the **Decisions** bullet, after "Every staged file must be the `target` of a non-noop decision", insert "(ingest runs; `brief`/`debrief` publish their single exact target without a decisions file)".

- [ ] **Step 8: Commit**

```bash
git add system/scripts/vaultlib/publish.py system/scripts/vaultlib/publish_cli.py system/scripts/publish_staged.py system/scripts/vaultlib/cli.py system/tests/python/test_publish.py system/tests/python/test_publish_commit.py system/tests/python/test_stage_cli.py docs/superpowers/specs/2026-09-30-vault-template-design.md
git commit -m "feat(ultra-magnus): add staged, validated, journaled publish with recovery"
```

---

### Task 7: `run_headless.sh`

**Files:**
- Create: `system/scripts/run_headless.sh`, `system/tests/headless.bats`, `system/tests/stub_claude`

**Interfaces:**
- Consumes: `lib_args.sh`, `lib_config.sh`, `publish_staged.py snapshot|commit|abort|recover`, `vault_index.py field`, `.claude/commands/<cmd>.md`, `CLAUDE.md`, `system/headless.settings.json`.
- Produces: `system/scripts/run_headless.sh ingest <raw path>… | brief | debrief` with the exit codes in Global Constraints; ledger lines `{run_id, command, started_at, finished_at, inputs, input_sha256, partition, exit, publish{status, published, rejected, conflicts}, attempt, warnings{permission_denials}}`; honours `CLAUDE_BIN`, `HEADLESS_TIMEOUT`, `HEADLESS_MAX_RUNS_PER_DAY`, `HEADLESS_LOCK_WAIT`, and `JARVIS_ORIGINAL_SHA256` (space-separated originals aligned with inputs, set by the intake daemon).

- [ ] **Step 1: Write the stub claude**

`system/tests/stub_claude`:
```bash
#!/bin/bash
# Test double for claude -p. Behaviour via STUB_MODE; records argv to $STUB_ARGS and stdin target to $STUB_STDIN.
printf '%s\n' "$@" > "${STUB_ARGS:-/dev/null}"
readlink /proc/self/fd/0 > "${STUB_STDIN:-/dev/null}"
run_id="$(ls wiki/.staging | head -1)"
s="wiki/.staging/$run_id"
case "${STUB_MODE:-write}" in
  write)
    mkdir -p "$s/wiki/work/concepts"
    printf -- '---\ntype: concept\ntags: []\ncompiled_at: "2026-09-30"\npartition: work\n---\n# New\nSee [[Kafka]].\n' > "$s/wiki/work/concepts/New.md"
    printf '{"item":"x","decision":"create","target":"wiki/work/concepts/New.md","source":"s","reason":"r"}\n' > "$s/_decisions.jsonl" ;;
  noop)
    printf '{"item":"x","decision":"noop","target":"wiki/work/concepts/Kafka.md","source":"s","reason":"r"}\n' > "$s/_decisions.jsonl" ;;
  brief)
    mkdir -p "$s/briefings"
    printf -- '---\ntype: briefing\ndate: "%s"\n---\n# Brief\n' "$(date +%F)" > "$s/briefings/$(date +%F).md" ;;
  nothing) ;;
  fail) exit 1 ;;
  sleep) sleep 5 ;;
esac
printf '{"type":"result","subtype":"success","permission_denials":%s}\n' "${STUB_DENIALS:-[]}"
```

- [ ] **Step 2: Write the failing tests**

`system/tests/headless.bats`:
```bash
#!/usr/bin/env bats
load helpers

setup() {
  make_vault
  cd "$V"
  mkdir -p raw/work/notes raw/inbox/.staging
  printf -- '---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "s1"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\nDigest one.\n' > raw/work/notes/d1.md
  export CLAUDE_BIN="$REPO/system/tests/stub_claude" STUB_ARGS="$BATS_TEST_TMPDIR/args" STUB_STDIN="$BATS_TEST_TMPDIR/stdin"
  RH="$V/system/scripts/run_headless.sh"
  LEDGER="system/logs/runs-$(TZ=America/Denver date +%Y-%m).jsonl"
}

@test "usage errors exit 2" {
  run "$RH"; [ "$status" -eq 2 ]
  run "$RH" rm; [ "$status" -eq 2 ]
  run "$RH" ingest; [ "$status" -eq 2 ]
  run "$RH" brief extra; [ "$status" -eq 2 ]
  run "$RH" ingest wiki/work/concepts/Kafka.md; [ "$status" -eq 2 ]
  printf -- '---\ntype: session_digest\npartition: personal\ncodebase: "v"\nsession_id: "s"\ncreated_at: "2026-10-01T09:00:00-06:00"\n---\nx\n' > "$BATS_TEST_TMPDIR/p.md"
  mkdir -p raw/personal/notes && cp "$BATS_TEST_TMPDIR/p.md" raw/personal/notes/p.md
  run "$RH" ingest raw/work/notes/d1.md raw/personal/notes/p.md; [ "$status" -eq 2 ]
}

@test "invalid settings exit 3 without calling claude" {
  echo '{' > system/headless.settings.json
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 3 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "exact invocation flags, inlined prompt and /dev/null stdin" {
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  grep -qx -- '--restricted' "$STUB_ARGS"
  grep -qx -- 'system/headless.settings.json' "$STUB_ARGS"
  grep -qx -- '--strict-mcp-config' "$STUB_ARGS"
  grep -qx -- '--no-session-persistence' "$STUB_ARGS"
  grep -qx -- 'dontAsk' "$STUB_ARGS"
  grep -qx -- 'json' "$STUB_ARGS"
  grep -qx -- 'CLAUDE.md' "$STUB_ARGS"
  grep -qx -- 'Read,Glob,Grep,Edit,Write,Bash' "$STUB_ARGS"
  grep -qE -- '^Edit\(/wiki/\.staging/[0-9]{8}T[0-9]{6}-ingest-[0-9a-f]{4}/\*\*\)$' "$STUB_ARGS"
  grep -qx -- 'Bash(system/scripts/vault_index.py stage:*)' "$STUB_ARGS"
  ! grep -q -- '--setting-sources' "$STUB_ARGS"
  ! grep -q -- 'vault_index.py set' "$STUB_ARGS"
  ! grep -qF -- '$ARGUMENTS' "$STUB_ARGS"
  grep -q -- 'raw/work/notes/d1.md' "$STUB_ARGS"
  [ "$(cat "$STUB_STDIN")" = "/dev/null" ]
}

@test "successful ingest publishes with provenance and writes a ledger line" {
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  grep -q 'provenance: \["headless"\]' wiki/work/concepts/New.md
  [ "$(jq -r .exit "$LEDGER")" = "0" ]
  [ "$(jq -r '.publish.published[0]' "$LEDGER")" = "wiki/work/concepts/New.md" ]
  [ "$(jq -r '.partition' "$LEDGER")" = "work" ]
  [ "$(jq -r '.input_sha256[0]' "$LEDGER")" = "$(sha256sum raw/work/notes/d1.md | cut -d' ' -f1)" ]
  [ -z "$(ls -A wiki/.staging)" ]
}

@test "noop ingest succeeds; brief that writes nothing exits 5" {
  STUB_MODE=noop run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  STUB_MODE=nothing run "$RH" brief
  [ "$status" -eq 5 ]
  STUB_MODE=brief run "$RH" brief
  [ "$status" -eq 0 ]
  [ -f "briefings/$(TZ=America/Denver date +%F).md" ]
}

@test "claude failure and timeout are recorded and staging is quarantined" {
  STUB_MODE=fail run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 1 ]
  HEADLESS_TIMEOUT=1 STUB_MODE=sleep run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 124 ]
  [ "$(jq -s 'map(.exit) | sort | join(",")' "$LEDGER")" = '"1,124"' ]
  [ -z "$(ls -A wiki/.staging)" ]
  grep -q 'failed (exit 1)' system/logs/alerts_*.md
}

@test "daily cap exits 4 and alerts once" {
  mkdir -p system/logs
  today="$(TZ=America/Denver date +%F)"
  for i in 1 2; do printf '{"run_id":"r%s","command":"ingest","started_at":"%sT01:00:00-06:00","exit":0}\n' "$i" "$today" >> "$LEDGER"; done
  HEADLESS_MAX_RUNS_PER_DAY=2 run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  HEADLESS_MAX_RUNS_PER_DAY=2 run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 4 ]
  [ "$(grep -c 'daily headless cap' system/logs/alerts_*.md)" -eq 1 ]
  [ ! -e "$STUB_ARGS" ]
}

@test "malformed ledger line is ignored" {
  mkdir -p system/logs
  printf '{"run_id":"r1","command":"ingest","started_at":"%sT01:0' "$(TZ=America/Denver date +%F)" > "$LEDGER"
  printf '\n' >> "$LEDGER"
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
}

@test "brief gives up on a busy run.lock with exit 6" {
  mkdir -p system/logs
  flock system/run.lock sleep 4 &
  sleep 0.5
  HEADLESS_LOCK_WAIT=1 STUB_MODE=brief run "$RH" brief
  [ "$status" -eq 6 ]
  wait
}

@test "permission denials are recorded as warnings" {
  STUB_DENIALS='[{"tool_name":"Write"}]' run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ "$(jq -r '.warnings.permission_denials' "$LEDGER")" = "1" ]
}

@test "recovery quarantines leftover staging before the run" {
  mkdir -p wiki/.staging/20260930T010101-ingest-0000/wiki/work/concepts
  echo x > wiki/.staging/20260930T010101-ingest-0000/wiki/work/concepts/Old.md
  run "$RH" ingest raw/work/notes/d1.md
  [ "$status" -eq 0 ]
  [ -f system/quarantine/20260930T010101-ingest-0000/staged/wiki/work/concepts/Old.md ]
}
```

- [ ] **Step 3: Run to verify failure**

Run: `chmod +x system/tests/stub_claude && bats system/tests/headless.bats`
Expected: FAIL (`run_headless.sh: No such file or directory`).

- [ ] **Step 4: Implement**

`system/scripts/run_headless.sh`:
```bash
#!/bin/bash
# Wheeljack's harness: the only way automation invokes claude (spec §6.3).
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
# shellcheck source=lib_args.sh
source system/scripts/lib_args.sh
# shellcheck source=lib_config.sh
source system/scripts/lib_config.sh

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
MAX_PER_DAY="${HEADLESS_MAX_RUNS_PER_DAY:-60}"
TIMEOUT="${HEADLESS_TIMEOUT:-15m}"
LOCK_WAIT="${HEADLESS_LOCK_WAIT:-600}"
TZ="$(config_get timezone UTC)"
export TZ JARVIS_HEADLESS=1
TODAY="$(date +%F)"
LEDGER="system/logs/runs-$(date +%Y-%m).jsonl"
mkdir -p system/logs/headless system/logs/runs

die() { echo "run_headless: $2" >&2; exit "$1"; }
alert() { printf -- '- %s [wheeljack] %s\n' "$(date +%H:%M:%S)" "$1" >> "system/logs/alerts_${TODAY}.md"; }
json_list() { if (( $# )); then printf '%s\n' "$@" | jq -R . | jq -cs .; else echo '[]'; fi; }

input_partition() {
  local p
  p="$(system/scripts/vault_index.py field "$1" partition 2>/dev/null || true)"
  case "$p" in work|personal|shared) ;; *) p="$(config_get default_partition personal)" ;; esac
  printf '%s\n' "$p"
}

cmd="${1:-}"
(( $# )) && shift
case "$cmd" in ingest|brief|debrief) ;; *) die 2 "unknown command: ${cmd:-<none>}" ;; esac
LOG="system/logs/headless/${cmd}_${TODAY}.log"

inputs=() partition=""
if [[ "$cmd" == ingest ]]; then
  (( $# >= 1 && $# <= 5 )) || die 2 "ingest takes 1-5 raw paths"
  for arg in "$@"; do
    relpath="$(args_vault_path "$arg")" || die 2 "not a file inside the vault: $arg"
    case "$relpath" in
      raw/inbox/.staging/*) p="$(input_partition "$relpath")" ;;
      raw/work/notes/*|raw/personal/notes/*|raw/shared/notes/*) p="${relpath#raw/}"; p="${p%%/*}" ;;
      *) die 2 "not an ingestible raw path: $relpath" ;;
    esac
    [[ -z "$partition" || "$partition" == "$p" ]] || die 2 "inputs span partitions ($partition, $p)"
    partition="$p"
    inputs+=("$relpath")
  done
else
  (( $# == 0 )) || die 2 "$cmd takes no arguments"
fi

if ! jq empty system/headless.settings.json 2>/dev/null; then
  alert "system/headless.settings.json is missing or invalid; $cmd not run"
  die 3 "invalid system/headless.settings.json"
fi

exec 9>system/run.lock
if [[ "$cmd" == ingest ]]; then
  flock 9
elif ! flock -w "$LOCK_WAIT" 9; then
  alert "$cmd skipped: run.lock busy for ${LOCK_WAIT}s"
  die 6 "run.lock busy"
fi

system/scripts/publish_staged.py recover >> "$LOG" 2>&1 || true

runs_today=0
if [[ -f "$LEDGER" ]]; then
  runs_today="$(jq -R --arg d "$TODAY" 'fromjson? | select(.command != "retry" and ((.started_at // "") | startswith($d))) | 1' "$LEDGER" | wc -l)"
fi
if (( runs_today >= MAX_PER_DAY )); then
  marker="system/logs/.cap-alerted-$TODAY"
  [[ -e "$marker" ]] || { alert "daily headless cap ($MAX_PER_DAY) reached; inputs left in place"; : > "$marker"; }
  die 4 "daily cap reached"
fi

run_id="$(date +%Y%m%dT%H%M%S)-$cmd-$(od -An -N2 -tx1 /dev/urandom | tr -d ' \n')"
case "$cmd" in
  ingest) if [[ "$partition" == shared ]]; then targets=("wiki/shared/**"); else targets=("wiki/$partition/**" "wiki/shared/**"); fi ;;
  brief) targets=("briefings/$TODAY.md") ;;
  debrief) targets=("briefings/$TODAY.debrief.md") ;;
esac
started="$(date -Iseconds)"
system/scripts/publish_staged.py snapshot "$run_id" --targets "${targets[@]}" >/dev/null

cmdfile=".claude/commands/$cmd.md"
[[ -f "$cmdfile" ]] || die 2 "missing $cmdfile"
body="$(awk 'NR==1 && $0=="---" {fm=1; next} fm && $0=="---" {fm=0; next} !fm' "$cmdfile")"
argstr="$run_id"
(( ${#inputs[@]} )) && argstr="$run_id ${inputs[*]}"
prompt="${body//\$ARGUMENTS/$argstr}"

vi="system/scripts/vault_index.py"
allow=("Edit(/wiki/.staging/$run_id/**)")
for sub in query related show backlinks orphans issues validate field stage; do allow+=("Bash($vi $sub:*)"); done

out="system/logs/runs/$run_id/claude.json"
printf '\n===== %s %s %s\n' "$(date -Iseconds)" "$run_id" "${inputs[*]:-}" >> "$LOG"
set +e
timeout "$TIMEOUT" "$CLAUDE_BIN" -p "$prompt" --append-system-prompt-file CLAUDE.md \
  --restricted --settings system/headless.settings.json --strict-mcp-config --no-session-persistence \
  --permission-mode dontAsk --output-format json --tools "Read,Glob,Grep,Edit,Write,Bash" \
  --allowedTools "${allow[@]}" < /dev/null > "$out" 2>> "$LOG"
rc=$?
set -e
denials="$(jq -r '(.permission_denials // []) | length' "$out" 2>/dev/null || true)"
[[ "$denials" =~ ^[0-9]+$ ]] || denials=0

if (( rc == 0 )); then
  set +e
  system/scripts/publish_staged.py commit "$run_id" >> "$LOG" 2>&1
  prc=$?
  set -e
  if (( prc != 0 )); then
    rc=5
    alert "$cmd $run_id: publish rejected or empty (system/logs/runs/$run_id/publish.json)"
  fi
else
  system/scripts/publish_staged.py abort "$run_id" >> "$LOG" 2>&1 || true
  alert "$cmd $run_id failed (exit $rc)"
fi

shas=()
if [[ -n "${JARVIS_ORIGINAL_SHA256:-}" ]]; then
  read -r -a shas <<< "$JARVIS_ORIGINAL_SHA256"
else
  for f in "${inputs[@]}"; do shas+=("$(sha256sum -- "$f" | cut -d' ' -f1)"); done
fi
attempt=1
if (( ${#shas[@]} )); then
  prev="system/logs/runs-$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m).jsonl"
  failures="$( { cat "$prev" "$LEDGER" 2>/dev/null || true; } | jq -R --argjson s "$(json_list "${shas[@]}")" \
    'fromjson? | select(.command != "retry" and (.exit // 0) != 0 and (.exit // 0) != 4 and ([.input_sha256[]?] | any(. as $x | $s | index($x)))) | 1' | wc -l)"
  attempt=$(( failures + 1 ))
fi
pubsum="$(jq -c '{status, published: (.published // []), rejected: ([(.problems // [])[].path] | unique), conflicts: (.conflicts // [])}' \
  "system/logs/runs/$run_id/publish.json" 2>/dev/null || echo '{}')"
jq -cn --arg run_id "$run_id" --arg command "$cmd" --arg started "$started" --arg finished "$(date -Iseconds)" \
  --argjson inputs "$(json_list "${inputs[@]}")" --argjson shas "$(json_list "${shas[@]}")" \
  --arg partition "$partition" --argjson exit "$rc" --argjson publish "$pubsum" \
  --argjson attempt "$attempt" --argjson denials "$denials" \
  '{run_id:$run_id, command:$command, started_at:$started, finished_at:$finished, inputs:$inputs,
    input_sha256:$shas, partition:(if $partition == "" then null else $partition end), exit:$exit,
    publish:$publish, attempt:$attempt, warnings:{permission_denials:$denials}}' >> "$LEDGER"
exit "$rc"
```
Run: `chmod +x system/scripts/run_headless.sh`

- [ ] **Step 5: Run to verify pass**

Run: `bats system/tests/headless.bats`
Expected: `11 tests, 0 failures`.

- [ ] **Step 6: Run all suites and commit**

Run: `python3 -m pytest system/tests/python -q && bats system/tests/vault_integrity.bats system/tests/scripts.bats system/tests/lib.bats system/tests/headless.bats`
Expected: all pass.
```bash
git add system/scripts/run_headless.sh system/tests/headless.bats system/tests/stub_claude
git commit -m "feat(wheeljack): add run_headless.sh, the isolated headless harness"
```

---

### Task 8: Intake daemon — briefing extraction and inbox

**Files:**
- Create: `system/scripts/vaultlib/intake.py`, `system/scripts/intake.py`, `system/scripts/intake_daemon.sh`
- Test: `system/tests/python/test_intake.py`

**Interfaces:**
- Consumes: `run_headless.sh ingest …` (exit codes above; reads `JARVIS_ORIGINAL_SHA256`), the run ledger, `redact.redact`, `frontmatter.parse`, `schema.PARTITIONS`.
- Produces: `intake.Intake(vault, now=None, max_runs=None)` with `extract_briefing()`, `process_inbox() -> bool` (False when the daily cap stopped processing), `process_digests() -> bool` (Task 9), `retry(run_id=None) -> list[str]` (Task 9), `run() -> None`; CLI `system/scripts/intake.py [--retry RUN_ID | --retry-all]`; `system/scripts/intake_daemon.sh` (exec wrapper). Files: `system/logs/intake_manifest-<YYYY>.jsonl`, `system/logs/alerts_<date>.md`, `system/quarantine/poisoned/<name>` + `<name>.origin.json`.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_intake.py`:
```python
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from helpers import REPO, write
from vaultlib.intake import Intake

TZ = ZoneInfo("America/Denver")  # the iv fixture's configured timezone


def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def ledger_month():
    return datetime.now(TZ).strftime("%Y-%m")

STUB = """#!/usr/bin/env python3
import json, os, sys, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
TZ = ZoneInfo("America/Denver")
vault = Path(__file__).resolve().parents[2]
args = sys.argv[1:]
calls = vault / "calls.jsonl"
staged = {a: (vault / a).read_text(errors="replace") for a in args[1:] if (vault / a).is_file()}
rc_queue = vault / "rc_queue.json"
rcs = json.loads(rc_queue.read_text()) if rc_queue.exists() else []
rc = rcs.pop(0) if rcs else int(os.environ.get("STUB_RC", "0"))
rc_queue.write_text(json.dumps(rcs))
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
with open(calls, "a") as fh:
    fh.write(json.dumps({"args": args, "staged": staged}) + "\\n")
ledger = vault / "system/logs" / f"runs-{datetime.now(TZ).strftime('%Y-%m')}.jsonl"
ledger.parent.mkdir(parents=True, exist_ok=True)
with open(ledger, "a") as fh:
    fh.write(json.dumps({"run_id": f"stub-{time.time_ns()}", "command": "ingest",
                         "started_at": datetime.now(TZ).isoformat(), "inputs": args[1:],
                         "input_sha256": os.environ.get("JARVIS_ORIGINAL_SHA256", "").split(), "exit": rc}) + "\\n")
sys.exit(rc)
"""


@pytest.fixture
def iv(vault):
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    stub = vault / "system/scripts/run_headless.sh"
    stub.write_text(STUB)
    stub.chmod(0o755)
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\n'
          'debrief_time: "17:00"\nremote_mode: "none"\ndefault_partition: "personal"\n---\n')
    for d in ("raw/inbox", "raw/archive", "raw/telemetry"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    return vault


def calls(vault):
    path = vault / "calls.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def later():
    return time.time() + 3600


def test_inbox_file_ingested_and_archived(iv):
    write(iv, "raw/inbox/note.md", "plain note\n")
    Intake(iv, now=later()).run()
    assert calls(iv)[0]["args"] == ["ingest", "raw/inbox/.staging/note.md"]
    assert (iv / "raw/archive/note.md").read_text() == "plain note\n"
    assert not (iv / "raw/inbox/note.md").exists() and not (iv / "raw/inbox/.staging/note.md").exists()
    manifest = (iv / "system/logs" / f"intake_manifest-{datetime.now(TZ).year}.jsonl").read_text()
    assert '"name": "note.md"' in manifest


def test_fresh_and_temp_files_skipped(iv):
    write(iv, "raw/inbox/fresh.md", "x")
    for name in (".hidden.md", "a.md~", "b.tmp", "c.swp", "d.sync-conflict-1.md", ".~lock.e#", "f.crdownload", "g.part"):
        write(iv, f"raw/inbox/{name}", "x")
    Intake(iv).run()
    assert calls(iv) == []
    Intake(iv, now=later()).run()
    assert [c["args"][1] for c in calls(iv)] == ["raw/inbox/.staging/fresh.md"]


def test_unicode_name_sanitized(iv):
    write(iv, "raw/inbox/Meeting – café notes.md", "x")
    Intake(iv, now=later()).run()
    staged = calls(iv)[0]["args"][1]
    assert staged.startswith("raw/inbox/.staging/Meeting") and staged.endswith("notes.md")
    assert all(ch.isascii() for ch in staged)


def test_duplicate_is_archived_without_ingest(iv):
    write(iv, "raw/inbox/a.md", "same")
    Intake(iv, now=later()).run()
    write(iv, "raw/inbox/b.md", "same")
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert any(p.name.startswith("b-dup-") for p in (iv / "raw/archive").iterdir())


def test_production_error_routed_to_telemetry(iv):
    write(iv, "raw/inbox/err.md", '---\ntype: production_error\nservice: "x"\nexception: "E"\n'
          'operation_id: "1"\ndetected_at: "2026-10-01T00:00:00Z"\n---\nboom\n')
    Intake(iv, now=later()).run()
    assert calls(iv) == [] and (iv / "raw/telemetry/err.md").is_file()


def test_archive_collision_renamed_before_ingest(iv):
    write(iv, "raw/archive/n.md", "older")
    write(iv, "raw/inbox/n.md", "newer")
    Intake(iv, now=later()).run()
    staged = calls(iv)[0]["args"][1]
    assert staged.startswith("raw/inbox/.staging/n-") and staged.endswith(".md")
    assert (iv / "raw/archive/n.md").read_text() == "older"


def test_redacted_copy_ingested_original_archived(iv):
    write(iv, "raw/inbox/s.md", "password=hunter2\n")
    Intake(iv, now=later()).run()
    assert "hunter2" not in calls(iv)[0]["staged"]["raw/inbox/.staging/s.md"]
    assert (iv / "raw/archive/s.md").read_text() == "password=hunter2\n"


def test_daily_cap_leaves_inputs_and_stops(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "4")
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert (iv / "raw/inbox/a.md").exists() and (iv / "raw/inbox/b.md").exists()


def test_failures_poison_after_three_attempts(iv, monkeypatch):
    write(iv, "raw/inbox/bad.md", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(2):
        Intake(iv, now=later()).run()
        assert (iv / "raw/inbox/bad.md").exists()
    Intake(iv, now=later()).run()
    assert (iv / "system/quarantine/poisoned/bad.md").is_file()
    origin = json.loads((iv / "system/quarantine/poisoned/bad.md.origin.json").read_text())
    assert origin["origin"] == "raw/inbox/bad.md"
    assert "poisoned" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_max_runs(iv, monkeypatch):
    for i in range(4):
        write(iv, f"raw/inbox/{i}.md", str(i))
    Intake(iv, now=later(), max_runs=2).run()
    assert len(calls(iv)) == 2


def test_malformed_ledger_line_ignored(iv, monkeypatch):
    write(iv, f"system/logs/runs-{ledger_month()}.jsonl", '{"run_id": "x", "exit"\n')
    write(iv, "raw/inbox/a.md", "a")
    Intake(iv, now=later()).run()
    assert (iv / "raw/archive/a.md").exists()


def test_concurrent_daemons_do_not_double_ingest(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    monkeypatch.setenv("STUB_SLEEP", "1")
    threads = [threading.Thread(target=lambda: Intake(iv, now=later()).run()) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls(iv)) == 1


def briefing(iv, text):
    path = write(iv, f"briefings/{today()}.md", text)
    old = time.time() - 600
    os.utime(path, (old, old))
    return path


def test_briefing_block_extracted_and_removed(iv):
    path = briefing(iv, "top\n#wiki-ingest-start\nidea one\n#wiki-ingest-end\nbottom\n")
    Intake(iv, now=later()).extract_briefing()
    assert path.read_text() == "top\nbottom\n"
    drops = list((iv / "raw/inbox").glob("daily_note_drop_*.md"))
    assert len(drops) == 1 and drops[0].read_text() == "idea one\n"


def test_unterminated_marker_leaves_briefing(iv):
    text = "top\n#wiki-ingest-start\nidea\n## Evening\nimportant\n"
    path = briefing(iv, text)
    Intake(iv, now=later()).extract_briefing()
    assert path.read_text() == text
    assert not list((iv / "raw/inbox").glob("daily_note_drop_*.md"))
    assert "unterminated" in next((iv / "system/logs").glob("alerts_*.md")).read_text()


def test_fresh_briefing_skipped_and_never_created(iv):
    path = write(iv, f"briefings/{today()}.md", "#wiki-ingest-start\nx\n#wiki-ingest-end\n")
    Intake(iv).extract_briefing()
    assert "#wiki-ingest-start" in path.read_text()
    path.unlink()
    Intake(iv, now=later()).run()
    assert not path.exists()


def test_cli_entry(iv):
    write(iv, "raw/inbox/a.md", "a")
    res = subprocess.run([str(iv / "system/scripts/intake_daemon.sh")], capture_output=True, text=True,
                         env={**os.environ, "INTAKE_NOW_OFFSET": "3600"})
    assert res.returncode == 0, res.stderr
    assert (iv / "raw/archive/a.md").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_intake.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'vaultlib.intake'`.

- [ ] **Step 3: Implement**

`system/scripts/vaultlib/intake.py`:
```python
"""Wheeljack intake: compile inbox files and digest batches through run_headless.sh (spec §6.4)."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import frontmatter, redact as redactmod, schema as schemamod

FRESH_SECONDS = 60
MAX_ATTEMPTS = 3
DIGEST_BATCH = 5
SKIP_SUFFIXES = ("~", ".tmp", ".swp", ".crdownload", ".part")
RAW_NAME = re.compile(r"^[A-Za-z0-9._ -]+$")
START, END = "#wiki-ingest-start", "#wiki-ingest-end"
CAP_EXIT = 4


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize(name: str) -> str:
    cleaned = "".join(ch if (ch.isascii() and (ch.isalnum() or ch in "._ -")) else "_" for ch in name)
    cleaned = cleaned.lstrip(".")
    return cleaned or "file"


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    return path.with_name(f"{stem}-{time.time_ns()}{suffix}")


class Intake:
    def __init__(self, vault, now=None, max_runs=None):
        self.vault = Path(vault)
        offset = float(os.environ.get("INTAKE_NOW_OFFSET", "0"))
        self._now = now if now is not None else (time.time() + offset if offset else None)
        self.max_runs = max_runs if max_runs is not None else int(os.environ.get("INTAKE_MAX_RUNS", "5"))
        self.runs = 0
        self.logs = self.vault / "system" / "logs"
        try:
            self.tz = ZoneInfo(self.config("timezone", "UTC"))
        except (ZoneInfoNotFoundError, ValueError):
            self.tz = timezone.utc

    # -- helpers ---------------------------------------------------------
    def now(self) -> float:
        return self._now if self._now is not None else time.time()

    def dt(self) -> datetime:
        """Wall clock in the configured timezone (matches run_headless.sh's TZ)."""
        return datetime.now(self.tz)

    def today(self) -> str:
        return self.dt().strftime("%Y-%m-%d")

    def alert(self, message: str) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        with open(self.logs / f"alerts_{self.today()}.md", "a", encoding="utf-8") as fh:
            fh.write(f"- {self.dt().strftime('%H:%M:%S')} [wheeljack] {message}\n")

    def config(self, key: str, default: str) -> str:
        path = self.vault / "system" / "config.md"
        try:
            data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
        except (OSError, UnicodeDecodeError):
            return default
        value = data.get(key)
        return value if isinstance(value, str) and value else default

    @contextlib.contextmanager
    def lock(self, name: str, timeout: float):
        """flock(2) on system/<name>; interoperates with flock(1) in run_headless.sh."""
        path = self.vault / "system" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as handle:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(name)
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def eligible(self, path: Path) -> bool:
        name = path.name
        if path.is_symlink() or not path.is_file() or name.startswith(".") or name.endswith(SKIP_SUFFIXES):
            return False
        if ".sync-conflict" in name:
            return False
        return self.now() - path.stat().st_mtime >= FRESH_SECONDS

    def _jsonl(self, path: Path):
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record

    def _ledgers(self):
        now = self.dt()
        first = now.replace(day=1)
        prev = (first.toordinal() - 1)
        prev_month = datetime.fromordinal(prev).strftime("%Y-%m")
        for month in (prev_month, now.strftime("%Y-%m")):
            yield from self._jsonl(self.logs / f"runs-{month}.jsonl")

    def failures_since_retry(self, sha: str) -> int:
        count = 0
        for record in self._ledgers():
            shas = record.get("input_sha256") or []
            if not isinstance(shas, list) or sha not in shas:
                continue
            if record.get("command") == "retry":
                count = 0
            elif record.get("exit") not in (0, CAP_EXIT, None):
                count += 1
        return count

    def manifest_has(self, sha: str) -> bool:
        year = self.dt().year
        return any(r.get("sha256") == sha for y in (year - 1, year)
                   for r in self._jsonl(self.logs / f"intake_manifest-{y}.jsonl"))

    def manifest_add(self, sha: str, name: str) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        with open(self.logs / f"intake_manifest-{self.dt().year}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"sha256": sha, "name": name,
                                 "published_at": self.dt().isoformat()}) + "\n")

    def headless(self, rel_paths, shas) -> int:
        self.runs += 1
        env = {**os.environ, "JARVIS_ORIGINAL_SHA256": " ".join(shas)}
        return subprocess.run([str(self.vault / "system/scripts/run_headless.sh"), "ingest", *rel_paths],
                              cwd=self.vault, env=env).returncode

    def poison(self, path: Path, origin: str, sha: str) -> None:
        dest = unique(self.vault / "system" / "quarantine" / "poisoned" / path.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        (dest.parent / f"{dest.name}.origin.json").write_text(
            json.dumps({"origin": origin, "sha256": sha, "poisoned_at": self.dt().isoformat()}),
            encoding="utf-8")
        self.alert(f"poisoned after {MAX_ATTEMPTS} failed attempts: {origin} → {dest.relative_to(self.vault)}")

    # -- briefing extraction ---------------------------------------------
    def extract_briefing(self) -> None:
        path = self.vault / "briefings" / f"{self.today()}.md"
        if not path.is_file() or self.now() - path.stat().st_mtime < FRESH_SECONDS:
            return
        text = path.read_text(encoding="utf-8")
        if START not in text:
            return
        kept, extracted, inside = [], [], False
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped == START:
                if inside:
                    self.alert("briefing has a nested #wiki-ingest-start; left untouched")
                    return
                inside = True
                continue
            if stripped == END and inside:
                inside = False
                continue
            (extracted if inside else kept).append(line)
        if inside:
            self.alert(f"briefing {path.name} has an unterminated #wiki-ingest-start; left untouched")
            return
        try:
            with self.lock("run.lock", timeout=600):
                inbox = self.vault / "raw" / "inbox"
                inbox.mkdir(parents=True, exist_ok=True)
                drop = unique(inbox / f"daily_note_drop_{int(time.time())}.md")
                drop.write_text("\n".join(extracted) + "\n", encoding="utf-8")
                tmp = path.with_name(f".{path.name}.tmp")
                tmp.write_text("\n".join(kept), encoding="utf-8")
                os.replace(tmp, path)
        except TimeoutError:
            self.alert("briefing extraction skipped: run.lock busy")

    # -- inbox -----------------------------------------------------------
    def process_inbox(self) -> bool:
        inbox = self.vault / "raw" / "inbox"
        if not inbox.is_dir():
            return True
        for path in sorted((p for p in inbox.iterdir() if self.eligible(p)), key=lambda p: p.stat().st_mtime):
            if self.runs >= self.max_runs:
                return True
            if not self._inbox_file(path):
                return False
        return True

    def _inbox_file(self, path: Path) -> bool:
        archive, telemetry = self.vault / "raw" / "archive", self.vault / "raw" / "telemetry"
        if not RAW_NAME.match(path.name):
            renamed = unique(path.with_name(sanitize(path.name)))
            path.rename(renamed)
            path = renamed
        sha = sha256_file(path)
        if self.manifest_has(sha):
            archive.mkdir(parents=True, exist_ok=True)
            path.rename(unique(archive / f"{path.stem}-dup-{int(time.time())}{path.suffix}"))
            return True
        if path.suffix == ".md":
            data = frontmatter.parse(path.read_text(encoding="utf-8", errors="replace")).data or {}
            if data.get("type") == "production_error":
                telemetry.mkdir(parents=True, exist_ok=True)
                path.rename(unique(telemetry / path.name))
                return True
        if (archive / path.name).exists():
            renamed = path.with_name(f"{path.stem}-{int(time.time())}{path.suffix}")
            path.rename(renamed)
            path = renamed
        staging = self.vault / "raw" / "inbox" / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        copy = staging / path.name
        raw = path.read_bytes()
        try:
            text, count = redactmod.redact(raw.decode("utf-8"))
            copy.write_text(text, encoding="utf-8")
        except UnicodeDecodeError:
            copy.write_bytes(raw)
        try:
            rc = self.headless([copy.relative_to(self.vault).as_posix()], [sha])
        finally:
            copy.unlink(missing_ok=True)
        if rc == 0:
            archive.mkdir(parents=True, exist_ok=True)
            path.rename(unique(archive / path.name))
            self.manifest_add(sha, path.name)
            return True
        if rc == CAP_EXIT:
            return False
        if self.failures_since_retry(sha) >= MAX_ATTEMPTS:
            self.poison(path, f"raw/inbox/{path.name}", sha)
        else:
            self.alert(f"ingest of raw/inbox/{path.name} failed (exit {rc}); will retry")
        return True

    # -- digests (Task 9) --------------------------------------------------
    def process_digests(self) -> bool:
        return True

    def run(self) -> None:
        try:
            with self.lock("intake.lock", timeout=0):
                self.extract_briefing()
                if self.process_inbox():
                    self.process_digests()
        except TimeoutError:
            pass  # another daemon is running
```

`system/scripts/intake.py`:
```python
#!/usr/bin/env python3
"""Wheeljack intake daemon (spec §6.4)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vaultlib.intake import Intake  # noqa: E402

parser = argparse.ArgumentParser(prog="intake_daemon.sh")
group = parser.add_mutually_exclusive_group()
group.add_argument("--retry", metavar="RUN_ID")
group.add_argument("--retry-all", action="store_true")
args = parser.parse_args()
intake = Intake(Path(__file__).resolve().parents[2])
if args.retry or args.retry_all:
    for restored in intake.retry(args.retry):
        print(restored)
else:
    intake.run()
```

`system/scripts/intake_daemon.sh`:
```bash
#!/bin/bash
# Wheeljack intake daemon entry point (spec §6.4); the logic lives in vaultlib/intake.py.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"
exec system/scripts/intake.py "$@"
```
Run: `chmod +x system/scripts/intake.py system/scripts/intake_daemon.sh`

Note: `test_cli_entry` runs without `--retry`, so `Intake.retry` (Task 9) is not needed yet.

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python/test_intake.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/intake.py system/scripts/intake.py system/scripts/intake_daemon.sh system/tests/python/test_intake.py
git commit -m "feat(wheeljack): add intake daemon for briefing drops and inbox files"
```

---

### Task 9: Intake daemon — digest batches, batch splitting, retries

**Files:**
- Modify: `system/scripts/vaultlib/intake.py` (replace `process_digests`; add `retry`)
- Test: `system/tests/python/test_intake_digests.py`
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (mark Plan 2a complete)

**Interfaces:**
- Consumes: Task 8's `Intake`.
- Produces: `Intake.process_digests() -> bool`; `Intake.retry(run_id: str | None) -> list[str]` (restored origin paths); `system/logs/intake_solo.json` (list of digest SHAs to process one at a time); ledger lines `{"run_id": "retry-<epoch>", "command": "retry", "input_sha256": […], "inputs": […], "exit": 0, "started_at": …}`.

- [ ] **Step 1: Write the failing tests**

`system/tests/python/test_intake_digests.py`:
```python
import json

from helpers import write
from test_intake import calls, iv, ledger_month, later  # noqa: F401  (iv is a fixture)
from vaultlib.intake import Intake


def digest(vault, partition, name, body="digest"):
    return write(vault, f"raw/{partition}/notes/{name}.md",
                 f'---\ntype: session_digest\npartition: {partition}\ncodebase: "vault"\nsession_id: "{name}"\n'
                 f'created_at: "2026-10-01T09:00:00-06:00"\n---\n{body}\n')


def test_batch_of_digests_one_call_and_archived(iv):
    for n in ("d1", "d2", "d3"):
        digest(iv, "work", n)
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1 and len(calls(iv)[0]["args"]) == 4
    assert sorted(p.name for p in (iv / "raw/work/archive").iterdir()) == ["d1.md", "d2.md", "d3.md"]


def test_batches_capped_at_five(iv):
    for i in range(7):
        digest(iv, "work", f"d{i}")
    Intake(iv, now=later()).run()
    assert [len(c["args"]) - 1 for c in calls(iv)] == [5, 2]


def test_partitions_never_mixed(iv):
    digest(iv, "work", "w1")
    digest(iv, "personal", "p1")
    Intake(iv, now=later()).run()
    batches = [c["args"][1:] for c in calls(iv)]
    assert all(len({a.split("/")[1] for a in batch}) == 1 for batch in batches) and len(batches) == 2


def test_failed_batch_is_split_next_run(iv):
    for n in ("d1", "d2"):
        digest(iv, "work", n)
    (iv / "rc_queue.json").write_text(json.dumps([5]))
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    Intake(iv, now=later()).run()
    assert [len(c["args"]) - 1 for c in calls(iv)[1:]] == [1, 1]


def test_digest_poisoned_after_three_solo_failures(iv, monkeypatch):
    digest(iv, "work", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert (iv / "system/quarantine/poisoned/bad.md").is_file()
    origin = json.loads((iv / "system/quarantine/poisoned/bad.md.origin.json").read_text())
    assert origin["origin"] == "raw/work/notes/bad.md"


def test_cap_leaves_digests(iv, monkeypatch):
    digest(iv, "work", "d1")
    monkeypatch.setenv("STUB_RC", "4")
    Intake(iv, now=later()).run()
    assert (iv / "raw/work/notes/d1.md").exists()


def test_retry_all_restores_and_resets_attempts(iv, monkeypatch):
    write(iv, "raw/inbox/bad.md", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert Intake(iv, now=later()).retry(None) == ["raw/inbox/bad.md"]
    assert (iv / "raw/inbox/bad.md").exists()
    assert not list((iv / "system/quarantine/poisoned").glob("*.origin.json"))
    Intake(iv, now=later()).run()
    assert (iv / "raw/inbox/bad.md").exists()  # one failure since retry, not poisoned


def test_retry_by_run_id(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    ledger = (iv / "system/logs" / f"runs-{ledger_month()}.jsonl").read_text().splitlines()
    run_a = next(json.loads(l)["run_id"] for l in ledger if "a.md" in l)
    assert Intake(iv, now=later()).retry(run_a) == ["raw/inbox/a.md"]
    assert (iv / "system/quarantine/poisoned/b.md").is_file()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest system/tests/python/test_intake_digests.py -q`
Expected: FAIL (`AttributeError: 'Intake' object has no attribute 'retry'`, and digest tests seeing no calls).

- [ ] **Step 3: Implement — replace `process_digests` in `vaultlib/intake.py` and add `retry`**

```python
    # -- digests ---------------------------------------------------------
    def _solo(self) -> set:
        path = self.logs / "intake_solo.json"
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            return set()

    def _save_solo(self, shas: set) -> None:
        self.logs.mkdir(parents=True, exist_ok=True)
        (self.logs / "intake_solo.json").write_text(json.dumps(sorted(shas)), encoding="utf-8")

    def process_digests(self) -> bool:
        attempted: set = set()
        progress = True
        while progress:
            progress = False
            for partition in schemamod.PARTITIONS:
                if self.runs >= self.max_runs:
                    return True
                notes = self.vault / "raw" / partition / "notes"
                if not notes.is_dir():
                    continue
                pending = sorted((p for p in notes.iterdir() if p.suffix == ".md" and self.eligible(p)
                                  and p not in attempted), key=lambda p: p.stat().st_mtime)
                if not pending:
                    continue
                solo = self._solo()
                shas = {p: sha256_file(p) for p in pending}
                first = pending[0]
                batch = [first] if shas[first] in solo else [p for p in pending if shas[p] not in solo][:DIGEST_BATCH]
                attempted.update(batch)
                progress = True
                rc = self.headless([p.relative_to(self.vault).as_posix() for p in batch], [shas[p] for p in batch])
                if rc == 0:
                    archive = self.vault / "raw" / partition / "archive"
                    archive.mkdir(parents=True, exist_ok=True)
                    for p in batch:
                        p.rename(unique(archive / p.name))
                    self._save_solo(solo - {shas[p] for p in batch})
                elif rc == CAP_EXIT:
                    return False
                elif len(batch) > 1:
                    self._save_solo(solo | {shas[p] for p in batch})
                    self.alert(f"digest batch in {partition} failed (exit {rc}); retrying one at a time")
                elif self.failures_since_retry(shas[first]) >= MAX_ATTEMPTS:
                    self.poison(first, f"raw/{partition}/notes/{first.name}", shas[first])
                else:
                    self.alert(f"digest raw/{partition}/notes/{first.name} failed (exit {rc}); will retry")
        return True

    # -- retry -----------------------------------------------------------
    def retry(self, run_id=None) -> list:
        poisoned = self.vault / "system" / "quarantine" / "poisoned"
        if not poisoned.is_dir():
            return []
        wanted = None
        if run_id is not None:
            wanted = set()
            for record in self._ledgers():
                if record.get("run_id") == run_id and isinstance(record.get("input_sha256"), list):
                    wanted.update(record["input_sha256"])
        restored, shas = [], []
        for sidecar in sorted(poisoned.glob("*.origin.json")):
            try:
                info = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if wanted is not None and info.get("sha256") not in wanted:
                continue
            item = poisoned / sidecar.name[: -len(".origin.json")]
            origin = info.get("origin", "")
            if not item.is_file() or not re.match(r"^raw/(inbox|work/notes|personal/notes|shared/notes)/[^/]+$", origin):
                continue
            dest = unique(self.vault / origin)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dest))
            sidecar.unlink()
            restored.append(dest.relative_to(self.vault).as_posix())
            shas.append(info.get("sha256"))
        if restored:
            self._save_solo(self._solo() - set(shas))
            self.logs.mkdir(parents=True, exist_ok=True)
            with open(self.logs / f"runs-{self.dt().strftime('%Y-%m')}.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"run_id": f"retry-{int(time.time())}", "command": "retry",
                                     "started_at": self.dt().isoformat(),
                                     "inputs": restored, "input_sha256": shas, "exit": 0}) + "\n")
        return restored
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest system/tests/python -q`
Expected: all tests pass.

- [ ] **Step 5: Run every gating suite**

Run: `python3 -m pytest system/tests/python -q && bats system/tests/vault_integrity.bats system/tests/scripts.bats system/tests/lib.bats system/tests/headless.bats && system/scripts/lint_vault.sh`
Expected: all pass; lint reports 0 errors.

- [ ] **Step 6: Mark the roadmap and commit**

In `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`, change the Plan 2a row's status cell to `Complete (<date>): 2026-10-01-plan-2a-headless-core.md`.
```bash
git add system/scripts/vaultlib/intake.py system/tests/python/test_intake_digests.py docs/superpowers/plans/2026-09-30-jarvis-roadmap.md
git commit -m "feat(wheeljack): add digest batching, batch splitting and retries; mark Plan 2a complete"
```
