# Research brief: semantic recall for the index

**Date:** 2026-10-11
**Status:** A research brief for a Work Order (`/order ask`, `--kind research`). Not a spec: its output is a findings note, and a spec follows only if the findings say so.
**From:** the 2026-10-11 review ("retrieval is lexical").

## Question

Which way of adding meaning-based retrieval to the Foundry's index fits its constraints, and is the gain worth it? The constraints: notes are Markdown in git and the SQLite index is derived from them; headless runs have no network; `vault_index.py related` is the sanctioned entry point (CLAUDE.md "Index first"); partition walls apply to recall; Python 3 standard library plus `sqlite3` is the current dependency floor; the server is a Linux box without a GPU.

## Scope

- Options to compare, at least: embeddings stored in SQLite (`sqlite-vec` or a plain table with cosine in Python) computed by a local model (a small sentence-transformers or GGUF model through a local runtime) or by an API at index time only; Khoj as a sidecar with its Obsidian plugin; Basic Memory's approach (Markdown as source, SQLite index, MCP server); keeping lexical search and improving it (synonym expansion from `aliases`, better `related` ranking).
- For each: what runs where (index time vs. query time, network or not), the dependency it adds, how partition walls are kept, what `related` would return differently, and the cost in disk, time and setup steps.
- Sources: the Foundry's `vaultlib/index.py` and `retrieve.py` (read `template` at the default branch under `code/`), the projects' own documentation, and no more than five web pages per option.
- Web hosts: `github.com`, `docs.khoj.dev`, `pypi.org`, `sqlite.org`, `huggingface.co`.

## Done when

The findings note has: one table across the options with the columns above; a recommendation for the smallest version worth building, or a recommendation to build nothing yet and the signal that would change that (for example a `related` miss rate measured on the owner's real queries); the two or three constraints that ruled options out; and the open questions a grill would have to settle.

## Output

`wiki/shared/summaries/SemanticRecallOptions.md`, a new note (`type: concept`, `partition: shared`, `tags: [index, research]`), `sources` holding vault wikilinks only, web pages under `## Web sources`.

## Queue line (for the Foreman session)

```
system/scripts/nightshift.py add --kind research --title "Semantic recall options for the index" --partition shared \
  --brief-file docs/superpowers/specs/2026-10-11-semantic-recall-research-brief.md \
  --output wiki/shared/summaries/SemanticRecallOptions.md \
  --host github.com --host docs.khoj.dev --host pypi.org --host sqlite.org --host huggingface.co \
  --repo template
```
