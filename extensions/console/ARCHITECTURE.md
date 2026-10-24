# The console's architecture

The rules every console screen follows (#377 Q12, owner, 2026-10-24). A change that breaks one of them changes this file first. The program is `docs/superpowers/2026-10-24-console-plan.md`; each phase's spec cites this file.

## 1. The three parts

```
browser ── Vue client (Feature-Sliced Design, §2)
             │ GET/POST /api/<route>  (the only way out)
           Nitro server (thin handlers over pure utils, §3)
             │ execFile, argument list, timeout
           Python adapter, one per screen (§4)
             │ execFile, argument list
           core scripts' --json commands, and the morning's prep files
```

Each part talks only to the one below it. The client never sees a path or a command. The server never opens a vault file. The adapter never imports a core module other than `vaultlib.api`.

## 2. The client: Feature-Sliced Design

The client follows [Feature-Sliced Design](https://feature-sliced.design/) (FSD) as its Nuxt guide sets it out, adapted to Nuxt 4's `app/` source folder. **Steiger** (`steiger` and `@feature-sliced/steiger-plugin`) checks the rules in CI. It is beta software; a rule it gets wrong is turned off in `steiger.config.ts` with a one-line reason, never by moving code to dodge it.

### 2.1 Layers

From top to bottom. A module imports only from layers below its own, and from its own slice.

| Layer | Holds | Console slices (C1; later phases add) |
|---|---|---|
| `app` | Bootstrapping: the Vue Query provider, global styles and tokens, the root component | one, unsliced |
| `pages` | One slice per screen: composes widgets, owns nothing else | `today` (C3: `search`) |
| `widgets` | Self-contained blocks of a page, composing features and entities | `header-bar`, `summary-tiles`, `focus-projects`, `today-list`, `calendar`, `meeting-actions`, `now-lines`, `work-orders`, `pipeline`, `errors-strip` |
| `features` | One user action each, with its own UI and state | `switch-partition`, `filter-now-lines`, `refresh-today` (C2: `ask-wiki`; C3: `tick-now-line`, `queue-work-order`) |
| `entities` | One thing the vault holds: its type, its display, its query | `today`, `project`, `now-line`, `work-order`, `meeting-action`, `calendar-event`, `source` |
| `shared` | No knowledge of the vault: the fetch client, UI primitives, formatters, config | unsliced: `api`, `ui`, `lib`, `config` |

### 2.2 Slices, segments and the public API

- A slice is a folder: `app/<layer>/<slice>/`. Slices on one layer never import each other. When two widgets need the same thing, it moves down a layer.
- Inside a slice, code sits in segments: `ui/` (components), `model/` (types, state, computed values), `api/` (queries), `lib/` (helpers for this slice only).
- Every slice has an `index.ts`, its public API. Code outside the slice imports `@/<layer>/<slice>` only, never a file inside it.
- `shared` and `app` have segments but no slices.

### 2.3 Naming

| Thing | Name |
|---|---|
| Slice folder | kebab-case noun or verb phrase: `now-line`, `filter-now-lines` |
| Component | PascalCase, prefixed by its slice: `NowLineRow.vue`, `FilterNowLines.vue` |
| Query composable | `use<Thing>Query()` in `entities/<thing>/api/` |
| Type | PascalCase in `entities/<thing>/model/types.ts`, matching the adapter's JSON key for key |
| Page | `<Screen>Page.vue` in `pages/<screen>/ui/` |

### 2.4 Nuxt settings

- **Routing:** `dir.pages: 'routes'`, so Nuxt reads routes from `app/routes/`. Each route file is one line that renders a page slice: `<template><TodayPage /></template>` with an explicit import from `@/pages/today`.
- **No auto-imports:** `components: false` and `imports.autoImport: false`. Every component and composable is imported by name through a public API, so Steiger sees each dependency. Nuxt's own helpers come from `#imports`.
- **Alias:** `@` is `app/`, so imports read `@/entities/now-line`.
- **Rendering:** `ssr: false`. The server's only job is the API.

### 2.5 State

- **Server state** is TanStack Vue Query only, one query per adapter, in `entities/<thing>/api/`. No other store holds server data.
- **UI state** that one feature owns (a tab, a filter) lives in that feature's `model/` as a composable. A page passes it down to the widgets that read it.
- No global store. When two pages need the same UI state, it moves to `shared/model` and this file says why.

### 2.6 Style

Design tokens are CSS custom properties in `app/styles/tokens.css`: ground, card, ink, muted, line, accent, warn and ok, from the mockup. Components use scoped styles and the tokens only, never a raw colour. UI primitives (`Card`, `Tag`, `Chip`, `Button`, `Tile`) live in `shared/ui`.

## 3. The server: thin handlers over pure utils

- One file per route: `server/api/<route>.<method>.ts`. A handler reads the request, calls one util and sets the status. No logic.
- Logic lives in `server/utils/` as plain functions whose dependencies are parameters (`runAdapter(vault, name, exec)`), so Vitest tests them with no Nuxt runtime.
- Cross-cutting rules are Nitro hooks: `server/middleware/auth.ts` checks the login on every request; `server/plugins/host.ts` refuses a non-loopback host at start.
- **Reads** are `GET`, take no input that reaches a command, and run one adapter with constant arguments.
- **Writes** (C3 on) are `POST /api/<action>`. Each runs exactly one vault script (`system/scripts/now.py set`, `nightshift.py add`) through `server/utils/script.ts`. That util takes an allowlist entry and validated values, builds an argument list, and returns `{exit, stdout, stderr}`. The handler validates the body against a schema before the call, answers 400 on bad input and passes the exit code back. No route writes a file.

## 4. The adapters: one per screen

- `extensions/console/scripts/<screen>.py --json` gathers everything one screen shows into one object starting `"v": 1`. A key renamed or removed bumps `v`; a key added does not.
- It runs core commands as subprocesses with argument lists and reads only prep files and logs. It imports `vaultlib.api` only (the F2 ban).
- A failing source leaves its part empty and adds one line to `errors`. It exits 0 unless its arguments are bad (2).
- Each partition's object holds only that partition's data.
- Its pytest suite imports helpers from a uniquely named module (`console_<screen>_fixtures.py`), never `from conftest import`: the gate runs every extension's tests in one process.

## 5. One contract, tested on both sides

`app/tests/fixtures/<screen>.json` is the shape both sides agree on. The Python suite checks that the adapter's real output has the fixture's keys at every level; the Vitest suite renders the page from the fixture, typed as `entities/<screen>/model/types.ts`. Changing the shape changes the fixture, the type and the adapter in one PR.

## 6. Tests

| What | Where | Tool |
|---|---|---|
| A slice's components | `app/<layer>/<slice>/ui/*.test.ts` beside them | Vitest, happy-dom |
| A slice's model and lib | beside them | Vitest |
| A page against the fixture | `app/pages/<screen>/ui/*.test.ts` | Vitest |
| Server utils | `server/utils/*.test.ts` | Vitest, node |
| The layer rules | the whole of `app/` | Steiger |
| The adapter | `tests/python/` | pytest |

CI's `console` job runs Steiger, Vitest and `nuxi build`.
