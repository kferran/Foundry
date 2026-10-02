---
description: Read-only blast-radius analysis for a component across the registered codebases and the wiki.
argument-hint: <component> [--repo name]
---

Map the downstream impact of changing: $ARGUMENTS

This is read-only. Do not modify any code.

1. **Codebases.** List `system/codebases/*.md` (skip `example.md`). With `--repo <name>`, use only that one. For each, read `path`, `search_globs` and `layers` with `system/scripts/vault_index.py field system/codebases/<name>.md <key>`, and read the file's body for conventions.
2. **Search.** In each codebase's `path`, search the component name across files matching its `search_globs`. Classify each hit by the layer whose directory contains it (`layers`, e.g. `ui`, `api`).
3. **Cross-layer and cross-repo matching.** Match API routes, endpoints and exported names found in one layer to their consumers in other layers and other codebases, so a change on one side shows every caller on the other.
4. **Wiki.** Run `system/scripts/vault_index.py related "<component>"` and read the returned notes for plans, decisions and log-event maps that mention it.
5. **Report**, grouped by codebase: a table `File | Layer | Relationship | Blast Radius (High/Med/Low)`, then affected files without tests, then the wiki notes involved. Offer to draft an intent proposal from `system/templates/intent-shaper.md` with its **Downstream Impact & Risk Radii** section filled in.
