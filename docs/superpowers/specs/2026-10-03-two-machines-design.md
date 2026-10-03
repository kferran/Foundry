# Two-Machine Design: machine roles, git sync, commit history, Debian

**Date:** 2026-10-03
**Status:** Approved in brainstorming
**Extends:** `2026-09-30-vault-template-design.md` (§6.1 config, §6.2 dependencies, §6.4 intake, §6.6 units, §6.11 remotes, §6.12 updates, §8 `/backup`, §11 `/setup`, §12 tests)
**Roadmap:** Plan 8

## 1. Problem

The template assumes one machine runs everything: the timers, the coding sessions, the focus tracker and the Obsidian window. A common setup splits this. An always-on server runs the automation and the coding sessions, and a second machine is used to read the daily briefing and take notes in Obsidian through the day.

Nothing moves vault data between machines today. `raw/` and `system/logs/` are gitignored. No script pulls from `origin`, and `/backup` only pushes. The installers and `check_deps.sh` have no notion of what a machine is for, and every install hint is a `pacman` hint.

The template stays machine-agnostic. Hostnames, paths and distro choices live in each vault's own gitignored config, never in the template.

## 2. Decisions

| Topic | Decision |
|---|---|
| Roles | `machine_role` per machine: `standalone` (default, today's behavior), `server`, `client` (§3) |
| Where work runs | The server runs all automation and the coding sessions (so session digests are produced there). A client reads and edits the vault in Obsidian |
| Sync | Git on both sides through the private `origin` (`remote_mode: private`). Client: the Obsidian Git plugin. Server: `vault_sync.sh` on a timer and around every run (§4) |
| Client notes | Typed into today's briefing between `#wiki-ingest-start` and `#wiki-ingest-end` (§6.4 extraction, unchanged). No new input path |
| Conflicts | Never resolved automatically. A conflict blocks the server's runs until a human resolves it (§4.3) |
| Commit history | Every automated commit message is built by a script from recorded facts, one commit per run, with trailers. History is a readable handoff log (§5) |
| Focus tracking | Standalone only. Server and client run no focus tracker; brief and debrief already report missing focus data |
| Offline client | Tolerated, not designed for: the client keeps a full clone and syncs when it can reach `origin` |
| Distros | `check_deps.sh` detects `pacman` or `apt` and prints matching hints. The suite is proven on Debian in a container (§7) |

## 3. Machine roles

`system/config.md` (gitignored, so set per machine) gains:

- `machine_role`: enum `standalone | server | client`, default `standalone`.
- `sync_interval_minutes`: positive integer, default `5`. Read on the server only.

Both are added to `system/config.example.md` and the config schema note.

| | standalone | server | client |
|---|---|---|---|
| systemd units | intake, brief, debrief, focus | intake, brief, debrief, sync | none |
| Sync drop-ins on the run services | no | yes (§4.2) | n/a |
| Memory hooks offered by `/setup` | yes | yes | no |
| Codebases registered | yes | yes | no |
| `remote_mode` | any | `private` required | `private` required |
| Linger | offered | required | n/a |
| Calendar (`gcalcli`) | checked | checked | skipped |

### 3.1 `/setup`

The role is asked first, before preflight, showing the current value as the default.

- **standalone:** today's phases, unchanged.
- **server:** today's phases. Phase 4 requires `private`. Phase 5 installs the server units and requires linger: it explains that timers stop at logout without it and gives the `loginctl enable-linger` command for the user to run. The report shows the sync timer.
- **client:** preflight with the client dependency list; config interview limited to timezone and default partition; phase 4 requires `private` (the client is normally a clone of the private origin, so `--detect` finds it); codebases, units, memory hooks, calendar and hand-off are skipped and reported as "not used on a client"; `core.hooksPath` is still set so lint runs on commit; it ends by printing the Obsidian Git settings in §4.4.

README "Getting started" gains the second path: create the first machine (standalone or server) from the template and run `/setup`, which creates the private origin; on a client, `git clone <private origin>`, then `claude` and `/setup`, choosing `client`.

### 3.2 Installers

- `install_units.sh` reads `machine_role` (via `vault_index.py field`; a missing config means `standalone`).
  - standalone: today's four units, unchanged.
  - server: `jarvis-intake`, `jarvis-brief`, `jarvis-debrief` and a new `jarvis-sync.service`/`jarvis-sync.timer` (`OnCalendar` every `sync_interval_minutes`, `Persistent=true`), plus a drop-in `jarvis-{intake,brief,debrief}.service.d/sync.conf` per run service (§4.2). The shared `*.service.in` templates do not change.
  - client: installs nothing, prints `install_units: machine_role client: no units`, and exits 0. `--uninstall` still removes any units this vault owns, whatever the role.
  - A role change followed by a re-run removes owned units the new role does not use.
- `update_template.sh` re-renders by role through `install_units.sh`, as today.
- `install_hooks.sh` does not change. `/setup` decides whether to offer it.

### 3.3 `check_deps.sh`

- New `--role <r>`; the default is the config's `machine_role`, else `standalone`. `--strict` keeps its meaning for the role's required list.
- Required items:
  - **client:** `git`, `python3`, PyYAML.
  - **server:** today's list without `hyprctl`.
  - **standalone:** today's list.
- Optional items stay optional for every role.
- Install hints follow the detected package manager (`pacman`, else `apt`, else a generic "install <item>"). Each item keeps one hint per manager, for example PyYAML: `sudo pacman -S python-yaml` / `sudo apt install python3-yaml`; bats: `bash-bats` / `bats`.

`system_health.bats` becomes role-aware. The focus unit is checked only for standalone. On the server, the sync timer is active, linger is `yes`, and `system/logs/sync-blocked` is absent. A client checks only `check_deps --strict` and `core.hooksPath`.

## 4. Sync

### 4.1 `system/scripts/vault_sync.sh`

The same script runs on every role, and runs from the vault root. It takes `system/run.lock` without waiting (`flock -n`). If the lock is busy it exits 4 and does nothing; the next tick retries. The cycle:

1. **Commit pending run records** (§5.2), each as its own commit.
2. **Commit remaining local changes:** `git add -A` (gitignored paths never enter), then one `sync(<role>)` commit (§5.1) through the pre-commit lint hook. If the hook fails, nothing is committed, an alert is written, and the script exits 1 without pulling or pushing.
3. **Pull:** `git fetch origin`, then `git merge --no-edit -m '<§5.1 merge message>' origin/<upstream branch>`. On a conflict, see §4.3.
4. **Push:** `git push origin HEAD`. If the push is rejected as non-fast-forward, fetch, merge (step 3) and push once more. A second rejection, or any other push failure, writes an alert and exits 1.
5. **Reindex:** `vault_index.py rebuild` if any `*.md` changed in steps 1–3.

Exit codes: 0 synced (or nothing to do), 1 failure with an alert, 2 usage, 3 blocked by a conflict, 4 lock busy. `--pre` (used only by the run services' pre-step) differs in one way: a busy lock exits 0, because the run itself waits for the lock. Alerts go to `system/logs/alerts_<date>.md`, which the brief already reads. A missing upstream or `remote_mode` other than `private` exits 1 with a one-line reason.

### 4.2 When the server syncs

- `jarvis-sync.timer` runs `vault_sync.sh` every `sync_interval_minutes`.
- Each run service gets a drop-in:
  - `ExecStartPre=` runs `vault_sync.sh --pre` (no `-` prefix). Exit 3 (blocked) and exit 1 (sync failed) stop the service before any model run; a busy lock exits 0 so it never skips a run. The run then starts from the latest client edits.
  - `ExecStartPost=` runs `vault_sync.sh` so the run's commit (§5.2) is pushed at once. If the run fails, the next timer tick commits and pushes what exists.
- `run_headless.sh` does not change, so the headless acceptance gate is unaffected by sync itself.
- Interactive `/backup` calls `vault_sync.sh` in every role where `remote_mode` is `private`, so a push always pulls first. `none` and `keep` keep today's behavior.

### 4.3 Conflicts

- A merge conflict: `git merge --abort`, write `system/logs/sync-blocked` (the conflicting paths and the time), alert once per blocked period, exit 3.
- While the marker exists, every run service's pre-step exits 3, so intake, brief and debrief do not run. Manual `run_headless.sh` calls are not blocked; the marker is a guard on automation, not a lock.
- The timer keeps trying. The first clean merge removes the marker and writes a "sync unblocked" alert.
- The user resolves the conflict on either machine (merge, resolve, commit, push). Nothing resolves conflicts automatically.
- The expected hot spot is today's briefing (server extraction while the client is typing). Extraction already runs under `run.lock` and requires the briefing to be unmodified for 60 seconds; a pull updates the file's mtime, so extraction never runs on a briefing that changed in the last minute on either side.

### 4.4 Client sync

The client runs no units. The Obsidian Git plugin syncs it; `/setup` prints these settings:

- auto commit-and-sync every 5 minutes; pull on startup; push after commit;
- merge, not rebase;
- commit message `sync(client): {{numFiles}} files` with the file list in the body (`{{files}}`), and the trailer `Jarvis-Role: client`.

A lint failure in the pre-commit hook makes the plugin's commit fail with a visible notice. Interactive sessions on a client may run `/backup`, which calls `vault_sync.sh`.

## 5. Commit history as a handoff log

Every automated commit message is built by a script from facts the system already records. No model writes commit messages. Subjects stay under 72 characters; bodies list the facts; trailers make history queryable (`git log --grep 'Jarvis-Command: ingest'`).

### 5.1 Message formats

| Commit | Subject | Body | Trailers |
|---|---|---|---|
| ingest run | `ingest(<partition>): <decisions>` e.g. `ingest(work): create NightlyExport, patch BillingService` (truncated with `+N more`) | one line per non-noop decision: `<decision> <target> <- <source>` | `Jarvis-Command: ingest`, `Jarvis-Run: <run_id>`, `Jarvis-Role: <role>` |
| brief / debrief run | `brief <date>: published <path>` / `debrief <date>: published <path>` | published, rejected and conflict lists from `publish.json` | same, with the command |
| rejected or empty run | not committed (nothing published) | — | — |
| briefing extraction | `intake: <n> #wiki-ingest block(s) from briefings/<date>.md` | the `raw/inbox/` file each block became | `Jarvis-Command: extract`, `Jarvis-Role: <role>` |
| other local changes | `sync(<role>): <n> file(s)` | each path with `+added/-removed` lines, `(new)` or `(deleted)` | `Jarvis-Command: sync`, `Jarvis-Role: <role>` |
| merge from origin | `sync(<role>): merge origin/<branch>` | — | `Jarvis-Command: sync` |

### 5.2 One commit per run

- `publish_staged.py commit` already writes `system/logs/runs/<run_id>/publish.json`. A published run whose run directory has no `committed` marker is a **pending run record**.
- A new `system/scripts/commit_runs.py` commits each pending run in ledger order. It stages exactly that run's published paths (`git add -- <paths>`), commits with the §5.1 message, and writes the `committed` marker with the commit sha. A run whose published files have since changed again still commits its paths at their current content; the message describes the run.
- Briefing extraction appends a record to `system/logs/extractions-<YYYY-MM>.jsonl` (time, briefing path, created inbox files). `commit_runs.py` commits each uncommitted record as an `intake:` commit before the remaining changes.
- `vault_sync.sh` step 1 calls `commit_runs.py`. `/backup` calls it too, before its own commit, in every `remote_mode`, so history reads the same in every vault.

### 5.3 Use

The debrief already reads the vault's git log for the day (`debrief_prep.sh`), so it reports these commits unchanged. A new session can read `git log --since=yesterday` for what changed and why. Feeding git history into recall is out of scope (§9).

## 6. Error handling summary

| Condition | Behavior |
|---|---|
| Lint fails on a local commit | no commit, no pull or push; alert; exit 1 |
| Merge conflict | abort; `sync-blocked`; runs skipped; alert; exit 3 |
| Push rejected twice / network down | alert; exit 1; the next tick retries |
| `run.lock` busy | exit 4; nothing done; the next tick retries |
| `remote_mode` not `private`, or no upstream | exit 1 with the reason |
| Client pushes a note that fails lint (hooks bypassed) | the server merges it; lint reports it in `/lint` and the brief's alerts as today; the server's own commits still lint only what they stage |

## 7. Tests

All gated tests are hermetic: temporary git repos (a bare `origin` plus a server and a client clone under `$BATS_TEST_TMPDIR`), stubbed commands, no network.

- **`sync.bats`** (new):
  - local edits are committed and pushed, and gitignored paths never are;
  - a client commit reaches the server's tree on the next sync, and the index is rebuilt;
  - a conflict aborts the merge, writes `sync-blocked` and one alert, and exits 3; the next clean sync removes the marker;
  - a lint failure blocks the commit, the pull and the push;
  - a rejected push is fetched, merged and retried once;
  - a busy `run.lock` exits 4 and changes nothing;
  - `remote_mode` other than `private` exits 1.
- **pytest for `commit_runs.py`:** fixture runs (`_decisions.jsonl`, `publish.json`) and extraction records produce exact subjects, bodies and trailers; each run's commit contains only its paths; the `committed` marker prevents a second commit; rejected runs are not committed.
- **`units.bats`:** rendering per role; drop-ins only on the server; client installs nothing; role change removes unused owned units; the drop-in's pre-step exit 3 stops the unit (checked with `systemd-analyze verify` and the rendered text).
- **`setup.bats`:** `check_deps.sh --role` lists per role; `apt` and `pacman` hints via stubbed `command -v`.
- **`commands.bats`:** `setup.md` asks the role first and skips the client phases with the stated wording; `backup.md` calls `vault_sync.sh` when `private`.
- **`system_health.bats`:** role-aware (advisory, as today).
- **Debian:** `system/tests/debian/` holds a Containerfile (Debian stable with the `apt` dependencies) and `run.sh`, which runs `verify_setup.sh` inside it with `podman` or `docker`, whichever exists. Not part of the gate (it needs a container runtime); run at each plan's acceptance.

### 7.1 Live acceptance

In throwaway clones only, with a local bare repo as `origin`; nothing goes to a hosted remote.

1. **Server clone:** run the commands the units run (sync, a headless brief via `run_headless.sh`, sync). Expected: one `brief <date>` commit with the right trailers, pushed.
2. **Client clone:** add a `#wiki-ingest` block to today's briefing, commit with the §4.4 message, push. Server: sync, intake (extraction and ingest), sync. Expected: an `intake:` commit, an `ingest(<p>):` commit, the compiled note published; the client sees it after a pull.
3. **Forced conflict:** both clones change the same briefing line. Expected: `sync-blocked`, the brief service's pre-step exits 3, resolving and pushing clears it.
4. **Debian:** `system/tests/debian/run.sh` exits 0.
5. The Plan 4a acceptance steps are re-run if `run_headless.sh` or the headless commands changed.

## 8. Template rules

- No hostname, user path, distro or remote URL is committed. Examples in docs use placeholders (`<server>`, `<private origin>`).
- Single-machine vaults (`standalone`) keep today's behavior; the only change they see is `/backup` pulling before pushing when `remote_mode` is `private`, and the structured commit messages.

## 9. Out of scope

- Syncthing, sshfs or other file sync; more than one server; Windows and macOS clients.
- Focus tracking on a client and shipping its logs.
- Automatic conflict resolution.
- Feeding git history into recall.
- Migrating existing vaults between roles beyond re-running `/setup` and `install_units.sh`.
