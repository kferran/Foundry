# Run-time resilience 2: Now merges, a gated update, notice holds, retention and the calendar check (#436 S2, S5–S8)

**Grill:** 2026-11-03, the owner took every recommendation: https://github.com/kferran/Foundry/issues/436#issuecomment-6598636084, copied under `## Grill`.
**Builder check:** 2026-11-03, by the author against master `7e2f7b4`. Six questions were settled in §3 to §8: curl is not a listed dependency; `get-url` expands `insteadOf`; no raw `list_events` page is recorded; an offline client ticks a line the server archives; old run folders that a recovery still needs; the watch shares the calendar log. A fresh builder check (2026-11-03) found: the client merges through Obsidian Git, outside the driver (§9 Q-C); the "settled" run folder needs both conditions (§6); extraction entries also wait 30 days (§6); a smaller calendar mark through the existing unavailable line (§7); the prune log dropped; the lift touches `hold.lifted` (§5); five wrong line cites corrected. The owner decided its three questions as recommended (§9).
**Blueprint:** none: fixes to the existing sync, update, notify, intake and calendar code.

## 1. Why

S1, S3 and S4 shipped (#460, #461, #469). Five findings remain, re-checked on master `7e2f7b4`. How often each happens is unknown.

- **S5.** A merge conflict blocks intake, the brief and the debrief until merged by hand (`vault_sync.sh:137-146`, `block()` :88-93, `--pre` exit 3 :103). `wiki/<p>/Now.md` is the one note both machines write.
- **S2.** `update_template.sh:103` merges the template's head every morning without looking at its CI.
- **S6.** Exit 7 writes `system/logs/notify/hold` (`notify.sh:72`), and every tick then exits 5 (:40) until the owner deletes it.
- **S7.** Nothing prunes `system/logs/runs/`, `system/logs/inputs/`, `system/quarantine/` or `extracted_blocks.jsonl`, which every 5-minute tick reads in full up to three times (`vaultlib/intake.py:212, 262, 282`).
- **S8.** `calendar_tsv.py:113-125` checks the shape of the model's output. The `list_events` results (`w.results`, :103-104) are checked only for size.

## 2. Goals

1. A Now.md conflict the line rules settle no longer blocks the sync.
2. The unattended update merges a GitHub template commit only after its check runs pass.
3. A notice hold ends itself after 24 h and says so.
4. Old run folders, prep inputs, settled quarantine and extraction records go after 30 days.
5. A brief whose calendar rows disagree with the connector says so.

**Non-goals:** `--rollback` and a `stable` tag; rebuilding rows from the raw result; pruning what Q4 does not name (ledgers, monthly logs, intake manifests, `alerts_<date>.md`); a merge driver for any other file.

**Anti-goals:** the Now merge never guesses; a line it cannot place blocks the sync as today, and no tick or note is lost. An unknown CI state never merges. The prune never deletes a poisoned input, a quarantined meeting, or a run folder that a recovery or commit still needs. No new unit or config key.

## Grill

Copied verbatim from the issue comment:

> ## Grill: S2, S5-S8 (owner took every recommendation, 2026-11-03)
>
> | # | Finding | Decision |
> |---|---|---|
> | Q1 | S5 Now.md conflict | A git merge driver for `wiki/<p>/Now.md` in `now.py`, wired at `vault_sync.sh`'s merge: a tick on either side wins, lines added on either side are kept, a line rewritten on the server and ticked on the client keeps the server's text with the tick. Any other conflicting file still blocks. |
> | Q2 | S2 update with no CI gate | `update_template.sh` reads the public check-runs of the template head commit (`curl` + `jq`, no auth): all green merges; pending, red or unreachable skips today with one alert naming the commit and tries the next run; a template remote that is not GitHub merges as today (documented). No `--rollback`: the post-merge alert names the merge commit and FOUNDRY.md documents `git revert -m 1 <sha>`. |
> | Q3 | S6 Slack hold | The hold lifts after 24 h with a repeat alert; the next notice runs under the same checker, so a second trip holds again. |
> | Q4 | S7 retention | A prune step in the intake tick: `system/logs/runs/`, `system/logs/inputs/`, quarantine's held-back run staging and state backups keep 30 days; poisoned inputs are never deleted automatically; `extracted_blocks.jsonl` drops only entries for briefings already archived, and the builder shows a pruned entry cannot cause a re-ingest. |
> | Q5 | S8 calendar | Compare the model's rows with the raw `list_events` results (count, start, title); on a mismatch alert once a day and mark the brief's calendar unverified. Rebuilding rows from the raw result waits until the log shows a mismatch. |
> | Q6 | Delivery | One spec for all five; one PR per finding in the order S5, S2, S6, S7, S8; the owner merges each. |
>
> https://claude.ai/code/session_01EZnnKRuLxKtqiULqPqSgoJ

## 3. S5: Now.md merges by line

**Wiring.** The merge at `vault_sync.sh:137` gains `-c core.attributesFile="$attrs" -c merge.now.driver="<quoted absolute now.py> merge-driver %O %A %B"`, where `$attrs` is a `mktemp` file holding `wiki/*/Now.md merge=now`, removed on EXIT (the `update_template.sh:99-103` pattern). The vault's `.gitattributes` is untouched and sets no `merge`. For this one command the temporary file replaces the user's global attributes file, as it does in the update. Hand merges and the update's merge define no driver and stay textual. The driver takes no lock and reads only its three files: the sync holds run.lock while git runs the driver (fd 9 closed, :24), and now.py's writers take run.lock (`now.py:154`).

**The driver.** `now.py merge-driver` calls `vaultlib/now.py` `merge(base, ours, theirs)`. It writes the result to %A and exits 0, or prints one reason to stderr and exits 1. Each version splits into blocks (a `- [` line and its notes, `_block_end` :149) and layout (every other line). A block belongs to the heading above it.

- **Identity.** A line's key is the line minus trailing space, its `[.]` mark and its ` _(closed: …)_` suffix (`STAMP` :35). Blocks pair by key. A base block left unpaired on one side pairs with the one unpaired line there that parses (`parse` :55) with the same kind, since and who in the same section. That catches `set_statement` (:420), `add`'s updated forms (:327) and `tag_writers` (:549). With zero or several candidates the block stays unpaired. A hand-written line pairs by key only.
- **Mark:** three-way. When both sides change it differently, closed beats open and `[x]` beats `[-]`.
- **Text and layout:** three-way each. When both sides change either one differently, the driver exits 1.
- **Suffix:** an open line has none (:141). A closed line takes the closing side's suffix, or ours when both sides have one.
- **Notes:** exact lines. A note either side removed goes. The result keeps ours in order, then theirs' new notes.
- **Deletion.** Gone on one side and unchanged on the other: gone. Gone on one side and only closed on the other: gone, but only when the deleting side had no rewrite candidate for it. This covers the offline client: the brief archived (:168) a line the client had ticked. Gone on one side and changed on the other in its text or notes, or in its mark with two or more candidates: exit 1, so an ambiguous rewrite never drops a tick.
- **Added blocks** are kept; one added on both sides is kept once. Theirs' new block goes after its predecessor on theirs, or first in its section.
- **Exit 1** also for a key twice in one version, a note twice under one block, a conflict-marker line in any input (a criss-cross base can hold one), or a file that is not UTF-8.

The grill's case pairs as a rewrite: the server's text, the client's tick. The rules are the same whichever side rewrote.

**Failure.** Exit 1, or a crash, leaves Now.md conflicted. :139 then aborts, pushes the pending branch and blocks as today. The marker (:90) adds `now merge: <reason>` from `$err`. A conflict in any other file still blocks.

**Docs.** FOUNDRY.md:279 is stale: the server writes Now.md for more than closing lines (`add`, `set`, `note`, `tag_writers`, expiry, the brief's publish). It now gives the line rules, says that an unplaceable line still blocks, and that the driver settles the server's merge only: a conflict on a client is merged in Obsidian (Q-C).

**Tests.** `test_now.py`: `test_merge_tick_against_close`, `test_merge_rewrite_and_tick`, `test_merge_adds_on_both_sides`, `test_merge_archived_against_ticked`, `test_merge_blocks` (each exit-1 case). `sync.bats`: "a settled Now.md conflict does not block", "a refused one blocks with its reason", "another file's conflict still blocks", "a hand merge has no driver".

## 4. S2: the update merges only a green template commit

**Where.** In `--unattended`, after the nothing-new exit (:92-95) and before the merge (:99), on the `template/<branch>` commit just fetched.

**Owner/repo.** These come from `git config --get remote.template.url`, the raw URL (`git remote get-url` expands `insteadOf`, which the tests use). They go through the sed at `lib_prep.sh:62`, which moves to `lib_git.sh` as `git_github_slug` for both callers. A template not on github.com merges as today, and FOUNDRY.md says so.

**The check.** `curl -fsS --connect-timeout 10 --max-time ${UPDATE_CHECKS_TIMEOUT:-20} "https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs?per_page=100"`, with no token: one request a day, against a limit of 60 an hour. It is **green** when every run comes back (`total_count` equals the list length), every run is `completed` with conclusion `success`, `neutral` or `skipped`, and at least one is `success`. Otherwise the state is one of:
- **pending:** a run is not completed;
- **failing:** some other conclusion, named by check;
- **no runs:** none, only skipped or neutral, or more than 100;
- **unreachable:** curl failed, HTTP error, unreadable JSON.

Skipped and neutral pass because GitHub's required checks count them as passing. Requiring one success keeps a template with CI off (its jobs skip unless `FOUNDRY_CI` is true, `gate.yml:10`) from reading green. Every app's runs count (on 2026-11-03 master's three were all from github-actions).

**Not green.** The update exits 0 with the vault unchanged and writes one `[update]` alert (Slack carries it, `vaultlib/alerts.py:14`; the timer is daily): `template update skipped: CI for <owner>/<repo>@<sha12> is <state>; the vault is unchanged; the next run tries again`. The alert carries the usual `committed first` prefix.

**After a merge.** The `template updated:` alert (:186) adds `; merge <sha12> (undo: git revert -m 1 <sha12>)`. FOUNDRY.md Updating gives the revert, and notes that the reverted commits stay out of later updates until the revert is itself reverted.

**Deps.** `curl` joins `check_deps.sh:26` for standalone and server; no script uses it today. `conformance.bats` gains `update.checks` and the step `update 1 - update.checks`. The update runs its old script, so the gate applies from the morning after its merge.

**Tests.** `remote.bats`, with a PATH `curl` stub and a template URL of the form `https://github.com/<owner>/<repo>.git` fetched locally through `insteadOf`: "a green head merges and names its revert", "each other state skips with one alert, exit 0", "no curl call off GitHub or with nothing new", "a hand run merges". `lib.bats`: "git_github_slug reads https and ssh forms".

## 5. S6: a notice hold lifts after 24 h

Before `notify.sh:40`, a hold more than 24 h old by mtime (`find "$hold" -mmin +1440`) moves to `system/logs/notify/hold.lifted` and is touched, so its mtime is the lift time. The tick alerts once a day `[notify] Notices hold lifted after 24 h: <the hold's line>; a session that breaks its rules holds them again`, then goes on. A younger hold exits 5 as today. The next session runs under the same checker (:70-72), so a second trip holds again (Q3). A hold written within 7 days of a lift (`hold.lifted`'s mtime) stays until deleted by hand, and its alert says so (Q-B). `[notify]` has severity `never` (`alerts.py:23`): the lift shows in the brief, never in Slack. After the lift the collector's one-day window for unsent events applies.

**Docs:** FOUNDRY.md Slack notices ("until you … delete the hold file") and `notify.sh:9`. **Tests** (`notify.bats`): "a hold older than 24 h lifts with one alert and the tick posts", "a younger hold still exits 5", "a rule break after a lift holds again".

## 6. S7: one prune a day

**Trigger.** `Intake.run` (`intake.py:861`) calls `prune()` after `extract_briefing`, in its own `try`. On an exception it alerts `prune failed (…); will retry`. It runs once a day: it skips when `system/logs/.pruned` holds today's date, takes run.lock with timeout 0 (busy: the next tick tries), and writes the date after a full pass. The cutoff is today minus 30 days, in the vault's timezone.

**What goes.**
- `system/logs/runs/<run_id>/` folders dated before the cutoff, once settled. Settled needs both: (1) the publish journal is absent or `_committed` (`publish.py:484`; `recover` :610 rolls forward the rest), and (2) a `committed` marker, a `publish.json` that published nothing, no `publish.json` at all (a run that ended before publish), or an id before `commit_runs.since` (`pending`, `commit_runs.py:68-85`, commits the rest). An unsettled old folder stays, and one `[intake]` alert a day names the count and the oldest id.
- `system/logs/inputs/<date>/` folders before the cutoff (`/brief <date>` rebuilds one, `brief.md:13`).
- `quarantine.items` rows of kind `run` and `telemetry_state` aged 30 days or more (the brief's "safe to delete"). Poisoned and meeting rows are never touched.
- `extracted_blocks.jsonl` entries for a `briefings/<date>.md` dated before the cutoff whose file is gone while `briefings/archive/<YYYY-MM>/<date>.md` exists (both conditions: the 30 days keep the #57 re-save window covered), rewritten with a temp file and `os.replace` under run.lock (extraction's lock, :199).

**Why a pruned entry cannot re-ingest.** The three readers (`done` :212, `known` :262, the alert dedupe :282-283; every `intake.py` line here is `system/scripts/vaultlib/intake.py`) only ask about the briefing being extracted. Only `briefings/<today>.md` (:197) and the non-recursive `briefings/*.md` glob (:213) are extracted, so an entry for an absent path matters again only if a file reappears there. `brief_prep.sh:115-140` never moves one back. A file can reappear through a hand restore, or through a client that re-saves an archived briefing it still had open (the reason yesterday's stays a day, #57). Either way, its blocks drop again with the same bytes (`body + "\n"`, :272). `_inbox_file` (:348) finds their sha in the intake manifest (`manifest_has` :170, this year and last, not pruned) and archives them as duplicates with no session. A re-ingest needs a reappeared briefing plus a block that never published (a retry, as today) or published before last calendar year.

**Docs:** one sentence in FOUNDRY.md Repository layout. **Tests** (`test_intake.py`): `test_prune_runs_settled_only`, `test_prune_inputs_and_safe_quarantine_only`, `test_prune_entries_of_archived_briefings_only`, `test_restored_briefing_drops_a_duplicate`, `test_prune_once_a_day_and_lock_busy`.

## 7. S8: the calendar rows checked against the raw results

**The comparison.** After `rows` (`calendar_tsv.py:123`), each `list_events` page in `w.results` (`connector.py:58`) is read with `structured` (:33) or `text_json` (:40), whichever the probe shows. Each raw event becomes (start date, start time, title). A timed start converts to the run's TZ (`calendar_fetch.sh:22-23`), an all-day start keeps its date with an empty time, and the title gets rows()' cleaning (:67). These triples are compared as sorted lists with the rows'. A mismatch sets `unverified` to the first difference, with no event text: `the connector listed N events, the rows hold M`, or `row K (<date> <time>) differs from the connector's results`. Unreadable pages read `the connector's results could not be read`, so a shape change shows instead of switching the check off. The exit stays 0 and the rows are written.

The repository records no raw page: the calendar spec and fixtures hold only the structured output. So the plan's first task captures one real page (real claude, the owner's calendar, sandbox off, the owner's approval), and a scrubbed copy becomes the fixture.

**Report.** The summary gains `unverified` ("" when verified), which `finish` (`calendar_fetch.sh:38`) logs. `calendar_fetch.sh` alerts `[calendar]` (severity brief, `vaultlib/alerts.py:19`) once a day, keyed `calendar rows unverified:` (`alert_once` needs `FETCH_TAG=calendar`; :68 writes the tag by hand today). The brief, the smoke `--check` and the intraday watch all run this script, so they raise one alert between them, and `--check` still passes. It also prints `calendar_fetch: unverified: <reason>` on stderr.

**The mark.** On exit 0, `brief_prep.sh` reads that line from `prep_errors.log`, as its exit-6 branch does (`brief_prep.sh:27`), and adds `prep_unavailable "calendar: rows unverified: <reason> (check today's events in Google Calendar)"`. The brief already prints the unavailable lines, so `brief.md` does not change and the brief's live acceptance needs no re-run (author's call, from the builder check: the smallest path to Q5's mark).

**Tests.** `test_calendar_tsv.py`: `test_matching_rows_verified`, `test_count_mismatch`, `test_changed_row_named_without_text`, `test_all_day_and_offset_times`, `test_unreadable_pages_unverified`. `calendar.bats`: `stream_ok` (:20) gains a matching `list_events` result, because without one every existing case reads unverified; then "an unverified fetch prints the rows, exits 0 and alerts once" and "--check passes when unverified". `prep.bats`: "an unverified calendar adds one unavailable line; a verified one adds none".

## 8. Constraints and author's calls

- Exit codes, alert texts and log fields stay unless named. Alerts use existing tags (`scripts.bats` test 28). Bats ruling R1. Tests stub claude and curl.
- **Core cap.** Core is 15,830 of 15,850. Estimates: S5 90 lines, S2 40, S6 6, S7 50, S8 40 (about 226). One raise for the spec of 230 lines on the cap S5's PR finds (15,850 today → 16,080; if the recall R0 PR (#474) has raised it to 16,250 first, → 16,480), with one comment line naming all five. Going past it is the owner's call.
- **Safety surfaces:** sync (S5), update (S2), notify's fail-closed hold (S6), connector checker (S8). No unit file changes. The owner merges each PR.
- Author's calls: the details §3 to §7 add to the grill. Two need a reason here. A hand-run update stays ungated and prints the CI state, because the owner is at the keyboard and it is §9 Q-A's way out. The calendar mark reads the fetch's own stderr in `prep_errors.log`, never the month's log, which the watch appends to all day.

## 9. Decided by the owner

Decided by the owner, 2026-11-03: Q-A, Q-B and Q-C as recommended.

- **Q-A. A GitHub template that never goes green.** A fork with CI off (all jobs skipped) or a private template (unauthenticated 404) never updates unattended and alerts daily. Recommended: accept it with no config key; FOUNDRY.md names the way out, `system/scripts/update_template.sh` by hand, which stays ungated. The alternative is an `update_ci_check: off` key.
- **Q-B. Does a second hold lift too?** Read literally, Q3 lets a session that keeps breaking its rules post once a day forever, each post checked only after it ran. Recommended: a hold written within 7 days of a lift (`hold.lifted`'s mtime) stays until deleted by hand, and its alert says so (about 3 lines). The alternative is that every hold lifts after 24 h.

- **Q-C. The client's own merges.** The client syncs through Obsidian Git (FOUNDRY.md:261, `syncMethod: merge` from `setup.md:140`), never `vault_sync.sh`, so the driver runs only when the server merges. When the server's commit reached origin first (the offline client in §3's deletion rule, whose brief archive was pushed hours earlier), the client does the merge, textually, in Obsidian. Recommended: the server's merge only. The finding's cost is the server's block, which stops intake, the brief and the debrief, and only the server's merge causes it; a conflict on the client stops no run, and Obsidian shows it. FOUNDRY.md says the driver settles the server's merge and a client conflict is merged in Obsidian. The alternative has `/setup` write the driver into a client's `.git/config` and `.git/info/attributes`, which also makes hand merges use it, needs a real-client test harness, and does nothing on Obsidian mobile (isomorphic-git ignores merge drivers).

## 10. Delivery

- One plan (superpowers:writing-plans), a task group per finding. One PR per finding, in the order S5, S2, S6, S7, S8, failing test first. The owner merges each.
- Each PR's first commit marks its finding in progress on the roadmap's #436 line (`docs/superpowers/roadmap.md:77` names only S1, S3 and S4; S5's first commit adds S2 and S5–S8), and its last commit marks it done. Release notes: `changes/<date>-now-merge.md`, `-update-ci-gate.md`, `-notify-hold-lift.md`, `-log-prune.md`, `-calendar-check.md`.
- After the last merge: tick S2 and S5–S8 on #436 and close it.

## 11. Live acceptance

- **S5,** `.scratch`, sandboxed: a bare origin with a server and a client clone. A tick against a close, a rewrite against a tick, and archived against ticked all merge. Two rewrites, or another file's conflict, still block. On the real pair: the next Now.md conflict, with no `sync blocked`.
- **S2,** `.scratch` with network (sandbox off, owner approval): the real public template as the remote. The green head merges. A real failed or no-run commit, served through `insteadOf`, skips with the alert. Then the server's first morning `[update]` line.
- **S6:** tests only (`touch -d`).
- **S7,** `.scratch` with aged folders, then the server: the first prune line, and no Notes drop for archived dates the next morning.
- **S8,** real connector: Task 1's probe and one verified real fetch in `.scratch`. On the server's first day, any `calendar rows unverified` alert is traced, and a false mismatch is fixed before S8 is ticked.

## 12. Left to the builder

The layout of a merged page within §3's rules; the raw event field names, from the probe; where `prune()` lives; the FOUNDRY.md wording.
