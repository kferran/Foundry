# Plan 11 outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-06 (plan: `2026-10-05-plan-11-meetings.md`, commits 2c658dd..d76e98f plus this status commit). Planned in a scratch clone by a subagent, reviewed on Opus and proven on a fresh clone; executed natively on the Debian host (each task's patches applied as written, tests red, then green), then one whole-branch review on Opus and one test-first fix pass. Acceptance: `docs/superpowers/spikes/2026-10-06-plan-11-acceptance.md`.

Final verification at d76e98f: `verify_setup.sh` exit 0 (17/17) on the Debian host (jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2); lint 0 errors. Live acceptance: run 1 FAIL (the parser did not read real Docs), fixed test-first; run 2 PASS.

**Next on the roadmap:** Plan 12 (the `minutes` plugin, in its own repo: fold the spec re-review, then plan); then Plans 7 and 5 once the real vault has run for a few weeks.

## Rulings

- Execution: Ruling: `.scratch/` ships in the template (`.scratch/.gitignore`, a `CLAUDE.md` map line, an integrity test) and the gate exports `TMPDIR=<vault>/.scratch/tmp` and `GIT_CEILING_DIRECTORIES=<vault>/.scratch`, at the user's request mid-plan; the confined fetch sessions keep `mktemp -d -p /tmp` (they must sit outside any project) — cost if wrong: two commits to move to their own branch.
- Final: Ruling: first source wins applies only when a drop is involved; two `gdoc:` sources are two meetings (spec §1.1: one Doc per meeting). This narrows spec §2.3 step 5 — cost if wrong: a Doc that reaches the user under two IDs imports twice and is deprecated by hand.
- Final: Ruling: the empty-text check is in `parse_drop` only; a read with no `fileContent` already fails — cost if wrong: one empty meeting note from a broken Doc.
- Final: Ruling: Finder and Explorer files in drop folders are gitignored; the hook is unchanged.
- Final: Ruling: the reviewer's eleven set-aside behaviors stand as described (each spec-sanctioned or a design limit): a mobile drop's secret stays in history (§2.2); half-written client drops (a synced-folder limit); shared "Notes by Gemini" Docs are imported (§1.1); the duplicate match crosses partitions (D3); non-English locales are not found; the hook accepts `sub/x.vtt`, which the server quarantines (D27); a failed read older than the overlap is not retried (§2.1); search pagination is not pinned by a fixture; the brief is told not to read the quarantine (prompt-level); an interactive `/ingest` may edit meeting notes (the gate is headless-only); a read of another ID that also errors exits 1, not 7 (fails closed) — cost if wrong: each comes back as an issue from the live systems.
- Task 9: Ruling: acceptance clones live in `.scratch/foundry-accept/`, not `~/.cache/foundry-accept/` (the user's request) — cost if wrong: a tool that walks into a nested clone.
- Task 9: Ruling: Step 2 runs one intake tick per meeting input (at most inputs + 1) — cost if wrong: extra no-op ticks.
- Task 9: Ruling: Step 4 also counts action owners written as one word (counts only), since Gemini sometimes writes a first name only — cost if wrong: one line in the record.
- Task 9: Ruling: the plan's stream-shape filter is parenthesized (`A | B, C` bound as `A | (B, C)`) — cost if wrong: none, record-only tooling.
- Task 9: Ruling: the user owns no action in the window, so Step 5 ticked another owner's action (Waiting on 80 → 79) — cost if wrong: the Yours list is unproven live until the user owns an action.

## Final-review fixes

- C1: a search result in any shape but a `files` list, a call with no result, or a listing where no file carries the four keys exits 1 instead of an empty listing that moved `.since` (f496334).
- I1: two Gemini Docs are never one meeting (5f81019).
- I2: an empty drop is quarantined, not published; the client notes say to move a finished file in (ee04548).
- I3: every `[` that touches another `[` is escaped, so `[[[x]]` leaves no link (0eb5391).
- I4: `.DS_Store`, `._*`, `Thumbs.db` and `desktop.ini` in drop folders are gitignored (16931e5).

## Acceptance fixes

- Real Gemini Docs bold every heading and group Decisions under level-2 topic headings; headings now drop surrounding `**`, and a topic heading inside a section stays in it as a bold line (bad13f9). Found by run 1, where every real Doc imported empty.
- The search session calls `search_files` more than once; the listing keeps one entry per Doc (9f0fe5c).

## Deferred minors (issues)

- #37 an apply-time publish conflict quarantines the source with a blank reason.
- #38 the no-connector exit is decided by a substring match (the live `tool_reference` shape is now recorded).
- #39 a failed search (exit 1) is never alerted, and the morning brief misses it.
- #40 a unit timeout leaves the session's `/tmp` directory behind.
- #41 UTF-16 transcripts publish as text full of NULs.
- #42 a Doc from a colleague in another timezone gets the wrong start (2 of 10 real Docs carried `CDT` against a configured `MDT`).
- #43 a crash on the resume path loses the `imported` log line and its notice.
- #44 no documented way to retry a Doc skipped after three failed reads.
- #46 (from the acceptance, older than this plan) a rejected run's staged copy in `system/quarantine/` makes links to that note ambiguous.
