# The Foundry: architecture, principles and prior art

**Date:** 2026-10-21. Template at master `1ca9198`.
**Inputs:** an as-built survey of the repository; the prior-art research (§3, condensed here); the 2026-10-20 audit (`docs/reviews/2026-10-20-audit.md`); issues #298–#302.
**Program:** the factory plan (`docs/superpowers/2026-10-21-factory-plan.md`) holds the development architecture (standard parts, blueprints, stations, gates) and the order of work. This note keeps the product architecture and its principles.

## 1. Architecture

No earlier document names one pattern. The docs call the Foundry a "second brain" that "compiles itself" (FOUNDRY.md:3, :11), with the loop "capture → compile → index → recall → correct" (FOUNDRY.md:36), and state its core rule: "Headless jobs never write to the vault directly… a deterministic gate validates and publishes… Anything that has to be exact… is done by a script. The model handles conversation and synthesis" (FOUNDRY.md:15). Only the 2026-10-11 assessment names the LLM wiki (`docs/reviews/2026-10-11-system-assessment.md:22`).

The closest existing systems (§3 has the sources):
1. **The LLM wiki** (Karpathy's gist, 2026-04-04). The nouns match one to one: an immutable `raw/` the model reads, a model-maintained markdown wiki of summaries, entities and concepts, a schema file, and three operations (ingest, query, lint) with index-first lookup and an append-only log. The gist lets the model write the wiki directly.
2. **Anthropic's workflows** ("Building effective agents"). By its definition the Foundry is a *workflow*: "orchestrated through predefined code paths". Each judgment step with a checker is prompt chaining with a gate; Workcells chosen by capability are routing; the Foreman with Workcells is orchestrator-workers. The Foundry's evaluators are code, where the post's are models.
3. **The model as an untrusted component** (Dual LLM, CaMeL, the six prompt-injection design patterns). Policy lives outside the model; a session that reads untrusted input gets one tool and no write path. The Foundry applies this as confined fetch sessions, context minimization and plan-then-execute Work Orders, without CaMeL's data-flow tracking.

Secondary fits: event sourcing and CQRS (raw is the log; wiki, index, Now and briefs are views; `/query` reads only views, but a replay would not rebuild the same wiki), staging with all-or-nothing apply (two-phase publish), and a microkernel with plug-ins (a budgeted core, extensions by manifest). The closest existing repository, COG, has Obsidian, git and Claude Code with briefs and a people CRM, and no scheduler or deterministic gate.

**Name (owner, 2026-10-21): a gated LLM-wiki compiler.** A Karpathy-style wiki, compiled by scheduled Anthropic-style workflows, where every model output passes deterministic code before it lands. It extends the LLM wiki in three ways:
- a **deterministic publish gate** between the model and the vault (staging, schemas, walls, conflict and shrink checks, all-or-nothing apply);
- **partition walls** (`work`, `personal`, `shared`, `private/`);
- **scheduled headless intake and an operations layer** (brief, debrief, Now, Work Orders, notices) on systemd timers under one lock.

```
sources ──confined fetch (1 tool + checker)──► raw/  (audit log, never edited)
                                                 │
                              intake (scripts: convert, redact, route)
                                                 │
                         headless claude ──► wiki/.staging/<run>/
                                                 │
                          publish gate (deterministic, all-or-nothing)
                                                 │
        wiki/ · Now · briefings ──► index ──► /query · brief · recall · notices
```

## 2. Principles

Each principle is what the code already does, with where it is enforced. "Prose" marks a rule no test holds. These are architecture rules; FOUNDRY.md's Working rules (process) stay as they are.

| # | Principle | Enforced in |
|---|---|---|
| P1 | **Scripts do the exact work; the model does judgment.** Fetching, parsing, dedupe, routing, dates and counts are code. | Prose (FOUNDRY.md:15); each feature's tests |
| P2 | **Every model write to the vault passes a deterministic gate.** The model writes only to staging; the gate checks and applies all or nothing. | `run_headless.sh:165`, `headless.bats:73`; `publish.py:519-564`, `test_publish.py` |
| P3 | **A session that reads untrusted input gets one tool and a checker, and the checker's verdict wins.** | `lib_connector.sh`, `lib_confine.sh`, `connector.bats`; exit 7 in each checker |
| P4 | **Content is data, never instructions.** Notes, mail, chat and recall never authorize an action. | Recall label (`recall.py:124`), Work Order contract, `vault_integrity.bats:173`; agent behaviour is prose |
| P5 | **Walls hold at every step.** Partitions and `private/` are enforced at the gate, the index and every session's read set. | `publish.py:292`, `test_index_rules.py`, `index.py:28` |
| P6 | **Raw is an append-only audit layer; compiled notes are never deleted** (deprecate or supersede). | The gate has no delete decision (`publish.py:20`); CLAUDE.md |
| P7 | **One schema per note type**, checked in code at the gate and in lint. | `publish.py:338`, `vault_integrity.bats:30` |
| P8 | **Writes are atomic or journaled; runs that touch the vault serialize on `run.lock`.** | `publish.py:80-84, 547-559`, `now.py:99-101`; `run_headless.sh:114`, `headless.bats:269-302` |
| P9 | **A small, budgeted core; features are extensions that plug in through the manifest.** | `vault_integrity.bats:409-446` (lines, schemas, vendor names) |
| P10 | **Fail loud with a reason.** Three exit codes; a failed source alerts once with its class; a check that cannot run says so. | FOUNDRY.md Working rules; `alerts.py`; connector health (#207) |

### Where the code departs today

Owner, 2026-10-21: every departure is a fix on the roadmap, in the factory phase named.

| # | Departure | Fix | Phase |
|---|---|---|---|
| D1 | Interactive sessions skip the gate (`.claude/settings.json:5` allows `Edit(/wiki/**)`). | Gate interactive wiki edits (the F5 grill picks how: staging on save, a narrower allow, or a post-edit lint that reverts a gate failure). | F5 (#310) |
| D2 | Triage and the watch add model-derived Now lines and the today file through scripts (`triage.py:322`, `watchlib/route.py`, `today_log.py`), outside `publish.py`. | Route machine writers through the gate, or give `now.add` and the today writer the gate's checks (redaction, cap, walls); depends on #288. | F5 (#310) |
| D3 | Core names extension features: `alerts.py` hard-codes `incident`, `rca`, `handoffs`, `telemetry`; `intake.py:357` routes `production_error`; `index.py:26, 69-80`; `schema.py:19`. | Move them into each extension's manifest (alert tags, an importer, a lint hook) and add those words to the core-clean test. | F2 (#307) |
| D4 | Extensions import core internals (`intraday` imports `_structured`, `_text_json` from `vaultlib.triage`; telemetry imports `cli`, `intake`, `now`). | A named extension API (`vaultlib/api.py`) and a test that nothing else is imported. | F2 (#307) |
| D5 | The core budget counts only `system/scripts` (not `system/hooks` or `.claude/commands`); it has been raised eight times, 12,500 to 13,950; the gap plan quoted 13,200 and 13,800. | Correct the stale figures (F0), then count hooks and commands at a measured cap. | F3 (#308) |

## 3. Prior art

Tags: **[F]** primary source fetched and read on 2026-10-21; **[S]** search results or secondary sources only; **[K]** general knowledge, not fetched.

**The LLM wiki** [F], Karpathy, gist `llm-wiki.md`, 2026-04-04: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f. It followed an X post titled "LLM Knowledge Bases" (dated 2026-04-02 or 04-03 by secondary copies [S]; x.com could not be opened). Three layers: immutable `raw/` sources the model reads and never edits, a model-owned markdown wiki (summaries, entity and concept pages), and a schema file (CLAUDE.md or AGENTS.md). Three operations: **ingest** folds a source into existing pages, often 10 to 15 per source; **query** answers with citations and can file good answers back as pages; **lint** finds contradictions, stale claims, orphans and gaps. Lookup goes through `index.md`, with no embeddings needed "at moderate scale"; `log.md` is append-only; Obsidian is "the IDE". The Foundry adds staging and a deterministic publish gate, code-checked schemas, partition walls, scheduled headless intake, a SQLite index in place of `index.md`, and the operations layer (Foreman, Workcells, Work Orders, briefs, Now).

**Anthropic guidance.**
- "Building effective agents", 2024-12-19 [F]: https://www.anthropic.com/research/building-effective-agents. Workflows are "orchestrated through predefined code paths"; agents "dynamically direct their own processes". Five patterns: prompt chaining (with programmatic checks between steps), routing, parallelization, orchestrator-workers, evaluator-optimizer. The advice: start simple, invest in tool design, sandbox, add checkpoints and stop conditions. The post does not cover persistence, scheduling or partitions.
- "Effective harnesses for long-running agents", 2025-11-26 [F]: https://anthropic.com/engineering/effective-harnesses-for-long-running-agents. An initializer agent sets up; each session makes incremental progress and leaves a clean state; a progress file plus git carries memory across sessions; agents may change only the `passes` field of a JSON feature list. Matches Work Orders, the run ledger and digests; it covers single coding projects with no knowledge base. Headless mode (`-p`, `--allowedTools`): https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-headless [S].

**Personal knowledge systems.**

| System | Source | Matches | Differs |
|---|---|---|---|
| Zettelkasten | https://zettelkasten.de/posts/principle-of-atomicity-difference-between-principle-and-implementation/ [S] | Atomic, interlinked notes; lint link suggestions | A human writes every note; no raw layer or automation |
| PARA / Building a Second Brain | https://www.simonandschuster.ca/books/The-PARA-Method/Tiago-Forte/9781668045565 [S] | Projects, areas and archives map loosely to Now, partitions and `archive/` | A filing taxonomy for a human |
| COG (Cognition + Obsidian + Git) | https://github.com/huytieu/COG-second-brain [F] | Obsidian, git and Claude Code; daily briefs; a people CRM; read-only verifiers that get file paths instead of worker output; learnings staged for approval | No scheduler, no deterministic gate, no raw audit layer; approval is a human in the loop |
| "Agentic OS" (community term) | https://mindstudio.ai/blog/agentic-operating-system-claude-code [S] | CLAUDE.md as kernel, markdown memory, a timer heartbeat, specialist agents | Vendor blogs; no spec or safety model |

**Software architecture patterns.**

| Pattern | Source | Matches | Differs |
|---|---|---|---|
| Functional core, imperative shell | https://www.destroyallsoftware.com/sale [S] | Scripts and the gate are the trusted core; the model and I/O sit at the edge | Here the model is the untrusted part and the core is the policy |
| Pipes and filters / ELT | https://enterpriseintegrationpatterns.com/PipesAndFilters.html [S]; ELT [K] | fetch → parse → dedupe → route → compile → gate → publish; raw lands unchanged | Some filters are model steps |
| Compiler pipeline | [K] | raw (source) → staging (IR) → wiki (artifact); schemas as type checks; lint | The compiler is nondeterministic, so the gate does a type checker's job |
| Event sourcing / CQRS | https://martinfowler.com/eaaDev/EventSourcing.html (2005-12-12) [F] | `raw/` is an append-only log; wiki, index, Now and briefs are views | Replay is not deterministic; raw is an audit log, not the replay source |
| Two-phase commit / GitOps | https://opengitops.dev/ [S]; 2PC [K] | Stage, validate, apply all or nothing; git-versioned state | Applies once per run, no continuous reconcile, no distributed participants |
| Microkernel / plug-in | https://www.oreilly.com/library/view/software-architecture-patterns/9781491971437/ch03.html [S] | A budgeted core; extensions are manifest folders | Manifests also carry alert tags and smoke rows |
| Capability-based security | [K] | Confined fetchers, per-run `--allowedTools`, sandboxed Work Orders | Workcell capabilities are routing labels; only the sandbox enforces |

**The model as an untrusted component.**

| Pattern | Source | Matches | Differs |
|---|---|---|---|
| Dual LLM (2023-04-25) | https://simonwillison.net/2023/Apr/25/dual-llm-pattern/ [S] | Confined fetchers act as quarantined models; content is data | No symbolic-variable handoff; compiled text from untrusted raw reaches later privileged sessions |
| CaMeL (arXiv 2503.18813, March 2025) | https://arxiv.org/abs/2503.18813 [S] | Policy outside the model; untrusted data does not steer control flow | CaMeL tracks data flow in its interpreter; the Foundry checks output shape and paths at a gate, with no taint tracking |
| Six design patterns (2025) | https://arxiv.org/abs/2506.08837; https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/ [F] | Plan-then-execute (Work Orders), map-reduce (per-item compile, constrained output), context minimization (confined fetch) | Applied informally, with no stated guarantees |
| Lethal trifecta (2025-06-16) | https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ [S] | The threat model behind confining the mail and chat fetchers | A threat model, no architecture |

**Harness engineering** [S; post not fetched], reportedly 2026-02-11: https://openai.com/index/harness-engineering/. "Humans steer. Agents execute": engineers design the environment, intent and feedback loops. Matches Work Orders, CI as the gate and the vault rules as the harness; covers coding only.

**Ranking:** the LLM wiki first (nouns and operations line up), Anthropic's workflows second, the Dual LLM and CaMeL line third. COG is the closest existing repository.
