# Plan 3 outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-02 (plan: `2026-10-02-plan-3-memory.md`, commits c7db765..a87d5fa, subagent-driven with a task review per task and one final whole-branch review). Live acceptance: `docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md`.

Final verification at a87d5fa: `system/scripts/verify_setup.sh` exit 0; `memory.bats` 29/29, `hooks_install.bats` 17/17, pytest 329 passed.

**Memory stays off** until the user installs the hooks: review `system/scripts/install_hooks.sh --dry-run`, then run it, or use `/setup` once Plan 4b adds the step.

## Rulings
- | T1–T4 → T5 | live acceptance | Ruling below |
- Ruling: Task 5 (live interactive acceptance) is run by the user as a manual checklist, not driven by the controller — user decided after discussion (what appears on screen in a real interactive session is the evidence) — cost if wrong: acceptance waits on the user; Task 6 waits on Task 5.
- Task 2: Ruling: Important (plan-mandated) "agent_id substring match undercounts sessions that edit files containing agent_id" — not fixed: tested that file content and tool output arrive as JSON strings, so their quotes are escaped (\"agent_id\") and the pattern does not match; the only real miss is a tool whose input is a nested object with an agent_id key (MCP tools), whose event goes uncounted — cost if wrong: an occasional uncounted event delays a digest request slightly.
- Task 3: Ruling: Important (plan-mandated) "slug built from unredacted digest text, so a secret on the first line reaches disk in the filename" — fix: redact first, derive the slug from the redacted text, and keep the redaction-count temp file out of raw/<p>/notes/ — spec §6.18/§6.17 step 2 (redact before write) outranks the plan's code order — cost if wrong: none.
- Task 4: Ruling: Important (plan-mandated) "rewrite drops settings.json mode to the umask default (600 → 644), exposing env secrets" — fix: preserve the original mode on the new file (and create temp files under umask 077); add a mode-preservation test — §7.3a limits user-level changes to the owned entries, and widening file permissions is not one — cost if wrong: none.
- Final: Ruling: fix Important 1–5 and Minor 1 (dry-run labels, consumed by Plan 4b's /setup) in one wave; I3 and I4 were deferred minors in the ledger, now upgraded by effect (junk digests likely in this vault; uninstall must restore foreign empty containers per §12) — cost if wrong: none.
- Final: parked — install+uninstall leaves "allow": [] when permissions had other keys but no allow — Ruling: parked to Plan 4b; harmless (an empty allow grants nothing) and a clean fix needs the installer to remember whether allow pre-existed — cost if wrong: a cosmetic empty array in the user's settings after uninstall.
- Final: parked — wall-clock assertion (< 30 ms avg) in gated memory.bats can flake on a loaded machine and would then block verify_setup.sh and /backup — Ruling: surfaced to the user to decide (recommend replacing it with a structural check: the hook contains no `read -d`) — cost if wrong: an occasional false gate failure.
- Final: Ruling resolved — user chose to replace the wall-clock assertion before the PR: structural check (no byte-wise read) plus the behavioral count, proven able to fail (a87d5fa); memory.bats 29/29, gate exit 0.

## Final-review fixes
- fixed frozen scope on SessionStart re-entry — memory.bats re-entry tests (both directions) RED→GREEN; fixed declined request re-asked — "declined request is not re-asked" RED→GREEN; fixed tag mention / empty block captured — 3 capture tests RED→GREEN; fixed PostToolUse byte-wise read — 100 KB 82.9 → 8.6 ms, 1 MB 414.6 → 45.7 ms; fixed dry-run labels — foreign-digest dry-run test RED→GREEN. Suite after the wave: memory.bats 29/29, hooks_install.bats 17/17, pytest 329, gate exit 0 (commits af8606b..9230b60).

## Deferred minors
- Task 1: recall.py:118 SECTION regex matches bare prose lines starting "Outcome"/"Follow up", re-enabling keep (plan-mandated regex).
- Task 1: recall.py:233 empty Outcome section falls back to body[:400], which can include Decisions text.
- Task 1: recall.py:241 non-TimeoutError refresh failures (corrupt db) propagate — carried to Task 2: the SessionStart hook must log and emit nothing on any recall failure.
- Task 1: test_recall.py negative substring asserts can collide with the tmp path in the hint line.
- Task 2: memory_activity.sh:158 counter read-then-write without a lock; parallel tool hooks can lose a count.
- Task 2: lib_memory.sh:111 mem_freeze writes .json before .eligible; a crash between them leaves the slow path on for the session.
- Task 2: lib_memory.sh:48 scope cache not invalidated by a deleted codebase file or a repo git-init'ed after registration.
- Task 2: lib_memory.sh:58 unused local; IFS tab read collapses empty fields.
- Task 2: memory_activity.sh:145 BASH_SOURCE dirname breaks when invoked without a slash (Claude Code uses absolute paths).
- Task 2: test gaps — frozen scope across a cwd change, codebase-session wall, invalid session_id, .out marker assertion.
- Task 2: mem_prune by mtime can prune a session idle > 14 days; next hook re-freezes from the current cwd.
- Task 2: memory.bats is mode 755; other bats files are 644.
- Task 3: a message that merely mentions <vault-digest>…</vault-digest> is captured; consider requiring the tag at line start.
- Task 3: stop_hook_active never read (safe: awaiting_digest prevents a double block).
- Task 3: test gaps — created_at offset value under a non-UTC tz, unterminated <vault-digest>, failed write leaves state unchanged, crew test asserts no alert.
- Task 3: a ?-ending reply while a request is outstanding still alerts (matches spec order).
- Task 4: backup name has 1 s resolution; install+uninstall in the same second overwrites the original backup.
- Task 4: empty foreign containers (allow: [], hooks.Notification: [], Stop [{hooks: []}]) are pruned.
- Task 4: well-formed but unexpected-shape JSON exits 5 with a raw jq error instead of exit 1 (file left intact).
- Task 4: --uninstall refuses when a hook file is missing or not executable; the escape hatch should not depend on them.
- Task 4: owned-digest check matches the marker anywhere and for any vault.
- Task 4: --dry-run prints internal digest labels (foreign/remove), not the documented ones — Plan 4b's /setup reads this output.
- Task 4: symlinked settings written in place; no trap cleans settings.json.tmp.$$ on failure.
- Task 4: test gaps — missing hook file, unwritable config dir, unchecked $status at hooks_install.bats:56 and :114.
- Task 4: owned entries matched by suffix from any root (plan D7) — a second vault's entries count as ours.
- Task 4: chmod --reference is GNU-only (Linux target per spec; note for macOS).
- Final: corrupted session state (null threshold) makes Stop exit 1 under set -u — only from a corrupted file.
- Final: multi-document settings.json ({} {}) passes the object check and is rewritten instead of refused.
- Final: .eligible not re-touched; mem_prune can delete it from a live >14-day session (slow path thereafter).
- Final: deleted codebase file does not invalidate the scope cache (compare the codebases dir mtime).
- Final: failed cache build leaves scope_cache.tsv.<pid> behind.
- Final: af8606b commit trailers lack a blank line before them (already pushed; cosmetic).
- Final: an empty <vault-digest> block shadows a later valid block in the same message (awk exits at the first close tag).
