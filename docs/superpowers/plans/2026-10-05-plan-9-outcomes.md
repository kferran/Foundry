# Plan 9 outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-05 (plan: `2026-10-05-plan-9-foundry-rename.md`, commits 0ef78bf..5b2d6db plus this status commit). Planned in a scratch clone by a subagent and proven on a fresh clone by the controller; executed natively on the Debian host (each task's tests red, then green), then one whole-branch review on Opus. Acceptance: `docs/superpowers/spikes/2026-10-05-plan-9-acceptance.md`.

Final verification at 5b2d6db: `verify_setup.sh` exit 0 (16/16) on the Debian host (Debian 12.15, jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2); lint 0 errors. Live acceptance PASS, $0.63.

**Next on the roadmap:** set up the real vault (one server, one client) from the merged `master`; then Plans 7 and 5 once it has run for a few weeks, then Sub-project 2 (the Foreman orchestrator) on the capability seam.

## Rulings

- Spec: Ruling: personas live under `system/agents/` (`foreman.md`, `workcells/`), at the user's correction (2026-10-05) — cost if wrong: none.
- Spec: Ruling: the old-name tests cover only the files the template owns (`OWN`), so a user's note saying "fleet" or "crew" never fails the gate; the template URL is read from `system/template_source` at run time and never written in a test — cost if wrong: an old name inside a user-owned folder of the template goes unnoticed.
- Spec: Ruling: "Chief of Staff" is dropped; "ship" and "scout" are session kinds reserved for Sub-project 2, not capabilities — cost if wrong: two prompt lines.
- Planning: Ruling: the persona moves happen with the capability seam (Task 1), not in the rename script; `system/codebases/example.md` gets its own pathspec in the old-name tests; the names line goes into the four earlier specs only — cost if wrong: none (the spec was updated to match).
- Execution: Ruling: the plan's commit messages carry the session trailers (Global Constraint) — cost if wrong: none.
- Final: Ruling: a leftover `agent_owner` written by a model publishes with an unknown-field warning (as every unknown field always has); no prompt or template mentions it any more and no vault exists, so no forbidden-key check was added — cost if wrong: such a note is missing from the "By capability" dashboard until fixed (lint warns).

## Final-review fixes

None needed: no Critical findings; the one Important finding left for execution was Task 4, done above.

## Deferred minors

- The capability-union test prints only the Workcells' union on failure, not the concept enum.
- Review Focus 3 says "at commit time": the hook checks the `workcell` schema only; the union, duplicate and name-pattern rules are checked by the gate.
- README's repository layout lists `foundry-{intake,brief,debrief,focus}` without `sync` (older than this plan).
- `vault_index.py related` and `query` can return the persona files (unchanged exposure).
