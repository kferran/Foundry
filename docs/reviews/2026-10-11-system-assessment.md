# The Foundry as a CTO's chief of staff: an assessment

**Date:** 2026-10-11
**Reviewed:** the template repository at commit `6535249` (the manual `FOUNDRY.md`, `CLAUDE.md`, the design spec and roadmap under `docs/superpowers/`, the commands in `.claude/commands/`, the `order` and `dtcc-watch` skills, the Foreman and Workcell personas, `system/scripts/` and `system/hooks/`, the schemas and templates, and the test suites).

**Scope: template, not PorchOS.** This repository is the template that PorchOS, the owner's live vault, is cloned from and updated through `update_template.sh`. Everything below is about the machinery PorchOS inherits (commands, scripts, hooks, schemas, prompts, rules), and nothing here measures PorchOS's compiled wiki, its entity notes, its run ledger or how its briefs read. Where a finding says "nothing seeds X" or "no feature uses Y", it is a statement about template code; PorchOS may hold that content by hand, and the finding still stands because no template feature reads it. Recommendations are marked **template** (ships to every vault through the update) or **vault** (PorchOS content or settings, done in that repository).

## 1. Verdict

The Foundry is an engineering-operations assistant with unusually strong safety, provenance and automation discipline. As a chief of staff for a CTO it is incomplete in the three places a chief of staff earns their keep: it does not reach you (the brief lands in a Markdown file on a Linux server), it does not read your mail or chat unattended, and it holds no model of your organization (people, teams, commitments between them). Those gaps are on the roadmap, so this is a question of order, and the order should change: delivery and communications intake before any further engineering features.

Compared with the popular alternatives, the Foundry is ahead on control, auditability and engineering integration, and behind on reach, communications coverage and the cost of keeping it running.

## 2. The comparison set

Four kinds of system are in common use for this job in late 2026.

| Group | Examples | What they are |
|---|---|---|
| Hosted scheduled assistants | Claude Cowork scheduled tasks (Feb 2026) and Claude Code Routines (Apr 2026); ChatGPT scheduled tasks, which replaced Pulse when OpenAI retired it in June 2026 per a third-party report; Microsoft 365 Copilot; Gemini in Workspace | A prompt on a cadence, run by the vendor, reading the vendor's connectors, delivered to the vendor's app. Setup is a paragraph. Memory is the vendor's. |
| Self-hosted agent daemons | OpenClaw; Hermes Agent (Nous Research, Feb 2026) | A long-running process on your machine reachable from Telegram, Slack, WhatsApp and the like, with file-based memory, cron jobs and a periodic "heartbeat" check. Hermes writes its own skills and full-text searches every past conversation. |
| Obsidian + Claude Code wiki templates | Karpathy's LLM wiki pattern (Apr 2026) and its derivatives: claude-obsidian, karpathy-llm-wiki-second-brain, obsidian-wiki | `raw/` → `wiki/` compiled by the model under a `CLAUDE.md` rulebook, with `/ingest`, `/query`, `/lint`. Knowledge only; no schedule, no connectors, no safety gate. |
| Vertical executive-assistant products | Lindy, Motion, Superhuman, Granola, Tana, alfred_ | Hosted products for one slice each (calendar, inbox, meetings, workflows) or a workflow builder. Comparisons available online are vendor-written. |

The Foundry sits between the second and third groups: a wiki template with a scheduler, a publish gate and engineering integrations bolted on. Its own spec surveyed 20 open-source projects and adopted patterns from ten of them (spec §13.5), and the Foreman persona is modelled on firstmate.

## 3. Scorecard

Ratings are relative within the set. "Hosted" means Claude Cowork tasks, Claude Code Routines and ChatGPT tasks; "Daemons" means OpenClaw and Hermes; "Wiki" means the Karpathy-pattern templates.

