# Four open-source second brains compared with The Foundry

Date: 2026-11-04. Sources: shallow clones of each repo's default branch on this date (read in `.scratch/sb-compare/`), and this vault's `FOUNDRY.md` and `docs/superpowers/roadmap.md`.

## The four projects in one line each

| Project | What it is | License |
|---|---|---|
| **kepano/obsidian-skills** (Obsidian's CEO) | Six reference skills that teach an agent Obsidian's file formats and tools: Obsidian Markdown, Bases (`.base`), JSON Canvas, the Obsidian CLI, Defuddle (web page to clean Markdown) and Knap (templates from JSON/CSV). No workflow, no automation. | MIT |
| **AgriciDaniel/claude-obsidian** (v3.0.1) | A Claude Code plugin for Karpathy's "LLM wiki" pattern: `inbox/` capture, ingest, query, save, lint, plus Canvas, BM25 search, log folding and filing modes (Generic, LYT, PARA, Zettelkasten). Every write is one hashed, journaled transaction. Runs only when you ask. | MIT |
| **eugeniughelbur/obsidian-second-brain** (v0.18) | 49 commands across Claude Code, Codex, Gemini, OpenCode and others. Ingest rewrites 5 to 15 existing pages per source; automatic contradiction reconcile and synthesis; 4 scheduled agents; X, Perplexity and YouTube research; "Crew", a shared job log across agents. | MIT |
| **coleam00/second-brain-starter** | One skill that turns a requirements form into a 9-phase build plan (PRD), plus memory templates (`SOUL.md`, `USER.md`, `MEMORY.md`, `HEARTBEAT.md`, `HABITS.md`, a self-deleting `BOOTSTRAP.md`). A blueprint, not a system. | none in repo |

## How they compare with The Foundry

| Dimension | The Foundry | claude-obsidian | obsidian-second-brain | starter / obsidian-skills |
|---|---|---|---|---|
| Runs unattended | Yes: systemd timers for intake, brief, debrief, triage, meetings, Work Orders, sync | No; on demand only | 4 scheduled agents (brief, nightly consolidation, weekly review, health) | starter plans a heartbeat; kepano none |
| Write safety | Headless runs write to staging; a deterministic gate checks schemas, partition walls, shrinkage and a snapshot, then publishes all or nothing | SHA-256 per target, one transaction, journal with `recover`; user edits win | Write-time validator hook; ingest rewrites many pages per source | n/a |
| Work/personal separation | Partition walls enforced by the gate, recall and Now writers | None | None | None |
| Retrieval | SQLite FTS5 index, index-first rule | BM25 with optional rerank, plus a `bench` command over your own questions | Semantic index (`/obsidian-reindex`) and `/obsidian-retrieval-eval` (recall@k, MRR) | starter specifies hybrid 70% vector + 30% keyword |
| Open loops | Now page per partition, closed by evidence (merged PR, closed issue, finished Work Order), with due dates and Overdue | None | Kanban boards, tasks, recurring obligations | `HABITS.md` nudges |
| Inputs | Files incl. xlsx/docx/pptx/pdf, session digests, meeting transcripts and Gemini notes, Gmail and Slack triage, intraday watch | Local files kept as hashed copies; PDF/EPUB metadata only; web pages as approved plans | URLs, PDF, docx, audio (Whisper), images, YouTube, podcasts, X posts, Telegram captures | n/a |
| Staleness | `/lint` staleness suggestions; freshness lint is #344 in the grill queue | Lint for dead links, orphans, gaps | Freshness policy with a lint (`freshness_lint.py`), bi-temporal facts, owner check-in | n/a |
| Tests | bats + pytest suites, ingest evals, smoke check, health scorecard | `make test`, CI | Smoke tests over the build pipeline; command behavior checked by hand | none |
| Portability | Linux (Arch, Debian), Claude Code only | Claude Code plugin plus 6 other hosts | 8 agent hosts via adapters | Any Agent Skills host |
| Setup cost | High: `/setup` interview, units, hooks, connectors; 560-line manual | Two commands | One installer, API keys for research | Copy a folder |

### Where The Foundry is ahead

- **It runs the day.** None of the four has an equivalent of the Now page with evidence-closed lines, the brief/debrief pair, inbox triage, meeting action tracking or Work Orders that end in a pull request.
- **Unattended writes are gated.** claude-obsidian's transaction core is the only comparable design, and it covers interactive writes only. obsidian-second-brain lets one source rewrite up to 15 pages with no publish gate; the Foundry's shrinkage check would reject much of that.
- **Partition walls and redaction.** No other project separates work from personal or redacts credentials before notes are written.
- **Confinement.** Work Order sessions run with no vault access, no credentials and a sealed verify sandbox. The others run in the user's session with its full access.
- **Proof.** Live acceptance records, ingest evals and the health scorecard. obsidian-second-brain says command behavior "is still verified manually".

### Where The Foundry is behind

- **No retrieval measurement.** Both claude-obsidian (`bench --queries`) and obsidian-second-brain (`/obsidian-retrieval-eval`) measure search quality on your own questions. The Foundry has ingest evals but no retrieval eval, and #345 (semantic retrieval) is waiting on a research brief that has nothing to score against.
- **Inputs from the web and media.** URLs, YouTube, audio and images are handled by obsidian-second-brain today; the Foundry's URL capture is still a waiting item under #333.
- **Obsidian-native views.** The Foundry depends on the Dataview community plugin. Bases is now a core Obsidian feature, and kepano's skill teaches its syntax. Canvas is unused.
- **Portability and setup cost.** Linux and systemd only, Claude Code only, a long setup. This is a deliberate trade for unattended runs, but it is the main reason the others are easier to adopt.
- **Thinking tools.** obsidian-second-brain's `/obsidian-challenge`, `/obsidian-emerge` and `/obsidian-panel` use the vault to push back on a decision. The Foundry has `/grilling`, which does not read the wiki; #346 covers this and is ungrilled.

## Worth borrowing, ranked

1. **Retrieval eval (from claude-obsidian `bench` and obsidian-second-brain `/obsidian-retrieval-eval`).** A golden file of 20 to 40 real questions with the notes that should answer them, scored as recall@k and MRR against `vault_index.py query|related`. Small (one script, one golden file, reuses the `eval_check.py` pattern), and it gives #345 a baseline: semantic recall gets built only if it beats FTS5 on this file. Recommend doing this before queuing the semantic-recall research brief.
2. **Freshness policy and lint (obsidian-second-brain `references/freshness-policy.md`, `scripts/freshness_lint.py`).** This is #344. The spec is already written and MIT: every fact is timeless, dated (`(as of YYYY-MM-DD)`) or a pointer to where truth lives; a present-tense count or status with no stamp is an error. Its refresh loop (re-observe, convert to pointer, or retire into a dated note) fits the Foundry's Stale claims rule. Borrow the rule text into the ingest skill and the concept schema, and the lint rules into `/lint` and the publish gate (gate as warning first).
3. **Owner check-in on stale people and project notes (`/obsidian-checkin`).** Lint can only compare notes with notes; news that never reached the vault (a job change, a settled bill) needs the owner. Its design fits the Foundry well: a script picks at most 3 entity notes untouched for 14 days, the model writes 1 to 3 facts from each, open cards persist in a state file, and "same" stamps `last-checked`. In the Foundry this would be a brief section (or Now lines with `[via:: checkin]`) and pairs with gap plan E, the people Workcell.
4. **Vendor kepano's `obsidian-markdown` and `obsidian-bases` skills.** Reference-only, MIT, maintained by Obsidian's CEO. Ingest gets correct callouts, embeds and properties, and Bases gives a core-plugin path for the From Now block and `wiki/Index.md` dashboards, which removes the Dataview dependency over time. `defuddle` is the natural fetcher for #333 URL capture.
5. **`/obsidian-challenge` as the model for #346.** "Your vault argues against your idea using your own history": search the index for reversed decisions, failures and earlier preferences on the topic and quote them. A read-only skill on top of `vault_index.py`, close to what `/grilling` already does with an added wiki search step.
6. **Source and claim ledgers (claude-obsidian `provenance.md`).** SHA-256 identity per source, an authority level (`official`, `primary`, `secondary`, `community`), and the rule that two sources with the same origin do not count as independent corroboration. Worth it only if research Work Orders start citing many web sources; until then, note it and skip.
7. **Proactivity levels (second-brain-starter).** Observer, Advisor, Assistant, Partner as one named setting for how far triage and the intraday watch may act. The Foundry is fixed at Advisor (it drafts, never sends). Useful only as wording if you later let it send low-risk messages.

## Not worth borrowing

- **Automatic contradiction reconcile and page rewrites per source.** They conflict with the publish gate's shrinkage rule and the noop/patch/create decision per fact, which exist so a run cannot silently rewrite your notes.
- **"For future agent" preambles and AI-first note style.** They conflict with the humanizer rules the Foundry's notes follow; the index already does retrieval.
- **Multi-host adapters, X/Perplexity research keys, the Telegram bot, Crew.** Crew's "a lesson becomes a rule only when a human keeps it" is what the Foundry's preferences already do (confirmed in `/brief`).
- **`SOUL.md`/`USER.md`/`BOOTSTRAP.md`.** `system/config.md`, `foreman.md` and `/setup` cover the same ground.

## Already on your roadmap

Items 2, 4 (`defuddle`, through #333), 5 and the semantic half of item 1 already exist as #344, #333, #346 and #345. What these repos add is working reference implementations to read before each grill, and the retrieval eval, which is not on the roadmap and should come before #345.
