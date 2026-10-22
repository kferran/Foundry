# F3: conformance gates

**Date:** 2026-10-22
**Status:** draft for the owner
**Program:** `docs/superpowers/2026-10-21-factory-plan.md` (phase F3)
**Grill:** 2026-10-21, recorded in the program plan's `## Grill` section (the factory is the owner's idea; F3 is part of the program the owner approved with #304).
**Builder check:** 2026-10-22, three questions, all settled as my calls in §6 (PR 1's merge lane, an extension unit with no sessions, the cap in a vault); the two owner decisions are in §7.
**Blueprint:** none: conformance tests and one core reader, no feature shape.
**Lane:** small feature (task list in §4, no separate plan). PR 1 touches alert, intake and Work Order screen code, so the owner merges it; PR 2 auto-merges on green CI (program plan §1 table) once the owner has settled §7.

## 1. Why

F0 stopped new copies with ratchets: allowlists of known violators that each F1 retrofit shrank. F1 and F2 are merged, so the lists hold only the parts' homes, shapes that differ on purpose, and five core config readers. F3 turns the ratchets into rules a new Source must pass before anyone reviews it, which is what F4's `new-source` scaffold is tested against (program plan §3, F4 done-when). It also closes departure D5: the core line budget counts only `system/scripts`.

## 2. Goals, non-goals, anti-goals

- **Goals:** one test per rule, each shown failing on a seeded violation in a fixture tree before it passes on the real one; no allowlist left whose lines a later PR is expected to delete, except the timing overruns #299 owns (§3.4); one core reader of `system/config.md`; an extension's timing budget stated in its manifest; the core budget counting hooks and commands at a cap.
- **Non-goals:** the core manifest (core's units, smoke rows and tags stay hard-coded; the test's own table names core sources, as the plan says); fixing #299's overruns (§3.4); calendar's own alert line (§9); F4's skills.
- **Anti-goals:** a rule that passes today only because it reads a hand-kept list of the current files; a script that reads its timeouts from its manifest (the script default stays the value, the manifest states it and the test checks they agree); a manifest `contract` bump.

## 3. Decisions

### 3.1 The Source rule

**What a Source is.** A tracked script under `system/scripts/` or `extensions/*/scripts/` that calls `connector_run`. Today seven: `calendar_fetch.sh`, `meetings_fetch.sh`, `notify.sh`, `triage_fetch.sh` (core); `jira_fetch.sh` (handoffs), `watch_fetch.sh` (intraday), `rca_file.sh` (telemetry).

**No session outside a runner.** No script starts a `claude` session except the three runners: `lib_connector.sh` (Sources), `run_headless.sh` (Compile runs), `vaultlib/nightshift_session.py` (Work Orders). `lib_confine.sh` (`claude mcp list`), `smoke_check.sh` (`--version`) and `nightshift_run.py` (`auth status`) call the binary for no session and are listed as such. Without this check a new fetch that runs `claude -p` itself would not count as a Source and would skip every rule below. The match is a pattern on code lines (the binary or `CLAUDE_BIN`/`claude_bin` with `-p`); the exact pattern is the builder's.

**Every Source:**
1. sources `lib_fetch.sh` (after `lib_connector.sh`);
2. has a checker that uses the shared walker. The checker is the program the script feeds the session's stream to (`< "$work/out.jsonl"` with `2> "$work/check.err"`, the pair `connector_outcome` reads). That program, or a module it imports directly from its own feature (a `vaultlib/<name>.py`, or a module in the same extension's `scripts/` tree), calls `walk(` or `check_stream(`. Imports through `vaultlib.api` and `vaultlib/connector.py` itself do not count, since every extension script imports the API. Today: `calendar_tsv.py`, `meetings_extract.py`, `notify.py` (via `vaultlib/notify.py`), `triage.py` (via `vaultlib/triage.py`), `jira_handoffs.py`, `watch.py` (via `watchlib/check.py`), `rca.py` (via `telemetrylib/rca.py`);
3. has a smoke row when its script accepts `--check`: a core Source in `smoke_check.sh` (a `connector <row> … <script> --check` line), an extension Source in its manifest's `smoke` list (`connector: true`, `run: "scripts/<script> --check"`). A core Source with `--check` and no row gives its reason in the table below. A Source without `--check` is a write session (today `rca_file.sh`, which files a ticket); F4's review skill checks that a new read Source has one;
4. has its alert tag: the script's `FETCH_TAG` is a key of `alerts.TAGS` (core) or an entry of its own manifest's `alert_tags` (extension, bare or `{tag: …}`). A core Source that sets no `FETCH_TAG` names its tag in the table;
5. has a unit: each of its session timeouts is summed under a unit by the timing rule (§3.4). This is how the brief carries `jira_fetch.sh` and the intake tick carries `rca_file.sh`, so no unit list is needed.

