# Work Orders: one corepack home for the install and the sealed verify

**Date:** 2026-10-15
**Status:** Draft. Plan: `docs/superpowers/plans/2026-10-15-orders-corepack-home.md`.
**Issue:** #189 (follow-up to #138 and #156; builds option 1 of the issue).

## 1. Problem

A live Work Order on a pnpm codebase blocked at verify. `order_install` ran with the network open and exited 0. The first verify command, `pnpm -r typecheck`, exited 1: `pnpm` on the toolchain PATH is corepack's shim, which tried to download the version pinned in `package.json`'s `packageManager` field inside the sealed verify, and the registry lookup failed (`EAI_AGAIN`). Corepack keeps its downloads under `COREPACK_HOME` (default `~/.cache/node/corepack`). Each sandboxed step gets a fresh, empty `$HOME`, so the pnpm the install step fetched was gone by verify.

## 2. The rule

- `verify_sha` makes the item's verify directory a container: the private checkout at `<vdir>/checkout` and the corepack home at `<vdir>/corepack`, where `<vdir>` is `nightshift-<id>-verify` under `order_workspace`. The corepack home is outside the checkout, so git never sees it, and the one `rmtree` of `<vdir>` that removes the checkout today removes it too (in `verify_sha`'s `finally`, and in `_reconcile` after a killed runner).
- Every sandboxed step of the item, install and verify, gets `COREPACK_HOME=<vdir>/corepack` and `COREPACK_ENABLE_DOWNLOAD_PROMPT=0`. The install step binds the directory writable; each verify command binds it read-only. Both binds come after the `$HOME` tmpfs, so the directory shows through even when `order_workspace` sits under `$HOME`.
- The install step's corepack download is what verify runs. Corepack reuses a version it finds in its install folder by reading that folder's `.corepack` file and writes nothing (corepack's `installVersion`), so a read-only home serves a pinned `packageManager` version.
- `COREPACK_ENABLE_DOWNLOAD_PROMPT=0` keeps a download from ever waiting on a prompt. The corepack bundled with current Node prompts only when the variable is `1` and stdin is a terminal, which the runner never has; the variable holds that for other corepack versions too. It is set for verify as well as install: a download there fails at once on the missing network.
- No config key. A codebase that does not use corepack sees two unused variables and an empty directory.

**Ruling: the plan session gets no `COREPACK_HOME`.** The session ends before `verify_sha` creates the item's corepack home, so pointing the session at it would mean a directory that does not exist yet. The session keeps the owner's real `$HOME` (`session_env()` carries `HOME`, and the Claude sandbox denies reads of named paths without hiding `$HOME`), so its corepack shim finds the versions under the owner's `~/.cache/node/corepack`, where the owner's own runs put them. #156's PATH prepend makes the tools visible to the session; where corepack keeps its downloads is a separate question that the owner's cache already answers. The session's environment stays the eight named variables the manual lists. If a session needs a version the owner's cache lacks, its download depends on `order_hosts` and on the session sandbox letting it write `~/.cache`; this spec does not change that, and no run has shown it yet.

## 3. What stays sealed

- Verify still has no network (`--unshare-net`); the install is still the only sandboxed step with it.
- The corepack home is read-only in verify, so a verify command cannot change the package manager the next command runs.
- Nothing in the corepack home reaches the pushed commit: it lives outside the checkout, in the throwaway verify directory of the runner's own repository.
- `$HOME` and the environment stay empty apart from the toolchain binds, the checkout and the corepack home.

## 4. Changes

- `nightshift_deliver.py`: `bwrap(workdir, cmd, toolchain=(), net=False, corepack_home=None)` binds the home (`--bind` when `net`, else `--ro-bind`) and sets the two variables; `run_verify` and `run_install` pass it through; `verify_sha` builds `<vdir>/checkout` and `<vdir>/corepack` and passes the home to both steps.
- `FOUNDRY.md` Work Orders: the sentence that says a corepack-downloaded pnpm is gone by verify now says the install's corepack download is kept for verify, read-only.
- `docs/superpowers/specs/2026-10-13-orders-toolchain-design.md` §2: the matching sentence points here.

## 5. Tests

- pytest `test_nightshift_deliver.py`: the install and the verify argv carry the same `COREPACK_HOME`, writable in install and read-only in verify, bound after the `$HOME` tmpfs, outside the checkout (argv check, no bwrap needed). With bwrap, and `order_workspace` under a `$HOME` the sandbox empties: a fake `corepack`-like tool on the toolchain PATH writes into `$COREPACK_HOME` during install and verify reads it back; a verify command that writes into `$COREPACK_HOME` fails.
- pytest `test_nightshift_run.py`: the end-to-end plan item with the fake tool as `order_install` reaches `done`, its verify reading the install's download.
- bats `commands.bats`: `FOUNDRY.md` names `COREPACK_HOME`.

Each fails before the change. The bwrap cases skip with a reason when bwrap is absent, as the existing ones do. Bound tools: pytest, bats and the gate.

## 6. Rollout

No owner action. The next Work Order on a corepack codebase keeps the install's download for verify. A codebase that installed pnpm globally into its nvm toolchain as the workaround (option 3 of #189) keeps working: a real `pnpm` binary ignores `COREPACK_HOME`.
