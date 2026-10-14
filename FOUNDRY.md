# The Foundry

An Obsidian + Claude Code "second brain" vault template. This file is its manual. A vault's own `README.md` describes that vault (its machines, codebases and what runs where), and template updates never change it (see [Updating and uninstalling](#updating-and-uninstalling)).

> **Status:** in daily use since 2026-10-05 on one Debian server and a laptop client. The headless brief, debrief and intake pipeline passed live acceptance ([record](docs/superpowers/spikes/2026-10-02-plan-4a-acceptance.md)), as did memory capture and recall ([record](docs/superpowers/spikes/2026-10-02-plan-3-acceptance.md)), two-machine sync ([record](docs/superpowers/spikes/2026-10-04-plan-8c-acceptance.md)) and meetings ([record](docs/superpowers/spikes/2026-10-06-plan-11-acceptance.md)). Preferences, style lint and the Foreman orchestrator are still to come (see [Status](#status)).

## What The Foundry is

The Foundry is a template repository that becomes your vault. You clone it, run `claude` inside it, and run `/setup`. Setup configures the vault for your machine, your schedule and your codebases. Nothing specific to a machine or a user is committed. Per-user state is generated at setup time and gitignored.

The vault compiles itself. Raw inputs (files you drop in, plus short digests of your Claude Code sessions) are compiled in batches into a wiki of concepts, entities, summaries and preferences. The wiki is split into `work`, `personal` and `shared` partitions, and links are not allowed to cross between `work` and `personal`. A derived SQLite FTS5 index lets agents ask the index for the notes they need before reading anything, so a lookup reads only the notes that answer it rather than the whole wiki.

Agents follow the writing rules in `CLAUDE.md`: chat replies are sized by type (quick answer, one-screen task report, or a linked document), and notes avoid common AI writing tells. The headless intake, brief and debrief runs edit their own prose against the vendored [humanizer](#acknowledgements) skill before they publish, and `/humanizer` runs it interactively.

Automation runs on systemd user timers: isolated headless `claude -p` jobs for intake, a morning brief and an evening debrief, plus a scripted git sync on a server. Headless jobs never write to the vault directly. They write to a staging area, and a deterministic gate validates and publishes their output. Anything that has to be exact (parsing, validation, indexing, unit rendering, git remote handling) is done by a script. The model handles conversation and synthesis.

## Status

**Works today:**
- Headless intake, morning brief and evening debrief, published through a deterministic gate
- Memory: session digest capture and bounded recall (optional hooks)
- Two machines: a server runs the automation and syncs through a private `origin`; clients read and edit in Obsidian
- Calendar input to the brief from the Google Calendar connector
- Error telemetry from Sentry and Azure Data Explorer
- Meetings: Gemini notes and dropped transcripts become meeting notes, tracked actions and searchable transcripts
- Work Orders: queued plans and research briefs run unattended
- DTCC change watcher (phase 1)
- Active Projects in the brief, and an archive of past briefings

**Next:** RCA-to-Jira (phase 1), preference notes from `/ingest`, then the Foreman orchestrator (Sub-project 2). Preferences (Plan 5) and style lint (Plan 7) wait for a few weeks of real use.

- Roadmap, with every plan, its records and its status: [docs/superpowers/roadmap.md](docs/superpowers/roadmap.md)
- Design spec: [docs/superpowers/specs/2026-09-30-vault-template-design.md](docs/superpowers/specs/2026-09-30-vault-template-design.md)

## How it works

The intended loop is **capture → compile → index → recall → correct**:

1. **Capture.** Files you drop in go to `raw/inbox/`, and meeting transcripts to `meetings/drop/<partition>/` (a server with `meetings_enabled` also fetches Gemini notes from Google Drive); each meeting becomes a meeting note with tracked action items and a searchable transcript. Once the memory hooks are installed, sessions in the vault and in registered codebases also leave short, redacted session digests in `raw/<partition>/notes/` (see [Memory](#memory) below).
2. **Compile.** The intake timer batches up to 5 inputs from one partition into an isolated headless `/ingest` run. For each fact, the run records an explicit noop, patch or create decision and writes its output to `wiki/.staging/<run_id>/`.
3. **Publish.** The publish gate validates schemas and partition walls and rejects changes that shrink existing notes. It also checks each target against a snapshot taken at the start of the run. If every check passes, it publishes everything at once. If any check fails, it publishes nothing and the run is quarantined. If you edited a note while the run was going, your edit is kept. A note you edited while the gate was renaming is held back, the rest publishes, and the alert names the staged copy under `system/quarantine/<run_id>/staged/`; the gate does not retry it. A rename the filesystem refuses is reported as a failed run, never as a held-back note.
4. **Index.** Markdown is the source of truth. `system/index.db` is a gitignored SQLite FTS5 index that can be rebuilt at any time. Agents run `related`, `query`, `show` and `backlinks` against it before reading any notes.
5. **Recall.** With the memory hooks installed, a `SessionStart` hook adds up to `recall_budget_chars` of vault data (default 9,000 characters, never more than 9,500) to new sessions in scope: the latest digests for the codebase or partition and, once enabled, preferences you have confirmed. Recalled text is marked as data, not instructions.
6. **Correct.** Each digest has a Corrections section. Ingest turns these into `preference` notes with linked evidence. A preference's status is calculated in the index, and it becomes confirmed only after you accept it in `/brief`.

**History.** `/backup` first commits each headless run that published files, one commit per run, with a message `commit_runs.py` builds from the run's records (no model writes it). Each carries `Foundry-Command`, `Foundry-Run` and `Foundry-Role` trailers, so `git log` reads as a handoff log: `git log --grep 'Foundry-Command: ingest'` lists the ingest runs.

| Name | Role | Concrete artifacts |
|---|---|---|
| **The Foundry** | The vault / product | this repo, `foundry-*` systemd units |
| **The Foreman** | The only role you address: briefings, debriefs and the agenda; the orchestrator in Sub-project 2 | `system/agents/foreman.md`, `/brief`, `/debrief` |
| **Workcells** | Specialist agents, each dispatched by the capabilities it lists | `system/agents/workcells/*.md` (each lists its `capabilities`), `capability` on concept notes |
| **The Core** | The compiled wiki, the index and memory | `wiki/`, plus the index and memory rows below |
| index | Search and views over the wiki | `system/index.db`, `vault_index.py` |
| memory | Session digest capture and recall | `system/hooks/memory_*.sh`, `/digest`, `vault_index.py recall` |
| intake compiler | Headless compile of raw inputs | `foundry-intake.service`/`.timer`, `intake_daemon.sh`, `run_headless.sh ingest` |
| publish gate | Validate, conflict-check, publish | `publish_staged.py`, `vaultlib/publish.py` |
| watcher | Zero-token watcher of Workcell sessions (reserved, Sub-project 2) | `foundry-watcher.service` (reserved) |
| Workcell sessions | Ship and scout sessions of a Workcell (reserved, Sub-project 2); scout reports land in `raw/inbox/` | `system/jobs/` (reserved), `FOUNDRY_WORKCELL_SESSION` |
| Production Job, Work Order | A multi-step assignment and each of its tasks (Sub-project 2) | `FOUNDRY_WORK_ORDER`, the digest field `work_order` |

Script and module filenames stay descriptive so they are easy to grep. Unit `Description=` lines read `The Foundry: <role>`, and log and alert tags use plain names (`[intake]`, `[memory]`, `[sync]`).

## Daily use

| Command | What it does |
|---|---|
| `/brief [date]` | The Foreman writes `briefings/<date>.md`: calendar commitments, Before today's meetings (each entity named in today's calendar with its open Now lines and open actions), the open lines of your Now pages (From Now), your open meeting actions, 🎯 Active Projects, a Blockers section (telemetry, friction, pipeline, communication debt), ⏳ Waiting on (one brief's worth of everyone else's meeting actions, computed from the import log where meetings are imported and from the notes' own start times elsewhere), and 🧾 Handoffs to chase when handoffs are set up. It adds 3–5 objectives tied to your superpowers and handed to a capability, and any new DTCC changes, to the Now pages. A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Briefings and debriefs from before yesterday move to `briefings/archive/<YYYY-MM>/` |
| `/debrief [date]` | The Foreman writes `briefings/<date>.debrief.md` (embedded in the briefing): commits per repo, digest outcomes, headless runs, alerts, agent health and what you delivered today |
| `/ingest <raw file>` | Compiles one raw input into `wiki/`; the intake timer runs it headless in batches |
| `/query <question>` | Answers from compiled `wiki/` notes only, through the index |
| `/lint` | Integrity report plus link, duplicate, contradiction and staleness suggestions |
| `/impact <component> [--repo name]` | Read-only blast-radius table across registered codebases and the wiki; offers to draft an intent proposal |
| `/rca <raw/telemetry/note.md>` | Root-cause analysis of one production error group: an `rca` note with a Ticket draft, filed to Jira only after you tick its Now line |
| `/backup` | Runs the gate (lint, then the test suites when bats and pytest are installed; lint only on a client), commits each headless run on its own, then commits and pushes the rest according to `remote_mode` (through `vault_sync.sh` in `private`) |
| `/order add\|ask\|list\|cancel\|status` | Queues an approved plan (or a task range of one) or a research brief as a Work Order for an unattended run; lists, cancels and reports on queued Work Orders |
| `/dtcc-watch [check\|status\|accept]` | Runs the DTCC change watcher by hand, checks its map, reports recent changes, or accepts held changes as the new baseline |
| `/setup` | Onboarding; safe to re-run |
| `/humanizer`, `/digest` | Edit prose against the vendored skill; write a session digest on demand |

**Superpowers** are your strategic anchors, set in `system/config.md` (`superpowers:`). The brief ties each objective to one, and onboarding and intent notes name the ones they serve. They are unrelated to the superpowers Claude Code plugin used in [Development](#development).

**Brief inputs.** The calendar (`calendar.tsv`, from the Google Calendar connector, read 3 events per page so long event descriptions stay under the session's result limit; a page that still exceeds it fails the fetch and the smoke check), `people.md` (the Before today's meetings blocks: each entity note whose title or alias appears in an event title, with its open Now lines and open meeting actions, at most five entities and five lines each), `actions.md` (your open meeting actions, any age, and everyone else's from the meeting notes imported since the previous weekday brief, printed once; none on a weekend), today's and yesterday's alerts, production-error groups in `raw/telemetry/` (new groups as a table, recurring as one line with a count and the three largest, resolved as a count, per environment), `friction.md` (the friction notes no earlier brief has listed, plus a count of all open ones), quarantined inputs, and mail and chat when a Gmail or Slack connector is present in an interactive session. Missing sources are listed under Unavailable Sources; a source that does not exist yet (agent metrics before a Workcell runs) is omitted, and the brief never fails for one.

**Error telemetry.** `foundry-telemetry.timer` runs `telemetry_fetch.py` every hour, and `brief_prep.sh` runs it once more before the brief. Each source in `system/telemetry/<name>.md` (written by `/setup` phase 6a, gitignored) is a set of Sentry projects or one Azure Data Explorer database with a filter. An empty filter value (`adx_filter: {deployment.instance: ""}`) selects the rows that lack that attribute, so shared services that log without it get a source of their own. A filter on one value and an empty filter on the same key never select the same row; a source with no filter (`{}`) overlaps both and counts their groups twice. Each error group becomes one `production_error` note in `raw/telemetry/` holding group keys, counts, times, opaque IDs, links and the Sentry issue title or one sample log message, ticket identifiers included; credentials and emails are masked. Sentry needs a read-only token in `~/.config/foundry/sentry.token` (mode 0600); ADX uses your `az login`. `--check <name>` tests a source, `--dry-run` prints the groups without writing.

**Work Orders.** `/order` queues refined work for an unattended run: an approved plan, or a task range of one, or a research brief written with you. Queuing is your approval, and a readiness check refuses items that are not refined enough. `foundry-nightshift.timer` ticks every 15 minutes on a standalone machine or a server (never a client) and runs one due item at a time. A Work Order starts now unless it was queued for a set time (`--at`) or for the run window (`--window`, the `run_window` setting). By default `run_window` is empty and the window is always open; a vault that sets one, such as `22:00-05:00`, keeps it. Before this update the window defaulted to `22:00-05:00`: if you relied on that, set `run_window: "22:00-05:00"` before updating, or Work Orders already queued for the window start at the next tick. No new Work Order starts while the last session's 5-hour usage is at or above `order_max_five_hour` (default `0.6`) and that reading is under 5 hours old; a running one carries on, and `/order status` shows the hold. Design sessions (brainstorm, spec, plan) hand an approved plan to the Foreman session, which queues it with `/order add`. Run the Foreman session and your design sessions in the same permission mode, so a handoff is not held for approval. A plan item runs in a private clone under `order_workspace`, is verified, pushed to a branch and ends in a pull request; it never merges or deploys. The sealed verify sees only `/usr/local/bin:/usr/bin:/bin` and nothing under `$HOME`, so a toolchain installed per user (nvm, volta, asdf, `~/.local/bin`) is not found and its command ends with `exit 127 (command not found in the sealed verify sandbox)`. Two optional keys in `system/codebases/<name>.md` open that up: `order_toolchain`, a list of directories (`~` allowed) that hold the toolchain's executables, which the sandbox binds read-only and puts first on its PATH (the rest of `$HOME` stays empty), and which lead the plan session's own PATH too; and `order_install`, one command (such as `pnpm install --frozen-lockfile --ignore-scripts`) that runs once, first, in the same private checkout with the network open, before the verify commands run offline. The install is the only sandboxed step with network, and the branch's lockfile decides what it fetches. Each sandboxed step starts with a fresh, empty `$HOME`, so the install must leave what verify needs inside the checkout: anything it puts under `$HOME` (a corepack-downloaded pnpm, a `packageManager` download, browser binaries) is gone by verify. The install runs from an empty cache every run, under the 30-minute step timeout, and without `--ignore-scripts` the branch's install scripts run with the network open. A failing install blocks the item like a failing check, as `Fix the failing check: order_install: <command>: exit <code>`. A listed directory that is gone when the item starts (an nvm upgrade, an item queued on a client with other paths) blocks it before the session runs, with the same wording queuing uses. List the directories the tools really live in; only those show through the empty `$HOME`, so a symlink into an unlisted directory dangles. For nvm that is `~/.nvm/versions/node/<version>/bin` and its `lib` sibling, since `npm`, `npx` and a globally installed `pnpm` there are symlinks into `../lib`. A shim directory that needs its manager's environment does not work in the sealed sandbox. Queuing refuses a listed directory that does not exist. A research item reads its sources and writes one findings note. Each item runs in a fresh, confined `claude -p` session that reads nothing of the vault, gets eight named environment variables and holds no credential. The session's sandbox and its Read tool deny the vault root, every other registered codebase and the common credential paths (`~/.ssh`, `~/.config/gh`, `~/.gitconfig`, the Claude transcripts under `~/.claude/projects` and its `settings*.json` among them). Its environment is `PATH`, `HOME`, `USER`, `LANG`, `TZ`, `TMPDIR`, `FOUNDRY_CLAUDE_BIN` and `CLAUDE_CONFIG_DIR`, each when set, and nothing else: an agent socket or a token in the unit's environment (`SSH_AUTH_SOCK`, `GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`) never reaches it, and the daily sandbox self-test fails when one of its probes (`SSH_AUTH_SOCK`, `GH_TOKEN`, `GITHUB_TOKEN`, `DBUS_SESSION_BUS_ADDRESS`, `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`) does. Everything else is dropped, `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, `SSL_CERT_FILE` and `NODE_EXTRA_CA_CERTS` included, so a vault behind a proxy or TLS inspection stops starting sessions, and the self-test's reason carries the session's result text and its last stderr line. A vault whose `claude` is logged in only through `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` therefore starts no Work Order session; the sandbox alert says so, and `claude login` (the credentials file the health check tests) is the login a session can use. After `claude login`, the self-test reruns on the next report day's first tick, or at once with `system/scripts/nightshift.py selftest`. `order_workspace` must sit outside the vault: the clone, a research item's context copy and its `out/` live there, and the session denies the vault root, so `/order add` answers `not ready: order_workspace is inside the vault` and an item already queued fails with a Needs-you line until the workspace moves. The report, `system/logs/nightshift/<date>.md` (heading `# Work Orders: <date>`), starts with a health banner, then "Needs you" (decisions only), which the brief adds to the Now page. Queue notes live in `raw/<partition>/nightshift/`, tracked in your vault so an item queued on a client reaches the server. A plan item for this template is read from `template_remote`: push its branch there before queuing it, and queuing checks the remote, which needs the network and the remote's credentials. Settings renamed with Work Orders: `run_window` was `nightshift_window`, `order_workspace` was `nightshift_workspace`, and a codebase's `order_pr`, `order_hosts` and `order_plugins` were `nightshift_pr`, `nightshift_hosts` and `nightshift_plugins`. The old names still work; rename them when convenient. The command, the skill and printed text say Work Orders; files, units, the queue folders and `nightshift.py` keep their names.

**The usage ceiling.** Every unattended session shares one Claude account's usage window. While the last 5-hour usage reading is at or above `order_max_five_hour` (default `0.6`) and under 5 hours old, intake ingests, the meetings fetch, inbox triage and new Work Orders wait: their inputs stay where they are, the next tick re-reads, and each raises one alert a day. The brief, the debrief and Slack notices never wait, nor does filing an RCA ticket you approved (one short session per ticked line). The reading comes from the session itself: every headless run, brief and debrief included, records the reading its stream reports, as Work Orders do, in `system/logs/nightshift/health-<date>.json`. A run keeps its full stream (`system/logs/runs/<run_id>/stream.jsonl`) only when it failed.

**Smoke check.** `foundry-smoke.timer` runs `smoke_check.sh` 15 minutes before the brief on a standalone machine or a server. It runs every configured fetch's `--check` (calendar always; meetings, handoffs, inbox triage, telemetry sources and the DTCC map when they are set up) and compares the `claude` version with `system/logs/claude.version`, then prints one line per source: `ok`, `failed: <reason>` or `off`. A failing source raises one `[smoke]` alert a day, which the brief lists under Blockers; a `claude` version change raises one alert naming both versions and the acceptance steps to re-run, then records the new version. Nothing is fixed or rolled back for you. The checks are logged to `system/logs/smoke-<YYYY-MM>.jsonl`. Slack notices are not checked: `notify.sh --check` posts a real message, so you run it by hand. Each connector check is one short confined session, so the run costs usage once a day; at the usage ceiling the connector checks are held (`held: <reading>`, one alert) and the local checks still run. To stop the daily check, run `systemctl --user disable --now foundry-smoke.timer`; later updates keep it disabled.

**DTCC change watcher.** It is for a codebase that integrates with DTCC Insurance & Retirement Services. `foundry-dtcc-watch.timer` runs `dtcc_watch.py` daily, 30 minutes before the brief. No model runs. It reads DTCC's public product pages, release dates, Important Notices and API catalog, and writes one `dtcc_change` note per change to `wiki/<partition>/changes/` with the codebase paths it touches. The brief adds each change to the Now page as an `owed` line, which stays until you tick it. The watcher does nothing until your vault has `system/dtcc/map.yaml` (start from `system/dtcc/map.example.yaml`).

**The Now page.** `wiki/<partition>/Now.md` is one checklist per partition of open loops: what you owe (`owed`), what you wait on (`waiting`) and messages not yet sent (`draft`). Each line is `- [ ] <kind>: <statement> (<who>, since <date>[, <evidence>])`. Sessions add lines with `system/scripts/now.py add`, and the brief adds its new objectives, DTCC changes and Work Order decisions. The brief's **From Now** block is a Dataview query over both pages: tick a line there (`[x]` done, `[-]` dropped) and the tick lands on the Now page. Every 5 minutes on a standalone machine or a server, the intake timer runs `now.py check`: a line whose evidence is a GitHub pull request that merged or closed, or a Work Order that is done, failed or cancelled, is ticked with `_(closed: <how> <date>)_`. A line you tick gets `_(closed: ticked <date>)_` on the page's next write (a line added or closed by evidence), not on a tick of its own, so the server rewrites a page the client edits less often; the stamp can be a day or two later than the tick. Closed lines leave the page 7 days after their stamp. In a lull, the Foreman runs `system/scripts/now.py review --partition <partition>` (read-only: lines closed by their evidence, open more than 14 days with no evidence, or duplicated; `--stale-days N` moves the threshold) and proposes the closes and merges to you as one batch; it ticks nothing itself. Session recall shows the session partition's open lines first. The first brief after this update creates your default partition's page from the previous brief's open objectives.

**Inbox triage.** With `triage_enabled: true` (`/setup` phase 6b), `foundry-triage.timer` runs `triage_fetch.sh` every 30 minutes on workdays from 08:00 to 18:00 on a standalone machine or a server. A confined `claude -p` session that may only search Gmail reads the inbox since the last tick (promotions, social and forums skipped) and lists the threads that need you: a person asks you something, waits on your answer, or reports a production problem. Each new message in such a thread becomes one `owed` line on the Now page of `triage_partition`, with its mail link, plus one `[triage]` alert line. The links and dates come from the search results, never from the model's words. It reads subjects and snippets, not full bodies. With `triage_watch_senders` set (domains such as `@example.com`, or addresses), each tick also searches those senders' unread mail outside the inbox from the last two days, and lists every such thread: mail archived unread by hand is not missed. It only reads; it never moves mail back to the inbox. A tick is skipped while the 5-hour usage is at or above `order_max_five_hour`, and a connector failure alerts once a day.

**RCA.** `/rca raw/telemetry/<note>.md` diagnoses one production error group in an interactive session, read-only on code: symptom to code areas through the index, the environment from the note, the logs the note stores, a trace to `file:line`, and a root-cause confidence and a fix confidence (1 to 5 each). It writes an `rca` note to `wiki/<partition>/rca/` with a Ticket draft and adds "Review RCA draft: …" to the Now page. Ticking that line approves filing: on the next intake tick, `rca_file.sh` runs a confined session that may only create one Jira issue, with the draft's summary and description and the `rca_*` settings, then writes the key back to the note. The tick marks the note `approved`, so the approval outlasts the line. A ticket is never filed twice: if a session called the create tool and no key came back, filing that draft stops with a `[rca]` alert until you find the ticket in Jira and record it with `system/scripts/rca.py filed <partition> <stem> <key>`, or delete the `.attempt` file the alert names to file again. Dropping the line (`[-]`) rejects a draft. Filing and rejecting are off until `rca_project` is set (`/setup` phase 6c). A draft marked `hotfix_candidate` also raises an alert line.

**Slack notices.** With `slack_notify_channel` set (`/setup` phase 6d), `foundry-notify.timer` runs `notify.sh` every 5 minutes on a standalone machine or a server. It sends one message with everything new since the last one: a brief that finished (how many Now lines need you, how many wait, how many alerts today, and a GitHub link to the briefing), a debrief that finished (its link), a brief or debrief that failed (its exit status), a Work Order that ended (its state and pull request or what it needs), and every new line in the day's alerts file (an alert repeated while a problem lasts goes out once a day, and inbox triage alerts go out as a count, never with mail text). With nothing new it starts no session. Otherwise one confined `claude -p` session that may only call the Slack connector's `slack_send_message` posts it. The connector is `slack_connector`, by default `claude.ai Slack` (Slack connected at claude.ai), which is what a headless session loads; when a session finds no Slack tool, `notify.sh` exits 3 and names the Slack server the session did load. A post that did not reach Slack is resent on the next tick, for events up to a day old. A session that breaks its rules (another tool or channel) stops notices until you read the `[notify]` alert and delete the hold file it names. No note text from `wiki/` is sent. Notices are not held at the usage ceiling, and they cannot be sent while the account's usage limit is reached. Empty `slack_notify_channel` turns them off.

**Active Projects.** An optional `wiki/<partition>/ActiveProjects.md` lists your project pages in priority order under `## Active`. Each morning, `active_projects.py` reads those pages, and the brief shows each project's next 3 open checkboxes and the open items under its "Decisions…" heading, as plain bullets. You tick items on the project page, so nothing is tracked twice.

**Meetings fetch: retrying a skipped Doc.** After three failed reads of one Gemini Doc (any non-zero exit, timeouts and usage limits included), the fetch alerts once ("`<id>` failed 3 reads; it is skipped from now on") and skips it, because it counts failures in this month's and last month's `system/logs/meetings_fetch-<YYYY-MM>.jsonl`. To fetch it again: delete that Doc's `"step": "read"` lines from those two log files, then set `system/logs/meetings_fetch.since` to a time before the Doc was created (ISO 8601, UTC), so the next run's search window includes it. The next fetch reads it once more; the `.since` file moves forward again on success. (#44)

**Debrief inputs.** The prep files in `system/logs/inputs/<date>/` (git commits, session digests, and `orders.md`, the open Work Orders report), alerts, the run ledger `system/logs/runs-<YYYY-MM>.jsonl`, the telemetry run log `system/logs/telemetry-<YYYY-MM>.jsonl`, and agent metrics in `system/logs/metrics/*.json`. An agent whose 3 most recent metric files all show `test_suite_passed: false` is reported under Agent Health; the debrief does not act on it.

**Handoffs and delivered work.** With `handoffs_site` and `handoffs_projects` set (`/setup` phase 6c), each brief runs `jira_fetch.sh`: a confined `claude -p` session that may call only the Atlassian connector's JQL search, with a query built from those settings. It lists under 🧾 Handoffs to chase the tickets you reported that someone else holds and that have had no status-category change for 7 days (the connector returns no change history, so a move inside one category, such as In Progress to In Review, does not reset the clock). The vault keeps no copy of the tickets. The debrief lists what you delivered under 6. Delivered Today: each digest's Delivered section, `delivered:` lines in the briefing's 📝 Notes (the Foreman adds one when you ask it to log something), and pull requests you opened, merged or reviewed in the registered GitHub repositories (`gh`, logged in; a codebase's `order_pr: github:<owner>/<repo>` and a GitHub `template_remote`).

**Workcells.** Work goes to the Workcell whose `capabilities` include the one the work needs, never by name:

| Workcell | Capabilities |
|---|---|
| `coding.md` | `code`, `tests`, `refactor`; writes a `compilation-metric.json` instance to `system/logs/metrics/` after each task |
| `maintenance.md` | `vault-health`, `dependencies`, `telemetry`, `alerts`; owns `raw/telemetry/` notes, which it checks against local branches of the affected codebase |
| `research.md` | `research`; answers a question within the session, read-only (index first, then named sources and public web pages), and hands the Foreman a findings note draft to file through `/ingest` or `raw/inbox/` |

**Friction.** Ingest sets `is_friction: "true"` when a fact's source text says "not sure", "waiting on", "stuck", "blocked", "tbd" or "double-check". The brief prints each flagged note's name once, the first morning after it is flagged, then counts it: "listed before" is read from the earlier briefings (the Friction part, or the old Friction notes bullet), so the two machines agree without a ledger.

**Intent proposals.** `system/templates/intent-shaper.md` creates a `plan_gate` note (`PENDING_REVIEW`, `APPROVED` or `REJECTED`) for a planned code change: its superpower, the upstream plan note it traces to, the files it touches, how it is verified and its blast radius.

## Memory

Memory is part of The Core. It is optional and off until you install its hooks. `/setup` offers them in its memory step: it shows the change `system/scripts/install_hooks.sh --dry-run` would make to your user-level `~/.claude/settings.json`, explains each entry, and installs only after an explicit yes. Declining leaves memory off; re-run `/setup` to turn it on later.

| Entry | What it does |
|---|---|
| `memory_recall.sh` (`SessionStart`) | Adds recent digests for the codebase or partition to a new session, up to `recall_budget_chars` (default 9,000 characters), marked as vault data, not instructions |
| `memory_capture.sh` (`Stop`) | After enough work (`digest_min_events` tool events and `digest_min_minutes` minutes since the last digest, default 5 and 20), asks for a short digest once, then redacts it and writes it to `raw/<partition>/notes/` |
| `memory_activity.sh` (`PostToolUse`) | Counts edits and Bash calls toward that threshold |
| three `permissions.allow` rules | Let codebase sessions run `vault_index.py related`, `show` and `backlinks`, which return only that codebase's partition plus `shared` |
| `~/.claude/commands/digest.md` | The `/digest` command, written only if you have no `digest.md` of your own |

The hooks run in every Claude Code session on the machine but act only inside the vault and registered codebases. Headless runs, subagents and `claude -p` scripts are skipped.

**"Stop hook error" is not an error.** Claude Code labels every request from a `Stop` hook "Stop hook error:". When the vault asks for a digest, you see `Stop hook error: Foundry memory (not an error): please reply with a short session digest. …`; Claude replies with the digest and the session carries on. The hook never asks twice in a row, and not when Claude's last reply ended with a question to you.

**`/digest`** writes a digest of the work since the last one whenever you want, in any session in scope. The `Stop` hook captures it from the reply; no script or session id is needed.

## Repository layout

The layout, abbreviated from spec §5. `/digest` is not in the repo: it is a user-level command that `install_hooks.sh` writes to `~/.claude/commands/digest.md`, so it works in codebase sessions too.

```
README.md                     your vault's own README (the template ships a landing page)
FOUNDRY.md                    this manual
CLAUDE.md                     generic rules; imports @system/config.md
.claude/settings.json         interactive permissions
.claude/commands/             setup brief debrief ingest query lint backup impact
.claude/skills/humanizer/     vendored humanizer v3.0.0 (MIT): /humanizer, headless self-edit
.claude/skills/order/         /order: queue plans and research briefs as Work Orders
.claude/skills/dtcc-watch/    /dtcc-watch: the DTCC change watcher by hand
.githooks/pre-commit          deterministic linter (lint_vault.sh --staged); redacts staged drops (redact.py --drop); refuses secret shapes (secret_scan.py --staged)
.scratch/                     throwaway clones, worktrees and temp files (ignored; the gate's temp files go here)
raw/                          contents gitignored
  inbox/ archive/ telemetry/  manual drops, compiled drops, production-error notes
  <partition>/notes|archive/  session digests and meeting inputs (created on demand)
  meetings/                   fetched Gemini notes awaiting import
meetings/drop/work|personal/  dropped meeting transcripts (redacted by the hook on commit, synced; imported, then removed)
wiki/
  Index.md                    cross-partition index, Dataview dashboards
  work/ personal/ shared/     concepts/ entities/ summaries/ preferences/
  work/ personal/meetings/    meeting notes and their transcripts
  .staging/                   headless output awaiting publish (gitignored)
briefings/                    today's and yesterday's briefs and debriefs; earlier days in archive/<YYYY-MM>/
system/
  config.example.md           example global config (real config.md is gitignored)
  codebases/example.md        example codebase file
  telemetry/example.md        example error source (real sources are gitignored)
  dtcc/map.example.yaml       example DTCC watch map (your map.yaml is tracked in your vault)
  nightshift/                 session profiles for Work Order plan and research runs
  headless.settings.json      headless permissions
  template_source             canonical template URL
  schemas/                    one schema note per note type
  hooks/                      user-level memory hooks
  templates/                  briefing, debrief, concept, intent-shaper, compilation-metric.json
  agents/                     foreman.md (the Foreman persona)
    workcells/                coding.md, maintenance.md, research.md: one per Workcell, with its capabilities
  scripts/                    vault_index.py, vaultlib/, publish_staged.py, run_headless.sh,
                              intake_daemon.sh, install_units.sh, install_hooks.sh,
                              setup_remote.sh, update_template.sh, check_deps.sh,
                              vault_sync.sh, commit_runs.py, calendar_fetch.sh, meetings_fetch.sh, telemetry_fetch.py,
                              nightshift.py, dtcc_watch.py, active_projects.py, ...
  systemd/                    foundry-{intake,brief,debrief,sync,telemetry,meetings,triage,notify,nightshift,update,dtcc-watch} unit templates (*.in)
    dropins/                  foundry-sync.conf.in: sync before and after each run (server)
  tests/                      *.bats per area (system_health.bats is advisory), python/ for pytest
  jobs/                       reserved for Sub-project 2 (gitignored)
docs/superpowers/             specs, plans, spike results
```

## Machine roles

Each machine that holds the vault has a `machine_role` in its own `system/config.md`, chosen in `/setup`:

| Role | Runs | Use it for |
|---|---|---|
| `standalone` (default) | intake, brief, debrief and smoke check units, and the meetings fetch when enabled; memory hooks; codebases | one machine that does everything |
| `server` | intake, brief, debrief, smoke check and sync units, and the meetings fetch when enabled; memory hooks; codebases | an always-on machine that runs the automation and your coding sessions |
| `client` | nothing automated | reading and editing the vault in Obsidian on another machine |

A server and its clients share the vault through a private `origin` (`remote_mode: private`):

- **Server.** `vault_sync.sh` runs every `sync_interval_minutes` (`foundry-sync.timer`) and before and after every run: it commits headless runs and other changes with scripted messages, merges `origin` and pushes. A run whose note the pre-commit hook refuses stays pending with one `[commit_runs]` alert a day, its note is left out of the sync commit, and the cycle goes on; the daily template update waits for it to be fixed. Network and credential failures never stop the runs; they are alerted once a day until sync works again.
- **Client.** The Obsidian Git plugin commits and syncs every few minutes; `/setup` prints its settings. Write notes in today's briefing between the `#wiki-ingest-start` and `#wiki-ingest-end` markers already in 📝 Notes: the server sends that block to the wiki once, at 05:00 the next morning, so you can edit it all day and the night's sync can bring your last edits over. A block you mark anywhere else in the briefing is compiled within a few minutes. The briefing stays as it is (on every role, blocks stay in the briefing after compiling). Edits that reach the server after 05:00 the next morning are not sent. Files in `raw/inbox/` on a client are not synced. Meeting transcripts dropped into `meetings/drop/<partition>/` are synced, and the server imports them; move a finished file in (an empty one is quarantined). A drop is redacted by the pre-commit hook when it is committed: the file in the folder and the commit both get the redacted text (the same redaction the import applies, with `[REDACTED:…]` in place of each secret), so the raw copy is gone once Obsidian Git commits and the pushed history holds nothing the published transcript does not. Drive links are stripped as the import strips them. A UTF-16 file is rewritten as UTF-8; a file in another encoding is read as UTF-8 with replacement characters, as the import reads it; one that holds NUL bytes once decoded is refused, and the hook names it. The hook also refuses a drop that is a symlink or that has unstaged changes (stage the whole file). Obsidian mobile runs no git hooks, so a drop from a phone is redacted only at import.

### Sync conflicts

A conflict is never resolved automatically. The server aborts the merge, pushes its side to `foundry/server-pending` on `origin`, writes `system/logs/sync-blocked`, alerts once, and skips intake, brief and debrief until it is resolved. Resolve it on the other machine (for `foundry/server-pending`, a client):

```sh
git fetch origin
git merge origin/foundry/server-pending   # a client's own conflict uses origin/foundry/client-pending
# fix the conflicted files, then
git commit
git push
```

On the machine that pushed the pending branch, its side is already checked out: run `git merge origin/<branch>` there instead (`<branch>` is the vault's branch), then resolve, commit and push.

The next server sync clears the marker, deletes the pending branch and starts a brief or debrief that was skipped today.

`wiki/<partition>/Now.md` is the one note both machines write: you tick lines on the client, and the server closes lines on checked evidence. The server rewrites the page only when it closes a line, but a tick on the client next to a line the server just closed can still conflict. Resolve it as above, keeping both changes. The pre-commit hook rejects any file that still holds conflict markers; if a client note that bypassed the hook blocks your commit, the hook names it: fix it, or commit with `--no-verify` knowingly.

## Requirements

The Foundry runs on Arch / Omarchy and on Debian. `system/scripts/check_deps.sh --role <role>` checks what that role needs and prints `pacman` or `apt` install hints:

- `claude` (Claude Code), `git`, `jq`, `flock`, `timeout`
- `python3` with PyYAML (`sudo pacman -S python-yaml`). Missing PyYAML blocks setup.
- `sqlite3` built with FTS5
- systemd user units (`systemctl --user`, `systemd-analyze`). If you want timers to run while you are logged out, enable lingering.
- `bwrap` (bubblewrap): headless runs turn Claude Code's sandbox on.
- A Google Calendar connector on the Claude account the brief machine is logged in with, for calendar input to the brief. Without it the brief lists the calendar under Unavailable Sources. Each morning fetch costs about $0.20.
- A client needs only `claude`, `git`, `jq`, `python3` with PyYAML, and SQLite with FTS5.
- Optional: the Azure CLI (`az`, logged in) for ADX error sources, and a read-only Sentry token for Sentry sources. Without them those sources stay off.
- Optional: `pdftotext` (`poppler` on Arch, `poppler-utils` on Debian) for the DTCC change watcher, which reads the header of each notice's PDF.
- Optional: `herdr` or `tmux` as session backends for sub-project 2
- Development tools, for changing the template (`check_deps.sh` lists them as `dev`): `bats`, `pytest` and `shellcheck`. Without them `verify_setup.sh` and `/backup` lint the vault and skip the test suites.
- Obsidian, with the **Dataview** plugin recommended (`wiki/Index.md` dashboards are plain code blocks without it). **[Vault Curate](https://github.com/notoriouslab/vault-curate)** is an optional plugin for link suggestions. It is not a dependency.

## Getting started

Before you start, install what [Requirements](#requirements) lists and sign in to Claude Code (`claude`, then `/login`). For a server or a client, also create an **empty private repository** for your vault on your git host (no README, license or `.gitignore`, so it has no commit of its own to reconcile): that is your private `origin`, and every machine syncs through it.

**First machine (standalone or server).** Clone the template (a repository created from a hosting site's template button shares no history with it, so template updates cannot merge), start Claude Code in it, and paste the prompt below with your answers filled in:

```sh
git clone <template-url> my-vault
cd my-vault
claude
```

**A client.** Set up the first machine first. Then clone your private vault (not the template) and paste the same prompt with `client` as the role:

```sh
git clone <private origin> my-vault
cd my-vault
claude
```

The prompt (replace every `<…>` first; `/setup` asks for any answer still written as `<…>`):

```text
Set up this clone as a new Foundry vault. Run /setup and use these answers; ask me only for what is missing:
- Machine role: <standalone | server | client>
- Brief at <HH:MM>; debrief at <HH:MM>
- Remote: private, origin <private origin URL>   (or: none, standalone only)
- Features: <any of codebases (paths), memory hooks, calendar, telemetry, meetings,
  inbox triage, Jira handoffs, Slack notices, Work Orders, template update; or none>
                                                  (not used on a client)
Never push to the template repository. Before installing units or memory hooks,
show me what will change and wait for my yes. Run any command that needs sudo
(linger) only by giving it to me. When you finish, show the /setup report table
and list what I still have to do by hand.
```

You can also type `/setup` and answer its questions one at a time; the prompt only gives it the answers up front. On a server, `/setup` stops at the units phase until linger is on (`sudo loginctl enable-linger $USER`, which you run yourself). On a client it ends with the Obsidian Git settings to enter and asks you to make one test edit.

`/setup` is idempotent and can be re-run at any time. Its phases (spec §11):

- **0. Role and preflight:** you choose the machine role, then `check_deps.sh --role <role>` lists missing items with install hints. A vault path with a space stops setup (the memory hooks cannot run from it). A client gets no features list and skips phases 3, 6, 6a to 6d, 9, 9a and 11; on a client, phases 5 and 5a only remove units and hooks left from an earlier role.
- **1. Existing config:** if `system/config.md` already exists, it is shown and edited, not overwritten.
- **2. Interview:** the brief and debrief times. The timezone is read from the machine; superpowers, the default partition, digest thresholds and the recall budget keep their defaults, and the report says how to change them.
- **2a. Features:** one numbered list of the optional blocks below, with their current state; you pick the ones to set up or change, once. Blocks you do not pick are left as they are.
- **3. Codebases:** you choose repos from a directory scan. Each one is inspected, drafted as `system/codebases/<name>.md` with a partition, and shown to you once to accept or correct.
- **4. Remote:** the template `origin` of a plain clone is renamed `template` for updates, and you choose a private `origin`, no remote, or keep (maintainer mode). A server or client must use a private `origin`; setup checks that git can reach it without a prompt and publishes the branch.
- **5. Units:** the role's systemd units, plus those the features you picked turn on (Work Orders, the template update, meetings, inbox triage), are rendered and enabled on your yes, and you are offered linger (required on a server).
- **5a. Memory hooks:** you are shown the diff to `~/.claude/settings.json` and what each hook does, and it is applied only after an explicit yes. Declining leaves memory off (see [Memory](#memory)).
- **6. Calendar:** one fetch from the Google Calendar connector checks that the brief can read today's events.
- **6a. Telemetry:** Sentry and Azure Data Explorer error sources, each checked.
- **6b. Meetings and inbox triage:** the meetings partition and your names in action items; the Now page triage writes to; each connector checked.
- **6c. Handoffs:** the Jira site and projects the brief reads, and whether approved `/rca` drafts are filed.
- **6d. Slack notices:** the channel, and a test message only on your yes.
- **7. Index:** the index is rebuilt and the run-commit cutover is recorded (`commit_runs.py --init-cutover`).
- **8. Verify:** `verify_setup.sh --health` runs (lint, then the test suites when the development tools are installed).
- **9. Hand-off:** an onboarding assignment note is created for each codebase.
- **9a. README:** the template's landing page is replaced with your vault's own README.
- **10. Report:** the Obsidian plugins, then a status table of everything that was set up.
- **11. First brief:** `/brief` runs, so you read a brief before setup ends.

Once the units are installed, the timers run real headless `claude -p` jobs. They use your Claude subscription and are capped at 60 runs a day (`HEADLESS_MAX_RUNS_PER_DAY`).

## Security model

- **Headless isolation.** Automation calls `claude` in three ways. `run_headless.sh` runs the vault's own commands; `system/scripts/lib_connector.sh` runs every connector session (calendar, meetings, handoffs, triage, notices, RCA filing): one connector tool allowed, every other tool denied, `dontAsk`, a fresh directory, a timeout, and a checker that reads the session's tool use afterwards; and the Work Order session (`vaultlib/nightshift_session.py`) runs an approved plan under its own profile (Work Orders, below): the deny list is the profile's `denyRead` plus `CREDENTIALS`, the vault root and every other registered codebase, each entry fencing sandboxed Bash and, as a `Read(...)` rule, the Read tool; the environment is the `session_env()` allowlist of eight variables. `run_headless.sh` runs in restricted mode with a dedicated settings file, no user settings, no user hooks, no MCP servers, no session persistence, a tool list per command, a timeout and a daily run cap. Reads are limited to the vault, writes are limited to the run's staging directory, and Bash runs in Claude Code's sandbox (no network) with sandbox auto-allow turned off, so only allowlisted commands run.
- **Staged publish.** Headless output reaches the wiki only through the publish gate, which checks targets, schemas, partition walls, protected fields, shrinkage and conflicts. Every headless-written note gets `headless` added to its `provenance`.
- **Partition walls.** Links from `work` to `personal` (and the other way) are lint errors. A headless run writes to one partition plus `shared`. From a codebase session, the index CLI returns only that codebase's partition plus `shared`, and those sessions get no general read access to the vault. Walls control links and recall, not storage: all partitions are pushed to the same private `origin`.
- **Data, not instructions.** `CLAUDE.md` tells agents to treat note bodies, raw files, recall blocks and tool output as data. Digests and inbox copies are passed through `redact.py`, and `<private>…</private>` spans are removed. A transcript drop is passed through the same redaction twice: by the pre-commit hook when it is committed (so the pushed blob is already redacted) and by the import.
- **Secret shapes.** The pre-commit hook scans every staged file with the credential shapes `redact.py` redacts (cloud, git host, chat and model API keys, JWTs, PEM private keys, US Social Security numbers) and refuses the commit while one is found, printing `secret shape: <path>:<line>: <shape>` and never the value. It reads the staged copy, so fixing the file on disk is not enough: stage the fix. If the shape list cannot be read or the scanner is missing, the commit is refused as unscanned. `/lint` reports the same shapes over tracked and untracked files without failing. Both skip `.scratch/` and binary files; `/lint` also skips `system/tests/` and `docs/superpowers/`, whose fake tokens are test fixtures. The only way past a refusal is `git commit --no-verify`, for a match that is not a secret (a hand-resolved template update conflict that stages those fixtures is one). Obsidian mobile runs no hooks, so a secret committed from a phone shows up only in the next `/lint`.
- **Error telemetry.** `telemetry_fetch.py` runs no model and keeps network access out of headless runs. Sentry and ADX responses are reduced to group keys, counts and one title or sample message before anything is written. Group keys keep their shape (GUIDs, emails, long hex and digit runs, URL query strings collapsed); titles and messages keep ticket identifiers with credentials and emails masked; the note store re-checks every field. The Sentry token lives outside the vault, so git and sync never carry it.
- **User-level changes.** `install_hooks.sh` changes only its own entries in `~/.claude/settings.json` and `~/.claude/commands/digest.md`. It takes a backup first, shows a diff during `/setup`, applies nothing without confirmation, and can be fully reversed with `--uninstall`.
- **Trust dialog.** The first time you open the vault, Claude Code asks whether to trust the folder and lists the permissions `.claude/settings.json` pre-approves: edits under `wiki/`, `briefings/`, `docs/` and `.scratch/`; the vault scripts the commands run (the prep scripts, `now.py`, `lint_vault.sh`, the `vault_index.py` read, rebuild and recall commands, the Work Order queue commands, `dtcc_watch.py` runs and status, the telemetry checks, `commit_runs.py` and `vault_sync.sh`, the `--check` and `--dry-run` forms of the setup scripts, `verify_setup.sh` and the health suite); and the `git` commands `/backup`, `/order` and `/setup` run against the configured remotes (`status`, `add -A`, `commit -m`, a plain `push` or `push -u origin HEAD`, `fetch` from `template`, `show`, `remote get-url`, `config user.name` and `user.email`). Still a prompt, by design: `vault_index.py set` (a config change), `install_units.sh` and `install_hooks.sh` without `--dry-run`, `update_template.sh`, `dtcc_watch.py --accept`, `nightshift.py tick`, any push to another remote or with `--force`, every connector write (sending mail or chat, creating events, moving tickets) and every command outside the vault. Those apply to your interactive sessions only; headless runs ignore project settings entirely. Start the Foreman session with the same permission mode as your design sessions (see Work Orders); with the rules above, `acceptEdits` leaves only those boundary prompts, and the Foreman can reach a registered codebase because `/setup` lists it under `additionalDirectories` in `.claude/settings.local.json`. Connector reads a Foreman session uses every day (mail and chat search, calendar reads, ticket lookups) are vault-specific tool names and go in your vault's own copy of the file, above the template block.
- **Gitignored.** `raw/**` contents, `system/quarantine/*`, `system/logs/*`, `system/config.md` (it holds the machine role), `.claude/settings.local.json`, `system/index.db*`, `system/*.lock`, `wiki/.staging/`, `system/jobs/` and Obsidian workspace files.
- **Tracked in your vault, never in the template.** Your vault's `README.md` (the template ships only its landing page), `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Work Order queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).

## Updating and uninstalling

- **Pull template updates:** `system/scripts/update_template.sh`. Run by hand it refuses to run on a dirty tree; it fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders only the units this vault installed. A unit the update adds is listed as `new unit available: <unit>` and left out; read `system/scripts/install_units.sh --dry-run`, then run `system/scripts/install_units.sh` to add it. On a standalone machine or a server, `foundry-update.timer` runs it every morning 45 minutes before the brief (`update_template.sh --unattended`, #87), ahead of the DTCC watcher 30 minutes before it (#117) and the smoke check 15 minutes before it, so a fetch the update broke is usually in the alerts before the brief reads them (on a server a long update can still be running then). It waits for `run.lock` and skips the day if another run holds it, commits uncommitted changes first, as the sync does (`commit_runs.py`, then one `sync(<role>)` commit of everything else, half-written notes included), and aborts a conflicted merge (`git merge --abort`), leaving the vault unchanged. A sync commit the pre-commit hook refuses stops the update with the hook's line and nothing is fetched. A published run the hook refuses stops it too: the other runs and the sync commit land, nothing is fetched, and the `[update]` line names the refused paths and points at the same day's `[commit_runs]` alert, which carries the hook's line. It reports each of those, and a successful update with what it committed and the template pull requests it merged, as an `[update]` line in the alerts the brief reads; the line always lists the commits it made, so a day with nothing new to merge is silent only when there was nothing to commit. On a server the sync runs before and after it. A client gets updates through sync. Rollout: a standalone vault that is dirty every morning is still running the old script, which stops before merging, so run `/backup` once and the next morning's update brings this change. To stop the daily update, run `systemctl --user disable --now foundry-update.timer`; later updates keep it disabled.
- **Your README survives updates:** for its own merge only, `update_template.sh` marks `README.md` `merge=ours` and defines that driver (`git -c core.attributesFile=… -c merge.ours.driver=true merge`). A README your vault has changed keeps your version, on the first update too; one you never edited takes the template's landing page. Sync merges between your machines define no driver, so a README edited on two machines conflicts as usual and nothing is lost. `/setup` writes a starting README while yours is still the landing page.
- **The first update with the briefing archive:** the first brief after it moves every briefing older than yesterday into `briefings/archive/`, and the next sync lints them all, so run `system/scripts/lint_vault.sh` before updating and fix what it reports.
- **Update the humanizer skill:** `.claude/skills/humanizer/` is humanizer v3.0.0, copied unchanged with its MIT license. To move to a newer version, copy the new `SKILL.md` and `LICENSE` over it by hand in the template repo, then update the version and checksum in `system/tests/vault_integrity.bats` and the version in this manual. Vaults receive it through `update_template.sh`.
- **Remove systemd units:** `system/scripts/install_units.sh --uninstall` removes only units whose header names this vault.
- **Remove memory hooks:** `system/scripts/install_hooks.sh --uninstall` removes only the entries owned by this vault, any container the install had to create, and the owned `/digest` command. It still works if the hook files are gone.

Both installers also accept `--dry-run`.

## Development

Work follows the superpowers workflow: brainstorm → spec in [`docs/superpowers/specs/`](docs/superpowers/specs/) → plan in [`docs/superpowers/plans/`](docs/superpowers/plans/) → test-driven implementation in small, focused commits. Spike results go in [`docs/superpowers/spikes/`](docs/superpowers/spikes/). Every finding from the design reviews is traced in spec §13.

**Two lanes.** That workflow is the feature lane. A fix takes the fast lane and skips the grill, the spec and the plan. A fix is a change whose scope is clear from one sentence, with one failing test that passes after the change and the gate green, that touches none of the safety surfaces: permissions and settings files, the sandbox, the publish gate, redaction, and new note types. A fix that edits the `ingest`, `brief` or `debrief` command text also re-runs the live acceptance steps (below). It ships as a pull request whose body is the issue line or review finding it fixes and the name of its test. A fix may run as a Work Order: the readiness check reads the plan from a file committed at the Work Order's base, so it then needs a short plan file with its `### Task N:` list. A fix that grows past its sentence, or draws a design question in review, stops and becomes a feature; the default when in doubt is the feature lane.

The gating suites must pass at the end of every task. Install the development tools first (`bats`, `pytest`, `shellcheck`, and optionally `parallel` (GNU) and `pytest-xdist`): without the first two the gate lints only and prints `SKIP suites` in its summary. The gate runs the bats suites side by side when GNU `parallel` is installed and spreads pytest over every core when `pytest-xdist` is. In the template repository, CI runs the same gate on every pull request. One command runs them all and exits non-zero if any fails:

```sh
system/scripts/verify_setup.sh            # lint, every system/tests/*.bats except system_health.bats, then pytest
system/scripts/verify_setup.sh --health   # also the advisory live-state suite
```

One suite or one pytest target runs through `system/scripts/test.sh <suite.bats | pytest path> [args…]`, which sets the gate's environment (temp files under `.scratch/tmp`, a git ceiling) so no command needs a leading `TMPDIR=` assignment. Plans name it in their test steps.

`vault_integrity.bats` fails when a tracked template file holds a name from your forbidden-names list, kept outside the repository at `$FOUNDRY_FORBIDDEN_NAMES` (default `~/.config/foundry/forbidden-names`, one case-insensitive name per line, `#` comments); it reports `<path>:<line>` and the list line, never the name, and skips when the list is absent or the checkout is a vault.

**Permissions while developing.** The template's `.claude/settings.json` allows only the read-only vault commands, because vaults merge it (fewer-prompts spec). Development commands go in `.claude/settings.local.json` (gitignored; "Yes, and don't ask again" writes there too), for example:

```json
{"permissions": {"defaultMode": "acceptEdits", "allow": [
  "Bash(system/scripts/test.sh *)", "Bash(system/scripts/verify_setup.sh*)", "Bash(shellcheck *)",
  "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)", "Bash(git show*)", "Bash(git fetch *)",
  "Bash(git add *)", "Bash(git commit *)", "Bash(git checkout -b *)", "Bash(git switch *)",
  "Bash(mkdir -p .scratch*)"]}}
```

A rule matches one plain command: a leading assignment other than a few known-safe variables, a `&&` chain, a loop or a redirect each draw a prompt again, which is why `CLAUDE.md`'s Bash line forbids them and why `test.sh` exists. The `auto` permission mode (a classifier approves routine calls) is honoured only in `~/.claude/settings.json` or on the command line (`claude --permission-mode auto`); a project or local file silently ignores it. An approved plan needs no prompts at all when it runs as a Work Order (`/order add`): the session runs with `--permission-mode dontAsk` and a fixed tool list.

`system/tests/system_health.bats` checks live service state and is advisory only. To prove the suite on Debian, run `system/tests/verify_on_host.sh <ssh-host>`: it copies the committed tree to a temporary directory on that host, runs the gate there, and exits with its code. The host needs the `apt` packages `check_deps.sh` lists, its `dev` tools included: the script runs `verify_setup.sh --require-suites`, which fails rather than skip the suites. After any change to `run_headless.sh` or the settings files, re-run the spike checklist (spec §7.4) by hand. After any change to `run_headless.sh`, `system/headless.settings.json` or the `ingest`, `brief` or `debrief` commands, re-run the live acceptance steps (Plan 4a, Task 9) in a throwaway clone. After a change to `lib_connector.sh` or a `claude` version change, one `system/scripts/calendar_fetch.sh` run from a throwaway clone proves the connector flags: that file is the one place they live. On a live vault a `[smoke] version` alert is the trigger: the daily smoke check records the version in `system/logs/claude.version` and reports a change once.

## Acknowledgements

- Yonatan Karp, [The self-compiling second brain](https://yonatankarp.com/blog/self-compiling-second-brain/): the capture → compile → recall model.
- [firstmate](https://github.com/kunchenguid/firstmate): the model for the Foreman orchestrator (Sub-project 2).
- [humanizer](https://github.com/blader/humanizer) by Siqi Chen (MIT): vendored in `.claude/skills/humanizer/`; its wording rules are condensed in `CLAUDE.md` and applied by the headless commands before they write.
- Projects from the ecosystem survey (spec §13.5). Each one contributed a design pattern; none is a dependency:
  - [open-second-brain](https://github.com/itechmeat/open-second-brain): corrections → preference notes with evidence
  - [DocMason](https://github.com/JetXu-LLM/DocMason), [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian): stage → validate → atomic publish
  - [second-brain-cloudflare](https://github.com/rahilp/second-brain-cloudflare), [agentmemory](https://github.com/rohitg00/agentmemory), [sage-wiki](https://github.com/xoai/sage-wiki): note lifecycle fields, `<private>` redaction, per-source caps
  - [chubbyskills](https://github.com/chubbyguan/chubbyskills): content-hash duplicate skip, run ledger, retry
  - [memU](https://github.com/NevaMind-AI/memU): explicit noop / patch / create decisions
  - [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory): recall item caps and timeout
  - [makerskills](https://github.com/coreyhaines31/makerskills): contradiction, staleness and topic-gap lint checks
  - [agent-second-brain](https://github.com/smixs/agent-second-brain): daily headless run cap
  - [Vault Curate](https://github.com/notoriouslab/vault-curate): optional link-suggestion plugin