**The core table** (in `conformance.bats`; extension Sources are found from `extensions/*/scripts/` and checked against their manifest):

| Source | Smoke rows | Tag |
|---|---|---|
| `calendar_fetch.sh` | `calendar` | `calendar` (its `finish()` writes the line; no `FETCH_TAG`) |
| `meetings_fetch.sh` | `meetings` | `FETCH_TAG` |
| `triage_fetch.sh` | `triage`, `triage_chat` | `FETCH_TAG` |
| `notify.sh` | none: its `--check` posts a message to the channel | `FETCH_TAG` |

A core Source missing from the table fails, and so does a table row with no script.

### 3.2 Part homes replace the copy allowlist

`COPIES_ALLOWED` becomes `PART_HOMES`, same format and same `copies()` scan. Every line is a design fact, so the comment drops "may only shrink" and says a new line needs the owner's review with its reason. The "listed but no longer found" check stays. Each current entry, decided:

| Entry | Decision |
|---|---|
| `walker vaultlib/connector.py`, `fail-class vaultlib/connector.py` | home (F1 §3.1) |
| `helper lib_fetch.sh:logline`, `:alert_once`, `:fail`, `:skip` | home (F1 §3.2) |
| `stub system/tests/stub_claude_connector` | home (F1 §3.4) |
| `walker vaultlib/nightshift_session.py` | other shape: a Work Order session has many tools and no single connector; the program plan gives Work Orders a blueprint and no refactor until a defect shows the need |
| `stub system/tests/stub_claude`, `stub_claude_nightshift` | other shapes: the headless and Work Order stubs |
| `helper vault_sync.sh:fail` | other shape: `fail <step> <reason>` for a sync step, no fetch exit. Renaming it would touch the sync script for no behaviour |
| `config` × 5 | gone: folded into one reader (§3.3) |

The `config` kind's scan changes from the name `^def config\(` (three readers already dodge it as `_config`) to any `.py` under `system/scripts/` or `extensions/*/scripts/` with a path literal ending in `config.md` (the name followed by its closing quote, so prose such as `jira_handoffs.py`'s docstring passes). Its homes: `vaultlib/config.py` (the reader) and `vaultlib/extensions.py` (`enable` edits the `extensions:` line as text). A path built at run time passes; F4's review skill covers that.

### 3.3 One config reader

