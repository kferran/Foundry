# Factory F6, PR 1: declared pipeline graph (#477) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declare every core unit's node in `system/pipeline.yml` and fail CI when a declaration disagrees with the code or a node can stop with nothing raised, outside a shrinking list of known gaps.

**Architecture:**
- `system/pipeline.yml`: data only, YAML, not indexed.
- `system/tests/pipeline_graph.py`: a checker on the standard library and PyYAML, run as `pipeline_graph.py <root> <gaps-file>`, printing one problem per line.
- `system/tests/pipeline.bats`: runs the checker on the repository and on mutated fixture copies, and holds `PIPELINE_GAPS`.

No script, unit or hook changes.

**Tech Stack:** Python 3 stdlib, PyYAML, bats.

**Spec:** `docs/superpowers/archive/specs/2026-11-03-factory-f6-pipeline-graph-design.md`

## Global Constraints

- No runtime change: nothing under `system/scripts`, `system/hooks`, `system/systemd` or `.claude/commands` is edited. Core cap and schema count unchanged.
- The checker reads files only. It never runs a script or `systemctl`.
- **Rules P1–P8 (spec §4):** each prints a stable line, `<subject>: <problem>`, that the fixture tests match exactly.
- **`PIPELINE_GAPS`:**
  - The format is `"<node> <rule> <issue>  # what is missing"`, like `TIMING_OVERRUNS`.
  - A gap that now passes prints `<node> <rule>: gap closed, delete its line`.
  - Every gap names #436 or a new issue.
- **Bats ruling R1:** no mid-test `!`, no `&&` assertion chains, and no wall-clock assertions.
- **Template rule:** no hostname, user path, employer or people name in the manifest or the fixtures.
- **Change file:** none (no vault user sees a change). The factory line paragraph in FOUNDRY.md names the manifest.
- **Delivery:** one PR, branch `feat/factory-f6`, cut from master. The owner merges it.

## Review Focus

1. Every row of `system/pipeline.yml` matches the code at the branch's base: re-read each unit, script, lock and failure path (spec §6). The spec's inventory is a starting point, not evidence.
2. P2 and P3 compare the declarations with the code. A rule that compares the manifest only with itself (P6, P7) must not be presented as proof.
3. No gap is hidden by declaring an edge the code does not have. A silent path is `none` with a `PIPELINE_GAPS` line.

## Task 1: the checker skeleton and P1 (units)

**Files:** create `system/tests/pipeline_graph.py`, `system/tests/pipeline.bats`.

- [ ] Write a failing bats test: a fixture tree with `system/systemd/foundry-a.service.in` and an empty `nodes:` prints exactly `foundry-a: no node`.
- [ ] Write a second failing test: a node naming `unit: foundry-b` with no template prints `b: no unit foundry-b`.
- [ ] Implement:
  - `load(root)`, which reads `system/pipeline.yml` with `yaml.safe_load`;
  - `units(root)`, the `foundry-*.service.in` names;
  - `p1()`;
  - `main()`, which prints the sorted problems and exits 0 (the bats test asserts on the output, as `timing_problems` does).
- [ ] Run `bats system/tests/pipeline.bats`. Both pass.
- [ ] Commit.

## Task 2: P4 (tags) and P5 (retry needs a timer)

- [ ] Failing tests:
  - `other: alert:nosuch` prints `<node>: alert:nosuch is not a known tag`.
  - `busy: retry-next-tick` on a unit with no `.timer.in` prints `<node>: retry-next-tick on a unit with no timer`.
- [ ] Implement: read `TAGS` from `system/scripts/vaultlib/alerts.py` with `ast` (no import of vault code), and check for a timer file next to each unit.
- [ ] Run the tests and commit.

## Task 3: P2 (locks match the scripts)

- [ ] Failing tests:
  - A node declaring `locks: [run.lock]` whose script names `intake.lock` too prints `<node>: locks [run.lock] but its scripts name [intake.lock, run.lock]`.
  - A declared lock no script names fails the same way.
- [ ] Implement: for each path in `scripts`, find every lock name from the fixed list in spec §4 as a whole-word string. Compare the sorted sets.
- [ ] Run the tests and commit.

## Task 4: P3 (catch-all alert needs a crash handler) and P8 (gaps)

- [ ] Failing tests:
  - A bash entry script with `other: alert:intake` and no `crash_trap` prints `<node>: other is alert:intake but <script> installs no crash handler`.
  - A Python entry script with no `alerts.guard` prints the same.
  - A node with `other: none` and no gap line prints `<node>: other is none with no PIPELINE_GAPS line`.
  - A gap line for a node that now passes prints `<node> P3: gap closed, delete its line`.
- [ ] Implement: the entry script is `scripts[0]`. Bash passes on a `crash_trap ` call; Python passes on `alerts.guard(`. The gaps file is passed as the second argument.
- [ ] Run the tests and commit.

## Task 5: P6 and P7 (every folder written has a reader, every folder read has a writer)

- [ ] Failing tests:
  - A node writing `x/` that no node reads and no sink names prints `x/: written by <node>, read by no node and not a sink`.
  - The reverse case prints `y/: read by <node>, written by no node and not a source`.
  - A `*` part matches one path part (`raw/*/notes/` matches `raw/work/notes/` declared elsewhere).
- [ ] Implement with `fnmatch` on `/`-split parts.
- [ ] Run the tests and commit.

## Task 6: write `system/pipeline.yml` for the 10 core units

- [ ] For each unit in `system/systemd/` (brief, debrief, intake, meetings, nightshift, notify, smoke, sync, triage, update), read its `.service.in`, its `ExecStart` script and each script it calls. Write its node from the spec §3 shape. Cite nothing in the YAML; the Review Focus check covers it.
- [ ] Add the `sources` and `sinks` lists the graph needs. Each entry gets a `by:` naming who reads or writes it outside the graph.
- [ ] Run `pipeline_graph.py . gaps.txt` on the repository with an empty gaps file. Every problem it prints is a real gap or a wrong declaration. Fix the wrong declarations; list each real gap.
- [ ] Commit.

## Task 7: seed `PIPELINE_GAPS`, the repository test, and #436

- [ ] Add `PIPELINE_GAPS` to `pipeline.bats` with one line per real gap from Task 6. Expected, per spec §6: intake P3, meetings P3, notify P3, sync P3, triage P3, update P3, each `#436`.
- [ ] Add the test "the pipeline graph matches the code, outside the known gaps": it runs the checker on the repository and requires empty output.
- [ ] Post one comment on #436 listing the gaps F6 added (node, rule, what is missing), so each is tracked there.
- [ ] Run `bats system/tests/pipeline.bats` and commit.

## Task 8: docs and the gate

- [ ] In FOUNDRY.md "The factory line", add one step: a new core unit needs a node in `system/pipeline.yml`, and `pipeline.bats` checks it against the code.
- [ ] Run `system/scripts/lint_vault.sh`, `bats system/tests/commands.bats system/tests/vault_integrity.bats system/tests/conformance.bats system/tests/pipeline.bats` and the full gate where the host allows (`verify_setup.sh --require-suites`). On a root container the gate fails by design (`helpers.bash:11`); record that, and rely on CI.
- [ ] Self-review the diff against the Review Focus.
- [ ] Run `/foundry-review`.
- [ ] Open the PR.
