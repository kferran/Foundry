# Plan 4b: Memory Integration and Renames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/setup` offers the memory hooks (spec §11 step 5a) with a reviewed dry run and an explicit yes. The README documents memory, the "Stop hook error" label and `/digest`. `install_hooks.sh` gets the fixes Plans 3 and 4a parked for this plan. The last code commit applies the §15 rename `ChiefOfStaff.md` → `Optimus.md`.

**Architecture:** Most of this plan is prompt and documentation work around code that already exists.
- `install_hooks.sh` gains three things. It refuses input it cannot merge. Its `--uninstall` escape hatch needs nothing but `jq` and the settings file. And a small vault-local record (`system/logs/memory/install_hooks.json`) lists the containers each install had to create, so an uninstall removes exactly those and leaves every container the user already had, even an empty one.
- `/setup` phase 5a reads the installer's existing `--dry-run` output, explains it, and runs the installer only on an explicit yes.
- Two `/setup` minors from Plan 4a are fixed in the same prompt: the config is created from the example's frontmatter only, and the current `remote_mode` is offered as the default.

**Tech Stack:** bash 5, `jq` 1.8, bats 1.14, Python 3 (the existing `vaultlib`, used only through `vault_index.py`), Markdown prompts.

**Spec:** `docs/superpowers/specs/2026-09-30-vault-template-design.md`. This plan implements §11 step 5a, the §6.17 "README and `/setup` explain this" sentence about the Stop hook label, the README memory sections and `/digest` (§6.17, §6.19, §7.3a), and §15's remaining rename. The parked items come from `docs/superpowers/plans/2026-10-02-plan-3-outcomes.md` and `docs/superpowers/plans/2026-10-02-plan-4a-outcomes.md`. Read §6.19 and the installer (`system/scripts/install_hooks.sh`) before Task 1.

## Global Constraints

- **Never touch the real `~/.claude/`.** Tests set a temporary `HOME` and unset `CLAUDE_CONFIG_DIR` (the existing `hooks_install.bats` `setup()` already does). Never run `install_hooks.sh`, or any hook, against the real settings while implementing. Only the user does that, in Task 7.
- **`install_hooks.sh` touches only owned entries** (§6.19, §7.3a): the three hooks, the three `vault_index.py related|show|backlinks` Bash allows, and a `commands/digest.md` carrying `<!-- managed by vault: … -->`. The record file lives inside the vault, under the gitignored `system/logs/`, and is not a user-level change.
- **`CLAUDE.md` changes only its persona path** (Task 6). Its communication and Writing rules belong to Plan 6 (`docs/superpowers/specs/2026-10-02-communication-design.md`).
- **The headless acceptance gate stays valid:** do not change `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands. Changing any of them would require re-running Plan 4a's acceptance.
- **bats ruling R1:** no mid-test `!`, no `&&` assertion chains. Bats files stay mode 644.
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log`. **Lint:** `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log` (expected `0 errors`). Read every verdict from an exit code, never through a pipe.
- American English. Keep the README's existing style: short active sentences and tables. Commit trailers name the authoring model, after a blank line. Branch `feat/plan-4b`, from `origin/master` at 9332160.

## Decisions made while planning

- **D1 A vault-local record of created containers fixes the parked `"allow": []`.** The parked item needs the installer to remember whether `permissions.allow` existed before it ran. The general problem covers all six containers the merge writes into: `hooks`, its three event arrays, `permissions` and `permissions.allow`. An empty container the install created looks exactly like an empty one the user already had. On each install, the installer writes the list of containers that were absent to `system/logs/memory/install_hooks.json`, keyed by the settings path. `--uninstall` removes a container only if it is on that list, held an owned entry and is now empty. Rejected alternatives:
  - a marker key inside `settings.json`: a foreign key in a file whose schema belongs to Claude Code, and §7.3a limits user-level changes to §6.19's entries;
  - inferring from `settings.json.bak.*`: backups are not guaranteed to exist or to predate the first install;
  - "add `allow` only when absent": this is the same question, and it still has to be remembered.
  The record is gitignored and moves with the vault, and it needs no change outside the vault.
