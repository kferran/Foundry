# `/ingest` writes preference notes from digest Corrections

**Date:** 2026-10-08
**Status:** Draft for the owner's review. Approach A chosen by the owner (rules in `ingest.md`, checked by tests); to run as a Nightshift item.
**Closes the gap:** base spec §6.21, "Compile".

## 1. Problem

Digests carry a **Corrections** section (base spec §6.17): one bullet per explicit user correction or stated preference, written *statement — context*. Spec §6.21 says `/ingest` turns each bullet into a `preference` note under `wiki/<p>/preferences/`, so that the later preference phase (Plan 5: derived status, `/brief` acceptance, the recall slot, all behind `preferences_enabled`) has evidence to work from.

`.claude/commands/ingest.md` step 8 instead says to "treat Corrections as facts about how the user wants things done and patch the note they concern". No run has ever written a preference note; a live vault with weeks of digests has none. The schema (`system/schemas/preference.md`), the folders, the `v_preference` view and the gate's protected-field check (`accepted_at`, `rejected_at`) already exist.

## 2. Decisions

- `/ingest` writes preference notes for the Corrections bullets of `work` and `personal` digests. A `shared` digest's Corrections get no preference note (there are no shared preferences, §6.21).
- The rules live in `ingest.md` (approach A). The model applies them; tests pin the rules' text, and a gate test proves the note shape the rules ask for publishes.
- A correction that fixes a fact in an existing note still patches that note as well, as today.
- Out of scope, unchanged: status derivation, `/brief` acceptance, recall, `preferences_enabled` (Plan 5).

## 3. The rules (`ingest.md`)

Step 8 ("Digest sections") changes its Corrections sentence to point at a new step, **Preferences**, placed after it. That step says:

1. **Which inputs.** Only `session_digest` inputs whose partition `<p>` is `work` or `personal`; for `shared`, compile Corrections as facts as before and write no preference note.
2. **The statement.** For each bullet in the digest's `## Corrections` section, the statement is the text before the first ` — ` (space, em dash, space), or the whole bullet when there is none, with the leading `- ` and surrounding spaces removed. Copy it **verbatim**: no rewording, no added or dropped words, same case and punctuation. The derivation counts evidence only when the digest contains the exact statement.
3. **Find a match** with `system/scripts/vault_index.py query "SELECT path, statement, evidence FROM v_preference WHERE partition = '<p>'"`, and read the candidates it returns.
4. **Decide** (one decision line per bullet, in `_decisions.jsonl` headless):
   - **noop**: a preference with the same meaning already lists this digest in `evidence`. Target: that note. (This covers a digest compiled a second time.)
   - **patch**: a preference with the same meaning exists. Stage it and append `"[[<digest stem>]]"` to `evidence`.
   - **patch** with `counter_evidence`: the bullet contradicts an existing preference without replacing it. Append the digest link to `counter_evidence`.
   - **create** + **supersede**: the bullet replaces an existing preference. A create decision for the new preference, which carries `supersedes: ["[[<Old>]]"]`, and a supersede decision for the old one, staged with `superseded_by: "[[<New>]]"`.
   - **create**: no preference matches.
5. **A new note** goes to `wiki/<p>/preferences/<PascalCaseName>.md`, named from the statement's subject, with this frontmatter and nothing else: `type: preference`, `statement` (verbatim), `partition: <p>`, `codebase` (the digest's value, when it has one), `evidence: ["[[<digest stem>]]"]`, `created_at` (today; headless: the run id's date). The body is a `# <Title>` heading and one line with the bullet's context.
6. **Links.** `evidence` and `counter_evidence` link only to `session_digest` inputs of the current run. Never set or change `accepted_at`, `rejected_at` or `provenance` (the gate rejects it).
7. **Self-edit** (step 10) never changes a preference's `statement`.

The same rules apply to an interactive run, which edits `wiki/` directly.

## 4. Tests

- **bats (`system/tests/commands.bats`), text of `ingest.md`:** the Preferences step exists; it names `wiki/<p>/preferences/`, the verbatim rule, the ` — ` split, the `v_preference` query (an allowlisted `query` call, so the existing allowlist test keeps passing), the noop-on-repeat rule, the `evidence`/`counter_evidence`/supersede rules, "no preference note" for `shared`, and that `statement` is left alone by the self-edit; step 8 no longer says to patch Corrections into "the note they concern" as the only outcome.
- **pytest (`system/tests/python/test_publish.py`), the note shape:** a staged new preference written exactly as §3.5 says, with `evidence` linking a `session_digest` in `raw/work/notes/`, and a create decision, publishes with no problems; the same note under `wiki/shared/preferences/` is rejected; a staged patch that appends a second `evidence` link to an existing preference publishes.

The bats test fails before the change. The pytest tests pass before it too: the gate already accepts preference notes, and the tests pin that it accepts the exact shape the new step asks for. Bound tools: bats (`commands.bats`), pytest (`test_publish.py`), the gate (`system/scripts/verify_setup.sh`).

## 5. Rollout

- Runs as a Nightshift item on a `template` branch; the owner merges the pull request.
- After the merge, the live headless acceptance is re-run (roadmap rule for any change to the `ingest` command): one digest with a Corrections bullet, compiled by the intake timer, yields a preference note the gate publishes. This is a step for the owner or the vault session, outside the Nightshift.

## 6. Known limits (approach A)

The model applies the rules, so results can vary: a reworded statement (which the derivation later ignores), a different file name for the same preference, or a different restate/contradict call. Approach D (a model-free capture step after the model, before publish) was considered and not chosen; it remains the fix if live runs show these problems.
