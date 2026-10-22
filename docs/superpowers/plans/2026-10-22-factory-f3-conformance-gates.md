# Factory F3: Conformance Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with superpowers:test-driven-development for every task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The F0 ratchets become rules a new Source must pass (one core config reader, part homes, the Source rule, timing budgets in manifests), and the core budget counts hooks and commands under a 15,000-line cap.

**Architecture:** PR 1 adds `vaultlib/config.py`, moves all 13 core readers onto it and turns `COPIES_ALLOWED` into `PART_HOMES` with a path-literal `config` scan. PR 2 adds the Source rule as a pytest over a root, a `budget` manifest field that the timing test reads through a small test helper, and the budget count and cap in `vault_integrity.bats`. Every rule is a function over a root directory, run on the repository and on a fixture copy of the tracked tree with one seeded violation.

**Tech Stack:** Python 3 stdlib (`ast`, `re`, `subprocess`), PyYAML through `vaultlib.frontmatter`, pytest, bats.

**Spec:** `docs/superpowers/specs/2026-10-22-factory-f3-conformance-gates-design.md`

## Global Constraints

- Cap: **15,000** lines over `git ls-files system/scripts system/hooks .claude/commands`; the cap assertion skips when `system/config.md` exists, the count is printed either way. `.githooks/pre-commit` stays out.
- Manifest `contract` stays 1. `FIELDS` gains `budget`; a manifest without it still loads, and the loader does not validate it.
- `budget` shape: `values` (name → number), `steps` (`"<unit> <count> <grace> <key>"` strings), optional `out` (a reason string). Scripts keep their own defaults; the test checks the manifest agrees, nothing reads timeouts from a manifest.
- Part homes: `walker`/`fail-class` in `vaultlib/connector.py`; `helper` `lib_fetch.sh:logline|alert_once|fail|skip`; `stub` `stub_claude_connector`; other shapes `walker vaultlib/nightshift_session.py`, `stub stub_claude`, `stub stub_claude_nightshift`, `helper vault_sync.sh:fail`; `config` in `vaultlib/config.py` and `vaultlib/extensions.py`.
- Runners: `system/scripts/lib_connector.sh`, `system/scripts/run_headless.sh`, `system/scripts/vaultlib/nightshift_session.py`. No-session callers (listed in a comment): `lib_confine.sh` (`mcp list`), `smoke_check.sh` (`--version`), `vaultlib/nightshift_run.py` (`auth status`).
- `TIMING_OVERRUNS` keeps its five #299 lines; `TIMING_OUT` keeps only `foundry-nightshift`.
- Conformance tests read manifests by presence (`extensions/*/extension.md`), never through `enabled()`/`extensions.py field`, which return nothing in the template (no `config.md`).
- Fixture style, all rules: copy the tracked tree (`git ls-files`) into a temp dir, `git init -q` and `git add -A` there, seed one violation, assert the exact problem lines. Bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- Template stays generic. Each user-visible change gets a CHANGELOG line under a `## 2026-10-22` heading.

## Review Focus