- **D2 Fallback without a record.** For installs made before the record existed, or after `system/logs/` was cleaned, uninstall uses the old rule: emptied hook containers are dropped, and an emptied `allow` only when it is the sole `permissions` key. A corrupt record counts as no record, so the escape hatch never fails because of it.
- **D3 Three conditions to delete.** A container is deleted only if the record lists it, it held an owned entry before this run, and it is empty now. A stale or hand-edited record can therefore never delete a container the user owns.
- **D4 Shape refused up front.** Before merging, install and `--dry-run` check that `hooks` and `permissions` are objects and that the three event arrays and `allow` are arrays. Anything else exits 1 and names the bad paths. A `jq` failure during the merge also maps to exit 1. A file that does not slurp to exactly one object (`{} {}`, an empty file) is refused. `--uninstall` skips the shape check, because it only removes what it recognizes.
- **D5 The escape hatch has no preconditions.** `--uninstall` no longer requires the hook files to be executable or the vault path to be plain. Both checks only matter for writing new entries.
- **D6 Backups never overwrite.** A backup that already exists for this second gets a `.1`, `.2`, … suffix (§6.19's `settings.json.bak.<epoch>` is otherwise kept). The installer prints `backup: <path>`, and `/setup` reports that line.
- **D7 `/setup` 5a defaults to no.** It shows the dry run before asking anything. When the dry run prints both `unchanged` lines, the hooks are already installed and no question is asked. Any answer other than an explicit yes changes nothing.
- **D8 New configs carry no example body.** `/setup` creates `system/config.md` from the example's frontmatter plus a fixed two-line body, by one exact command that `commands.bats` executes. An existing `config.md` keeps whatever body it has.
- **D9 Remote default.** `/setup` reads `remote_mode` and offers it as the default. When the mode is `private`, the current `origin` URL is the default URL.
- **D10 `/digest` stays user-level.** §5 lists `digest.md` under `.claude/commands/`, but §6.17 and §6.19 make it a user-level command written by `install_hooks.sh`. Only the user-level form works in codebase sessions. The README layout is corrected. `CLAUDE.md`'s command list is not touched (Global Constraints), and the README documents `/digest` instead.
- **D11 Rename scope and order.** §15's other names already exist: the `jarvis-*` units with themed `Description=` lines, `agent_owner: Optimus`, the `[wheeljack]` and `[soundwave]` log headers, and the module docstrings. Only `system/agents/ChiefOfStaff.md` remains. Task 6 is the last code commit. Tasks 7 and 8 are acceptance and status documents only. An `[ultra-magnus]` log header for publish events would mean editing `run_headless.sh` and re-running Plan 4a's acceptance, so it is deferred.
- **D12 Where the rename test looks.** The test greps only template-owned paths (`CLAUDE.md README.md .claude system`), so a user's own wiki notes can never fail `/backup`. `docs/superpowers/` keeps the old name as history. The pattern is `[C]hiefOfStaff` so the test cannot match itself.
- **Parked items taken:**
  - from Plan 3: the `allow: []` residue (Task 2); `--uninstall` depending on the hook files (Task 1); unexpected shape exiting 5 and `{} {}` being rewritten (Task 1).
  - cheap ones in the same code: the same-second backup overwrite, the unchecked `$status` lines, and the missing-hook test gap (Task 1); foreign empty `{}` and `[]` containers lost on uninstall (Task 2, same mechanism as `allow`).
  - from Plan 4a: the `/setup` `remote_mode` default and the "(example)" body (Task 4).
- **Parked items left deferred:** everything else in both outcomes docs, notably:
  - the `settings.json.tmp.$$` cleanup trap and the symlink write (no feasible failing test);
  - owned-digest marker matching for any vault, and suffix ownership from any root (Plan 3 D7);
  - every `recall.py`, `lib_memory.sh` and `memory_*.sh` minor (code this plan does not touch);
  - the Plan 4a prompt minors in `ingest`, `debrief`, `brief` and `/backup` (they would reopen the acceptance gate, or are outside this plan).

## Review Focus

1. **A user who installed the hooks by hand before this plan, then runs `--uninstall` or re-runs `/setup`.** No record exists. Uninstall must still restore their settings as well as the old code did, and a corrupt record must not block it. Pinned in Task 2: "an install made before records existed still uninstalls cleanly".
2. **A settings file the user keeps editing after install.** Here the user adds their own allow rule to a list the install created. Uninstall must keep the user's rule and the list. Pinned in Task 2: "a rule the user adds after install keeps its allow list through uninstall".
3. **A vault moved or renamed between install and uninstall.** The record moves with the vault and still restores exactly. Pinned in Task 2: "a vault moved after install still uninstalls exactly". A move into a path with spaces still uninstalls (Task 1).
4. **Re-running `/setup` with the hooks already installed.** 5a must recognize this from the dry run and must not ask again or reinstall. Pinned in Task 3: "after an install, --dry-run prints the two lines /setup reads as already installed", plus the 5a prompt test. Checked live in Task 7.
5. **An answer at the 5a question that is not a clear yes** ("maybe", "later", an Enter). Nothing is installed, and the report says memory is off. This is prompt behavior: Task 3's structural test pins the wording ("Only an explicit yes installs.", "default no"), and Task 7 checks it live with a non-yes answer.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `system/scripts/install_hooks.sh` (modify) | Input refusal, uninstall preconditions, backups (T1); created-container record (T2) | 1, 2 |
| `system/tests/hooks_install.bats` (modify) | Installer tests | 1, 2, 3 |
| `.claude/commands/setup.md` (modify) | Phase 5a, report row (T3); config creation and remote default (T4) | 3, 4 |
| `system/tests/commands.bats` (modify) | Structural `/setup` tests (T3, T4); rename pin (T6) | 3, 4, 6 |
| `README.md` (modify) | Memory section, layout, getting started, uninstall (T5); artifacts header (T6); 4b status (T8) | 5, 6, 8 |
| `system/agents/ChiefOfStaff.md` → `system/agents/Optimus.md` (rename) | §15 | 6 |
| `CLAUDE.md` (modify) | Persona path only | 6 |
| `docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md` (create) | Live 5a record | 7 |
| `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (modify), `docs/superpowers/plans/2026-10-02-plan-4b-outcomes.md` (create) | Status and outcomes | 8 |

Verified while planning: every test below was run red against `origin/master` and green against the drafts. The full gate exited 0 with every suite PASS (pytest 329 passed), and lint reported 0 errors.

---

### Task 1: `install_hooks.sh` refuses what it cannot merge, and `--uninstall` has no preconditions

**Files:**
- Modify: `system/scripts/install_hooks.sh`
- Test: `system/tests/hooks_install.bats`

**Interfaces:**
- Consumes: the existing installer and its test helpers `relocate`, `ours`, `$IH`, `$SET`, `$CFG`, `$V`, `$VP` (`hooks_install.bats` `setup()`).
- Produces:
  - exit 1 with `… is not a single JSON object; fix it by hand first (nothing was changed)`, or `… has an unexpected shape at: <paths> …`, for input it cannot merge;
  - `--uninstall` independent of the hook files and of the vault path;
  - a `backup: <path>` output line whenever a backup is written, with backups never overwritten.
  - Task 2 builds on this file, and Task 3's `/setup` reports the `backup:` line.

- [ ] **Step 1: Write the failing tests.** First, in `system/tests/hooks_install.bats`, add the line `  [ "$status" -eq 0 ]` directly after each of these `run` lines, which currently go unchecked (Plan 3 deferred minor):
  - the first `run "$IH"` in "install writes the managed /digest command; a foreign one is never touched";
  - the first `run "$IH"` in "a second run changes nothing and writes no new backup";
  - the `run "$IH"` in "a change is preceded by a timestamped backup of the old file";
  - in "--uninstall restores the original settings and removes only the owned /digest": after `run "$IH"` and after the second `run "$IH" --uninstall`;
  - the first `run "$IH"` in "moving the vault re-points the entries instead of duplicating them".

Then append these tests at the end of the file:

```bash
@test "a settings.json holding two JSON documents is refused, not rewritten" {
  printf '{} {}\n' > "$SET"
  run "$IH"
  [ "$status" -eq 1 ]
  [[ "$output" == *"is not a single JSON object"* ]]
  [ "$(cat "$SET")" = '{} {}' ]
}

@test "well-formed JSON of an unexpected shape exits 1 with a message and is left untouched" {
  for doc in '{"hooks": []}' '{"hooks": {"Stop": {}}}' '{"permissions": "ask"}' '{"permissions": {"allow": "Bash(x)"}}'; do
    printf '%s\n' "$doc" > "$SET"
    for mode in "" --dry-run; do
      run "$IH" $mode
      [ "$status" -eq 1 ]
      [[ "$output" == *"unexpected shape at: "* ]]
      [ "$(cat "$SET")" = "$doc" ]
    done
  done
}

@test "install refuses a missing or non-executable hook and changes nothing" {
  chmod -x "$V/system/hooks/memory_capture.sh"
  run "$IH"
  [ "$status" -eq 1 ]
  [[ "$output" == *"missing or not executable: system/hooks/memory_capture.sh"* ]]
  [ "$(sha256sum < "$SET")" = "$(sha256sum < "$BATS_TEST_TMPDIR/original.json")" ]
}

@test "--uninstall works without the hook files and from a path that needs quoting" {
  run "$IH"
  [ "$status" -eq 0 ]
  rm "$V/system/hooks/memory_recall.sh"
  chmod -x "$V/system/hooks/memory_capture.sh"
  relocate "$BATS_TEST_TMPDIR/my vault"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  [ ! -e "$CFG/commands/digest.md" ]
}

@test "a backup never overwrites an earlier one from the same second" {
  now="$(date +%s)"
  for t in $(seq "$now" $((now + 3))); do printf 'older %s\n' "$t" > "$SET.bak.$t"; done
  run "$IH"
  [ "$status" -eq 0 ]
  for t in $(seq "$now" $((now + 3))); do [ "$(cat "$SET.bak.$t")" = "older $t" ]; done
  bak="$(sed -n 's/^backup: //p' <<< "$output")"
  [ -f "$bak" ]
  [ "$(jq -S . "$bak")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  [ "$(ls "$CFG" | grep -c 'settings.json.bak')" -eq 5 ]
}
```

- [ ] **Step 2: Run them and watch them fail.** `bats system/tests/hooks_install.bats > system/logs/t1.log 2>&1; echo "exit=$?"; grep 'not ok' system/logs/t1.log`. Expected: `exit=1`, with these four failing:
  - "two JSON documents" (`[ "$status" -eq 1 ]`: the base rewrites `{} {}`);
  - "unexpected shape" (status 5 from a raw `jq` error);
  - "--uninstall works without the hook files…" (`[ "$status" -eq 0 ]`: the base refuses on the missing hook);
  - "a backup never overwrites…" (an `older <t>` backup was overwritten).
  "install refuses a missing or non-executable hook" passes on the base. It closes a test gap, so it is a guard, not a red test.

- [ ] **Step 3: Implement.** Replace `system/scripts/install_hooks.sh` with:

```bash
#!/bin/bash
# Merge Soundwave's memory hooks into the user's Claude Code settings (spec §6.19).
# Touches only owned entries: hook commands under <vault>/system/hooks/memory_*.sh, the three
# absolute vault_index.py allow rules, and a commands/digest.md carrying the managed-by line.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CONFIG_DIR/settings.json"
DIGEST="$CONFIG_DIR/commands/digest.md"
MANAGED="<!-- managed by vault: "

die() { echo "install_hooks: $2" >&2; exit "$1"; }
usage() { die 2 "usage: install_hooks.sh [--dry-run | --uninstall]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  *) usage ;;
esac

# --uninstall is the escape hatch: it needs only jq and the settings file, never the hooks or a plain path.
if [[ "$mode" != uninstall ]]; then
  # Hook commands and Bash allow rules are matched as plain strings, so the vault path must not need quoting.
  [[ "$VAULT_ROOT" =~ ^/[A-Za-z0-9._/@+-]+$ ]] \
    || die 1 "the vault path must not contain spaces or shell metacharacters: $VAULT_ROOT"
  for h in memory_recall.sh memory_capture.sh memory_activity.sh; do
    [[ -x "system/hooks/$h" ]] || die 1 "missing or not executable: system/hooks/$h"
  done
fi

refuse() { die 1 "$SETTINGS $1; fix it by hand first (nothing was changed)"; }
current='{}'
if [[ -e "$SETTINGS" ]]; then
  current="$(cat -- "$SETTINGS")"
  # Slurped, so "{} {}" (two documents) is refused instead of passing a per-document check.
  jq -s -e 'length == 1 and (.[0] | type) == "object"' <<< "$current" > /dev/null 2>&1 \
    || refuse "is not a single JSON object"
fi

# The merge writes into these four containers; anything else in their place is refused up front.
SHAPE='
  [ ([["hooks"], "object"], [["hooks", "SessionStart"], "array"], [["hooks", "Stop"], "array"],
     [["hooks", "PostToolUse"], "array"], [["permissions"], "object"], [["permissions", "allow"], "array"]) as [$p, $t]
    | (try getpath($p) catch null) as $x
    | select($x != null and ($x | type) != $t) | $p | join(".") ] | join(", ")'
if [[ "$mode" != uninstall ]]; then
  bad="$(jq -r "$SHAPE" <<< "$current")"
  [[ -z "$bad" ]] || refuse "has an unexpected shape at: $bad (hooks and permissions must be objects, hook events and allow arrays)"
fi

# Owned = ours from any vault location, so moving the vault re-points the entries instead of duplicating them.
STRIP='
  def owned_cmd: type == "string" and test("/system/hooks/memory_(recall|capture|activity)\\.sh$");
  def owned_allow: type == "string" and test("^Bash\\(/.*/system/scripts/vault_index\\.py (related|show|backlinks):\\*\\)$");
  def has_owned: type == "object" and (.hooks | type) == "array" and any(.hooks[]; type == "object" and (.command | owned_cmd));
  # Only containers that held an owned element are pruned; foreign empty ones are left as found.
  (if (.hooks | type) == "object" then
     ([.hooks[] | select(type == "array") | .[] | select(has_owned)] | length > 0) as $had
     | .hooks |= with_entries(
         if (.value | type) == "array" then
           (.value | any(.[]; has_owned)) as $held
           | .value |= map(if has_owned then (.hooks |= map(select((type == "object" and (.command | owned_cmd)) | not))) | select((.hooks | length) > 0) else . end)
           | select(($held | not) or (.value | length) > 0)
         else . end)
     | if $had and .hooks == {} then del(.hooks) else . end
   else . end)
  | (if (.permissions | type) == "object" and (.permissions.allow | type) == "array" then
       (.permissions.allow | any(.[]; owned_allow)) as $held
       | .permissions.allow |= map(select(owned_allow | not))
       # An emptied allow array is indistinguishable from a foreign empty one, so it is dropped only
       # when it was the sole permissions key (the shape a fresh install creates); otherwise it stays.
       | if $held and .permissions.allow == [] and (.permissions | keys) == ["allow"] then del(.permissions) else . end
     else . end)'
ADD='
  .hooks.SessionStart = ((.hooks.SessionStart // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_recall.sh"), timeout: 5}]}])
  | .hooks.Stop = ((.hooks.Stop // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_capture.sh"), timeout: 10}]}])
  | .hooks.PostToolUse = ((.hooks.PostToolUse // []) + [{matcher: "Edit|Write|MultiEdit|NotebookEdit|Bash",
      hooks: [{type: "command", command: ($v + "/system/hooks/memory_activity.sh"), timeout: 5}]}])
  | .permissions.allow = ((.permissions.allow // []) + [
      "Bash(" + $v + "/system/scripts/vault_index.py related:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py show:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py backlinks:*)"])'
if [[ "$mode" == uninstall ]]; then
  new="$(jq "$STRIP" <<< "$current" 2> /dev/null)" || refuse "could not be read for the uninstall"
else
  new="$(jq --arg v "$VAULT_ROOT" "$STRIP | $ADD" <<< "$current" 2> /dev/null)" || refuse "could not be merged"
fi
jq -e 'type == "object"' <<< "$new" > /dev/null || die 1 "the merged settings did not parse; nothing was changed"

digest_body() {
  printf -- '---\ndescription: Write a Jarvis session digest of the work since the last one.\n---\n%s%s -->\n\n' "$MANAGED" "$VAULT_ROOT"
  cat system/hooks/digest_instructions.md
}
digest_owned() { [[ -f "$DIGEST" ]] && grep -qF -- "$MANAGED" "$DIGEST"; }
if [[ "$mode" == uninstall ]]; then
  if digest_owned; then digest_action=remove; else digest_action=none; fi
elif [[ ! -e "$DIGEST" ]]; then
  digest_action=new
elif ! digest_owned; then
  digest_action=foreign
elif [[ "$(cat -- "$DIGEST")" == "$(digest_body)" ]]; then
  digest_action=unchanged
else
  digest_action=changed
fi

if [[ "$(jq -S . <<< "$current")" == "$(jq -S . <<< "$new")" ]]; then settings_action=unchanged; else settings_action=changed; fi

if [[ "$mode" == dry ]]; then
  diff -u --label "$SETTINGS (current)" --label "$SETTINGS (after install)" \
    <(jq -S . <<< "$current") <(jq -S . <<< "$new") || true
  echo "settings: $settings_action (dry run, nothing written)"
  case "$digest_action" in
    foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault) (dry run, nothing written)" ;;
    remove) echo "digest command: removed (dry run, nothing written)" ;;
    *) echo "digest command: $digest_action (dry run, nothing written)" ;;
  esac
  exit 0
fi

if [[ "$settings_action" == changed ]]; then
  mkdir -p -- "$CONFIG_DIR"
  if [[ -e "$SETTINGS" ]]; then
    # Never overwrite an earlier backup: an install and an uninstall can land in the same second.
    stamp="$(date +%s)"
    bak="$SETTINGS.bak.$stamp"
    n=1
    while [[ -e "$bak" ]]; do bak="$SETTINGS.bak.$stamp.$n"; n=$((n + 1)); done
    cp -p -- "$SETTINGS" "$bak"
    echo "backup: $bak"
  fi
  if [[ -L "$SETTINGS" ]]; then
    jq . <<< "$new" > "$SETTINGS"  # write through a symlink (dotfile managers), keeping the link
  else
    tmp="$SETTINGS.tmp.$$"
    ( umask 077; jq . <<< "$new" > "$tmp" )  # settings often hold env secrets: never wider than the original
    [[ -e "$SETTINGS" ]] && chmod --reference="$SETTINGS" -- "$tmp"
    mv -f -- "$tmp" "$SETTINGS"
  fi
fi
echo "settings: $settings_action"

case "$digest_action" in
  new|changed) mkdir -p -- "$(dirname "$DIGEST")"; digest_body > "$DIGEST"; echo "digest command: $digest_action" ;;
  remove) rm -f -- "$DIGEST"; echo "digest command: removed" ;;
  foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault)" ;;
  *) echo "digest command: $digest_action" ;;
