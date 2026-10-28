# Finishing the in-flight items

**Date:** 2026-10-28
**Goal (owner, 2026-10-28):** finish every roadmap row that is in progress or in flight.
**Inputs:** the roadmap (#400); two read-only audits of origin/master on 2026-10-28 (the safety findings #298, #317 to #321, #326; the reliability findings #299, #301, #302, #332, #353, #386). Their tables are summarized here. Every verdict has file:line evidence in the audit reports, and each PR re-checks its finding before changing code.

## 1. Inventory

The 11 in-flight rows, and who can finish each:

| Row | What is left | Who |
|---|---|---|
| Roadmap candidates (#333) | #399 merge; `tag-writers` in the vault; tuning after two weeks of writer data | Owner, then a tuning grill about 2026-11-10 |
| The console (#377) | #392 merge; C2 and C3 | Owner merge; the console session builds |
| Health scorecard | Live check (#380) | Owner |
| Ingest evals (#218) | Measuring run and 3-run baseline on the server | Owner |
| CTO gap plan | Live checks for phases A (Task 11), C (Task 3) and D (Task 11); phases E to G | Owner checks; E to G come after this plan |
| Hardening after the audit | 20 open findings (below) | This plan, phases 1 to 3 |
| Delivery notifications (#28) | The owner's `notify.sh --check`; Slack captures, at grill step 3 | Owner check; the captures grill in phase 4 |
| Simplify the template | Step 4, the prompt layer (grill first) | Phase 4 |
| Fixes from live use | Ongoing by design | Each new issue takes the fast lane |
| Smoke check | Built and merged; its row still says "Built" | Phase 1, roadmap edit |
| 12. minutes plugin | Its own repository and session | Outside this plan |

Already fixed and only waiting on ticks: #298's three high-severity findings (tick re-screen #324/#330, research `private/` #324, publish symlinks #323/#328), and #299's long brief line (#366, for lines in now.py's form). #401 (the watch read as ok) is merging.

## 2. Phases

Each item is one pull request, built natively in a `.scratch/` worktree, with a failing test first. Fast-lane PRs auto-merge on green CI. A PR that touches a safety surface (settings, sandbox, publish gate, redaction, hooks, connector confinement, the Work Order runner, notify) waits for the owner's merge. Phases 1 and 2 run interleaved: a phase 2 PR waits on the owner, so phase 1 work fills that wait.

### Phase 1: fast-lane fixes (auto-merge)

| # | Item | Issue | Value |
|---|---|---|---|
| 1.1 | The watch's whole tick, and its smoke reason | #302 | A failed Slack or mail session shows as failed in the brief. In review as #401 |
| 1.2 | `wiki/<p>/Now.md` no longer an orphan in lint | #302 | Lint stops warning about the one page every vault has |
| 1.3 | The watch's blank counts and the doubled `other: other:` | #302 | Readable smoke and log lines |
| 1.4 | A wall alert names no note path | #386 | A note's path stops reaching Slack through an alert |
| 1.5 | Docs sweep: the stale "gitignored" and "phase 6a" text, `gh` in Requirements, `setup.md:8`, the `query` takes-SQL hint, the `install_units.sh` hint when `XDG_RUNTIME_DIR` is unset, the notify unit comment | #302, #299 | A new install hits fewer wrong instructions |
| 1.6 | Roadmap: the Smoke check row reads Complete; tick the fixed #298 and #299 items | | The records match the code |

### Phase 2: small safety fixes (each waits for the owner's merge)

In order of harm if exploited:

| # | Item | Issue | Value |
|---|---|---|---|
| 2.1 | Redaction: `_`-joined names (`AWS_SECRET_ACCESS_KEY=`), JSON `"password":` outside credentials, PGP blocks, `sk_live_`, and the pre-commit scan using the same rules; `password: <ordinary word>` no longer redacted | #298, #301 S8, #386 | Secrets stop reaching digests, notes and notify text, and ordinary wording stops being masked |
| 2.2 | Deny `git commit --no-verify` and `-n` | #298 | The pre-commit secret scan can't be skipped by a pre-approved command |
| 2.3 | The research publish holds `run.lock` | #298 | A concurrent recover can't quarantine a run or apply it twice |
| 2.4 | Slack-escape the model's text in notices | #298 | Model text can't post `<!channel>` or mention people |
| 2.5 | A hand-shaped Now line in a brief is cut or dropped with a note, never a reason to reject the brief | #299 | One bad line no longer costs the morning brief |
| 2.6 | A finished Work Order adds a Now line (review and merge, answer, or fix) | #332 | Finished work reaches the Now page instead of waiting to be noticed |
| 2.7 | The headless profile gets the sandbox network keys the Work Order profiles have | #298 | Backs the docs' "no network" claim with config. It re-runs the live acceptance steps, because it changes `system/headless.settings.json` |
| 2.8 | The secret scan skips `extensions/*/tests/` fixtures | #302 | A fresh vault's `/lint` stops opening with 6 false errors. It narrows the scan, so the owner looks at it |

### Phase 3: Work Order confinement (one grill, one spec, then PRs)

#317, #318, #319, #320, #321 and #326 share one surface: what a Work Order session can read, where it can send it, and what runner state it can change. #319's fix depends on #326 (a glob deny masks nothing on Linux, so sibling workspaces need literal paths). The worst combination is #326 with #317: a session reads a `.env` and queues a research order to any host. One grill settles the options; one spec covers them all:

- **#326:** probe what the sandbox's `denyRead` matches, then list literal paths.
- **#317 and #318:** the owner approves a research order's hosts (stop pre-allowing `nightshift.py add:*` for new hosts), and names that resolve inside the network are refused.
- **#319:** deny sibling `nightshift-*` workspaces.
- **#320:** move runner state where a session can't write it, or deny the writes.
- **#321:** record the base commit at `add`, or accept the risk (owner's call).

The #301 rulings ride in the same grill, because they are the same kind of question: S9 (stale claims in a research report reach ingest), S10 (headless Read across partitions), S11 (`deniedMcpServers`), and the text of the S1 revisit trigger.

### Phase 4: specs and grills for the rest

- **#299, brief retry and unit time limits:** a rejected brief retries once; intake, smoke, the watch and the calendar get limits that fit their worst case (conformance already lists the five overruns). One small spec, tied to #122.
- **#353, the brief checks an item's live status:** a spec. Jira, Slack and the calendar have no evidence check today.
- **Simplify step 4, the prompt layer:** grill first. The CLAUDE.md prune folds in.
- **Delivery notifications, Slack captures:** the grill at step 3, with the chat-gateway research brief as input.

## 3. Decisions for the owner

1. **/setup prompts (#302):** allow the read-only setup commands that still prompt (`discover_codebases.sh`, `inspect_codebase.sh`, `calendar_fetch.sh --check`) and list the rest in FOUNDRY.md. Recommended: yes. It's a settings change, so you merge it.
2. **Phase order:** phases 1 and 2 interleaved, as above, then the phase 3 grill. Recommended: yes, so no PR waits on another.
3. **Phase 3 as one grill:** recommended. The six issues share one surface and one test harness.

Your merges and checks from section 1 can happen at any time: #399, #392, #380, the #218 baseline, the phase A, C and D checks, and `notify.sh --check`.

## 4. Done when

Every row in section 1 reads Complete in the roadmap, or names only an owner step or a later program (gap plan E to G, the console's C2 and C3, minutes).