| Dimension | Foundry | Hosted | Daemons | Wiki | Vertical EA |
|---|---|---|---|---|---|
| Morning brief from calendar, open loops, alerts | Strong, deterministic inputs, cited sources | Good, prompt-dependent | Good, prompt-dependent | None | Good for their slice |
| Reaches you (phone, chat, email) | None | App push | Any chat app | None | App or email |
| Mail and chat as inputs | Interactive only | Yes | Yes | No | Yes |
| Durable, structured memory | Strong: schemas, lifecycle, provenance, partitions | Vendor memory, opaque | Flat files plus conversation search | Strong, unstructured | Per product |
| Recall quality | Shallow: 3 digests plus Now page, keyword search | Good within product | Good (Hermes searches all sessions) | Model reads wiki | n/a |
| Safety of unattended runs | Strongest: staging, gate, confined sessions, no credentials | Vendor sandbox | Weak: broad tool access by design | None | Vendor |
| Engineering integration (code, PRs, telemetry) | Strongest: Work Orders to PR, Sentry and ADX, Jira handoffs | Routines on GitHub events | Possible, hand-built | None | None |
| Organization model (people, teams, 1:1s) | None | Light | None | None | Some (Tana, alfred_) |
| Auditability | Strongest: run ledger, trailers in git, decisions file | Logs | Logs | git | Little |
| Setup and upkeep | High: Linux, systemd, ~10.8k lines of shell and Python, 15 unit templates | Minutes | An hour; ongoing | Minutes | Minutes |
| Portability | Linux only (Arch, Debian) | Anywhere | Linux, macOS, containers | Anywhere | Anywhere |
| Lock-in | Low (Markdown, git) | High | Low | Low | High |
| Cost control | Explicit: daily run cap, 5-hour usage ceiling | Plan limits | Your API spend | Your plan | Subscription |

## 4. Where the Foundry is ahead

- **The publish gate.** Headless output goes to `wiki/.staging/<run_id>/` and reaches the wiki only after schema, partition-wall, shrinkage and conflict checks (`vaultlib/publish.py`). An edit you made during the run wins. None of the daemons or wiki templates have this; they write straight into your files.
- **Confined connector fetches.** `calendar_fetch.sh` and `jira_fetch.sh` run a `claude -p` session allowed exactly one MCP tool, then a script checks which tools were actually used and refuses the result otherwise. This is the right pattern for pulling vendor-connector data into an unattended pipeline without handing the pipeline credentials.
- **Data, not instructions, enforced in code.** Recall blocks are labelled as data, digests pass through `redact.py`, headless notes carry `provenance: headless`, and `headless.settings.json` turns off auto-allow in the sandbox. Prompt injection through a meeting transcript or a Sentry title is a live risk for every daemon in the set; here it is designed against at each layer.
- **Work Orders.** An approved plan runs unattended in a confined clone, is verified, pushed and ends in a pull request, never a merge (`nightshift.py`, `system/nightshift/*.settings.json`). The 5-hour usage ceiling keeps headroom for your own sessions. Claude Code Routines can do similar work but without the readiness check, the queue in your vault, or the morning report.
- **Engineering telemetry in the brief.** Hourly, model-free Sentry and ADX fetches become `production_error` notes with masked identifiers; the brief lists new, recurring and resolved groups per environment. No general assistant does this out of the box.
- **Scripted history.** Each headless run becomes one commit with `Foundry-Command`, `Foundry-Run` and `Foundry-Role` trailers, so `git log` is the audit trail. The run ledger, the decisions file and the quarantine make a failed night diagnosable.
- **Partition walls.** `work` and `personal` cannot link, a headless run writes to one partition plus `shared`, and codebase sessions see only their partition. For a CTO whose vault also holds personal notes, this matters, and nothing else in the set has it.
- **Test coverage of the deterministic parts.** 443 bats tests and 715 pytest tests, with fault-injection on the publish journal and a Debian host gate. The wiki templates have none; the daemons have far less.
- **Writing discipline.** Reply sizing, humanizer rules and a self-edit pass in every headless command. This is small but it is what makes a daily brief readable for months.

## 5. Where it falls short

### 5.1 It does not reach you

The brief is written to `briefings/<date>.md`. You see it when you open Obsidian or the vault. A failed brief is silent: the roadmap's "Delivery notifications" row (none, desktop, ntfy or Slack) is "grill first". Every other system in the set pushes to a phone or a chat app. For a chief of staff the delivery channel is the product; a brief nobody is nudged to read is a log file.

### 5.2 Mail and chat are read only when you are in the room

`brief.md` reads Gmail and Slack "only if a Gmail or Slack tool is available in this session (never in a headless run)", and otherwise writes "Mail and chat skipped". The spec puts live Gmail and Slack intake out of scope. For a CTO, the inbox and Slack are where most owed items, waiting items and "stuck" signals live, so the Friction Matrix's Communication Debt line and the Now page are fed from the thinnest sources. The confined-fetch pattern already built for the calendar and Jira is the obvious vehicle; it is not applied here.

