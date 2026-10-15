# Shrink guard: accept a heading renamed in place (#160)

## Problem

The publish gate's shrink guard (vault template design §6.20, item 4) refuses a patch that removes a heading of the existing note. It compares heading titles as a set, so a renamed heading counts as one heading removed and one added. A heading that encodes a state, such as `## <thing> (merged, not yet in the vault)`, goes stale once the state changes. An ingest that correctly retires it is refused on every attempt, the input is poisoned after three tries, and the owner has to rename the heading by hand.

## The rule

1. **Position.** A heading's position is its ordinal among the headings of the same level in the note body (the 3rd `##`, the 1st `###`). Headings inside fenced code are not headings, as today.
2. **Section.** A heading's section is the set of non-blank lines (stripped) between it and the next heading of any level. A subsection is its own section, guarded by its own heading.
3. **Counted headings.** Headings are compared as a multiset of heading lines (the `#`s carry the level): each copy of a repeated heading, such as a `### Status` under every `##`, counts on its own. A copy removed while another survives is a removed heading. Before this change the guard compared a set, so deleting one of two copies passed.
4. **Rename accepted.** A removed heading counts as renamed, and the guard does not report it, when the staged note's heading at the same level and position has a title the old note does not have and its section holds every non-blank line of the old section. The section may grow. A rename accounts for exactly one removed copy.
5. Everything else in the guard is unchanged: removed frontmatter keys are refused, the body must keep 60% of its length, and `deprecate` and `supersede` decisions are exempt.

## What stays refused

- A heading removed together with its section, or one whose position in the staged note holds a heading the old note already has.
- A rename whose section drops any non-blank line, also when the body as a whole stays above 60%.
- A heading moved to another position under a new title (the heading now at its old position is judged, and fails rule 4).
- One copy of a repeated heading renamed and another copy deleted: the rename accounts for one copy only.
- Two headings renamed into each other's positions: each is judged by the section at its position, so a swap passes only when each new section keeps the old one's lines.
- A level change (`##` to `###`) under any title.

Known limits, accepted for a smaller rule:
- A run that renames a heading and also adds or removes a same-level heading above it shifts the position and is refused. The ingest makes the two changes in two runs.
- Section lines are compared as a set, so a rename may drop a repeated copy of a line while one copy stays.

## Ingest

`.claude/commands/ingest.md` step 5 (the patch bullet) gains two sentences: retire a heading that encodes a state by renaming it in place and keeping its section, never deleting the section; and in that run add or remove no heading of the same level above the renamed one.

## Alert line

The rejection reason in `publish.json` keeps its wording, `shrink guard: headings removed: <old heading>`, which names the old heading. The alert line from `run_headless.sh` carries no reason at all, so naming the old and new heading there is more than a one-line change; it belongs to #162's notice rewrite, which reads the first `problems[].reason`.

## Tests

Beside `test_shrink_guard` in `system/tests/python/test_publish.py`, each citing `(#160)`: a rename with the section kept passes; a rename whose section loses a line is refused; a heading removed with its section, the body above 60%, is refused; a heading moved to another position with a new title is refused; one copy of a repeated heading renamed and another deleted is refused; one of two copies deleted with no rename is refused; one of two copies renamed with its section kept passes; a rename onto a title the note already has is refused; a rename that changes the level is refused. `commands.bats` pins the ingest sentences.
