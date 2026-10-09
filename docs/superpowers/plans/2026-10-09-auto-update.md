# Daily Template Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Template updates reach a standalone or server vault every morning without the owner running `update_template.sh` by hand (#87).

**Architecture:** `update_template.sh --unattended` is the existing update with four differences:
- it takes `run.lock`;
- it aborts a conflicted merge;
- it is silent when nothing is new;
- it reports through the alerts file the brief reads.

A new `foundry-update` service and timer (05:30 daily) run it, with the server sync drop-in. `install_units.sh --update` re-enables only timers that are enabled, so the owner can turn the update off.

**Tech Stack:** bash, systemd user units, bats 1.8.2.

**Spec:** `docs/superpowers/specs/2026-10-09-auto-update-design.md`

## Global Constraints

- Work on branch `feat/auto-update`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Template rule: no machine, employer or people names.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once), outside a sandbox: `units.bats` and `remote.bats` use `/tmp` and systemd paths. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: bats (`units.bats`, `remote.bats`, `commands.bats`, `vault_integrity.bats`) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step. A "Create" step writes the whole file.

## Review Focus

- **A held lock:** the unattended run waits, then skips the day, exits 0 and alerts; it never merges under another run. Test: the `run.lock` test.
- **A conflict:** the vault ends with no merge in progress and HEAD unchanged. Test: the conflict test.
- **Uncommitted changes:** never committed or merged. Test: the unclean-tree test.
- **The manual run:** unchanged, including leaving a conflicted merge for the owner. The existing `update_template` tests pass unmodified, except the enable list, which gains the new timer.
- **Opt-out:** a timer the owner disabled stays disabled after `install_units.sh --update`, and one still enabled is re-enabled. Test: the disabled-timer test.

---

### Task 1: The unattended update, its units and the opt-out

**Files:**
- Create: `system/systemd/foundry-update.service.in`, `system/systemd/foundry-update.timer.in`
- Modify: `system/scripts/update_template.sh`, `system/scripts/install_units.sh`, `.claude/commands/setup.md`, `README.md`
- Test: `system/tests/units.bats`, `system/tests/remote.bats`, `system/tests/commands.bats`, `system/tests/vault_integrity.bats`

