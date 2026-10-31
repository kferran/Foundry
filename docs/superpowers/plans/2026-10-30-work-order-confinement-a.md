# Work Order confinement, PR A (runner confinement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Work Order session cannot read a `.env` file, another order's folder or runner state; a research host that resolves to an internal address is refused; runner state moves out of the vault.

**Architecture:** One helper, `nightshift_report.state_dir(vault)`, puts `items/`, `alerts.json` and `health-*.json` under `<order_workspace>/state/`, and the tick moves the old files there once. `nightshift_check.resolve_problems(hosts)` resolves research hosts at add and once before a session starts. The three profiles deny `.env` by anchored globs; a Work Order session's sandbox also denies the whole workspace and re-opens only its own folder, while `--restricted` keeps the Read tool inside that folder.

**Tech Stack:** Python (`system/scripts/vaultlib/`), JSON settings profiles, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-30-work-order-confinement-design.md` §3.2, §3.3, §3.4 and §6 item 1 (approved by the owner's merge of #427, 2026-10-30)

## Global Constraints

- The Work Order runner and the session profiles are safety surfaces: the owner merges the PR.
- No test writes under the real home. Every test that reaches `record-usage`, `tick`, `report`, `Ctx.alert`, `triage.hold` or `notify` sets `order_workspace` in its vault's config or `HOME` to a temp directory.
- The daily report `system/logs/nightshift/<date>.md` and the ledger `system/logs/nightshift-YYYY-MM.jsonl` stay in the vault (spec §3.4).
- Owner-set `order_hosts` are never resolved (spec §3.2).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Run only the changed files' suites locally (`system/scripts/test.sh <paths>`); CI is the gate.
- `headless.settings.json` changes, so a live acceptance runs in a throwaway clone under `.scratch/` with the real `claude` (one brief, one research order, one plan order), then the clone is deleted.
- Template rule: no hostname, user path, remote URL, distro, account ID, or employer, client, codebase or people names in any committed file.

## Rulings against the spec

- **Ruling 1, the workspace deny is sandbox-only** (§3.3 "the Read tool gets the same pair"): `profile()` mirrors each deny entry as a `Read(//…)` rule, and a deny rule beats an allow rule, so a mirrored `Read(//<order_workspace>/**)` refused the session's own folder (probe S1, 2026-10-30). The Read tool is already confined to the session's working directory by `--restricted` ("is outside …; --restricted confines …"), so siblings are refused without a rule (probe with the working directory inside the workspace: the own file read, a sibling refused by both Read and Bash). The spec's fallback clause foresaw this; the form that holds is recorded in the spike note. Cost if wrong: a later Claude Code that drops `--restricted`'s confinement opens siblings to the Read tool; the live acceptance probe would catch it.
- **Ruling 2, the add-time DNS check goes in `_add`** (§3.2 says `research` calls it): the `research` subcommand is PR B. `_add` calls `resolve_problems` for a research order now; PR B moves the call with the subcommand. `nc.check()` stays network-free apart from git. Cost if wrong: none; PR B owns the move.
- **Ruling 3, the upstream report is drafted, not filed** (§3.3 "goes to the Claude Code repository"): filing on a public third-party repository under the owner's account is an outward action. The draft goes in the spike note and the PR body lists filing it as the owner's call.

## Review Focus

1. A vault whose `order_workspace` is a symlink: the sandbox deny and the allow-back name both the given and the resolved path, so bwrap's real-path binds match.
2. An order in flight across the update (`items/<id>/` holding `session.pid`, `claim-N`, `delivery.json`): the first tick moves it into `state/` before `_screen`, and the order resumes or delivers.
3. A research host that resolves to an IPv4-mapped IPv6 address (`::ffff:127.0.0.1`) or a multicast address is refused.
4. `triage.hold` and `notify` on a vault with no `state/` folder yet (a client): no crash, no hold, no notice.
5. A codebase registered with a `path` outside the home directory: its `<path>/**/.env` globs reach the session's sandbox and Read rules; a `path` inside home adds nothing (the home globs cover it).

---

### Task 1: Runner state under `<order_workspace>/state/` (§3.4)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_report.py` (`state_dir`, `item_dir`, `write_health`, `record_usage`, `_outcomes`, `data`)
- Modify: `system/scripts/vaultlib/nightshift_run.py:110,618,690,699,775,783,801,814,876` (every `rep.DIR` state path and `rep.item_dir` use), `tick()` (migration)
- Modify: `system/scripts/vaultlib/triage.py:34,113`, `system/scripts/vaultlib/notify.py:243`
- Test: `system/tests/python/test_nightshift_run.py`, `test_triage.py`, `test_notify.py`, `test_intake.py`, `test_nightshift_parallel.py`; `system/tests/headless.bats:201-212`, `meetings.bats:82-83`, `triage.bats:116-117`; `extensions/console/tests/python/test_contract.py:29`

**Interfaces:**
- Produces: `rep.state_dir(vault) -> Path` (`nc.workspace(nc.config(vault)) / "state"`); `rep.item_dir(vault, id)` now `state_dir(vault) / "items" / id`; `rep.migrate_state(vault) -> list[str]` (the names it moved).

- [ ] **Step 1: Write the failing tests** in `test_nightshift_run.py`:
  - `test_state_lives_under_the_workspace`: a tick that finishes an order writes `<ws>/state/items/<id>/outcome.json` and `<ws>/state/health-<date>.json`, writes `system/logs/nightshift/<date>.md`, and leaves no `system/logs/nightshift/items`.
  - `test_first_tick_moves_old_state`: seed `system/logs/nightshift/items/<id>/outcome.json`, `alerts.json` and `health-<date>.json`; after `tick`, each is under `<ws>/state/` with the same bytes and gone from the vault; a second seed of `alerts.json` with `state/alerts.json` already present is left in place.
  - In `test_triage.py`, `test_hold_reads_state_usage`: a `health-*.json` with `usage5: 0.9` under `<ws>/state/` holds; the same file under `system/logs/nightshift/` does not.
  - In `test_notify.py`, the existing outcome-notice test seeds `<ws>/state/items/…` instead.
- [ ] **Step 2: Run them.** `system/scripts/test.sh system/tests/python/test_nightshift_run.py system/tests/python/test_triage.py system/tests/python/test_notify.py` → the new tests FAIL (paths under `system/logs/nightshift/`).
- [ ] **Step 3: Implement.** `state_dir` and `migrate_state` in `nightshift_report.py`; `migrate_state` moves `items/*`, `alerts.json` and `health-*.json` from `<vault>/system/logs/nightshift/` with `shutil.move`, skipping a name already present under `state/`. Every state path in the files listed goes through `state_dir`/`item_dir`; `triage.HEALTH_DIR` goes; `notify` gets the vault it already has. `tick()` calls `rep.migrate_state(ctx.vault)` first and logs one ledger line naming what moved.
- [ ] **Step 4: Point the other suites at a temp workspace.** Each bats and pytest site listed under Test sets `order_workspace` (or `HOME`) to a temp path and reads or seeds state under it; `headless.bats:201` checks no `state/` was created instead of no `system/logs/nightshift`.
- [ ] **Step 5: Run the changed suites** → PASS.
- [ ] **Step 6: Commit** `feat(orders): runner state moves to <order_workspace>/state/ (#320)`.

### Task 2: Research hosts that resolve inside the network (§3.2)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py` (new `resolve_problems`)
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_add`, `run_item` before line 626)
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `nc.resolve_problems(hosts) -> tuple[list[str], list[str]]`: (internal, unresolved). Internal: `host <h> resolves to <a>, an internal address`. Unresolved: `host <h> does not resolve`.

- [ ] **Step 1: Write the failing tests** with `socket.getaddrinfo` monkeypatched in `nightshift_check`:
  - `test_internal_addresses_are_refused`: `127.0.0.1`, `10.0.0.1`, `169.254.169.254`, `::1`, `::ffff:127.0.0.1` and `224.0.0.1` each yield one internal problem naming the host and address; `93.184.216.34` yields none.
  - `test_unresolvable_host`: `socket.gaierror` yields one unresolved problem.
  - In `test_nightshift_run.py`: `test_add_refuses_internal_and_unresolvable_research_hosts` (exit 2, `not ready: host … internal address`, no note written); `test_session_start_fails_internal_host` (a queued research order whose host now resolves to `10.0.0.1` ends `failed`, reason `host`, its Needs-you line names the host, no session ran); `test_session_start_leaves_unresolvable_queued` (state stays `queued`, `attempts` unchanged, one ledger line, no session); `test_order_hosts_not_resolved` (a plan order on a codebase with `order_hosts: ["*.npmjs.org"]` starts with the resolver stub raising on any call).
- [ ] **Step 2: Run them** → FAIL (`resolve_problems` not defined).
- [ ] **Step 3: Implement** `resolve_problems` with `socket.getaddrinfo(h, None)` and `ipaddress.ip_address(a)` (an IPv4-mapped address is checked as its `ipv4_mapped`), refusing `not is_global or is_multicast`. `_add` calls it for a research order after `nc.check` passes and prints both lists as `not ready:` lines. `run_item` calls it for a research order before the `running` update: internal → `_finish` with `{"state": "failed", "reason": "host", "needs": [<problem>; "remove the host and queue <id> again"]}`; unresolved → `ctx.log({"item": id, "state": "queued", "reason": "host does not resolve"})` and return 0.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(orders): refuse research hosts that resolve to internal addresses (#318)`.

### Task 3: What a session cannot read (§3.3)

**Files:**
- Modify: `system/headless.settings.json`, `system/nightshift/plan.settings.json`, `system/nightshift/research.settings.json`
- Modify: `system/scripts/vaultlib/nightshift_session.py` (`profile`), `system/scripts/vaultlib/nightshift_run.py` (`_deny`, `_run_session`)
- Modify: `docs/superpowers/spikes/2026-10-30-env-glob-and-workspace-deny-probe.md` (the Read-tool probes, the upstream report draft)
- Test: `system/tests/python/test_nightshift_session.py`, `test_nightshift_run.py`; the bats test that checks `headless.settings.json` (find it with `grep -rn "env\*" system/tests`)

**Interfaces:**
- Consumes: `rep.state_dir` (Task 1), only to name what the workspace deny covers.
- Produces: `ss.profile(vault, kind, hosts, web_hosts=(), deny=(), *, cwd, fence=None)`: `fence` is the order workspace; when set, `sandbox.filesystem.denyRead` gains the workspace (given and resolved) and `allowRead` gains `cwd` (given and resolved), with no `Read(…)` mirror. `_deny(ctx, fm)` adds `<p>/**/.env` and `<p>/**/.env.*` for every registered codebase `path` and for the workspace when they lie outside the home directory.

- [ ] **Step 1: Write the failing tests:**
  - `test_profiles_use_anchored_env_globs`: each of the three JSON files has `~/**/.env` and `~/**/.env.*` in `denyRead` and no `**/.env*`; `headless.settings.json` has `Read(~/**/.env)` and `Read(~/**/.env.*)` and no `Read(//**/.env…)`.
  - `test_profile_fences_the_workspace`: `profile(..., cwd=ws/nightshift-x, fence=ws)` → `denyRead` holds `ws`, `allowRead` is `[ws/nightshift-x]`, and no `permissions.deny` entry starts with `Read(//<ws>`; with a symlinked `ws`, both forms appear in each list.
  - `test_deny_adds_env_globs_outside_home`: a codebase at `/srv-like temp path` outside `HOME` adds its two globs (mirrored as `Read(//…)` rules by `profile`); a codebase under `HOME` adds none.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement.** Swap the globs in the three JSON files. `profile` takes `fence`; `_run_session` passes `fence=ctx.workspace`; the self-test keeps no fence. `_deny` appends the outside-home globs. Keep the existing `Read(//…)` mirror for every `deny` entry.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Update the spike note:** add the Read-tool table (S1, S2, S3 and the production-shape case), replace "Not checked: … the Read tool" with what is still not checked (Glob, Grep, paths outside home, an interactive session), and add `## Upstream report (draft)`: a `denyRead` or `Read(//**/…)` entry whose first segment is a wildcard masks nothing on Linux, silently; ask for a warning when settings load. No vault details.
- [ ] **Step 6: Commit** `feat(orders): anchored .env globs and a workspace fence for sessions (#326, #319)`.

### Task 4: Docs, change file, core cap

**Files:**
- Modify: `FOUNDRY.md:122` (Work Orders: the session's read fence, the DNS check, where runner state lives), `FOUNDRY.md:126` (the usage reading's new path), the Security model's deny list
- Create: `changes/2026-10-30-work-order-confinement-a.md`
- Modify: `system/tests/vault_integrity.bats:9` (`CORE_CAP`) and its reason comment near line 521

- [ ] **Step 1:** Edit FOUNDRY.md in place: `system/logs/nightshift/health-<date>.json` becomes `<order_workspace>/state/health-<date>.json`; the session denies `.env` files under home, codebases and the workspace, other orders' folders, `nightshift-runner.git` and `state/`; a research host that resolves to a loopback, private, link-local, multicast or metadata address is refused at add and fails the order at start, and one that does not resolve waits for the next tick.
- [ ] **Step 2:** Write the change file (what changed for a vault owner: state moves on the first tick; nothing to do).
- [ ] **Step 3:** Run `system/scripts/test.sh system/tests/vault_integrity.bats`; raise `CORE_CAP` by the measured overrun with a comment `# 15,510 -> N (#320/#318/#326 PR A, owner to approve at merge): …`.
- [ ] **Step 4:** Run `system/scripts/test.sh system/tests/vault_integrity.bats system/tests/conformance.bats` → PASS.
- [ ] **Step 5: Commit** `docs(orders): PR A confinement in FOUNDRY.md, change file, core cap`.

### After the tasks

- Live acceptance in a throwaway clone under `.scratch/` (Global Constraints), including a seeded `.env` in the session's folder and a sibling order's file, read from Bash and the Read tool; both refused. Delete the clone.
- Whole-branch review, then the PR ("Part of #402"; `Closes #318, #319, #320, #326`; #317 and #321 stay open for PR B), naming for the owner: the merge, the core cap raise, and filing the upstream report.
