# Two-Machine Design: machine roles, commit history, git sync, Debian

**Date:** 2026-10-03
**Status:** Approved in brainstorming; revised after an independent design review (rev 2)
**Extends:** `2026-09-30-vault-template-design.md` (§6.1 config, §6.2 dependencies, §6.4 intake, §6.6 units, §6.11 remotes, §6.12 updates, §8 `/backup`, §11 `/setup`, §12 tests)
**Roadmap:** Plan 8, split into three plans (§10): 8a roles and Debian, 8b commit history, 8c sync

## 1. Problem

The template assumes one machine runs everything: the timers, the coding sessions, the focus tracker and the Obsidian window. A common setup splits this. An always-on server runs the automation and the coding sessions, and a second machine is used to read the daily briefing and take notes in Obsidian through the day.

Nothing moves vault data between machines today. `raw/` and `system/logs/` are gitignored. No script pulls from `origin`, and `/backup` only pushes. The installers and `check_deps.sh` have no notion of what a machine is for, and every install hint is a `pacman` hint.

The template stays machine-agnostic: a machine's own hostname, paths, remote URL and distro choice live in its gitignored config, never in the template.

## 2. Decisions

| Topic | Decision |
|---|---|
| Roles | `machine_role` per machine: `standalone` (default, today's behavior), `server`, `client` (§3) |
| Where work runs | The server runs all automation and the coding sessions, so session digests are produced there. A client reads and edits the vault in Obsidian |
| Commit history | Every automated commit message is built by a script from recorded facts, one commit per headless run, with trailers, so `git log` is a handoff log. Applies to every role (§4) |
| Sync | Git on both sides through the private `origin`. Client: the Obsidian Git plugin. Server: `vault_sync.sh` on a timer and around every run (§5) |
| Client notes | Typed into today's briefing between `#wiki-ingest-start` and `#wiki-ingest-end`. Extraction no longer rewrites the briefing: compiled blocks are recorded by hash and left in place (§5.6) |
| Conflicts | Never resolved automatically. The server publishes its side to a branch so the conflict can be resolved from either machine; the server's runs pause until it is (§5.4) |
| Other sync failures | Network, credential and push failures never stop runs: the server keeps working on its own copy, alerts (rate-limited), and catches up when sync works (§5.3) |
| Focus tracking | Standalone only |
| Offline client | Tolerated, not designed for: the client keeps a full clone and syncs when it can reach `origin` |
| Distros | `check_deps.sh` detects `pacman` or `apt` and prints matching hints. The suite is proven in Debian containers on the oldest supported release (oldstable, currently bookworm) and on stable (§6) |

## 3. Machine roles (Plan 8a)

### 3.1 Config

`system/config.md` gains, in `system/config.example.md` and the config schema note:

- `machine_role`: enum `standalone | server | client`; default `standalone`. A config without the key is `standalone`.
- `sync_interval_minutes`: integer 1–60; default `5`. Read on the server only (Plan 8c).

| | standalone | server | client |
|---|---|---|---|
| systemd units | intake, brief, debrief, focus | intake, brief, debrief (Plan 8c adds sync) | none |
| Memory hooks offered by `/setup` | yes | yes | no |
| Codebases registered | yes | yes | no |
| `remote_mode` | any | `private` required | `private` required |
| Linger | offered | `/setup` stops phase 5 until `loginctl show-user` reports `yes`, giving the command to run | n/a |
| Calendar (`gcalcli`) | checked | checked | skipped |

### 3.2 `/setup`

The role is asked first, before preflight, with the current value as the default.

- **standalone:** today's phases, unchanged.
- **server:** today's phases, with the linger rule above and `remote_mode: private` required in phase 4. Phase 4 also checks, before finishing:
  - `git config user.name` and `user.email` are set;
  - `origin` is reachable without prompting (`GIT_TERMINAL_PROMPT=0 git ls-remote origin`);
  - the branch is published: when `origin` has no branch of this name, phase 4 runs `git push -u origin HEAD` (after the template-origin refusal `backup.md` already applies).
- **client:** preflight with the client list (§3.4); config interview limited to timezone and default partition; phase 4 requires `private` and runs the same three checks; codebases, units, memory hooks, calendar and hand-off are reported as "not used on a client"; phases 7 (index) and 8 (verify) run, where phase 8 runs `lint_vault.sh` instead of `verify_setup.sh --health`. The report ends with the client notes in §5.7.

README "Getting started" gains the second path: set up the first machine (standalone or server) from the template, give it a private `origin` in `/setup` phase 4, which publishes the branch; then on a client, `git clone <private origin>`, `claude`, `/setup`, and choose `client`.

### 3.3 Installers

- `install_units.sh` reads `machine_role` (`vault_index.py field`; a missing config or key means `standalone`) and selects templates and the enable list by role. The hard-coded unit list becomes a per-role table in the script.
  - standalone: today's four units.
  - server: intake, brief, debrief.
  - client: installs nothing, prints `install_units: machine_role client: no units`, exits 0.
  - Re-running after a role change removes owned units (and, from Plan 8c, owned drop-ins) the new role does not use. `--uninstall` removes every owned unit whatever the role.
- `update_template.sh` re-renders through `install_units.sh`, as today.
- `install_hooks.sh` does not change; `/setup` decides whether to offer it.

### 3.4 `check_deps.sh`

- New `--role <r>`; default: the config's `machine_role`, else `standalone`. `--strict` keeps its meaning for the role's required list. Optional items stay optional for every role.
- Required lists:
  - **standalone:** today's list.
  - **server:** today's list without `hyprctl`.
  - **client:** `claude`, `git`, `python3`, PyYAML, FTS5 (the lint hook builds the index), `jq`.
- Install hints follow the package manager detected on `PATH`: `pacman`, else `apt-get`, else a generic `install <item>`. Each item carries one hint per manager, for example PyYAML `sudo pacman -S python-yaml` / `sudo apt install python3-yaml`, bats `bash-bats` / `bats`.

### 3.5 Health

`system_health.bats` becomes role-aware. Focus unit: standalone only. Server: the run timers are active and linger is `yes` (Plan 8c adds: sync timer active, no `sync-blocked`). Client: `check_deps --strict` and `core.hooksPath`.

### 3.6 `/backup` on a client

A client has no bats or pytest, so `/backup` step 1 runs `lint_vault.sh` on a client and `verify_setup.sh` elsewhere.

## 4. Commit history as a handoff log (Plan 8b)

Every automated commit message is built by a script from facts the system records. No model writes them. Subjects stay under 72 characters; bodies list facts; trailers make history queryable (`git log --grep 'Jarvis-Command: ingest'`). This applies to every role, including standalone vaults that never sync.

### 4.1 Formats

| Commit | Subject | Body | Trailers |
|---|---|---|---|
| ingest run | `ingest(<partition>): <decisions>`, e.g. `ingest(work): create NightlyExport, patch BillingService`, truncated with `+N more` | one line per non-noop decision: `<decision> <target> <- <source>` | `Jarvis-Command: ingest`, `Jarvis-Run: <run_id>`, `Jarvis-Role: <role>` |
| brief / debrief run | `brief <date>: <published path>` / `debrief <date>: <published path>` | published and conflict lists from `publish.json` | `Jarvis-Command: brief` or `debrief`, `Jarvis-Run`, `Jarvis-Role` |
| other local changes (Plan 8c sync, and `/backup` in `private`) | `sync(<role>): <n> file(s)` | each path with `+added/-removed`, `(new)` or `(deleted)` | `Jarvis-Command: sync`, `Jarvis-Role` |
| merge from origin (Plan 8c) | `sync(<role>): merge origin/<branch>` | — | `Jarvis-Command: sync`, `Jarvis-Role` |

### 4.2 `system/scripts/commit_runs.py`

- **Pending run:** a directory `system/logs/runs/<run_id>/` with a `publish.json` whose `published` list is non-empty (any status, so `conflict` and `recovered` count when they published something), with no `committed` file, and with `run_id` at or after the cutover time.
- **Cutover:** the first time `commit_runs.py` runs, it writes `system/logs/commit_runs.since` with the current time; older run directories are never committed. A fresh vault therefore does not replay its history.
- **Order:** by `run_id` (it starts with a timestamp). The partition comes from the run's ledger line, falling back to the partition folder of the first decision target.
- **Commit:** `git add -- <published paths>` then `git commit --only -m <message> -- <published paths>`, so anything else already staged stays out. The commit runs through the pre-commit hook.
- **Already committed:** when none of the paths differ from `HEAD` (another commit already holds them), write `committed` with `{"sha": null, "reason": "already committed"}` and move on.
- **Hook failure:** alert, leave the run pending, stop processing further runs, exit 1.
- **Marker:** `committed` holds `{"sha": "<sha>"}`.
- Exit 0 when every pending run is committed or recorded as already committed.

### 4.3 Callers

- `/backup`, in every `remote_mode`, runs `commit_runs.py` after verification and before its own commit. In `none` and `keep` the remaining changes still get the model-written commit message (unchanged in Plan 8b); in `private` Plan 8c replaces the remaining commit and the push with `vault_sync.sh`.
- Plan 8c's `vault_sync.sh` runs it as its first step.

### 4.4 Debrief

`debrief_prep.sh` stops filtering the **vault's** log by `user.email`. The vault is the user's own, and commits come from more than one machine and from scripts. Codebase logs keep the filter.

## 5. Sync (Plan 8c)

### 5.1 `system/scripts/vault_sync.sh`

Runs from the vault root on any role. Environment for every git call: `GIT_TERMINAL_PROMPT=0`; when `GIT_SSH_COMMAND` is unset, `ssh -o BatchMode=yes -o ConnectTimeout=15`. Network calls (`fetch`, `push`, `ls-remote`) run under `timeout 120`.

**Preconditions** (checked in this order before taking the lock):
1. `remote_mode` is `private`, else exit 1 with the reason.
2. `origin` is not the template repository (the same comparison `backup.md` uses), else exit 1.
3. The branch has an upstream, else exit 1 ("no upstream; run /setup phase 4").
4. No operation is in progress: `.git/MERGE_HEAD`, `.git/rebase-merge/`, `.git/rebase-apply/`, `.git/CHERRY_PICK_HEAD`, or unmerged entries in `git ls-files -u`. If any exists: write `sync-blocked` (reason "operation in progress"), exit 3.
5. `system/logs/sync-blocked` from an earlier conflict exists: try the cycle anyway (a clean merge clears it, §5.4).

**Lock:** `flock -n system/run.lock`; busy: exit 4, nothing done.

**Cycle:**
1. `commit_runs.py` (§4.2). Failure: alert, exit 1.
2. Remaining local changes: `git add -A`, then one `sync(<role>)` commit (§4.1) through the pre-commit hook. Hook failure: `git reset -q` (unstage), alert, exit 1.
3. `git fetch origin`. Failure: alert, exit 1.
4. `git merge --no-edit -m '<merge message>' origin/<upstream>` when `origin` is ahead. Outcomes:
   - clean (or nothing to merge): continue;
   - conflict (`git ls-files -u` non-empty): §5.4;
   - refused without starting (local changes or untracked files would be overwritten, which happens when an interactive session writes a file between steps 2 and 4): no `MERGE_HEAD` exists; alert, exit 1, retry on the next tick.
5. `git push origin HEAD:<upstream branch>`. Non-fast-forward: repeat steps 3–5 once. A second rejection or any other failure: alert, exit 1.

**Exit codes:** 0 synced or nothing to do; 1 failure (alerted); 2 usage; 3 blocked; 4 lock busy.

**Modes:**
- default (timer, `/backup`): as above.
- `--pre` (run services, before the run): check preconditions 4 and the `sync-blocked` marker **first**; either present: exit 3. Then the cycle; a busy lock and every exit-1 failure exit 0, so runs proceed on local state.
- `--post` (run services, after the run): the cycle; always exits 0 (failures are alerted), so a successful run is never marked failed.

The index does not need an explicit rebuild: `Index.refresh` runs on every read.

### 5.2 Server units

- `jarvis-sync.service` (oneshot, `ExecStart=vault_sync.sh`, `TimeoutStartSec=10min`) and `jarvis-sync.timer` (`OnBootSec=2min`, `OnUnitActiveSec=<sync_interval_minutes>min`), as `system/systemd/jarvis-sync.{service,timer}.in`, installed for `server` only.
- One drop-in template, `system/systemd/dropins/jarvis-sync.conf.in`, rendered per run service to `jarvis-{intake,brief,debrief}.service.d/jarvis-sync.conf` with the `# Managed by vault: <root>` first line. It resets the pre-steps and restores order:
  ```
  ExecStartPre=
  ExecStartPre="{{VAULT_ROOT}}/system/scripts/vault_sync.sh" --pre
  {{PREP_LINE}}
  ExecStartPost="{{VAULT_ROOT}}/system/scripts/vault_sync.sh" --post
  ```
  `{{PREP_LINE}}` is the service's own prep line (`ExecStartPre=-…/brief_prep.sh` for brief, `…/debrief_prep.sh` for debrief, empty for intake), so prep reads a freshly pulled tree. `ExecStartPost` runs only after a successful run; a failed run's output is committed by the next timer tick.
- `install_units.sh`'s owned-unit scan, and `update_template.sh`'s "units installed" check, include `*.service.d/*.conf` files whose first line names this vault. `TimeoutStartSec` of brief and debrief rises from 20 to 30 minutes to cover a pre-sync and the existing 600 s lock wait.

### 5.3 Failures that are not conflicts

Fetch, push, credential, refused-merge and hook failures exit 1 and never stop runs (`--pre`, `--post`). Alerts for one failure kind are written once per day while it persists, plus one "sync recovered" alert when it clears. State lives in `system/logs/sync-state.json` (kind, first seen, last alerted). The brief reads alerts as today, so a sync problem appears in the next briefing.

### 5.4 Conflicts

On a merge conflict, `vault_sync.sh`:
1. records the conflicted paths, runs `git merge --abort`, and checks its exit status (a failed abort: alert, keep `sync-blocked`, exit 3);
2. pushes its own side to a branch named for the role: `git push --force origin HEAD:refs/heads/jarvis/<role>-pending` (the server's own branch, so forcing it is safe);
3. writes `system/logs/sync-blocked` (paths, time, pending branch) and one alert per blocked period;
4. exits 3.

While `sync-blocked` exists, every run service's pre-step exits 3, so intake, brief and debrief do not run. Manual `run_headless.sh` calls are not blocked. Resolution, on either machine: `git fetch origin`, `git merge origin/jarvis/server-pending`, resolve, commit, push. The server's next sync then merges cleanly (normally a fast-forward), deletes `jarvis/server-pending` on `origin`, removes the marker, and writes a "sync unblocked" alert.

On a client, `/backup` (which runs `vault_sync.sh`) also reports any `origin/jarvis/*-pending` branch it sees after fetching, so a conflict surfaces wherever the user next syncs by hand. A missing briefing in the morning is the other visible signal; push notifications are out of scope.

### 5.5 Conflict markers never land

- `.githooks/pre-commit` rejects any staged text file containing a line matching `^(<<<<<<<|=======|>>>>>>>)( |$)`, for every staged path (not only notes). It does not use `git diff --check`, which also flags Markdown's trailing double-space line breaks.
- `vault_sync.sh` precondition 4 refuses to commit during an unfinished merge, rebase or cherry-pick (a sync killed mid-merge, or `update_template.sh` stopping on conflicts).
- A user resolving a merge on the server runs the same hook. If a client note that bypassed the hook blocks the resolution commit, the hook's message names it; the user fixes it or commits with `--no-verify` knowingly. The README documents this.

### 5.6 Non-destructive extraction

Briefing extraction (`intake.py`) no longer rewrites the briefing:

- Each complete `#wiki-ingest-start` … `#wiki-ingest-end` block is identified by the sha256 of its text (markers excluded, whitespace trimmed).
- A block whose hash is not in `system/logs/extracted_blocks.jsonl` is written to `raw/inbox/daily_note_drop_<epoch>.md` and its hash appended (briefing path, hash, drop file, time), inside `run.lock`, before the lock is released. The briefing file is not modified.
- An edited block has a new hash and is extracted again; ingest's noop/patch decisions absorb the overlap.
- The existing rule that the briefing is unmodified for 60 seconds stays. Client notes recommend Obsidian Git's "commit-and-sync after stopping file edits" (§5.7) so half-typed blocks rarely reach the server.
- An unterminated or nested start marker is alerted once per briefing per day (recorded in the same file), not on every tick.

This applies to every role. Standalone users see their blocks stay in the briefing after compiling; the README says so.

### 5.7 Client

The client runs no units. `/setup` (client) prints these Obsidian Git settings (data.json keys verified against the plugin source):

| Setting | Key | Value |
|---|---|---|
| Auto commit-and-sync interval (minutes) | `autoSaveInterval` | `5` |
| Auto commit-and-sync after stopping file edits | `autoBackupAfterFileChange` | on |
| Pull on startup | `autoPullOnBoot` | on |
| Push on commit-and-sync | `disablePush` | `false` |
| Pull on commit-and-sync | `pullBeforePush` | on |
| Merge strategy | `syncMethod` | `merge` |
| Commit message on auto commit-and-sync | `autoCommitMessage` | `sync(client): {{numFiles}} files` + blank line + `{{files}}` + blank line + `Jarvis-Command: sync` + newline + `Jarvis-Role: client` |

The plugin stops auto commits and pushes while a merge has conflicts and shows a notice; it runs the repository's pre-commit hook. `.obsidian/plugins/obsidian-git/data.json` is added to `.gitignore` (machine-specific settings; no secrets on desktop).

The client notes also say:
- files dropped into `raw/inbox/` on a client are not synced (it is gitignored); write notes in the briefing instead. `lint_vault.sh` on a client warns when `raw/inbox/` holds files.
- disable any Obsidian plugin that creates `briefings/<date>.md` on the client (daily notes, templates): the server creates it, and two creations conflict.
- `/backup` on a client runs lint, then `vault_sync.sh`.

### 5.8 `/backup` in `private`

Order: verification (§3.6) → `vault_sync.sh` (which runs `commit_runs.py` and makes the scripted `sync` commit, replacing the model-written message) → report its exit code in words (0 synced, 1 the alert text, 3 blocked with the pending branch, 4 "a run is in progress; try again shortly"). `none` and `keep` keep today's steps plus §4.3.

## 6. Debian (Plan 8a)

- `system/tests/debian/Containerfile` takes `ARG DEBIAN_RELEASE` (default `oldstable`) and installs the `apt` dependencies; tests run as a non-root user (some tests rely on permission checks root bypasses).
- `system/tests/debian/run.sh [release…]` builds and runs `verify_setup.sh` with `podman` or `docker`, whichever exists; with no argument it runs `oldstable` and `stable`. Exit 0 only if every release passes.
- Inside the container (`JARVIS_CONTAINER=1`), tests that need a running user systemd (`systemd-analyze --user verify`) skip with that reason; they still run on the host.
- Not part of the gate (it needs a container runtime); run at each plan's acceptance. The oldest supported release sets the tool floor (currently jq 1.6, bats 1.8); code and tests must work on it.

## 7. Error handling summary

| Condition | Behavior |
|---|---|
| Merge, rebase or cherry-pick in progress | exit 3, `sync-blocked`; runs pause |
| Merge conflict | abort; push `jarvis/<role>-pending`; `sync-blocked`; runs pause; alert once |
| Merge refused (local or untracked changes) | exit 1; retry next tick; runs continue |
| Fetch or push failure, credentials, network | exit 1; alert once a day; runs continue on local state |
| Pre-commit hook fails (lint or conflict markers) | unstage; exit 1; alert; runs continue |
| `run.lock` busy | exit 4 (`--pre`/`--post`: 0) |
| `remote_mode` not `private`, origin is the template, or no upstream | exit 1 with the reason |
| Client pushes a note that fails lint (hook bypassed) | server merges it; `/lint` and the brief report it; server commits lint only what they stage |

## 8. Tests

Gated tests are hermetic: temporary repos (a bare `origin` plus server and client clones under `$BATS_TEST_TMPDIR`), stubs on `PATH`, no network. They must pass with jq 1.6 and bats 1.8 (§6).

- **8a:** `check_deps.sh --role` lists; `pacman`/`apt-get` hints via `PATH` stubs; `install_units.sh` per role (client installs nothing, role change removes unused owned units); `setup.md` asks the role first and states each client skip; `backup.md` lints on a client; role-aware `system_health.bats` (advisory); config schema accepts the new keys and rejects out-of-range `sync_interval_minutes`.
- **8b:** pytest for `commit_runs.py`: exact subjects, bodies and trailers from fixture runs; only the run's paths in its commit even with other files staged; cutover ignores older runs; already-committed paths get the marker without a commit; a hook failure leaves the run pending; `conflict`/`recovered` runs with published files are committed, rejected and empty ones are not. `debrief_prep.sh` lists vault commits from any author.
- **8c:** `sync.bats`: commit and push; gitignored paths never committed; client commit reaches the server; conflict → abort, pending branch pushed, marker, one alert, exit 3; resolution from the client clone clears it and deletes the pending branch; in-progress merge and unmerged index → exit 3 without committing; conflict-marker file rejected by the hook; refused merge → exit 1 with no `MERGE_HEAD`; rejected push retried once; busy lock → 4, `--pre` → 0, `--post` → 0; `--pre` with a marker → 3 even when the lock is busy; template origin and missing upstream → 1; alert rate limiting. `units.bats`: sync units and drop-ins only for `server`, drop-in text order (reset, sync, prep, post), owned drop-ins removed on uninstall and role change. pytest for non-destructive extraction: briefing bytes unchanged, one drop per new block, no repeat for a known hash, a new drop for an edited block, unterminated alert once per day. `system_health.bats` server checks.

### 8.1 Live acceptance (per plan, in throwaway clones; a local bare repo stands in for `origin`)

- **8a:** `system/tests/debian/run.sh` exits 0 on `oldstable` and `stable`; `check_deps.sh --role client|server` output read on the host.
- **8b:** a headless ingest and a brief in a throwaway clone, then `commit_runs.py`: one commit per run with the expected message and trailers; Plan 4a acceptance steps re-run if `run_headless.sh` or the headless commands changed.
- **8c:**
  1. Server clone: `vault_sync.sh --pre`, a headless brief, `vault_sync.sh --post`: a `brief <date>` commit pushed.
  2. Client clone: a `#wiki-ingest` block added to today's briefing and pushed. Server: sync, intake, sync: an `ingest(<p>)` commit, the briefing unchanged, the note published; the client sees it after a pull.
  3. Forced conflict: both clones change the same briefing line: `jarvis/server-pending` on origin, `sync-blocked`, the brief pre-step exits 3; resolved from the client clone; the next server sync clears both.
  4. Network failure (origin path made unreadable): the brief still runs and publishes locally; one alert; recovery alert after restoring.

## 9. Template rules

- No machine's own hostname, user path, remote URL or distro choice is committed. Docs use placeholders (`<server>`, `<private origin>`). Generic support files (apt hints, the Debian Containerfile) are fine.
- Standalone vaults keep today's behavior except: scripted run commits (§4), the vault log in the debrief without the author filter (§4.4), non-destructive extraction (§5.6), the conflict-marker hook (§5.5), and, in `private`, `/backup` syncing through `vault_sync.sh` (§5.8).

## 10. Plans

| Plan | Sections | Depends on |
|---|---|---|
| **8a. Roles and Debian** | §3, §6 | — |
| **8b. Commit history** | §4 | — (useful alone) |
| **8c. Sync** | §5, sync parts of §3.2 and §3.5 | 8a, 8b |

Each plan ends with its live acceptance (§8.1) and an outcomes doc.

## 11. Out of scope

- Syncthing, sshfs or other file sync; more than one server; Windows, macOS and mobile clients.
- Focus tracking on a client.
- Automatic conflict resolution; push notifications for conflicts.
- Feeding git history into recall.
