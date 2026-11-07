# Factory F6, PR 1: a declared pipeline graph, checked in CI (#477)

**Grill:** 2026-11-03, the owner's round 1 for F6 and F7 on #477, copied below in `## Grill`.
**Builder check:** 2026-11-03, from a read-only inventory of master at `fac74b9`. Three changes to the grill's wording:
- **Manifest file:** Q6 named the manifest `system/pipeline.md`. The index walks every `.md` file outside its skip list (`vaultlib/index.py:274`), so a Markdown manifest would be a note and need a schema, and core is at its 14-schema limit (`vault_integrity.bats:576`). The manifest is `system/pipeline.yml`: the index skips it, and the core line cap does not count it (the cap counts `system/scripts`, `system/hooks` and `.claude/commands` only, `vault_integrity.bats:11-13`).
- **Proving a failure edge:** a "failure edge" cannot be proven from a declaration alone. PR 1 checks the one claim the code can confirm: a node whose catch-all edge is an alert must install the crash handler for its language (`crash_trap` from `lib_fetch.sh` in bash, `alerts.guard` in Python).
- **Today's gaps:** the inventory found more silent exits than #436 lists (§6). They seed the known-gaps list, each naming the issue that will close it.

**Blueprint:** none: a test and a data file, with no runtime change.

## 1. Why

The Foundry is already a pipeline graph: timers start units, units run scripts, scripts pass files through folders, and a lock decides who runs. No file states that graph, so nothing checks it as a whole. The defects #436 keeps finding are missing edges:
- **S5:** a sync conflict stopped intake, the brief and the debrief with nothing raised. Fixed in #479.
- **S6:** one exit 7 holds every Slack notice until the hold file is deleted by hand.
- **S3:** a crash read as success. Fixed in #461.

A read of master on 2026-11-03 (§6) found more paths of the same kind:
- `intake.py` is not wrapped in `alerts.guard`, so an exception it does not catch fails the unit with only a traceback.
- `triage_fetch.sh`, `notify.sh` and `update_template.sh` run under `set -e` with no `crash_trap`.
- A timed-out meetings search exits 4 with no alert.

Each was found by reading code. F6 makes the next one fail CI.

## Grill

