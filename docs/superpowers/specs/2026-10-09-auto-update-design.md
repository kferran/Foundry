# Daily template update

**Date:** 2026-10-09
**Status:** Draft for the owner's review. Scope settled by a grilling session the same day.
**Issue:** #87.

## 1. Problem

Template updates reach a vault only when the owner runs `system/scripts/update_template.sh` by hand. Claude Code's auto mode refuses it inside a session as self-modification. On 2026-10-09 the owner ran it three times, and between runs the vault lagged a feature behind while queued work depended on template fixes.

## 2. Decisions (owner, 2026-10-09)

- A daily systemd timer runs the update unattended, at 05:30 local, on standalone and server machines only. A client gets updates through sync, so two machines never merge the same update.
- It takes `run.lock` like every other writer, waiting briefly. If the lock is busy, or the vault has uncommitted changes, it skips the day and raises an alert. It never commits someone's edits.
- On a merge conflict it runs `git merge --abort`, leaving the vault as it was, and raises an alert. It never resolves a conflict.
- On a server, the existing sync drop-in syncs before and after it, so the update starts from the latest vault and its merge is pushed at once.
- **Reporting:** one line in the alerts file, which the brief already reads. The line covers what merged (the template's pull requests), a conflict, a failure, or a busy skip. A day with nothing new is silent, and each kind alerts at most once a day.
- **Opt-in:** the timer is one more unit in the role's list, so `/setup` installs it with the other units on the owner's yes. An existing vault gets it by running `install_units.sh` once. An update never installs it on its own (#35).
- **Opt-out:** `systemctl --user disable --now foundry-update.timer`. Today `install_units.sh --update` re-enables every installed timer, so it now keeps a disabled timer disabled.
- **Cut from #87:** a report file, a brief section, Needs-you items for renamed settings, and an `auto_update` setting.

## 3. Changes

### 3.1 `update_template.sh --unattended`

The manual run is unchanged. With `--unattended` the script:
- takes `system/run.lock` (`flock -w 300`). When the lock is busy it raises an alert ("skipped: another run held run.lock") and exits 0;
- treats an unclean tree, a missing template remote, a failed fetch, a template branch that cannot be found and unrelated history as failures: an alert and exit 1;
- exits 0 silently when the template branch holds nothing the vault lacks;
- on a merge conflict runs `git merge --abort`, raises an alert naming the conflicted files and the command to run by hand, and exits 1;
- after a merge does what the manual run does (the cutover, the index rebuild, re-rendering installed units). It then raises one alert listing the merged pull requests: the first-parent commits between the old and new template head, each by its PR number and title when it is a pull-request merge, otherwise by its subject, at most 10, then "and N more".

Alerts are written as `- HH:MM:SS [update] <text>` to `system/logs/alerts_<date>.md`, as the sync does. "At most once a day" holds because the timer fires once a day.

### 3.2 Units

- `foundry-update.service` (oneshot: `update_template.sh --unattended`, the vault's `TZ` and `PATH`, `TimeoutStartSec=20min`) and `foundry-update.timer` (`OnCalendar=*-*-* 05:30:00 {{TZ}}`, `Persistent=true`, so a machine that was off at 05:30 updates when it starts).
- `install_units.sh` adds both to the standalone and server lists and enables the timer. A server gets the sync drop-in `foundry-update.service.d/foundry-sync.conf` with no prep step.
- `install_units.sh --update` enables only the timers that were enabled before it ran (`systemctl --user is-enabled`). An installed timer the owner disabled stays disabled.

### 3.3 Docs

`/setup` phase 5 lists `foundry-update` among the units it describes. The README replaces "run `update_template.sh`" guidance with the daily timer, how to turn it off, and that a conflict leaves the vault unchanged with an alert.

## 4. Tests

- **bats (`remote.bats`, stub git remote):**
  - `--unattended` merges and alerts with the PR list;
  - it is silent with nothing new;
  - it aborts a conflict (no merge in progress afterwards, vault HEAD unchanged) and alerts;
  - it skips with an alert while `run.lock` is held;
  - it fails with an alert on an unclean tree.
- **bats (`units.bats`):**
  - standalone and server get the update service and timer, a client none, and a server the drop-in;
  - `--update` leaves a disabled timer disabled and still enables an enabled one.
- **bats (`commands.bats`):** the setup and README text.

Every test fails before the change. Bound tools: bats (`remote.bats`, `units.bats`, `commands.bats`) and the gate.

## 5. Rollout

The owner merges, runs `update_template.sh` one last time, then `system/scripts/install_units.sh` to add the timer. From then on, updates arrive at 05:30 and the brief reports them.
