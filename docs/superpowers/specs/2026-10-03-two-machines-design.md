# Two-Machine Design: machine roles, commit history, git sync, Debian

**Date:** 2026-10-03
**Status:** Approved in brainstorming; revised after an independent design review and its re-review (rev 3)
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
| Distros | `check_deps.sh` detects `pacman` or `apt` and prints matching hints. The suite is proven by running it natively on a Debian host, the oldest supported release available (§6) |

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
| Calendar (Google Calendar connector, `2026-10-03-calendar-connector-design.md`) | checked | checked | skipped |

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
- **Cutover:** `system/logs/commit_runs.since` holds a timestamp in `run_id` format (`YYYYmmddTHHMMSS`, local time, as `run_headless.sh` writes it), compared as a string with each `run_id`'s first 15 characters. `/setup` phase 7 writes it when absent, and so does `update_template.sh` after merging; `commit_runs.py` writes it as a last resort when it is still missing. Older run directories are never committed, so a vault does not replay its history.
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
4. No operation is in progress: `.git/MERGE_HEAD`, `.git/rebase-merge/`, `.git/rebase-apply/`, `.git/CHERRY_PICK_HEAD`, unmerged entries in `git ls-files -u`, or a stale `.git/index.lock` (older than 10 minutes with no `git` process running in this repository). Before the lock this is a **check only**: exit 3 without writing anything, because a sync holding the lock may be mid-merge.
5. `system/logs/sync-blocked` from an earlier conflict exists: try the cycle anyway (§5.4 says when it clears).

**Lock:** `flock -n system/run.lock`; busy: exit 4, nothing done. After taking the lock, precondition 4 is checked again; if it still holds, write `sync-blocked` (reason "operation in progress" or "stale index.lock"), alert, exit 3.

**Deadline:** the whole script has one budget, `SYNC_DEADLINE` (default 300 s). Each network call gets `timeout` set to the smaller of 120 s and the time left. A `TERM`/`INT` trap aborts an in-progress merge (`git merge --abort` when `MERGE_HEAD` exists) before exiting, so a systemd stop never leaves a half-merged tree.

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
- `--pre` (run services, before the run): check the `sync-blocked` marker and precondition 4 (check only) **first**; either present: exit 3. Then the cycle; a busy lock and every exit-1 failure exit 0, so runs proceed on local state.
- `--post` (run services, after the run): the cycle; always exits 0 (failures are alerted), so a successful run is never marked failed.

The index does not need an explicit rebuild: `Index.refresh` runs on every read.

### 5.2 Server units

- `jarvis-sync.service` (oneshot, `ExecStart=vault_sync.sh`) and `jarvis-sync.timer` (`OnBootSec=2min`, `OnUnitActiveSec=<sync_interval_minutes>min`), as `system/systemd/jarvis-sync.{service,timer}.in`, installed for `server` only.
- One drop-in template, `system/systemd/dropins/jarvis-sync.conf.in`, rendered per run service to `jarvis-{intake,brief,debrief}.service.d/jarvis-sync.conf` with the `# Managed by vault: <root>` first line. It resets the pre-steps and restores order:
  ```
  ExecStartPre=
  ExecStartPre="{{VAULT_ROOT}}/system/scripts/vault_sync.sh" --pre
  {{PREP_LINE}}
  ExecStartPost="{{VAULT_ROOT}}/system/scripts/vault_sync.sh" --post
  ```
  `{{PREP_LINE}}` is the service's own prep line (`ExecStartPre=-…/brief_prep.sh` for brief, `…/debrief_prep.sh` for debrief, empty for intake), so prep reads a freshly pulled tree. `ExecStartPost` runs only after a successful run; a failed run's output is committed by the next timer tick.
- `install_units.sh`'s owned-unit scan, and `update_template.sh`'s "units installed" check, include `*.service.d/*.conf` files whose first line names this vault. Every pre- and post-step counts toward a oneshot's `TimeoutStartSec`, so the limits rise by two sync deadlines plus margin: brief and debrief from 20 to 35 minutes (sync 5 + lock wait 10 + run 15 + sync 5), intake from 90 to 105 minutes. `jarvis-sync.service` gets `TimeoutStartSec=10min`, twice its deadline.

### 5.3 Failures that are not conflicts

Fetch, push, credential, refused-merge and hook failures exit 1 and never stop runs (`--pre`, `--post`). Alerts for one failure kind are written once per day while it persists, plus one "sync recovered" alert when it clears. State lives in `system/logs/sync-state.json` (kind, first seen, last alerted). The brief reads alerts as today, so a sync problem appears in the next briefing.

### 5.4 Conflicts

