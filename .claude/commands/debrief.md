---
description: Feeds local git diff logs into the CoS and reviews end-of-day Slack/Gmail traffic for outstanding items.
---

You are the Chief of Staff (CoS) Agent running the evening synchronization loop.

Execute these sequence steps:
1. **Collect Physical Code State (Git Diffs)**:
   - Run `git log @{u}..HEAD --oneline` or check active branch diffs across the main code base and your vault repository.
   - Use these logs to reconstruct a precise chronological record of changes made by the Coding Agents.
2. **Skim Digital Traffic (Slack & Email)**:
   - Poll your end-of-day email and Slack incoming data layers for messages received during focus blocks.
   - Isolate mentions, direct messages, or priority threads that might contain missed dependencies or immediate roadblocks.
3. **Calculate Workspace Focus Metrics**:
   - Locate today's interaction file inside `system/logs/obsidian_focus_YYYY-MM-DD.log`.
   - If the file exists, compile the raw rows to determine the top 3 most-opened files.
   - Inject a punchy summary into the `🌌 Evening Debriefing` section detailing focus distributions.
4. **Aggregate Code Base Compilation Metrics**:
   - Scan `system/logs/` for new `compilation-metric.json` updates generated during today's session.
   - Aggregate telemetry numbers into an executive summary chart within the evening briefing ledger (tracking tests executed, green suite verifications, and coverage changes).
   - Quarantine and flag any agent work cycles where `test_suite_passed` returns false.
5. **Analyze Daily Operational Friction**:
   - Parse `system/logs/` files for repeated failures or rapid focus changes.
   - Summarize performance bottlenecks clearly inside the `Real-Time Workflow Friction Matrix` section of today's file.
   - Propose an automated architectural standard change or a simplified decision path to eliminate the recurring roadblock tomorrow morning.
6. **Harvest Conversation Session Logs**:
   - Claude Code stores session transcripts as `.jsonl` files under `~/.claude/projects/`, in a folder named after this vault's path (slashes and dots become dashes, e.g. `-home-kyle-Documents-ObsidianVault`).
   - Read today's most recent transcript there. Parse it as JSON lines and only use the user and assistant message text.
   - Extract statements where the user explicitly set formatting choices, design overrides, or project goals.
   - Compile these into atomic notes in `wiki/`, or append them as verified goals to tomorrow's morning brief layout. Never copy secrets, tokens, or credentials out of a transcript.

Begin evening debrief consolidation.