**Interfaces:**
- Produces: `update_template.sh [--unattended]`, exit 0 (merged, nothing new, or skipped because `run.lock` was busy), 1 (failure or conflict) or 2 (usage). Alerts are `- HH:MM:SS [update] <text>` lines in `system/logs/alerts_<date>.md`. `UPDATE_LOCK_WAIT` (seconds, default 300) is for tests.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/units.bats`. Find:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-nightshift.timer' "$STUB_SYSTEMCTL_LOG"
````

Replace with:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
````

Edit 2 in `system/tests/units.bats`. Find:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-sync.timer foundry-nightshift.timer' "$STUB_SYSTEMCTL_LOG"
````

Replace with:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-sync.timer foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
````

Edit 3 in `system/tests/units.bats`. Find:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-meetings.timer foundry-nightshift.timer' "$STUB_SYSTEMCTL_LOG"
````

Replace with:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-meetings.timer foundry-nightshift.timer foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
````

Edit 4 in `system/tests/units.bats`. Find:

````text
  grep -q 'enable --now .*foundry-dtcc-watch.timer' "$STUB_SYSTEMCTL_LOG"
}
````

Replace with:

````text
  grep -q 'enable --now .*foundry-dtcc-watch.timer' "$STUB_SYSTEMCTL_LOG"
}

@test "standalone and server get the template update every morning at 05:30, a server with its sync drop-in (#87)" {
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qxF "ExecStart=\"$VP/system/scripts/update_template.sh\" --unattended" "$UD/foundry-update.service"
  grep -qx 'OnCalendar=\*-\*-\* 05:30:00 America/Denver' "$UD/foundry-update.timer"
  grep -qx 'Persistent=true' "$UD/foundry-update.timer"
  [ ! -e "$UD/foundry-update.service.d" ]
  system/scripts/vault_index.py set system/config.md machine_role server > /dev/null
  run "$IU"
  [ "$status" -eq 0 ]
  grep -qx 'TimeoutStartSec=35min' "$UD/foundry-update.service.d/foundry-sync.conf"
  grep -qxF "ExecStartPost=\"$VP/system/scripts/vault_sync.sh\" --post" "$UD/foundry-update.service.d/foundry-sync.conf"
  system/scripts/vault_index.py set system/config.md machine_role client > /dev/null
  run "$IU"
  [ ! -e "$UD/foundry-update.timer" ]
}

@test "--update keeps a timer the owner disabled disabled, and re-enables only enabled ones (#87)" {
  "$IU" > /dev/null
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n[[ "$*" != *"is-enabled --quiet foundry-nightshift.timer"* ]]\n' > "$STUBS/systemctl"
  : > "$STUB_SYSTEMCTL_LOG"
  run "$IU" --update
  [ "$status" -eq 0 ]
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
}
````


Edit 1 in `system/tests/remote.bats`. Find:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service' "$STUB_SYSTEMCTL_LOG"
````

Replace with:

````text
  grep -qx -- '--user enable --now foundry-intake.timer foundry-brief.timer foundry-debrief.timer foundry-focus.service foundry-update.timer' "$STUB_SYSTEMCTL_LOG"
````

Edit 2 in `system/tests/remote.bats`. Find:

````text
  [[ "$output" == *"setup_remote.sh"* ]]
}
````

Replace with:

````text
  [[ "$output" == *"setup_remote.sh"* ]]
}

# alerts: today's update alerts in the vault's timezone.
alerts() { cat "system/logs/alerts_$(TZ=America/Denver date +%F).md" 2>/dev/null; }

# upstream_pr <n> <title> <file>: a pull request merged on the template's default branch, as GitHub writes it.
upstream_pr() {
  git -C "$W" checkout -q -b "pr$1"
  printf '%s\n' "$3" > "$W/$3"
  git -C "$W" add -A
  git -C "$W" commit -qm "$2"
  git -C "$W" checkout -q -
  git -C "$W" merge -q --no-ff "pr$1" -m "Merge pull request #$1 from someone/pr$1" -m "$2"
  git -C "$W" push -q
}

@test "--unattended merges and raises one alert listing the merged pull requests (#87)" {
  template_setup
  upstream_pr 7 "Add the export job" a.txt
  upstream_commit b.txt direct
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(cat a.txt)" = a.txt ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  [ "$(alerts | grep -c '\[update\]')" -eq 1 ]
  alerts | grep -qF '[update] template updated: merged 2 change(s): upstream: b.txt; #7 Add the export job'
}

@test "--unattended with nothing new merges nothing and stays silent (#87)" {
  template_setup
  before="$(git rev-parse HEAD)"
  run "$UT" --unattended
  [ "$status" -eq 0 ]
  [ "$(git rev-parse HEAD)" = "$before" ]
  [ -z "$(alerts)" ]
}

@test "--unattended aborts a conflict, leaves the vault unchanged and alerts (#87)" {
  template_setup
  upstream_commit "my notes.txt" theirs
  printf 'ours\n' > "my notes.txt"
  git commit -qam ours
  before="$(git rev-parse HEAD)"
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ ! -e .git/MERGE_HEAD ]
  [ "$(git rev-parse HEAD)" = "$before" ]
  [ -z "$(git status --porcelain)" ]
  alerts | grep -qF '[update] template update stopped on a conflict in my notes.txt; the vault is unchanged.'
}

@test "--unattended skips with an alert while another run holds run.lock (#87)" {
  template_setup
  upstream_commit new.txt hello
  exec 8> system/run.lock
  flock 8
  UPDATE_LOCK_WAIT=1 run "$UT" --unattended
  exec 8>&-
  [ "$status" -eq 0 ]
  [ ! -e new.txt ]
  alerts | grep -qF '[update] template update skipped: another run held run.lock'
}

@test "--unattended fails with an alert on uncommitted changes and never commits them (#87)" {
  template_setup
  upstream_commit new.txt hello
  echo x > dirty.txt
  run "$UT" --unattended
  [ "$status" -eq 1 ]
  [ ! -e new.txt ]
  [ "$(git status --porcelain)" = '?? dirty.txt' ]
  alerts | grep -qF '[update] template update failed: working tree is not clean'
}
````


Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'the connector returns no change history' README.md
}
````

Replace with:

````text
  grep -qF 'the connector returns no change history' README.md
}

@test "/setup and the README describe the daily template update and how to turn it off (#87)" {
  grep -qF '`foundry-update` (standalone and server), which merges template updates every morning at 05:30' .claude/commands/setup.md
  grep -qF '`systemctl --user disable --now foundry-update.timer`' .claude/commands/setup.md
  grep -qF '`foundry-update.timer` runs it every morning at 05:30 (`update_template.sh --unattended`, #87)' README.md
  grep -qF 'aborts a conflicted merge (`git merge --abort`), leaving the vault unchanged' README.md
  grep -qF 'later updates keep it disabled' README.md
}
````


Edit 1 in `system/tests/vault_integrity.bats`. Find:

````text
  [ "${#files[@]}" -eq 18 ]
````

Replace with:

````text
  [ "${#files[@]}" -eq 20 ]
````


- [ ] **Step 2: Run them to verify they fail**

Run: `bats system/tests/units.bats system/tests/remote.bats system/tests/commands.bats system/tests/vault_integrity.bats`
Expected: FAIL, 13 `not ok` (the 8 new tests, 4 whose enable list gains `foundry-update.timer`, and the unit-template count, now 20).

- [ ] **Step 3: Implement**

Create `system/systemd/foundry-update.service.in`:

````text
[Unit]
Description=The Foundry: template update

[Service]
Type=oneshot
WorkingDirectory={{VAULT_ROOT}}
Environment="TZ={{TZ}}"
Environment="PATH={{UNIT_PATH}}"
# Waiting for run.lock (5 min), the fetch, the merge, the index rebuild and re-rendered units.
TimeoutStartSec=20min
ExecStart="{{VAULT_ROOT}}/system/scripts/update_template.sh" --unattended
````

Create `system/systemd/foundry-update.timer.in`:

````text
[Unit]
Description=The Foundry: template update every morning before the brief

[Timer]
OnCalendar=*-*-* 05:30:00 {{TZ}}
Persistent=true

[Install]
WantedBy=timers.target
````

Edit 1 in `system/scripts/update_template.sh`. Find:

````text
# Fetch and merge template updates; never auto-resolves (spec §6.12).
````

Replace with:

````text
# Fetch and merge template updates; never auto-resolves (spec §6.12).
# --unattended (foundry-update.timer, #87): take run.lock, abort a conflicted merge, and report through the
# alerts file the brief reads: what merged, a conflict, a failure or a busy skip. Nothing new is silent.
````

Edit 2 in `system/scripts/update_template.sh`. Find:

````text
die() { echo "update_template: $2" >&2; exit "$1"; }
(( $# == 0 )) || die 2 "usage: update_template.sh"

git remote get-url template >/dev/null 2>&1 || die 1 "no template remote; run system/scripts/setup_remote.sh first"
[[ -z "$(git status --porcelain)" ]] || die 1 "working tree is not clean; commit or stash first"

git fetch --quiet template || die 1 "git fetch template failed"
# LC_ALL=C: "HEAD branch:" is translated in other locales.
branch="$(LC_ALL=C git remote show template 2>/dev/null | sed -n 's/^ *HEAD branch: //p')"
[[ -n "$branch" && "$branch" != "(unknown)" ]] || die 1 "cannot determine the template's default branch"
ref="template/$branch"
git merge-base HEAD "$ref" >/dev/null 2>&1 \
  || die 1 "$ref shares no history with this vault (created from a GitHub template?); merge it by hand: git merge --allow-unrelated-histories $ref"

if ! git merge --no-ff --no-edit "$ref"; then
  conflicted="$(git diff --name-only --diff-filter=U)"
  [[ -n "$conflicted" ]] || die 1 "git merge $ref failed"
````

Replace with:

````text
unattended=0
alert() { mkdir -p system/logs; printf -- '- %s [update] %s\n' "$(date +%H:%M:%S)" "$1" >> "system/logs/alerts_$(date +%F).md"; }
die() {
  (( ! unattended )) || alert "template update failed: $2"
  echo "update_template: $2" >&2
  exit "$1"
}
case "${1:-}" in
  "") ;;
  --unattended) unattended=1 ;;
  *) die 2 "usage: update_template.sh [--unattended]" ;;
esac
(( $# <= 1 )) || die 2 "usage: update_template.sh [--unattended]"
# git children run with run.lock's fd 9 closed: a detached gc must not keep the lock.
g() { git "$@" 9>&-; }

if (( unattended )); then
  exec 9> system/run.lock
  if ! flock -w "${UPDATE_LOCK_WAIT:-300}" 9; then
    alert "template update skipped: another run held run.lock; it runs again tomorrow"
    exit 0
  fi
fi

g remote get-url template >/dev/null 2>&1 || die 1 "no template remote; run system/scripts/setup_remote.sh first"
[[ -z "$(g status --porcelain)" ]] || die 1 "working tree is not clean; commit or stash first"

g fetch --quiet template || die 1 "git fetch template failed"
# LC_ALL=C: "HEAD branch:" is translated in other locales.
branch="$(LC_ALL=C g remote show template 2>/dev/null | sed -n 's/^ *HEAD branch: //p')"
[[ -n "$branch" && "$branch" != "(unknown)" ]] || die 1 "cannot determine the template's default branch"
ref="template/$branch"
g merge-base HEAD "$ref" >/dev/null 2>&1 \
  || die 1 "$ref shares no history with this vault (created from a GitHub template?); merge it by hand: git merge --allow-unrelated-histories $ref"
(( ! unattended )) || ! g merge-base --is-ancestor "$ref" HEAD || exit 0

if ! g merge --no-ff --no-edit "$ref"; then
  conflicted="$(g diff --name-only --diff-filter=U)"
  [[ -n "$conflicted" ]] || die 1 "git merge $ref failed"
  if (( unattended )); then
    g merge --abort
    alert "template update stopped on a conflict in $(paste -sd ' ' <<< "$conflicted"); the vault is unchanged. Run system/scripts/update_template.sh by hand and resolve it."
    exit 1
  fi
````

Edit 3 in `system/scripts/update_template.sh`. Find:

````text
system/scripts/commit_runs.py --init-cutover
system/scripts/vault_index.py rebuild
````

Replace with:

````text
system/scripts/commit_runs.py --init-cutover 9>&-
system/scripts/vault_index.py rebuild 9>&-
````

Edit 4 in `system/scripts/update_template.sh`. Find:

````text
  system/scripts/install_units.sh --update
````

Replace with:

````text
  system/scripts/install_units.sh --update 9>&-
````

Edit 5 in `system/scripts/update_template.sh`. Find:

````text
  echo "update_template: units not installed; skipped (install them with system/scripts/install_units.sh)"
fi
````

Replace with:

````text
  echo "update_template: units not installed; skipped (install them with system/scripts/install_units.sh)"
fi

if (( unattended )); then
  # The template's own history since the vault's last merge of it: one entry per pull request merged there.
  merged=()
  while IFS=$'\x1f' read -r -d $'\x1e' subject title; do
    subject="${subject#$'\n'}" title="${title%%$'\n'*}"
    if [[ "$subject" =~ ^Merge\ pull\ request\ (#[0-9]+) && -n "$title" ]]; then
      merged+=("${BASH_REMATCH[1]} $title")
    else
      merged+=("$subject")
    fi
  done < <(g log --first-parent --format='%s%x1f%b%x1e' HEAD^1..HEAD^2)
  list="$(printf '%s; ' "${merged[@]:0:10}")"
  list="${list%; }"
  (( ${#merged[@]} <= 10 )) || list+="; and $(( ${#merged[@]} - 10 )) more"
  alert "template updated: merged ${#merged[@]} change(s): $list"
fi
````


Edit 1 in `system/scripts/install_units.sh`. Find:

````text
  ENABLE+=(foundry-nightshift.timer)
fi
````

Replace with:

````text
  ENABLE+=(foundry-nightshift.timer)
fi
# Template update: standalone and server, every morning (#87); a client gets updates through sync.
if [[ "$role" != client ]]; then
  UNITS+=(foundry-update.service foundry-update.timer)
  ENABLE+=(foundry-update.timer)
fi
````

Edit 2 in `system/scripts/install_units.sh`. Find:

````text
                                    foundry-debrief.service.d/foundry-sync.conf)
declare -A DROPIN_TIMEOUT=([foundry-intake]=105min [foundry-brief]=60min [foundry-debrief]=60min)
declare -A DROPIN_PREP=([foundry-intake]="" [foundry-brief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/brief_prep.sh"'
                        [foundry-debrief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"')
````

Replace with:

````text
                                    foundry-debrief.service.d/foundry-sync.conf foundry-update.service.d/foundry-sync.conf)
declare -A DROPIN_TIMEOUT=([foundry-intake]=105min [foundry-brief]=60min [foundry-debrief]=60min [foundry-update]=35min)
declare -A DROPIN_PREP=([foundry-intake]="" [foundry-brief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/brief_prep.sh"'
                        [foundry-debrief]='ExecStartPre=-"{{VAULT_ROOT}}/system/scripts/debrief_prep.sh"' [foundry-update]="")
````

Edit 3 in `system/scripts/install_units.sh`. Find:

````text
  for n in "${ENABLE[@]}"; do [[ " ${keep[*]} " != *" $n "* ]] || keep_enable+=("$n"); done
````

Replace with:

````text
  # Only what is enabled now stays enabled: a timer the owner disabled stays off across updates (#87).
  for n in "${ENABLE[@]}"; do
    [[ " ${keep[*]} " != *" $n "* ]] || ! "$SYSTEMCTL" --user is-enabled --quiet "$n" || keep_enable+=("$n")
  done
````


Edit 1 in `.claude/commands/setup.md`. Find:

````text
Run `system/scripts/install_units.sh --dry-run` and summarize the units it prints: `foundry-intake` (every 5 minutes), `foundry-brief` and `foundry-debrief` (at the configured times), `foundry-focus` (standalone only), the focus tracker; `foundry-sync` (server only), which syncs with `origin` every `sync_interval_minutes` and, through a drop-in on each run service, before and after every run; `foundry-meetings` (when `meetings_enabled` is `true`), which fetches Gemini notes from Google Drive every hour from 08:00 to 18:00 on workdays. Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged|removed` line.
````

