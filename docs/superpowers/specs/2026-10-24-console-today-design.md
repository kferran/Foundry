# Console C1: the Today Screen Design

**Date:** 2026-10-24
**Program:** docs/superpowers/2026-10-24-console-plan.md (phase C1)
**Grill:** 2026-10-24, decisions recorded on https://github.com/kferran/Foundry/issues/377 (Q1 to Q11).
**Builder check:** 2026-10-24, seven questions, all settled in §8: where `node_modules` and the build live; how an always-on unit installs, a client included; how one poll reads everything; which mockup fields have no source today; how the app proves the caller is the owner; what the Foreman link points at; how CI builds Node in a Python repository.
**Blueprint:** none: a read-only web app over the scripts' JSON; no source, poller, compile run or Work Order.
**Lane:** feature. C1.1 touches the unit installer, so the owner merges it; C1.2 to C1.4 are extension code and docs.

## 1. Problem

The owner starts the day from Slack, GitHub or the calendar, not the brief (#351 grill, Q1). The vault holds what they need: focus projects, open Now lines, Work Orders, the day's calendar and meeting actions. Today the only views are the brief (once a day) and Obsidian (one note at a time).

## 2. Goal

`extensions/console/` serves the Today screen exactly as drawn in the mockup (#377 Q1), live from the server's vault over Tailscale and from Omarchy's synced copy on `127.0.0.1`. It refreshes every 60 seconds while the tab is visible (Q6), never writes to the vault, and never starts a connector session (Q2).

## 3. Shape

```
browser ── tailscale serve (HTTPS, adds Tailscale-User-Login) ── 127.0.0.1:<console_port>
                                                                   Nuxt server (node, in console_build_dir)
                                                                     GET /api/health   → {"ok": true, "v": 1}
                                                                     GET /api/today    → execFile python3 extensions/console/scripts/today.py --json
                                                                                          (cwd = vault root, 15 s timeout)
today.py ── execFile ── system/scripts/now.py list --json
                     ── system/scripts/active_projects.py <today> --json
                     ── system/scripts/nightshift.py list --json, report --json
                     ── reads system/logs/inputs/<today>/ (calendar.tsv, actions.md, sources.md, quarantine.md)
                        and system/logs/alerts_<today>.md through vaultlib.api
```

`today.py` is the one adapter. The Node side never opens a vault file and never builds a path into the vault from request input: `/api/today` takes no parameters.

## 4. The Today screen's data

Each mockup element and where it comes from. "Prep" means `system/logs/inputs/<today>/`, written at about 05:40 (Q2).

| Element | Source | Live or prep |
|---|---|---|
| Header date, partition tabs | `Intake.today()`; `partitions` keys | live |
| "Read from prep HH:MM · index HH:MM" | mtime of the prep folder and of `system/index.db` | live |
| Tiles: Focus, Needs you, Overdue, Waiting, Work Orders | counts over the projects, the Now lines (`section`, `band`) and the Work Order items (`state`) | live |
| Focus project cards: rank, link, focus, Next, Decisions waiting | `active_projects.py --json` | live |
| Card stale flag; "Also active" line | `stale`, `also_active` from #351; hidden when absent | live |
| Card "N Now lines" | Now lines whose statement links the project (`[[Name]]`) or names it as a whole word, case-insensitive | live |
| Card "N open PRs" | of those lines, the ones whose evidence is a pull request URL | live |
| Card "changed …" | the newest commit date of the project page (`git log -1 --format=%cs -- <path>`) | live |
| Today list | the first Next item of each focus project, in rank order, at most 5 (the #351 Q7 rule) | live |
| Calendar | prep `calendar.tsv` | prep |
| Your meeting actions | prep `actions.md`, the **Yours** section | prep |
| Now lines table and its filters | `now.py list --json`; Project column from the same match as the card count, "—" when none | live |
| Work Orders | `nightshift.py list --json` (queued, running, waiting_reset, delivering) and `report --json` items; "not on focus" as in #351 Task 3 | live |
| Pipeline | prep `sources.md`; `quarantine.md` counts; today's alert count from `alerts_<today>.md` | prep and live |
| "Talk to the Foreman" | `console_foreman_url` | config |

`today.py --json` prints one object: `{"v": 1, "date", "stamps": {"prep", "index"}, "partitions": {<p>: {"tiles", "projects", "also_active", "today", "now", "actions"}}, "calendar", "orders", "pipeline", "foreman_url", "errors": []}`. A source that fails (a non-zero exit, unreadable JSON, a missing prep file) leaves its part empty and adds one line to `errors` naming the source and the exit code; the rest still prints and `today.py` exits 0. It exits 2 only on bad arguments. The page shows `errors` in a strip under the header.

## 5. Running it

**Config keys** (the extension's `schemas/config.md` fragment):

| Key | Default | Meaning |
|---|---|---|
| `console_port` | `3110` | the port on `127.0.0.1` |
| `console_auth` | `tailscale` | `tailscale`: only `console_login` gets an answer; `none`: no check (Omarchy fallback) |
| `console_login` | `""` | the owner's Tailscale login; with `console_auth: tailscale` and this empty, every request gets 403 |
| `console_foreman_url` | `https://claude.ai/code` | where "Talk to the Foreman" goes |
| `console_build_dir` | `~/.cache/foundry-console` | where `build.sh` puts the source copy, `node_modules` and `.output` |

**Build.** `extensions/console/scripts/build.sh` copies `extensions/console/app/` to `<console_build_dir>/src` (`rsync --delete`, excluding `node_modules` and `.output`), runs `mise install` and `npm ci` there, then `npx nuxi build`. It exits 0, 1 on a failed step (naming it) or 2 on bad config. The template update does not rebuild; the owner runs `build.sh` after an update that changes `app/` (the CHANGELOG line says so) and then `systemctl --user restart foundry-console`.

**Unit.** `foundry-console.service` (`Type=simple`, `Restart=on-failure`): `ExecStart=mise exec --cd <console_build_dir>/src -- node .output/server/index.mjs`, with `NITRO_HOST=127.0.0.1`, `NITRO_PORT=<console_port>` and `FOUNDRY_VAULT=<vault root>`. Its manifest entry is `{name: foundry-console, roles: [standalone, server, client], timer: false}` (§8.2).

**Tailscale.** On the server the owner runs `tailscale serve --bg --https=443 http://127.0.0.1:<console_port>` once. The manifest body says so; nothing runs it for them.

**Smoke.** `{source: console, run: "scripts/today.py --check"}`: runs `today.py` and the health route (`curl -fsS http://127.0.0.1:<port>/api/health`) and prints `ok` or `failed: <class>: <reason>`.

**Setup.** `/setup` phase 6e lists the extension. Its manifest body asks for `console_login` (on the server), `console_auth` (`none` on Omarchy) and the port, then names `build.sh`, `install_units.sh` and the `tailscale serve` line.

## 6. Security

- **Bind.** Nitro listens on `127.0.0.1` only; the unit sets it and `server/middleware/auth.ts` refuses to start when `NITRO_HOST` is anything else.
- **Login.** With `console_auth: tailscale`, the middleware answers 403 unless `Tailscale-User-Login` equals `console_login` exactly. `tailscale serve` sets that header from the tailnet identity. Any local process on the server could send the header to `127.0.0.1` too; local processes are inside the trust boundary already (they can read the vault).
- **Reads only.** Every route is a GET. No route takes input that reaches a command line or a path.
- **No secrets.** The app holds no token. `today.py` prints what the scripts print; Now statements were redacted when written (#310).
- **Partition walls.** The page shows one partition at a time from the `partitions` object; nothing combines the two.

## 7. Out of scope

`ask` (C2), search and any write (C3), the Search and manage screen, mobile layout beyond the mockup's wrap rules, notifications, a second user.

## 8. Builder check (2026-10-24)

1. **`node_modules` and the build.** Inside the vault they would reach Obsidian's file list, Obsidian Git and `/lint`'s untracked scan. Settled: `build.sh` builds in `console_build_dir`, outside the vault; `app/` holds only source, and `.gitignore` excludes `extensions/console/app/{node_modules,.nuxt,.output}` in case someone builds in place.
2. **An always-on unit.** `install_units.sh:126-133` adds `.service` and `.timer` for each manifest unit and enables the timer; a client gets no units. Settled (C1.1): a `units` entry may carry `timer: false`. The installer then adds and enables the `.service` alone, and such an entry may list `client`, the one unit a client installs. A timer unit on a client stays refused. The loader rejects `timer` that is not a boolean.
3. **One poll.** Four commands and five files per poll from Node would be nine spawns every 60 s per tab. Settled: `today.py` gathers them in one process, so the app spawns one.
4. **Mockup fields with no source.** Now lines carry no project field (#351 Q4) and nothing counts PRs per project. Settled: the match in §4 (a `[[Name]]` link or the whole-word name), the PR count from those lines' evidence, and the page's last commit date. A line that matches nothing shows "—". A false match costs a wrong count on a read-only screen.
5. **The login.** Settled: the Tailscale header behind a `127.0.0.1` bind (Q4), and 403 for an empty `console_login`, so a fresh install answers nothing until the owner names themselves.
6. **The Foreman link.** feOS sessions are replaced every day or two, so a session link goes stale. Settled: `console_foreman_url`, default `https://claude.ai/code` (the session list).
7. **Node in CI.** Settled: a third job, `console`, in `gate.yml`: `jdx/mise-action` with the pinned Node, `npm ci`, `npx vitest run`, `npx nuxi build` in `extensions/console/app/`. The two existing jobs need no Node; `today.py`'s pytest suite runs in `gate-all-extensions`.
