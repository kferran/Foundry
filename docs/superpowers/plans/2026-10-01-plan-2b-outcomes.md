# Plan 2b outcomes: rulings and deferred minors

Recorded from the execution ledger on 2026-10-02 (plan: `2026-10-01-plan-2b-operations.md`, commits 34c09cf..a5248b8, executed inline with one final whole-branch review).

Final verification at a5248b8: `system/scripts/verify_setup.sh` exit 0 (bats codebases, focus, headless, lib, prep, remote, scripts, setup, units, vault_integrity all PASS; pytest 317 passed); `lint_vault.sh` 0 errors, 4 pre-existing README warnings.

**Gate:** still in force: do not run `install_units.sh` or `update_template.sh` against a real session until Plan 4 rewrites the commands (see the roadmap).

**For Plan 4:** `/setup` step 4 must call `setup_remote.sh --detect` first and act only after the user answers; in this repo `origin` is the template.

## Rulings
- Ruling: leave .claude/settings.json untouched and never stage it; the gate for every task is "no failures except vault_integrity 'settings files are valid JSON with the deny list and read fence'" — the edit is the user's to keep or revert; touching it is a security-relevant change — cost if wrong: a real regression in that one test would be masked (the committed file is unchanged by this plan, so none can come from it). Retired 2026-10-02: the user reverted the edit, and the gate has been fully green since.
- Ruling: D15 template URL https://github.com/kferran/jarvis.git accepted — user said "proceed" after the plan flagged it — cost if wrong: one-line change to system/template_source.
- Task 6: Ruling: Step 3's git rm empties and removes system/systemd/, so Step 4's writes fail — mkdir -p system/systemd before writing the templates (plan omission; the spec layout keeps the directory) — cost if wrong: none
- Final: Ruling: re-graded Minor 2 (update_template.sh default-branch lookup breaks under a non-English locale) to Important — a user on a German locale can never pull an update — cost if wrong: none (LC_ALL=C).
- Final: Ruling: Important 3 (setup_remote.sh has no detect-only mode for /setup step 4) fixed now with --detect rather than deferred to Plan 4 — it guards the maintainer repo whose origin is the template — cost if wrong: one unused flag.
- Final: Ruling: Important 2 fixed in update_template.sh only; install_units.sh keeps `enable --now` on every run, because spec §6.10 makes enabling part of install and /setup re-runs are explicit — cost if wrong: re-running /setup re-enables a unit the user disabled by hand.
- Final: Ruling: two of the new tests were defective before the fix pass and were corrected — the locale test needs LC_ALL=en_US.UTF-8 (the only installed locale) for git to translate, and template_setup now copies .gitignore so the index.db that install_units creates does not dirty the tree — cost if wrong: none.

## Final-review fixes
- fixed debrief_prep failures reported as success — "a failing index query is recorded and writes no digests.md", "a codebase whose git log fails is recorded, not reported as idle" RED→GREEN, prep 13/13.
- fixed update_template installs units in a vault that never installed them — "update_template leaves units alone in a vault that never installed them" RED→GREEN, remote 19/19.
- fixed setup_remote has no detect-only mode — "--detect reports the case and changes nothing" RED→GREEN.
- fixed locale-dependent default branch — "update_template finds the default branch under a non-English locale" RED→GREEN.

## Deferred minors
- discover_codebases.sh prints nothing when the start dir itself has a pruned name (bin, vendor, dist, target…) — add -mindepth 1.
- setup_remote.sh exits 1 with no message when system/template_source is missing (head fails under pipefail before die).
- debrief_prep.sh digest heading shifts columns when a field is empty (IFS tab is whitespace).
- install_units.sh replaces a symlinked unit with a regular file; a dangling symlink skips the ownership check.
- install_units.sh re-points units whose owning vault is merely unmounted.
- .claude/commands/setup.md still references the deleted brain-*/ultron-telemetry units (Plan 4 rewrites it).
- brief_prep.sh `timeout 60 gcalcli` lacks `-k 5`.
- setup_remote.sh ls-remote can still hit ssh host-key/passphrase prompts (add GIT_SSH_COMMAND='ssh -o BatchMode=yes').