Replace with:

````text
Run `system/scripts/install_units.sh --dry-run` and summarize the units it prints: `foundry-intake` (every 5 minutes), `foundry-brief` and `foundry-debrief` (at the configured times), `foundry-focus` (standalone only), the focus tracker; `foundry-sync` (server only), which syncs with `origin` every `sync_interval_minutes` and, through a drop-in on each run service, before and after every run; `foundry-meetings` (when `meetings_enabled` is `true`), which fetches Gemini notes from Google Drive every hour from 08:00 to 18:00 on workdays; `foundry-update` (standalone and server), which merges template updates every morning at 05:30 and reports them through the alerts the brief reads (turn it off with `systemctl --user disable --now foundry-update.timer`). Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged|removed` line.
````


Edit 1 in `README.md`. Find:

````text
- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders only the units this vault installed. A unit the update adds is listed as `new unit available: <unit>` and left out; read `system/scripts/install_units.sh --dry-run`, then run `system/scripts/install_units.sh` to add it. It never runs automatically.
````

Replace with:

````text
- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders only the units this vault installed. A unit the update adds is listed as `new unit available: <unit>` and left out; read `system/scripts/install_units.sh --dry-run`, then run `system/scripts/install_units.sh` to add it. On a standalone machine or a server, `foundry-update.timer` runs it every morning at 05:30 (`update_template.sh --unattended`, #87). It waits for `run.lock` and skips the day if another run holds it, refuses uncommitted changes, and aborts a conflicted merge (`git merge --abort`), leaving the vault unchanged. It reports each of those, and a successful update with the template pull requests it merged, as an `[update]` line in the alerts the brief reads; a day with nothing new is silent. On a server the sync runs before and after it. A client gets updates through sync. To stop the daily update, run `systemctl --user disable --now foundry-update.timer`; later updates keep it disabled.
````


- [ ] **Step 4: Run the tests and the gate**

Run: the command from Step 2.
Expected: PASS, no `not ok`.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(update): a daily template update (#87)

foundry-update.timer runs update_template.sh --unattended at 05:30 on
standalone and server machines. Unattended, the script takes run.lock
(skipping the day with an alert when another run holds it), fails with
an alert on uncommitted changes or a failed fetch, aborts a conflicted
merge so the vault is unchanged, and on success raises one [update]
alert listing the template pull requests it merged. Nothing new is
silent. On a server the sync drop-in syncs around it.

install_units.sh --update now re-enables only timers that are enabled,
so turning the daily update off with systemctl disable sticks. /setup
and the README describe it.

Closes #87
```

Run: `git add system/systemd/foundry-update.service.in system/systemd/foundry-update.timer.in system/scripts/update_template.sh system/scripts/install_units.sh .claude/commands/setup.md README.md system/tests/units.bats system/tests/remote.bats system/tests/commands.bats system/tests/vault_integrity.bats`

Run: `git commit -q -F .scratch/msg-1.txt`
