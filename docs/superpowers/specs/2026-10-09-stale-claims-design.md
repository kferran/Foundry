# Stale claims get corrected, not just reported

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #85, items 1 and 2 only. The 2026-10-09 grill deferred the lint staleness pass (item 3) until a stale note bites after this ships, and dropped the debrief counts (item 4).

## 1. Problem

Sessions and research Work Orders find vault notes that are out of date: a note describes code a later commit removed, or a label a vendor document contradicts. They report it as a side finding, and the stale claim keeps feeding answers and briefs.

Since #96, a digest's `## Corrections` section holds the owner's corrections of Claude, and ingest turns each one into a preference note. A stale vault claim is a different thing, so it needs its own section.

## 2. Decisions

- **A stale claim found anywhere becomes a correction.**
  - A session working in the vault fixes the note directly.
  - Any other session records it in its digest, and ingest fixes the note.
  - A research Work Order records it in its findings note, and delivery hands it to ingest.
- **A correction is a patch in place:** the note states the current fact, and the source that showed it is added to `sources`. A note that is wrong as a whole is deprecated or superseded, as ingest already does.
- **New digest section `## Stale claims`**, kept apart from Corrections. Each bullet is `[[Note]]: <the old claim> → <the current fact> (<evidence: commit, file:line, document or link>)`.

## 3. Changes

- **`CLAUDE.md` (Vault Rules), a new rule "Stale claims":** when a vault note contradicts the code, a document or what this session established, correct it. In the vault, patch the note and add the evidence to `sources` (or deprecate or supersede it). Outside the vault, add the claim to the digest's Stale claims section. Never leave it only as a side finding.
- **`system/hooks/digest_instructions.md`:** add `Stale claims` after `Corrections`, in the bullet form above; the section is left out when there are none.
- **`.claude/commands/ingest.md`, step 8 (Digest sections):** each Stale claims bullet is a **patch** of the note it names (or **deprecate** or **supersede** when the whole note is wrong), with the digest added to `sources`. It never becomes a preference note. A bullet that names no existing note compiles as a fact. A digest's Outcome or Decisions that contradict a compiled note also patch that note (stated explicitly).
- **Research Work Orders:**
  - `vaultlib/nightshift_session.research_prompt` asks for a `## Stale claims` section in the findings note, in the same bullet form, listing vault notes under `context/` that the sources contradict.
  - On delivery, `vaultlib/nightshift_deliver` copies a non-empty section into `raw/<partition>/notes/<item id>.stale-claims.md`, a `session_digest` whose body is only that section. Ingest then applies it on the next intake tick.

## 4. Tests

- **bats (`commands.bats`):** the `CLAUDE.md` rule, the digest instruction's section list in order, and ingest's Stale claims rule (patch, never a preference).
- **pytest:**
  - `test_nightshift_session.py`: the research prompt asks for the section;
  - `test_nightshift_deliver.py`: a findings note with Stale claims writes one valid `session_digest` input with only that section; one without the section writes none.

Bound tools: pytest, bats and the gate.
