# Note tags: reuse before inventing, one form, per-partition listings

**Date:** 2026-10-14
**Status:** Built (2026-10-15): PR #208.
**Issue:** #158. Owner's outcome (2026-10-14): find and group things in Obsidian.

## 1. Problem

`tags` is a required list on `concept` notes (`system/schemas/concept.md`) and optional on `index` and `rca`; the other schemas have none. No vocabulary exists: `/ingest` writes whatever tags the run picks (`ingest.md` line 39 says only "`tags` (a list)"), lint checks nothing about them, recall does not read them, and the index stores them (`tags(path, tag)` in `index.py`) without any command listing them. The fixtures show the drift in miniature: `tooling`, `streaming`, `hobby`, `now`, `rca`. In Obsidian the tag pane then fills with near-duplicates (`tooling`, `tools`, `Tooling`) and the owner cannot group notes by them.

## 2. Decisions

- **Open vocabulary, reuse first.** No fixed list. A new command, `vault_index.py tags [--partition work|personal|shared]`, prints each tag with its count from the index, most used first. `/ingest`'s prompt is told: query the partition's tags and reuse an existing tag before inventing one; invent only when no existing tag fits. **Owner decision:** open with reuse (recommended), or a closed list in a note the owner edits. Recommendation: open; a closed list is one more thing to maintain, and the count listing gives the same grouping.
- **One form, checked by lint.** A tag is lowercase ASCII kebab-case (`[a-z0-9]+(-[a-z0-9]+)*`), with `/` allowed between segments for Obsidian's nested tags (`project/alpha`). Spaces, uppercase, `#` and other characters are an `issue` of severity `warning` on existing notes (nothing published breaks) and `error` on a staged note, so the hook catches a new one. **Owner decision:** nested tags allowed (recommended) or flat only.
- **System tags are reserved.** Tags a script writes (`now` on the Now page, `rca` on RCA notes, `clearinghouse-change` if the watcher writes one) are listed in the spec and in `FOUNDRY.md`; lint warns when `/ingest` or a hand edit puts one on another note type.
- **No cross-partition vocabulary.** A work tag can name a client or a product, which is work content; the listing is per partition and nothing is written to `wiki/shared/`. A `shared` tag listing shows `shared` notes only. This is a rule, from the partition wall.
- **No new required field.** Only `concept` requires `tags` today. **Owner decision:** require at least one tag on every wiki note type, or leave it. Recommendation: leave it; the brief, meeting and RCA notes are found by date and key, and an empty required list is what people write to satisfy a rule.

## 3. Changes

- `vault_index.py tags [--partition P]`: `SELECT tag, COUNT(*) FROM tags JOIN notes … GROUP BY tag ORDER BY count DESC`, printed as `<count>\t<tag>`; partition from the note's frontmatter as the index stores it. Read-only, so it joins the `vault_index.py` read subcommands allowed in `.claude/settings.json` and in the per-run allow list `run_headless.sh` writes (a settings change: feature lane, the owner's review).
- `vaultlib/index.py` (the issues pass): the form rule and the reserved-tag rule as issues, `warning` for a committed note, `error` under `--staged`.
- `.claude/commands/ingest.md` line 39: the reuse instruction, with the command.
- `FOUNDRY.md` Memory section: one paragraph (form, reuse, reserved tags, the listing). `system/schemas/concept.md`: the form in the field's description.

## 4. Tests

`test_index.py` or `test_cli.py`: `tags` lists counts per partition and never mixes partitions; `test_lint.py` (or the issues tests): `Tooling`, `two words`, `#tag` are warnings on a committed note and errors staged; `project/alpha` passes; `now` on a concept note warns. `commands.bats`: `ingest.md` names the listing and the reuse rule; `FOUNDRY.md` has the paragraph. `headless.bats`: a headless run's settings allow `vault_index.py tags`; `vault_integrity.bats` or `scripts.bats`: `.claude/settings.json` allows it. Each fails before the change.

## 5. Out of scope

- Renaming tags across the vault (a one-off script when the owner wants it).
- Tags in recall ranking.
- Tag pages or Dataview views (the owner's Obsidian setup).
- Alert tags (the companion spec, `2026-10-14-alert-tags-design.md`).
