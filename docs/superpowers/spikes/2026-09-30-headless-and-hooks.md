# Spike results: headless runs and hooks (§7.4)

**Date:** 2026-09-30 · **claude --version:** 2.1.286 (Claude Code) · **Mode used:** preferred (`--restricted --settings`) unless noted

`--restricted` help text (verbatim excerpt): "removes the built-in tools that run commands or code (Bash, PowerShell, REPL and the other code-running tools) and WebFetch unless --tools names them, and ignores user, project and local settings files (managed settings and --settings still apply; add --strict-mcp-config to skip MCP servers too). Also confines the file …". `--permission-prompts none` also exists ("anything that would prompt is denied automatically").

| # | Item | Command / procedure | Observed (excerpt) | Result | Spec impact |
|---|---|---|---|---|---|
| 1 | User settings, hooks, MCP ignored under --restricted | | | | |
| 2 | Project commands + CLAUDE.md load under --restricted | `run.sh probe` (restricted); `claude -p "Quote CLAUDE.md…" --restricted …` | "`/probe` isn't available in this session"; "NO-CLAUDE-MD". Fallback (`--setting-sources project`) loads both. Restricted + prompt inlined from the command file + `--append-system-prompt-file CLAUDE.md` runs the probe correctly | **FAIL** (preferred form) | §6.3: `run_headless.sh` must inline the command body (with `$ARGUMENTS` substituted) as the `-p` prompt and pass `--append-system-prompt-file CLAUDE.md` under `--restricted` |
| 3 | dontAsk denies unlisted tools, detectable | probe in both modes | Denied calls return `tool_result` `is_error: true` "Permission to use Write has been denied because Claude Code is running in don't ask mode"; result object has `permission_denials` (7 entries) while `subtype: success`, exit 0 | PASS | §6.3: treat a non-empty `permission_denials` in `--output-format json` as a run warning recorded in the ledger |
| 4 | Staging Edit allow; denies wiki/, CLAUDE.md, system/ | probe action 1–3 | Action 1 created `wiki/.staging/<id>/wiki/work/concepts/Spike.md` in a new nested dir; actions 2–3 denied with `is_error: true` | PASS | none |
| 5 | Read fence; tool-results still readable | probe actions 4–5 | `../outside.txt`: "is outside … the permissions.blockReadsOutsideWorkingDirectories" (fallback) / "--restricted confines the file tools" (restricted); `~/.ssh`: "directory that is denied by your permission settings" | PASS (headless); interactive tool-results part in Task 3 | none so far |
| 6 | Bash prefix rule matching and non-matching variants; set denied | probe 6–10; `chain` probe | `system/scripts/vault_index.py query …` allowed; `python3 …`, `$(…)`, `set` denied. `… ; echo chained` **allowed** (echo is a built-in read-only command); `; touch`, `&& cat ../outside.txt`, `| tee`, `; ls ~/.ssh`, `$(touch …)`, `> file` all denied, no files created | PASS (with note) | §7.3: note that read-only built-ins may be chained after an allowed command; writes and out-of-vault reads are still denied |
| 7 | --no-session-persistence writes no transcript | find `~/.claude/projects` after runs | Only an empty `memory/` dir created for the spike vault path; no `.jsonl` | PASS | none |
| 8 | Untrusted folder and moved vault | probe in a copied, never-trusted `vault-moved` with `--allowedTools` | `--allowedTools` and `--settings` rules apply (action 1 allowed, others denied). A project `.claude/settings.json` allow `Edit(/wiki/**)` was **ignored** in `-p` for the untrusted folder (no `hasTrustDialogAccepted` entry) | PASS (flags); project allows ignored until trusted — re-tested after Task 3 trust | §7.2: never rely on project-settings allows for headless runs (they appear once the folder is trusted); restricted mode avoids them entirely |
| 9 | @-import of missing file; sandbox + prep scripts | fallback run quoting CLAUDE.md; settings with `sandbox.enabled: true`, Bash `curl` and `touch ../x` | CLAUDE.md loads normally with missing `@system/config.md`. Sandbox: curl → "CONNECT tunnel failed, response 403 … deny network-outbound example.com:443"; out-of-vault touch did not happen. No sandbox CLI flag; enabled via settings | PASS | §7.2: enable `sandbox.enabled` in `headless.settings.json`; prep scripts run as `ExecStartPre` outside Claude, so no network allowance is needed for headless runs |
| 10 | Stop block yields one more turn; stop_hook_active | | | | |
| 11 | last_assistant_message holds the full digest turn | | | | |
| 12 | Interactive/attended signal; agent_id in subagents | | | | |
| 13 | SessionStart additionalContext shape, size limit, sources | | | | |
| 14 | User hooks don't run under run_headless; JARVIS_HEADLESS honoured | | | | |
| 15 | Hook latency budgets | | | | |
| 16 | Absolute-path allows from a codebase session | | | | |
| 17 | User-level /digest in a codebase session | | | | |
| 18 | Write into nested staging dirs; stage + Edit | `RUN_ID=spike2 run.sh ingest` (fallback) | Stub `stage` copied the note into `wiki/.staging/spike2/wiki/work/concepts/Existing.md`; Edit changed `old`→`new` in the copy; original untouched | PASS | none |

## Required spec edits
- (none yet)
