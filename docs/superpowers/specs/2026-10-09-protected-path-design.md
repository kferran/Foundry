# Work Orders: a protected-file path the session can write

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #92.

## 1. Problem

A plan session cannot write under `.claude/`, so the plan prompt tells it to write such a file to `.nightshift/protected/<that same path>`, and the runner commits it. That path, `.nightshift/protected/.claude/commands/<file>`, contains a `.claude` segment. A `--restricted` session in `dontAsk` mode refuses file-tool writes to any path with that segment (probed 2026-10-09: the Write tool was refused there and allowed at `.nightshift/protected/plain/`; Bash was allowed at both).

The `/ingest` preference-notes Work Order followed the prompt, was refused twice and failed with "no result" (2026-10-09 04:15Z and 17:30Z). The #79 order succeeded only because its session wrote those files with Bash.

## 2. Change

- The plan prompt names `.nightshift/protected/claude/<path under .claude/>`, with no leading dot, and says the dotted form is refused.
- `nightshift_deliver.protected_files` maps a proposal under `claude/` to `.claude/<path>`, so it passes through the same checks: only `.claude/skills/`, `.claude/commands/` and `.claude/agents/`, no symlinks, regular files under 256 KB.
- Proposals under the old `.claude/` form are still read, so an order queued before the update still delivers.

## 3. Tests

- `protected_files`: a file under `claude/commands/` comes back as `.claude/commands/…`, and `claude/settings.json` is refused like `.claude/settings.json`.
- The plan prompt names `.nightshift/protected/claude/` and not `.nightshift/protected/.claude/`.
- End to end: a session that writes `.nightshift/protected/claude/skills/demo/SKILL.md` gets `.claude/skills/demo/SKILL.md` on the pushed branch.

All three fail before the change. Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_session.py`, `test_nightshift_run.py`) and the gate.