### 5.3 No model of the organization

The wiki has `entities/` folders, but nothing seeds them from the org chart, GitHub, Jira or the calendar, and no feature uses them. There is no 1:1 preparation, no per-person "what I owe them, what they owe me" view, no team-level roll-up, no hiring or OKR tracking. Handoffs are limited to Jira tickets you reported that someone else holds. The products marketed as chief-of-staff tools (Tana, alfred_) lead with people and meeting context; the Foundry today is an engineering-operations assistant with a chief-of-staff persona.

### 5.4 Recall is shallow and memory capture is lossy

`vaultlib/recall.py` injects the partition's open Now lines plus the Outcome and Follow-ups of the last three digests, capped at 9,000 characters. Search is SQLite FTS5 keyword matching with a stop list; the spec defers embeddings, decay-weighted ranking and folder overviews. Confirmed preferences are off until Plan 5. Capture depends on the Stop hook asking for a digest after 5 events and 20 minutes; a session that ends earlier leaves nothing (an accepted loss in spec §14). Hermes full-text searches every past conversation; the hosted assistants carry memory across every surface. The Foundry's memory is better structured than any of them and worse at surfacing the right thing in a new session.

### 5.5 The model's output quality is unmeasured

Every test covers scripts. None scores what `/ingest` compiles, whether the brief's objectives are useful, or whether Work Orders produce mergeable pull requests. "Ingest evals" is a roadmap row marked "grill first". Fifty-eight plans and specs shipped in eleven days; the acceptance records are manual checklists. Without a golden set and a few metrics (open loops closed per week, brief items acted on, PRs merged without rework), there is no way to tell which of the next ten features will matter.

### 5.6 Upkeep cost and portability

The system is about 10,800 lines of shell and Python, 19 schemas, 15 systemd unit templates, three machine roles and a daily self-update. It runs only on Linux with systemd; the focus tracker needs Hyprland. The manual already carries migration notes for renamed settings and a changed `run_window` default. One person maintains it, and that person is the CTO. A Claude Cowork scheduled task or a Claude Code Routine delivers a serviceable morning brief from the same connectors with a paragraph of prompt and no server. The Foundry's extra value has to keep paying for this gap, and today it does so on the engineering side only.

### 5.7 Smaller points

- **Connector calls are expensive for what they do.** Each calendar fetch spins up a full `claude -p` session to call one MCP tool (about $0.20 and up to 150 seconds). A direct Google Calendar API call would be cheaper and faster; the session exists only because connectors live in claude.ai. The same applies to the Jira fetch.
- **Vestigial rules.** `CLAUDE.md` carries a "Strategic Intent Shaper" section and an `intent-shaper.md` template (`plan_gate` notes) that no command or script reads, a Focus Fragmentation rule that needs Hyprland, and headings written in the buzzword register the same file forbids. Each rule costs context in every session.
- **Long, brittle headless prompts.** `brief.md` is about 100 lines of rules, including tool-syntax constraints ("no `cd`, loops, `;`, `&&`"). A model update that reads them differently breaks a night silently, and the only guard is the acceptance checklist re-run by hand.
- **Dataview dependency.** The From Now block in the brief is a Dataview query, so the brief is incomplete in any viewer except Obsidian with the plugin.
- **One remote for all partitions.** Walls govern links and recall, not storage; `work` content is pushed to the same private origin as `personal`. The spec says so; a company security review may not accept it.
- **Clients are read-mostly.** A client cannot drop inbox files (not synced), only transcripts and notes in the briefing's Notes block.

## 6. Recommendations, in order