New `system/scripts/vaultlib/config.py`, lifted from the copies:
- `config(vault) -> dict`: the frontmatter of `<vault>/system/config.md`; `{}` when the file is missing or unreadable (`OSError`, `UnicodeDecodeError`). `frontmatter.parse` never raises, so malformed YAML is `{}` too.
- `text(vault, key, default) -> str`: the value when it is a non-empty string, else the default (today's `Intake.config` and `commit_runs.config`).

Every core Python reader moves onto it (owner decides the scope, §7 item 2; this spec is written for all of them):

| File | Today |
|---|---|
| `alert.py`, `commit_runs.py`, `vaultlib/nightshift_check.py`, `vaultlib/notify.py`, `vaultlib/triage.py` | `def config(` (the five #308 names) |
| `meeting_actions.py`, `vaultlib/meeting_prep.py`, `vaultlib/sources.py` | `def _config(` |
| `away.py`, `vaultlib/meetings.py`, `vaultlib/recall.py` (two), `vaultlib/extensions.py` (`listed`, `migrate`), `vaultlib/intake.py` (`Intake.config`) | inline parse |

Public names keep their signatures and delegate: `Intake.config(key, default)` (extensions call it), and `vaultlib.api.config`, whose import moves from `.triage` to `.config`. `nightshift_check._fm` stays for codebase notes. The shell already reads through `lib_config.sh` and `vault_index.py field`.

One behaviour changes: `triage`, `notify` and `nightshift_check` raised on a config file that exists and cannot be read; they now get `{}` and their defaults, like the other readers. Nothing in the template writes a non-UTF-8 config.

### 3.4 The timing rule

**The overrun list stays for #299.** `TIMING_OVERRUNS` keeps its five lines, each naming #299, and F3 does not wait for #299. `intake` (an unbounded `flock 9` in `run_headless.sh`, five headless runs) and `smoke` (120 s more per telemetry source) need design work that #299 owns on the safety track, where the owner merges. The other three (`watch`, `smoke/calendar`, `smoke/watch`) are the server listings F0's table found; they are not in #299's body, so the PR adds them to its checklist. The existing check ("fits now; delete its known-overrun line") empties the list as #299 lands; the last deletion removes the variable and its loop. Any new overrun fails today.

**Extension budgets move into the manifest.** Today `TIMING_VALUES` and `TIMING_STEPS` name extension script paths and regexes (`jira_fetch.sh`, `watch_fetch.sh`, `watchlib/calendar.py`, `watch.py`, `rca_file.sh`, the three manifests). They move to one new manifest field (`FIELDS` gains `budget`; the contract stays 1):

```yaml
budget:
  values: {WATCH_SLACK_TIMEOUT: 420, WATCH_MAIL_TIMEOUT: 480, MAX_FETCH_DAYS: 2, ROUTE_LOCK_WAIT: 120}
  steps:
    - "watch 2 grace.listing listing"
    - "watch 1 grace.connector WATCH_SLACK_TIMEOUT"
```

- `values`: name to number. The test finds each name's default in the extension's `scripts/` tree as `${NAME:-N}` (bash) or `NAME = N` (Python), exactly once, and fails when N differs. A literal in neither form becomes a named constant (today `watch.py`'s `intake.lock("run.lock", timeout=120)` becomes `ROUTE_LOCK_WAIT`).
- `steps`: `TIMING_STEPS` syntax. A key is one of the extension's `values` or a core `TIMING_VALUES` key (`listing`, `calendar`, `grace.*`). The unit is a template unit (its own or a core one, as handoffs adds two steps to `brief`), `smoke/<row>` for its smoke rows, or `tick`: the extension's own tick, whose limit is its `tick.timeout`. Telemetry's `rca_file.sh` sessions become `tick PER_TICK grace.listing listing` and `tick PER_TICK grace.connector RCA_TIMEOUT` (3 × 345 s against 1,900), summed for the first time.
- `out`: an optional reason the extension's own units run no session, which takes them out of the sum. It replaces core's `TIMING_OUT` entry for `foundry-telemetry` (`out: "the HTTP poller: no session, each call has its own 60 s limit"`); `TIMING_OUT` keeps `foundry-nightshift`.
- Summed without a step line, from fields the manifest already has: each `tick` adds `intake 1 - <its timeout>`; each `smoke` row adds `smoke 1 - <its timeout>` (2 for an `each` row, as today) and is the limit of `smoke/<row>`.

Core's `TIMING_VALUES` and `TIMING_STEPS` keep only core lines. The check that every session default has a value line now also requires a step: a Source session no unit sums fails (rule 5 of §3.1).

### 3.5 The budget counts hooks and commands

The line count in `vault_integrity.bats` becomes `git ls-files -z system/scripts system/hooks .claude/commands | xargs -0 cat | wc -l`, and the cap comes back at a measured value (the owner removed it for F1 and F2 in #328; the test comment says it returns at a measured value once F1 is done). Measured at `fd59bc5`: `system/scripts` 14,128, `system/hooks` 372, `.claude/commands` 406, total 14,906. `.githooks/pre-commit` (90) is not named by D5 and stays out. The cap is the owner's (§7 item 1). `vault_integrity.bats` is every vault's gate, and a vault adds its own commands and hooks, so the cap assertion skips when `system/config.md` exists (as `conformance.bats` does); the count is still printed there. The #122 tightening sweep lowers it later; each raise keeps its dated comment line.

### 3.6 "Config keys match the schema" is moot

F2 (#350, #352) states each extension's config keys once, in its `schemas/config.md`, and the loader reads them from there. There is no second copy to compare, so F3 adds no rule for it.

## 4. Pull requests

1. **One config reader and part homes** (§3.2, §3.3; the owner merges). `vaultlib/config.py`, the readers moved onto it, `api.py`'s import, `COPIES_ALLOWED` to `PART_HOMES` with the `config` scan widened. Core lines go down; the PR prints the count.
2. **Source rule, timing in manifests, budget scope** (§3.1, §3.4, §3.5; auto-merge). The Source rule and its table, the `budget` field in `FIELDS` and the three template manifests, `watch.py`'s named lock wait, the extension lines out of the timing tables, the budget count and cap, FOUNDRY.md's D5 row and a `budget` sentence beside the other manifest parts (its Intraday paragraph), a checklist line on #299 for the three listing overruns. Core lines: about +5 (the loader key, the constant) plus the 778 lines of hooks and commands the count now includes.

PR 2 rebases on PR 1 (both edit `conformance.bats`). CHANGELOG line in each.

## 5. Tests

Each rule is a function over a root directory, as `pipeline_problems` is, run once on the repository and once on a fixture tree with one seeded violation per case. Bats ruling R1 holds: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions; a fixture case asserts the exact problem lines, as the pipeline fixture test does.

| Rule | Seeded violation |
|---|---|
| No session outside a runner | a fixture script that runs `claude -p` |
| Source parts | a Source that does not source `lib_fetch.sh`; a checker with no `walk(`/`check_stream(` in it or its feature module; a core Source missing from the table; a table row with no script |
| Smoke row | an extension Source with `--check` and no manifest smoke row; a core Source with `--check`, no row and no reason |
| Alert tag | an extension `FETCH_TAG` missing from its `alert_tags`; a core one missing from `alerts.TAGS` |
| Part homes | a `.py` with its own `tool_result` loop; a second `.py` naming `config.md` |
| Timing | a manifest `values` number that differs from the script default; a Source session with no step; a `tick` budget over its timeout |
| Budget | a fixture tree whose `system/hooks` takes the count over the cap; the same tree with a `system/config.md` skips the cap |

PR bodies show each new test's red run on its seeded case before the green run. The config reader gets one pytest: missing, non-UTF-8 and malformed-frontmatter files give `{}`; `text()` returns the default for a missing, empty or non-string value.

## 6. Settled while specifying (my calls)

From the builder check:
- **PR 1's lane.** It changes `alert.py`, `Intake.config` and `nightshift_check.py` (the Work Order add-time screen), surfaces the owner merges, so PR 1 is owner-merged and PR 2 stays auto. The screen's new behaviour fails closed: with `{}`, a template order is refused for "config has no template_remote", and the workspace default is outside the vault.
- **An extension unit with no sessions** says so with `budget.out` (§3.4), so no extension unit name stays in the core test and F4's `new-source` never edits core for one.
- **The cap in a vault** skips (§3.5); the template is what the cap guards.
- **The `config.md` scan** matches path literals only (§3.2).

Made while specifying: write sessions owe no smoke row (§3.1 rule 3); `vault_sync.sh:fail` keeps its name (§3.2); F3 does not wait for #299 and adds the three listing overruns to its checklist (§3.4); the `budget` field's shape, the `tick` unit and the named lock wait (§3.4); the reader returns `{}` on an unreadable file (§3.3); `.githooks/pre-commit` stays out of the count (§3.5).

## 7. Owner decisions

1. **The cap.** Recommended: the count at PR 2's merge over `system/scripts`, `system/hooks` and `.claude/commands`, rounded up to the next 50 (14,950 at `fd59bc5`; PR 1 lowers the count a little).
2. **Reader scope.** #308 names the five `def config(` copies. Recommended: all 13 core readers in §3.3, since a rule keyed on the name `def config(` already misses three `_config` copies and the inline reads, and each move is a line or two deleted.

## 8. Left to the builder

Bats or pytest for each rule (the import walk of §3.1 rule 2 reads naturally in Python with `ast`); the session pattern of §3.1; how the test reads manifests (the loader or `yamlload`); the names inside `vaultlib/config.py` beyond keeping `vaultlib.api.config`.

## 9. Out of scope

#299's fixes (the overrun list empties as it lands); the core manifest; `calendar_fetch.sh` writing its `[calendar]` line with `printf` (no once-a-day rule, and the watch runs it every 30 minutes): a fix-lane item; `.githooks/pre-commit` in the budget; rules for Pollers (telemetry's HTTP fetch), Compile runs and Work Orders.

## 10. Risks

1. **Pattern rules read literal code.** A session started through a computed binary name, or a config path built at run time, passes. F4's review skill checks diffs for both.
2. **A vault's own extension is not checked.** `conformance.bats` skips in a vault, so a vault-only extension needs no `budget` field and is never failed for lacking one; the loader accepts a manifest without it.
3. **One template update carries both sides.** A vault that edited a template manifest gets a merge conflict on the new `budget` field, and the update aborts on conflict (F2 risk 4).