esac
```

- [ ] **Step 4: Run them and watch them pass.** `bats system/tests/hooks_install.bats > system/logs/t1.log 2>&1; echo "exit=$?"`. Expected: `exit=0`, 22 tests.

- [ ] **Step 5: Commit.** `git add system/scripts/install_hooks.sh system/tests/hooks_install.bats && git commit -m "fix(soundwave): install_hooks refuses unmergeable settings, uninstall needs no hook files, backups never overwrite"`

---

### Task 2: `install_hooks.sh` records the containers it created

**Files:**
- Modify: `system/scripts/install_hooks.sh`
- Test: `system/tests/hooks_install.bats`

**Interfaces:**
- Consumes: Task 1's installer (`refuse`, the shape check, the `backup:` line).
- Produces:
  - `system/logs/memory/install_hooks.json`, a JSON object mapping each settings path (the `$SETTINGS` string) to the list of key paths the last install created, in this order: `["hooks"]`, `["hooks","SessionStart"]`, `["hooks","Stop"]`, `["hooks","PostToolUse"]`, `["permissions"]`, `["permissions","allow"]`;
  - each install rewrites its entry, `--uninstall` deletes it, and `--dry-run` never writes it.
  - Nothing else reads the record.

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/hooks_install.bats`:

```bash
record() { jq -c --arg k "$SET" '.[$k]' "$V/system/logs/memory/install_hooks.json"; }

@test "permissions without an allow list come back without one after install and uninstall" {
  printf '%s\n' '{"permissions": {"deny": ["Read(~/.ssh/**)"], "defaultMode": "default"}}' > "$SET"
  jq -S . "$SET" > "$BATS_TEST_TMPDIR/fixture.json"
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(cat "$BATS_TEST_TMPDIR/fixture.json")" ]
}

@test "foreign empty containers of every kind the installer writes into survive install and uninstall" {
  for doc in '{"hooks": {}}' '{"permissions": {}}' '{"hooks": {"Stop": []}}' '{"hooks": {"SessionStart": [], "PostToolUse": []}, "permissions": {"allow": []}}'; do
    printf '%s\n' "$doc" > "$SET"
    run "$IH"
    [ "$status" -eq 0 ]
    [ "$(ours | wc -l)" -eq 3 ]
    run "$IH" --uninstall
    [ "$status" -eq 0 ]
    [ "$(jq -S . "$SET")" = "$(jq -S . <<< "$doc")" ]
  done
}

@test "the record names exactly the containers the install created, and uninstall drops it" {
  printf '%s\n' '{"hooks": {"Stop": []}, "permissions": {"deny": []}}' > "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(record)" = '[["hooks","SessionStart"],["hooks","PostToolUse"],["permissions","allow"]]' ]
  run "$IH"
  [ "$status" -eq 0 ]
  [ "$(record)" = '[["hooks","SessionStart"],["hooks","PostToolUse"],["permissions","allow"]]' ]
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(record)" = null ]
}

@test "--dry-run writes no record" {
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  [ ! -e "$V/system/logs/memory/install_hooks.json" ]
}

@test "an install made before records existed still uninstalls cleanly" {
  run "$IH"
  [ "$status" -eq 0 ]
  rm "$V/system/logs/memory/install_hooks.json"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(jq -S . "$BATS_TEST_TMPDIR/original.json")" ]
  rm "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  printf 'not json\n' > "$V/system/logs/memory/install_hooks.json"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -c . "$SET")" = '{}' ]
}

@test "a rule the user adds after install keeps its allow list through uninstall" {
  printf '%s\n' '{"permissions": {"deny": []}}' > "$SET"
  run "$IH"
  [ "$status" -eq 0 ]
  jq '.permissions.allow += ["Bash(make test)"]' "$SET" > "$SET.new"
  mv "$SET.new" "$SET"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -c .permissions "$SET")" = '{"deny":[],"allow":["Bash(make test)"]}' ]
}

@test "a vault moved after install still uninstalls exactly" {
  printf '%s\n' '{"permissions": {"deny": []}, "hooks": {"Stop": []}}' > "$SET"
  jq -S . "$SET" > "$BATS_TEST_TMPDIR/fixture.json"
  run "$IH"
  [ "$status" -eq 0 ]
  relocate "$BATS_TEST_TMPDIR/moved"
  run "$IH" --uninstall
  [ "$status" -eq 0 ]
  [ "$(jq -S . "$SET")" = "$(cat "$BATS_TEST_TMPDIR/fixture.json")" ]
}
```

