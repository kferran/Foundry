# Work Order confinement, PR B (the CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A research order and a requeue each take a prompt; only the CLI writes queue notes, codebase notes and session profiles; a plan runs on the commit its owner queued.

**Architecture:** `nightshift.py` gains `research` and `requeue` subcommands; `add` keeps plan orders only. `add` records `base_sha`; the first clone checks it. `requeue` starts a blocked or failed order fresh. The settings lines (ask rules, write denies, excluded commands) are listed for the owner, who adds them in the PR (spec §3.1, §3.1a).

**Tech Stack:** Python (`system/scripts/vaultlib/nightshift_run.py`), Markdown skill and manual, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-30-work-order-confinement-design.md` §3.1, §3.1a, §3.5, §3.6 and §6 item 2 (approved by the owner's merge of #427, 2026-10-30). Probes: `docs/superpowers/spikes/2026-10-31-excluded-command-and-deny-write-probe.md`.

## Global Constraints

- The Work Order runner and `.claude/settings.json` are safety surfaces: the owner merges the PR.
- The settings lines are not committed by the build; the PR body lists them exactly (spec §3.1, §3.1a; grill round 2 Q2).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Run only the changed files' suites locally (`system/scripts/test.sh <paths>`); CI is the gate.
- Template rule: no hostname, user path, remote URL, distro, account ID, or employer, client, codebase or people names in any committed file.
- An order queued before this change has no `base_sha` and runs as today (spec §3.5).

## The settings lines for the owner (from the probes)

`permissions.ask`:
`Bash(system/scripts/nightshift.py research:*)`, `Bash(system/scripts/nightshift.py requeue:*)`,
`Edit(/raw/*/nightshift/**)`, `Write(/raw/*/nightshift/**)`, `Edit(/system/codebases/**)`, `Write(/system/codebases/**)`, `Edit(/system/nightshift/**)`, `Write(/system/nightshift/**)`.

`sandbox.filesystem.denyWrite` (literal folders, project-relative; a glob or a leading `/` denies nothing, probe 2026-10-31):
`raw/work/nightshift`, `raw/personal/nightshift`, `raw/shared/nightshift`, `system/codebases`, `system/nightshift`.

`sandbox.excludedCommands` (the `<command> *` form; a bare path matches only the command with no arguments):
`system/scripts/nightshift.py *` (every subcommand, each still under its allow or ask rule), `system/scripts/vault_sync.sh` (its pull writes a client's queue notes; the allow rule is the no-argument form).

Interactive writers of the three paths, and how each still works:
- `/order` → `nightshift.py add`, `research` and `cancel`: excluded, under their allow and ask rules.
- `/setup` registering a codebase → the Write tool: the new ask rule prompts during `/setup`, which is interactive.
- `/backup` in `private` mode → `vault_sync.sh`: excluded.
- A `git merge` or `git pull` run by hand inside a session that touches these paths is refused by the sandbox; run it outside the session. `update_template.sh` runs from its timer outside any session.

## Rulings against the spec

- **Ruling 1, `requeue` clears more than attempts and session_id** (§3.6): it also drops `reason`, `result`, `started_at`, `finished_at` and `reset_at`, so the 7-day clean-up and the report do not treat the fresh order as finished. Cost if wrong: one field kept that should have been.
- **Ruling 2, `requeue` takes no runner lock**: it touches only blocked and failed orders, which no tick starts, like `cancel`. Cost if wrong: a tick that screens the note mid-write reads the old state once.
- **Ruling 3, the probes change two spec details**: `denyWrite` lists five literal folders (the spec's three paths, with one per partition), and `vault_sync.sh` joins `excludedCommands`, from the spec's list of interactive writers.
- **Ruling 4 (owner, 2026-10-31), §3.1a ships as ask rules only.** The final review and probe 4 showed that an excluded command runs whatever a sandboxed session wrote under its name (the script, its imports, a copy reached with `cd`). So the `denyWrite` and `excludedCommands` lines above are dropped. The ask rules (research, requeue, and Edit/Write on the three paths) go into `.claude/settings.json` in this PR. A new issue closes the Bash path in the runner. This supersedes Ruling 3.

## Review Focus

1. `nightshift.py add --kind research …` from an older `/order` skill or a hand-off message: refused with the line naming `research`, exit 2, no note.
2. An abbreviated flag (`--tit`, `--res`) to any subcommand: refused, exit 2.
3. A `template` plan order whose `template_remote` cannot be read at add: `base_sha` is not recorded and `add` refuses with the existing not-ready line (it already reads the remote).
4. `requeue` on a `running`, `queued`, `delivering`, `done` or `cancelled` order: refused, naming the state; the note, clone and items folder are untouched.
5. `requeue` twice on the same id: `items/<id>.1/` then `items/<id>.2/`.

---

### Task 1: `research` subcommand; `add` is plan-only; no abbreviations (§3.1)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_parser`, `_add`, `main`)
- Modify: `.claude/skills/order/SKILL.md` (`/order ask` runs `research`), `FOUNDRY.md` (Work Orders: `research`, its prompt)
- Test: `system/tests/python/test_nightshift_run.py`, `system/tests/python/test_nightshift_parallel.py` (their research adds), `system/tests/commands.bats` or the docs test that reads the skill

**Interfaces:**
- Produces: `nightshift.py research --title --partition [--repo] [--base] --brief-file --output --host… [--now|--at|--window] [--budget] [--model]`; `_add(ctx, a, kind)`.

- [ ] **Step 1: Write the failing tests:** `test_add_refuses_research` (`add --kind research …` → exit 2, `use nightshift.py research for a research order`, no note); `test_research_writes_the_note_add_wrote` (the note's frontmatter equals the old `add --kind research` note's for the same flags, `kind: research`); `test_abbreviated_flags_are_refused` (`add --tit x …` and `research --tit x …` → exit 2); a docs check that `.claude/skills/order/SKILL.md` names `nightshift.py research` and no `--kind research`. Switch every existing research add in the two Python suites to `research`.
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement:** a `research` subparser with the research flags; `add --kind` keeps `choices=["plan", "research"]` and `_add` refuses `research` with the message; every `add_parser` and the top parser get `allow_abbrev=False`; `main` routes `research` to `_add(ctx, a, "research")`. Update the skill and FOUNDRY.md.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(orders): a research order is its own subcommand (#317)`.

### Task 2: `base_sha` (§3.5)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_add`, `_clone`, `run_item`)
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `_base_sha(ctx, fm) -> str` (`git rev-parse <base>^{commit}` in the codebase; `git ls-remote <template_remote> refs/heads/<base>` for `template`; "" when it does not resolve); `BaseMoved(Exception)` raised by `_clone` with the Needs-you text.

- [ ] **Step 1: Write the failing tests:** `test_add_records_base_sha` (template and codebase plan orders carry the 40-hex commit of their base); `test_a_moved_base_blocks_the_order` (push a new commit to the base after add; tick → `blocked`, reason `base moved`, Needs-you line `the base feat/x moved since <id> was queued (<old7> → <new7>); read the plan at the new base, then run nightshift.py requeue <id>`, no clone left); `test_an_unmoved_base_runs` (no block); `test_a_note_without_base_sha_runs` (strip the key; the order starts); `test_a_reused_clone_is_not_checked` (move the base after the clone exists; the order carries on).
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement:** `_add` stores `base_sha` for a plan order; `_clone`, when it is about to make a new clone and the note has `base_sha`, compares `_base_sha` and raises `BaseMoved`; `run_item` turns it into `_finish(... {"state": "blocked", "reason": "base moved", "needs": [text]})`.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(orders): a plan runs on the commit queued, or blocks (#321)`.

### Task 3: `requeue` (§3.6)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_run.py` (`_parser`, `main`, the Needs-you lines at the three "queue {id} again" sites)
- Modify: `.claude/skills/order/SKILL.md` (`/order requeue <id>`), `FOUNDRY.md`
- Test: `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Consumes: `_base_sha` (Task 2), `rep.item_dir`, `rep.state_dir`.
- Produces: `nightshift.py requeue <id>` → 0 requeued, 2 refused or unknown id.

- [ ] **Step 1: Write the failing tests:** `test_requeue_a_blocked_order_records_the_new_base` (after Task 2's moved-base block, `requeue` → `queued`, new `base_sha`, then a tick runs it); `test_requeue_a_failed_order_starts_fresh` (clone and `-verify` folder removed; `items/<id>/` moved to `items/<id>.1/`; `attempts`, `session_id`, `reason`, `result`, `started_at`, `finished_at` gone); `test_requeue_twice_counts_up` (`.1` then `.2`); `test_requeue_refuses_other_states` (parametrized over queued, running, delivering, done, cancelled: exit 2, message names the state, nothing changed); `test_needs_you_lines_name_requeue` (the three former "queue <id> again" lines say `run nightshift.py requeue <id>`).
- [ ] **Step 2: Run them** → FAIL.
- [ ] **Step 3: Implement** the subparser, the handler (find the note, check the state, remove the two folders, move the items folder to the first free `.<n>`, `ni.update` with the fields of Ruling 1 set to None, `state="queued"`, `base_sha` for a plan order) and the three Needs-you texts. Update the skill and FOUNDRY.md.
- [ ] **Step 4: Run them** → PASS.
- [ ] **Step 5: Commit** `feat(orders): requeue starts a blocked or failed order fresh (#321)`.

### Task 4: Docs, change file, core cap

**Files:**
- Modify: `FOUNDRY.md:122` ("written into the folder without `/order add`" → a note you write yourself still runs; a session cannot write one without the CLI once the settings lines are in), the settings section listing the new rules
- Create: `changes/2026-10-31-work-order-confinement-b.md`
- Modify: `system/tests/vault_integrity.bats` (`CORE_CAP` and its reason line)

- [ ] **Step 1:** Edit FOUNDRY.md; write the change file.
- [ ] **Step 2:** Run `system/scripts/test.sh system/tests/vault_integrity.bats system/tests/conformance.bats system/tests/commands.bats`; raise `CORE_CAP` by the measured overrun with its reason line.
- [ ] **Step 3: Commit** `docs(orders): PR B in FOUNDRY.md, change file, core cap`.

### After the tasks

- Live acceptance in a throwaway clone under `.scratch/` with the settings lines applied to the clone's `.claude/settings.json`:
  - `nightshift.py research …` is refused in a `-p` auto-mode session (the ask rule);
  - `nightshift.py add` writes its note;
  - a sandboxed `touch raw/work/nightshift/x.md` and the same write to `system/codebases/` and `system/nightshift/` are refused.
  Delete the clone.
- Whole-branch review, then the PR ("Part of #402"; `Closes #317, closes #321`), listing the settings lines for the owner to add before merging.
