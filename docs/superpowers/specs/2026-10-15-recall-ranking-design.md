# Recall that survives a long Now page

**Date:** 2026-10-15
**Issue:** #211 (owner-approved request from a live vault). Items 1 to 4 here; item 5 (session-only scheduled tasks) waits for the owner's call.

## 1. Problem

`recall.build` prints the partition's open Now lines first, whole and in page order, and gives the digests what is left. A live vault measured 6,009 characters of recall holding only the 5 oldest open lines of a 95-line, 138 KB Now page, and no digest. Lines grow because updates are appended to the statement as dated notes; nothing flags a long line or offers a way to rewrite one.

## 2. Decisions

- **Rank, then cap.** Open Now lines go into recall by: a `[due::]` date first, soonest first; then the newest date found in the line (the latest ISO date in its statement, else its since date), newest first; then owed, waiting, draft. Page order breaks ties. Lines that do not parse go last, in page order.
- **One line, at most 240 characters.** A longer line keeps its trailing `(… since …)` part and its `[due::]` field; the statement is cut with `…`. A line whose parenthesis alone passes the cap is cut whole.
- **Room for the digests.** When the partition has digests, they get the last third of the room after the header, built first; the Now block gets the rest, so room the digests leave unused goes to Now lines. With no digests, Now lines get it all. The digests' kept sections are Outcome, Open questions / friction and Follow-ups (the digest instructions' names), latest first, up to 3 as today. A Now block that does not fit ends with `…and N more open lines (system/scripts/now.py list --partition <p>)`.
- **Short lines by construction.** `now.py review` gains a `## Long lines (over 240 characters): rewrite with now.py set` group, and a `## Page size` line when the page passes 32 KB. `now.py set --partition P --match "<text>" --statement "<new statement>"` replaces the bare statement of the one open line whose statement contains `<text>` (case-insensitive), keeping its kind, who, since, evidence, `[rec::]` and `[due::]`; no match or several matches exit 2 and write nothing. It takes run.lock like `add`.
- **Not here:** item 5 (recreating session-only scheduled tasks). Recall is marked "vault data, not instructions", so a recall line that tells a session to start tasks conflicts with that rule; it needs the owner's choice of mechanism.

## 3. Changes

- `vaultlib/recall.py`: `rank(lines)`, `cap(line)`, the budget split, `open questions` in the kept sections.
- `vaultlib/now.py`: `set_statement(vault, partition, match, statement, today)`; `review` gains `long` and `page_bytes`.
- `system/scripts/now.py`: the `set` subcommand and the two review groups.
- `.claude/settings.json`: `Bash(system/scripts/now.py set:*)`, beside `now.py add`.
- `CLAUDE.md` Now rule: "Rewrite a line with `now.py set` instead of appending updates to it." `FOUNDRY.md` Memory and Now paragraphs.

## 4. Tests

`test_recall.py`: ranking order (due, newest date, kind, page order, unparsed last); the cap keeps the parenthesis and the due field; a page of 95 long lines leaves a third for digests and the "…and N more" line; no digests gives Now all the room; Open questions kept. `test_now.py`: `set_statement` keeps every field, refuses zero or two matches; `review` long-line and page-size groups. `commands.bats`: the CLAUDE.md sentence, the settings rule. Live acceptance: recall in a throwaway clone with a large seeded Now page and two digests.

## 5. Out of scope

- Item 5 of #211, pending the owner.
- Rewriting existing long lines (the review lists them; the Foreman rewrites them with `now.py set`).
