# Recall R0 and R1: measure recall, and backfill a missed digest (#449, #438)

**Grill:** 2026-10-31, the owner's round 1 for the whole recall track on #449, copied verbatim in `## Grill` below.
**Builder check:** 2026-11-03, six questions found while writing, all settled. `vault_index.py` resolves the caller's scope with one `git` call per codebase before any subcommand runs, too slow for a hook on every Bash call: the pull log gets its own entry point and reads the frozen session state (§3.3). The headless settings block reads outside the vault (`blockReadsOutsideWorkingDirectories`), and the kept transcript lives outside it: the tick writes a redacted excerpt into the vault first (§4.3). `memory_capture.sh` resets the event counter after a missed request, so the counter alone would skip the very session R1 is for: the queue test also reads `last_request_at` (§4.1). A backfill written days later would sort as the newest digest in recall: `created_at` is the session's end (§4.4). `PostToolUse` may not fire for a Bash call that exits non-zero, which hides a `show` miss: the plan probes it first (§3.3). The digest's frontmatter is model-copied: the tick reads it back and quarantines a mismatch (§4.4). A fresh builder check on 2026-11-03 found: the §1 loss case was overstated (corrected), five more `run_headless.sh` places that name commands (§4.2), `commit_runs.py` must keep its own run id pattern (§4.2), the read-back also checks provenance and Corrections (§4.4), two index calls in one command share their output (§3.3), and whether `SessionEnd` fires on a killed terminal is unknown (O3).
**Blueprint:** Compile run (R1, the digest backfill); R0 adds log lines to the existing recall and hooks and needs no shape.

## 1. Why

