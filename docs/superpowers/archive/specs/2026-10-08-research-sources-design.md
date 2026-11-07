# Nightshift research: sources outside the vault, and code to read

**Date:** 2026-10-08
**Status:** Rev 2. Rev 1 (#75) was approved in chat; rev 2 adds #77 (owner, 2026-10-08: "fold it into the #75 spec"). Awaiting written-spec review.
**Closes:** #75, #77

## 1. Problems and decisions

**#75, sources outside the vault.** A research item writes a findings note whose frontmatter `sources:` the concept schema limits to vault wikilinks (`[[Note]]`). The research prompt asks for `sources` with no such rule, so a session that cites web pages or code paths there gets the whole note rejected by the publish gate: the item ends `failed (delivery)` and the night's research is lost.
- The prompt states the rule: `sources:` holds vault wikilinks only; web pages and code paths go in a `## Web sources` section of the body.
- Delivery is the safety net: before the note is staged, every `sources:` entry that is not a wikilink moves into that section.

**#77, no code to read.** Nightshift spec §3.3 promises research items "read-only clones of the repositories in the brief's scope", but the research directory holds only `out/` and `context/` (a copy of the partition's wiki), and every registered codebase path is denied. A research item queued with `--repo <codebase>` finds no code and stops asking for access.
- A research item may name a repository (`--repo`, a registered codebase or `template`) and a commit to read (`--base`, default the repository's default branch).
- The runner gives the session a clone of that repository at that commit, in the research directory as `code/`. The live checkout stays denied.
- Research sessions get more turns: code-reading briefs need many more tool calls (`MAX_TURNS` for research from 120 to 300).
- A research item creates one new note; it never updates an existing one. The skill says so.

## 2. Changes

### 2.1 Sources (#75)

- `vaultlib/nightshift_session.py`, `research_prompt`: after the frontmatter list, add that `sources` lists only vault notes as wikilinks (`[[Note]]`) and that web pages and code paths are listed in a `## Web sources` section at the end of the body.
- `vaultlib/nightshift_deliver.py`, `publish_research`: the findings are passed through a new `move_outside_sources(text) -> str` before they are written to staging.
  - An entry of `sources` is a wikilink when its whole value is `[[…]]`.
  - Every other entry is removed from `sources` and appended, one `- <entry>` line each, under `## Web sources` at the end of the body; the section is created when absent, and an entry already listed there is not repeated.
  - Other frontmatter keys, their order and the body text are kept as written. When `sources` holds only wikilinks, or the note has no frontmatter or no `sources`, the text is returned unchanged.
  - The frontmatter is read and written with the vault's own frontmatter module and YAML settings, so the result validates like any other note.

### 2.2 Code to read (#77)

- `vaultlib/nightshift_check.py`, `_research`: when `repo` is set, it must be a registered codebase or `template`, and `base` (when set) must resolve: in the codebase's registered clone, or on `template_remote` (read as plan items read it). Without `base`, the default branch is used: `origin/HEAD` of the registered clone (falling back to `origin/main`, then `origin/master`), or the template remote's `HEAD`.
- `vaultlib/nightshift_run.py`, `_research_dir`: when the item has `repo`, it adds `code/`:
  - a codebase: `git clone --local --no-checkout <registered clone> code`, then a detached checkout of the resolved base commit;
  - `template`: fetched from `template_remote` the way plan items are (`fetch_base`), then a detached checkout;
  - the commit is resolved once, at the first attempt, and recorded in the item's run directory, so a resumed session reads the same commit.
  - A clone failure ends the item `failed (base)` with a Needs-you line, as for plan items.
- `_deny`: for a research item, the registered checkout of its own `repo` stays denied too (the session reads `code/` only).
- `research_prompt`: when `code/` exists, the prompt says that `code/` is a read-only copy of `<repo>` at `<short sha>` (its commit date), to read and cite by path.
- `vaultlib/nightshift_session.py`: `MAX_TURNS["research"]` is `"300"`.
- `system/scripts/nightshift.py add` (through `nightshift_run`): `--repo` and `--base` are accepted for `--kind research`.
- `.claude/skills/nightshift/SKILL.md`, `/nightshift ask`: name the repository and commit when the brief reads code; the output is a new note (a research item cannot update an existing one).

## 3. Tests (pytest)

- `move_outside_sources`: mixed wikilinks and URLs (wikilinks kept in order, URLs listed under `## Web sources`, the rest unchanged); an existing section gains only new entries; only wikilinks, no `sources`, or no frontmatter leave the text unchanged.
- `publish_research`: a findings note with a URL in `sources` publishes, with the URL in its body (the #75 case).
- `research_prompt`: names the `## Web sources` rule; with `code/`, names the repository and commit.
- `_research`: an unregistered `repo` and an unresolvable `base` are refused; a codebase with no `base` resolves its default branch.
- `_research_dir`: with a codebase `repo`, `code/` holds the base commit, detached, and a commit made later in the registered clone is absent; with `template`, `code/` comes from the template remote; without `repo`, no `code/`; a resumed attempt keeps the recorded commit.
- `_deny`: a research item's own registered checkout is in the deny list.
- `MAX_TURNS["research"] == "300"`.

Each test fails before the change.

Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_run.py`, `test_nightshift_check.py`, and the suite that holds `research_prompt`'s tests), the gate.

## 4. Out of scope

- Updating an existing note from a research item.
- Fetching a codebase's remote before the clone (the registered clone's remote-tracking refs are used as they are; the prompt shows the commit date).
- Other note types and other writers of `sources`.