| # | Question | Decision |
|---|---|---|
| Q1 | Worth building? | Yes, as the factory's next phase. #436 found S3, S5 and S6 by reading the code by hand; F6 finds missing failure edges mechanically, and F7 stops the Now-line defect class (it came back 3 times after its gate). |
| Q2 | For whom? | Whoever builds on the Foundry: the owner, coding sessions and Work Orders. The owner notices the results as fewer lost briefs and silent stops. |
| Q3 | Without it? | Acceptable until the open #436 items ship, not longer. |
| Q4 | Smallest version | F6 PR 1: the failure-edge and reader/writer rules over core units. F6 PR 2: lock cycles, timing coverage, the Mermaid diagram and extensions. F7: the Now line only, at first. |
| Q5 | Displaces | After the audit track, before recall (Now item 3, #481). |
| Q6 | How steps declare reads, writes and locks | One core manifest, `system/pipeline.md`, written like an extension manifest, plus `reads`, `writes` and `locks` fields in each `extension.md`. The test checks the declared locks against the `flock` calls it finds in each script. A manifest is not script code, so it does not count against the core line cap. (Builder check: `system/pipeline.yml`.) |
| Q7 | Gaps that exist today | An allowlist of dated lines, the same way `TIMING_OVERRUNS` works, started with today's known gaps (each naming its #436 item), so CI is green on day one and the list can only shrink. |
| Q8 | Order | F6 first (no runtime change); then F7 for the Now line, then inputs, then Work Orders, one PR each. |
| Q9 | `/new-source` | Once F6 lands, a new Source writes its pipeline entry and fails CI until it declares its reads, writes, locks and failure edge. |

## 2. Goals

1. Every core unit template in `system/systemd/` has one node in `system/pipeline.yml`, with its scripts, reads, writes, locks and failure edges.
2. CI fails when:
   - a unit has no node;
   - a node's declared locks differ from the lock files its scripts name;
   - a node's catch-all failure edge is an alert but its entry script installs no crash handler;
   - a folder is written that no node reads (outside the declared sinks), or read when no node writes it (outside the declared sources).
3. Every gap that exists on the day PR 1 merges is a dated line in `PIPELINE_GAPS` naming its issue. A gap that is closed must be deleted from the list, so the list can only shrink.

**Non-goals (F6 PR 2):** lock cycles, timing coverage against upstream waits, the Mermaid diagram in FOUNDRY.md, extension nodes (a `pipeline` field in `extension.md`, which needs a core change in `vaultlib/extensions.py`'s field list), and `/new-source` writing a node (Q9).

**Anti-goals:**
- Any runtime change: no script, unit or hook is edited in PR 1.
- A generator that runs the scripts.
- A check that passes when a declaration is merely present but wrong. Each rule compares the declaration with something the code shows.

## 3. The manifest: `system/pipeline.yml`

```yaml
# One node per core unit (F6, #477). The test in system/tests/pipeline.bats checks this file against the code.
sources:   # folders written from outside the graph: the owner, Obsidian, connectors, git
  - {path: raw/inbox/, by: owner}
  - {path: meetings/drop/, by: owner}
  - {path: wiki/*/Now.md, by: owner}           # ticks typed in Obsidian
sinks:     # what the owner reads; read by no node
  - {path: briefings/, by: owner}
  - {path: system/logs/alerts_*.md, by: notify and the brief}
nodes:
  intake:
    unit: foundry-intake
    scripts: [system/scripts/intake_daemon.sh, system/scripts/intake.py, system/scripts/run_headless.sh]
    reads: [raw/inbox/, raw/*/notes/, raw/meetings/, meetings/drop/, wiki/*/Now.md]
    writes: [raw/archive/, raw/*/archive/, system/quarantine/poisoned/, wiki/, wiki/*/Now.md]
    locks: [intake.lock, run.lock]
    failure:
      input: quarantine            # exit 2, or a third failed attempt
      busy: retry-next-tick        # intake.lock or run.lock busy
      other: alert:intake          # catch-all: must be backed by alerts.guard or crash_trap
```

The fields:
- **`unit`:** the unit's name in `system/systemd/`.
- **`scripts`:** the files whose source the lock and crash-handler checks read.
- **`reads` and `writes`:** vault paths. A trailing `/` means a folder, and `*` matches one path part.
- **`locks`:** file names under `system/` or `system/logs/`.
- **`failure`:** a map from condition to edge. The keys are free text except `other`, which every node must have.

The edge kinds:
- `alert:<tag>`: a tag in `vaultlib/alerts.py` `TAGS`.
- `quarantine`.
- `retry-next-tick`: allowed only for a timer unit.
- `caller:<node>`: the failure is reported by the node that ran it.
- `unavailable`: written to `system/logs/inputs/<date>/unavailable.md`, which the brief reads.
- `none`: allowed only with a `PIPELINE_GAPS` line.

## 4. The checks: `system/tests/pipeline_graph.py` and `system/tests/pipeline.bats`

`pipeline_graph.py <vault>` prints one line per problem. It uses only the standard library and PyYAML, the floor `vaultlib` already has. `pipeline.bats` runs it on the repository, and on fixture copies for the negative tests (the pattern of `conformance.bats:442-463`).

| Rule | Problem it prints | How it compares with the code |
|---|---|---|
| P1 units | `<unit>: no node` / `<node>: no unit <unit>` | the `foundry-*.service.in` names in `system/systemd/` |
| P2 locks | `<node>: locks <declared> but its scripts name <found>` | every `run.lock`, `intake.lock`, `nightshift.lock`, `meetings.lock`, `notify.lock`, `index.lock` and `stage.lock` string in the node's `scripts` |
| P3 catch-all | `<node>: other is alert:<tag> but <script> installs no crash handler` | the first script in `scripts`: `crash_trap` (bash) or `alerts.guard` (Python) |
| P4 tags | `<node>: alert:<tag> is not a known tag` | `vaultlib/alerts.py` `TAGS` |
| P5 retry | `<node>: retry-next-tick on a unit with no timer` | a `.timer.in` next to the unit |
| P6 readers | `<path>: written by <node>, read by no node and not a sink` | the manifest itself |
| P7 writers | `<path>: read by <node>, written by no node and not a source` | the manifest itself |
| P8 gaps | `<node>: other is none with no PIPELINE_GAPS line`; `<line>: gap closed, delete its line` | `PIPELINE_GAPS` |

P6 and P7 compare declarations with each other. They catch a folder that piles up unread, or an input no step produces, but cannot catch a wrong declaration. P2 and P3 tie the declarations to the code, as the timing rule ties `TIMING_VALUES` to script defaults.

## 5. Known gaps

`PIPELINE_GAPS` in `pipeline.bats`, one line per gap, in the format of `TIMING_OVERRUNS` (`conformance.bats:325`): `"<node> <rule> <issue>  # what is missing"`. A listed gap that no longer fails prints `gap closed, delete its line`, so the list can only shrink (Q7).

## 6. The graph on master (inventory, 2026-11-03)

| Node | Unit | Locks | Catch-all today | Gap |
|---|---|---|---|---|
| intake | foundry-intake | intake.lock, run.lock | no `alerts.guard` around `intake.py` | P3, #436 |
| brief | foundry-brief | run.lock | `brief_run.sh` alerts after a second rejection; `brief_prep.sh` writes `unavailable.md` and exits 0 | none |
| debrief | foundry-debrief | run.lock | `run_headless.sh` alerts `[intake]`; prep failures write `unavailable.md` | none |
| meetings | foundry-meetings | meetings.lock | search exit 4 and exit 127 are silent | P3, #436 |
| nightshift | foundry-nightshift | nightshift.lock, run.lock | `alerts.guard(..., "orders")` | none |
| notify | foundry-notify | notify.lock | no `crash_trap`; its `[notify]` tag never reaches Slack | P3, #436 (S6) |
| smoke | foundry-smoke | none | `crash_trap foundry-smoke` | none |
| sync | foundry-sync | run.lock | `fail` and `block` alert `[sync]`; "not a git repository" exits 1 silently | P3, #436 |
| triage | foundry-triage | run.lock | no `crash_trap`; exit 127 not in `FETCH_ALERTS` | P3, #436 |
| update | foundry-update | run.lock | `set -e` with no `crash_trap` | P3, #436 (S2 area) |

The full inventory is in the PR description. Line references are against master `fac74b9`. The plan's first task re-reads every row against the branch it starts from.

## 7. Done when

- `bats system/tests/pipeline.bats` passes on the repository, with every gap above on a `PIPELINE_GAPS` line naming its issue.
- Each rule P1–P8 has a negative fixture test that fails with its exact problem line.
- `#436` has one comment listing the gaps F6 added to it.
- FOUNDRY.md "The factory line" names `system/pipeline.yml` and the rule that a new unit needs a node.
- The core cap and the schema count are unchanged.

## 8. Open questions

- **O1:** whether P2 should also check lock waits (`flock -w N`) against the timing rule. Deferred to PR 2, with timing coverage.
- **O2:** whether `caller:<node>` edges should require the caller to name the callee's exit codes. Deferred until a gap shows it is needed.
