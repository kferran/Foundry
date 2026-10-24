# JSON Output for the Console's Reads Design

**Grill:** 2026-10-24, decisions recorded on https://github.com/kferran/Foundry/issues/377 (Q2, Q7, Q9); this is its milestone M0, https://github.com/kferran/Foundry/issues/375.
**Builder check:** 2026-10-24, six questions, all settled: `nightshift.py report` writes its file as a side effect (§3.3: `--json` builds without writing); `now.py list` drops the notes under a line (§3.1: they are read with their line); a hand-written open line that does not parse (§3.1: listed under `unparsed`, never dropped); which day the overdue band is measured from (§3.1: `--date`, default today); the focus-first brief's stale and overflow fields not yet on master (§3.2: the keys exist now and fill in when #351 merges); how the console detects a contract change (§3: a top-level `"v": 1`).
**Blueprint:** none: a `--json` flag on four existing read commands; no new source, poller, compile run or Work Order.

## 1. Problem

The console extension (#377) reads the vault only through the scripts' output (Q7). `vault_index.py` already prints JSON for `query`, `related`, `backlinks`, `orphans`, `tags`, `issues` and `validate` (`vaultlib/cli.py:442-446`). The Today screen also needs the Now lines, the focus projects and the Work Orders, and those scripts print only markdown or tab-separated text:
- `now.py list` prints the raw `- [ ] ` lines (`now.py:97-101`), without their notes.
- `active_projects.py <date>` prints markdown blocks with items cut to 160 characters.
- `nightshift.py list` prints tab-separated fields (`nightshift_run.py:915-917`); `nightshift.py report` prints the report markdown and writes it to disk (`nightshift_run.py:924-926`).

## 2. Goal

Each of those four commands takes `--json` and prints one JSON object on stdout. Without the flag, output is byte-identical to today. Exit codes stay 0, 1 and 2 as each command defines them.

## 3. Design

Every object starts with `"v": 1`. A change that removes or renames a key bumps it; adding a key does not. Printed with `json.dumps(obj, ensure_ascii=False)`, one line. Text values are the text the markdown form prints, uncut; the console decides what to truncate. Nothing is redacted beyond what the vault files already hold, since the output stays on the machine.

### 3.1 `now.py list --json [--partition <p>] [--date YYYY-MM-DD]`

```json
{"v": 1, "date": "2026-10-24", "partitions": {"work": {
  "lines": [{"kind": "owed", "section": "Needs you", "statement": "Reply on the retry cap question",
             "who": "Blake Sample", "since": "2026-10-19", "evidence": "https://mail.example.com/x",
             "rec": "", "due": "2026-10-20", "over": 4, "band": "1-7",
             "notes": [{"date": "2026-10-21", "text": "asked for metrics first"}],
             "raw": "- [ ] owed: Reply on the retry cap question [due:: 2026-10-20] (Blake Sample, since 2026-10-19, https://mail.example.com/x)"}],
  "unparsed": ["- [ ] a hand-written line"]}}}
```

- `statement` has the `[rec:: …]` and `[due:: …]` fields taken out; `rec` and `due` hold them (`""` when absent). Reuses `now.parse()` and `now.fields()`.
- `section` comes from the kind: `owed` and `draft` are `Needs you`, `waiting` is `Waiting`, as `add()` files them.
- `over` is the days past `due` measured from `--date` (default `Intake.today()`), `null` when there is no valid due or it is not past. `band` is `"1-7"`, `"8-30"`, `"30+"` or `null`, the same groups as `now.overdue()`; one helper serves both.
- `notes` are the indented `  - YYYY-MM-DD: <text>` lines under the line (`_block_end()`); a note line in another shape keeps its text with `date: ""`.
- An open line that `parse()` cannot read goes in `unparsed` as written, so the count of open lines in the JSON equals `len(open_lines())`.
- A partition with no page is present with empty lists. `--partition` limits the object to that one.

### 3.2 `active_projects.py <date> --json`

```json
{"v": 1, "date": "2026-10-24", "partitions": {"work": {
  "projects": [{"link": "Alpha", "path": "wiki/work/concepts/alpha.md", "focus": "cutover plan",
                "next": ["Write the cutover runbook"], "decisions": ["Retry cap: 3 or 5 attempts"],
                "decisions_more": 0, "stale": null}],
  "also_active": []}},
 "notices": ["- work: [[Gamma]] in ActiveProjects does not resolve to a note."]}
```

- Built from the same pass as the markdown (`partition_blocks()` returns data; the markdown is rendered from it), so the two cannot disagree. Caps unchanged: at most `MAX_NEXT` next items and `MAX_DECISIONS` decisions, with `decisions_more` counting the rest.
- `stale` (a date string or `null`) and `also_active` (links) exist now as `null` and `[]`. When the focus-first brief (#351) merges, its Task 1 and Task 2 fill them; whichever lands second wires the other's fields.
- `notices` is the same list the markdown prints under `## Notices`.

### 3.3 `nightshift.py list --json` and `nightshift.py report --json [date]`

```json
{"v": 1, "items": [{"id": "2026-10-23-focus-first-brief", "partition": "work", "kind": "plan", "state": "queued",
  "start": "at", "start_at": "2026-10-23T22:00:00-06:00", "queued_at": "…", "started_at": null, "finished_at": null,
  "repo": "template", "result": null, "reason": null}]}
```

```json
{"v": 1, "date": "2026-10-24", "health": {"…": "…"}, "held": null,
 "needs": [{"id": "2026-10-23-focus-first-brief", "text": "Review the pull request"}],
 "items": [{"id": "…", "kind": "plan", "state": "done", "reason": null, "started_at": "…", "finished_at": "…",
            "result": "https://github.com/kferran/Foundry/pull/380", "notes": null}]}
```

- `list --json` reads every item's frontmatter (`ni.items()`), the fields above, `null` for a missing one.
- `report --json` uses the data `build()` renders (a new `data(vault, date)`, which `build()` then formats), and **does not write** `system/logs/nightshift/<date>.md`: a read from the console must not change the vault. Text keeps the report's `_clean()` bound.
- Neither takes the runner lock, as today.

## 4. Out of scope

The console itself (#377 M1), `--json` on other commands, any write command, a JSON schema file, and changing the markdown output.

## 5. Tasks

### Task 1: `now.py list --json`

**Files:** `system/scripts/now.py`, `system/scripts/vaultlib/now.py`; test `system/tests/python/test_now.py`.

- [ ] Failing tests: `test_list_json_parses_fields_and_notes` (a line with who, evidence, rec, due and two notes); `test_list_json_bands_match_overdue` (due 3, 10 and 40 days before `--date` give `1-7`, `8-30`, `30+`; the same lines through `now.overdue()` land in the same groups); `test_list_json_keeps_unparsed_lines` (open-line count equals `len(open_lines())`); `test_list_json_missing_page_is_empty`; `test_list_without_json_is_unchanged` (output equals today's for a fixture page).
- [ ] Implement: a `band(due, day)` helper shared with `overdue()`; a `line_data()` reader; the flag. Run `system/scripts/test.sh system/tests/python/test_now.py`. Commit.

### Task 2: `active_projects.py --json`

**Files:** `system/scripts/active_projects.py`; test `system/tests/python/test_active_projects.py`.

- [ ] Failing tests: `test_json_matches_the_markdown` (the same fixture: every project, next item and decision in the markdown is in the JSON, uncut); `test_json_counts_decisions_more`; `test_json_carries_notices`; `test_json_has_stale_and_also_active_keys`; `test_markdown_is_unchanged`.
- [ ] Implement: `partition_blocks()` returns data, rendered to markdown by a separate function. Run `system/scripts/test.sh system/tests/python/test_active_projects.py` and `system/scripts/test.sh system/tests/prep.bats`. Commit.

### Task 3: `nightshift.py list --json` and `report --json`

**Files:** `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/vaultlib/nightshift_report.py`; tests `system/tests/python/test_nightshift_report.py`, `system/tests/python/test_nightshift_run.py`.

- [ ] Failing tests: `test_list_json_has_every_item_with_nulls`; `test_report_json_matches_build` (the ids, states and needs in `build()`'s markdown equal the JSON's); `test_report_json_writes_no_file` (the report path does not exist after the call); `test_report_without_json_is_unchanged`.
- [ ] Implement `data(vault, date)`; `build()` formats it. Run `system/scripts/test.sh system/tests/python/test_nightshift_report.py` and `system/scripts/test.sh system/tests/python/test_nightshift_run.py`. Commit.

### Task 4: Docs

**Files:** `FOUNDRY.md` (the commands table rows for `now.py`, `active_projects.py`, `nightshift.py`), each script's usage docstring, `CHANGELOG.md` (a line under the merge date ending `(#PR)`).

- [ ] Name the flag and the `"v": 1` rule. Run `system/scripts/test.sh system/tests/commands.bats` and `system/scripts/test.sh system/tests/conformance.bats`. Commit.
