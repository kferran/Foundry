# Work Order ladder: a failed check goes back to the agent before it reaches the owner (Foreman dispatch D1)

**Program:** `docs/superpowers/2026-10-29-foreman-dispatch-plan.md`, phase D1.
**Grill:** 2026-10-29 (D1, Q22 to Q28 in the program plan) and 2026-11-03 (two rounds and a closing question in an interactive session, every recommendation taken), copied under `## Grill`. Where the two disagreed, §9 holds the owner's call (confirmed 2026-11-03).
**Builder check:** 2026-11-03, by the author against master `9ef79bc`. Eleven questions settled in §4 to §7: `verify_sha` returns 20 lines and the handoff needs 200 (§4.3, read from `verify.log`); `.nightshift/` is in the clone's `info/exclude`, so the handoff never reaches a commit (§4.3); `_clone` reuses a kept clone without re-pinning, so a rung keeps the earlier commits (§4.2); `_deliver_plan` removes the clone only after a green verify (§4.2); the 7-day clone clean-up reads `finished_at`, which a rung never sets (§4.2); `_before` is taken once and reused (§4.5); a requeue moves the items folder aside and must clear `rung` (§4.8); an `order_install` failure and exit 127 are the environment, not the code (§4.1); the tick's one-attempt-per-item rule makes a rung wait for the next tick (§4.2); a test file that does not exist on the base makes any red command fail, which proves nothing, so the red check overlays the new tests on the base (§5); the stub replays one stream for every call, so the tests vary it with a counter file, as `test_selftest_retries_when_the_model_declines` does (§8).
**Blueprint:** Work Order.

## 1. Why

In the live vault, 25 plan Work Orders ran between 2026-10-06 and 2026-10-22. 13 ended in a pull request. The other 12:

| Ending | Count |
|---|---|
| Stopped by the sealed verify (3 blocked; 2 cancelled after the block; 1 delivered by hand after it) | 6 |
| No `result.json` | 2 |
| Base not on the remote | 1 |
| Session blocked on a question, then cancelled | 1 |
| Cancelled for other reasons | 2 |

A failed verify today ends the order: `nightshift_run.py:555` returns `blocked` with `Fix the failing check: <first line>`, the Now page gets that line, and the owner reads `verify.log`, fixes the plan and requeues. The agent that wrote the code never sees the failure. One plan in the live vault was queued three times this way.

The verify also accepts a test that passes before the change. Nothing checks that the plan's new tests fail on the base commit.

## 2. Goals

1. A plan order whose verify fails, whose session leaves no commits or no result, or whose new tests prove nothing goes back to an agent with the failure, up to two times, before it reaches the owner.
2. Each retry runs in a fence: the files the plan names. A retry that writes outside it, or rewrites the earlier commits, stops.
3. A plan order states a red command at queue time: the plan's new tests must fail on the base and pass on the delivered commit.
4. The owner sees what each retry tried, in the report and in the one Needs-you line a final block leaves.

