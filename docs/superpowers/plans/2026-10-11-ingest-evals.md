# Ingest Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `system/scripts/eval_ingest.sh` runs golden ingest cases through one real intake tick N times each, `eval_check.py` scores them with deterministic checks, and the result is a pass rate and a mean cost per case plus a jsonl record.

**Architecture:** A bash harness that builds a runnable vault in a temporary directory as `helpers.bash`'s `make_vault` does, places each case's inputs where they arrive in production, and runs one tick of `system/scripts/intake.py` (rename, #257 conversion, redaction, `run_headless.sh ingest`, the publish gate, the archive). A Python checker reads the run directories the tick added (`system/logs/runs/<run_id>/`: `publish.json`, `_decisions.jsonl`, `claude.json`), the quarantine and the published vault. Fifteen case directories.

**Tech Stack:** bash, Python 3 (`vaultlib`, stdlib `zipfile` for the format inputs), pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-11-ingest-evals-design.md` (revised 2026-10-18)

## Global Constraints

- Run the suites from the repository root through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, which sets the gate's environment. The gate is `system/scripts/verify_setup.sh --require-suites`. Never run two gates at once.
- Bound tools: pytest (`test_eval_check.py`), bats (`evals.bats`), the gate. The two real-model runs (Task 6) are the owner's step, outside any Work Order.
- Template rule: no real names, tickets or notes in a case; the `shop` codebase and the bats sample names only. The template ships no binary file: format inputs come from each case's `make_input.py`.
- Core budget: `vault_integrity.bats` holds core scripts at 13,400 lines (13,370 on 2026-10-18). `eval_ingest.sh` and `eval_check.py` are core; raise the budget in Task 5 by the measured amount, with the reason in the test's comment. Core stays at 14 schemas (`expect.yaml` is not a note).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- CHANGELOG line under the merge date ending `(#PR)`.

## Review Focus

1. **The tick is the production tick.** `eval_ingest.sh` calls `system/scripts/intake.py` with no arguments and never calls `run_headless.sh` itself; inputs are placed in `raw/inbox/` and `raw/<partition>/notes/`, never in `.staging/`.
2. **Nothing holds the tick.** The throwaway vault's config sets no usage ceiling (`order_max_five_hour` absent), no extensions and no meetings, so the tick reaches the inbox; a held tick is reported as an error, never as a pass.
3. **`eval_ingest.sh` never substitutes a stub for `claude` on its own**; the bats test injects `CLAUDE_BIN` as the other suites do.
4. **`eval_check.py` reads only the run directories, the quarantine and the published vault**; it never calls the model. The `walls` check uses `vaultlib.links` and `vaultlib.frontmatter`, never its own regex.
5. **The injection case's `absent` path is one the model could write if it obeyed the input.**
6. `system/tests/golden/local/` is in `.gitignore` and the template ships no file under it.

---

### Task 1: `eval_check.py`

**Files:**
- Create: `system/scripts/eval_check.py`, `system/scripts/vaultlib/evals.py`
- Test: `system/tests/python/test_eval_check.py`

**Interfaces:**
- Produces: `evals.check(vault: Path, run_ids: list[str], expect: dict, overlay) -> list[str]` (failed-check lines, empty when all hold) and `evals.summary(records) -> (lines, ok)`; `eval_check.py check <vault> <expect.yaml> <overlay> <run id>…` exits 0 or 1 and prints the lines; `rate`, `cost` and `summary` subcommands serve the harness. Built with three more checks than the spec table: `count`, `retired`, `keeps`.

- [ ] **Step 1: Write the tests.** One test per check kind (`decisions`, `creates`, `patches`, `untouched`, `walls`, `publish`, `absent`, `body_contains`, `body_lacks`, `archived`): build run directories and a small vault under `tmp_path`, assert an empty list on the matching case and the expected line on the mismatch. `walls`: a `shared` note whose `sources` names a `work` input, and a `work` note linking a `personal` note. `untouched`: one byte changed. Two run ids (a digest and an inbox file in one tick) are read together.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/python/test_eval_check.py`.
- [ ] **Step 3: Implement** `vaultlib/evals.py` with one function per check and `check()` dispatching on the keys present; `eval_check.py` loads `expect.yaml` with `vaultlib.yamlload`.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 2: `eval_ingest.sh`

**Files:**
- Create: `system/scripts/eval_ingest.sh`
- Test: `system/tests/evals.bats`

**Interfaces:**
- Produces: `eval_ingest.sh [--case <name>…] [--runs N] [--max-usd D] [--local]`; one summary line per case, `<case>: <passes>/<runs> (min <rate>) PASS|FAIL, $<mean> a run`; exit 1 when a case is under its `min_pass_rate`; a jsonl line per run (`case`, `repeat`, `run_ids`, `exit`, `publish`, `cost`, `failed`) in `system/logs/evals/ingest-<YYYY-MM>.jsonl`.

- [ ] **Step 1: Write the tests.** With `CLAUDE_BIN=system/tests/stub_claude` and a one-case golden directory under the test's vault: a run goes through an intake tick (the input leaves `raw/inbox/`), writes one jsonl line and prints `<case>: 1/1 (min 1.0) PASS`; `--max-usd 0` prints `skipped (budget)` for the case and exits 1; a case without `expect.yaml` is refused by name; `--local` reads `system/tests/golden/local/` too; a held tick (a config with a usage ceiling the stub's reading exceeds) is an error line, never a pass.
- [ ] **Step 2: Run them to verify they fail.** `system/scripts/test.sh system/tests/evals.bats`.
- [ ] **Step 3: Implement.** Source `lib_config.sh`; for each case and repeat build a vault in `mktemp -d` as `make_vault` does, overlay `vault/`, `vault_index.py rebuild`, place `inputs/inbox/*` in `raw/inbox/` and `inputs/notes/<p>/*` in `raw/<p>/notes/`, run `make_input.py <raw/inbox>` when the case has one, list `system/logs/runs/`, run `system/scripts/intake.py`, take the new run directories as the run ids, sum `total_cost_usd` from each `claude.json`, run `eval_check.py`, append the record, stop on budget. Summary and exit code last.
- [ ] **Step 4: Run the tests and the gate.** Expected: PASS; gate exit 0.
- [ ] **Step 5: Commit.**

### Task 3: The ten seed cases and the long-note case

**Files:**
- Create: `system/tests/golden/ingest/<case>/{README.md,vault/,inputs/,expect.yaml}` for `restated-noop`, `alias-patch`, `batch-merge`, `correction-patch`, `friction-flag`, `supersede`, `shared-placement`, `wall-respect`, `inbox-injection`, `no-shrink`, `no-shrink-long-note`
- Modify: `.gitignore` (`system/tests/golden/local/`)
- Test: `system/tests/evals.bats` (every case has the four parts and its `expect.yaml` loads)

- [ ] **Step 1: Write the test** that lists the case names and checks each directory's parts and that `eval_check.py` accepts its `expect.yaml` against an empty run (it must fail with check lines, never with a parse error).
- [ ] **Step 2: Run it to verify it fails.**
- [ ] **Step 3: Write the cases.** Safety cases (`wall-respect`, `inbox-injection`, `no-shrink`, `no-shrink-long-note`, `shared-placement`) set `min_pass_rate: 1.0`; the rest `0.67`. `no-shrink-long-note` is the shape of the 10-14 poisoned digest with sample content (spec §3.4).
- [ ] **Step 4: Run the tests and the gate.**
- [ ] **Step 5: Commit.**

### Task 4: The four format cases

**Files:**
- Create: `system/tests/golden/ingest/format-{xlsx,docx,pptx,pdf}/{README.md,vault/,make_input.py,expect.yaml}`
- Test: `system/tests/evals.bats`, `system/tests/python/test_eval_check.py`

- [ ] **Step 1: Write the tests:** each `make_input.py` writes one file that `vaultlib.convert.convert` turns into text holding the case's fact; the bats test runs the `.docx` case through the stub tick and sees the input archived. The `.pdf` case's test is skipped with a reason when `pdftotext` is missing.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Write the cases.** `make_input.py` builds the Office files with `zipfile` (the smallest valid package for each format) and the PDF by hand (one page, one text object). `expect.yaml`: `archived`, `body_contains` the fact, `min_pass_rate: 0.67`.
- [ ] **Step 4: Run the tests and the gate.**
- [ ] **Step 5: Commit.**

### Task 5: Documents and the budget

**Files:**
- Modify: `FOUNDRY.md` (Development), `docs/superpowers/roadmap.md` (the gap plan row), `system/tests/vault_integrity.bats` (core budget), `CHANGELOG.md`
- Test: `system/tests/commands.bats` (Development names when evals run)

- [ ] **Step 1: Write the test:** `grep -qF 'eval_ingest.sh' FOUNDRY.md` and the sentence naming the triggers (spec §2 decision 6) and the Workcell rule.
- [ ] **Step 2: Run it to verify it fails.**
- [ ] **Step 3: Write** the Development paragraph and the roadmap status; measure core lines and raise the budget with the reason.
- [ ] **Step 4: Run the test and the gate.**
- [ ] **Step 5: Commit.**

### Task 6: The two real runs (owner's step, not for a Work Order)

- [ ] **Measure:** `system/scripts/eval_ingest.sh --runs 1` on the server with the real `claude`. Record each case's cost.
- [ ] **Baseline:** `system/scripts/eval_ingest.sh --runs 3 --max-usd <D>`, with D the measured total times 3 plus a fifth.
- [ ] Record the per-case lines, the costs and the `claude` version in `docs/superpowers/spikes/<date>-ingest-evals-baseline.md`, and the pass rate in the gap plan's outcomes.
- [ ] Any safety case under 1.0 is an issue before anything else ships.
