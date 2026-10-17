# Changelog

What changed in The Foundry, newest first. A vault's morning update shows the new lines in its brief under What changed.

## What's next

- Finish the extensions work: no vendor names left in the core, fewer note types, and every check passing with all extensions on and with all off.
- Ingest checks: a set of sample inputs that scores how well `/ingest` compiles notes, before any new input source is added.
- A brief that stays on one screen and a shorter Now page: long sections get caps, and unattended runs read less prompt text.
- An intraday brief: what changed since the morning, with Slack messages captured into the inbox.
- Work Orders that run side by side, so a long research order no longer holds up the others (#229).
- Details: [roadmap](docs/superpowers/roadmap.md).

## Changes

## 2026-10-17
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
