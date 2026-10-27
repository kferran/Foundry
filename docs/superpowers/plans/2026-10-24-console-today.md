# Console C1: the Today Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `extensions/console/` serves the Today screen as drawn in the mockup, read-only, from the server over Tailscale and from Omarchy on `127.0.0.1`.

**Architecture:** One core change lets an extension declare an always-on unit (C1.1). The extension's Python adapter, `today.py`, gathers the scripts' JSON and the prep files into one object (C1.2). A Nuxt app built outside the vault serves the page and two GET routes; its server spawns `today.py` with an argument list (C1.3). Live acceptance and docs close it (C1.4).

**Tech Stack:** Python 3.11 stdlib, bash, bats, pytest; Node (LTS, pinned by mise), Nuxt 4, Vue 3, TanStack Vue Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-console-today-design.md`

## Global Constraints

- The Node side never opens a vault file, never runs a shell (`execFile` only) and takes no request input that reaches a command or a path. Every route is a GET.
- `today.py` imports only `vaultlib.api` (the F2 ban, `test_extension_api.py`). It runs core commands as subprocesses with argument lists, never imports their internals.
- Nitro binds `127.0.0.1`. With `console_auth: tailscale`, a request whose `Tailscale-User-Login` is not `console_login` gets 403, and an empty `console_login` refuses everything.
- No connector session, no write to the vault, no network call from `today.py` or the app.
- `node_modules`, `.nuxt` and `.output` never get committed; `build.sh` builds in `console_build_dir`.
- Template rule: no real names, ticket keys or sites in fixtures or docs (`Blake Sample`, `Alpha`, `ABC-123`, `owner@example.com`).
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- Core budget: C1.1 is the only core change. If it passes the `vault_integrity.bats` cap, raise the cap by the measured amount with the reason in the test's comment (owner approves at merge).
- Each PR: a change file in `changes/` (FOUNDRY.md, Release notes); `/foundry-review` before the PR; open as ready (FOUNDRY.md Development).
- Per-task suites: `system/scripts/test.sh system/tests/units.bats`, `system/scripts/test.sh system/tests/python/test_extensions.py`, `system/scripts/test.sh extensions/console/tests/test_today.py`, and in `extensions/console/app/`: `npx vitest run`, `npx nuxi build`.

## Review Focus

1. **The unit installer stays tight.** `timer: false` installs and enables only the `.service`; a timer unit on a client is still refused; a non-boolean `timer` is a loader reason; `--dry-run`, `--update` and `--uninstall` treat the new unit like the others. Task 1.
2. **`today.py` never fails the page whole.** Each failing source leaves its part empty and adds one `errors` line with the source and exit code; the exit stays 0. Task 3.
3. **No path from a request to a command.** `/api/today` takes no query; the spawn's arguments are constants. Task 5's tests pin it.
4. **The login check fails closed.** Missing header, a different login, and an empty `console_login` each get 403; `console_auth: none` passes; a non-local `NITRO_HOST` stops the server at start. Task 5.
5. **Partition walls on screen.** The work tab shows only `partitions.work`; switching tabs never merges the two lists. Task 6.

---

## PR C1.1: an always-on extension unit (core; the owner merges)

### Task 1: `timer: false` on a manifest unit

**Files:**
- Modify: `system/scripts/vaultlib/extensions.py` (validate `timer`; `units <role>` prints a third column, `timer` or `service`), `system/scripts/extensions.py` (usage text), `system/scripts/install_units.sh` (the extension block at `:121-134`: for a `service` unit add only `<unit>.service` and enable it; allow such units on `client`)
- Test: `system/tests/units.bats`, `system/tests/python/test_extensions.py`; the demo extension fixture gains a `timer: false` unit

**Interfaces:**
- `units <role>` prints `<ext>\t<unit>\t<timer|service>`. A `service` entry is listed for `client` when the entry's roles name it; a `timer` entry never is.
- `check` reports `units: timer must be true or false` for any other value.

- [ ] Step 1: failing tests: `install_units.sh --dry-run` on a fixture with a `timer: false` unit lists `foundry-demo-web.service` and no `.timer`, and enables the service; on `client` it lists only that unit; a `timer` unit listing `client` is not installed there; `extensions.py check` names a `timer: "yes"` entry; `--uninstall` removes the service.
- [ ] Step 2: run them, see them fail. Implement. Run `system/scripts/test.sh system/tests/units.bats` and `system/scripts/test.sh system/tests/python/test_extensions.py`.
- [ ] Step 3: FOUNDRY.md's extension manifest paragraph names `timer: false`; change file. Check the core cap. Commit; `/foundry-review`; PR.

---

## PR C1.2: the extension's Python side

### Task 2: manifest, config fragment, unit and build script

**Files:**
- Create: `extensions/console/extension.md` (name, contract 1, description, `units: [{name: foundry-console, roles: [standalone, server, client], timer: false}]`, `smoke`, `deps: [mise, node, rsync]`, `index_ignore: []`, the setup questions and the security statement in the body), `extensions/console/schemas/config.md` (the five keys of spec §5), `extensions/console/units/foundry-console.service.in`, `extensions/console/scripts/build.sh`, `.gitignore` lines for `extensions/console/app/{node_modules,.nuxt,.output}/`
- Test: `extensions/console/tests/console.bats`

- [ ] Step 1: failing tests: `extensions.py check` passes with `console` listed; `build.sh` with an unwritable `console_build_dir` exits 2 naming it; `build.sh` with a stub `mise`, `npm` and `npx` on PATH copies `app/` without `node_modules` and runs the three steps in order; the unit renders with `127.0.0.1` and the port.
- [ ] Step 2: run, see them fail, implement, run `system/scripts/test.sh extensions/console/tests/console.bats`. Commit.

### Task 3: `today.py --json` and `--check`

**Files:**
- Create: `extensions/console/scripts/today.py`
- Test: `extensions/console/tests/test_today.py` (a fixture vault: two Now pages, an ActiveProjects list with two projects, one queued and one finished Work Order, a prep folder with `calendar.tsv`, `actions.md`, `sources.md`, `quarantine.md`, an alerts file)

**Interfaces:**
- `today.py --json` prints spec §4's object; `today.py --check` prints `ok` or `failed: <class>: <reason>` (classes as `smoke_check.sh` uses) and exits 0 or 1.
- Matching (spec §8.4): `matches(project_name, statement) -> bool`, true for `[[Name]]` or the whole word, case-insensitive.

- [ ] Step 1: failing tests: `test_today_has_every_part_for_each_partition`; `test_tiles_count_from_the_parts`; `test_project_card_counts_now_lines_and_prs_by_match`; `test_today_list_is_first_next_per_project_at_most_five`; `test_a_failing_source_adds_one_error_and_exit_stays_zero` (stub `now.py` exiting 1); `test_missing_prep_files_leave_calendar_and_actions_empty`; `test_partitions_never_mix`; `test_check_reports_ok_and_failed`; `test_imports_only_vaultlib_api` (the ban covers it; assert the file passes).
- [ ] Step 2: run, see them fail, implement, run `system/scripts/test.sh extensions/console/tests/test_today.py` and `system/scripts/test.sh system/tests/python/test_extension_api.py`. Change file. Commit; `/foundry-review`; PR.

---

## PR C1.3: the Nuxt app

### Task 4: the app skeleton and CI job

**Files:**
- Create: `extensions/console/app/` (`package.json`, `package-lock.json`, `mise.toml` pinning Node LTS, `nuxt.config.ts` with `ssr: true` and `nitro.preset: node-server`, `app.vue`, `vitest.config.ts`)
- Modify: `.github/workflows/gate.yml` (a `console` job: checkout, `jdx/mise-action`, `npm ci`, `npx vitest run`, `npx nuxi build`, working directory `extensions/console/app`)

- [ ] Step 1: a trivial Vitest test passes locally; `npx nuxi build` succeeds. Confirm the Node version mise pins runs on bookworm (`mise install` on a bookworm container or the server) and record it in the PR body.
- [ ] Step 2: commit.

### Task 5: server routes and the login middleware

**Files:**
- Create: `extensions/console/app/server/middleware/auth.ts`, `server/api/health.get.ts`, `server/api/today.get.ts`, `server/utils/run.ts` (`execFile("python3", [vault + "/extensions/console/scripts/today.py", "--json"], {cwd: vault, timeout: 15000})`)
- Test: `extensions/console/app/tests/server/*.test.ts`

- [ ] Step 1: failing tests: 403 with no header, with another login, and with an empty `console_login`; 200 with the matching login; `console_auth: none` passes; start-up throws on `NITRO_HOST=0.0.0.0`; `/api/today` ignores any query string and calls `run` with constant arguments; a `today.py` timeout gives a 502 with `{"errors": ["today.py: timed out"]}`; `/api/health` returns `{"ok": true, "v": 1}`.
- [ ] Step 2: run, see them fail, implement, run `npx vitest run`. Commit.

### Task 6: the Today page

**Files:**
- Create: `extensions/console/app/pages/index.vue` and components for the header, tiles, focus cards, Today list, calendar, meeting actions, Now table (TanStack Vue Table for the filters), Work Orders and Pipeline; `composables/useToday.ts` (TanStack Vue Query, `refetchInterval: 60000`, `refetchIntervalInBackground: false`)
- Test: `extensions/console/app/tests/pages/*.test.ts` with fixture JSON from Task 3's test vault

- [ ] Step 1: failing tests: the page renders every mockup section from the fixture; the Work tab shows only work lines and Personal only personal; the Overdue filter shows only lines with a `band`; stale flags and "Also active" hide when the keys are absent; `errors` show in the strip; the Refresh button refetches; the stamps print.
- [ ] Step 2: run, see them fail, implement against the mockup's layout and colors (IBM Plex Sans and Mono, the mockup's tokens, wrap rules at phone width), run `npx vitest run` and `npx nuxi build`. Change file. Commit; `/foundry-review`; PR.

---

## PR C1.4: live acceptance and docs

### Task 7: live on both machines

- [ ] Server: set `console_login`, run `build.sh`, `install_units.sh`, `tailscale serve --bg --https=443 http://127.0.0.1:3110`; open the page from Omarchy and the phone over the tailnet; a request with another login (curl with a forged header from another tailnet device is not possible, so check the 403 with `curl -H 'Tailscale-User-Login: x@example.com' http://127.0.0.1:3110/api/today` on the server); `smoke_check.sh` prints `console: ok`.
- [ ] Omarchy: `console_auth: none`, `build.sh`, `install_units.sh`; the page on `http://127.0.0.1:3110`; the stamps show the synced prep.
- [ ] Record each check's result in the PR body.

### Task 8: docs

**Files:** `FOUNDRY.md` (an Extensions entry for the console: what it shows, the keys, the build and unit, the Tailscale line, the security list), a change file in `changes/`, `docs/superpowers/roadmap.md` (the console row), the program plan's phase table.

- [ ] Write them; run `system/scripts/test.sh system/tests/conformance.bats` and `system/scripts/test.sh system/tests/commands.bats`. Commit; PR.
