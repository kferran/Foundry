# A Now page you can keep up with: each line names its writer, and machine lines expire

**Date:** 2026-10-24
**Status:** draft for the owner
**Grill:** 2026-10-24, rounds 1 and 2 of #333 (Q4, Q13 to Q17), every recommendation taken, recorded on https://github.com/kferran/Foundry/issues/333
**Builder check:** 2026-10-24, five questions and three code gaps, all settled as my calls (none needed the owner): a line never expires before its own `due` (§3.2); the watch's own `free:` note does not count as a touch (§3.2); `set` hands a line to the session (§3.1); health keeps writer keys apart from evidence guesses (§3.3); the brief's `now.md` input leaves `via` out (§3.1); `screen()`, the fit path, repeat `add`, `set` and RCA `reopen` all carry `via` through their re-render (§3.1); expiry runs whether or not an evidence check closed anything (§3.2).
**Blueprint:** none: a field and a close rule on the existing Now writers; no new feature shape.
**Lane:** feature, one pull request with a plan. No safety surface: the publish gate, redaction, settings and hooks are unchanged. It auto-merges on green CI.

## 1. Why

In the live vault, 2026-10-10 to 2026-10-23 (counts read by the vault session, recorded on #333):

- The work Now page held 170 open lines and was 57.8 KB, against the 25 KB review limit (`now.py:22`).
- About 37 lines arrived a day: 520 in 14 days.
- More lines were dropped by hand (165) than ticked (148), and 32 closed on their evidence.
- By evidence, 276 of the 520 new lines carry a mail or Slack link, and 141 carry none.

No field records which writer added a line, so precision per source cannot be measured. The health extension's "dismissed share" guesses the source from the evidence host (`extensions/health/scripts/health.py:197-203`), and a line with no evidence counts as `none`.

The owner's goal (FOUNDRY.md, What The Foundry is): "the Now page is a list you finish, not one you prune".

## 2. Goals, non-goals, anti-goals

- **Goals:**
  - Every new Now line names its writer.
  - A line from a machine writer that the owner has not touched closes itself 7 days after it opened.
  - The health scorecard's dismissed share reads the writer, so after two weeks the numbers show which source to tune.
- **Non-goals:**
  - Tuning any source's bar (for example triage's). The owner deferred that until two weeks of writer data exist (#333 Q16).
  - The page size limit, and the brief's Overdue and From Now blocks.
- **Anti-goals:**
  - Expiring a line the owner owes and still means to do.
  - A second copy of the Now rules in a caller.
  - A change to `now.py list --json` that breaks the console (#377). A new key is allowed; nothing is renamed or removed.

## 3. Design

### 3.1 The writer field

A line gains a third optional Dataview field after `[rec:: …]` and `[due:: …]`: `[via:: <writer>]`. The five writers are:

| `via` | Writer | Machine? |
|---|---|---|
| `mail` | inbox triage, mail | yes |
| `chat` | inbox triage, Slack | yes |
| `watch` | the intraday watch | yes |
| `brief` | the headless morning brief's new lines: its objectives, Work Order decisions, extension sections | no |
| `session` | `now.py add` from any session, the default; an interactive `/brief` adds its lines this way, so they are `session` | no |

- **Parsing:** a `VIA` regex is added next to `REC` and `DUE` (`vaultlib/now.py:39-41`).
  - `fields()` strips it from the bare statement, so repeats still compare bare statements.
  - `FIELD_KEY` gains `via`, so a statement cannot smuggle one in.
  - A new `via(statement) -> str` returns the value, or `""` when the field is missing or not one of the five.
  - `fields()` keeps its three-tuple. The paths that re-render a line from its parts read `via()` as well and pass it to `render()`, so no path drops the field: `screen()`'s canonical test and rebuild, `screen_line()`'s fit cut, a repeat `add`, `set_statement()` and RCA `reopen` (`extensions/telemetry/scripts/telemetrylib/rca.py`). A test per path holds it.
- **Rendering:** `render()` takes `via=""` and writes it last of the three fields. The 300-character cap and `_cut` already measure the whole line.
- **Writing:**
  - `add()` gains `via="session"`. A repeat add keeps the line's existing `via`.
  - RCA `reopen` keeps the line's `via`, as it keeps `rec` and `due`.
  - `set_statement()` writes `[via:: session]`: a session that rewrites a line has taken it over, so a rewritten machine line no longer expires. Its writer's record moves with it, so the line is never counted as that writer's dismissal.
  - `now.py add` gets no `--via` flag: a session is always `session`.
  - Triage passes `"mail"` or `"chat"` from its `source` argument (`vaultlib/triage.py`, `record`). The watch passes `"watch"` (`watchlib/route.py`, `now_line`).
- **The brief:** the brief prompt is at its 2,500-word cap, so the prompt does not change. Instead, `fit_staged` (`vaultlib/now.py`) adds `[via:: brief]` to each line the run added that has no `via`, before it screens the line. The gate's `screen()` then sees a canonical line, as today.
- **`now.py list --json`:** each line gains `"via"`. `v` stays `1`, since the change only adds a key.
- **`now.py list` (plain text):** prints each line without its `[via:: …]` field. The brief's prep writes `now.md` from this output (`brief_prep.sh:53`), and the brief prompt compares statements ignoring only `[rec::]` and `[due::]` (`brief.md:60`), so this keeps the brief from adding a repeat without changing the prompt.

### 3.2 Machine lines expire

`check()` (run by the intake tick every 5 minutes) closes each open line where all of these hold:

- its `via` is `mail`, `chat` or `watch`;
- its `since` is 7 or more days before today (`EXPIRE_DAYS = 7`);
- it has no `due`, or its `due` is before today, so a deadline or a commitment the watch dated never closes before its date;
- it has no note under it (`_block_end`) other than the watch's own `free: …` note (`watchlib/route.py`, written with the line).

The line becomes `- [-] … _(closed: expired <today>)_`, a drop the archive moves at the next brief like any other.

The owner keeps a machine line by adding a note under it (`now.py note`, or an indented line typed in Obsidian), or by deleting its `[via:: …]` field, which makes the line theirs. A line with no `via`, which includes every line written before this change, never expires. `check()` already writes the page only when a line closes, from a fresh read. Expiry is its own pass over that fresh read: it runs whether or not an evidence check closed a line, and a failed `gh` check, which skips the remaining pull requests, does not skip it.

FOUNDRY.md's Now paragraph states the rule and how to keep a line.

### 3.3 Health reads the writer

`dismissed()` (`health.py:206`) keys each closed line by its `via` when it has one. A line with none keeps today's evidence-host guess under a separate key, `guess:mail`, `guess:slack`, `guess:github`, `guess:other` or `guess:none`, so the writer keys start their own history and the trend check never compares a writer share with medians recorded under the old meaning. An expired line is a `[-]` drop, which `dismissed()` already counts. Its text names the keys (`mail 62%, watch 40%, guess:none 30%, …`). The thresholds are unchanged.

## 4. Done when (a test per part)

| Part | Test |
|---|---|
| field | `add` writes `[via:: session]` by default. A repeat add keeps the old `via`. `set` writes `session`. `fields()` ignores it. A statement holding `[via::` is refused. `list --json` has `via`; plain `list` leaves it out. A long `fit` line, `screen()` and RCA `reopen` keep it. |
| triage, watch | their lines carry `mail`, `chat` and `watch` |
| brief | `fit_staged` adds `[via:: brief]` to an added line that has none, and the gate passes the result |
| expiry | a `mail` line 7 days old with no note is closed `expired`, also on a tick whose `gh` check failed. A watch line holding only its `free:` note expires too. These stay open: a 6-day-old line, a line whose `due` is today or later, a line with an owner's note, a `session` or `brief` line, and a line with no `via`. |
| health | the dismissed share is keyed by `via`, with `guess:` keys for lines that have none |
| docs | FOUNDRY.md's Now paragraph names `via` and the expiry rule (a `commands.bats` key check) |
