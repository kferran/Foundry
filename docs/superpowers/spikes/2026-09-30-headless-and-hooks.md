# Spike results: headless runs and hooks (§7.4)

**Date:** 2026-09-30 · **claude --version:** 2.1.286 (Claude Code) · **Mode used:** preferred (`--restricted --settings`) unless noted

`--restricted` help text (verbatim excerpt): "removes the built-in tools that run commands or code (Bash, PowerShell, REPL and the other code-running tools) and WebFetch unless --tools names them, and ignores user, project and local settings files (managed settings and --settings still apply; add --strict-mcp-config to skip MCP servers too). Also confines the file …". `--permission-prompts none` also exists ("anything that would prompt is denied automatically").

| # | Item | Command / procedure | Observed (excerpt) | Result | Spec impact |
|---|---|---|---|---|---|
| 1 | User settings, hooks, MCP ignored under --restricted | | | | |
| 2 | Project commands + CLAUDE.md load under --restricted | | | | |
| 3 | dontAsk denies unlisted tools, detectable | | | | |
| 4 | Staging Edit allow; denies wiki/, CLAUDE.md, system/ | | | | |
| 5 | Read fence; tool-results still readable | | | | |
| 6 | Bash prefix rule matching and non-matching variants; set denied | | | | |
| 7 | --no-session-persistence writes no transcript | | | | |
| 8 | Untrusted folder and moved vault | | | | |
| 9 | @-import of missing file; sandbox + prep scripts | | | | |
| 10 | Stop block yields one more turn; stop_hook_active | | | | |
| 11 | last_assistant_message holds the full digest turn | | | | |
| 12 | Interactive/attended signal; agent_id in subagents | | | | |
| 13 | SessionStart additionalContext shape, size limit, sources | | | | |
| 14 | User hooks don't run under run_headless; JARVIS_HEADLESS honoured | | | | |
| 15 | Hook latency budgets | | | | |
| 16 | Absolute-path allows from a codebase session | | | | |
| 17 | User-level /digest in a codebase session | | | | |
| 18 | Write into nested staging dirs; stage + Edit | | | | |

## Required spec edits
- (none yet)