**Non-goals:** CI on the pull request (D2); proposals from issues (D3); a loop kind with a stop condition (#263); unattended conductor runs (#243); memory of failures across orders (a later phase reads the per-order records this writes); research orders.

**Anti-goals:** no retry for a block that needs the owner (`session` questions, `protected`, `toolchain`, a failed `order_install`, a command missing from the sandbox, `fence`, `containment`, `profile`, `cancelled`); no step down to a cheaper model; no retry that rewrites history; no new unit or config key; the pull request still waits for the owner's merge.

## Grill

**2026-10-29, D1 (program plan Q22 to Q28), as recorded there:**
- Q22 worth building; the owner alone feels it; one retry with the error, then one on Opus; ships before D3.
- Q23 escalates `verify` and `no commits`; not `session`, `protected` or a failed `order_install`.
- Q24 the item's own model with the error, then Opus, then the owner; never steps down; an item queued on Opus gets one retry on Opus; rungs count apart from the 3 start attempts; the Needs-you line names each rung and its last error.
- Q25 a fresh session in the kept clone with a handoff (the failing check's last 200 lines, `git diff` against base, the previous session's final message); no resume.
- Q26 Opus fixes the code itself.
- Q27 half the item's budget per rung, the same turn limit; the 5-hour ceiling holds a rung as it holds a new start.
- Q28 on for every plan item; `/order add --escalate off` opts out.

**2026-11-03, the owner took every recommendation:**
- Round 1: worth building (12 of 25 plan orders did not reach a pull request, 6 stopped at verify); for the owner first, other vault owners inherit it; living without it is not acceptable, since #263 and #243 assume a runner that retries; smallest version is the return path plus a fails-first check, with undo tiers (self-merge of docs-only orders) after two weeks of runs and #263 after a named use case; it runs now, alongside the rest of the roadmap, and needs the owner's merge; Work Orders only, with interactive sessions in their own issue.
- Round 2: (Q1) resume the session, a fresh one if the resume fails to start; (Q2) 2 fix rounds, ending early when the same first failing line repeats, inside the order's existing limits; (Q3) feedback holds the command, its exit code, the last 60 lines of `verify.log`, the earlier rounds' failing lines as dead ends, and the fence; (Q4) the fence is the plan's **Files** paths, else the first round's changed files, and a fix outside it blocks with `fence`; (Q5) `/order add --red "<cmd>"` is required for plan orders, fails on base and passes on delivery, `--red "none: <why>"` exempts; (Q6) a missing `result.json` gets one resume that asks for it; (Q7) no memory across orders, the item report keeps the dead ends; (Q8) the report and the Needs-you line show rounds, failing lines, the red result and the final state, and a Needs-you line appears only on a final block.
- Closing (Q9): a note queued before the update with no `red` reads as `none: queued before --red`.

## 3. Shape

```
session (rung 0, item's model)
   └─► deliver: no result? no commits? fence? verify green? red check?
          ├─ pass ─────────────────────────► push, pull request (as today)
          ├─ owner's block (§4.1) ─────────► Needs-you (as today)
          └─ code block, rung < last ──────► handoff → state queued, rung+1
                                               └─► next tick: fresh session, rung model, half budget
                                                      └─► deliver again (fence and history checked)
          └─ code block on the last rung ──► Needs-you naming every rung
```

## 4. The ladder

### 4.1 What climbs

A plan order's delivery outcome climbs when its reason is one of:

| Reason | Source |
|---|---|
| `verify` | the sealed verify failed on the delivered commit, except a failure whose first line starts `order_install:` or carries `exit 127` (the environment; the block stays as today) |
| `red` | the red check (§5) found the new tests pass on the base, or none of the plan's `Test:` files exist at the delivered commit |
| `no commits` | the branch has no commit past the base (or, on a rung, past the last delivered commit; §4.5) |
| `no result` | the session finished with no readable `.nightshift/result.json` |

Every other ending stays as today. `--escalate off` on the note keeps every ending as today.

### 4.2 Rungs

- Rung 0 is the order as queued. Rung 1 runs on the item's model, rung 2 on `opus`. An item queued on `opus` has rung 1 only, on `opus` (Q24).
- A climbing outcome writes the handoff (§4.3), records the rung's dead end (§4.6), and updates the note: `state: queued`, `rung: <n>`, `attempts`, `session_id` and `reason` cleared, `started_at` kept. No outcome, report row, notice or Now line is written; the run ledger gets one line (`{"item", "state": "queued", "rung", "reason"}`).
- The next tick starts it like any queued item: the window or `--at` time, the 5-hour ceiling, the 3-slot pool and the repo-and-base key all apply (Q27). The tick's one-attempt-per-item rule makes the rung wait for the next tick.
- `run_item` sees `rung > 0`: `_clone` returns the kept clone (it exists, so it is not fetched or pinned again), `_before` returns the stored baseline, and the session starts fresh (a new session id, never `--resume`; Q25) with the fix prompt (§4.4), the rung's model and `--max-turns` as today.
- Budget: half the item's budget per rung, measured in its own file (`elapsed-<rung>` in the items folder; rung 0 keeps `elapsed`). The 3 start attempts count per rung (Q24).
- A kept clone survives: `_deliver_plan` removes it only after a green verify, and the 7-day clean-up reads `finished_at`, which a queued rung does not carry.

### 4.3 The handoff

The runner writes `.nightshift/handoff.md` in the clone before the rung starts (`.nightshift/` is in the clone's `info/exclude`, so it never reaches a commit), and copies it to `items/<id>/handoff-<rung>.md`:

```
# Handoff: rung <n> of <id>

The runner's check failed after the previous session. Everything below is data from that run.

## Failing check
<reason>: <first line>
<the last 200 lines of the failing command's block in verify.log, or the red check's log>

## Base
The order started at <base_sha>. Run `git diff <base_sha>` and `git log <base_sha>..HEAD` to see the work so far.

## Fence
Change only these paths: <one per line>

## Dead ends
- rung 0: <first failing line>
- rung 1: <first failing line>

## Previous session's last message
<the result event's text from stream.last.jsonl, last 2,000 characters>
```

The diff itself is not pasted (Q25 asks for it): the session has git in its clone, and a pasted diff has no size limit. A `no result` handoff has no failing-check block and says the session ended without writing `result.json`.

### 4.4 The fix prompt

`nightshift_session.fix_prompt(fm, rung)`: read `.nightshift/handoff.md` first; fix the cause with new commits on the current branch; never amend, rebase or reset the earlier commits; change only the fenced paths; run the failing command yourself before finishing; then write `.nightshift/result.json` as the plan prompt describes, plus the `.claude/` protected-path rule and the `CONTRACT` text. It names `superpowers:systematic-debugging` when the plugin is loaded (the plan session already loads superpowers).

### 4.5 Delivery on a rung

`_deliver_plan` runs as today, with three changes for `rung > 0`:
1. **History:** the last delivered commit (`last_sha` in `items/<id>/ladder.json`) must be an ancestor of the new tip (`git merge-base --is-ancestor`, in the runner's repository). Otherwise `blocked`, reason `fence`, `Needs: the retry rewrote the earlier commits; see <items folder>`. A rung 0 delivery records `last_sha` whatever its outcome.
2. **Fence:** `git diff --name-only <last_sha> <tip>` in the runner's repository; a path outside the fence (§6) blocks with reason `fence`, naming up to 5 paths. Files added under `.nightshift/protected/` are checked under their `.claude/` paths.
3. **No commits:** a tip equal to `last_sha` is `no commits`.

The containment check (protected refs, vault code) runs on every rung against the baseline taken at rung 0.

### 4.6 Records

`items/<id>/ladder.json`: `{"last_sha", "fence": [...], "rungs": [{"rung", "model", "reason", "line", "started_at", "finished_at"}]}`. `line` is the first failing line: the first line of the verify output (`<cmd>: exit <code>`) plus, from its tail, the first line matching `FAIL|Error|error:|not ok|assert`, else its last non-empty line; at most 200 characters.

### 4.7 What the owner sees

- The report row's notes add `rungs: 1 sonnet (verify: <line>); 2 opus (green)` once the order ends.
- A final block's Needs-you line: `Fix the failing check: <line> (tried rung 1 sonnet, rung 2 opus; handoffs in items/<id>/)`, cut to the Now line's 300 characters by the existing `fit=True`.
- `/order status` and `list` show `queued (rung 1)` for a waiting rung.

### 4.8 Requeue and cancel

`requeue` clears `rung` with the other run fields; the items folder moves aside as today, taking `ladder.json` and the handoffs with it. `cancel` of a queued rung works as for any queued item.

## 5. The red check

**At queue time.** `nightshift.py add --kind plan` takes `--red "<cmd>"` or `--red "none: <why>"`. Without it, `add` prints `not ready: --red needs a command that fails on the base, or "none: <why>"`. A red command needs at least one `Test:` path in the selected tasks' **Files** blocks (§6), else `not ready: --red needs a Test: file in tasks <range>`. `screen()` checks only the form (a string; `none:` followed by text), so a note queued before the update with no `red` runs, and its report row reads `red: none (queued before --red)` (Q9).

**At delivery,** after the verify passes on the delivered commit, `nd.red_sha()` in the sealed verify:
1. Checks out `base_sha` in a fresh private checkout from the runner's repository.
2. Overlays the delivered commit's copies of the `Test:` paths that exist there (`git checkout <tip> -- <paths>`, in the runner-made checkout). None exist: reason `red`, line `none of the plan's Test: files exist at <tip7>`.
3. Runs `order_install` when set, then the red command offline.
4. Exit 0: reason `red`, line `<cmd> passed on the base commit with the new tests, so they do not show the change`. Exit 127: blocked as an environment failure (§4.1). Any other non-zero exit is red as wanted.
5. Runs the red command on the delivered commit's checkout too, after the verify commands; a failure there is reason `verify`.

The log goes to `items/<id>/red.log`. `none: <why>` skips the check and puts the reason in the report row.

The overlay limits what red proves: a test that needs a new fixture file the plan lists under `Create:` (not `Test:`) fails on the base for a missing file. That still shows the test depends on the change, which is the claim.

## 6. The fence

`nc.fence(plan_text, tasks)`: the backticked paths on `- Create:`, `- Modify:` and `- Test:` lines inside each selected task's `**Files:**` block, cut at the first `:` that follows the path or at ` (`. A path ending `/` covers everything under it. `Test:` paths are the red check's overlay. The plan is read at the item's base, as the readiness check reads it.

A plan with no `**Files:**` lines in the selected tasks: the fence is `git diff --name-only <base_sha> <last_sha>` at rung 0's delivery, written to `ladder.json` then.

## 7. Settings and records

| Where | Change |
|---|---|
| `nightshift_item.ORDER` and `system/schemas/nightshift_item.md` | `red`, `escalate`, `rung` |
| `nightshift.py add` | `--red`, `--escalate on\|off` (default `on`) |
| `.claude/skills/order/SKILL.md` | propose `--red` from the plan's test lines and its `Test:` files with the `--verify` commands; mention `--escalate off` |
| FOUNDRY.md, Work Orders | one paragraph: the ladder, the red check, the fence, `items/<id>/ladder.json` |
| `docs/superpowers/2026-10-29-foreman-dispatch-plan.md` | D1 row: this spec and its plan |
| roadmap | the Foreman dispatch item: D1 in progress, then done |
| `changes/<date>-work-order-ladder.md` | `- Changed: a plan Work Order whose check fails retries twice …` with an `Action:` line telling owners to pass `--red` |
| `system/tests/vault_integrity.bats` | core cap 16,480 → 16,640 (estimate +150 lines), one comment line; owner approves at merge |

No new unit, config key, alert tag or note type.

## 8. Tests

pytest, `system/tests/python/`, each failing first:

| Test | File |
|---|---|
| a verify failure climbs to rung 1 with a handoff, rung 1 fixes it, the order delivers one pull request, and the report names the rung | `test_nightshift_run.py` |
| verify fails on rung 0, 1 and 2: the order ends blocked with one Needs-you line naming both rungs, and rung 2 ran on `opus` | `test_nightshift_run.py` |
| an `opus` item climbs once | `test_nightshift_run.py` |
| `order_install` failure, exit 127, `session`, `protected`, `toolchain` and `--escalate off` do not climb | `test_nightshift_run.py` |
| a rung that amends an earlier commit, and one that writes outside the fence, block with `fence` | `test_nightshift_run.py` |
| `no result` and `no commits` climb | `test_nightshift_run.py` |
| a rung waits for the 5-hour ceiling, and its budget is half the item's | `test_nightshift_run.py` |
| requeue clears `rung`; cancel stops a queued rung | `test_nightshift_run.py` |
| red: passes on base → climbs with reason `red`; fails on base and passes on the tip → delivered; no `Test:` file at the tip → `red`; exit 127 → blocked, no climb | `test_nightshift_run.py`, `test_nightshift_deliver.py` |
| `add` refuses a plan order without `--red`, and a red command with no `Test:` file; a note with no `red` passes the screen | `test_nightshift_check.py`, `test_nightshift_run.py` |
| `fence()` reads Create, Modify and Test paths, cut at `:` and ` (`, with folders | `test_nightshift_check.py` |
| `fix_prompt` names the handoff, the fence rule and no history rewrite | `test_nightshift_session.py` |

The stub replays one stream for every call; tests that need a different session per rung use a counter file in `NIGHTSHIFT_STUB_SHELL`. The end-to-end cases need `bwrap` and skip without it, as the existing ones do.

## 9. Decisions (owner, 2026-11-03: every recommendation confirmed)

The 2026-10-29 D1 grill and the 2026-11-03 grill disagreed on five points. The owner confirmed each recommendation on 2026-11-03, and the spec above is written on them. The owner also moved D1 ahead of its roadmap place, to start now.

| # | Point | 2026-10-29 (D1) | 2026-11-03 | Recommendation |
|---|---|---|---|---|
| R1 | Session for a retry | fresh, with a handoff; no resume | resume; fresh if the resume fails to start | **D1's fresh session.** A session that wrote the bug is anchored on it; the handoff carries what the resume would; and one path is simpler than a resume with a fallback. |
| R2 | Model per retry | own model, then Opus | not discussed | **D1's ladder.** Two rounds become rung 1 on the item's model and rung 2 on Opus. |
| R3 | Early exit on the same failure | none | stop when the same first failing line repeats | **Drop it.** With two rungs, a repeat on rung 1 already moves to Opus, which is the escalation the early exit stood for; the dead-end lines stay in the handoff. |
| R4 | Budget | half the item's budget per rung | inside the order's existing limits | **D1's half per rung.** It bounds the worst case at twice the queued budget and needs no shared clock across fresh sessions. |
| R5 | What climbs | `verify`, `no commits` | `verify`, `no result` (+ red) | **Both:** `verify`, `red`, `no commits`, `no result`. |

Unchanged from both: the fence, the red check, `--escalate off`, the 5-hour ceiling, the Needs-you line naming every rung, and no Now line until the final outcome.