On a merge conflict, `vault_sync.sh`:
1. records the conflicted paths, runs `git merge --abort`, and checks its exit status (a failed abort: alert, keep `sync-blocked`, exit 3);
2. pushes its own side to a branch named for the role: `git push --force origin HEAD:refs/heads/jarvis/<role>-pending` (the server's own branch, so forcing it is safe);
3. writes `system/logs/sync-blocked` (paths, time, pending branch) and one alert per blocked period;
4. exits 3.

While `sync-blocked` exists, every run service's pre-step exits 3, so intake, brief and debrief do not run. Manual `run_headless.sh` calls are not blocked. Resolution: on the other machine, `git fetch origin`, `git merge origin/jarvis/<role>-pending`, resolve, commit, push; on the machine that pushed the pending branch, its side is already checked out, so it merges `origin/<branch>` instead. The same steps apply to `jarvis/client-pending`, which a client's `/backup` pushes when its own sync conflicts.

**Clearing:** the marker is removed by any cycle that completes step 5, whether or not `origin` was ahead. That cycle also deletes `jarvis/<role>-pending` on `origin` (a branch that is already gone is not an error) and writes a "sync unblocked" alert.

**Missed daily runs:** brief and debrief fire once a day, and a pre-step that exits 3 skips them. On unblocking, the server starts (`systemctl --user start --no-block`) `jarvis-brief.service` and `jarvis-debrief.service` when that command's scheduled time today has passed and the run ledger has no run of it today. The blocked alert says runs are skipped until unblocked.

On a client, `/backup` (which runs `vault_sync.sh`) also reports any `origin/jarvis/*-pending` branch it sees after fetching, so a conflict surfaces wherever the user next syncs by hand. A missing briefing in the morning is the other visible signal; push notifications are out of scope.

### 5.5 Conflict markers never land

- `.githooks/pre-commit` rejects any staged text file (every staged path, not only notes) that contains both a line matching `^<<<<<<< ` and a later line matching `^>>>>>>> `; git always writes a label after both. It does not look at `=======` lines, which are valid Markdown (a setext heading underline), and it does not use `git diff --check`, which also flags Markdown's trailing double-space line breaks.
- `vault_sync.sh` precondition 4 refuses to commit during an unfinished merge, rebase or cherry-pick (a sync killed mid-merge, or `update_template.sh` stopping on conflicts).
- A user resolving a merge on the server runs the same hook. If a client note that bypassed the hook blocks the resolution commit, the hook's message names it; the user fixes it or commits with `--no-verify` knowingly. The README documents this.

### 5.6 Non-destructive extraction

Briefing extraction (`intake.py`) no longer rewrites the briefing:

- Each complete `#wiki-ingest-start` … `#wiki-ingest-end` block is identified by the sha256 of its text (markers excluded, whitespace trimmed).
- A block whose `(briefing path, hash)` pair is not in `system/logs/extracted_blocks.jsonl` is written to `raw/inbox/daily_note_drop_<epoch>.md`, and a record `{"kind": "block", "briefing", "hash", "drop", "time"}` is appended inside `run.lock`, before the lock is released. The same text in a later day's briefing is a new block. The briefing file is not modified.
- An edited block has a new hash and is extracted again; ingest's noop/patch decisions absorb the overlap.
- The existing rule that the briefing is unmodified for 60 seconds stays. Client notes recommend Obsidian Git's "commit-and-sync after stopping file edits" (§5.7) so half-typed blocks rarely reach the server.
- An unterminated or nested start marker is alerted once per briefing per day, recorded as `{"kind": "alert", "briefing", "reason", "date"}` in the same file, not on every tick.

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

The plugin stops auto commits and pushes while a merge has conflicts and shows a notice; it runs the repository's pre-commit hook. `.obsidian/plugins/obsidian-git/data.json` is added to `.gitignore` (machine-specific settings; no secrets on desktop); client `/setup` runs `git rm --cached` on it when it is already tracked. Other plugins' settings stay synced on purpose, so Dataview and the like behave the same on every machine.

The plugin runs the pre-commit hook inside Obsidian's environment, whose `PATH` may differ from a terminal's (Flatpak and AppImage builds especially). Client `/setup` asks the user to make one test edit and confirm the plugin's commit succeeds; the hook's error names any missing tool.

The client notes also say:
- files dropped into `raw/inbox/` on a client are not synced (it is gitignored); write notes in the briefing instead. `lint_vault.sh` on a client warns when `raw/inbox/` holds files.
- disable any Obsidian plugin that creates `briefings/<date>.md` on the client (daily notes, templates): the server creates it, and two creations conflict.
- `/backup` on a client runs lint, then `vault_sync.sh`. It shares no lock with the plugin; if both touch git at once, one fails on git's own `index.lock` and the next attempt succeeds.

### 5.8 `/backup` in `private`

Order: verification (§3.6) → `vault_sync.sh` (which runs `commit_runs.py` and makes the scripted `sync` commit, replacing the model-written message) → report its exit code in words (0 synced, 1 the alert text, 3 blocked with the pending branch, 4 "a run is in progress; try again shortly"). `none` and `keep` keep today's steps plus §4.3.

## 6. Debian (Plan 8a)

- Debian is proven by running the gate natively on a Debian machine, not in a container (user decision, 2026-10-03). `system/tests/verify_on_host.sh <ssh-host>` copies the committed tree (`git archive HEAD`) to a new directory under the host's `/tmp`, runs `verify_setup.sh` there with its output in a log beside it, prints the summary, and exits with the gate's code. On success it removes the directory and the log; on failure it keeps both and prints their paths. It installs nothing and writes nothing outside that directory and its log. The host needs the apt dependencies from §3.4 (no `claude`: the suite stubs it).
- Not part of the gate (it needs a reachable host); run at each plan's acceptance on the oldest supported Debian release available. That release sets the tool floor (currently jq 1.6, bats 1.8, SQLite 3.40, Python 3.11); code and tests must work on it.
- Defects found on Debian 12 while planning, fixed in Plan 8a:
  - `vaultlib/guard.py`: SQLite 3.40 reports its own schema parse as an `UPDATE` of `sqlite_master` while it builds the FTS5 table, which the query authorizer denied, so `vault_index.py query` failed for FTS `MATCH` and `pragma_table_info`. The authorizer allows `UPDATE` on `sqlite_master`/`sqlite_schema` only; the connection stays read-only (`mode=ro`, `query_only`).
  - `install_hooks.sh`: jq 1.6 exits 0 for `jq -e .` on empty input (newer jq exits 4), so an empty install record passed the one-value check and broke the merge. The check tests for a non-empty value explicitly.

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

Gated tests are hermetic: temporary repos (a bare `origin` plus server and client clones under `$BATS_TEST_TMPDIR`), stubs on `PATH`, no network. They must pass with jq 1.6, bats 1.8 and SQLite 3.40 (§6).

- **8a:** `check_deps.sh --role` lists; `pacman`/`apt-get` hints via `PATH` stubs; `install_units.sh` per role (client installs nothing, role change removes unused owned units); `setup.md` asks the role first and states each client skip; `backup.md` lints on a client; role-aware `system_health.bats` (advisory); config schema accepts the new keys and rejects out-of-range `sync_interval_minutes`.
- **8b:** pytest for `commit_runs.py`: exact subjects, bodies and trailers from fixture runs; only the run's paths in its commit even with other files staged; cutover ignores older runs; already-committed paths get the marker without a commit; a hook failure leaves the run pending; `conflict`/`recovered` runs with published files are committed, rejected and empty ones are not. `debrief_prep.sh` lists vault commits from any author.
- **8c:** `sync.bats`: commit and push; gitignored paths never committed; client commit reaches the server; conflict → abort, pending branch pushed, marker, one alert, exit 3; resolution from the client clone clears it and deletes the pending branch; in-progress merge and unmerged index → exit 3 without committing; conflict-marker file rejected by the hook; refused merge → exit 1 with no `MERGE_HEAD`; rejected push retried once; busy lock → 4, `--pre` → 0, `--post` → 0; `--pre` with a marker → 3 even when the lock is busy; `--pre` during another sync's merge → 3 without writing a marker; stale `index.lock` → 3; TERM during a merge leaves no `MERGE_HEAD`; a note with a setext `=======` underline commits; marker cleared by a cycle with nothing to merge; missed brief started on unblock (stubbed `systemctl`); template origin and missing upstream → 1; alert rate limiting. `units.bats`: sync units and drop-ins only for `server`, drop-in text order (reset, sync, prep, post), owned drop-ins removed on uninstall and role change. pytest for non-destructive extraction: briefing bytes unchanged, one drop per new block, no repeat for a known `(briefing, hash)`, the same text in a later briefing extracted, a new drop for an edited block, unterminated alert once per day. `system_health.bats` server checks.

### 8.1 Live acceptance (per plan, in throwaway clones; a local bare repo stands in for `origin`)

- **8a:** `system/tests/verify_on_host.sh <debian host>` exits 0; `check_deps.sh --role client|server` output read on that host.
- **8b:** a headless ingest and a brief in a throwaway clone, then `commit_runs.py`: one commit per run with the expected message and trailers; Plan 4a acceptance steps re-run if `run_headless.sh` or the headless commands changed.
- **8c:**
  1. Server clone: `vault_sync.sh --pre`, a headless brief, `vault_sync.sh --post`: a `brief <date>` commit pushed.
  2. Client clone: a `#wiki-ingest` block added to today's briefing and pushed. Server: sync, intake, sync: an `ingest(<p>)` commit, the briefing unchanged, the note published; the client sees it after a pull.
  3. Forced conflict: both clones change the same briefing line: `jarvis/server-pending` on origin, `sync-blocked`, the brief pre-step exits 3; resolved from the client clone; the next server sync clears both.
  4. Network failure (origin path made unreadable): the brief still runs and publishes locally; one alert; recovery alert after restoring.

## 9. Template rules

- No machine's own hostname, user path, remote URL or distro choice is committed. Docs use placeholders (`<server>`, `<private origin>`). Generic support files (apt hints, the host-verification script) are fine.
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
