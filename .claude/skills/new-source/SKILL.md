---
name: new-source
description: |
  Use when adding a Source: a feature that reads one connector tool into the morning brief. Use for /new-source, or
  when the user asks for a new Source, a new connector read or a new brief input from an MCP server.
---
# New Source

Spec: `docs/superpowers/specs/2026-10-23-factory-f4-line-skills-design.md` §3.2. `new_source.py` writes an extension Source that passes CI before any feature code exists; the feature then fills in the call and the parse.

**Extension Sources only.** When asked for a core Source, stop and say why: core's Source parts are five hand-kept lists (the `CORE` table in `system/tests/python/test_source_rule.py`, `smoke_check.sh`'s connector rows, `alerts.TAGS`, `conformance.bats`'s `TIMING_VALUES` and `TIMING_STEPS`, and `install_units.sh`), so a core Source cannot pass CI without editing five core files. New features go in extensions.

**The brief's room.** The Source runs inside the brief. One more brief Source at the default 300 s fits the timing rule; the next one fails it in CI and needs its own unit, built by the feature that hits it.

## Steps

1. **Gather the inputs.**
   - The tool's full name: `mcp__<server>__<tool>`.
   - The server's name as `claude mcp list` prints it (`--server`).
   - The server's tool table: the name of a `lib_fetch.sh` table that holds the tool's bare name (`--tools <NAME>_TOOLS`); for any other server, every tool of that server from this session's own tool list (`--server-tool <tool> …`, the tool included).
   - A one-line description, what credential to renew and how (`--description`, `--credential`, `--renew`).
   - The issue number (`--issue`, required in the template repository; a vault skips the CHANGELOG line).
2. **Run the script** from the repository root:
   `python3 .claude/skills/new-source/new_source.py <name> --tool <mcp__server__tool> --server "<server>" (--tools <table> | --server-tool <tool>…) --description "<one line>" --credential "<what>" --renew "<how>" [--issue <n>]`
   It writes `extensions/<name>/` (manifest, fetch, checker, brief prep and section, bats tests) and, in the template, one `- Added: <description>. (#<issue>)` line under today's date in CHANGELOG.md. A trailing "." on the description is dropped.
3. **Run the three suites** with `system/scripts/test.sh`: `system/tests/conformance.bats`, `system/tests/python/test_source_rule.py` and `extensions/<name>/tests/<name>.bats`. All must be green before any feature code. When the task is the scaffold alone, stop here.
4. **Write the feature.**
   - Probe the tool once in a throwaway directory under `.scratch/` and record what came back (FOUNDRY.md "Probe first").
   - Write the feature's tests red first. **REQUIRED SUB-SKILL:** `superpowers:test-driven-development`.
   - Fill `ARGS` and `lines()` in `scripts/<name>_check.py`, and the `TODO(feature)` task sentence in the prompt in `scripts/<name>_fetch.sh` (and the manifest body's).
   - When a result can be too large for the model, pass `persisted` to `check_stream` as the handoffs extension does, with its own test. Without it, a too-large result exits 6.
   - When you change the fetch's `<NAME>_TIMEOUT` default, change the manifest's `budget` value to match.
5. **Review:** run `/foundry-review` before the pull request.

## Exit 2 (nothing written)

One `new_source: <reason>` line on stderr. The reasons, in the order checked:
- not run from the repository root (no `system/scripts/lib_fetch.sh`); a missing or unknown argument (argparse usage, `--tools` names no `lib_fetch.sh` table, or both `--tools` and `--server-tool`)
- the name is not `[a-z][a-z_]*` (no digits or dashes: the runner and the alert router read tags as `[a-z_]+`)
- `--tool` is not `mcp__<server>__<tool>`
- `--server`, `--description`, `--credential` or `--renew` is empty, or holds a quote, apostrophe, backslash, `$`, backtick or newline
- `extensions/<name>` exists; the name is a core alert tag or another extension's alert tag
- the tool's bare name is not in the `--tools` table; a `--server-tool` entry is not a tool name, or the bare name is not among them
- `--issue` is missing in the template repository; CHANGELOG.md has no `## Changes` heading
