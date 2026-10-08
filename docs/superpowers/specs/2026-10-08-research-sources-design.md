# Nightshift research: sources outside the vault

**Date:** 2026-10-08
**Status:** Design approved by the owner in chat (2026-10-08), awaiting written-spec review
**Closes:** #75

## 1. Problem and decision

A Nightshift research item writes a findings note whose frontmatter `sources:` the concept schema limits to vault wikilinks (`[[Note]]`). The research prompt asks for `sources` with no such rule, so a session that cites web pages or code paths there gets the whole note rejected by the publish gate, and the item ends `failed (delivery)`: the night's research is lost until someone publishes it by hand.

**Decision:** both layers.
- The prompt states the rule: `sources:` holds vault wikilinks only; web pages and code paths go in a `## Web sources` section of the body.
- Delivery is the safety net: before the note is staged, every `sources:` entry that is not a wikilink moves into that body section, so a prompt slip cannot lose the note.

## 2. Changes

- `vaultlib/nightshift_session.py`, `research_prompt`: after "frontmatter with type concept, tags, compiled_at (today), partition, provenance ["headless"] and sources", add that `sources` lists only vault notes as wikilinks (`[[Note]]`), and that web pages and code paths are listed in a `## Web sources` section at the end of the body.
- `vaultlib/nightshift_deliver.py`, `publish_research`: the findings are read and passed through a new `move_outside_sources(text) -> str` before they are written to staging.
  - An entry of `sources` is a wikilink when its whole value is `[[…]]`.
  - Every other entry is removed from `sources` and appended, one `- <entry>` line each, under `## Web sources` at the end of the body; the section is created when absent, and an entry already listed there is not repeated.
  - Other frontmatter keys, their order and the body text are kept as written. When `sources` holds only wikilinks, or the note has no frontmatter or no `sources`, the text is returned unchanged.
  - The rewrite reads and writes the frontmatter with the vault's own frontmatter module (`vaultlib.frontmatter`) and YAML settings, so the result validates the way any other note does.

## 3. Tests (pytest)

- `move_outside_sources`:
  - mixed wikilinks and URLs: `sources` keeps the wikilinks in order; the URLs are listed under `## Web sources`; the rest of the frontmatter and the body are unchanged;
  - an existing `## Web sources` section gains only entries it does not list yet;
  - only wikilinks, no `sources`, or no frontmatter: the text is unchanged.
- `publish_research`: a findings note with a URL in `sources` publishes (the case from #75), and the published note has the URL in its body.
- `research_prompt` names the `## Web sources` rule.

Each test fails before the change.

Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_session.py` or the suite that holds `research_prompt`'s tests), the gate.

## 4. Out of scope

- Other note types and other writers of `sources` (ingest has its own rules).
- Checking that the moved URLs are reachable.
