# Live vault usage survey

**Date:** 2026-10-21. **Window:** 2026-10-05 to 2026-10-21, read-only, counts only.
**Used by:** the factory plan (`docs/superpowers/2026-10-21-factory-plan.md`), which orders the F1 retrofits by this use.

Weeks: W41 = 10-05..11, W42 = 10-12..18, W43 = 10-19..21 (partial).

| # | Feature | Usage (W41 / W42 / W43) | Trend | Failures |
|---|---|---|---|---|
| 1 | Session digests → ingest | runs 113 / 107 / 48 (about 16 a day); digests 96 / 106 / 41 | flat to rising | 8 rejected and 1 aborted of 268 (96.6% ok); median 90 s |
| 2 | Now page | 413 lines added (26 / 276 / 111; 37 a day in W43); 254 closed | open 0 → 57 → 111 → **159** | 53.7 KB against the 25 KB mark |
| 3 | Brief / debrief | brief 16 of 17 days, debrief 16 of 16 | steady; about 31 KB now | 2 briefs rejected over Now.md (10-16, 10-18) |
| 4 | Meetings import | 24 / 35 / 18 imports | rising | 13 search failures, 5 ceiling holds, 2 duplicates |
| 5 | Inbox triage (mail) | 106 ticks → 75 Now lines; 55 alerts | falling | 26 failed ticks 10-19/20 (line cap); 55 of 107 ticks kept 0 rows |
| 6 | Intraday watch | from 10-20: 33 ticks, 111 items, 33 Now lines, 31 alerts | new | 0 fetch failures after #289 |
| 7 | Telemetry → RCA | about 300 ticks × 6 sources; 132 notes; 11 rca Now lines | yield falling | 50 failed source checks; **RCA filer 4 attempts, 0 tickets** |
| 8 | Work Orders | created 24 / 17 / 3 | declining | 5 failed (W41), 7 cancelled, 3 blocked; 11 PRs |
| 9 | Slack notices | 94 good runs, 123 events | working since W42 | 136 failed runs in W42 (fixed) |
| 10 | Handoffs | 23 fetches | steady | 1 |
| 11 | Vault-only change watch | 15 runs, 3 changes | low yield | 0 |
| 12 | Briefing Notes block | 1 of 14 briefs non-empty | unused | — |
| 13 | Personal partition | 0 notes | unused | — |

Findings:
- Digests are the main input (about 14 a day on weekdays), mostly from Foreman sessions in the vault.
- The Now page is the most-handled surface and is noisy: of 254 closed lines, 120 were dismissed (`[-]`) and 134 done; only 15 closed on evidence. Since 10-16 almost nothing is ticked while about 37 lines a day arrive; 159 are open. Mail and chat triage produce about half of all lines (mail link 114, Slack link 75, no evidence 147).
- Both brief failures are Now-page rejects.
- Built but unused or low-yield: the Notes block, the personal partition, the RCA filer (0 tickets), the vault-only change watch; Work Orders are tapering.
- Not measurable: `/query`, `/lint`, `/impact` and interactive `/rca` (not logged); triage thread counts per tick (not logged), so page loss after weekend gaps (10-19 11:31 and 10-20 08:31 kept 0 rows) can be neither confirmed nor ruled out.
