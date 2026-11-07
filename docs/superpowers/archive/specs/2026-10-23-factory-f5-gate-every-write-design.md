# F5: every model write passes the gate's checks

**Date:** 2026-10-23
**Status:** approved and built (#373, #379; #310 closed)
**Program:** `docs/superpowers/2026-10-21-factory-plan.md` (phase F5, #310)
**Grill:** 2026-10-23, two rounds, every recommendation taken, recorded on https://github.com/kferran/Foundry/issues/310 (comment of 2026-10-23); summarised in §3.
**Builder check:** 2026-10-23, four questions and four code corrections, all settled as my calls: each write path checks only its own line, not a page diff (§4.1); redaction runs per field before rendering (§4.1); `add` and `set` redact before their repeat test (§4.1); the 60 s conflict stays with #299 (§1); the once-a-day alert helper moves to `vaultlib` (§4.2); `set` takes no `fit`; `_resolves` is a symlink test, enough for the fixed Now path. None needed the owner.
**Blueprint:** none: one shared check on the existing Now and today-file writers and the gate; no new feature shape.
**Lane:** feature, two PRs with a plan. PR 1 changes the publish gate, so the owner merges it (program plan §1 table).

## 1. Why

The publish gate checks what a headless run writes: schema, partition walls, the 300-character Now cap, protected fields, the shrink guard and the symlink test (`vaultlib/publish.py:_check`). Every other writer of model-derived text into `wiki/` or `briefings/` applies some of those checks by hand, or none. Five live incidents came from those writers: #294 (triage Now lines of 345-452 characters failed 23 of 27 ticks), #211 (a 138 KB Now page of chained updates), #299 and #255 (an ungated Now write inside the 60 s window got a gated brief rejected), and #361 (ten interactive `/rca` notes with no schema). F5 removes the over-long and unchecked lines behind #294 and #211 and the schema gap behind #361. The 60 s conflict in #299 and #255 is a timing rule of the gate, and it stays with #299 in the safety track; F5 does not change it.

Nothing redacts a Now line today, from any writer: `publish.py`, `now.py`, `triage.py`, `route.py` and `rca.py` never call `redact` (#288). The today file redacts its text but not its `link` field.

## 2. Goals, non-goals, anti-goals

- **Goals:** every write of an open Now line or a note line under one, from any writer, passes one check (redaction, the 300-character cap, partition walls on its links, the page's realpath) in `vaultlib/now.py`; the gate runs the same check on the Now lines a run adds; the today file's lines get the same redaction, including `link`; interactive `/rca`, `/brief` and `/debrief` run lint like `/ingest`; lint and the gate share one wall rule. Each held by a test per writer.
- **Non-goals:** staging interactive edits (D1's hook, parked, §3.6); #298's other redaction gaps (they stay in the safety track; F5 inherits them through `redact`); the Now archive and the briefing archive (they move text already written); new note types.
- **Anti-goals:** a tick that fails because of one line (#294's failure mode); a second copy of the check in a caller; high-entropy redaction that eats ticket keys, IDs or PR URLs in Now lines.

## 3. Decisions (owner, grill 2026-10-23)

1. **Worth building:** yes, on the five incidents above.
2. **For whom:** the owner first, then the build agents.
3. **Without it:** ungated machine writers are not acceptable; ungated interactive edits are, since the owner sees each one.
4. **Smallest version:** D2 through one shared check (§4.1); D1 limited to lint steps (§4.5).
5. **#288 folds in:** its part 1 is §4.1's redaction. Part 2: `[watch]` notices keep their text, already redacted by notify (`vaultlib/notify.py:124-138`); this spec records that exception (§4.6).
6. **Order:** F5 goes next, ahead of #331, then #333, then gap plan E-G.
7. **Where:** in `vaultlib/now.py`'s write path, plus `today_log.py`; no caller-side copies.
8. **What it checks:** redaction, the cap (also on `note` and `seed`), partition walls on wikilinks, the target's realpath. The gate runs the same check on added Now lines.
9. **On failure:** fix where a fix exists (redact, cut); otherwise refuse that one line, and a machine caller drops it with one alert a day and goes on. An interactive call gets the same fixes; a refusal exits 2 with the reason.
10. **D1:** `/rca`, `/brief` and `/debrief` in interactive mode gain `/ingest`'s lint step. The staging hook stays parked; its trigger is an interactive edit that causes a defect lint cannot catch.
11. **Walls:** one rule, the gate's (only `wiki/Index.md` is exempt); lint follows it.
12. **Out of scope:** #298's other redaction gaps; the two archives.

## 4. Design

### 4.1 The check: `now.screen`

`vaultlib/now.py` gains one check that each write path runs on the line it writes, never on the page as a whole. A page diff would also catch lines the call did not write: `stamp()` rewrites an owner-reopened line on every write (`now.py:113-114`), so `check` or triage would fail every tick on an old long or walled line they never touched (builder check, 2026-10-23). The check has two parts:

- `screen_fields(kind, statement, who, evidence, rec) -> tuple`: redaction, per field, before the line is rendered. `redact_credentials` (named credential shapes, bearer, URL user info, connection strings, JSON secrets; no high-entropy guess, which hits ticket keys, GUID URLs and PR URLs) runs on the statement, `who` and `rec` separately. Redacting the rendered line would let `ASSIGNMENT` or `CONNECTION` eat a closing `)` or `]` and leave a line `LINE` no longer reads. Evidence keeps its shape check (`validate`); evidence that redaction would change is dropped, which triage and the watch already handle (their second `add` with no link). It returns the redacted fields.
- `screen_line(vault, partition, line, old="", fit=False) -> str`: the rendered line's cap and walls. Over `MAX_LINE` (300): with `fit`, an open line is cut by `_cut` on its bare statement, keeping its fields and parenthesis (the #366 rule), and a note line is cut at its end with "…"; without `fit` it raises `ValueError` as `_fits` does. A line no longer than `old` (the line it replaces) keeps its length, the cap's grandfather rule. Walls: each wikilink and markdown link resolves as the gate resolves it (`linkmod.Resolver` over the vault's files, built only when the line holds a link); a link into a partition the page may not link to (`wall_blocked`) raises `ValueError("partition wall: …")`. Before any write, the page path passes the gate's `_resolves` symlink test (`publish.py:69-73`; the path `wiki/<p>/Now.md` is fixed, so the symlink test is the realpath test here).

Callers, each on its own line only:

| Path | Fields | Line | `fit` |
|---|---|---|---|
| `add` | first, before its repeat test, so a repeat of a redacted statement matches the line already on the page (`now.py:265-266`) | the new or updated line, `old` the line it updates | the caller's (triage and the watch pass `True`, as today) |
| `set_statement` | first, before its match (`now.py:334`) | the rewritten line, `old` the line it replaces | `False`: its only callers are interactive |
| `note` | the note text | the note line | new `fit` parameter, default `False`; the watch's "free:" note passes `True` |
| `seed` | each statement | each seeded line | `True`: it copies an earlier brief's lines |
| RCA `reopen` (`rca.py:167-183`) | the reason before it joins the statement | the rewritten line, `old` the line before | `True`; it calls the two `now` functions, which is the shared check, not a copy |

`check`, `archive`, `stamp` and RCA `filed` write no new text into an open line, so they run no check.

The 300-character cap moves out of `_fits` into `screen_line`; `_fits` goes.

### 4.2 Machine callers

Triage (`triage.py:280-284`) and the watch (`route.py:108-112`, `:143`) already catch `ValueError` and keep going. Each refusal now also raises one alert a day per caller, naming the reason and never the line's text. `Intake.alert` writes only `[intake]` with no key (`intake.py:97-100`); the tagged once-a-day alert lives in the intraday extension (`watchlib/common.py:44-54`). It moves to `vaultlib` (an `Intake` method, tag and key as arguments, the PART_HOMES ratchet updated) and the watch's copy goes, so triage, the watch and the RCA filer use one helper. The alert never carries the line's text (outside text stays out of alerts, `foundry-review`'s `alert-text` check). The RCA filer catches `ValueError` from `reopen` the same way.

### 4.3 The gate

A headless run's Now lines are the one case where the writer is the model editing a page, so here the lines are found by the gate's diff (`publish.py:380`: an open line whose `rstrip()` is not in the live page). `publish.py:_check` replaces its Now cap test (`:380-385`) with the two checks run in check mode on each such line, parsed back into fields: a line the checks would change (redact or cut) or refuse is a Problem. The runner's pre-publish step from #366 (`now.fit_staged`) becomes the fixing pass on the same lines: it re-renders each from its redacted fields and cuts it with `fit=True`, so a brief's added lines arrive redacted and cut, and the gate only verifies. A line that does not parse is left to the gate, as #366 leaves it. A line screen refuses (a wall) still rejects the run, as a wall in any staged note does today.

### 4.4 The today file

`today_log.py:write` already passes each line's text through `clean` (`redact_credentials`, one line, 200 characters). It also cleans the `link` field (`:137`) and checks the file's path with `_resolves`. The today file is not a wiki note and has no partition walls; its frontmatter is written by the script, never by a model, so no schema check is added (the grill's "schema for a new note" applies to notes a model writes).

### 4.5 D1: lint steps

`/rca` (`extensions/telemetry/skills/rca/SKILL.md`), `/brief` and `/debrief` (`.claude/commands/`) in interactive mode end with the lint step `/ingest` has (`.claude/commands/ingest.md:13`): run `system/scripts/lint_vault.sh` and fix each error in the files written. The brief prompt is at 2,495 of its 2,500-word cap (`prep.bats:777`): the `/brief` line is written within the cap by trimming existing wording, and the cap is not raised. Editing headless command text re-runs the brief's live acceptance (FOUNDRY.md); the next scheduled brief after the owner's merge is that check, read from its run ledger.

### 4.6 Walls in lint, and the `[watch]` exception

`index.py:430` exempts any source note of `type: index` from the wall check; it changes to exempt only `wiki/Index.md` (`publish.INDEX_NOTE`), the gate's rule. In the template the only `type: index` notes are `wiki/Index.md` and its test fixtures, so no existing note is newly flagged; a vault that has others sees them as lint errors, which the CHANGELOG line names.

The `[watch]` notice carries outside text (a subject or a snippet) into notify, which redacts every message before it posts (`vaultlib/notify.py:124-138`) from one confined session. That is the recorded exception for #288 part 2: a code comment at the watch's alert line names this section, and `foundry-review`'s `alert-text` check lists the watch alert as a known exception.

## 5. PRs

1. **PR 1 (owner merges):** §4.1-§4.3: `screen_fields` and `screen_line`, their callers, the shared once-a-day alert, the gate's check, `fit_staged` as the fixing pass. Closes #288 part 1. The plan ships in this PR.
2. **PR 2 (auto-merge on green CI unless the plan finds a safety surface):** §4.4-§4.6: the today file's `link`, the lint steps, the wall rule, the `[watch]` exception. Closes #288 and #310.

Each PR has its CHANGELOG line; the plan lists the tests per writer (one per row of §6).

## 6. Done when (a test per writer)

| Writer | Test |
|---|---|
| `now.add` / `set` / `note` / `seed` | a credential-shaped string is redacted and the line still parses (an evidence URL ending `?token=…` included); a repeat add of a credential-bearing statement adds no second line; a long line is cut with `fit`, refused without; an old long line updated by `add` keeps its length; a cross-partition link is refused; a symlinked page is refused |
| `check` with an owner-reopened long or walled line on the page | the tick succeeds and the line is untouched |
| triage, the watch | a refused line is dropped with one alert that day, and the tick exits 0 |
| RCA filer `reopen` | a 300+ character Jira reason is cut, not refused |
| the gate | a staged added Now line that is unredacted, over the cap or walled is a Problem; an old long line is not |
| `fit_staged` | redacts and cuts a brief's added lines before publish |
| `today_log` | a credential in `link` is redacted |
| lint | a `type: index` note outside `wiki/Index.md` that links across partitions is an error |
| `/rca`, `/brief`, `/debrief` | the interactive lint step is in each command (commands.bats key check) |