- [ ] **Step 2: Run them and watch them fail.** `bats system/tests/hooks_install.bats > system/logs/t2.log 2>&1; echo "exit=$?"; grep 'not ok' system/logs/t2.log`. Expected `exit=1`, with these failing:
  - "permissions without an allow list…" (the base leaves `"allow": []`);
  - "foreign empty containers of every kind…" (the base drops a foreign `{}` or `[]`);
  - "the record names exactly…" (no record file);
  - "an install made before records existed…" (`rm` of the missing record);
  - "a vault moved after install…" (the base leaves `"allow": []`).
  "a rule the user adds after install…" and "--dry-run writes no record" pass on the base. They guard D3 and the dry run.

- [ ] **Step 3: Implement.** Replace `system/scripts/install_hooks.sh` with:

```bash
#!/bin/bash
# Merge Soundwave's memory hooks into the user's Claude Code settings (spec §6.19).
# Touches only owned entries: hook commands under <vault>/system/hooks/memory_*.sh, the three
# absolute vault_index.py allow rules, and a commands/digest.md carrying the managed-by line.
set -euo pipefail
VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$VAULT_ROOT"

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CONFIG_DIR/settings.json"
DIGEST="$CONFIG_DIR/commands/digest.md"
MANAGED="<!-- managed by vault: "
RECORD="system/logs/memory/install_hooks.json"

die() { echo "install_hooks: $2" >&2; exit "$1"; }
usage() { die 2 "usage: install_hooks.sh [--dry-run | --uninstall]"; }
(( $# <= 1 )) || usage
case "${1:-}" in
  "") mode=install ;;
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  *) usage ;;
esac

# --uninstall is the escape hatch: it needs only jq and the settings file, never the hooks or a plain path.
if [[ "$mode" != uninstall ]]; then
  # Hook commands and Bash allow rules are matched as plain strings, so the vault path must not need quoting.
  [[ "$VAULT_ROOT" =~ ^/[A-Za-z0-9._/@+-]+$ ]] \
    || die 1 "the vault path must not contain spaces or shell metacharacters: $VAULT_ROOT"
  for h in memory_recall.sh memory_capture.sh memory_activity.sh; do
    [[ -x "system/hooks/$h" ]] || die 1 "missing or not executable: system/hooks/$h"
  done
fi

refuse() { die 1 "$SETTINGS $1; fix it by hand first (nothing was changed)"; }
current='{}'
if [[ -e "$SETTINGS" ]]; then
  current="$(cat -- "$SETTINGS")"
  # Slurped, so "{} {}" (two documents) is refused instead of passing a per-document check.
  jq -s -e 'length == 1 and (.[0] | type) == "object"' <<< "$current" > /dev/null 2>&1 \
    || refuse "is not a single JSON object"
fi

# The merge writes into these four containers; anything else in their place is refused up front.
SHAPE='
  [ ([["hooks"], "object"], [["hooks", "SessionStart"], "array"], [["hooks", "Stop"], "array"],
     [["hooks", "PostToolUse"], "array"], [["permissions"], "object"], [["permissions", "allow"], "array"]) as [$p, $t]
    | (try getpath($p) catch null) as $x
    | select($x != null and ($x | type) != $t) | $p | join(".") ] | join(", ")'
if [[ "$mode" != uninstall ]]; then
  bad="$(jq -r "$SHAPE" <<< "$current")"
  [[ -z "$bad" ]] || refuse "has an unexpected shape at: $bad (hooks and permissions must be objects, hook events and allow arrays)"
fi

# The containers an install may have to create. Those it did create are recorded per settings file in
# $RECORD, so --uninstall removes exactly them and leaves a container the user already had, even an empty one.
LIB='
  def containers: [["hooks"], ["hooks", "SessionStart"], ["hooks", "Stop"], ["hooks", "PostToolUse"],
                   ["permissions"], ["permissions", "allow"]];
  def at($p): try getpath($p) catch null;'
# Owned = ours from any vault location, so moving the vault re-points the entries instead of duplicating them.
STRIP='
  def owned_cmd: type == "string" and test("/system/hooks/memory_(recall|capture|activity)\\.sh$");
  def owned_allow: type == "string" and test("^Bash\\(/.*/system/scripts/vault_index\\.py (related|show|backlinks):\\*\\)$");
  def has_owned: type == "object" and (.hooks | type) == "array" and any(.hooks[]; type == "object" and (.command | owned_cmd));
  def holds_owned: [.. | strings | select(owned_cmd or owned_allow)] | length > 0;
  . as $before
  | (if (.hooks | type) == "object" then
       .hooks |= with_entries(
         if (.value | type) == "array" then
           .value |= map(if has_owned then (.hooks |= map(select((type == "object" and (.command | owned_cmd)) | not))) | select((.hooks | length) > 0) else . end)
         else . end)
     else . end)
  | (if (.permissions | type) == "object" and (.permissions.allow | type) == "array" then
       .permissions.allow |= map(select(owned_allow | not))
     else . end)
  # No record (an install made before records existed): every hooks container counts as created, and an
  # emptied allow array only when it is the sole permissions key, the shape a fresh install creates.
  | ((.permissions | type) == "object" and (.permissions | keys) == ["allow"]) as $sole
  | (if $created == null then [containers[] | select(.[0] == "hooks" or $sole)] else $created end) as $prune
  # A container is removed only if it was created, held an owned entry before, and is empty now; deepest first.
  | reduce ($prune | sort_by(-length))[] as $p (.;
      if (($before | at($p)) | holds_owned) and (at($p) == [] or at($p) == {}) then delpaths([$p]) else . end)'
ADD='
  .hooks.SessionStart = ((.hooks.SessionStart // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_recall.sh"), timeout: 5}]}])
  | .hooks.Stop = ((.hooks.Stop // []) + [{hooks: [{type: "command", command: ($v + "/system/hooks/memory_capture.sh"), timeout: 10}]}])
  | .hooks.PostToolUse = ((.hooks.PostToolUse // []) + [{matcher: "Edit|Write|MultiEdit|NotebookEdit|Bash",
      hooks: [{type: "command", command: ($v + "/system/hooks/memory_activity.sh"), timeout: 5}]}])
  | .permissions.allow = ((.permissions.allow // []) + [
      "Bash(" + $v + "/system/scripts/vault_index.py related:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py show:*)",
      "Bash(" + $v + "/system/scripts/vault_index.py backlinks:*)"])'
CREATED='[containers[] as $p | select(at($p) == null) | $p]'

# This settings file's record, or null when there is none or it is not a list of key paths.
created=null
if [[ -f "$RECORD" ]]; then
  created="$(jq -c --arg k "$SETTINGS" '(.[$k] // null) as $c
    | if ($c | type) == "array" and all($c[]; type == "array" and all(.[]; type == "string")) then $c else null end' \
    "$RECORD" 2> /dev/null)" || created=null
fi

stripped="$(jq --argjson created "$created" "$LIB $STRIP" <<< "$current" 2> /dev/null)" \
  || refuse "could not be read"
if [[ "$mode" == uninstall ]]; then
  new="$stripped"
else
  now_created="$(jq -c "$LIB $CREATED" <<< "$stripped")"
  new="$(jq --arg v "$VAULT_ROOT" "$ADD" <<< "$stripped" 2> /dev/null)" || refuse "could not be merged"
fi
jq -e 'type == "object"' <<< "$new" > /dev/null || die 1 "the merged settings did not parse; nothing was changed"

digest_body() {
  printf -- '---\ndescription: Write a Jarvis session digest of the work since the last one.\n---\n%s%s -->\n\n' "$MANAGED" "$VAULT_ROOT"
  cat system/hooks/digest_instructions.md
}
digest_owned() { [[ -f "$DIGEST" ]] && grep -qF -- "$MANAGED" "$DIGEST"; }
if [[ "$mode" == uninstall ]]; then
  if digest_owned; then digest_action=remove; else digest_action=none; fi
elif [[ ! -e "$DIGEST" ]]; then
  digest_action=new
elif ! digest_owned; then
  digest_action=foreign
elif [[ "$(cat -- "$DIGEST")" == "$(digest_body)" ]]; then
  digest_action=unchanged
else
  digest_action=changed
fi

if [[ "$(jq -S . <<< "$current")" == "$(jq -S . <<< "$new")" ]]; then settings_action=unchanged; else settings_action=changed; fi

if [[ "$mode" == dry ]]; then
  diff -u --label "$SETTINGS (current)" --label "$SETTINGS (after install)" \
    <(jq -S . <<< "$current") <(jq -S . <<< "$new") || true
  echo "settings: $settings_action (dry run, nothing written)"
  case "$digest_action" in
    foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault) (dry run, nothing written)" ;;
    remove) echo "digest command: removed (dry run, nothing written)" ;;
    *) echo "digest command: $digest_action (dry run, nothing written)" ;;
  esac
  exit 0
fi

if [[ "$settings_action" == changed ]]; then
  mkdir -p -- "$CONFIG_DIR"
  if [[ -e "$SETTINGS" ]]; then
    # Never overwrite an earlier backup: an install and an uninstall can land in the same second.
    stamp="$(date +%s)"
    bak="$SETTINGS.bak.$stamp"
    n=1
    while [[ -e "$bak" ]]; do bak="$SETTINGS.bak.$stamp.$n"; n=$((n + 1)); done
    cp -p -- "$SETTINGS" "$bak"
    echo "backup: $bak"
  fi
  if [[ -L "$SETTINGS" ]]; then
    jq . <<< "$new" > "$SETTINGS"  # write through a symlink (dotfile managers), keeping the link
  else
    tmp="$SETTINGS.tmp.$$"
    ( umask 077; jq . <<< "$new" > "$tmp" )  # settings often hold env secrets: never wider than the original
    [[ -e "$SETTINGS" ]] && chmod --reference="$SETTINGS" -- "$tmp"
    mv -f -- "$tmp" "$SETTINGS"
  fi
fi
echo "settings: $settings_action"

# Keep the record in step with the settings: rewritten on every install, this file's entry dropped on uninstall.
record() {
  local old='{}' tmp="$RECORD.tmp.$$"
  if [[ -f "$RECORD" ]]; then old="$(jq -c 'if type == "object" then . else {} end' "$RECORD" 2> /dev/null)" || old='{}'; fi
  mkdir -p -- "$(dirname "$RECORD")"
  jq --arg k "$SETTINGS" "$@" <<< "$old" > "$tmp"
  mv -f -- "$tmp" "$RECORD"
}
if [[ "$mode" == install ]]; then
  record --argjson c "$now_created" '.[$k] = $c'
elif [[ -f "$RECORD" ]]; then
  record 'del(.[$k])'
fi

case "$digest_action" in
  new|changed) mkdir -p -- "$(dirname "$DIGEST")"; digest_body > "$DIGEST"; echo "digest command: $digest_action" ;;
  remove) rm -f -- "$DIGEST"; echo "digest command: removed" ;;
  foreign) echo "digest command: left alone ($DIGEST exists and is not managed by a vault)" ;;
  *) echo "digest command: $digest_action" ;;
esac
```

