# F4: the line's skills (`new-source`, `foundry-review`)

**Date:** 2026-10-23
**Status:** approved and built (#359, #360, #362; connector-probe and live-acceptance still open on #309)
**Program:** `docs/superpowers/2026-10-21-factory-plan.md` (phase F4, #309)
**Grill:** 2026-10-21, recorded in the program plan's `## Grill` section: item 4 set F4's order (`new-source` and `foundry-review` first, with the spec template's blueprint checklist; `connector-probe` and `live-acceptance` after the first new feature built on the line). The factory is the owner's idea, approved with #304.
**Builder check:** 2026-10-22, three questions, all settled as my calls in §6: the scaffold test once the brief is full, `changelog-label` in a vault, the acceptance run's tool and stopping point (plus the name rule, tightened). The owner settled two deviations from the plan's wording (§7).
**Blueprint:** none: two development skills and their scripts; `new-source` writes the Source shape for later features.
**Lane:** small feature, two PRs (task list in §4, no separate plan). Both auto-merge on green CI (program plan §1 table); neither changes a safety surface, an existing Source's confinement or the Work Order runner.

## 1. Why

F1 to F3 built the parts and made CI reject a Source that lacks them. Two gaps remain from the development pattern survey's "by hand per feature" list. A new Source is still assembled by hand: fetch script, checker, manifest rows, budget, alert tag, deny list, stub tests. F3's rules then reject what was missed, one CI run at a time. And some defect classes have no test that can hold them, because the defect is a judgment about a line of code (is this text from outside? is this `sleep` ordering two processes?). The survey counted a "final review fixes" commit on most feature PRs, and C1 and C2 were found only in live use.

F4 gives the line its first two stations: `new-source` writes a Source that passes the line before any feature code exists, and `foundry-review` checks a diff for the classes a test cannot catch before the pull request opens.

## 2. Goals, non-goals, anti-goals

- **Goals:** a Source scaffolded by one command passes `conformance.bats`, `test_source_rule.py`, `extensions.py check` and its own suites with no other file edited; a review that flags a seeded violation for each of its checks; a spec rule that names the parts and defect classes a feature's shape brings; each held by a CI test.
- **Non-goals:** `connector-probe` and `live-acceptance` (deferred, §3.5); a core Source scaffold (§3.2); a unit or tick runner for the scaffold (§3.2); the Work Order runner running the review (§7); changing any part, rule or runtime script.
- **Anti-goals:** a review check that blocks CI (its hits are candidates a reviewer rules on; a check precise enough to block belongs in a test); a scaffold that writes feature code it has to guess (the call's arguments and the parse are the feature's); a second copy of the blueprint parts list beside FOUNDRY.md's.

## 3. Decisions

### 3.1 Where the skills live

`.claude/skills/new-source/` and `.claude/skills/foundry-review/`, tracked in the template as `order` is. Every vault receives them through `update_template.sh`'s merge (owner, 2026-10-21: "development skills ship in the template's `.claude/skills/`"). In a vault, `new-source` builds a vault-only extension (the live vault has one) and `foundry-review` checks the vault's own diffs; both work there, with one vault branch each (no CHANGELOG line, and no CHANGELOG check), and `conformance.bats` skips there as it does today.

Each skill is a `SKILL.md` written with `superpowers:writing-skills` and one Python script beside it (stdlib only, run as `python3 .claude/skills/<skill>/<script>`). The scripts sit in the skill folder, outside the core budget's count (`system/scripts`, `system/hooks`, `.claude/commands`): they are development tools that no unit, hook or command runs, and the budget measures the runtime core (P9). The tests live in `system/tests/python/`, where the gate runs them. FOUNDRY.md's layout block names both skills (its `manual_drift` test requires `` `/new-source` `` and `` `/foundry-review` ``).

### 3.2 `new-source`

**Extension Sources only.** Core's Source parts are hand-kept lists since the grill cut the core manifest: the `CORE` table in `test_source_rule.py`, the `connector` rows in `smoke_check.sh`, `alerts.TAGS`, `TIMING_VALUES` and `TIMING_STEPS` in `conformance.bats`, and `install_units.sh`. A core Source cannot pass CI without editing five core files, and P9 puts new features in extensions. The skill says so and stops when asked for a core Source.

**The command:** `python3 .claude/skills/new-source/new_source.py <name> --tool <mcp__server__tool> --server "<server as claude mcp list names it>" (--tools <ARRAY> | --server-tool <tool>…) --description "<one line>" --credential "<what to renew>" --renew "<how>" [--issue <n>]`. It writes `extensions/<name>/` from the template folder `.claude/skills/new-source/template/` and, in the template repository, one CHANGELOG line. It exits 2 with a reason, writing nothing, when the name is not `[a-z][a-z0-9_]*` (the loader also allows `-`, which cannot appear in `<NAME>_TIMEOUT` or a `FETCH_TAG`), `extensions/<name>/` exists, or `<name>` is a core alert tag or another extension's tag. `--tools` names one of `lib_fetch.sh`'s server tables (`GMAIL_TOOLS`, `SLACK_TOOLS`, `DRIVE_TOOLS`, `CALENDAR_TOOLS`); for any other server, `--server-tool` lists the server's full tool table and the fetch script holds it, as handoffs holds Atlassian's (core's `lib_fetch.sh` names no vendor, F1 §2 decision 7). The skill tells the agent to read that table from its own session's tool list (every connected server's tools are listed there) until `connector-probe` exists.

**What it writes.** The template is the handoffs extension with its Jira query and brief list taken out:

| File | From | Parts |
|---|---|---|
| `extension.md` | handoffs' manifest | `sources` row; one `smoke` row (`timeout: 360`, `connector: true`, `run: "scripts/<name>_fetch.sh --check"`); `brief: true`; `units: []`; `alert_tags: [<name>]`; one `allow` rule for `--check`; `budget` with `values: {<NAME>_TIMEOUT: 300}` and four steps (`brief` and `smoke/<name>`, each a listing and a connector session). Body: the `/setup` steps and the exit table, as handoffs' |
| `scripts/<name>_fetch.sh` | `jira_fetch.sh` | sources `lib_config.sh`, `lib_confine.sh`, `lib_connector.sh`, `lib_fetch.sh`; `fetch_check_arg`, `fetch_workdir`, `fetch_others`, `connector_run`, `connector_outcome`, `fail`, `logline`; `FETCH_TAG=<name>`; `CONNECTOR_TIMEOUT="${<NAME>_TIMEOUT:-300}"`; the ToolSearch preamble (F1 §6 left its nine copies to this scaffold) |
| `scripts/<name>_check.py` | `jira_handoffs.py` | imports only `vaultlib.api`; `args` prints the one call's input as JSON, which the fetch puts in the prompt; `extract` reads the stream with `check_stream`, whose `accept` takes only that input, then passes the pages to `lines(pages)` |
| `brief/prep.sh`, `brief/section.md` | handoffs' | the brief runs the fetch and writes `sections/<name>.md`; a failure is an unavailable input and a `failed` reading on the Sources line |
| `tests/<name>.bats` | `handoffs.bats` | §5 |

The call's input (`ARGS`) and `lines()` are the feature's code. The scaffold writes `ARGS = {}` and a `lines()` that returns no lines, so a half-built Source writes an empty brief section and never puts unparsed outside text in the brief. `extract` calls `check_stream` without `persisted`, so a result too large for the model fails with exit 6; a feature that reads the whole `structuredContent` passes `persisted` as handoffs does, with its own test.

**The runner is the brief, as in handoffs.** The plan's `new-source` bullet says "unit files"; the template it names has none and runs inside the brief, and a unit or tick runner would be invented before any feature asked for one (program order rule 3). The timing rule sums the new session under `brief`: today 3,150 s of 3,600 s, so a scaffolded Source at the default 300 s brings it to 3,495 s. One more brief Source fits; the next fails the timing rule in CI and needs its own unit, which waits for the feature that needs it (§10 risk 1).

**The tests it writes are green.** The plan's "failing tests for exits 1, 3, 6, 7 and too-large" are tests of the failure exits. On the bare scaffold they pass, because the shared parts give those exits (`check_stream`, `fail`, `connector_outcome`); a red test in the scaffold would fail CI, which the done-when forbids. The feature's own tests (its arguments, its parse, its lines) are written red first after scaffolding, with `superpowers:test-driven-development`.

**The CHANGELOG line** goes under today's date in **Changes**: `- Added: <description>. (#<issue>)`. `--issue` is required in the template repository and the line is skipped in a vault (a vault's CHANGELOG is the template's, and a vault line would conflict on every update).

**The skill's steps:** refuse a core Source; gather the inputs (the tool's full name, the server's tool table, the issue); run the script; run `system/scripts/test.sh` on `system/tests/conformance.bats`, `system/tests/python/test_source_rule.py` and `extensions/<name>/tests/<name>.bats`, all green before any feature code; then probe the tool once (FOUNDRY.md "Probe first", until `connector-probe` exists), write the feature's tests red, fill `ARGS`, `lines()` and the prompt's task sentence, and set the budget value if the timeout changes; then `/foundry-review` before the pull request.

### 3.3 `foundry-review`

**When:** after `superpowers:requesting-code-review` and its fixes, before `gh pr create`. FOUNDRY.md's Development table already names it at the Review station.

**The script:** `python3 .claude/skills/foundry-review/review_diff.py [--base <ref>]` reads `git diff -U0 <merge-base>..HEAD` (base default: the merge base with `origin/master`), runs each check on the added lines, and prints one `<check>: <path>:<line>: <text>` line per hit, then one `<check>: pass` line per check with none. Exit 0 no hits, 1 hits, 2 could not run (no git, an unknown base). It never runs in CI as a gate.

**The skill:** for each hit, read the hunk and either fix it or keep it with a one-line reason. The PR body gets a `## Foundry review` section with one line per check: `pass`, `fixed: <path:line>` or `kept: <path:line>: <reason>`. A fix branch passes its `defect:<class>` label to `gh pr create --label`.

**The checks.** Each flags candidates on added lines only. The seed is the line shape of a named past defect (FOUNDRY.md working rule: seed from the hazard), and the near miss is a line that must pass.

| Check | Class | Flags | Seed | Near miss |
|---|---|---|---|---|
| `now-redaction` | C7 | a Now or Slack writer (`now.add(`, `now.py add`, a `notify` post) in a file that calls neither `redact_credentials(` nor `redact(` | #288: a chat statement passed through `one_line` only, then to `now.add` | the same file calling `redact_credentials(` on the statement |
| `gate-escape` | C14 | a write (`write_text`, `open(…, "w"`/`"a"`, `>`/`>>`, `tee`, `cp`, `mv`, `os.replace`) on a line naming `wiki/` or `briefings/`, outside `vaultlib/publish.py` and `vaultlib/now.py`; an added `Edit(`/`Write(` allow rule on those paths in a settings file | D1: an `Edit(/wiki/**)` allow rule; a script writing `wiki/<p>/x.md` directly | a `read_text` of a wiki path |
| `alert-text` | C5, C7 | an alert line or failure reason (`alert_once`, `alert.py`, `fail`, `raise Fail(`, an append to `alerts_*.md`) that interpolates a value other than an exit code, a count or the runner's own reason variables | #288: a `[watch]` notice carrying chat text | `fail 7 "$CONNECTOR_REASON"`; a count |
| `sleep-race` | C6, C10 | `sleep` or `time.sleep(` added in a test file, except a stub's timeout knob (`STUB_SLEEP=`) | #247: overlap proved by sleeps, replaced with barriers | `STUB_SLEEP=3 X_TIMEOUT=1 run …` |
| `skip-reason` | C10 | a bats `skip` with no reason; a pytest `skip(`, `mark.skip` or `skipif(` with no `reason`; a fetch script's `skip` with no reason | #199: a missing environment skips with `environment:` | `skip "environment: no bwrap"` |
| `changelog-label` | C13, C12 | the diff changes a vault-visible path (`system/scripts`, `system/hooks`, `system/systemd`, `system/schemas`, `.claude/commands`, `.claude/skills`, `CLAUDE.md`, `extensions/*` outside `tests/`) and adds no `- … (#N)` line to `CHANGELOG.md` (skipped in a vault, where `system/config.md` exists: a vault adds no CHANGELOG line, §3.2); on a `fix/` branch, a line asking for one `defect:` label (C1 to C14) | FOUNDRY.md Release notes; the fast lane's label | a docs- or tests-only diff; a diff with its line |
| `read-source-check` | C4 | a new script that calls `connector_run` and accepts no `--check` (F3 §3.1 rule 3 left this to F4) | a new read fetch without `fetch_check_arg` | `rca_file.sh`'s shape kept with its reason (a write session) |
| `computed-session` | C4 | `-p` or `--print` passed to a command named by a variable or a built string, outside the three runners (F3 §10 risk 1) | `"$tool" -p "$prompt"` | `"${CLAUDE_BIN:-claude}" -p` (F3's rule already fails it) |
| `computed-config` | part home | a `.py` line that builds a path ending in `config.md` from parts (`"config" + ".md"`, an f-string, `with_suffix(".md")`), outside `vaultlib/config.py` (F3 §3.2 left this to F4) | `root / "system" / ("config" + ".md")` | `from vaultlib.api import config` |

The last three are F3's hand-offs: its pattern rules read literal code, and its spec named F4's review as the check for what they miss.

### 3.4 The blueprint checklist

The plan puts the checklist in "the spec template (brainstorming output)". The brainstorming skill is the superpowers plugin's and the Foundry does not edit it, so the rule goes where the Foundry's other spec rules are: FOUNDRY.md Development, held by the pipeline test.

- **The parts** stay in FOUNDRY.md Architecture's Blueprints list, the one copy. Each shape's line already names its parts.
- **New in Development:** a table of the defect classes C1 to C14, each with what holds it: a CI test by name, a `foundry-review` check, or "prose only". It is built from the tree at PR time; §3.3's check column and these known gates seed it: C1 `too_large` and the scaffold's exit-6 test; C3 the timing rule; C4 the Source rule; C8 the forbidden-names and core-clean tests; C9 `extensions.py check` and `test_extension_api.py`; C13 `merge=union` and the duplicate-heading test; C14 the publish gate's tests. A class held by nothing says so.
- **The rule:** a spec whose `**Blueprint:**` names a shape has a `## Blueprint checklist` section: each part of that shape marked `uses` or `n/a: <why>`, then each defect class the change can reopen with what holds it.
- **The test:** `pipeline_problems` fails a spec dated `CHECKLIST_SINCE` or later whose Blueprint names a shape and that has no `## Blueprint checklist` line. Heading only (FOUNDRY.md "docs tests check names"). `CHECKLIST_SINCE` is PR 2's merge date, so F1's spec (`**Blueprint:** Source`, dated 2026-10-21) stays grandfathered, as `PIPELINE_SINCE` grandfathers older specs.

### 3.5 Deferred

`connector-probe` (a real `connector_run` from `.scratch` that records a tool's stream shape and size, C1 and C4) and `live-acceptance` (`--check` in a scratch vault, then a read-only log audit 24 h after the server updates) come after the first new feature is built on the line, so they are written from a real use (grill item 4). The program plan's F4 checklist keeps both lines open; #309 stays open for them.

## 4. Pull requests

Independent; they build in parallel, and the second to merge rebases (both edit FOUNDRY.md's layout block and CHANGELOG.md, which merges by union).

1. **`new-source`** (auto-merge). `.claude/skills/new-source/` (`SKILL.md`, `new_source.py`, `template/`), `system/tests/python/test_new_source.py`, FOUNDRY.md's layout line, CHANGELOG line.
   - Task 1: the template folder from handoffs, and `new_source.py` with its usage exits.
   - Task 2: `test_new_source.py` (§5), red before Task 1's script exists.
   - Task 3: `SKILL.md` with `superpowers:writing-skills`; FOUNDRY.md; CHANGELOG.
   - Task 4: the acceptance run (§5).
2. **`foundry-review` and the checklist** (auto-merge). `.claude/skills/foundry-review/` (`SKILL.md`, `review_diff.py`), `system/tests/python/test_foundry_review.py`, `conformance.bats`'s checklist rule and fixture cases, FOUNDRY.md (layout line, the Review row's "once F4 ships" removed, the checklist rule and the classes table), CHANGELOG line.
   - Task 1: `test_foundry_review.py`, each seed and near miss red first.
   - Task 2: `review_diff.py`.
   - Task 3: the checklist rule in `pipeline_problems`, with its fixture cases.
   - Task 4: `SKILL.md`; FOUNDRY.md; CHANGELOG.

Core lines: none. Neither PR changes `system/scripts`, `system/hooks` or `.claude/commands`.

## 5. Tests

Both test files skip when `system/config.md` exists, as their neighbours do. Bats ruling R1 holds for the bats files the PRs touch and the one the scaffold writes: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.

**`test_new_source.py`** copies the tracked tree into a temporary git repository (`test_source_rule.tree`), runs `new_source.py demo_src` there for a server with a `lib_fetch.sh` table and once for one with `--server-tool`, and asserts:
1. `git status --porcelain` shows only `extensions/demo_src/` and `CHANGELOG.md`: no hand wiring;
2. `source_problems(root)` and `session_problems(root)` are empty;
3. the copy's `conformance.bats` passes its part-homes and pipeline tests, and `timing_problems` on the copy gives the same problem lines as on the tree before scaffolding, with one exception: a `brief` overrun, which the test prints by name and lets pass. Once a real brief Source fills the brief, the scaffold still proves its parts, and the overrun is left to the next feature's own CI run (§10 risk 1);
4. with `demo_src` enabled in a config, `extensions.py check` prints nothing, and the copy's `extensions/demo_src/tests/demo_src.bats` passes;
5. each usage error exits 2 and writes nothing: an existing extension, a core tag (`calendar`), a bad name, a missing `--issue` in the template.

**The scaffold's own bats** (through the fetch script with `stub_claude_connector`, as `handoffs.bats`): a good session exits 0 with the confined argv (the one allowed tool; the server's other tools and `Bash` denied; other servers denied); `--check` prints its count line; exit 1 for an error result message; exit 3 when no ToolSearch result names the tool; exit 6 for an error tool result; exit 6 for a `<persisted-output>` result; exit 7 for another tool and for other arguments, with one alert a day; the manifest loads with its smoke and allow lines; the brief section is written on success and is empty with a `failed` reading on a failed fetch.

**`test_foundry_review.py`** builds a small git repository per case: a base commit, then one commit with the seed. For each check, the seed is flagged with the expected `<check>: <path>:<line>` line and exit 1, and the near miss gives `<check>: pass`. A clean diff exits 0; an unknown base exits 2; with a `system/config.md` in the repository, a script change with no CHANGELOG line passes `changelog-label`.

**The checklist fixture** (in `conformance.bats`'s existing pipeline fixture test): a spec dated `CHECKLIST_SINCE` with `**Blueprint:** Source` and no `## Blueprint checklist` fails; the same with the section passes; one with `**Blueprint:** none: …` passes; one dated the day before passes.

**Acceptance (done-when, PR 1 Task 4):** in a worktree under `.scratch`, an agent given only "add a Source for <a read tool on a server with a `lib_fetch.sh` table>" runs `/new-source`, stops once the three suites are green (no probe, no feature code, no live session), commits the scaffold on a throwaway branch and pushes it; both CI jobs (`gate`, `gate-all-extensions`) pass on that push with nothing edited by hand. The PR body links the run; the branch is deleted after and never merged. `foundry-review`'s half of the done-when is `test_foundry_review.py` in CI.

## 6. Settled while specifying (my calls)

- **Extension only** (§3.2): core's parts are hand-kept lists, so a core Source cannot pass CI unwired.
- **The brief runner only** (§3.2), with the brief's remaining room stated.
- **"Failing tests" means tests of the failure exits**, green on the bare scaffold (§3.2).
- **Too large fails by default** (no `persisted`); a feature opts in with its own test (§3.2).
- **No config keys in the scaffold**: the extension being listed is the switch; a feature adds `schemas/config.md` when it needs a setting. Handoffs' `handoffs_projects` off-switch is feature code.
- **No `tests/python/` in the scaffold**: an empty pytest folder collects no tests; the feature adds it with its parse tests.
- **Scripts in the skill folders**, outside the core budget (§3.1).
- **The CHANGELOG line takes the issue number** (`--issue`), as F3's lines did (#308), since the PR number does not exist when the scaffold runs; skipped in a vault.
- **The review never gates CI**, and its hits are candidates (§2 anti-goals).
- **Three of the nine checks are F3's hand-offs** (§3.3).
- **The checklist's parts stay in FOUNDRY.md Architecture**; Development gains the classes table and the rule; the test checks the heading (§3.4).
- **Labels:** the repository has fourteen `defect:` labels (C14, gate escape, came after the plan's C1 to C13); the review names all fourteen.
- **Throwaway branch** pushed for the acceptance and deleted after, never a PR.

From the builder check:
- **The scaffold test once the brief is full** (§5 item 3): it compares timing problems before and after scaffolding and lets a `brief` overrun pass by name, so the first real brief Source does not turn F4's own test red. The template keeps its 300 s default; a smaller one would hide the limit from the feature that hits it.
- **`changelog-label` in a vault** skips its CHANGELOG half, matching `new_source.py` (§3.3); a test case covers it.
- **The acceptance run** uses a server with a `lib_fetch.sh` table and stops at green suites, with no live session; `test_new_source.py`'s second scaffold covers `--server-tool` (§5).
- **The name rule** is `[a-z][a-z0-9_]*`, and the checker is `<name>_check.py`, so no name shadows a stdlib module (`email`, `json`) on the checker's import path.

## 7. Owner decisions

Answered by the owner on 2026-10-23: the recommendation, for both. The spec as written stands.

1. **The runner: the brief only, or unit files too?** Owner: the brief only. The plan's `new-source` bullet says "unit files"; the template it names (handoffs) has none and runs in the brief. Recommendation: the brief only (§3.2). A unit runner is a second shape with no feature asking for it yet, and the first Source that cannot fit the brief adds it from a real use.
2. **Do Work Order pull requests run `foundry-review`?** Owner: not in F4. The plan says the review "runs before a PR opens"; a Work Order opens its pull request from the runner's sealed session, and changing its prompt is an owner-merge change to the runner. Recommendation: not in F4. The review runs in interactive and subagent builds; a Work Order PR's reviewer runs it on the branch, and the runner learns it when a Work Order PR ships a class the review would have caught.

## 8. Left to the builder

The template's placeholder syntax and how `new_source.py` fills it; `review_diff.py`'s patterns within each check's definition; the base ref fallback when `origin/master` is missing; how `test_new_source.py` runs the copy's bats and the extension's suite.

## 9. Out of scope

`connector-probe` and `live-acceptance` (§3.5); core Sources; unit and tick runners in the scaffold; the Work Order runner; Poller, Compile run and Work Order scaffolds; any change to the parts, rules or runtime scripts.

## 10. Risks

1. **The brief has room for one more Source.** 3,150 s of 3,600 s today; a second scaffolded brief Source fails the timing rule. That is the rule working; the feature that hits it adds a unit runner (and #299 may give room back). `test_new_source.py` tolerates that one overrun (§5) so the scaffold test stays green after the first brief Source merges.
2. **The smoke unit grows.** Each scaffolded smoke row adds its timeout to the smoke unit, already on the overrun list under #299; the list entry hides the growth until #299 lands.
3. **The template drifts from handoffs.** A change to `lib_fetch.sh`, `vaultlib.api` or the Source rule can break the template without touching handoffs. `test_new_source.py` runs the line on a fresh scaffold in every CI run, so drift fails the gate.
4. **Review patterns read literal code.** A writer reached through a helper, or a path built across lines, passes the script. The skill tells the reviewer the checks are a floor and to read every hunk that adds a writer, an alert or a test.
5. **Work Order PRs skip the review** until the runner runs it (§7).

## 11. Corrections from the build (#359, #360)

The sections above stand as approved. These changes came out of the build:
- **The name rule is `[a-z][a-z_]*`** (§3.2, §6), with no digits. Three core regexes read tags as `[a-z_]+` (the reason prefix in `lib_connector.sh`, alert routing in `alerts.py`, the tag scans in `scripts.bats`), and F4 changes no core.
- **The scaffold writes no `brief/section.md`** (§3.2 table). The brief prompt's 2,500-word cap had 5 words left. The feature writes its section prompt when it fills `lines()`, and `test_new_source.py` runs the word check on the scaffold. The first real brief Source raises the cap with a measured reason.
- **`new_source.py` refuses more than §3.2 lists:** empty values; quotes, backslashes, `$`, backticks or newlines in text; a malformed `--tool`, or a tool missing from its table; an existing `<name>_fetch.sh` or a core smoke row name; a CHANGELOG with no `## Changes` heading.
- **`foundry-review`:** the checks skip `.md` files outside `.claude/`, `now-redaction` also matches `nowmod.add/note/set_statement`, and `alert-text` reads only from the alert or failure call onward and allows exit-code names.
