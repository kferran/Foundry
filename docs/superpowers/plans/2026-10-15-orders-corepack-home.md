# Orders Corepack Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The install step's corepack download is what the sealed verify runs: every sandboxed step of a plan item gets one `COREPACK_HOME` inside the item's verify directory, writable for the install and read-only for verify.

**Architecture:** `verify_sha` turns its directory into a container (`checkout/` and `corepack/`); `bwrap()` gains one optional argument that binds the home after the `$HOME` tmpfs and sets `COREPACK_HOME` and `COREPACK_ENABLE_DOWNLOAD_PROMPT=0`; `run_verify` and `run_install` pass it through. The plan session is unchanged (spec §2 ruling).

**Tech Stack:** Python, bubblewrap, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-15-orders-corepack-home-design.md`

## Global Constraints

- Work on branch `feat/orders-corepack-home` in worktree `.scratch/corepack`. Commit there; do not push or open a pull request.
- Run suites through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, outside a sandbox. Never run the gate.
- Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_run.py`, `test_nightshift_session.py`, `test_nightshift_check.py`), bats (`commands.bats`).
- No new config key, no new dependency. Tests never touch the network or a real `corepack`.
- Template rule: no hostnames, user paths, remote URLs or names in any file.
- Commits use `git commit -F <scratchpad file>` and end with the session's `Claude-Session:` line.

## Review Focus

- Verify still runs with `--unshare-net`, and the corepack home is `--ro-bind` there; only the install binds it writable.
- The home's bind follows the `$HOME` tmpfs in the argv, so it shows through when `order_workspace` is under `$HOME`.
- The home is never inside the checkout, and the existing `rmtree` of the verify directory (in `verify_sha` and in `_reconcile`) removes it.
- `bwrap()` without the new argument builds exactly today's argv.

---

### Task 1: one corepack home for install and verify

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_deliver.py` (`bwrap`, `run_verify`, `run_install`, `verify_sha`)
- Test: `system/tests/python/test_nightshift_deliver.py` (after `test_a_failing_install_blocks_before_verify_with_the_exit_127_wording`); update the spy in `test_verify_sha_runs_the_install_first_with_network_and_keeps_it_out_of_the_commit` to accept the new argument.

**Interfaces:**
- Produces: `bwrap(workdir, cmd, toolchain=(), net=False, corepack_home=None)`; `run_verify(..., corepack_home=None)`; `run_install(clone, cmd, toolchain, log_path, corepack_home=None)`; `verify_sha` checks out into `<vdir>/checkout` and uses `<vdir>/corepack`.

- [ ] **Step 1: Write the tests** (cite #189):
  - `test_install_and_verify_share_one_corepack_home_outside_the_checkout`: `verify_sha` with a spy on `bwrap` recording argv; both calls set the same `COREPACK_HOME`, the install binds it `--bind`, verify `--ro-bind`, after the second `--tmpfs`, not under the checkout; both set `COREPACK_ENABLE_DOWNLOAD_PROMPT=0`.
  - `test_the_install_download_is_readable_in_verify_and_read_only_there` (bwrap): `$HOME` and the verify directory under a temporary home; a fake `corepack-pm` on the toolchain PATH writes `$COREPACK_HOME/v1/pm/1.0/.corepack` when called as `corepack-pm install` and reads it back as `corepack-pm run`; install `corepack-pm install`, verify `corepack-pm run` passes; a second run whose verify is `touch "$COREPACK_HOME/w"` fails.
- [ ] **Step 2: Run them red.** `system/scripts/test.sh system/tests/python/test_nightshift_deliver.py -k corepack`. Expected: FAIL (no `COREPACK_HOME` in the argv; the fake tool finds no home).
- [ ] **Step 3: Implement** the argument in `bwrap` (bind after the toolchain binds, mode by `net`, two `--setenv`), pass-through in `run_verify` and `run_install`, the container layout in `verify_sha`.
- [ ] **Step 4: Run the suite green.** `system/scripts/test.sh system/tests/python/test_nightshift_deliver.py`.
- [ ] **Step 5: Commit.** `feat(orders): one corepack home for the install and the sealed verify (#189)`.

### Task 2: end to end through a tick

**Files:**
- Test: `system/tests/python/test_nightshift_run.py` (after `test_a_codebase_item_runs_its_install_before_verify_and_the_session_sees_the_toolchain`)

- [ ] **Step 1: Write the test** `test_a_corepack_download_from_the_install_reaches_the_sealed_verify` (bwrap): `codebase_item` with the fake tool's directory as `order_toolchain`, `order_install="corepack-pm install"`, verify `test -f done.txt` and `corepack-pm run`; a tick ends `done`.
- [ ] **Step 2: Run it red** before Task 1's implementation (write it alongside Task 1's tests). Expected: FAIL, the item ends `blocked (verify)`. After Task 1 it passes.
- [ ] **Step 3: Run the suite.** `system/scripts/test.sh system/tests/python/test_nightshift_run.py`.
- [ ] **Step 4: Commit.** `test(orders): a tick carries the install's corepack download into verify (#189)`.

### Task 3: documents

**Files:**
- Modify: `FOUNDRY.md` (Work Orders paragraph: the sentence on what the install puts under `$HOME`), `docs/superpowers/specs/2026-10-13-orders-toolchain-design.md` (§2, the matching sentence)
- Test: `system/tests/commands.bats` (the order_toolchain test, one new `grep -qF` line for `COREPACK_HOME`)

- [ ] **Step 1: Add the grep**, run `system/scripts/test.sh system/tests/commands.bats -f 'order_toolchain'`. Expected: FAIL.
- [ ] **Step 2: Edit the manual and the spec.** Keep the fragments the existing test greps.
- [ ] **Step 3: Run `commands.bats` green.**
- [ ] **Step 4: Commit.** `docs(orders): the install's corepack download is kept for verify (#189)`.

### Task 4: suites

- [ ] Run `test_nightshift_run.py`, `test_nightshift_session.py`, `test_nightshift_check.py`, `test_nightshift_deliver.py`, `commands.bats`.