- [ ] **Step 4: Run them and watch them pass.** `bats system/tests/hooks_install.bats > system/logs/t2.log 2>&1; echo "exit=$?"`. Expected: `exit=0`, 29 tests.

- [ ] **Step 5: Commit.** `git add system/scripts/install_hooks.sh system/tests/hooks_install.bats && git commit -m "fix(soundwave): install_hooks records the containers it created, so uninstall removes exactly those"`

---

### Task 3: `/setup` phase 5a: memory hooks

**Files:**
- Modify: `.claude/commands/setup.md`
- Test: `system/tests/commands.bats`, `system/tests/hooks_install.bats`

**Interfaces:**
- Consumes: the installer's output lines. `--dry-run` prints a unified diff, then `settings: <changed|unchanged> (dry run, nothing written)` and `digest command: <new|changed|unchanged|left alone (…)> (dry run, nothing written)`. A real run prints `backup: <path>` (when a file existed), `settings: …` and `digest command: …`.
- Produces: the `## 5a. Memory hooks` phase between `## 5. Units` and `## 6. Calendar`, and `memory hooks` in the phase 10 report. It also produces the helper `setup_section <heading>` in `commands.bats`, which Task 4 uses: it prints the body of one `## <heading>` phase of `setup.md`.

- [ ] **Step 1: Write the failing tests.** In `system/tests/commands.bats`, replace the whole test `@test "/setup detects remotes before changing them and installs no memory hooks" { … }` with:

```bash
# setup_section <heading>: the body of one "## <heading>" phase of setup.md.
setup_section() { awk -v h="## $1" '$0 == h { on = 1; next } /^## / { on = 0 } on' .claude/commands/setup.md; }

@test "/setup detects remotes before changing them" {
  text="$(cat .claude/commands/setup.md)"
  [[ "$text" == *'setup_remote.sh --detect'* ]]
  [[ "$text" == *'setup_remote.sh <url>'* ]]
  before_detect="${text%%setup_remote.sh --detect*}"
  before_act="${text%%setup_remote.sh <url>*}"
  [ "${#before_detect}" -lt "${#before_act}" ]
  grep -qF 'system/scripts/install_units.sh --dry-run' .claude/commands/setup.md
}

@test "/setup phase 5a shows the hooks dry run, explains it, and installs only on an explicit yes" {
  f=.claude/commands/setup.md
  [ "$(grep -E '^## (5|5a|6)\. ' "$f" | tr '\n' '|')" = '## 5. Units|## 5a. Memory hooks|## 6. Calendar|' ]
  sec="$(setup_section '5a. Memory hooks')"
  for s in memory_recall.sh memory_capture.sh memory_activity.sh '`/digest`' 'left alone' \
      'act only inside the vault and the registered codebases' 'Stop hook error: Jarvis memory (not an error)' \
      'It is not an error.' 'Only an explicit yes installs.' 'memory capture stays off' \
      'settings: unchanged (dry run, nothing written)' 'digest command: unchanged (dry run, nothing written)' \
      'system/scripts/install_hooks.sh --uninstall'; do
    [[ "$sec" == *"$s"* ]]
  done
  before_dry="${sec%%system/scripts/install_hooks.sh --dry-run*}"
  before_install="${sec%%run \`system/scripts/install_hooks.sh\` and report*}"
  [ "${#before_dry}" -lt "${#before_install}" ]
  [ "${#before_install}" -lt "${#sec}" ]
  # Nothing outside phase 5a runs the installer.
  [ "$(grep -o 'install_hooks' "$f" | wc -l)" -eq "$(grep -o 'install_hooks' <<< "$sec" | wc -l)" ]
  run grep -n 'not part of this version of setup' "$f"
  [ "$status" -eq 1 ]
  grep -qF 'linger, memory hooks, calendar' "$f"
}
```

Append to `system/tests/hooks_install.bats` (a contract pin for the two lines 5a reads):

```bash
@test "after an install, --dry-run prints the two lines /setup reads as already installed" {
  run "$IH"
  [ "$status" -eq 0 ]
  run "$IH" --dry-run
  [ "$status" -eq 0 ]
  grep -qx 'settings: unchanged (dry run, nothing written)' <<< "$output"
  grep -qx 'digest command: unchanged (dry run, nothing written)' <<< "$output"
}
```

- [ ] **Step 2: Run them and watch them fail.** `bats system/tests/commands.bats system/tests/hooks_install.bats > system/logs/t3.log 2>&1; echo "exit=$?"; grep 'not ok' system/logs/t3.log`. Expected: `exit=1`. Only "/setup phase 5a shows the hooks dry run…" fails, at the heading-order line, because there is no `## 5a.` yet. The `hooks_install.bats` pin passes on the base: it pins existing output that `/setup` now depends on.

- [ ] **Step 3: Implement.** In `.claude/commands/setup.md`:
  - Replace the line `Memory capture (session digests and recall) is not part of this version of setup; it arrives in a later release and will be added here.` with the block below. Keep the blank line that follows it, before `## 6. Calendar`.
  - In `## 10. Report`, replace `(config, each codebase, remote mode, each unit, linger, calendar, index, verification)` with `(config, each codebase, remote mode, each unit, linger, memory hooks, calendar, index, verification)`.

````markdown
## 5a. Memory hooks
Memory (Soundwave) is optional and stays off until its hooks are installed in your user-level Claude Code settings. Ask nothing until you have shown the dry run.

1. Run `system/scripts/install_hooks.sh --dry-run`. If it exits non-zero, show its message, say memory stays off, and go on to phase 6. Otherwise show its output unchanged: the diff to your user settings (`~/.claude/settings.json`, or `$CLAUDE_CONFIG_DIR/settings.json` when that is set) and its `settings:` and `digest command:` lines.
2. If it prints both `settings: unchanged (dry run, nothing written)` and `digest command: unchanged (dry run, nothing written)`, the hooks are already installed: say so, mention that `system/scripts/install_hooks.sh --uninstall` removes them, and go on to phase 6.
3. Explain each entry in the diff, in these words or close to them:
   - `memory_recall.sh` (SessionStart): when a session starts in the vault or in a registered codebase, it adds recent session digests for that codebase or partition, up to `recall_budget_chars` characters, marked as vault data, not instructions.
   - `memory_capture.sh` (Stop): after at least `digest_min_events` tool events and `digest_min_minutes` minutes since the last digest, it asks Claude for a short digest of the session, then redacts it and writes it to `raw/<partition>/notes/` for intake to compile. It asks at most once in a row, and not when Claude's last reply ended with a question to you.
   - `memory_activity.sh` (PostToolUse on edits and Bash): counts work events for that threshold. It only updates a counter.
   - Three `permissions.allow` rules for `vault_index.py related`, `show` and `backlinks`: the only way a codebase session reads the vault, and it sees only that codebase's partition plus `shared`.
   - `digest.md` in your user commands directory: the `/digest` command, which writes a digest on demand. If the dry run says `left alone`, a `digest.md` that is not managed by a vault already exists; it is kept, and `/digest` stays yours.
4. Say that the hooks run in every Claude Code session on this machine but act only inside the vault and the registered codebases. Everywhere else, and in headless runs, subagents and `claude -p` scripts, they exit at once and do nothing.
5. Explain the label: when the Stop hook asks for a digest, Claude Code shows the request as `Stop hook error: Jarvis memory (not an error): please reply with a short session digest. …`. It is not an error. Claude Code labels every request from a Stop hook that way; Claude replies with the digest and the session carries on.
6. Ask: "Install the memory hooks? (yes/no, default no)". Only an explicit yes installs. On yes, run `system/scripts/install_hooks.sh` and report its `backup:`, `settings:` and `digest command:` lines. On anything else, change nothing and say that memory capture stays off and that re-running `/setup` (or `system/scripts/install_hooks.sh` after reading its `--dry-run`) turns it on later.
````

