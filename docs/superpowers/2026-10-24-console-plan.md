# The console: program plan

**Date:** 2026-10-24
**Issue:** https://github.com/kferran/Foundry/issues/377 (the grills are recorded there: Q1 to Q12 on 2026-10-24; more workflows, Q1 to Q23, and the style system, Q24 to Q29, on 2026-11-03)
**Architecture:** `extensions/console/ARCHITECTURE.md` (Q12: Feature-Sliced Design on the client, Steiger in CI, no Nuxt auto-imports); every phase follows it. The style system (Q24 to Q29) joins its §2.6 in C1.5's first PR.
**Mockup:** https://claude.ai/artifact/XPgEhZdiXxjHdQy2HUcYvW (private to the owner; Today and Search and manage screens, sample data)
**Built by:** the Foundry's pipeline in a Foundry session (Q11), never a Work Order handed to the Foreman.

## 1. What it is

A web app over the vault, shipped as the extension `extensions/console/`. Vue with Nuxt; TanStack Vue Query and Vue Table only where a screen needs them (Q10). It runs on the Debian bookworm server (main copy, behind `tailscale serve`) and on the Omarchy machine (on `127.0.0.1`) (Q3, Q4). From C3a both machines write (2026-11-03 Q18, owner). It reads the vault only through the scripts' JSON and argument lists (Q7).

## 2. Phases

| Phase | Issue milestone | What ships | Depends on | Spec and plan | State |
|---|---|---|---|---|---|
| C0 | M0 | `--json` on `now.py list`, `active_projects.py`, `nightshift.py list` and `report` | none | `archive/specs/2026-10-24-json-output-design.md` (task list in the spec) | Complete (2026-10-24): spec #378, build #383 |
| C1 | M1 | The Today screen, read-only, and the "Talk to the Foreman" link | C0 merged; F2 closed (#307) | `specs/2026-10-24-console-today-design.md`, `plans/2026-10-24-console-today.md` | Built: C1.1 #389, C1.2 #391, C1.3 #392 (merged 2026-10-30). C1.4 waits on the owner's live checks on the server and Omarchy (tracked in the owner's vault) |
| C1.5 | M1 | Read-only screens: the style system (first PR, retrofitting Today), project drill-down, brief reader, ops panel, people view, meeting prep (§6) | C1 live; the proof-before-features count (roadmap) at 3 or fewer | to write when C1 is live | Grilled 2026-11-03 |
| C2 | M2 | `ask`: a read-only headless command over the compiled wiki, answered in the app (and in the notify thread, #333) | C1.5 | to write when C1.5 is live: it adds a `run_headless.sh` command, a confinement surface the owner merges | Not started |
| C3a | M3 | The write path and phone capture: the POST layer and its guards, capture, the brief's Notes box, drafts "Sent", meeting after-steps (§6) | C2; #385 (client sync on a timer); F5 closed (#310) | to write after C2: the first writes from the app, and three core writers the owner merges | Grilled 2026-11-03 |
| C3b | M3 | Search and manage: index search; Work Order review (read, answer `needs`, queue an approved plan, cancel); actions that run one vault script each (tick or add a Now line, retry a quarantined input, rebuild the index, a live smoke run); handing requests to the Foreman | C3a | to write after C3a | Not started |

Each phase gets its spec only once the phase before it is live, so each builds on what the last one taught.

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
- Writes wait for C3a. Until then every route is a GET and reads.
- From C3a, every POST needs a matching `Origin` and a JSON content type; with `console_auth: none` the `Host` must also be `127.0.0.1:3110` or `localhost:3110` (2026-11-03 Q19, Q23).

## 5. Open items

- Omarchy is a client (owner, 2026-10-24), so C1.1 lets an always-on unit install there. Its copy of the vault is only as fresh as its last sync. Today that sync is Obsidian Git, which runs only while Obsidian is open; #385 adds a sync timer for a client, and it moves ahead of C3a because Omarchy writes too (2026-11-03 Q22).
- The focus-first brief (#351) adds `stale` and `also_active` to `active_projects.py --json`. The Today screen shows them when present and hides them when not.
- Weekly review is folded until #112 item 6 is grilled (2026-11-03 Q1).

## 6. The 2026-11-03 decisions by screen

Full record on #377. Every phase follows §4 and ARCHITECTURE.md.

- **Style system (C1.5, first PR):** the mockup tokens with a dark value each, following the system setting; a deliberately grown `shared/ui` with Reka UI (headless, imported by name) for dialogs, tabs, menus, popovers and toasts; scoped CSS on the tokens, no Tailwind and no themed kit; a dev-only `/styleguide` route and a table of primitives in ARCHITECTURE.md §2.6; Stylelint in the `console` job fails a raw colour, font or spacing value; pages never style a native `<button>`, `<input>` or `<dialog>`; every primitive has `variant`/`size` props and a test.
- **Layout:** Today stays home and links into each screen; each screen has its own route.
- **Project drill-down:** every `ActiveProjects.md` entry within its partition: Next, Decisions, Now lines, Work Orders and PRs, the last 30 days of meetings, the Obsidian link.
- **Brief reader:** the brief's Markdown, with its Dataview blocks resolved on the server (From Now from `now.py list --json`) and the debrief embed inlined. The Notes box comes in C3a.
- **Ops panel:** the last smoke result, alerts, quarantine, unit status and ledger, read from the logs. A live smoke run is a C3b action.
- **People view:** names matched against entity `aliases`, per partition; a name with no entity note is plain text. It shows Now lines and meeting actions only, never an entity note's body.
- **Meeting loop:** prep (C1.5) shows the next meetings, each attendee's open lines and actions, and related notes from the index. After the meeting (C3a), upload the transcript and tick action items with a script that flips only that checkbox.
- **Drafts to send (C3a):** the `draft` Now lines with their links; "Sent" closes a line through `now.py` with the sent message's link as evidence. The app never sends.
- **Capture (C3a):** text and URLs to `raw/inbox/`; photos and transcripts by file type (transcripts to `meetings/drop/<partition>/`); no voice. Text up to 64 KB, files up to 20 MB of `.png`, `.jpg`, `.heic`, `.vtt`, `.srt`, `.txt`, `.md`, names sanitised.
- **Writers:** three new core scripts the owner merges: inbox add, meeting action tick, brief Notes append.
- **Omarchy writes:** new files land at once; an edit to an existing note pulls, writes, then commits and pushes, and a failed pull blocks the write with its reason.
- **Work Orders (C3b):** read plans and outcomes, answer `needs`, queue an approved plan, cancel. Plans are approved in a session.