1. A config file that exists but is not UTF-8: every moved reader returns its default; the Work Order screen refuses a template order with "config has no template_remote". Tests: Task 1 (reader), Task 2 (triage, notify, nightshift_check).
2. A Python docstring or comment that says `claude -p` (`vaultlib/stream.py` line 1) must not count as a session. Test: Task 4 runs the rule on the real tree, which holds that docstring.
3. A checker that only imports `walk` (no call) must fail rule 2: an import line names `walk` without `(`. Test: Task 4's seeded checker keeps its import and loses its calls.
4. A manifest that stops loading (a typo'd field) must fail the timing test loudly, not drop its steps silently. Test: Task 5 helper prints `P <ext>: <reason>` for a manifest that does not load; one fixture case.
5. A known overrun whose sum now comes from a manifest (`watch`, `smoke/watch`) must still be found, or the "known overrun with no steps" check fires. Test: Task 5's run on the real tree.

---

## PR 1: one config reader and part homes (branch `feat/factory-f3-config`)

### Task 1: `vaultlib/config.py`

**Files:** Create `system/scripts/vaultlib/config.py`, `system/tests/python/test_config.py`.

**Interfaces:** Produces `config(vault) -> dict` and `text(vault, key: str, default: str) -> str`. `config.py` imports only `vaultlib.frontmatter` (`extensions.py` will import it; anything more risks a cycle).

- [ ] Step 1: Write `test_config.py`: missing file, a `b"\xff"` file, malformed frontmatter (`---\n: [\n---\n`) and a file with no frontmatter each give `config(v) == {}`; `config(v)["timezone"] == "UTC"` for a good file; `text(v, k, "d") == "d"` for a missing key, `""`, a list and a missing file; `text` returns the string when set.
- [ ] Step 2: `system/scripts/test.sh system/tests/python/test_config.py` → FAIL (no module).
- [ ] Step 3: Implement: read `<vault>/system/config.md` as UTF-8, `frontmatter.parse(...).data or {}`, `{}` on `OSError`/`UnicodeDecodeError`; `text` returns the value when it is a non-empty `str`, else the default.
- [ ] Step 4: Run → PASS. Commit.

### Task 2: the 13 readers move onto it

**Files:** Modify `system/scripts/alert.py`, `commit_runs.py`, `away.py`, `meeting_actions.py`, `vaultlib/{nightshift_check,notify,triage,meeting_prep,sources,meetings,recall,extensions,intake,api}.py`, their pytest modules, `CHANGELOG.md`.

**Interfaces:** Consumes Task 1. Keeps: `triage.config`, `notify.config`, `nightshift_check.config` as module attributes (`from .config import config`; `watch.py` calls `triage.config`, the `notify.py` script calls `notify.config`), `Intake.config(key, default)` (delegates to `text`), `vaultlib.api.config` (import moves from `.triage` to `.config`). `nightshift_check._fm` stays for codebase notes. `extensions.listed` and `extensions.migrate` read through `config`; `extensions.enable` keeps its text edit.

- [ ] Step 1: Tests first: in `test_triage.py`, `test_notify.py`, `test_nightshift_check.py`, write `system/config.md` as `b"\xff\xfe"` and assert `config(v) == {}` (today they raise `UnicodeDecodeError`); in `test_nightshift_check.py` also assert a template order's screen gives `["config has no template_remote"]` (the line-205 path) with that file.
- [ ] Step 2: Run the three modules → FAIL on the new tests.
- [ ] Step 3: Replace each copy: the five `def config(`, the three `_config(` (delete the function, call `config(vault)` or the module-level import), the inline parses in `away.py`, `meetings.owner_names`, `recall.budget_for` and `recall.default_partition`, `extensions.listed`/`migrate`, `Intake.config`, `commit_runs.config` (becomes `text(VAULT, key, default)`). Keep each caller's own fallback (`away.vault_tz` still UTC on a bad zone; `recall` still `ValueError` → default). After this, `git grep -n 'config\.md["'"'"']' -- 'system/scripts/*.py' 'extensions/*/scripts/*.py'` lists only `vaultlib/config.py` and `vaultlib/extensions.py` (`enable`).
- [ ] Step 4: Run the touched pytest modules (`test_config`, `test_triage`, `test_notify`, `test_nightshift_check`, `test_alerts`, `test_commit_runs`, `test_meeting_actions`, `test_meeting_prep`, `test_meetings`, `test_recall`, `test_sources`, `test_extensions`, `test_intake`, `test_extension_api`) plus `extensions/intraday/tests/python`, `extensions/handoffs/tests/python`, `extensions/telemetry/tests/python` → PASS.
- [ ] Step 5: CHANGELOG `## 2026-10-22`: "Changed: every core script reads `system/config.md` through one reader. Triage, notices and the Work Order screen no longer stop on a config file that cannot be read; they use their defaults like the other scripts, and the screen refuses a template order (`config has no template_remote`). (#308)". Commit.

### Task 3: `COPIES_ALLOWED` becomes `PART_HOMES`

**Files:** Modify `system/tests/conformance.bats` (tests only, no CHANGELOG line).

**Interfaces:** Produces bats functions `copies <root>` (every `<kind> <path>[:<name>]` line in `<root>`'s tracked tree, sorted; `git -C "$1" grep`/`ls-files`) and `new_copies <root>` (`comm -13` of `PART_HOMES` against `copies <root>`).

- [ ] Step 1: Write the fixture test "a new copy of a shared part fails, a home passes (factory F3 §3.2)": copy the tracked tree into `$BATS_TEST_TMPDIR/repo`, `git init -q`, add `system/scripts/vaultlib/walker2.py` (`for b in blocks: if b.get("type") == "tool_result": ...`) and `extensions/handoffs/scripts/cfg.py` (`p = root / "system" / "config.md"`), `git add -A`; assert `new_copies` output is exactly `config extensions/handoffs/scripts/cfg.py` then `walker system/scripts/vaultlib/walker2.py`.
- [ ] Step 2: Run `system/scripts/test.sh system/tests/conformance.bats` → the new test FAILs (`new_copies` undefined, then the `config` line missing while the scan is `^def config\(`). Keep the red output for the PR body.
- [ ] Step 3: Rename to `PART_HOMES`; header comment: every line is a design fact, a new line needs the owner's review with its reason (drop "may only shrink"). Delete the five `config` lines; add `config system/scripts/vaultlib/config.py  # home: the one config reader (F3 spec §3.3)` and `config system/scripts/vaultlib/extensions.py  # home: enable edits the extensions: line as text (F3 spec §3.2)`. Reword the other reasons to say home or other shape per the Global Constraints. The `config` scan becomes `git -C "$1" grep -lE "config\.md[\"']"` over the `.py` pathspecs. The real-tree test calls `copies "$VAULT_ROOT"` and keeps the "listed but no longer found" check. Update the file header comment (ratchets → rules).
- [ ] Step 4: Run `conformance.bats` → PASS. Print `git ls-files -z system/scripts | xargs -0 cat | wc -l` and the three-folder total for the PR body. Commit.

PR 1 body: Part of #308; spec and plan paths; the red runs; core lines before (14,128 / 14,906) and after.

---

## PR 2: Source rule, manifest budgets, budget scope and cap (branch `feat/factory-f3-rules`, on PR 1)

### Task 4: the Source rule

**Files:** Create `system/tests/python/test_source_rule.py`.

**Interfaces:** Produces `tracked(root) -> list[str]` (`git -C root ls-files` under `system/scripts` and `extensions/*/scripts`), `session_problems(root) -> list[str]`, `source_problems(root, table=CORE) -> list[str]`, and a fixture helper `tree(tmp_path) -> Path` (copy tracked files, `git init -q`, `git add -A`). The module skips when `system/config.md` exists, as `test_extension_api.py` does.

`CORE` (spec §3.1 table): `{"calendar_fetch.sh": (("calendar",), "calendar"), "meetings_fetch.sh": (("meetings",), None), "triage_fetch.sh": (("triage", "triage_chat"), None), "notify.sh": ("its --check posts a message to the channel", None)}`: smoke rows (or a reason string), then the tag when the script sets no `FETCH_TAG`.

Rules, each on non-comment lines (`line.lstrip()` not starting with `#`):
- Session (any tracked file but the runners): shell `(\bclaude|\$\{?(CLAUDE_BIN|claude_bin)\b\S*)\s+-p\b`; `.py` `(["']claude["']|claude_bin\(\)|CLAUDE_BIN\b[^,\]]*)\s*,\s*["']-p["']`. Message `<rel>:<n>: starts a claude session outside a runner`.
- A Source is a tracked non-`.py` file other than `lib_connector.sh` with a code line calling `connector_run`. Core = under `system/scripts/`, keyed by basename in the table.
- 1: a `source …lib_fetch.sh` line after the `source …lib_connector.sh` line, else `<rel>: does not source lib_fetch.sh after lib_connector.sh`.
- 2: the checker is the program on each line holding `< "$work/out.jsonl"` and `2> "$work/check.err"`: a `*.py` path, or `"$VAR"` resolved from a `VAR=<path>` line. Its direct imports (`ast` `Import`/`ImportFrom`, resolved against `system/scripts` for core and the extension's `scripts/` for an extension, both `pkg.mod` and `from pkg import mod`; `vaultlib.api` and `vaultlib.connector` never count) plus itself must hold an `ast.Call` to `walk` or `check_stream` (a `Name` or an `Attribute`). Else `<rel>: its checker <checker rel> calls neither walk( nor check_stream(`. No checker line: `<rel>: no checker reads $work/out.jsonl`.
- 3: accepts `--check` = a code line with `--check` or `fetch_check_arg`. Core: rows = `^\s*connector (\w+) .*system/scripts/<name> --check` in `smoke_check.sh`; a tuple must equal the found rows (`<rel>: smoke rows <found> differ from the table's <want>`); an empty tuple: `<rel>: accepts --check and has no smoke row and no reason in the table`. Extension: a manifest `smoke` entry with `connector` `true` and `run` starting `scripts/<path under scripts/> --check`, else `<rel>: accepts --check and has no connector smoke row in its manifest`.
- 4: `FETCH_TAG=(\w+)`. Core: a key of `TAGS` read with `ast.literal_eval` from `<root>/system/scripts/vaultlib/alerts.py`, else `<rel>: FETCH_TAG <t> is not a key of alerts.TAGS`; no `FETCH_TAG` and no table tag: `<rel>: sets no FETCH_TAG`. Extension: a bare or `{tag: …}` entry of its manifest's `alert_tags`, else `<rel>: FETCH_TAG <t> is not in its manifest's alert_tags`.
- Table: `<rel>: a core Source missing from the table`; `<name>: a table row with no script`.

- [ ] Step 1: Tests: `session_problems(REPO) == []` and `source_problems(REPO) == []`; a test that the Sources found are exactly the spec's seven; parametrized seeded cases on `tree(tmp_path)`, each asserting the exact one-line list: `claude -p "$p"` in a new `extensions/handoffs/scripts/x.sh`; `"${CLAUDE_BIN:-claude}" -p` in a new core `.sh`; `subprocess.run([claude_bin(), "-p", p])` in a new `.py`; the `lib_fetch.sh` source line deleted from `jira_fetch.sh`; every `check_stream(` call in `jira_handoffs.py` renamed (its import kept); `table` without `notify.sh`; `table` plus `"gone_fetch.sh"`; the `smoke` entry deleted from `extensions/handoffs/extension.md`; `table` with `notify.sh: ((), None)`; `FETCH_TAG=handoffs` → `handoff`; `FETCH_TAG=meetings` → `meeting`.
- [ ] Step 2: Run → FAIL (functions missing); keep the red output. Step 3: implement. Step 4: run → PASS. Commit.

### Task 5: timing budgets in manifests

**Files:** Modify `system/scripts/vaultlib/extensions.py` (`FIELDS`), `extensions/{handoffs,intraday,telemetry}/extension.md`, `extensions/intraday/scripts/watch.py`, `extensions/telemetry/scripts/rca.py`, `system/tests/conformance.bats`, `system/tests/python/test_extensions.py`, `FOUNDRY.md` (Intraday paragraph). Create `system/tests/timing_manifests.py`.

**Interfaces:** `timing_manifests.py <root>` imports `vaultlib.extensions` from the repository it lives in and prints, for each `<root>/extensions/*/extension.md` by name: `V <key> <seconds>`, `S <unit> <count> <grace> <key>`, `O <unit>`, `P <problem>`. Extension value names become `<ext>.<NAME>`; unit `tick` becomes `tick/<ext>`; each `tick` adds `V tick.<ext> <timeout>` and `S intake 1 - tick.<ext>`; each `smoke` row adds `V row.<row> <timeout>` and `S smoke <1, or 2 with each> - row.<row>`; `out` adds `O <unit>` for each manifest unit (`foundry-` dropped). `P` lines: a manifest that does not load (`manifest()`'s reason); a `values` name whose default (`\$\{NAME:-([0-9]+)\}` or `^\s*NAME = ([0-9]+)\b` in the extension's `scripts/` tree) is found other than once (`<ext>: budget value NAME: <k> defaults in scripts/`) or differs (`<ext>: budget value NAME is <n>; <file> says <m>`); a step that is not four tokens. The bats test becomes `timing_problems <root>` (subshell `cd`, reads the core tables plus the helper's lines; prints `# <unit>: <t> s of <limit> s` info lines and problem lines).

Manifests (values and steps from today's core lines; numbers are the scripts' defaults):
- handoffs: `values: {JIRA_TIMEOUT: 300}`; steps `brief 1 grace.listing listing`, `brief 1 grace.connector JIRA_TIMEOUT`, `smoke/handoffs 1 grace.listing listing`, `smoke/handoffs 1 grace.connector JIRA_TIMEOUT`.
- intraday: `values: {WATCH_SLACK_TIMEOUT: 420, WATCH_MAIL_TIMEOUT: 480, MAX_FETCH_DAYS: 2, ROUTE_LOCK_WAIT: 120}`; today's `watch` and `smoke/watch` lines with the new keys (`watch.lock` → `ROUTE_LOCK_WAIT`). `watch.py` gets `ROUTE_LOCK_WAIT = 120` and uses it.
- telemetry: `values: {RCA_TIMEOUT: 300, PER_TICK: 3, FILED_LOCK_WAIT: 120}`; steps `tick PER_TICK grace.listing listing`, `tick PER_TICK grace.connector RCA_TIMEOUT`, `tick PER_TICK - FILED_LOCK_WAIT` (each filing's `rca.py filed`/`reopen` waits run.lock; `rca.py` gets `FILED_LOCK_WAIT = 120` for both locks); `out: "the HTTP poller: no session, each call has its own 60 s limit"`. Total 3 × 465 = 1,395 s of 1,900.

- [ ] Step 1: Tests first. In `conformance.bats`, the fixture test "a manifest budget that disagrees, a session no step sums, a tick over its timeout and a manifest that does not load each fail (factory F3 §3.4)": copy the tracked tree, `git init`, then seed with `sed -i`: intraday `WATCH_SLACK_TIMEOUT: 420` → `421`; handoffs' two `JIRA_TIMEOUT` step lines deleted; telemetry `timeout: 1900` → `1000`; a new `extensions/demo/extension.md` with `name: demo`, `contract: 1`, `bogus: 1`. Assert the problem lines are exactly (sorted): `demo: unknown manifest field(s) bogus`, `extensions/handoffs/scripts/jira_fetch.sh: JIRA_TIMEOUT has no step`, `intraday: budget value WATCH_SLACK_TIMEOUT is 421; extensions/intraday/scripts/watch_fetch.sh says 420`, `tick/telemetry: 1395 s of waits against a 1000 s limit`. In `test_extensions.py`: a manifest with `budget:` loads.
- [ ] Step 2: Run both → FAIL; keep the red output.
- [ ] Step 3: Implement. Delete from the core tables every line naming an `extensions/` path or an extension unit (`jira`, `tick.*`, `watch.*`, `row.handoffs|watch|telemetry`, `rca`; the `brief` jira steps, `intake` tick steps, the three manifest smoke rows, all `watch`, `smoke/handoffs`, `smoke/watch` steps); `TIMING_OUT='foundry-nightshift'`; rewrite the comments above the tables (the telemetry note moves to its `out`). Add a check: a `TIMING_VALUES` line naming an `extensions/` file is a problem. The session-default check: a core var needs a `TIMING_VALUES` line whose key some step uses; an extension var needs `<ext>.<VAR>` from `V` lines (`<rel>: <VAR> has no budget value in its manifest`) and a step using it (`<rel>: <VAR> has no step`). Smoke rows from `smoke_check.sh` still need `row.<row>` lines; manifest rows get theirs from the helper. Limits: `tick/<ext>` reads `tick.<ext>`. Units in `O` lines join `TIMING_OUT`. FOUNDRY.md Intraday paragraph: one sentence on `budget` (values the scripts' defaults, steps per unit, `out` for a unit with no session; `conformance.bats` checks them).
- [ ] Step 4: Run `conformance.bats`, `test_extensions.py`, `extensions/intraday/tests/python`, `extensions/telemetry/tests/python` → PASS; the real-tree totals match today's for every unit except the new `tick/telemetry`. Commit.

### Task 6: the budget counts hooks and commands, under a cap

**Files:** Modify `system/tests/vault_integrity.bats`, `FOUNDRY.md` (D5 row), `CHANGELOG.md`.

**Interfaces:** Produces `CORE_CAP=15000`, `core_lines <root>` (`git -C "$1" ls-files -z system/scripts system/hooks .claude/commands`, catted from `<root>`, `wc -l`) and `core_problem <root>` (nothing when `<root>/system/config.md` exists; else `core is <n> lines; the cap is 15000` when over).

- [ ] Step 1: Fixture test: `git init` a temp tree with `system/hooks/big` of 15,001 lines (`seq`), `git add`; assert `core_problem` prints `core is 15001 lines; the cap is 15000`; add `system/config.md`, assert empty output.
- [ ] Step 2: Run `vault_integrity.bats` → FAIL; keep the red output.
- [ ] Step 3: Implement; the budget test prints `core lines: <n> (cap 15000)` and asserts `core_problem "$VAULT_ROOT"` is empty. Replace the "Line cap removed" comment with a dated line: 15,000 over three folders (owner, 2026-10-22; 14,906 at `fd59bc5`); the #122 sweep lowers it. FOUNDRY.md D5: "Fixed: the budget counts `system/scripts`, `system/hooks` and `.claude/commands` under a 15,000-line cap | F3 (#308), done". CHANGELOG: "Changed: the core line budget counts `system/hooks` and `.claude/commands` with `system/scripts`, capped at 15,000 lines in the template; a vault prints its count and skips the cap. Extension manifests state their time budgets in a new `budget` field, checked against the scripts' defaults. (#308)".
- [ ] Step 4: Run → PASS. Commit.

PR 2 body: Part of #308; contains PR 1 while it is open; spec and plan; the red runs of Tasks 4–6; core lines; spec corrections (the Source table lives in `test_source_rule.py`; telemetry's tick also sums `FILED_LOCK_WAIT`).