- [ ] **Step 4: Run them and watch them pass.** `bats system/tests/commands.bats system/tests/hooks_install.bats > system/logs/t3.log 2>&1; echo "exit=$?"`. Expected: `exit=0`. Each of these one-line mutations, applied to the 5a section, must make the 5a test fail. All four were checked while planning:
  - deleting `Only an explicit yes installs.`;
  - changing `Stop hook error: Jarvis` to `Stop hook: Jarvis`;
  - dropping ``run `system/scripts/install_hooks.sh` `` from the yes branch;
  - adding an `install_hooks.sh` call to phase 5.

- [ ] **Step 5: Commit.** `git add .claude/commands/setup.md system/tests/commands.bats system/tests/hooks_install.bats && git commit -m "feat(setup): phase 5a offers the memory hooks from a reviewed dry run, on an explicit yes"`

---

### Task 4: `/setup` minors: config without the example body, current `remote_mode` as the default

**Files:**
- Modify: `.claude/commands/setup.md` (phases 1 and 4)
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: Task 3's `setup_section` helper; `system/config.example.md`, whose frontmatter ends at its second `---` line; `vault_index.py field system/config.md remote_mode`.
- Produces: the exact config-creation command, which the test extracts by the pattern `` `[ -f system/config.md ] …` `` and runs. Its body is exactly `# Config`, a blank line, then `Written by /setup. Re-run /setup to change it.`.

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/commands.bats`:

```bash
@test "/setup creates config.md from the example's frontmatter only, and never over an existing one" {
  cmd="$(grep -oE '`\[ -f system/config\.md \][^`]*`' .claude/commands/setup.md | tr -d '`')"
  [ -n "$cmd" ]
  d="$BATS_TEST_TMPDIR/v"
  mkdir -p "$d/system"
  cp system/config.example.md "$d/system/"
  (cd "$d" && eval "$cmd")
  n="$(awk 'NR > 1 && /^---$/ { print NR; exit }' system/config.example.md)"
  [ "$(head -n "$n" "$d/system/config.md")" = "$(head -n "$n" system/config.example.md)" ]
  [ "$(tail -n +"$((n + 1))" "$d/system/config.md")" = "$(printf '# Config\n\nWritten by /setup. Re-run /setup to change it.')" ]
  printf 'mine\n' > "$d/system/config.md"
  (cd "$d" && eval "$cmd")
  [ "$(cat "$d/system/config.md")" = mine ]
}

@test "/setup offers the current remote_mode as the default before asking" {
  sec="$(setup_section '4. Remote')"
  [[ "$sec" == *'showing the current mode as the default'* ]]
  before_read="${sec%%system/scripts/vault_index.py field system/config.md remote_mode*}"
  before_ask="${sec%%Then ask*}"
  [ "${#before_read}" -lt "${#before_ask}" ]
}
```

- [ ] **Step 2: Run them and watch them fail.** `bats system/tests/commands.bats > system/logs/t4.log 2>&1; echo "exit=$?"; grep 'not ok' system/logs/t4.log`. Expected `exit=1`, with two failures:
  - "/setup creates config.md…" (`[ -n "$cmd" ]`: there is no exact command yet);
  - "/setup offers the current remote_mode…" (the default wording is missing).

- [ ] **Step 3: Implement.** Replace the body of `## 1. Existing config` and of `## 4. Remote` so that `.claude/commands/setup.md` reads, in full:

````markdown
---
description: Interactive onboarding — config interview, codebases, remotes, systemd units, calendar, index and verification. Safe to re-run.
---

You are running Jarvis setup. Every phase is idempotent: show what exists and edit it, never overwrite blindly. Ask one question at a time, show the default, and wait for the answer. Scripts that are not allowlisted will ask the user for permission; that is intended. Run every script as `system/scripts/<name> …` from the vault root.

## 0. Preflight
Run `system/scripts/check_deps.sh`. List every `missing` line with its install hint, and every `optional` line as optional. If `pyyaml` is missing, stop: setup cannot continue without it. Otherwise continue, noting which features are off (no `gcalcli`: no calendar in the brief; no `hyprctl`: no focus tracking).

## 1. Existing config
If `system/config.md` exists, show its values and ask which to change. Otherwise create it from the example's frontmatter, without the example's body text, by running exactly this: `[ -f system/config.md ] || { awk '{ print } NR > 1 && /^---$/ { exit }' system/config.example.md; printf '# Config\n\nWritten by /setup. Re-run /setup to change it.\n'; } > system/config.md`. Use its values as the defaults below.

## 2. Interview
Ask, in order: timezone (default from config; must exist under `/usr/share/zoneinfo`), brief time (`HH:MM`), debrief time (`HH:MM`), superpowers (strategic anchors, one per line), default partition for vault sessions and inbox files (`personal`, `work` or `shared`; default `personal`), digest thresholds (default 5 work events and 20 minutes), recall budget (default 9000 characters, at most 9500).

Write each scalar with `system/scripts/vault_index.py set system/config.md <key> <value>` and the superpowers list by editing the file. Then run `system/scripts/vault_index.py validate system/config.md`; on an error, show it, ask again for that value, and re-validate.

## 3. Codebases
1. Show every existing `system/codebases/*.md` (except `example.md`) and ask whether to edit any. Never replace one.
2. Ask for a directory to scan. Run `system/scripts/discover_codebases.sh <dir>` and show the repos it prints (path, worktrees, remote). Ask which to register.
3. For each chosen repo, run `system/scripts/inspect_codebase.sh <path>` and draft `system/codebases/<name>.md` (name: letters, digits, `.`, `_`, `-`) from the evidence:
   - `type: codebase`, `name`, `path` (written with `~/` when under your home directory), `partition` (default `work`), `default` (`"true"` for at most one codebase), `stack` (from manifest kinds and notable dependencies), `search_globs` (from the most common extensions), `layers` (from `layer_candidates`, e.g. `ui: "web/"`, `api: "Api/"`).
   - In the body: conventions and owners you learn from the user.
   Confirm each field with the user, write the file, and run `system/scripts/vault_index.py validate system/codebases/<name>.md`.
4. Ask "add another directory?" and repeat until no.
5. Add every registered codebase path (expanded, absolute) to `permissions.additionalDirectories` in `.claude/settings.local.json`, keeping everything else in that file and the existing order. Run exactly this, with the paths in place of `<paths…>`: `[ -f .claude/settings.local.json ] || echo '{}' > .claude/settings.local.json; jq '.permissions.additionalDirectories = ((.permissions.additionalDirectories // []) + ($ARGS.positional - (.permissions.additionalDirectories // [])))' .claude/settings.local.json --args <paths…> > .claude/settings.local.json.tmp && jq -e 'type == "object"' .claude/settings.local.json.tmp > /dev/null && mv .claude/settings.local.json.tmp .claude/settings.local.json`

## 4. Remote
Run `system/scripts/setup_remote.sh --detect` and report what it found. Read the current mode with `system/scripts/vault_index.py field system/config.md remote_mode`. Then ask, showing the current mode as the default: a private URL for your vault (`private`), no remote (`none`), or keep the remotes as they are (`keep`, for template maintainers; choose this when `origin` is the template and you maintain it). If the current mode is `private`, show the current `origin` URL (`git remote get-url origin`) as the default URL. Run `system/scripts/setup_remote.sh <url>`, `--none` or `--keep` and report its output.

