# The console: program plan

**Date:** 2026-10-24
**Issue:** https://github.com/kferran/Foundry/issues/377 (the grill, Q1 to Q11, is recorded there)
**Mockup:** https://claude.ai/artifact/XPgEhZdiXxjHdQy2HUcYvW (private to the owner; Today and Search and manage screens, sample data)
**Built by:** the Foundry's pipeline in a Foundry session (Q11), never a Work Order handed to the Foreman.

## 1. What it is

A web app over the vault, shipped as the extension `extensions/console/`. Vue with Nuxt; TanStack Vue Query and Vue Table only where a screen needs them (Q10). It runs on the Debian bookworm server (main copy, behind `tailscale serve`) and on the Omarchy machine (read-only fallback on `127.0.0.1`) (Q3, Q4). It reads the vault only through the scripts' JSON and argument lists (Q7).

## 2. Phases

| Phase | Issue milestone | What ships | Depends on | Spec and plan | State |
|---|---|---|---|---|---|
| C0 | M0 | `--json` on `now.py list`, `active_projects.py`, `nightshift.py list` and `report` | none | `specs/2026-10-24-json-output-design.md` (task list in the spec) | Spec merged (#378); build in #383 |
| C1 | M1 | The Today screen, read-only, and the "Talk to the Foreman" link | C0 merged; F2 closed (#307) | `specs/2026-10-24-console-today-design.md`, `plans/2026-10-24-console-today.md` | Spec and plan drafted |
| C2 | M2 | `ask`: a read-only headless command over the compiled wiki, answered in the app (and later from Slack, #333) | C1 | to write when C1 is live: it adds a `run_headless.sh` command, a confinement surface the owner merges | Not started |
| C3 | M3 | Search and manage: index search; actions that run one vault script each (tick or add a Now line, queue a Work Order, retry a quarantined input, rebuild the index); handing requests to the Foreman | C1, C2; F5 closed (#310) | to write after C2: the first writes from the app | Not started |

C2 and C3 get their specs only once the phase before them is live, so each builds on what the last one taught.

## 3. C1's pull requests

| PR | Scope | Lane | Who merges |
|---|---|---|---|
| C1.1 | Core: an always-on extension unit (`timer: false` on a manifest `units` entry), installable on a client too | feature, core (`install_units.sh`, the loader) | the owner |
| C1.2 | The extension's Python side: manifest, config fragment, `today.py` (one JSON object for the Today screen), build script, unit template, smoke row | feature, extension | auto-merge once CI and the reviewer pass |
| C1.3 | The Nuxt app: the Today page as drawn, `/api/today` and `/api/health`, the login middleware, polling; the `console` CI job | feature, extension | auto-merge once CI and the reviewer pass |
| C1.4 | Live acceptance on the server and on Omarchy; FOUNDRY.md and CHANGELOG | docs | auto-merge |

C1.1 merges first. C1.2 and C1.3 can build in parallel once it has.

## 4. Rules for every phase

- The app never opens a vault file. Its server routes run `extensions/console/scripts/*.py` or `system/scripts/*` with an argument list (`execFile`, never a shell), from the vault root, with a timeout, and pass back their JSON.
- `node_modules` and the build never sit in the vault: `build.sh` builds in `console_build_dir` (default `~/.cache/foundry-console`), so Obsidian, Obsidian Git, the index and the secret scan never see them.
- The app listens on `127.0.0.1` only. With `console_auth: tailscale` it answers only requests whose `Tailscale-User-Login` equals `console_login`.
- No connector session, ever, from the app (Q2). Calendar and meeting actions come from the morning's prep.
- Writes wait for C3. Until then every route is a GET and reads.

## 5. Open items

- Omarchy is a client (owner, 2026-10-24), so C1.1 lets an always-on unit install there. Its copy of the vault is only as fresh as its last sync. Today that sync is Obsidian Git, which runs only while Obsidian is open; #385 adds a sync timer for a client so the console's fallback stays current without Obsidian.
- The focus-first brief (#351) adds `stale` and `also_active` to `active_projects.py --json`. The Today screen shows them when present and hides them when not.
