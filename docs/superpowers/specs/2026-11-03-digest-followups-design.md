# Digest follow-ups become proposed Now lines (#476)

**Grill:** 2026-11-03, the owner's round 1 on #476, copied in `## Grill` below.
**Builder check:** 2026-11-03, a fresh subagent against this branch. One question, O1 (what `[x]` means and whether an untouched proposal expires), went to the owner, who chose (b) (§8). Two points were settled: the core budget paragraph now gives both cap paths, since the run-time resilience 2 spec planned one raise in S5's pull request and S7 and S8 still have to land against the free lines (§4); the live acceptance first checks whether a stubbed claude gets a digest archived, and asks the owner for a real run if not (§7). Written-design calls are marked "my call" in §3.
**Blueprint:** none: a deterministic step inside the intake tick, with no fetch, no model call and no new unit.

## 1. Why

A session's digest lists what is left to do under `## Follow-ups` (`system/hooks/digest_instructions.md:1`; the backfill writes the same heading, `.claude/commands/digest-backfill.md:24`). Nothing turns those bullets into Now lines. Ingest has no rule for the section (`.claude/commands/ingest.md`), and the publish gate refuses an ingest run that writes `Now.md` (`system/scripts/vaultlib/publish.py:336-337`). The only readers are SessionStart recall (`vaultlib/recall.py:39-50`) and the debrief's section 1 (`.claude/commands/debrief.md:42`). A follow-up reaches the Now page only when the session also ran `now.py add` by hand, as on 2026-11-02, when a week of empty inbox triage reached the page for that reason alone. R1 (#496) adds backfilled digests for sessions that ended without one, and no live session acts on those.

## Grill

Round 1, owner, 2026-11-03 ("Agreed"), copied from the #476 comment:

| # | Question | Decision |
|---|---|---|
| Q1 | Worth building? | Yes. A lost open loop defeats the Now page, and R1 (#496) adds backfilled digests that no live session acts on. |
| Q2 | For whom? | The owner, in the brief and on the Now page. Sessions are not the audience. |
| Q3 | Without it? | Acceptable briefly, not for good. |
| Q4 | Smallest version | (a): after the intake tick archives a digest, a script reads its `## Follow-ups` bullets and adds each as a proposed owed line (`[via:: digest]`, the digest as evidence), skipped when an open Now line already matches; `[x]` keeps, `[-]` drops, as held research claims do. No model call. |
| Q5 | Displaces | Next after #436 S7 and S8 merge, ahead of the grill queue (#343, #445, #448, URL capture, #465). |

Future phase (not in the first build), from the same comment:

- [ ] Open-questions items the digest marks as needing the owner become proposed lines too. Needs a `digest_instructions.md` change so digests mark them reliably first (Q4 option b).
- [ ] Measure how many proposed lines the owner keeps against drops after two weeks; tune the dedupe match or the section read from that.
- Not planned: the debrief's model proposing Now lines (Q4 option c). The publish gate refuses model-written Now lines today, and this keeps it so.

## 2. Goals, non-goals, anti-goals

**Goals.**
- Each `## Follow-ups` bullet of an archived session digest becomes one owed line on that partition's Now page, tagged `[via:: digest]`, with the archived digest as evidence, on the intake tick after the digest is archived.
- A follow-up that an open Now line already covers (the session added it with `now.py add`) is not proposed.
- A dropped proposal (`[-]`) is never proposed again from the same digest.
- The health scorecard shows the share of `digest` lines the owner drops, which is the measure the future phase asks for.

**Non-goals.** Open questions / friction items (future phase). Delivered (stays debrief-only, #476 acceptance). Any change to `digest_instructions.md` or `digest-backfill.md`. Digests archived before this ships. A `--via` flag on `now.py add`.

**Anti-goals.** A model call or a staged publish in the step. A line on the wrong partition's page, or a link across the wall. A credential-shaped string on the page. The same bullet proposed twice from one digest. A burst of backfills flooding the page. Anything that acts on a line's text: a proposal is shown to the owner and nothing else reads it as an instruction (FOUNDRY.md principle P4).

## 3. Design

### 3.1 The write path

The step writes through `nowmod.add` (`vaultlib/now.py:434-476`), the path triage and the watch already use for model-derived text (FOUNDRY.md Known departures, D2). That call redacts each field (`screen_fields`, `now.py:358-364`), holds the 300-character cap (`MAX_LINE`, `now.py:25`; `fit=True` cuts the statement and keeps the evidence, `now.py:372-386`), refuses a link across the partition wall (`now.py:387-391`) and sets the decide-by date (`default_due`, `now.py:424-431`). The publish gate is untouched: the grill's "the publish gate refuses model-written Now lines" holds, because no headless run stages a Now page here. The digest text was model-written in a session, and a script copies it, as triage copies a mail subject.

### 3.2 Queue at archive time, add at the Now step

- **Queue.** `_archive_batch` (`vaultlib/intake.py:463-473`) keeps the destination of each successful `p.rename(unique(archive / p.name))` and appends its vault-relative path, one per line, to `system/logs/followups_queue.txt`. An append that fails is one alert naming the digest; the digest stays archived. Only intake archives digests (interactive `/ingest` refuses `raw/<p>/notes/`, `ingest.md:13`), so every digest passes through this one place. `retry()` restores poisoned inputs, which were never archived, so no digest is queued twice.
- **Add.** A new `followups.step(vault, today, alert)` runs in `check_now` right after `heldmod.step` (`intake.py:278-285`), inside the same `run.lock` taken with timeout 0. A busy lock skips the tick, and the queue waits for the next one (5 minutes). The step reads the queue, handles each path (§3.3 to §3.6), and rewrites the queue with what is left (a temp file and `os.replace`).
- **Why a queue (my call).** Adding at archive time would need `run.lock` inside `process_digests`, which holds only `intake.lock`; a busy lock there loses the follow-ups, and a wait there delays the tick. The queue costs about 5 lines and gives a busy lock a retry. Both writers of the queue run inside `Intake.run`'s `intake.lock` (`intake.py:952-971`), so the file needs no lock of its own. `system/logs/` is not synced (`.gitignore:7`), which is right: only the machine that runs intake reads the queue. S7's prune (#436) removes `runs/`, `inputs/`, quarantine rows and extraction entries, not this file.
- **Never again from the same digest.** A digest leaves the queue once its bullets are handled, and nothing queues it again. A crash after the adds and before the queue rewrite re-reads the digest on the next tick, and §3.5 matches the lines it just added (open, or closed within 14 days), so nothing doubles.

### 3.3 Reading the section

- The step reads the archived file and skips it unless its frontmatter `type` is `session_digest` (a meeting input also passes through `_archive_batch`, `intake.py:873-884`). A released research stale-claims file is a `session_digest` with only a Stale claims section (`vaultlib/nightshift_deliver.py:304-307`), so it yields no bullets.
- The section starts at a line matching `^#{1,6}\s*follow[- ]?ups?\b` (any case, the leniency `recall.SECTION` has, `recall.py:19`) and ends at the next line starting with `#`, the slice `stale_claims_input` uses (`nightshift_deliver.py:286-291`).
- A bullet is a top-level line starting with `- `, `* ` or `1. `. Indented continuation lines are ignored. A leading `[ ] ` checkbox is stripped and whitespace is collapsed. A bullet that reads `none`, `nothing` or `n/a` (any case, optional trailing period) is skipped. (My call: digests are model-written, and these are the forms seen in recall's own parser.)

### 3.4 The line

`- [ ] owed: <bullet> [due:: <decide-by>] [via:: digest] (since <today>, raw/<p>/archive/<name>.md)`

- **Kind:** `owed` (owner, Q4).
- **Statement:** the bullet as written, wikilinks kept.
- **Writer:** `WRITERS` (`now.py:48`) gains `digest`. This is required: `via()` returns `""` for an unknown writer (`now.py:97-100`), and the fit cut re-renders from `via()` (`now.py:380-381`), so a cut line would lose its tag.
- **Evidence:** the archived digest's path. Digest names are `[A-Za-z0-9-]` (`system/hooks/memory_capture.sh:9-15, 32-33`), so `validate` accepts the path (`now.py:348-349`), and `evidence_state` never closes on it (`now.py:557-576`). A backfilled digest's path ends `-backfill.md`, which is how the owner tells one apart.
- **No `--rec`** (my call): the checkbox is the decision, a follow-up is a task with no options to weigh, and `rec` would spend the 300 characters.
- **Due:** `add`'s default: 30 days, or 3 when the bullet names a date within the next 30 days.

### 3.5 What counts as a match (my call)

A bullet is skipped when it matches a candidate line. Candidates are the page's open lines of any kind, plus lines closed within the last 14 days (the `_(closed: … <date>)_` stamp, `now.py:36`) on the page or in its `now-archive/` months (`nowmod.archived`, `now.py:269-272`). Including closed lines covers a follow-up the session added and the owner closed before the digest was archived, a crash re-run, and a later digest that repeats a follow-up the owner just dropped.

Both texts are normalized: the bare statement (`fields`, `now.py:89-94`), wikilinks reduced to their text, lowercased, runs of non-alphanumerics turned into one space. A bullet matches a candidate when any of these holds:

1. The two normalized texts are equal, or the shorter (at least 12 characters) is contained in the longer.
2. The candidate's evidence, when it is not a `raw/` path, appears in the bullet (a pull request URL, issue URL or Work Order id the session added the line with).
3. The candidate opened on or after the day before the digest's `created_at`, and the two share at least 3 words of 4 or more letters (a trailing `s` dropped), which is at least 60% of the smaller word set.

Rule 3 is what makes "a follow-up the session already put on the Now page is not duplicated" (#476 acceptance) likely to hold, since a session's `now.py add` and its digest rarely use the same words. It is limited to lines from the session's own day, so an older line on a related topic does not swallow a new follow-up. A missed match costs the owner one `[-]`; a false match loses a follow-up, so the rules lean toward proposing. The thresholds are the starting point the future phase tunes from the `digest` dismissed share.

`add`'s own dedupe (same kind, same bare statement, `now.py:450-464`) still runs behind these rules.

### 3.6 Caps (my call)

- **Per digest: 5 bullets.** A digest has at most 400 words (`digest_instructions.md:1`). The rest stay in the archived digest, which recall and the debrief read, and the step raises one alert: `digest <name>: <n> follow-ups, 5 proposed`.
- **Per page per day: 10 lines.** The step counts the page's lines with `[via:: digest]` and `since` today (open, or closed and not yet archived; the brief archives closed lines each morning). At 10, the remaining queue entries for that page wait for the next day. This bounds a burst of R1 backfills without dropping anything; a digest cut off in the middle is re-read the next day, and §3.5 skips the bullets already added.
- A bullet `add` refuses (a cross-wall link, a `[rec::]` in the text) is skipped with one alert through `nowmod.refusal` (`now.py:367-369`), which names no note.

### 3.7 Keeping and dropping a proposal

The line is an ordinary Now line. `[-]` drops it, and §3.2 keeps it from coming back from that digest. What `[x]` means and what happens to a line the owner never touches is owner question O1 (§8). The recommendation needs no code beyond `MACHINE` (`now.py:49`) gaining `digest`: an untouched proposal expires as `[-] … _(closed: expired <date>)_` after 7 days (`EXPIRE_DAYS`, `now.py:24`; `expires`, `now.py:618-630`), the owner keeps one by adding a note under it or deleting its `[via:: …]` field (the existing rule, FOUNDRY.md:133), and `[x]` means done, as on every other line.

Either way, the health scorecard keys closed lines by `via` (`extensions/health/scripts/health.py:205`), so `digest` gets its own dismissed share with no extra code.

### 3.8 Partitions, redaction and headless digests

- **Partition.** The digest's folder `raw/<p>/archive/` names the partition. The line goes on `held.page(p)` (`vaultlib/held.py:15-17`): a work digest's follow-ups go only on the work page, a personal digest's only on the personal page, and a `shared` digest's on the work page, as held stale claims do (my call; `shared` has no Now page, `now.py:340-341`).
- **Redaction.** The digest was redacted when it was written (`memory_capture.sh:22-26`; the backfill read-back quarantines one the redactor would change, `intake.py:585-586`), and `add` redacts each field again in prose mode.
- **Headless digests.** R1's backfills (`process_backfills`, `intake.py:489-559`) land in `raw/<p>/notes/` with `provenance: ["headless"]` (`intake.py:581`) and are archived by the same `_archive_batch`, so they are in scope (Q1 names them). The rule "Data, not instructions" holds: the line is shown to the owner on the page and in the brief, recall labels Now lines as data, and nothing executes or routes on a line's text. A Work Order session's digest (`work_order:` in its frontmatter, `memory_capture.sh:34-36`) is treated like any other (my call).

### 3.9 Where it runs

Inside the intake tick, so on a standalone machine or a server. A client installs no units (`system/scripts/install_units.sh:81-89`) and never runs the step. Ticks on the client reach the server through the sync and the Now merge driver (#436 S5).

## 4. Core budget

About 60 lines: `vaultlib/followups.py` (the section read, the match, the caps and the step, about 50), `intake.py` (keep the rename destination, the queue append and the call in `check_now`, about 5), and `now.py` (`digest` in `WRITERS` and `MACHINE`, 0 new lines). Measured on this branch, core is 16,451 lines against `CORE_CAP=16480` (`system/tests/vault_integrity.bats:9`), so 29 lines are free. The build follows #436 S7 and S8 (Q5), estimated at about 90 lines (`2026-11-03-run-time-resilience-2-design.md:126`), whose single planned raise already landed in S5's pull request. S7's pull request is expected to raise the cap to 16,700, which would leave room. No raise is planned here: if the measured free lines at build time are fewer than this change needs, this pull request raises the cap by the difference, with the comment naming this spec, and the plan carries that as its own commit.

## 5. Constraints

- No safety surface in FOUNDRY.md's Two lanes list changes: no settings, sandbox, publish gate or redaction code, and no note type. It is a feature, so it takes the plan.
- `system/pipeline.yml`'s intake node (`pipeline.yml:24-36`): `scripts` gains `vaultlib/followups.py`; `reads` gains `raw/*/archive/` and `system/logs/followups_queue.txt`; `writes` gains `system/logs/followups_queue.txt`. `wiki/*/Now.md` is already listed in both.
- FOUNDRY.md's Now paragraph (line 133) names `[via:: digest]`, the digest path as evidence, the expiry (or the O1 answer), and the caps. One `changes/` file.
- Tests stub everything; no test calls claude. Fixtures use invented digest names and statements (template rule).

| Defect class | What holds it |
|---|---|
| C2 Now line | Every line goes through `nowmod.add` (cap, fit, dedupe); `test_followups.py` checks a long bullet is cut and keeps `[via:: digest]` and the evidence |
| C6 race | The queue is written and read only under `intake.lock`; the add runs under `run.lock`; a busy lock leaves the queue for the next tick (`test_followups.py`) |
| C7 redaction | A bullet with a credential shape lands redacted (`test_followups.py`) |
| C8 names | A cross-wall bullet's alert names no note (`test_followups.py`) |
| C11 input bounds | The per-digest and per-day caps; a digest with no section or a non-digest type adds nothing (`test_followups.py`) |
| C12 stale docs | FOUNDRY.md names `[via:: digest]`; prose only, since no docs test lists the writers |

## 6. Tests the plan needs

`system/tests/python/test_followups.py` (new):
- A digest with three follow-ups adds three owed lines on its partition's page, each with `[via:: digest]`, a due and the archive path as evidence.
- A bullet equal to, or contained in, an open line of any kind is skipped; an open line with a pull request URL as evidence skips a bullet naming that URL; a same-day line sharing 3 words skips, a line from a week earlier sharing the same words does not.
- A line closed `[-]` within 14 days (on the page, and in `now-archive/`) skips the same bullet from a second digest.
- A digest handled once is gone from the queue; running the step again adds nothing.
- A crash between the adds and the queue rewrite (the queue left as it was) adds nothing on the next run.
- Six bullets add five, with one alert; eleven queued digests on one day add ten lines and leave the rest queued for the next day.
- A personal digest's line goes only on the personal page; a shared digest's goes on the work page; a bullet with a link into the other partition is skipped with an alert that names no note.
- A credential-shaped bullet lands redacted; a 400-character bullet is cut and keeps its tag and evidence.
- A `meeting_input`, a stale-claims digest and a digest with no Follow-ups add nothing; `- None.` adds nothing.
- A backfilled digest (`provenance: ["headless"]`, `-backfill.md`) is proposed like any other.

`system/tests/python/test_now.py`: `via("[via:: digest]")` is `digest`; an untouched `digest` line expires after 7 days and one with a note under it does not (or the O1 answer's behaviour).

`system/tests/python/test_intake_digests.py`: a batch that archives two digests queues both destination paths, including a `unique()` rename; a failed rename queues nothing; `check_now` with a busy `run.lock` leaves the queue unchanged.

`system/tests/pipeline.bats` passes with the node's new reads and writes.

## 7. Delivery

One plan (`superpowers:writing-plans`), then one pull request, failing tests first, after #436 S7 and S8 merge (Q5). Part of #476; the plan's first commit marks #476 in progress on the roadmap and its last marks the first phase done, leaving the future-phase items open on #476.

**Live acceptance** (a throwaway clone under `.scratch/`, intake run by hand): drop a digest with two follow-ups into `raw/work/notes/`, one of them already added with `now.py add`; run intake twice (the first tick archives and queues it, the second adds); the work page gains one `[via:: digest]` line; mark it `[-]`, run intake again, nothing comes back. `_archive_batch` runs only when the ingest run exits 0 (`intake.py:451-452`): the plan first checks whether a stubbed `CLAUDE_BIN` (`run_headless.sh:11`) gets the digest archived; if not, the run needs real claude, which is the owner's approval.

## 8. Owner decisions

**O1 decided (owner, 2026-11-03): (b).** `digest` joins `MACHINE`; an untouched proposal expires as `[-]` after 7 days; a note under it or deleting its `[via:: …]` field keeps it; `[x]` means done. §3's and §6's "or the O1 answer" clauses resolve to this. The grill's Q4 wording ("`[x]` keeps") is superseded by it.

- **O1. What `[x]` means, and what happens to an untouched proposal.** The grill says "`[x]` keeps, `[-]` drops, as held research claims do". On every other Now line `[x]` means done, and the brief's From Now block ticks lines the same way.
  - **Recommended (b): a machine line.** `digest` joins `MACHINE`. An untouched proposal expires as `[-]` after 7 days, the owner keeps one with a note under it or by deleting its `[via:: …]` field (the mail and chat rule), `[x]` is done. No code beyond the tuple, the page stays bounded, and a week of silence counts as a drop in the health share.
  - (a) An ordinary line: open means kept, `[x]` done, `[-]` dropped, no expiry. The decide-by date moves it into Overdue after 30 days. No code; the page can fill with proposals nobody decided.
  - (c) The grill's words read literally: an open proposal waits, `[x]` makes the step reopen the line as the owner's own (the box cleared and the `[via:: …]` field removed), `[-]` drops. About 15 more lines, and `[x]` on these lines alone means "keep", which the brief's From Now block does not show.

## 9. Left to the builder

The module's name and function split; the queue file's exact name; the normalization's character classes; where the per-day count reads the page; the alert wording; test names within the files in §6.
