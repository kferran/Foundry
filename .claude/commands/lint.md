---
description: Audits the vault (schemas, links, orphans) and suggests links, merges, retirements and missing notes.
---

Audit the vault. The deterministic checks come first; your analysis only adds to them.

1. Run `system/scripts/lint_vault.sh` and `system/scripts/vault_index.py orphans`. Present errors first, then warnings, grouped by file.
2. Then add analysis, each item with the notes involved and a proposed fix:
   - **Links:** for each orphan and each dead link, suggest a link or a target.
   - **Duplicates:** notes that cover the same topic (check with `system/scripts/vault_index.py related <note>`); propose a merge by superseding one.
   - **Contradictions:** active notes in the same partition that disagree; propose `supersedes`/`superseded_by` or `status: deprecated`.
   - **Stale notes:** canonical notes with `compiled_at` more than 180 days old that recent session digests discuss.
   - **Topic gaps:** a term that appears in 3 or more notes with no note or alias of its own.
3. Ask before fixing anything. Never delete a note: retire it. Respect partition walls in every suggestion.
