# Factory F6, PR 2: lock order, cross-unit waits, the diagram and extension nodes (#477)

**Grill:** pending. Questions G1–G6 below, each with the builder's recommendation, go to the owner in one batch.
**Builder check:** 2026-11-04, from a read of master at `cd1d82b` (F6 PR 1 and crash-alerts PRs A–C merged; `PIPELINE_GAPS` empty). Two findings change PR 1's non-goal list:
- **F6 spec O1 is already done.** The timing rule (`conformance.bats` `TIMING_VALUES`) already reads every lock wait in core (`headless.lock`, `ingest.lock`, `archive.lock`, `intake.lock`, `triage.lock`, `update.lock`) and sums them into each unit's limit. PR 2 does not add a second per-unit timing check.
- **Extension nodes need no core field.** PR 1's non-goal said a `pipeline` field in `extension.md` needs a change to `vaultlib/extensions.py` `FIELDS` (core lines). A file next to the manifest, `extensions/<name>/pipeline.yml`, read only by the test, needs none: the core cap does not count `system/tests`.

**Blueprint:** none: a test, data files and a generated block in FOUNDRY.md, with no runtime change.

## 1. Why

PR 1 checks each node on its own: its locks, its catch-all edge, its folders. Two defect kinds cross nodes and are still found by hand:
- **Lock order.** Two units that take the same two locks in opposite orders can deadlock. Intake holds `intake.lock` for its tick (`vaultlib/intake.py:971`) and takes `run.lock` per run inside it; nightshift and `meeting_import.py` also take two locks each. PR 1 declares locks as a set, so no test states or keeps an order. The plan's first task reads each node's acquisition order from the code.
- **A wait shorter than the other side's hold.** The brief waits 1,400 s for `run.lock`; an intake tick can hold it for up to `INTAKE_MAX_RUNS` headless runs. A wait that can end before the holder lets go needs a `busy` edge that says what happens then. PR 1 does not compare the two.

Extension units (console, intraday's watch, telemetry) have no node, so P1–P8 skip them. FOUNDRY.md has no picture of the graph.

## 2. Grill questions (owner to decide)

| # | Question | Recommendation |
|---|---|---|
| G1 | How is lock order stated? | `locks` becomes an ordered list, outermost first. A new rule P9 fails when two nodes take any two locks in opposite orders. P2 keeps comparing the set with the code; the order is the declaration's claim, checked against the other nodes. |
| G2 | Cross-unit waits: what does the rule check? | P10: for each lock a node waits on, if its wait (a `TIMING_VALUES` key named on the lock) is shorter than the longest hold of that lock by another node (that node's `TIMING_STEPS` sum), the waiting node must declare a `busy` edge that is not `none`. It reuses the timing tables; it does not ask for waits to cover every hold, which would push the brief past its limit. |
| G3 | The diagram | `pipeline_graph.py --mermaid` prints a flowchart: nodes, the folders between them (writes to reads), and sources and sinks at the edges; locks are left out to keep it readable. FOUNDRY.md holds it between two markers, and `pipeline.bats` fails when the block differs from the generator's output. |
| G4 | Extension nodes | `extensions/<name>/pipeline.yml`, the same node shape, for every extension that ships a unit (console, intraday, telemetry today). The rules run on core alone in `gate` and on core plus every extension in `gate-all-extensions`. An extension's Sources and tick steps, which run inside core units, add their scripts to that core node through the same file (`extends: brief` or `extends: intake`). |
| G5 | `/new-source` (F6 Q9) | The skill writes or extends the extension's `pipeline.yml` for the Source's fetch script (`extends: brief`), and the skill's checklist adds the pipeline test to the checks it runs. |
| G6 | Delivery | Two PRs: PR 2a extension nodes, the diagram and `/new-source` (no new rule on core); PR 2b P9 and P10 with their gap lines. Either can merge first. |

## 3. Shape (if G1–G6 go as recommended)

- `system/pipeline.yml`: `locks` lists reordered outermost first; a comment states the order rule.
- `system/tests/pipeline_graph.py`: loads `extensions/*/pipeline.yml` when asked (`--extensions`); adds P9, P10 and `--mermaid`. P10 reads the timing tables through the same parser `conformance.bats` uses (`timing_manifests.py` for extension budgets).
- `system/tests/pipeline.bats`: negative fixtures for P9 and P10; the diagram check; extension runs.
- `extensions/{console,intraday,telemetry}/pipeline.yml`: one node each; Source-only extensions (handoffs, health) add `extends` entries if they run scripts in core units.
- FOUNDRY.md "The factory line": the diagram block and one line on extension nodes.
- `.claude/skills/new-source/SKILL.md`: the pipeline step.

Done when: every rule has a negative fixture test; `gate` and `gate-all-extensions` pass with any new gap on a `PIPELINE_GAPS` line naming its issue; the core cap and schema count are unchanged.

## 4. Open questions

- **O3:** whether P10 should also cover `flock -n` callers (no wait at all), which today all declare `busy`. Recommended: yes, they are the zero-wait case of the same rule.
