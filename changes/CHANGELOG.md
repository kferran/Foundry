# Changelog

What changed in The Foundry up to 2026-10-26, newest first. This file is frozen: each later change is its own file in this folder (FOUNDRY.md, Release notes).

## Changes

## 2026-10-24
- Changed: interactive sessions no longer ask before nine read-only commands: `now.py overdue` and `now.py --help`, `extensions.py check` and `allow` (without `--write`), `intake.py --quarantine`, `systemctl --user status`, `is-active` and `is-enabled`, and `journalctl --user`. (#393)
- Added: the `console` extension's Python side (#377, C1.2): `today.py --json` gathers the Today screen (focus projects, Now lines with their bands, Work Orders, the morning's calendar and meeting actions, the pipeline) into one object by running the core `--json` commands, and `today.py --check` is its smoke row; `build.sh` builds the app outside the vault, `serve.sh` starts it on `127.0.0.1`, and `foundry-console` is an always-on unit. The web app itself ships next (C1.3), so nothing is served yet. (#391)
- Added: an extension unit with `timer: false` is always on: `install_units.sh` installs and enables its `.service` alone, and a client installs it when its `roles` list `client` (the first units a client runs). `extensions.py units <role>` prints a third column, `timer` or `service`. For the console's web server (#377). (#389)
- Changed: `/rca` no longer adds a "Review RCA draft" line to the Now page; its Ticket draft is for filing by hand. `/rca <note> --file` adds the line as before, and ticking it files the ticket. (#333)
- Changed: FOUNDRY.md opens with **What the Foundry offers**: every feature with what turns it on, the unit that runs it, its smoke row and its output, and what each extension needs. **The factory line**, under Development, is the builders' entry point and ends with how to add a Source. A test fails when a command, skill, extension or unit ships without its row. (#331)
- Changed: the today file masks credentials in an item's link, as it does its text, and refuses a symlinked file. Interactive `/brief`, `/debrief` and `/rca` end with `system/scripts/lint_vault.sh`, as `/ingest` does. Lint walls every note but `wiki/Index.md`, as the publish gate does: a note of `type: index` elsewhere that links across partitions is now a lint error. (#310)
- Added: `--json` on `now.py list`, `active_projects.py`, `nightshift.py list` and `nightshift.py report`, for the console extension's reads (#377). Each prints one object starting `"v": 1`; text output is unchanged, and `report --json` writes no report file. (#378)

## 2026-10-23
- Added: the `health` extension. Monday's brief carries a 🩺 Health scorecard of the platform and the factory (source ticks, headless runs, the brief's time and size, the Now pages, cost, sync blocks, budget headroom and, with `gh`, defect recurrences, first-push CI and review fixes); other days show one Pipeline line per metric past its threshold. Off until listed. (#374)
  - Action: add `health` to `extensions` in `system/config.md`, and fill `health_defect_gates` as gates land.
- Changed: every write to a Now page (`now.py add`, `set` and `note`, inbox triage, the intraday watch, the RCA filer, a brief's new lines) redacts credential-shaped text, keeps the line to 300 characters and refuses a link across the partition wall; a symlinked Now page is refused. Triage, the watch and the RCA filer drop a refused line and raise one alert that day naming the reason, never the line. The publish gate checks a brief's added Now lines the same way, and the brief fixes them before publish. (#310)
- Changed: a Slack notice posted with drift keeps its collected text and posting session in `system/logs/notify/drift/` (the latest one only), and the drift alert names that folder.
- Fixed: a Now line the morning brief adds over 300 characters is cut to fit before publish, as triage's are; one long line no longer drops the whole briefing. (#365)
- Changed: `CLAUDE.md` is shorter. The Now rule points at `system/scripts/now.py add --help`, which now prints the flags, the evidence forms and the `--rec` and `--due` rules. The directory map names `extensions/<name>/` and `wiki/<partition>/rca/`, the Schemas rule names extension schemas, the Scannable layouts rule is one line, and the headings carry no emoji. (#361)
- Fixed: the lint no longer reports a link as ambiguous because a file in `system/logs/` (a prep input or a run log) shares its name; a bare `[[Name]]` never resolves to a log file. Archived briefings no longer warn when they link to a note retired since. The brief's What changed section links `[[CHANGELOG]]`, which resolves from archived briefings too. (#361)
- Changed: `/lint`'s stale-note check uses the new `system/scripts/vault_index.py stale`, which dates each active compiled note by its last commit (by `compiled_at` when the note was never committed), so a patched note no longer counts as stale. Briefings written before this update keep their old CHANGELOG link, which still warns as a dead link. (#361)
- Added: `/foundry-review`, a development skill that checks a branch's diff for nine defect classes that tests miss (unredacted Now writers, writes around the publish gate, outside text in alerts, sleeps in tests, skips with no reason, a missing CHANGELOG line or defect label, and three Source rule hand-offs) before its pull request opens. Specs that name a blueprint now carry a `## Blueprint checklist` section, checked in CI. (#309)
- Added: `/new-source`, a development skill that scaffolds an extension Source (fetch, checker, manifest, budget, alert tag, brief prep and tests) that passes CI before any feature code is written. (#309)
- Added: `/foundry-review`, a development skill that runs nine checks on a branch's diff for defect classes that tests miss (unredacted Now writers, writes around the publish gate, outside text in alerts, sleeps in tests, skips with no reason, a missing CHANGELOG line or defect label, and three Source rule hand-offs) before its pull request opens. Specs that name a blueprint now carry a `## Blueprint checklist` section, checked in CI. (#309)

## 2026-10-22
- Changed: an extension's alert tags, intake route and `system/<extension>/` folder now come from its manifest, and extension scripts import core only through `vaultlib/api.py`; a vault's own extension that imports another `vaultlib` module fails its tests until it imports from the API. (#307)
- Changed: the core line budget counts `system/hooks` and `.claude/commands` with `system/scripts`, capped at 15,000 lines in the template; a vault prints its count and skips the cap. Extension manifests state their time budgets in a new `budget` field, checked against the scripts' defaults. (#308)
- Changed: every core Python script reads `system/config.md` through one reader. Triage, notices, the intraday watch and Work Orders (the add-time check and the tick) no longer stop on a config file that cannot be read; they use their defaults like the other scripts, and a template Work Order is refused (`config has no template_remote`). (#308)

## 2026-10-21
- Changed: the intraday watch checks its sessions with the shared connector parts. A Gmail search with a pageSize other than 10 now fails the mail session (exit 7), and a search past its page limit fails at that call, even when an earlier page errored. Some failure reasons in `watch_fetch` log lines read differently ("the session called <tool> with other arguments than the ones built for this run", "a <search> result was too large for the model to read", "the session made <n> <search> calls; the limit is <n>"); exit codes and alert keys are unchanged. (#339)
- Changed: the calendar fetch now fails a session that replied `ok` without ever calling `list_events`, where it used to pass an empty day. It exits 3 ("no Google Calendar connector reachable") when the session never found the tool, and 1 when it found the tool and did not call it. The unexpected-tool exit (7) now names the first unexpected tool, and the log's `unexpected_tools` still lists all of them. A `list_events` page that claude cut short or saved to disk now also exits 6 with the `pageSize` hint. (#336)
- Fixed: inbox triage reads mail in pages of 10, at most 60 threads a tick (was 3 pages of 50). A page of 50 threads can pass the size the model can read, and the model then sees none of them; that cost the intraday watch its mail in #289 and is not confirmed for triage. A page still too large keeps triage's place in the inbox and raises one [triage] alert a day, and each tick's log line counts the threads returned and the rows kept and dropped. (#334)
- Fixed: a research Work Order whose session runs `cd` (into `code/` or `context/`) now publishes its findings note; before, the write to `out/` was denied and the item failed with `no result`. A write to `out/` the profile still denies now fails the item as `out write denied`, naming the path and the item's `stream.jsonl`. Headless runs' private-folder denies now also hold for the Read and Edit tools after a `cd`. (#327)
- Fixed: the publish gate also rejects a staged file that is a hard link ("staged file is a hard link"), and a run whose staging or run folder is a symlink fails at its start. (#328)
- Fixed: the publish gate no longer writes through a symlink. A headless run whose note, folder, staging folder or journal has a symlink on its path is rejected with "symlink on the target path" (or "staged path is a symlink") and the usual alert, so a linked folder under `wiki/` can no longer carry a note into `private/`, another partition or out of the vault. A publish recovery that could not apply a note now raises the "publish recovery failed" alert; it was silent before. (#323)
- Added: `/grilling`, a vendored skill (mattpocock-skills 1.2.3, MIT) that grills a plan or idea one round of numbered questions at a time, each with a recommended answer. For a new idea, its first round asks whether it is worth building, for whom, what happens without it, its smallest version and what it displaces. FOUNDRY.md gains an Architecture section, and its Development section now names a skill for each step; specs and plans dated from today must carry the Grill, Builder check and Blueprint lines (specs) or the writing-plans header lines (plans), checked in CI. (#313)
- The hooks install adds a usage log: in a session started at the vault root, each `/command` you type and each skill Claude runs appends one line (`{ts, command}` or `{ts, skill}`, never the prompt text or arguments) to `system/logs/usage-YYYY-MM.jsonl`, so the commands headless runs never see (`/query`, `/lint`, `/impact`, `/rca`) can be counted. Headless, unattended and codebase sessions log nothing. (#312)
  - Action: run `system/scripts/install_hooks.sh --dry-run`, then `system/scripts/install_hooks.sh` (or re-run `/setup`'s memory step) to add the two new hook entries.
- Changed: every Work Orders tick checks each order that can still run against the rules `/order add` uses, so a queue note edited after queuing, or written without `/order add`, no longer reaches a session unchecked. A research order's output must now be a new note in `wiki/<partition>/concepts/`, `entities/` or `summaries/` of its own partition, its web hosts must be names (IP addresses are refused), and its research session reads only those three folders (no `private/`, `Now.md`, `meetings/` or `preferences/`). An order's `repo` must be a codebase in its partition or `shared`. (#324)
  - Action: an order queued before this update whose output falls outside the three folders fails at the next tick with an alert (`<note> refused: output must be a note path under …`). Queue it again with `/order add` and a `wiki/<partition>/concepts/`, `entities/` or `summaries/` output.

## 2026-10-20
- Added: Slack notices in a daily thread. With `slack_notify_thread: daily`, the day's first notice posts one parent message, `Foundry updates <date>`, and every notice that day (brief, debrief, alerts, Work Orders) is a reply under it. The intraday capture can then read the same channel: your top-level posts and your replies in those threads become inbox drops, each reply with the notice above it; the Foundry's own posts are never captured. (#293)
  - Action: optional. To use one channel both ways, set `slack_notify_thread: daily` and set `capture_channel` to the `slack_notify_channel` ID (`watch_user_id` must be set).
- Fixed: inbox triage no longer fails a tick on a long ask. A statement that would put a Now line over 300 characters is cut to fit and ends with "…", so the tick and the items after it land; the intraday watch cuts its lines the same way and no longer drops them. `now.py add` still refuses a long line, so you shorten it yourself.
- Fixed: a session line in the today file no longer starts with the digest's bullet and bold markers (`- **…**`); it reads as plain text. (#291)
- Fixed: the intraday watch reads incoming mail again each tick, as the in-session sweep did. Its Gmail session also searches mail since its own cursor, less promotions, social, forums and the senders in `watch_inbound_skip`. A review request or a task assigned to you becomes an `owed` Now line, a production alert a `[watch]` alert, and a deadline an `owed` line; triage and the watch never both add a line for the same thread. `watch_inbound_mail` (default on) turns it off, and `--check` counts incoming mail next to Slack and sent mail. `foundry-watch.service` now really allows 25 minutes (it still said 20). (#290, #289)
  - Action: on a server with `intraday` on, run `system/scripts/install_units.sh --update` to install the 25-minute `foundry-watch.service`; optionally list bot and newsletter senders in `watch_inbound_skip`.
- Fixed: a telemetry source that fails now reaches Slack at once as a `[telemetry_source]` alert: one when it starts failing, one "still failing for N h" every 4 hours while it lasts, and one when it recovers, naming the backfilled window and its new and resolved groups. It replaces the `[telemetry]` failure line, which waited for the brief and came only after three failed runs. (#293)
- Fixed: the intraday watch could keep no incoming mail while Gmail returned dozens of threads, and nothing said why. Each tick now logs, per mail search, the threads returned, the model's rows, the rows kept and the rows dropped by reason (counts only), and raises one `[intraday]` alert a day when a `watch_inbound_rules` rule matched a thread the model gave no row for. The Gmail prompt now lists automated review, ticket and alert mail, names the thread's own id and the kinds it accepts. `watch_inbound_rules` (`from`, a `subject` and/or `snippet` regex, `kind`) turns matching incoming threads into items without the model, and `watch_fetch.sh --inbound-since <epoch>` replays the incoming search from an epoch of the last 7 days. A bad mail setting now stops the tick before any session runs. An incoming PR or ticket mail is skipped when an open or archived Now line already names the same PR number or ticket key, in its words or its evidence link, and the prompt no longer reads an approve, merge or comment event or another person's ticket as a request. (#289)
  - Action: optionally list the automated senders that must never be missed in `watch_inbound_rules` (see the intraday extension's setup text).
- Fixed: the intraday watch's model saw no incoming mail when a Gmail page was large: claude replaces an MCP result over 25,000 tokens with a "saved to a file" note, so the model got no threads and no next-page token, and the checker did not recognize that note. Mail pages now hold 10 threads, up to 6 a search, and the model follows each next-page token; a page the model still sees only as that note is counted in the tick log, keeps that search's cursor so the next tick reads it again, and raises one `[intraday]` alert a day. A `watch_inbound_rules` item reads as a task (no `Re:`, `Fwd:` or `[EXTERNAL]`/tool tags) and names the person a bot mail's snippet starts with instead of the bot. `foundry-watch.service` allows 29 minutes and the watch's smoke check 1,140 s. (#289)
  - Action: on a server with `intraday` on, run `system/scripts/install_units.sh --update` to install the 29-minute `foundry-watch.service`.

## 2026-10-19
- Intraday fixes: a captured message is captured once; the watch skips the Foundry's own Slack notices (and refuses a capture channel that is the notify channel); a Slack search cut at its page limit resumes from its last message read; a thread link, a short phrase or part of a name no longer marks a commitment as already on the Now page; a channel's cancellation the calendar still lists is one alert and one today line; a block names no one when nobody was named; the today file holds only work items; a capture-only setup starts; a tick fetches at most two extra calendar days and its unit allows 25 minutes; a calendar change alerts only when the next tick still has it; an unreadable extension manifest no longer stops Slack notices. (#285 follow-up)
  - Action: on a server with `intraday` on, run `system/scripts/install_units.sh --update` to install the 25-minute `foundry-watch.service`; the smoke check names it until then.
- A new extension, `intraday`, shows what changed since the brief. Every 30 minutes on workdays it reads the Slack channels you list in full, your group DMs, your own messages and sent mail, and today's calendar. Deadlines and your commitments become `owed` Now lines, blocks `waiting` lines, and a cancelled or moved meeting or an incident a `[watch]` alert that Slack carries at once. Everything it finds, with the day's session digests and imported meetings, is appended to `briefings/<date>.today.md`, which the briefing embeds under 🕑 Today so far. A capture channel you post to becomes inbox drops. It is off until you list it in `extensions:`. Core changes: an extension can now add a debrief section, and its alert tag can reach Slack at once. (#285)
  - Action: to turn it on, run `/setup` and answer phase 6e for `intraday`: the channels to read in full, your Slack member ID, and optionally a capture channel.
- `CLAUDE.md` is 50 lines, down from 77, and a test holds it there. The Workcells and the routing rules moved to `system/agents/foreman.md`, which `CLAUDE.md` tells every session to read. The approved-plans rule moved to the `order` skill, which now loads when you approve a plan. The command list is gone (the skills list themselves), and Scannable Layouts and Blocked Actions are Writing lines. Core holds at 14 schemas: new note types ship in extensions. (#281)
  - Action: if your vault edited the Agents, Commands or User Persona sections of `CLAUDE.md`, the template update reports a conflict; move your edits to `system/agents/foreman.md` or `system/config.md`.

## 2026-10-18
- `vault_index.py related` shows each hit's `compiled_at` date and first source, so a stale or off-topic note can be skipped without opening it; `--json` adds `compiled_at` and `source`. (#280)
- `system/scripts/eval_ingest.sh` scores what `/ingest` writes: 15 golden cases (restated facts, aliases, merges, corrections, friction, supersede, shared placement, the partition walls, an inbox injection, the shrink guard, and one case per converted document format) each run through one real intake tick, N times, against a pass rate, with a `--max-usd` budget stop. Results land in `system/logs/evals/`. It is not gating. (#276)
  - Action: on the server, run `system/scripts/eval_ingest.sh --runs 1` to measure each case's cost, then `--runs 3 --max-usd <D>` for the baseline.
- The brief's Overdue block shows at most 10 lines, those the fewest days over first, then `and N more of M overdue lines`; the Now pages still hold every line. (#272)
- Inbox document conversion refuses a UTF-16 part of an Office file, removes the half-written `.converted` file a killed tick leaves in `raw/inbox/.staging/`, and runs `pdftotext` under the same memory, CPU and core-dump limits as the Office converter. (#282)

## 2026-10-17
- The brief is shorter. Active Projects shows 3 decisions per project, then a count. Waiting on shows the 5 people with the most actions, then a count. Handoffs to chase lists 10 tickets, then counts the rest and those unchanged for more than 90 days. Every item is cut to 160 characters. New-message triage alerts print as one line, and a meeting notice prints in one brief only. Closed Now lines move to `wiki/<partition>/now-archive/<YYYY-MM>.md` at each brief. A Now line stays under 300 characters: add history under it with `system/scripts/now.py note`. A GitHub issue URL as evidence closes its line when the issue closes. (#270)
  - Action: in a lull, run `system/scripts/now.py review --partition work` and split each long line with `now.py set` and `now.py note`.
- The pre-commit hook refuses a `CLAUDE.md` over 16 KB or a `wiki/Index.md` over 8 KB when the commit makes it larger; shrinking always passes. (#259)
- A spreadsheet, Word document, slide deck or PDF dropped in `raw/inbox/` is converted to text and ingested (sheets as tables, footnotes and comments, speaker notes, numbered pages) (before, its raw bytes reached the ingest run as unreadable text); an encrypted or corrupt file is quarantined at once with the reason. PDFs need `pdftotext` (poppler). (#257)
- A note under `wiki/<partition>/private/` is closed to Claude: the settings deny reading and editing it, the index, lint and recall skip it, and headless runs cannot stage or publish it. To show Claude one such file, type `! cat <path>` yourself (FOUNDRY.md: Security model). `git show` now asks before it runs, since it can print a private note from history. (#258)
- With the memory hooks installed, each session's transcript is copied outside the vault when the context is compacted and when the session ends (`transcript_keep_dir`, default `~/.local/state/foundry/transcripts`), so a digest the Stop hook missed can be recovered; a copy never shrinks, and copies older than `transcript_keep_days` (default 90) are deleted. (#262)
  - Action: run `system/scripts/install_hooks.sh --dry-run`, then `system/scripts/install_hooks.sh` (or re-run `/setup`'s memory step) to add the two new hook entries.
- A telemetry source can set `secrets_scan: "true"` (off by default) to raise one alert per new error group whose log line holds a credential shape, sent to Slack at once, naming the group's note and the shape, never the value; at most three a run per source, then one line counting the rest. (#261)
- The first brief after two or more days with no session opens with "While you were away": counts of the pull requests merged and still open, Work Orders done and failed, Now lines added and closed, alerts held, and Decided for you lines over those days (up to 14). (#264)
- Every field in `system/schemas/` names the files that read it (`readers:`), and a test fails when a named reader is missing or never mentions the field; a field nothing reads (`readers: []`) only warns for now. (#256)
- `check_deps.sh` requires `socat` on a standalone machine or a server: Claude Code's sandbox, which headless runs turn on, needs it on Linux for its network proxy. Install it with `sudo apt install socat` or `sudo pacman -S socat`. (#260)
- A `claude` version change no longer counts as a failed smoke check source: the line reads `version: changed: <old> -> <new>` and its `[smoke]` alert still lists the acceptance steps in the brief's Pipeline. (#260)
- A new vault's first brief no longer fails to publish with "Now.md modified in the last 60 s": brief prep no longer writes an empty Now page, and the brief creates the page when it adds a line. (#255)
- A vault file whose name is not valid UTF-8 (such as a Latin-1 name copied from a Windows share) no longer breaks the index, `vault_index.py` and session recall; the index skips it and prints a warning naming it. (#254)

## 2026-10-16
- The brief and debrief list what they decided for you (the question, the option taken, the alternatives, how to reverse it); counts read `n of N` and a zero reads `none by HH:MM`; the debrief opens with a `signals: N (<date>)` line; a session in the vault names its uncommitted files outside `raw/`. (#253)
- `/lint` warns when an open (draft or approved) `rca` note or a codebase note cites `dir/file.ext:NN` and that file is missing from the codebase or has fewer lines. (#251)
- `/ingest` writes about people as dated behavior, never a verdict or a legal or medical label, and leaves a first or partial name unlinked unless a note settles who it is. (#251)
- Connector sessions fail closed when their settings cannot be built, instead of running with hooks on; a connector error's alert line stays on one line; an RCA filing stopped while it lists the servers no longer leaves a false "earlier session" block. (#252)
- The smoke check no longer reports the calendar as failed on a day with more than 100 events, a connector fetch refuses a too-broad allow rule before listing the servers, and a meetings fetch without `claude` prints its reason once. (#250)
- Dropping an RCA draft's Now line after its Jira ticket was already created now records that ticket on the note instead of marking the draft rejected. (#245)
- Inbox triage can also watch the Slack channels you are in: with `triage_chat_enabled: true`, messages that ask you something or report a production problem become `owed` Now lines with their Slack link. (#244)
- Up to three Work Orders run at the same time: a long research order no longer holds up the next one, and two plans on the same codebase and branch still take turns. (#241)
- A Work Order whose start was cut short by a restart or shutdown runs on the next tick instead of waiting forever. (#248)
- Extensions: optional features live in `extensions/<name>/` folders that ship with the template, and one `extensions:` list in `system/config.md` turns them on. (#226, #231)
  - Action: on a second (client) machine, add the extensions the update turned on to that machine's `extensions:` list (or re-run `/setup`), then run `system/scripts/extensions.py link`.
- Jira handoffs move to the `handoffs` extension. The update turns it on once for vaults that use handoffs. (#232)
- Telemetry and root-cause analysis (`/rca`) move to the `telemetry` extension. The update turns it on once for vaults with a telemetry source. (#235)
- The template no longer ships the DTCC watcher. (#237)
  - Action: a vault that uses the DTCC watcher keeps it as its own extension. Before taking this update, stop the update timer. After it, restore the folder from the template's history (`git checkout 9e3d45c -- extensions/dtcc`), add `dtcc` to `extensions:` on every machine, then run `system/scripts/extensions.py check`, `allow --write`, `link` and `system/scripts/install_units.sh`.
- The debrief drops the Agent Health section, which nothing ever filled. (#230)
- A new production error posts an `[incident]` line to Slack. (#223)
- A notes Doc that arrives after a dropped transcript fills the meeting note's empty sections. (#224)
- A transcript dropped for a meeting whose note already has content is kept and linked from that note, and the drop is archived. (#246)
- A failed Work Order found during cleanup is announced, and GitHub remotes written as `ssh://` get links in notices. (#220)
- Session recall ranks and caps Now lines and keeps room for digests. `now.py set` rewrites a Now line in place. (#214)
- A changelog page and a What changed section in the morning brief, showing what each update brought. (#239)

## 2026-10-15
- Slack gets only the alerts that need you now, and the rest wait for the brief. Notices use plain language, report only final outcomes, and link to notes in Obsidian. (#183, #213)
- The morning brief opens with where yesterday landed, linked to the previous debrief. (#210)
- Connector health: each fetch says why it failed (expired credential, network, timeout). The smoke check alerts once a day per expired credential and says how to renew it. The brief shows one Sources line for what was skipped and why. The smoke check also reports a timer that missed its run and installed units that differ from the template. (#184, #207)
- Now lines get a decide-by date and an optional recommendation, and the brief lists overdue lines. (#205)
- The brief and debrief read failed inputs the same way, and each failed input gets one automatic retry. (#206)
- A telemetry error group still firing after 24 hours reaches the brief and the Now page. (#204)
- `/ingest` reuses a partition's existing tags, and lint and the check before a run's notes are saved keep one tag form. (#208)
- Unattended runs check their wording against the short Writing rules in `CLAUDE.md`, so they read a much shorter prompt, and `CLAUDE.md` drops three sections of rules nothing enforced. (#201, #202)
- `/rca` reads required Jira fields from `rca_extra_fields`, and a ticket Jira refuses comes back as a draft you can retry. (#200)
- The pre-commit hook refuses added text shaped like a secret. The sync and the daily update leave that file out, keep going, and name it in an alert, and the update no longer stops on a refused commit. (#185, #193)
- Work Orders: each run records its real duration, readiness refuses tasks that need a credential the run does not have, and codebases whose package manager is pinned in the project install and check correctly. (#178, #192, #195)
- Meetings: a recording that replaces an empty note keeps its attendees, and `/ingest` compiles a dropped transcript. (#190)
- Fixes: lint warns about a note at the vault root, where nothing ingests it; a missing alerts file no longer shows as a problem in the brief; a correction that renames a heading is saved; the pre-commit lint checks what you are committing; `operation_id` is optional on production errors; setup requires Python 3.11 or newer and names the version it found. (#180, #182, #194, #196, #197, #209)

## 2026-10-14
- A research Workcell answers research questions in the session, read-only, from the index first. (#172)
- `now.py review` lists closed, stale and duplicate Now lines, and the Foreman reviews them when things are quiet. (#174)
- The calendar fetch works on busy calendars, so the brief gets its calendar again. (#176)
- The daily update commits uncommitted changes first, and a refused commit no longer stops the sync. (#165)
- Work Orders install a codebase's dependencies before their final check runs, with the project's own tools on hand. A Work Order session cannot read the vault and gets only the environment it names. (#155, #156)
- The pre-commit hook redacts a committed transcript drop. (#154)
- Fixes: a note held back at publish counts as a conflict and the run still succeeds; an empty first meeting notes source, or one holding only a divider line, no longer blocks a later recording of the same meeting. (#152, #153, #163)

## 2026-10-13
- Express install: setup asks three questions, offers each integration as a yes or no, and ends with your first brief. (#128)
- A usage ceiling: ingests and fetches wait when usage runs high, and the brief always runs. (#134)
- A daily smoke check tests every configured fetch and the `claude` version, 15 minutes before the brief. (#146, #147)
- Mail from watched senders that was archived unread still reaches the Now page. (#143)
- Security: unattended runs cannot read credential files, and `/ingest` no longer writes the Now page. (#141)
- Fixes: the debrief stops waiting on a hung GitHub search; the brief has more time before it times out; a failed telemetry source list no longer removes telemetry timers; extra spaces no longer hide a Now line from the duplicate check; notices default to Slack through claude.ai; connector reads are saved; a vault's own README passes lint. (#137, #139)

## 2026-10-12
- Slack notices for the brief, the debrief, failed runs, finished Work Orders and alerts. (#125)
- Root-cause analysis: `/rca` studies one production error group and files the ticket after you approve it on the Now page. (#120)
- The brief fits on one screen. (#115)
- The Foreman runs routine commands without asking and asks only for decisions that are yours. (#118, #124)

## 2026-10-11
- Mail that needs you reaches the Now page during the day. (#109)
- Each vault owns its `README.md`, and the template's manual is `FOUNDRY.md`. (#108)
- Fixes: links no longer collide with codebase file names, Gemini boilerplate is stripped from meetings, and preference notes stay clean. (#111)

## 2026-10-10
- The Now page: one checklist per partition of what you owe, what you wait on and what is drafted. (#102)
- Your notes in the brief's Notes section go to the wiki once, the next morning. (#105)
- When a note contradicts what a session found, the session corrects the note. (#104)

## 2026-10-09
- The vault updates itself from the template every day. (#100)
- Corrections in session digests become preference notes. (#96)
- The brief lists handoffs to chase, and the debrief lists what was delivered today. (#88)
- Fixes: Work Orders run on codebases that use Git LFS and can write the protected files they are allowed to; carried-forward objectives keep one open-since date. (#86, #93, #95)

## 2026-10-08
- Work Orders: an approved plan is queued and runs unattended to a pull request, with a usage ceiling and status in the brief and debrief. (#82)
- Research orders can read a codebase at a chosen commit, and findings notes keep web links in their body. (#80)
- Unattended runs start without waiting for you to go idle, with fixes for report time zones and template items. (#69, #70, #76)
- Fixes: meeting fetch and import; the update touches only installed timers, with clearer SSH and history checks; a fresh vault shows no lint warnings you cannot act on; telemetry keeps ticket numbers in error groups. (#71, #72, #73, #74)

## 2026-10-07
- Fewer permission prompts for read-only status commands. (#68)
- The brief shows the next actions and waiting decisions of each active project. (#66)
- The brief gets a Notes section, and past briefings move to an archive. (#53)
- A DTCC change watcher reports changes that affect a registered codebase. (#51)

## 2026-10-06
- Unattended plan and research runs overnight. (#49)
- Meeting notes from Gemini and from dropped transcripts. (#47)
- Error monitoring from Sentry and log queries, with production-error notes. (#33, #34)
- The brief carries open objectives forward until you tick them. (#36)

## 2026-10-05
- The system is named The Foundry: the Foreman you talk to, and Workcells chosen by what they can do. (#13)

## 2026-10-04
- Two machines: a server runs the automation and a client edits the vault in Obsidian, kept in step by git sync with readable commit messages. (#8, #10, #11)
- The calendar comes from the Google Calendar connector. (#9)

## 2026-10-03
- Writing rules for replies and notes, with a self-edit step in unattended runs. (#6)
- Setup installs the memory hooks. (#5)

## 2026-10-02
- The vault runs end to end: `/ingest`, `/brief`, `/debrief`, `/query`, `/lint`, `/backup`, `/impact` and `/setup`, with timers, remotes and codebase discovery. (#1, #2)
- Session memory: digests of each session and a short recall at the start of the next. (#4)
