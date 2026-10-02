# Plan 3 live acceptance

**Date:** 2026-10-02 · **claude:** 2.1.286 (Claude Code) · **Commit:** 08f8496 (`feat/plan-3`) · **Vault:** throwaway clone in `~/.cache/jarvis-mem/vault` with `system/config.example.md` as config (`digest_min_events: 1`, `digest_min_minutes: 0`) and a seeded personal digest. Hooks were installed with `install_hooks.sh` into a scratch `CLAUDE_CONFIG_DIR` (`~/.cache/jarvis-mem/cfg`) and passed to `claude --settings`; the real `~/.claude/settings.json` was unchanged (sha256 before = after). Steps 2–6 were run by the user in real interactive sessions; Steps 1, 7 and 8 by the controller.

| Step | Check | Result | Notes |
|---|---|---|---|
| 1 | `install_hooks.sh` into scratch settings | PASS | `settings: changed`, `digest command: new`, exit 0; SessionStart, Stop and PostToolUse present |
| 2 | SessionStart recall in a vault session | PASS | reply quoted `## Jarvis vault recall` and `SEED-OUTCOME: the export job moved to Fridays.`; state `scope: vault` (spike 12's attended variables still fire) |
| 3 | activity → one request → capture | PASS | one "Stop hook error: Jarvis memory (not an error): …", then a `<vault-digest>` reply; digest written to `raw/personal/notes/`, `validate` 0 errors, `created_at` with `-06:00` offset |
| 4 | no second request | PASS | "Say hi." produced no Stop-hook block and no new digest |
| 5a | `/clear` | PASS | recall injected again after `/clear` |
| 5b | `claude --continue` (spike 13) | observed | resume started a **new** session id (`3a932cac`); state was not reused, scope re-frozen as vault, a fresh digest captured (1 redaction) |
| 6 | codebase session and partition wall | PASS | first attempt was mistakenly typed into the resumed vault session (no codebase state existed; not a hook fault). Re-run from `~/.cache/jarvis-mem/code`: recall `Scope: codebase code (work)` with no SEED-OUTCOME; `related "export"` returned nothing (no personal notes); the codebase session's digest was captured to `raw/work/notes/` and validates |
| 7 | latency | PASS | SessionStart 356 ms (< 3000), PostToolUse avg 1 ms (< 30), Stop 26 ms (< 150) |
| 8 | intake compiles the captured digests | PASS | two headless ingests, exit 0, 0 permission denials: personal batch of 3 (seed + 2 captured) → `ExportJobSchedule.md`, `VaultRecallAndIndexing.md`; work digest → `VaultIndexRelatedCommand.md`; all inputs archived; lint 0 errors |

## Verdict

**PASS.** The hooks recall, request once, capture redacted schema-valid digests, respect the partition wall from a codebase session, stay well inside their latency budgets, and their digests compile through intake. No fix was needed during acceptance.
