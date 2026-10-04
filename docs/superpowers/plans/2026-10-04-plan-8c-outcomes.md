# Plan 8c outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-04 (plan: `2026-10-04-plan-8c-sync.md`, commits 6665dec..bd2ea00 plus this status commit). Executed subagent-driven on the Debian host. For each task, an implementer applied the plan's tested patches red-then-green and a task reviewer read the diff. Then came one whole-branch review on Opus and one fix wave, each fix test-first. Acceptance: `docs/superpowers/spikes/2026-10-04-plan-8c-acceptance.md`.

Final verification at bd2ea00: `verify_setup.sh` exit 0 (16/16) on the Debian host (Debian 12.15, jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2); lint 0 errors. Live acceptance PASS, $0.84.

**Next on the roadmap:** set up the real vault, one machine as `server` and one as `client`.

## Rulings

- Ruling: brief drop-in timeout 45 min, not the spec's 35. The spec's 35 assumed a 20-min base; Plan 8d raised the brief to 30, and plan D4 keeps the spec's formula (base + 15) — cost if wrong: a stuck brief holds `run.lock` 10 min longer.
- Ruling: the timeouts live in the drop-in so only a server changes (plan D4); spec §5.2's drop-in sample omitted them — cost if wrong: none; standalone keeps Plan 8d's values.
- Ruling: the controller extracted each task's patches from the plan verbatim into files, so implementers applied exact bytes — cost if wrong: none (`git apply --check` guards).
- Task 4: Ruling: the Global Constraint "systemctl is always a stub" beats the plan's test text. `sync.bats` `setup()` now writes a logging `systemctl` stub exported as `SYSTEMCTL`, and the client-conflict test sets both run times to 00:00 and asserts the pending branch is deleted. Two server-role tests had reached `start_missed` and called the real `systemctl --user start` during the day; this host had no jarvis units and the journal was empty, so nothing started — cost if wrong: none; tests only.
- Task 6: Ruling: spec §5.4's "resolution, on either machine" recipe was a no-op on the machine that pushed the pending branch (its HEAD already is that side). README and spec now say: the other machine merges `origin/jarvis/<role>-pending`; the machine that pushed it merges `origin/<branch>` — cost if wrong: none; docs only.
- Ruling: the final whole-branch review ran on Opus, the session model, as in Plans 8b and 8d, because the ranking between the top models is unclear — cost if wrong: a weaker final pass.
- Final: Ruling: every git call in `vault_sync.sh`, the `timeout git` in `net()` and the `systemctl` call run with `run.lock`'s fd 9 closed, through a `git()` wrapper — cost if wrong: none.
- Final: Ruling: the fetch prunes, and the clearing step checks the local `origin/jarvis/<role>-pending` ref in place of `ls-remote`. A completed push deletes this role's pending branch whenever it exists, marker or not: only this role pushes it, and a failed delete retries next tick — cost if wrong: a pending branch pushed by hand under this role's name is deleted on the next sync.
- Final: Ruling: `/setup` phase 4 runs its three checks for every `private` vault, standalone included. Check 3 also points the upstream at `origin/<branch>` when the branch already exists there. Spec §3.2 notes both — cost if wrong: a standalone private user sees two extra checks in `/setup`.
- Final: Ruling: the default `GIT_SSH_COMMAND` applies only when `core.sshCommand` is unset (spec silent) — cost if wrong: none.
- Final: Ruling: `SuccessExitStatus=4` on `jarvis-sync.service`, and spec §5.2's timeout line now matches the units. M2 (systemd may re-arm `TimeoutStartSec` per command, which would make the +15 min unnecessary; not checked on a live unit), M3 (a refused commit stops the fetch, so a fix pushed from a client cannot arrive; the order is spec-mandated) and M4 (the blocked alert names intake, brief and debrief on every role) stay deferred — cost if wrong: M4 shows a misleading alert line on a standalone or client vault.
- Acceptance: Ruling: the bare origin's `HEAD` was pointed at the plan branch so the client clone checked something out; a real origin publishes the vault's own branch — cost if wrong: none.

## Final-review fixes

- fixed `run.lock`'s fd 9 leaking into git's children: a credential-cache daemon or a detached `gc --auto` kept the lock after the sync exited, so a brief waited 600 s, exited 6 and was lost for the day. `sync.bats` "git children and systemctl run with run.lock's fd 9 closed" RED→GREEN; the re-review confirmed by mutation that the test fails without the fix. The `/proc` cwd check also gained a trailing-slash match, so `/x/vault2` cannot mask `/x/vault`.
- fixed stale `origin/jarvis/*-pending` refs: without `--prune`, `/backup` on the other machine reported a resolved conflict forever. Two `sync.bats` tests RED→GREEN.
- fixed a `private` vault whose upstream is `template/<branch>` (a renamed plain clone) or unset failing every `/backup` with no way out through `/setup`. `commands.bats` "/setup phase 4 checks every private vault and sets the upstream to origin" RED→GREEN.
- fixed the default `GIT_SSH_COMMAND` overriding a user's `core.sshCommand`. `sync.bats` RED→GREEN.
- fixed a busy lock (exit 4) marking `jarvis-sync.service` failed: `SuccessExitStatus=4`, pinned in `units.bats`.
- spec §5.2 now states brief 30→45, debrief 20→35, intake 90→105.

## Deferred minors

- The pre-commit hook scans binary files too (spec says "text file"); a binary holding both marker lines is a rare false positive.
- A crash between writing a drop and appending its record duplicates the drop on the next tick (the order is the safe one; a comment would help). `inbox.mkdir` runs inside the per-block loop. The same text twice in one briefing is extracted once, with no test pinning it.
- `system/template_source` is read without trimming whitespace (`setup_remote.sh` uses `tr -d '[:space:]'`).
- A hook failure inside `commit_runs.py` alerts twice. Configuration failures write `sync-state.json` before the lock.
- No test for unmerged entries without `MERGE_HEAD`, for an exhausted deadline, or for `start_missed`'s "time not yet passed" branch. The `chmod 000` test fails when run as root, and the TERM test relies on bash exec-optimizing `$(…)`.
- A failed pending-branch push still tells the user to merge a branch that does not exist, and re-alerts "could not push" on every blocked tick (it self-heals: each blocked tick pushes again).
- `block()` rewrites `time:` on every blocked cycle (the last attempt, not when the block started).
- Empty-array expansions under `set -u` need bash ≥ 4.4 (older exposure; the floor is bash 5). No test asserts that drop-ins appear in `install_units.sh --dry-run`.
- `backup.md` step 3 is one long paragraph holding two procedures, and says "In `private`" before step 6 explains `remote_mode`; it does not mention exit 2 (unreachable from `/backup`).
- The client `raw/inbox/` lint warning counts top-level files only.
- The README test for the removed by-hand sentence passes if the README path is wrong.
- The README code-block comment about `client-pending` reads oddly under "on the other machine", and the recipe does not say to bring the other machine up to date first.
- M2, M3 and M4 from the final review (see the last Final ruling).
