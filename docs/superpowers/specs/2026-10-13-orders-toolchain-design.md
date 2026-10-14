# Work Orders: an install phase and toolchain paths for the sealed verify

**Date:** 2026-10-13
**Status:** Accepted 2026-10-14 (both owner decisions below taken as recommended). Plan: `docs/superpowers/plans/2026-10-14-orders-toolchain.md`.
**Issue:** #138.

## 1. Problem

The runner reruns a plan item's `verify` commands inside `nightshift_deliver.bwrap()`: the host read-only, `$HOME` an empty tmpfs, `--clearenv`, `PATH=/usr/local/bin:/usr/bin:/bin`, `--unshare-net`, and only the private checkout writable. A toolchain installed per user (nvm, volta, asdf, a `pnpm` under `~/.local/share`) is under `$HOME`, so the sandbox cannot see it, and a fresh checkout has no `node_modules`, so even a visible `pnpm` could not install them offline. A Work Order that finished 12 tasks blocked at verify with `pnpm install: exit 127`; the same checks passed by hand. The fix for #138's first ask makes the line say `(command not found in the sealed verify sandbox)`; this spec closes the second: let a codebase declare what the sandbox needs.

The service PATH (`install_units.sh`) is `<claude's dir>:~/.local/bin:/usr/local/bin:/usr/bin:/bin`, so the session itself already sees `~/.local/bin`; nvm, volta and asdf directories it does not.

## 2. Decisions

- **Two optional keys in `system/codebases/<name>.md`, beside `order_hosts`, `order_pr` and `order_plugins`.** `order_toolchain`: a list of directories (`~` allowed) that hold the toolchain's executables. `order_install`: one shell command that installs the project's dependencies. Both are written by the owner in a tracked file, never by a session. No old `nightshift_*` names: the keys are new.
- **`order_toolchain` directories are bound read-only into the sandbox at their own paths and prepended to its PATH, in the listed order.** Nothing else from `$HOME` appears: the binds come after `--tmpfs $HOME` in the argv (bwrap mounts in order), so the rest of `$HOME` stays empty. The owner lists the directory that holds the real binaries (for nvm, `~/.nvm/versions/node/<version>/bin`); a shim directory that needs its manager's environment does not work under `--clearenv`, and the manual says so.
- **`order_install` runs once, first, in the same private checkout, with the host network namespace.** It is the only step with network; the verify commands then run offline as today. It logs to `verify.log` like a verify command, and a non-zero exit blocks the item as `verify` does, with the first Needs-you line `order_install: <command>: exit <code>`. The exit 127 wording from the fix applies to it too. An absent key skips the phase: nothing changes for a codebase that does not set it.
- **Owner decision (2026-10-14: the network stays open for the install command):** bwrap has no per-host filter; `--unshare-net` is all or nothing, so the install phase cannot be held to `order_hosts` the way `nightshift_session.profile()` holds the session. Recommendation: accept the open network for this one command. The command is the owner's text, the sandbox still hides `$HOME` and the environment, and the install cannot reach the pushed commit (`verify_sha` runs on a throwaway checkout of the runner's own repository). The risk to accept: the branch under test is the session's, so its lockfile decides what the install fetches and which install scripts run; an owner who wants no scripts writes them off in the command (`pnpm install --frozen-lockfile --ignore-scripts`).
- **Owner decision (2026-10-14: yes):** also prepend the `order_toolchain` directories to the session's PATH in `_run_session` (the `Popen` env), so the plan session can run the same tools during its tasks. Recommendation: yes; it is one line, and without it the session reports its own exit 127 while verify passes.
- **The readiness check stays command-free.** It refuses an `order_toolchain` entry that is not a directory and an `order_install` that is not a string, at queue time, with the file and key named.

## 3. Changes

- `system/schemas/codebase.md`: `order_toolchain: {kind: list, of: string}`, `order_install: {kind: string}`.
- `nightshift_deliver.py`: `bwrap(workdir, cmd, toolchain=(), net=False)` adds `--ro-bind <dir> <dir>` per directory after the `$HOME` tmpfs, builds PATH from the directories plus the fixed three, and drops `--unshare-net` when `net` is true. `run_verify` takes the toolchain; a new `run_install(vdir, cmd, toolchain, log_path)` runs the one command with `net=True`. `verify_sha` calls `run_install` before `run_verify` when the command is set.
- `nightshift_run.py`: `_deliver_plan` reads both keys with the codebase getter (`cb.get`; the keys have no old names, so no `nc.setting` fallback) and passes them; `_run_session` prepends the directories to the PATH of the environment it assembles for `Popen`. The Needs-you line keeps its `Fix the failing check:` prefix: `Fix the failing check: order_install: <command>: exit <code>`.
- `nightshift_check.py`: `_plan` adds the two readiness errors.
- `FOUNDRY.md`: the Work Orders paragraph names the two keys and the sentence on shim directories; `system/codebases/example.md` shows both keys commented in its body text.

**Existing vault:** no change until a codebase file sets a key. A vault with neither key runs exactly today's sandbox.

## 4. Tests

- pytest `test_nightshift_deliver.py` (bwrap cases): a directory listed in `order_toolchain` is visible and its executable runs by bare name; `$HOME` otherwise stays empty (`test ! -e "$HOME/.netrc"` with a `.netrc` beside the listed directory); the install argv has no `--unshare-net` and the verify argv has it (argv check, since the suite has no network); `verify_sha` with an install command that writes `installed` and a verify that reads it passes, and the runner's commit does not contain the file; an install that exits 127 reports `order_install: <command>: exit 127 (command not found in the sealed verify sandbox)`.
- pytest `test_nightshift_check.py`: a missing toolchain directory and a list-valued `order_install` are readiness errors naming the key; a codebase without the keys passes as before.
- pytest `test_nightshift_run.py`: the end-to-end plan item with `order_install` set runs it before verify (the log order in `verify.log`); the session's PATH starts with the toolchain directory (stub `claude` records its PATH).
- pytest `test_schema_notes.py`: the codebase schema accepts both keys.
- bats `commands.bats`: `FOUNDRY.md` names `order_toolchain`, `order_install` and the shim sentence.

Each fails before the change. Bound tools: pytest, bats and the gate.

## 5. Out of scope

- A per-host network filter for the install phase (needs a proxy or the Claude Code sandbox; neither is in the runner).
- Caching installs between items, or sharing a package store across checkouts.
- Toolchain managers' own environment (`NVM_DIR`, `VOLTA_HOME`, asdf shims): the owner lists resolved binary directories.
- Research items: they run no verify.
