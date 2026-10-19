# past.dev: ideas for the Foundry's memory and recall

**Date:** 2026-10-19
**Issue:** #271. A review only: nothing here is adopted without a grill.
**Read:** past.dev's [home page](https://past.dev), [MCP overview](https://past.dev/docs/mcp/overview), [Memory API overview](https://past.dev/docs/memory-api/overview), [concepts](https://past.dev/docs/memory-api/concepts), [API reference](https://past.dev/docs/memory-api/api-reference), [sending data](https://past.dev/docs/memory-api/sending-data), [access control](https://past.dev/docs/memory-api/access-control), [benchmarks](https://past.dev/benchmarks), [methodology](https://past.dev/benchmarks/methodology), [pricing](https://past.dev/pricing), [security](https://past.dev/security), the [BEAM harness README](https://github.com/pastdotdev/benchmarks/tree/main/beam) and the [BEAM paper abstract](https://arxiv.org/abs/2510.27246). Foundry code at `5cd8724` (master). Fetched pages were read as data.

## 1. What past.dev is

- **A hosted memory API.** You send text items ("data points") with the time they happened; a recall query returns ranked documents with dates and verbatim excerpts. Four core routes: `POST /api/v1/ingest` (and `/ingest/batch`, up to 1,000), `GET` and `DELETE /api/v1/ingest/{id}`, `POST /api/v1/recall` ([API overview](https://past.dev/docs/memory-api/overview)).
- **Reached by REST or MCP.** An account MCP server (54 tools, filtered by role) and one end-user MCP server per project with four tools; the overview names only `recall_memory` and `ingest_memory` ([MCP overview](https://past.dev/docs/mcp/overview)).
- **Closed and managed.** Runs on AWS, regions not named. Enterprise can run it in your own cloud account, "operated by us" ([pricing](https://past.dev/pricing)). No self-host option is described. Only the benchmark harness is public (MIT).
- **Priced by credits.** Free tier keeps data 365 days, Flex ($99/month) 3 years, Enterprise unlimited ([pricing](https://past.dev/pricing)). No export method is described on the pricing or security pages.
- **Benchmarks are self-reported.** BEAM 92.08% (100K), 89.63% (500K), 90.65% (1M), 85.03% (10M); one model (`openai/gpt-5.6-luna`) both answers and judges. Competitor rows are each vendor's own published numbers from separate runs ([benchmarks](https://past.dev/benchmarks)).

## 2. Fact versioning

**past.dev.** Two separate mechanisms:
1. *Same id, new content:* a re-send with the same `id` and any changed field replaces the data point and the memory derived from it; without an `id`, corrected text becomes a second data point ([sending data](https://past.dev/docs/memory-api/sending-data)). This is deterministic.
2. *Claim supersession:* "A later value for the same property can supersede the earlier claim, which then carries `artifact.supersededAt`" ([concepts](https://past.dev/docs/memory-api/concepts)). Recall exposes `supersededAt` when "a later statement readable by the viewer replaced this one"; a trace route exposes `validFrom`, `validTo`, `current` and `replacedId` ([API reference](https://past.dev/docs/memory-api/api-reference)). Statements can carry `hypothetical`, `proposed` or `retracted` status.

The docs do **not** say how a claim is extracted, how "same property" is matched, or whether "later" means occurrence time or arrival order. The data model is published; the decision is not. Occurrence time does drive eligibility: `queryTimestamp` limits recall to evidence at or before an instant, and "backfilled history keeps its original date".

**Foundry.**
- Supersession is per note: `supersedes`/`superseded_by` on concepts and preferences (`system/schemas/concept.md:14`, `system/schemas/preference.md:12`). A superseded or deprecated note is inactive (`system/scripts/vaultlib/index.py:289`) and drops out of `related` (`system/scripts/vaultlib/retrieve.py:51`). Lint checks the pair, the partition and cycles (`system/scripts/vaultlib/index.py:436`).
- A changed fact inside a note is a **patch** that overwrites the old value: the Stale claims rule (`CLAUDE.md:47`) and ingest's Stale claims step, "state the current fact in place of the old claim" (`.claude/commands/ingest.md:51`). The `correction-patch` eval requires the old wording gone (`system/tests/golden/ingest/correction-patch/expect.yaml:7`).
- Preferences come closest to versioning: a contradicting bullet goes to `counter_evidence` and a replacement is a create plus supersede (`.claude/commands/ingest.md:59`).
- The contradiction check is model prose in `/lint`, with no script behind it (`.claude/commands/lint.md:11`). Staleness is `compiled_at` older than 180 days (`.claude/commands/lint.md:12`).
- Ingest has no rule that compares an input's date with the note's. The last input compiled wins, so an old document dropped late could overwrite a newer fact. No eval case covers this.

**Could ingest record "was X, now Y"?** Yes, and most of it exists. A digest's Stale claims bullet already has that shape (`[[Note]]: <old claim> → <current fact> (<evidence>)`), the digest stays in the note's `sources`, and each run's `_decisions.jsonl` (`system/scripts/vaultlib/publish.py:25`) lists decision, target and source in the run's commit message (`system/scripts/commit_runs.py:139`). Git keeps the old text. What is missing is the old value in a queryable place: an optional `was`/`now` pair on patch decisions is a small change to `ingest.md` and `commit_runs.py`. No observed problem needs it yet.

## 3. Evidence per hit

| | past.dev recall | `vault_index.py related` | Session recall |
|---|---|---|---|
| Per-hit date | `occurredAt` | none printed | Now lines ranked by due date and newest date (`system/scripts/vaultlib/recall.py:57`); digests newest first with date (`recall.py:191`) |
| Per-hit source | `sources[].sourceId`, `label` | none printed | digest stem in its heading |
| Excerpt | verbatim `excerpts` | none | digest Outcome and Follow-ups sections |
| Rank | `rank` 1..n; basis not documented | BM25 over title, aliases, body (`system/scripts/vaultlib/retrieve.py:48`) | fixed order |
| Budget | `maxTokens` or `level` | `--limit` | 9,000 chars, cap 9,500 (`recall.py:11`) |
| Time filters | `queryTimestamp`, `occurredFrom/To`, `sort: chronological` | none (`query` over `v_*` views can filter `compiled_at`) | none |

`related` prints only title, path, partition and type (`system/scripts/vaultlib/cli.py:290`); the JSON adds the BM25 score (`retrieve.py:75`). The reader must open each note to learn its age or source. A date (`compiled_at`) and the first `sources` link would let it skip stale or off-topic notes; `_first_source` already exists (`retrieve.py:37`). An excerpt would save more reads but costs tokens in every headless ingest. Citation at the answer layer already exists: `/query` must say where the wiki is silent or notes disagree and end with Sources Compiled (`.claude/commands/query.md:10`).

## 4. BEAM and the ingest evals

- **What BEAM is.** 100 generated conversations up to 10M tokens, 2,000 questions in 10 categories: abstention, contradiction resolution, event ordering, information extraction, instruction following, knowledge update, multi-session reasoning, preference following, summarization, temporal reasoning. Scored by an LLM judge on rubric items (0, 0.5, 1), with Kendall tau-b for event ordering ([harness README](https://github.com/pastdotdev/benchmarks/tree/main/beam)).
- **Wrong layer.** The merged evals measure what ingest writes: decisions, patches, walls (`docs/superpowers/specs/2026-10-11-ingest-evals-design.md` §3.3). BEAM measures questions answered over a conversation. The Foundry has no recall eval to plug it into.
- **Wrong scoring.** The eval spec allows deterministic checks only and puts model grading and rubric scores out of scope (spec §2 decision 5, §5). BEAM needs a judge.
- **Wrong data.** Synthetic chat, separate dataset terms, about 1 GiB for the 10M split. Nothing in it looks like digests, inbox drops or meeting notes.
- **Borrowable: the categories.** `supersede` and `correction-patch` already cover knowledge update. Two shapes are missing and can be checked by script: an older input that arrives after a newer fact (temporal; `keeps` the newer value), and two inputs in one batch that disagree (contradiction resolution; one `decisions` outcome, no silent merge). BEAM's abstention is an answer-layer test; the nearest ingest shape is an input with nothing new producing only noops, which `restated-noop` covers.
- **Not answered by the sources:** the arXiv abstract lists no code link, and no BEAM repository from the paper's authors turned up; the only code found is past.dev's harness. The harness README gives no dataset URL (a search found a [10M split on Hugging Face](https://huggingface.co/datasets/Mohammadta/BEAM-10M)). past.dev's methodology asks for full-context and plain-RAG baselines and per-judge results but publishes neither the baseline scores nor the false-accept rates.

## 5. Permissions

| past.dev | Foundry |
|---|---|
| Project: "nothing crosses between projects" | Partition: `WALLS` (`system/scripts/vaultlib/index.py:58`), `partition-wall` lint error (`index.py:394`), supersession may not cross (`index.py:445`) |
| Audience (fixed list or trait rule) per data point; identity per read | None inside a partition. The caller's location sets scope: a codebase session reads its partition plus `shared` (`system/scripts/vaultlib/scope.py:68`) |
| Project key "reaches every audience of the project" | `wiki/*/private/` is denied to every agent: never indexed (`index.py:28`), never staged or published (`system/scripts/vaultlib/publish.py:69`), Read and Edit denied (`.claude/settings.json:62`, `system/headless.settings.json:10`) |
| A re-send without `audience` makes a scoped item project-visible | A write cannot widen a path deny; a wall breach fails lint and the gate |

past.dev filters what each end user of a multi-user app sees; the agent holding the key sees everything. The Foundry has one user and filters what the agent itself may read. The `private/` folder has no past.dev equivalent other than never sending those notes.

## 6. Adopt or borrow

**Borrow ideas; do not adopt.** Confirmed. The Foundry is not fully local today (headless runs send note text to the model API, and git pushes to a private `origin`), so the line is "no second store of the vault at a third party". Adopting past.dev would add one with:
- data on AWS in unnamed regions, unnamed model subprocessors (zero retention claimed), and no described export ([security](https://past.dev/security));
- a retention clock (365 days on the free tier) where the Foundry never deletes notes;
- no way to keep `private/` notes from the key holder other than not sending them;
- a closed engine whose supersession rule is not documented, in place of the gate's scripted checks;
- a per-credit bill for every recall.

Its strengths (per-user audiences, many-identity recall) answer a multi-user problem the Foundry does not have.

## 7. Ideas to take

| Idea | Size | Foundry file | Recommendation |
|---|---|---|---|
| Print `compiled_at` and the first `sources` link on each `related` hit | S | `system/scripts/vaultlib/retrieve.py`, `system/scripts/vaultlib/cli.py` | take |
| Golden case: an older input arrives after a newer fact and must not overwrite it | S | `system/tests/golden/ingest/` (new case) | take |
| Golden case: two inputs in one batch disagree; ingest picks one and records why | S | `system/tests/golden/ingest/` (new case) | take |
| Ingest rule: compare the input's date with the note's before a patch replaces a fact | M | `.claude/commands/ingest.md` | later, if the first case fails |
| Optional `was`/`now` fields on patch decisions, shown in the run's commit message | S | `.claude/commands/ingest.md`, `system/scripts/commit_runs.py` | later, when a changed fact needs tracing |
| One excerpt per `related` hit via FTS5 `snippet()` | S | `system/scripts/vaultlib/retrieve.py` | later (token cost in headless ingest) |
| Deterministic recall eval: questions with the expected note paths for `related` | M | `system/tests/` (new) | later, after the semantic-recall research Work Order |
| Per-claim validity windows (`validFrom`/`validTo`) | L | `system/schemas/`, ingest | skip |
| Per-note audiences inside a partition | L | schemas, index, gate | skip (one user) |
| BEAM dataset or LLM-judged scores | M | evals | skip (spec rules out model grading) |
| past.dev as the vault's store | L | intake, recall | skip |