## 5. Units
Run `system/scripts/install_units.sh --dry-run` and summarize the units: `jarvis-intake` (every 5 minutes), `jarvis-brief` and `jarvis-debrief` (at the configured times), `jarvis-focus` (the focus tracker). Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged` line.

Then run `loginctl show-user "$USER" -p Linger --value`. If it prints `no`, explain that timers only run while you are logged in, and offer `loginctl enable-linger "$USER"` (the user runs it).

## 5a. Memory hooks
Memory (Soundwave) is optional and stays off until its hooks are installed in your user-level Claude Code settings. Ask nothing until you have shown the dry run.

1. Run `system/scripts/install_hooks.sh --dry-run`. If it exits non-zero, show its message, say memory stays off, and go on to phase 6. Otherwise show its output unchanged: the diff to your user settings (`~/.claude/settings.json`, or `$CLAUDE_CONFIG_DIR/settings.json` when that is set) and its `settings:` and `digest command:` lines.
2. If it prints both `settings: unchanged (dry run, nothing written)` and `digest command: unchanged (dry run, nothing written)`, the hooks are already installed: say so, mention that `system/scripts/install_hooks.sh --uninstall` removes them, and go on to phase 6.
3. Explain each entry in the diff, in these words or close to them:
   - `memory_recall.sh` (SessionStart): when a session starts in the vault or in a registered codebase, it adds recent session digests for that codebase or partition, up to `recall_budget_chars` characters, marked as vault data, not instructions.
   - `memory_capture.sh` (Stop): after at least `digest_min_events` tool events and `digest_min_minutes` minutes since the last digest, it asks Claude for a short digest of the session, then redacts it and writes it to `raw/<partition>/notes/` for intake to compile. It asks at most once in a row, and not when Claude's last reply ended with a question to you.
   - `memory_activity.sh` (PostToolUse on edits and Bash): counts work events for that threshold. It only updates a counter.
   - Three `permissions.allow` rules for `vault_index.py related`, `show` and `backlinks`: the only way a codebase session reads the vault, and it sees only that codebase's partition plus `shared`.
   - `digest.md` in your user commands directory: the `/digest` command, which writes a digest on demand. If the dry run says `left alone`, a `digest.md` that is not managed by a vault already exists; it is kept, and `/digest` stays yours.
4. Say that the hooks run in every Claude Code session on this machine but act only inside the vault and the registered codebases. Everywhere else, and in headless runs, subagents and `claude -p` scripts, they exit at once and do nothing.
5. Explain the label: when the Stop hook asks for a digest, Claude Code shows the request as `Stop hook error: Jarvis memory (not an error): please reply with a short session digest. …`. It is not an error. Claude Code labels every request from a Stop hook that way; Claude replies with the digest and the session carries on.
6. Ask: "Install the memory hooks? (yes/no, default no)". Only an explicit yes installs. On yes, run `system/scripts/install_hooks.sh` and report its `backup:`, `settings:` and `digest command:` lines. On anything else, change nothing and say that memory capture stays off and that re-running `/setup` (or `system/scripts/install_hooks.sh` after reading its `--dry-run`) turns it on later.

## 6. Calendar
Run `timeout 20 gcalcli list < /dev/null`. If it fails, tell the user to run `! gcalcli init` and re-run this phase afterwards.

## 7. Index
Run `system/scripts/vault_index.py rebuild`, then `system/scripts/vault_index.py issues`, and report any error.

## 8. Verify
Run `system/scripts/verify_setup.sh --health` and `systemctl --user list-timers 'jarvis-*'`. Report each suite's PASS/FAIL line and the next run time of each timer. Health failures are advisory.

## 9. Hand-off
For each registered codebase without one, create `wiki/<partition>/concepts/<Name>OnboardingAssignment.md`, where `<partition>` is the codebase's partition and `<Name>` its name in PascalCase. Frontmatter: `type: concept`, `tags: ["onboarding"]`, `compiled_at` today, `partition`, `codebase`, `agent_owner: CodingAgent`, `status: draft`. Body: direct **CodingAgent** to map the codebase's layers and its logging and telemetry definitions (start from the `logging_hints` the inspection found) into `wiki/<partition>/entities/<Name>LogEventMap.md`; link `[[Index]]` and name each superpower the work serves. Run `system/scripts/lint_vault.sh` afterwards.

## 10. Report
Show a table of every item set up (config, each codebase, remote mode, each unit, linger, memory hooks, calendar, index, verification) with its status. Remind the user to install the Obsidian **Dataview** plugin for the `wiki/Index.md` dashboards, and that `system/scripts/update_template.sh` pulls template updates.
````

- [ ] **Step 4: Run them and watch them pass.** `bats system/tests/commands.bats > system/logs/t4.log 2>&1; echo "exit=$?"`. Expected: `exit=0`, 15 tests.

- [ ] **Step 5: Commit.** `git add .claude/commands/setup.md system/tests/commands.bats && git commit -m "fix(setup): new config carries no example body; offer the current remote_mode as the default"`

---

### Task 5: README memory sections

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–4's behavior: the `backup:` line, uninstall without hook files, the record, and the 5a flow.
- Produces: a `## Memory (Soundwave)` section (anchor `#memory-soundwave`), linked from How it works and Getting started. Task 8 sets the 4b row to Complete.

- [ ] **Step 1: Apply these replacements.** Every `old` string must exist exactly once in `README.md`; stop if one does not.
  - Replace the line:

    ```text
    > **Status:** built and tested. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)); `/setup` and the installed systemd units have not yet been run end to end. Memory capture and recall (Plan 3) are not built yet; `/setup` skips that step for now.
    ```

    with:

    ```text
    > **Status:** built and tested. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)); `/setup` and the installed systemd units have not yet been run end to end. Memory capture and recall (Plan 3) passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md)) and stay off until you install their hooks, which `/setup` offers.
    ```

  - Replace the line:

    ```text
    | 3. Memory (Soundwave) | Capture/recall hooks, hook installer, `/digest` | Pending |
    ```

    with:

    ```text
    | 3. Memory (Soundwave) | Capture/recall hooks, hook installer, `/digest` | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-3-memory.md), [acceptance](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md) |
    ```

  - Replace the line:

    ```text
    | 4b. Memory integration, renames | `/setup` memory step, README memory sections, final renames | Pending (after Plan 3) |
    ```

    with:

    ```text
    | 4b. Memory integration, renames | `/setup` memory step, README memory sections, final renames | In progress: [plan](docs/superpowers/plans/2026-10-02-plan-4b-memory-integration.md) |
    ```

  - Replace the line:

    ```text
    1. **Capture.** Files you drop in go to `raw/inbox/`. In the vault and in registered codebases, a `Stop` hook asks for a short session digest once enough work has happened (default: 5 tool events and 20 minutes). The hook writes the digest, redacted, to `raw/<partition>/notes/`. `/digest` writes one on demand. Claude Code shows a Stop hook's request under the label "Stop hook error:"; for Jarvis that line starts with "Jarvis memory (not an error)" and simply asks for the digest.
    ```

    with:

    ```text
    1. **Capture.** Files you drop in go to `raw/inbox/`. Once the memory hooks are installed, sessions in the vault and in registered codebases also leave short, redacted session digests in `raw/<partition>/notes/` (see [Memory](#memory-soundwave) below).
    ```

  - Replace the line:

    ```text
    5. **Recall.** A `SessionStart` hook adds up to about 9,500 characters of vault data to new sessions in scope: the latest digests for the codebase or partition and, once enabled, preferences you have confirmed. Recalled text is marked as data, not instructions.
    ```

    with:

    ```text
    5. **Recall.** With the memory hooks installed, a `SessionStart` hook adds up to about 9,500 characters of vault data to new sessions in scope: the latest digests for the codebase or partition and, once enabled, preferences you have confirmed. Recalled text is marked as data, not instructions.
    ```

  - Replace the line:

    ```text
    The layout, abbreviated from spec §5. `system/hooks/`, `install_hooks.sh` and `/digest` arrive with Plan 3.
    ```

    with:

    ```text
    The layout, abbreviated from spec §5. `/digest` is not in the repo: it is a user-level command that `install_hooks.sh` writes to `~/.claude/commands/digest.md`, so it works in codebase sessions too.
    ```

  - Replace the line:

    ```text
    .claude/commands/             setup brief debrief ingest query lint backup impact digest
    ```

    with:

    ```text
    .claude/commands/             setup brief debrief ingest query lint backup impact
    ```

  - Replace the line:

    ```text
    6. **Memory hooks** (optional, arrives with Plan 3): you will be shown the diff to `~/.claude/settings.json`, and it will be applied only after an explicit yes. Setup skips this step for now.
    ```

    with:

    ```text
    6. **Memory hooks** (optional): you are shown the diff to `~/.claude/settings.json` and what each hook does, and it is applied only after an explicit yes. Declining leaves memory off (see [Memory](#memory-soundwave)).
    ```

  - Replace the line:

    ```text
    - **Remove memory hooks** (after Plan 3): `system/scripts/install_hooks.sh --uninstall` removes only the entries owned by this vault and the owned `/digest` command.
    ```

    with:

    ```text
    - **Remove memory hooks:** `system/scripts/install_hooks.sh --uninstall` removes only the entries owned by this vault, any container the install had to create, and the owned `/digest` command. It still works if the hook files are gone.
    ```
  - Insert this section directly before `## Repository layout`, followed by one blank line:

```markdown
## Memory (Soundwave)

Memory is optional and off until you install its hooks. `/setup` offers them in its memory step: it shows the change `system/scripts/install_hooks.sh --dry-run` would make to your user-level `~/.claude/settings.json`, explains each entry, and installs only after an explicit yes. Declining leaves memory off; re-run `/setup` to turn it on later.

| Entry | What it does |
|---|---|
| `memory_recall.sh` (`SessionStart`) | Adds recent digests for the codebase or partition to a new session, up to `recall_budget_chars` (default 9,000 characters), marked as vault data, not instructions |
| `memory_capture.sh` (`Stop`) | After enough work (`digest_min_events` tool events and `digest_min_minutes` minutes since the last digest, default 5 and 20), asks for a short digest once, then redacts it and writes it to `raw/<partition>/notes/` |
| `memory_activity.sh` (`PostToolUse`) | Counts edits and Bash calls toward that threshold |
| three `permissions.allow` rules | Let codebase sessions run `vault_index.py related`, `show` and `backlinks`, which return only that codebase's partition plus `shared` |
| `~/.claude/commands/digest.md` | The `/digest` command, written only if you have no `digest.md` of your own |

The hooks run in every Claude Code session on the machine but act only inside the vault and registered codebases. Headless runs, subagents and `claude -p` scripts are skipped.

**"Stop hook error" is not an error.** Claude Code labels every request from a `Stop` hook "Stop hook error:". When Jarvis asks for a digest, you see `Stop hook error: Jarvis memory (not an error): please reply with a short session digest. …`; Claude replies with the digest and the session carries on. The hook never asks twice in a row, and not when Claude's last reply ended with a question to you.

**`/digest`** writes a digest of the work since the last one whenever you want, in any session in scope. The `Stop` hook captures it from the reply; no script or session id is needed.
```

- [ ] **Step 2: Verify.** Run the lint (Global Constraints). Expected: `lint exit=0` and `0 errors`. The new 4b plan link resolves because this plan is committed.