1. **Delivery first** (template; the channel and target are vault settings). Ship the deterministic notice after the brief and debrief (ntfy for phone, Slack DM for desk), plus a failure notice. This is a small script and a config key, and it changes whether the brief gets read.
2. **Communications intake through the confined-fetch pattern** (template; the accounts are vault settings). A model-free or single-tool fetch of unread Gmail threads and Slack mentions since yesterday, reduced to sender, subject, age and the friction keywords already used by `/ingest`, written to `system/logs/inputs/<date>/comms.md`. The brief's Communication Debt line and the Now page then have real inputs without giving headless runs connector credentials.
3. **Seed and use entities** (template for the script, schema and brief section; vault for the people themselves). One script that writes a `people` entity note per direct report and frequent calendar attendee (name, team, last 1:1, open lines from Now mentioning them), and a brief section "Before each 1:1 today". This is the cheapest step toward the chief-of-staff framing. If PorchOS already holds people notes by hand, the script should adopt them, and the brief section can ship first.
4. **A small eval set before the next feature** (template for the scorer and the gate; vault for the fixtures, since real digests are PorchOS data and stay out of the template). Ten digests and inbox files with expected decisions for `/ingest`, scored by a script in the gate; three weekly numbers in the Friday debrief (Now lines closed, brief items ticked, Work Orders merged without a follow-up fix).
5. **Trim `CLAUDE.md`** (template; it reaches PorchOS on the next update). Remove the intent-shaper section and template until something consumes them, drop the Hyprland-only rule into the focus script's own docs, and rewrite the section headings in the plain register the file asks for.
6. **A hosted fallback for the brief** (vault; a Claude Code Routine on the PorchOS account, not template code). A minimal brief from the calendar and the Now page when the server misses its slot. It also answers the Mac question for the day you are away from the server.
7. **Memory depth later, measured** (template). Before embeddings, try two cheap changes: include the last digest from each registered codebase, not only the session's, and show per-folder overview notes first. Measure recall hits in the digest Open questions section.

A second review against PorchOS itself would read its `system/logs/runs-*.jsonl`, `system/quarantine/`, the last two weeks of briefings and a sample of compiled notes, and would answer the questions §7 leaves open.

## 7. What this review does not show

The wiki here is empty, so nothing above measures how good PorchOS's compiled vault is after a week of real inputs, how often its publish gate rejects runs, or how its brief reads on a busy day. PorchOS's `system/logs/runs-*.jsonl` and quarantine would answer those. Claims about the alternatives come from vendor pages and third-party posts dated between February and September 2026; the retirement of ChatGPT Pulse and the cloud execution of Cowork tasks are reported by secondary sources only.

## Sources

- The Foundry: `FOUNDRY.md`, `CLAUDE.md`, `docs/superpowers/roadmap.md`, `docs/superpowers/specs/2026-09-30-vault-template-design.md` (§13.5, §14), `docs/superpowers/specs/2026-10-08-foreman-v1-work-orders-design.md`, `.claude/commands/brief.md`, `.claude/commands/ingest.md`, `system/scripts/calendar_fetch.sh`, `system/scripts/vaultlib/recall.py`, `system/scripts/vaultlib/retrieve.py`, `system/hooks/memory_capture.sh`, `.claude/settings.json`, `system/headless.settings.json`.
- Claude Cowork scheduled tasks: [announcement](https://x.com/claudeai/status/2026720870631354429); Claude Code Routines and Desktop scheduled tasks: [docs](https://code.claude.com/docs/en/desktop-scheduled-tasks), [guide](https://hatchworks.com/blog/claude/building-agents-with-claude/), [comparison](https://automatonagency.com/insights/claude-loops-for-business).
- ChatGPT Pulse and its retirement: [release notes](https://help.openai.com/en/articles/6825453-chatgpt-release-notes), [review](https://sider.ai/blog/ai-tools/chatgpt-pulse-review-is-openai-s-proactive-ai-briefing-worth-your-time), [retirement report](https://justinmckelvey.com/blog/chatgpt-pulse).
- OpenClaw: [site](https://openclaw.ai/), [heartbeat guide](https://klausai.com/blog/openclaw-automation-heartbeat-scheduled-tasks/), [overview](https://www.turingcollege.com/blog/openclaw).
- Hermes Agent: [overview](https://www.truefoundry.com/blog/what-is-hermes-agent), [review](https://dupple.com/reviews/hermes-agent), [user stories](https://hermes-agent.nousresearch.com/docs/user-stories).
- Karpathy LLM wiki pattern and templates: [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian), [karpathy-llm-wiki-second-brain](https://github.com/ddenzu/karpathy-llm-wiki-second-brain), [obsidian-wiki](https://github.com/ar9av/obsidian-wiki), [write-up](https://angelo-lima.fr/en/karpathy-second-brain-obsidian-claude-en/).
- Vertical tools (vendor-written): [Tana comparison](https://tana.inc/blog/best-ai-chief-of-staff-tools-2026), [alfred_ list](https://get-alfred.ai/blog/best-ai-chief-of-staff-tools), [Simular list](https://www.simular.ai/alternatives/ai-executive-assistants).