Nothing records what recall does or whether it helps (#449).
- `vaultlib/recall.py` builds the SessionStart block. Nothing logs its size, how many Now lines it showed or hid, or which digests it held.
- `usage_log.sh` logs slash commands and Skill calls in vault-root sessions only. Nobody can tell whether a session pulls from the index after the push.

A session's digest exists only if the working agent writes one when the `Stop` hook asks (#438). It is lost when the agent ignores the request and the session ends before the next one (`memory_capture.sh:73-78` alerts and skips that request; lines 83-90 ask again only after another `digest_min_events` events and `digest_min_minutes` minutes), when the session ends before the thresholds are first met, or when the terminal closes (if `SessionEnd` fires then: O3). `memory_keep.sh` already copies every in-scope transcript to `transcript_keep_dir` at `SessionEnd`, and no script reads the copies.

Every later recall change (R2 to R6: #450, #439 with #444, #446, #440, #345) is built only if R0's numbers show its gap (Q1).

## Grill

| # | Question | Decision |
|---|---|---|
| Q1 | Worth building? | Yes for R0 (this issue) and R1 (#438), now. R2–R6 are built only if R0's numbers show the gap each one targets. |
| Q2 | For whom? | The owner's interactive sessions in the vault and in registered codebases, the Foreman session included. Headless runs, Work Orders and subagents stay out (the recall hook already skips them). |
| Q3 | Without it? | Acceptable for a few more weeks, not for good. Without R0 no later recall change can show it helped. |
| Q4 | Smallest version | R0 is two logs only: what recall pushed, and which `vault_index.py` commands each session ran. Plus R1. The retrieval eval set waits for R4 (#446), the first change that needs scoring. |
| Q5 | Displaces | Recall goes ahead of console C2/C3, Foreman dispatch and gap plan E–G, and behind the audit track's security work (Work Order confinement PR C and #433). |
| Q6 | Core budget | One raise of the core cap, about 400 lines for R0–R5, stated in the recall spec. No raise per PR, and memory does not move to an extension. |
| Q7 | Where R1 runs | In the intake tick, from a queue the hook writes. The hook only records the session id. The tick writes the digest through staging and redaction, waits at the usage ceiling, and marks it `provenance: headless`. |
| Q8 | What the logs hold | Counts, note ids and paths only. No prompt text, no note text, and query terms hashed. |

## 2. Goals

1. Every SessionStart recall in scope leaves one line saying what it pushed.
2. Every `vault_index.py` call an in-scope session makes leaves one line saying what it asked for and what came back, by count, id and path.
3. An in-scope session that did real work and ended with no digest gets one, written from its kept transcript by a confined headless run, within a few intake ticks of its end.

**Non-goals:** R2 to R6. The retrieval eval set (Q4: it waits for R4, #446). The health scorecard reading the log (#374 can read it once it exists). Digests for the tail of a session that already has one (§8, O1). Log retention: the monthly file follows `usage-<YYYY-MM>.jsonl`, which has none today (#436 S7 covers both).

**Anti-goals:** a log line that holds prompt text, note text or a query in clear (Q8). A hook that can fail, block or slow a session past its budget. A backfill that writes a second digest for a session, runs above the usage ceiling, or writes anywhere the publish gate did not check. Headless runs, Work Orders and subagents in either log or the queue (Q2).

## 3. R0: two logs

### 3.1 The file

Both logs append to `system/logs/recall-<YYYY-MM>.jsonl` (gitignored under `system/logs/*`), one JSON object per line, each with `ts`, `kind` (`push`, `pull`, or R1's `backfill`) and `session` (the session id). A torn last line is terminated before the next append, as `intake._append_jsonl` does; that helper moves to a module `recall.py` can import without loading intake (builder's call where). Every write is wrapped so a failure is swallowed: logging never changes recall's output or a hook's exit.

### 3.2 The push log

`vault_index.py recall` gains `--session-id` and `--source` (the SessionStart `source`: startup, resume, compact or clear). `memory_recall.sh` passes both. Without `--session-id` (a manual run) nothing is logged.

`recall.build` returns its counts beside the text (builder's call how), and `cmd_recall` writes one line after the block is on stdout:

```json
{"ts": "...", "kind": "push", "session": "<id>", "source": "startup", "scope": "codebase", "codebase": "<name>",
 "partition": "work", "budget": 9000, "chars": {"head": 0, "dirty": 0, "now": 0, "digests": 0, "total": 0},
 "now_shown": 0, "now_hidden": 0, "digests": ["<digest stem>"], "digest_truncated": false, "index_wait_timeout": false}
```

`index_wait_timeout` is the `waited` flag from `_open_index` (the 2 s lock wait ran out and recall read the index unrefreshed). A block that came out empty still logs its line with `chars.total: 0`, since "pushed nothing" is a number R2 to R6 need. A Workcell session (`FOUNDRY_WORKCELL_SESSION=1`) logs nothing (Q2). When the hook's own `timeout 3` kills recall, or recall fails, the hook's existing failure branch (`memory_recall.sh:24`) appends `{"kind": "push", "session": ..., "failed": true}` with one `jq` call, on that path only.

**Time budget.** The SessionStart entry has a 5 s hook timeout (`install_hooks.sh:87`), and the hook gives recall 3 s (`memory_recall.sh:23`), inside which recall already spends up to 2 s on the index lock (`LOCK_TIMEOUT`) and 0.4 s on `git status` (`GIT_TIMEOUT`). The log adds one append of under 1 KB with no lock and no fsync, after the block is built, so it cannot push recall past its 3 s. No new hook entry and no `install_hooks.sh` change.

### 3.3 The pull log

**Where the data comes from.** `memory_activity.sh`, the existing `PostToolUse` hook, records the pull. Reasons from the code:
- It already matches `Bash` (`install_hooks.sh:89`) and runs only for sessions the memory hooks froze in scope (the `.eligible` file), with subagents skipped. That is Q2's set, codebase sessions included, and it needs no settings change.
- `usage_log.sh` acts only when the session's cwd is the vault root (`usage_log.sh:16`), which drops every codebase session, and it matches only `UserPromptSubmit` and `PreToolUse` on `Skill` (`install_hooks.sh:94-95`), never a Bash call.
- Logging inside `vault_index.py` cannot tell an agent's call from the scripts' and hooks' own calls (`lib_memory.sh` runs `query`, `memory_keep.sh` runs `field`, `run_headless.sh` runs `field`, headless ingest runs `related`), and it has no session id.

**The fast path stays.** The hook is pure bash because one `jq` call costs about 44 ms (spike item 15) and it runs on every edit and Bash call. After its counter write it tests, in bash, that the tool is `Bash` and that `$input` contains `vault_index.py` (the input also holds `tool_response`, so a note that mentions the script can still take the slow path, which reads only `tool_input.command`); only on a hit, and not in a Workcell session, it calls `system/scripts/recall_log.py pull` with the hook JSON on stdin. That entry point (a short wrapper like `vault_index.py`) skips the scope resolution in `cli.main`, which runs `git` once per registered codebase, and reads the scope from `system/logs/memory/sessions/<id>.json`. The slow path targets under 200 ms at p95, measured in the plan's probe; the hook's 5 s timeout and fail-open exit stay.

**What it records.** It splits `tool_input.command` with `shlex`, finds each `vault_index.py <sub>` invocation, and writes one line per invocation:

```json
{"ts": "...", "kind": "pull", "session": "<id>", "scope": "vault", "partition": "personal", "sub": "related",
 "terms": "<16 hex>", "hits": 4, "paths": ["wiki/personal/concepts/Example.md"], "note": null, "found": true}
```

- `related` and `query`: `terms` is a keyed SHA-256 of the argument (lowercased, whitespace collapsed), first 16 hex digits. The key is random, made on first use at `system/logs/memory/recall.key` (mode 600), so a short term cannot be found by hashing guesses, and the same terms still hash alike within one vault (author's call). For `related`, `hits` and `paths` (at most 10) are the vault paths parsed from its output lines, never the titles.
- `show` and `backlinks`: `note` is the argument as given (a note name or vault path, which Q8 allows); `found` is whether `show` printed a note, or `backlinks` printed any path (with `hits` and `paths` as for `related`).
- Any other subcommand: `sub` only.
- Two or more `vault_index.py` calls in one command share one `tool_response.stdout`, so their output cannot be split: each line then has `hits: null` and no `paths` (author's call, from the builder check).
- `tool_response` is read for those counts and paths and never written: for `show` it is the whole note.

**Probe first.** The plan's first task runs one real session with the hook and records the `PostToolUse` input for a `vault_index.py show` that finds a note and one that exits 1. If a failed Bash call fires no `PostToolUse` (or fires `PostToolUseFailure` instead), the log records what it can see and FOUNDRY.md says misses are not logged; adding a matcher for the failure event is the builder's call if it exists and costs no settings change beyond `install_hooks.sh`'s owned entries.

## 4. R1: backfill a missed digest

### 4.1 The hook queues the session id

`memory_keep.sh` on `SessionEnd` (never `PreCompact`, which is #440), after its copy step, creates an empty marker `system/logs/memory/sessions/<id>.backfill` when all of these hold:
- the event has no `agent_id` and `FOUNDRY_WORKCELL_SESSION` is not `1` (Q2; `memory_keep.sh` has no Workcell check today);
- the session state `<id>.json` exists (the hooks froze it in scope) and its `last_digest_at` is 0 (the session has no digest);
- the session did real work: `<id>.events` is at least the state's `digest_min_events`, or `last_request_at` is set (the Stop hook asked, which it does only after that many events; after a missed request `memory_capture.sh:77` resets the counter, so the counter alone would skip this case).

The marker holds nothing but its name (Q7). It sits beside the state, so `mem_prune` deletes a stale one after 14 days on every machine, a client included (a client runs no intake). The owner's interactive sessions run on the server or a standalone machine (roadmap, Two machines: a client reads and edits the vault in Obsidian), so the logs and the queue live where intake runs; a session on a client is logged and queued there and never backfilled, which FOUNDRY.md says. These are shell tests on files the hook already reads, plus one `jq` read of the state, inside the existing 30 s `SessionEnd` timeout.

### 4.2 The tick

`Intake.run()` gets a backfill step after `process_digests`, under `intake.lock`. For each marker at least `FRESH_SECONDS` old, oldest first, while `self.runs < self.max_runs`:
1. `self.held()` (the usage ceiling, `order_max_five_hour`): when held, the marker stays and the step ends.
2. Read the state. A missing state, or a missing `<keep_dir>/<id>.jsonl`, ends the marker with a `backfill` log line naming why.
3. **Idempotence.** If any `*-<id8>-*.md` exists in `raw/<p>/notes/`, `raw/<p>/archive/` or `system/quarantine/poisoned/` (the name pattern every digest has, `memory_capture.sh:32`, and the check `stale_claims_input` uses), the session has a digest: drop the marker. This also covers a Stop digest written after the marker. One session gets at most one backfill, ever: a resumed session whose earlier end was backfilled is not backfilled again (O1).
4. Build the excerpt (§4.3), write it, run the command (§4.5), then read the result back (§4.4).

Backfill runs share `self.runs` with the inbox and digest batches, so a tick still starts at most `INTAKE_MAX_RUNS` sessions and the conformance timing row `intake intake.runs grace.headless headless` covers them with no new step. They also count toward the daily headless cap (`run_headless.sh:140` counts `ingest` and now `digest-backfill`; author's call: the cap is the spend limit). `run_headless.sh` names its commands in several places, and each needs `digest-backfill`: the command list (`:37`), input validation (`:41-62`, where a non-ingest command refuses any argument at `:61`), the lock wait (`:115`, the `INGEST_LOCK_WAIT` branch), the cap check (`:137`, today ingest only), the targets `case` (`:150`) and the tool list (`:180`, hard-coded; the command's `Read,Write` becomes per command). `commit_runs.py:24` keeps its own run id pattern and stays as it is: a backfilled digest is gitignored (`raw/**`), and a matching pattern there would make `git add` fail and `/backup` refuse every run.

### 4.3 The excerpt

The headless session cannot read the keep directory, so the tick writes a redacted excerpt into the vault, the same path an inbox file takes (`_inbox_file`: redact, copy to `raw/inbox/.staging/`, run, unlink in `finally`).
- **Scope of the text.** User prompts and assistant text, in order, each with its timestamp; each tool call as one line (the tool's name and its file path, or the first 200 characters of a Bash command). Tool results are dropped: they are the bulk of a transcript and the least trusted part. Sidechain (subagent) entries are dropped (Q2). The plan's probe reads one kept transcript to confirm the field names before the parser depends on them.
- **Size limit.** At most 100,000 characters (about 25,000 tokens), keeping the newest part, with one `[… N earlier characters left out …]` line at the cut (author's call: the end of a session holds its outcome). A JSONL line over 2 MB is skipped unparsed (builder's call on the number; C11).
- **Redaction.** `redact.redact` runs on the excerpt before it is written; its count becomes the digest's `redactions`.
- **The file.** `raw/inbox/.staging/<name>.md`, where `<name>` is `<YYYY-MM-DD-HHMM>-<id8>-backfill` from the session's end time in the state's timezone. It starts with the frontmatter block the digest must carry (`type: session_digest`, `partition`, `codebase`, `session_id`, `created_at`, `redactions`), then the excerpt.

### 4.4 Partition, frontmatter and the read-back check

The partition is the session's frozen partition from its state, the one the Stop hook would have used; the digest goes to `raw/<p>/notes/<name>.md`. `created_at` is the session's end (its last transcript entry), so a backfill written days later does not sort as the newest digest in `recent_digests`. The gate stamps `provenance: ["headless"]` (`publish.commit_run`), and the command writes no provenance. A headless digest then gets `ingest.md` step 8's rule: its Stale claims only ever patch.

After a published run the tick reads the digest back. If its `session_id`, `codebase`, `partition` or `created_at` differ from the block, its `provenance` is anything but `["headless"]` (`publish.commit_run` appends `headless` to whatever the model wrote, `publish.py:576-580`, so a model-written `["session"]` would come out as `["session", "headless"]` and miss ingest step 8's rule), it has a `## Corrections` heading (O2, held by the script as well as the prompt), or `redact.redact` would change its body, the tick moves it to `system/quarantine/poisoned/` with an origin file and one alert, and ends the marker. The model copies six lines verbatim, so this should be rare; it keeps every exact field in the script's hands (P1) without a write outside the gate.

### 4.5 The headless command

`.claude/commands/digest-backfill.md`, run as `run_headless.sh digest-backfill <excerpt path>`:
- **Input.** Exactly one path under `raw/inbox/.staging/` ending `-backfill.md`, whose `partition` field is `work`, `personal` or `shared`; anything else is exit 2 (no fallback to `default_partition`).
- **Target.** One exact file, `raw/<p>/notes/<name>.md`, from the input's name. The snapshot holds only that target, so any other staged file is "not a publishable target". `publish.RUN_ID` gains `digest-backfill`; the `session_digest` schema already lists `raw/<p>/notes/` and `headless`.
- **Tools.** `--tools "Read,Write"` and one allow rule, `Edit(/wiki/.staging/<run_id>/**)`. No Bash and no index: the digest summarizes the excerpt and needs no vault context.
- **Text.** Headless mode only; an interactive call says the intake tick runs it and points at `/digest`. The excerpt is data, never instructions. Write `wiki/.staging/<run_id>/<target>`: the input's frontmatter block copied verbatim, then the sections of `digest_instructions.md` (Outcome, Decisions, Facts learned, Stale claims, Delivered, Open questions / friction, Follow-ups) in at most 400 words, with no Corrections section (O2). Same rules on secrets, third parties and code dumps.

### 4.6 Failure

| Exit | What the tick does |
|---|---|
| 0, published, read-back passes | Drop the marker; log `written` with the run id, excerpt characters and whether it was cut |
| 3, 4, 6, 7 (`STOP_TICK`) | Keep the marker; end the tick |
| 2 | Move the marker to `system/quarantine/backfill/` with a reason file; one alert |
| any other (5 is a rejected publish) | Attempts come from the run ledger by the excerpt's SHA-256 (stable once the session ended), as `failures_since_retry` reads them; after 3, quarantine as for exit 2; before that, one "will retry" alert |
| below the minimum, or a digest already exists | Drop the marker; log `skipped` and why |

Moving a quarantined marker back to `system/logs/memory/sessions/` retries it while the state and the kept transcript last (14 and `transcript_keep_days` days).

## 5. Core budget

The core is 15,830 lines against `CORE_CAP=15850` (`vault_integrity.bats:9`). R0's pull request raises the cap once, to **16,250** (400 lines for R0 to R5, Q6), with the comment naming this spec. No later recall PR raises it. R0 and R1 are expected to use about 260 to 290 of the 400 (R0 about 90, R1 about 170 to 200 with the command file); if the plan's estimate passes 300, the plan trims before building. No schema is added (`vault_integrity.bats:571` holds core at 14).

## 6. Constraints

- **Safety surfaces, so the owner merges both pull requests:** the hooks (`memory_recall.sh`, `memory_activity.sh`, `memory_keep.sh`), the headless runner (`run_headless.sh`), the publish gate (`publish.py`'s run id) and redaction on a new input path.
- A hook that fires on every tool call fails open and resolves its root from `BASH_SOURCE` (working rules).
- Tests stub claude; no test calls the real one. Bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing.
- Template rule: no hostname, user path, remote URL, or employer, client, codebase or people name in the code, tests, FOUNDRY.md or the change files. Fixtures use invented session ids and note names.
- FOUNDRY.md's Memory section gets the two logs, the queue, the backfill and the new command (the manual names every command: `vault_integrity.bats`); the `session_digest` schema's description names the backfill as a second writer. One `changes/` file per pull request.

## Blueprint checklist

R1 is a Compile run.

| Part | |
|---|---|
| `run_headless.sh` restricted settings | uses: `system/headless.settings.json`, with a per-command tool list (`Read,Write`) |
| timeout | uses: `HEADLESS_TIMEOUT`, unchanged |
| daily cap | uses: `digest-backfill` counts toward it |
| `run.lock` | uses: the `ingest` wait (`INGEST_LOCK_WAIT`); exit 6 keeps the marker |
| staging | uses: `wiki/.staging/<run_id>/`, one exact target |
| `publish.py` gate | uses: schema, walls and conflict checks on a `raw/<p>/notes/` target; provenance stamped |

| Defect class | What holds it |
|---|---|
| C3 timeout | The push log is one append after the block (`test_recall.py`); the activity fast path runs no `jq` or `python3` for a Bash call without `vault_index.py` (`memory.bats`, a PATH stub that fails if either runs); backfill shares `intake.runs` (`conformance.bats` unchanged) |
| C4 confinement | The excerpt is written inside the vault; `Read,Write` only; one exact target (`headless.bats`) |
| C6 race | A Stop digest written after the marker drops it (step 3, `test_intake_digests.py`); markers younger than `FRESH_SECONDS` wait |
| C7 redaction | The excerpt is redacted before it reaches the vault, and the read-back check quarantines a digest the redactor would change (`test_intake_digests.py`) |
| C8 names | A test puts a prompt, a note body and a query in front of both loggers and asserts none of their text is in the log (`test_recall.py`) |
| C11 input bounds | The excerpt cap and the line skip (`test_intake_digests.py`) |
| C12 stale docs | FOUNDRY.md names `digest-backfill` and both logs (`vault_integrity.bats`) |
| C14 gate escape | A staged second file, or a target in `wiki/`, is rejected (`test_publish.py`, `headless.bats`) |

## 7. Delivery

One plan (superpowers:writing-plans) at `docs/superpowers/plans/2026-11-03-recall-r0-r1.md`, then two pull requests, failing tests first, R0 first so the baseline starts before R1 changes what recall shows. The owner merges each.

**PR 1, R0** (part of #449). The cap raise; `recall.build`'s counts and the push line; `--session-id` and `--source`; the hook's failed-push line; `recall_log.py pull` and the activity hook's slow path; FOUNDRY.md; a change file.
- `test_recall.py`: the push line's fields; an empty block logs `chars.total: 0`; a Workcell session logs nothing; a log write that fails leaves stdout unchanged; the pull parser on `related`, `query`, `show` found and not found, `backlinks`, two invocations in one command, quoted arguments, and the keyed hash (same terms alike, no clear text).
- `memory.bats`: the hook passes the session id and source; a recall that fails writes `failed: true`; a Bash `show` logs one pull line, a plain Bash call logs none and runs no `jq` or `python3`, a subagent and a Workcell session log none.
- `vault_integrity.bats`: the cap at 16,250.

**PR 2, R1** (part of #438). The `SessionEnd` marker; the tick's backfill step; `run_headless.sh digest-backfill`; `publish.RUN_ID`; `.claude/commands/digest-backfill.md`; the schema description; FOUNDRY.md; a change file.
- `memory.bats`: `SessionEnd` queues a session with enough events and no digest, and one with a missed request and a reset counter; it queues none for `PreCompact`, a subagent, a Workcell session, a session with a digest, or one below the minimum.
- `test_intake_digests.py`: the excerpt (sidechain and tool results dropped, the cap and its marker line, redaction, the line skip); idempotence against notes, archive and poisoned; held at the ceiling; each exit in §4.6; the read-back check; runs shared with `max_runs`.
- `headless.bats`: `digest-backfill` takes only one `raw/inbox/.staging/*-backfill.md` input; its snapshot target is that one file; its tool list is `Read,Write`; it counts toward the cap.
- `test_publish.py`: a `digest-backfill` run id validates; a staged file outside the target is rejected.
- `commands.bats`: the command's frontmatter and headless-only text.

**Live acceptance** (once per PR, a throwaway clone under `.scratch/`, real claude, sandbox off, the hooks installed against the clone's settings):
- R0: start one session in the clone, run `related` and `show` once each, end it; the month's file holds one push line and two pull lines, and no prompt or note text.
- R1: run a session past five Bash calls and close it without a digest; the next tick writes `raw/<p>/notes/<name>.md` with `provenance: ["headless"]`; a second tick writes nothing more; the tick after that compiles it like any digest.

On the last merge: tick R0 and R1 on #449 and #438, and update the roadmap's recall track line. #449's proposal items 3 (the eval set) and 4 (health) stay open there as checklist lines, marked "waits for R4 (#446)" and "waits for #374".

## 8. Open for the owner

- **O1, the tail of a session that already has a digest.** A session whose Stop digest came early and whose later work had none keeps losing that later work. Recommended: leave it out of R1 (a session with any digest is never backfilled), and let #440 (M2), which reuses this step for partial sessions, decide it with R0's numbers. The alternative trims the excerpt to entries after `last_digest_at` and writes a second digest for such a session.
- **O2, Corrections in a backfilled digest.** A Correction becomes a preference note at ingest (`ingest.md` step 9). Recommended: no Corrections section in R1, so no preference is learned from a headless reading of a transcript whose assistant turns may quote untrusted text. The alternative keeps the section, limited to the owner's own words from user turns, and adds a tick check that each statement appears verbatim in a user turn of the excerpt.

- **O3, a terminal that closes without `SessionEnd`.** Nothing in the repository shows whether Claude Code fires `SessionEnd` when the terminal is killed (a dropped SSH session, SIGHUP) or the process crashes. R1's marker and the transcript copy both hang on that hook. The plan's first probe tests it. Recommended, if it does not fire: a tick-side sweep that queues a session whose state is older than a day, has no digest and no marker, and passes §4.1's work test; `mem_freeze` records `transcript_path` in the state (`lib_memory.sh:94-97`) so the tick can copy the transcript itself. The alternative drops the terminal-close case from R1's scope and says so in FOUNDRY.md.

## 9. Left to the builder

How `build` returns its counts; where `_append_jsonl` moves; the `recall_log.py` shape (a separate wrapper is the default; an early dispatch in `vault_index.py` before scope resolution is fine if it measures the same); how a tool call renders in the excerpt; the JSONL line limit; whether a `PostToolUseFailure` matcher is added after the probe; test names within the files listed in §7.
