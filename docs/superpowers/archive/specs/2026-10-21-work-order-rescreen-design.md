# Work Order re-screen at every tick

**Date:** 2026-10-21
**Status:** draft for the owner
**Grill:** not an owner idea: audit finding #298 (high), 2026-10-20 audit
**Builder check:** 2026-10-21, five questions, settled from existing rules or as the builder's calls (§1 repo wall, §6): a codebase's partition is a wall for `repo`; the threat is a writer reaching the note by sync or a client; `blocked` notes get identifiers only; a symlinked research output is refused; the host rule refuses IP literals only (internal names out of scope).
**Blueprint:** Work Order
**Lane:** feature (a safety surface: the Work Order runner); the owner merges

## Intent

A Work Order's queue note (`raw/<p>/nightshift/<id>.md`) is screened in full only by `nightshift.py add` (`nc.check`). Each tick, `_screen` (`nightshift_run.py:625-638`) runs only `nc.identifiers()`. The note syncs between machines and any session can edit it, so an edit after `add`, or a note written without `add` at all, reaches the research session unchecked:

- `hosts` flows into `allowedDomains` and `WebFetch(domain:…)` (`nightshift_session.py:42,51`).
- `output` becomes the publish snapshot target (`nightshift_deliver.py:247-254`). The gate accepts whatever target the run names, so a probe published `docs/injected.md`, `extensions/telemetry/skills/evil/SKILL.md` (a skill interactive sessions load) and a note in the other partition.

Separately, `_research_dir` (`nightshift_run.py:262-267`) copies all of `wiki/<p>/` into the session's `context/`, `private/` included.

