# Probe: SessionEnd on a killed terminal, and the kept transcript's fields (#438)

Plan `docs/superpowers/archive/plans/2026-11-03-recall-r0-r1.md` Task 6. Run 2026-11-03 by the controller: real interactive `claude` in `tmux`, in a `.scratch/` clone of master at the R0 merge, hooks passed by `--settings` (no `install_hooks.sh`): `memory_recall.sh` on `SessionStart`, `memory_activity.sh` on `PostToolUse`, and on `SessionEnd` a `cat` of the hook input to a file followed by `memory_keep.sh`. `transcript_keep_dir` pointed at a scratch folder outside the clone.

## SessionEnd

| How the session ended | `SessionEnd` fired | `reason` | Transcript copied |
|---|---|---|---|
| `tmux kill-session` (SIGHUP to `claude`, a dropped terminal) | yes | `other` | yes (531 KB, mode 600) |
| `kill -KILL` on the `claude` process (a crash) | no | n/a | no |

Both sessions froze a state (`last_digest_at: 0`) and counted 5 events from 5 Bash calls before they ended.

Outcome: Task 11 (the tick-side sweep) is dropped. A crash (SIGKILL, an out-of-memory kill, a power loss) leaves no marker and is not backfilled; FOUNDRY.md says so.

## Transcript fields

One JSON object per line. Only entries with `type` `user` or `assistant` carry `message.content`; the transcript also holds `attachment`, `system`, `last-prompt`, `session-owner`, `permission-mode`, `mode`, `ai-title`, `tools-used`, `cost-state` and `file-history-snapshot` entries, which the excerpt skips by whitelisting the two types.

- Every `user` and `assistant` entry has `isSidechain` (boolean) and `timestamp` (ISO 8601 UTC with milliseconds and `Z`, for example `2026-11-03T13:49:10.026Z`).
- The prompt is a `user` entry whose `message.content` is a string.
- A tool result is a `user` entry whose `message.content` is a list of `tool_result` blocks (`tool_use_id`, plus a top-level `toolUseResult`).
- An `assistant` entry's `message.content` is a list of blocks: `text` (`text`) and `tool_use` (`name`, `input`; a Bash call's `input` has `command` and `description`).
- `thinking` blocks did not appear in this short session; the excerpt still drops them.
- The longest line was 131,825 characters (an `attachment`), well under `LINE_CAP` (2 MB).

Task 9's fixtures use these names as the plan lists them; nothing differs.
