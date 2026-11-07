# Factory F7, PR 1: the Now line's state machine (#478)

**Grill:** 2026-11-03, https://github.com/kferran/Foundry/issues/478 (round 1 on #477 covers F6 and F7; the implementation choice, a plain transition table in `vaultlib` with no library, is on #478).
**Builder check:** 2026-11-03, from a read-only inventory of master (19 transitions, file:line in §3). Five findings change the issue's sketch:
- **The brief can tick or drop a line unchecked.** The headless brief's staged page can change the mark of any existing line, and the publish gate screens only the open lines the run added (`publish.py:384-393`). That makes it a transition outside every guard, and the only one a model makes.
- **Reopening an expired line does not stick.** An owner who reopens a `[-] … expired` machine line has it expire again at the next check: `stamp()` strips the stamp (`now.py:142-143`), and the line is still `[via:: mail|chat|watch]`, older than 7 days and without notes (`now.py:618-630`).
- **Unknown marks such as `[/]` are in no state at all.** They are neither open nor closed, are never archived, make the merge driver raise (`now.py:164, 222`), and make `held.step` re-add the held line (`held.py:47, 61-63`).
- **Two RCA writers write the line text themselves.** `rca.filed` and `rca.reopen` (`rca.py:167-204`) build line text and stamps outside `add`, `set` and `stamp`, and `reopen` unticks any mark, an open line included.
- **Core has 29 lines of headroom** (16,451 of 16,480). The table module needs a measured raise, which the owner approves at merge.

**Blueprint:** none: a module and guards in existing writers.

## 1. Why

The Now page is the open-loop list the goal sentence rests on. It has the most writers of any file and the most repeat defects: the C2 Now-line class came back three times after its gate, and there are 21 fix commits on `now.py` and `vaultlib/now.py` since 2026-10-09. Each writer applies its own rules for which change is allowed. There are 19 transitions (§3) across `now.py`, `held.py`, `rca.py`, the brief, triage, the watch, Work Orders, the merge driver and hand edits, and no file lists them.

## 2. Goals

1. One table, `vaultlib/now_states.py`, lists the states and the allowed transitions, each with the writers that may make it.
2. Every code writer that changes a line's mark or stamp does it through `transition()`, which refuses a change the table does not allow, logs the refusal to `system/logs/now-<YYYY-MM>.jsonl`, and leaves the line unchanged. The code writers are `check`, the stamp, `rca.filed`, `rca.reopen` and the brief's publish.
3. The publish gate refuses a brief run whose staged Now page changes the mark of a line that existed before the run. The brief may add open lines and nothing else (closes the first builder-check finding).
4. An owner reopening an expired machine line keeps it open. When `stamp()` strips an `expired` stamp from an open line, it also drops `[via::]`, so the line becomes the owner's and no longer expires (closes the second finding).
5. `now.py review` lists a line with an unknown mark as unreadable, with the fix "tick, drop or reopen it by hand" (closes the third finding for the owner's view). `held._mark` treats an unknown mark as open, so it no longer re-adds the held line.
6. Tests walk every (state, state) pair for each writer and assert that only the table's pairs change the line.

**Non-goals** (each needs the owner's call, §6):
- Changing the stamp wording for a dropped line (`ticked` today).
- Closing failed or cancelled Work Orders and closed-unmerged PRs as `[-]` (`[x]` today).
- Keeping a second identical close in a month in the archive.
- Inputs and Work Orders (F7 PRs 2 and 3, Q8 on #477).

**Anti-goals:**
- Blocking the owner's hand edits. Obsidian writes the file directly and the table cannot see it; the table governs code.
- Any change to the line format or the merge driver's ranking.
- A refusal that raises and fails a unit. Refusals log and leave the line as it was.

## 3. The states and transitions

The states:
- `open` (`- [ ] `, parsed or not);
- `done` (`[x]` or `[X]`) and `dropped` (`[-]`), each either unstamped or `stamped`;
- `archived` (moved to `now-archive/`);
- `unknown` (any other mark).

| # | From | To | Writers | Source |
|---|---|---|---|---|
| T1–T4 | none | open | add (session, triage, watch, Work Order, held, `/rca --file`), seed, brief | `now.py:434-476, 794-812`; brief via publish |
| T2, T5, T6, T12 | open | open | add again, set, note, tag-writers | `now.py:450-471, 530-554, 307-323, 659-684` |
| T7 | open | done, stamped by evidence | check | `now.py:633-653` |
| T8 | open (machine) | dropped, stamped `expired` | check | `now.py:618-630, 649-650` |
| T9 | done or dropped, unstamped | stamped `ticked` | stamp, on the next write | `now.py:137-147` |
| T10 | open with an old stamp | open (stamp removed; Goal 4: an expired one also drops `via`) | stamp | `now.py:142-143` |
| T11 | stamped | archived | archive | `now.py:275-304` |
| T13 | two versions | merged (`[x]` > `[-]` > open) | merge driver | `now.py:232-262` |
| T14 | done RCA line | done, stamped `filed <KEY>` | `rca.filed` | `rca.py:193-204` |
| T15 | done or dropped RCA line | open, "not filed" | `rca.reopen` (no longer from open: refused) | `rca.py:167-190` |
| T16–T18 | held line | (file moves; the line stays) | `held.step` | `held.py:50-69` |
| T19 | any | any | the owner by hand | not governed |

The brief has T1 only: its publish refuses any other change (Goal 3). The merge driver keeps its own ranking. Its result is checked against the table in tests only, since it runs inside git.

## 4. Design

- **`vaultlib/now_states.py`** (about 50 lines):
  - `STATE` gives a line's state from its mark and stamp.
  - `ALLOWED` is a dict from `(writer, from)` to the set of allowed `to` states.
  - `transition(line, writer, to, how=None, day=None)` returns the new line, or `None` and a log line.
- **`now.py` and `rca.py`:** the stamp, check, `rca.filed` and `rca.reopen` call `transition()` instead of building marks and stamps.
- **`publish.py`:** for a brief run, the existing Now screen (`:380-393`) also compares each old line's state with its state in the staged page. A change is a problem, `now: the brief changed <statement>: <from> to <to>`, and the publish is rejected like any other screen failure. The brief retries once (`brief_run.sh`).

## 5. Done when

- The table is the only place a mark or stamp is built in code. A test greps that no other module writes `- [x]`, `- [-]` or `_(closed:` outside fixtures and the table.
- The pair-walk tests pass for every writer.
- A brief fixture that ticks an existing line is rejected.
- An expired line reopened by hand stays open through two checks.
- `review` lists a `[/]` line.
- The core cap is raised by the measured lines, with a comment naming this spec. The owner approves the raise at merge.

## 6. Open questions for the owner (not blocking PR 1)

- **O1:** should a dropped line be stamped `dropped <date>` (`ticked` today)? The health scorecard's dismissed share reads the mark, not the word, so the change looks safe, but that is not verified.
- **O2:** should a failed or cancelled Work Order, or a PR closed without merge, close as `[-]` (`[x]` today, `now.py:648`)? Today a Work Order that failed reads the same as one that succeeded.
- **O3:** should archive keep a second identical close in the same month (`now.py:295-296` drops it with its notes)?
