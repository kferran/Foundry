# Plan 6 outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-03 (plan: `2026-10-02-plan-6-communication.md`, commits 2911669..abcbbe5 plus this status commit). Executed natively: the session implemented every task with red-then-green tests, then one final whole-branch review on the most capable model and one fix wave. Live acceptance: `docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md`.

Final verification at 24d98ab: `verify_setup.sh` exit 0 (14/14 suites), lint 0 errors. Live acceptance PASS at 938efd5 (Plan 4a steps 1–7) and at 24d98ab (brief with a seeded calendar, debrief, inbox ingest), every run exit 0 with 0 permission denials.

**Next on the roadmap:** Plan 8 (two machines: Omarchy laptop interactive, Debian server runs the automation).

## Decision for the user

- **Headless cost.** The self-edit makes each headless run cost about $0.07 more. Measured on the brief: +51,983 input tokens and +$0.075 (+40%: $0.185 → $0.260). The spec estimated ~5k tokens, but that counts the skill once, and billing counts it on every turn after the Read (mostly as cheap cache reads). Debrief and ingest have no baseline, so "about $0.30/day" for a brief, a debrief and a few ingests is an extrapolation; heavy-intake days cost more. If this is too much, have headless runs read only sections A, B, C and E of the skill.

## Rulings

- Task 4: Ruling: brief cost delta recorded as measured (+51,983 tokens, +$0.075), not the plan's expected 4–8k — the plan's range counted the skill once; the fail criterion (<3k, skill not read) is not met — cost if wrong: about $0.30/day more headless spend than the spec's estimate; the user decides.
- Task 4: Ruling: accepted `is_friction: true` (YAML bool) where Plan 4a's grep expects the literal `"true"` — the schema kind is bool and `v_concept` returns 1 — cost if wrong: none for brief and debrief; a literal grep elsewhere would miss it.
- Task 4: Ruling: `/humanizer` passes on "resolved and ran the v3.0.0 skill" — the project skill and the user's plugin are byte-identical, so the output can't show which ran — cost if wrong: untested live on a machine without the plugin.
- Task 4: Ruling: the acceptance record keeps the plan's filename (2026-10-02) though the runs happened 2026-10-03 — consistency with the plan's references — cost if wrong: cosmetic.
- Ruling: the final whole-branch review ran before Task 5 — the outcomes doc must record the review's fixes — cost if wrong: none.
- Final: Ruling: re-graded reviewer Minor 3 to Important — the skill's own "remove the sentence" rules (§23 on what a source doesn't show; section E) conflict with "Keep every fact", so the self-edit could delete an Unavailable Sources line the user relies on — fixed in the wave — cost if wrong: one extra sentence per command.
- Final: Ruling: the post-fix live re-run covered brief, debrief and inbox ingest, not the digest batch, re-brief or `related` steps — the fix is one clause that narrows cutting, and those steps passed at 938efd5 — cost if wrong: a digest-batch regression would surface on the first real intake run.

## Final-review fixes

- fixed: the frontmatter and staging clauses of the self-edit step were not pinned by any test (the plan's Review Focus 4 claimed they were); and the cut-versus-keep conflict above. `self_edit_contract` in `commands.bats` now also greps `leave frontmatter[ ,]`, `Headless, edit only` and "Where the skill says to cut a sentence, keep any fact it carries." RED (2 failing; with the clause present, deleting the frontmatter clause also failed) → GREEN; gate exit 0, 14/14 (24d98ab).
- fixed: no real calendar fact had gone through the self-edit, since every acceptance input was a negative. Live re-run at 24d98ab with 3 seeded calendar events: every start time, end time and title was kept and correctly paired, and the open windows were right (abcbbe5).

## Deferred minors

- `CLAUDE.md` rule 5 ("dashes sparingly") and humanizer §8 (no dashes in the final text) differ, so chat and headless notes follow different dash rules; this is not recorded as a decision.
- `LICENSE` is not checksum-pinned in `vault_integrity.bats` (its sha256 is in the plan).
- The acceptance record header says "run 2026-10-03", but the baseline brief ran 2026-10-02T21:31.
- `/humanizer` resolution could be shown directly (a marker line in the clone's `SKILL.md`, or the skill listing showing `humanizer` vs `humanizer:humanizer`).
- "$0.30/day" is extrapolated from one brief delta; days with many intake runs (up to the daily cap) cost more.