- [ ] **Step 3: Commit.** `git add README.md && git commit -m "docs: README memory section, Stop hook label, /digest, and Plan 3 complete"`

---

### Task 6: §15 rename (the final code commit)

**Files:**
- Rename: `system/agents/ChiefOfStaff.md` → `system/agents/Optimus.md`
- Modify: `CLAUDE.md` (the Agents line only), `README.md` (one table header)
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: nothing new.
- Produces: `system/agents/Optimus.md` (content unchanged). No template-owned file names the old file. Nothing loads the persona by path except `CLAUDE.md`'s Agents line. `brief.md` and `debrief.md` already say "You are **Optimus**".

- [ ] **Step 1: Write the failing test.** Append to `system/tests/commands.bats`:

```bash
@test "personas carry their §15 names and nothing names the old Chief of Staff file" {
  [ "$(cd system/agents && LC_ALL=C ls | tr '\n' ' ')" = 'CodingAgent.md Optimus.md SystemMaintenance.md ' ]
  grep -qx '# Role Profile: Optimus (Chief of Staff)' system/agents/Optimus.md
  grep -qF 'Persona: `system/agents/Optimus.md`.' CLAUDE.md
  # The [C] bracket keeps the pattern from matching this line.
  run git grep -nE '[C]hiefOfStaff' -- CLAUDE.md README.md .claude system
  [ "$status" -eq 1 ]
}
```

- [ ] **Step 2: Run it and watch it fail.** `bats -f '§15' system/tests/commands.bats > system/logs/t6.log 2>&1; echo "exit=$?"`. Expected `exit=1`, failing at the `ls` line because `ChiefOfStaff.md` is still present.

- [ ] **Step 3: Implement.**
  - Run `git mv system/agents/ChiefOfStaff.md system/agents/Optimus.md`.
  - In `CLAUDE.md`, replace ``Persona: `system/agents/ChiefOfStaff.md`.`` with ``Persona: `system/agents/Optimus.md`.``. Change nothing else in `CLAUDE.md`.
  - In `README.md`, replace `| Name | Role | Concrete artifacts (planned) |` with `| Name | Role | Concrete artifacts |`.
  - Then confirm that `git grep -n 'ChiefOfStaff' -- CLAUDE.md README.md .claude system` prints only the test's `[C]hiefOfStaff` line.

- [ ] **Step 4: Run the gate.** Run the test again (expected `exit=0`), then the full gate (expected `exit=0`, every suite PASS) and the lint (expected `0 errors`).

- [ ] **Step 5: Commit.** `git add -A system/agents CLAUDE.md README.md system/tests/commands.bats && git commit -m "refactor: rename the Chief of Staff persona to Optimus.md (spec §15)"`

---

### Task 7: Live check of `/setup` phase 5a (manual, run by the user)

**Files:**
- Create: `docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md`

**Interfaces:**
- Consumes: Tasks 1–6 on `feat/plan-4b`.
- Produces: a PASS or FAIL record. Task 8 waits on PASS.

This task is a checklist for the user, in their real vault, because the evidence is what a real interactive session shows. The controller does not drive it, and it must never run the installer against the real settings itself. The user may answer yes at step 5 or stop after step 4; both are valid outcomes.

- [ ] **Step 1 (user): Baseline.** In the vault on `feat/plan-4b`, run `sha256sum ~/.claude/settings.json; ls -l ~/.claude/commands/digest.md; ls ~/.claude/settings.json.bak.* 2>/dev/null | wc -l`, and note the output.
- [ ] **Step 2 (user): Reach 5a.** Run `claude`, then `/setup`, and accept the existing values through phase 5 (they are idempotent). At 5a, check four things:
  - the installer's dry-run output appears unchanged (diff plus the `settings:` and `digest command:` lines) before any question;
  - each of the five entries is explained;
  - the "act only inside the vault and the registered codebases" sentence appears;
  - the "Stop hook error … It is not an error" explanation appears.
- [ ] **Step 3 (user): Decline.** Answer `maybe later`. Expected: Claude says memory capture stays off, and the report row says the memory hooks are off. Then rerun Step 1's commands. The sha256 and the backup count must be unchanged, and no new `digest.md` must exist.
- [ ] **Step 4 (user): Re-run 5a.** Ask Claude to redo phase 5a. Expected: the same dry run and the same question.
- [ ] **Step 5 (user, optional): Accept.** Answer `yes`. Expected: Claude reports `backup: …`, `settings: changed` and `digest command: new` (or `left alone` if you have your own). Ask for phase 5a once more: Claude must say the hooks are already installed and not ask again. To undo, run `system/scripts/install_hooks.sh --uninstall`, then `jq -S . ~/.claude/settings.json | diff - <(jq -S . <the backup path>)`, which must print nothing.
- [ ] **Step 6 (controller): Record.** Write `docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md` from the user's answers, in this shape, then commit it: `git add docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md && git commit -m "docs: Plan 4b live check of /setup phase 5a"`.

```markdown
# Plan 4b live check: /setup phase 5a

**Date:** <YYYY-MM-DD> · **claude:** <claude --version> · **Commit:** <short sha> (`feat/plan-4b`) · **Vault:** the user's vault; run by the user.

| Step | Check | Result | Notes |
|---|---|---|---|
| 2 | dry run shown before any question; five entries, scope sentence and Stop-hook label explained | | |
| 3 | a non-yes answer installs nothing (sha256 and backup count unchanged) | | |
| 4 | re-running 5a asks again | | |
| 5 | yes installs; a further 5a reports "already installed"; uninstall restores the backup exactly | | (optional) |

## Verdict

**<PASS | FAIL>.** <one sentence>
```

On a FAIL, fix the prompt in a new commit, re-run the gate, and repeat the failing step. At most 3 attempts per step, then stop and report.

---

### Task 8: Roadmap, README status and outcomes

**Files:**
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`, `README.md`
- Create: `docs/superpowers/plans/2026-10-02-plan-4b-outcomes.md`

**Interfaces:**
- Consumes: Task 7's PASS. **If Task 7 did not pass, do not do this task**; report instead.
- Produces: Plan 4b marked complete. Sub-project 2 is unblocked in the roadmap.

- [ ] **Step 1: Roadmap.** In the 4b row of `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md`, replace the Status cell `After Plan 3` with ``Complete (<the date of this commit, YYYY-MM-DD>): `2026-10-02-plan-4b-memory-integration.md`; live check `docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md` ``.
- [ ] **Step 2: README.** Replace ``| 4b. Memory integration, renames | `/setup` memory step, README memory sections, final renames | In progress: [plan](docs/superpowers/plans/2026-10-02-plan-4b-memory-integration.md) |`` with ``| 4b. Memory integration, renames | `/setup` memory step, README memory sections, final renames | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-4b-memory-integration.md), [live check](docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md) |``. If the user ran `/setup` end to end in Task 7, also replace ``; `/setup` and the installed systemd units have not yet been run end to end`` in the status banner with ``; `/setup` has run end to end in a real vault``. Otherwise leave the banner as it is.
- [ ] **Step 3: Outcomes.** Create `docs/superpowers/plans/2026-10-02-plan-4b-outcomes.md` from the execution ledger, in the shape of the Plan 3 and 4a outcomes docs:

```markdown
# Plan 4b outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on <YYYY-MM-DD> (plan: `2026-10-02-plan-4b-memory-integration.md`, commits <first>..<last>, <execution method>). Live check: `docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md`.

Final verification at <sha>: `system/scripts/verify_setup.sh` exit <n>; `hooks_install.bats` <n>/<n>, `commands.bats` <n>/<n>, pytest <n> passed; `lint_vault.sh` <n> errors.

## Rulings
- <Task N>: Ruling: <finding> — <decision and reason> — cost if wrong: <cost>.

## Final-review fixes
- fixed <finding> — <test> RED→GREEN (<commit>).

## Deferred minors
- <Task N>: <minor>.
```

Carry forward, under Deferred minors, every item this plan's Decisions list as left deferred.
- [ ] **Step 4: Verify and commit.** Run the gate (expected `exit=0`) and the lint (expected `0 errors`). Then `git add docs/superpowers/plans/2026-09-30-jarvis-roadmap.md docs/superpowers/plans/2026-10-02-plan-4b-outcomes.md README.md && git commit -m "docs: Plan 4b complete — roadmap, README status, outcomes"`.

---

## Self-Review

- **Spec coverage:**
  - §11 step 5a → Task 3, with the §6.17 label explanation in Tasks 3 and 5;
  - §6.19 dry run, uninstall and backup → Tasks 1 and 2;
  - §7.3a "shown as a diff and confirmed during `/setup`, and removable with `--uninstall`" → Tasks 3, 1 and 2;
  - README memory sections and `/digest` → Task 5;
  - §15 → Task 6, with D11 for what was already done;
  - roadmap → Task 8.
- **Placeholder scan:** the only `<…>` fields are in the Task 7 and Task 8 record templates, filled from live results, and the documented `<paths…>` and `<heading>` argument names.
- **Type consistency:**
  - `setup_section` is defined in Task 3 and used in Task 4;
  - the record path `system/logs/memory/install_hooks.json` and its key (`$SETTINGS`) are the same in the Task 2 code and tests;
  - the output lines `backup:`, `settings:` and `digest command:` are the same in Tasks 1–3 and 7.
- **Review Focus:** each of the five lines names its pinning test or live step above.