This breaks P2 (model output reaches the vault only through the gate's own rules), P3 (a session reading untrusted input gets a narrow, checked capability) and P5 (walls hold at every step). The fix: the runner screens what it runs, when it runs it, and the research session reads only background notes.

## Goals

- Every capability-bearing field (`hosts`, `output`, `partition`) passes the add-time rule at the moment the tick uses it.
- The research `context/` holds no `private/` text and no file reached through a symlink.
- Failure looks like today's refusal: same state, reason, alert and exit code.

## Non-goals

- An owner approval gate for `hosts`. `nightshift.py add:*` is pre-allowed, so any session can queue a plain host today (see Out of scope).
- The other #298 items. Publish through a symlinked folder has its own spec (`2026-10-21-publish-symlink-escape-design.md`).

## Anti-goals

- A second copy of the add-time rules in the runner. One function, two callers.
- Network or git calls in the per-pass screen. `_screen` runs every pass of the tick loop (about every 5 s while workers run).
- A refused order that still runs, or that changes state with no alert.

## Constraints

- `nightshift_run.py` header: exit 0 ok, 1 an item failed, 2 usage or invalid item, 4 locked.
- `add` may run on a client. The note reaches the server by sync, and the runner itself rewrites it on every attempt (`state`, `attempts`, `session_id`).
- The template stays generic. One PR, merged by the owner.

## Design

### 1. One screen, two callers

Split `nc.check` (`nightshift_check.py:160`) into two halves:

- **Field half**, `nc.screen(fm, body, folder=None)`. It reads the note and the registered codebase files only: no git, no network, no other config. It runs `identifiers()`, the kind, `budget` and `start_at` parsing, then the kind's field rules. Research: the brief sections, the output rule and the host rule. Plan: `verify` is not empty. Moving `budget` here also stops a hand-edited bad budget from raising `ValueError` in `_fits` and stopping the tick.
- **Environment half.** Workspace, `template_remote`, the registered repo, base resolution, plan tasks. `check()` returns the field half's errors first and stops there, as it does today after `identifiers()`.

`_screen` calls `nc.screen` in place of `nc.identifiers` for every live note. Notes already `failed`, `done`, `cancelled` or `blocked` keep `identifiers()` only: they never run (`ns.due` passes only `queued` and `waiting_reset`, `nightshift_sched.py:38`), and `_reconcile` needs only their id. The in-loop `_screen` skips ids a worker holds: `ni.update` is read-modify-write with no lock, so marking a running note would race the worker's `_finish`. That worker is screened again at its next attempt. The environment half stays at `add` and `check` only. With the repo wall in the field half, nothing left in it widens a capability. Tasks and base pick plan content; the session holds no credential, and delivery checks protected refs.

New rules inside the field half:

- **Output:** `wiki/<p>/(concepts|entities|summaries)/….md`, where `<p>` is the note's `partition`. This refuses `docs/`, `extensions/`, the other partition, `private/`, `meetings/`, `preferences/` and `Now.md`. A run id `…-nightshift-…` gives the gate command `nightshift`, so the gate's `meetings/` and `Now.md` refusals (`publish.py:325-328`) never apply to research. The `/order` skill line "a new path under `wiki/<partition>/`" changes to name the three folders.
- **Partition:** `partition` must equal the note's folder (`raw/<p>/nightshift/`). The schema already says `matches_folder: true`, but nothing enforced it.
- **Repo wall (builder check):** a codebase file's `partition` is a wall (`system/schemas/codebase.md`; recall enforces it in `scope.py` and `lib_memory.sh`; CLAUDE.md: never copy `work` content into `personal`). An order's `repo` must name a codebase in the order's partition (or `shared`), at `add` and at every tick. The field half therefore reads the note and the registered codebase files (local files, no git or network); "reads the note only" above becomes "reads the note and `system/codebases/`".
- **Hosts:** `HOST` as today, and the last label must contain a letter. Today `HOST` accepts `127.0.0.1` and `169.254.169.254` (a cloud metadata address), at `add` too. This refuses IP literals only; a name that resolves to an internal address (a metadata hostname, a wildcard DNS service) needs a denylist in the sandbox's network proxy, out of scope here.

The fm a worker gets is the dict `_screen` passed. `_run_session` and `_deliver_research` read only that dict, so an edit during a session changes nothing until the next attempt, and that attempt is screened again. The builder keeps it that way: no reload of capability fields inside `run_item`.

Delivery retries read `fm["repo"]` again (`push_target`, `nightshift_deliver.py:75`). A repo swapped while an order sits in `delivering` would push one codebase's verified commit to another codebase's origin. `_deliver_plan` records `repo` in `delivery.json`, and `_deliver` uses that recorded value. It falls back to `fm["repo"]` only for a `delivery.json` written before the fix, which has no `repo` key.

### 2. A note that fails

Today's path for an identifiers failure, unchanged: `state: failed`, `reason: invalid: <errors>`, one alert per note per day keyed `invalid/<note name>` with the text `<note name> refused: <errors>` under the `[orders]` tag. The pre-loop screen returns 2 and the tick ends. In the loop, the note is marked and alerted, and the workers already running carry on. Like today, a refused note gets no `_finish`, no report row and no notice. The next tick skips it (exit 0). The owner fixes the field and queues the order again with `/order add`, which runs the same screen.

### 3. No content pin

The pin is dropped. A hash written at `add` would live in the note or in the synced vault, so whoever edits the note can rewrite the hash with it. The runner rewrites the note on every attempt anyway. A note written straight into the folder has no `add` to pin. A pin kept only on the server would guard values that a new `add` accepts anyway. The rule that closes every route is the one above: no field becomes a capability without passing the add-time rule at that moment.

### 4. The research read set

`_research_dir` rebuilds `context/` at every attempt (remove it, then copy), from `wiki/<p>/concepts/`, `entities/` and `summaries/` only. It skips dotfiles and every symlink. `copytree` follows links today, and the runner runs outside the sandbox, so a symlink synced into the partition copies any file the owner's user can read into `context/`. Left out:

- `private/`, which every session is denied.
- `Now.md` (open loops and drafts).
- `meetings/` (verbatim transcripts).
- `preferences/` (the owner's statements; a brief needs none).

A folder added to the wiki later stays out until someone lists it. Stale-claim bullets still link `[[Note]]` names under `context/`.

The copy is the enforcement. The profile denies the vault root (`_deny`, mirrored as `Read(//…)` rules), so `context/` is the only vault text the session sees. A settings rule on `context/` would add nothing.

### 5. Orders already queued

There is no migration step. The first tick after the update screens every live note. An order that passed the old rules and fails the new ones takes the §2 path, and the alert names the field. A research order in `running` or `waiting_reset` gets a fresh `context/` (no `private/`) on its next attempt. A session already running when the update lands keeps its settings until it ends.

### 6. Threat model and the research output (builder check)
The attacker this spec closes is a writer that reaches the queue note through sync or a client `add`. `system/logs/nightshift/items/<id>/` is git-ignored and never synced, so recording `repo` (and `pr_base`) in `delivery.json` holds against that writer. A session on the server that can write `system/logs/` can already push any verified commit and pre-set alert keys; that is a wider question (local sessions writing runner state), listed in Out of scope.
- **`blocked` notes** get identifiers only, like `failed`, `done` and `cancelled`: they never run, and flipping one back to `queued` screens it in full. This avoids failing a parked order on the first tick after the update.
- **Links in the research output:** `_deliver_research` and `stale_claims_input` read `out/<name>` outside the sandbox. A research session can `ln -s` that file to a `private/` or other-partition note. The runner reads `out/<name>` only when it is a regular file, not a symlink, and refuses the run otherwise (`failed`, reason `invalid: output is a link`, one alert). A `context/` replaced by a symlink is removed with `unlink`, not `rmtree`. One test each.

## Tests (each fails before the fix)

These go in `test_nightshift_run.py`, in the house style: `add` through `nr.main`, edit with `ni.update`, run a tick, then assert the state, the reason prefix, the alert text and which files are missing.

1. Hosts edit after add, parametrized over `"*"` and `"169.254.169.254"`. The tick returns 2, the state is `failed` with a reason starting `invalid: host`, and there is no `items/<id>/settings.json`.
2. Output edited after add to `docs/injected.md`. Refused, and the file is never created.
3. Parametrized: output to `extensions/telemetry/skills/evil/SKILL.md`, `wiki/personal/concepts/X.md` on a work note, `wiki/work/private/X.md` and `wiki/work/meetings/X.md`, plus `partition: personal` in `raw/work/`. Each is refused at the tick, and by `nc.check` in `test_nightshift_check.py`.
4. The partition holds `private/Secret.md`, `Now.md`, `meetings/M.md` and `concepts/Link.md`, a symlink to a file outside the vault. The stub's `SHELL` asserts that none of them is in `context/` and that `context/concepts/Background.md` is. The run ends `done`.
5. A resumed research order whose `context/private/` was built before the fix: the next attempt removes it.
6. Delivery after a repo edit in `delivering` pushes to the recorded repo.

Existing tests pass unchanged. Every research fixture in `test_nightshift_*.py` already writes its output under `wiki/work/concepts/`.

## Left to the builder

- *Builder's call:* the name `nc.screen` and how it learns the folder (a path argument, or `_screen` adds the folder rule).
- *Builder's call:* the three-folder allowlist for output and context. It is the simplest rule that covers `private/`, `meetings/`, `preferences/` and `Now.md` at once. Reversing one folder in review is a one-line change.
- Any docs that state the output rule (the `/order` skill, FOUNDRY.md).

## Out of scope (findings beyond the audit, for new issues)

- **No owner gate on hosts.** `Bash(system/scripts/nightshift.py add:*)` is pre-allowed, so a session can queue a research order with any plain host and WebFetch to it.
- **Sibling order directories.** The research profile does not deny other orders' directories under `order_workspace`: their `context/` copies of another partition, and plan clones, kept 7 days after a failure. Read from the code; not probed.
- **Internal host names.** Names that resolve to metadata or loopback addresses pass a text rule; the sandbox proxy needs a denylist.
- **Local writers of runner state.** Any server session that can write `system/logs/nightshift/` can redirect delivery and hide alerts.
- **The plan behind a branch.** A plan's base branch can move after `add`, which changes the plan text that runs. It is the owner's branch, so this is a git-side issue.

## Risks

- The stricter output rule fails queued orders that target other folders. Each one gets an alert, and the owner queues it again.
- A smaller `context/` gives research that relied on meeting notes less to work from.
- The pre-loop refusal stops that tick's other orders for one tick, as today.

## Size

One PR.
