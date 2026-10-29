# Console C1.3: Feature-Sliced Design Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The console's Vue client (#392) follows `extensions/console/ARCHITECTURE.md`: Feature-Sliced Design layers, slices with public APIs, no Nuxt auto-imports, Steiger in CI. The Today screen looks and behaves exactly as it does now.

**Architecture:** The single `TodayView.vue` splits into `shared`, `entities`, `features`, `widgets` and `pages/today` under `app/`. Nuxt reads routes from `app/routes/`, and every import is explicit through a slice's `index.ts`. The server and the Python adapter keep their shape; the server's helper is renamed to the general `runAdapter` that ARCHITECTURE.md §3 names, and one test pins the adapter's output to the shared fixture.

**Tech Stack:** Nuxt 4.6, Vue 3.5, TanStack Vue Query 5, Vitest 5, happy-dom, Steiger 0.8 with `@feature-sliced/steiger-plugin` 0.8, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-console-today-design.md` (C1), with `extensions/console/ARCHITECTURE.md` (owner decision #377 Q12, 2026-10-24: FSD, Steiger in CI, auto-imports off, refactor in #392 before merge).

## Global Constraints

- **Behaviour unchanged.** Every assertion in today's `tests/today-view.test.ts` and `tests/server.test.ts` still holds after the move. Tests move beside the code they cover; none is deleted or weakened.
- **The layer rules hold.** A module imports only from layers below its own and from its own slice, and only through a slice's `index.ts`. Steiger reports nothing on `app/`.
- **No auto-imports.** `components: false`, `imports.autoImport: false`. The build fails when an import is missing, which is the point.
- **No new runtime dependency.** Steiger and its plugin are dev dependencies. `package-lock.json` changes only through `npm install`.
- The client still reads only `/api/today`; the server still runs only `today.py --json` with constant arguments; the Python side is unchanged except one new test.
- Template rule: fixtures use `Alpha`, `Beta`, `Blake Sample`, `ABC-123`, `owner@example.com`.
- Per-task check, in `extensions/console/app/`: `npx vitest run`, `npx steiger ./app`, `npx nuxi build`. In the vault root: `system/scripts/test.sh extensions/console/tests/python`.
- CHANGELOG line ending `(#392)`; `/foundry-review` before pushing.

## Review Focus

1. **No reach-arounds.** No import path names a file inside another slice (`@/entities/now-line/ui/NowLineRow.vue`); only `@/entities/now-line`. Steiger's `fsd/public-api` and `fsd/forbidden-imports` cover it; the reviewer spot-checks three widgets by hand.
2. **No same-layer imports.** No widget imports another widget, and no feature imports another feature. Shared needs move down a layer.
3. **Auto-imports really off.** A component used without an import fails `nuxi build`. Task 1 seeds that failure once and reverts it.
4. **Partition walls on screen.** The page passes one partition's object to every widget; no widget reads `data.partitions` itself. Task 6's test pins it.
5. **Visual parity.** The page renders the same sections, text and classes as before; Task 7 compares a rendered snapshot of the fixture page before and after.

---

### Task 1: Nuxt settings, Steiger and the CI step

**Files:**
- Modify: `extensions/console/app/nuxt.config.ts` (`dir: { pages: 'routes' }`, `components: false`, `imports: { autoImport: false }`, `alias: { '@': fileURLToPath(new URL('./app', import.meta.url)) }`), `package.json` (dev dependencies `steiger@0.8.0` and `@feature-sliced/steiger-plugin@0.8.0`; script `lint:fsd`: `steiger ./app`), `vitest.config.ts` (the same `@` alias, test globs for `app/**/*.test.ts` and `server/**/*.test.ts`)
- Create: `extensions/console/app/steiger.config.ts` (the plugin's recommended config, nothing turned off)
- Modify: `.github/workflows/gate.yml` (the `console` job runs `npx steiger ./app` before Vitest)

- [ ] Step 1: before anything moves, record the parity snapshot: a Vitest test renders today's `TodayView` from the fixture and writes its text and section headings to `app/tests/fixtures/today.render.txt` (Task 7 compares against it). Then install the two dev dependencies with `npm install -D`, run `npx steiger ./app` on the current tree and record what it reports (it should flag `components/` and `composables/` as not FSD layers).
- [ ] Step 2: apply the Nuxt settings; confirm `nuxi build` now fails on the auto-imported `TodayView` and `useToday` (Review Focus 3); leave it failing for Task 6 to fix.
- [ ] Step 3: commit.

### Task 2: `shared`

**Files:**
- Create: `app/shared/config/index.ts` (`POLL_MS = 60000`), `app/shared/api/index.ts` (`getJson<T>(path)`: `$fetch` from `#imports`, typed), `app/shared/lib/index.ts` (`plural(n, word)`, `isLink(s)`, `obsidianLink(path)`, `slug(s)`), `app/shared/ui/index.ts` with `Card.vue`, `Tag.vue` (`tone: 'warn' | 'plain'`), `Chip.vue` (pressed state), `Button.vue`, `Tile.vue`; `app/app/styles/tokens.css` (the `:root` tokens moved from `app.vue`)
- Test: `app/shared/lib/index.test.ts`, `app/shared/ui/ui.test.ts`

- [ ] Step 1: failing tests: `plural` (0, 1, 2), `isLink`, `obsidianLink` encodes spaces, `slug`; `Chip` sets `aria-pressed` and emits `click`; `Tag` tone classes.
- [ ] Step 2: implement; run the per-task check. Commit.

### Task 3: `entities`

**Files:** under `app/entities/`, each with `index.ts`:
- `today/`: `model/types.ts` (`Today`, `Part`, `Tiles`: today's types moved out of `TodayView.vue`), `api/useTodayQuery.ts` (Vue Query, `refetchInterval: POLL_MS`, `refetchIntervalInBackground: false`)
- `project/`: `model/types.ts` (`Project`), `ui/ProjectCard.vue` (rank, Obsidian link, focus, stale tag, Next, Decisions with "and N more", the foot counts)
- `now-line/`: `model/types.ts` (`NowLine`), `lib/due.ts` (`dueLabel`: "N days over", else the date's month and day), `ui/NowLineRow.vue`
- `work-order/`: `model/types.ts`, `lib/focus.ts` (`onFocus(order, projectLinks)`, the slug match), `ui/WorkOrderItem.vue`
- `meeting-action/`, `calendar-event/`, `source/`: a type and one row component each
- Test: beside each `ui/` and `lib/`

- [ ] Step 1: failing tests: `ProjectCard` with and without `stale`, with `decisions_more`; `dueLabel` for over, future and empty; `onFocus` true and false; each row renders its fields.
- [ ] Step 2: implement by moving markup out of `TodayView.vue`, unchanged; run the per-task check. Commit.

### Task 4: `features`

**Files:** under `app/features/`, each with `index.ts`:
- `switch-partition/`: `model/usePartition.ts` (`ref<'work' | 'personal'>`), `ui/PartitionTabs.vue`
- `filter-now-lines/`: `model/useNowFilter.ts` (the filter ref, and `filterLines(lines, filter)`, a pure function), `ui/FilterChips.vue`
- `refresh-today/`: `ui/RefreshButton.vue` (takes `busy`, emits `refresh`)
- Test: beside each

- [ ] Step 1: failing tests: `filterLines` for each of the five filters; `PartitionTabs` and `FilterChips` set `aria-pressed` and update their model; `RefreshButton` shows "Refreshing" while busy and emits once per click.
- [ ] Step 2: implement; run the per-task check. Commit.

### Task 5: `widgets`

**Files:** under `app/widgets/`, each with `index.ts` and `ui/<Name>.vue`: `header-bar` (date, `PartitionTabs`, Foreman link, stamps, `RefreshButton`), `errors-strip`, `summary-tiles`, `focus-projects` (`ProjectCard` list, "Also active"), `today-list`, `calendar`, `meeting-actions`, `now-lines` (`FilterChips`, `NowLineRow` table, the unparsed note), `work-orders` (`WorkOrderItem` list, held line), `pipeline`
- Test: one per widget, beside it

- [ ] Step 1: failing tests: each widget renders from a slice of the fixture, and its empty state (`None.`, `Nothing in today's prep.`, `None queued or run today.`).
- [ ] Step 2: implement; widgets take one partition's `Part` or a top-level part of `Today` as props and never the whole `partitions` map. Run the per-task check. Commit.

### Task 6: `pages/today`, the route and the app layer

**Files:**
- Create: `app/pages/today/index.ts`, `app/pages/today/ui/TodayPage.vue` (holds `usePartition`, `useNowFilter` and `useTodayQuery`; passes `data.partitions[partition]` and the top-level parts down), `app/routes/index.vue` (one line: `TodayPage`), `app/app/providers/vue-query.ts` (the plugin, moved)
- Modify: `app/app.vue` (imports `tokens.css`, renders `<NuxtPage />`)
- Delete: `app/components/TodayView.vue`, `app/composables/useToday.ts`, `app/plugins/vue-query.ts` (each now lives in a slice)
- Test: `app/pages/today/ui/TodayPage.test.ts`: today's `today-view.test.ts` assertions, moved, against the page with the query mocked; plus "no widget receives the `partitions` map" (Review Focus 4)

- [ ] Step 1: move the tests and see them fail against the deleted component.
- [ ] Step 2: implement; `nuxi build` passes again (Task 1's seeded failure is gone). Run the per-task check. Commit.

### Task 7: the shared contract, parity and docs

**Files:**
- Move: `tests/fixtures/today.json` to `app/tests/fixtures/today.json` (ARCHITECTURE.md §5)
- Create: `extensions/console/tests/python/test_contract.py`: run `today.py --json` on the fixture vault and assert its output has every key the fixture has, at every level (lists checked through their first item)
- Move: `server/utils/run.ts` to `runAdapter(vault, name, exec)` (the screen name chooses `scripts/<name>.py` from a constant list: `['today']`); `server/api/today.get.ts` calls `runAdapter(vault, 'today')`; its tests move to `server/utils/run.test.ts`
- Test: a parity check: the fixture page's rendered text and section headings match the pre-refactor snapshot recorded in Task 1 Step 1
- Modify: `docs/superpowers/2026-10-24-console-plan.md` (§4 names ARCHITECTURE.md), `docs/superpowers/plans/2026-10-24-console-today.md` (Task 6's file list points at this plan), `CHANGELOG.md`

- [ ] Step 1: failing tests: the contract test with a key added to the fixture only; `runAdapter` refusing a name outside the list.
- [ ] Step 2: implement; run every check: Vitest, Steiger, `nuxi build`, the console pytest suite, `system/scripts/test.sh system/tests/conformance.bats`. `/foundry-review`. Commit and push to #392.

## As built

Where the build left this plan, and why. ARCHITECTURE.md carries each rule.

- **Source root `src/`, not `app/`** (`srcDir: 'src'`): Steiger read a root named `app/` as FSD's `app` layer. Paths above that say `app/<layer>` are `app/src/<layer>`. `tsconfig.json` repeats the `@` alias under `paths` so Steiger resolves it.
- **Single-use slices fold into the page** (owner, "a, follow the rule", on Steiger's `insignificant-slice`): every entity, feature and widget had one importer, so all of Tasks 3 to 5 live in `src/pages/today/` (`ui/`, `model/`, `lib/`, `api/`). They become slices when a second page uses them (C3 Search). The `Today` type and `useTodayQuery` sit in the page too, since entities may not import each other. `RefreshButton` is an inline `Button` in `HeaderBar`.
- **`server-state/`, not `providers/`**: Steiger's `segments-by-purpose`. The root component stays `src/app.vue`; an `app/index.ts` made Nuxt resolve the root to it.
- **Explicit server imports**: `imports.autoImport: false` also turns off Nitro's, so server files import `h3` and `nitropack/runtime`.
- **The missing-import guard is a test** (Review Focus 3): `nuxi build` passes with a missing component import. The page test mounts with a `warnHandler` that throws; seeding a missing `CalendarEventRow` import failed it.
- **Tests outside `src/`**: block tests are in `tests/today/` and `tests/layers/`, so Steiger does not read them as slices; `tests/server.test.ts` split into `server/utils/auth.test.ts` and `run.test.ts`.
- **The contract test** checks a list of objects through its first item and lets a list of strings be empty. Its vault helper, `today_vault`, moved to `console_today_fixtures.py` so both suites share it.
