---
name: new-source
description: |
  Use when adding a Source: a feature that reads one connector tool into the morning brief. Use for /new-source, or
  when the user asks for a new Source, a new connector read or a new brief input from an MCP server.
---
# New Source

Spec: `docs/superpowers/specs/2026-10-23-factory-f4-line-skills-design.md` §3.2. `new_source.py` writes an extension Source that passes CI before any feature code exists; the feature then fills in the call and the parse.

**Extension Sources only.** When asked for a core Source, stop and say why: core's Source parts are five hand-kept lists (the `CORE` table in `system/tests/python/test_source_rule.py`, `smoke_check.sh`'s connector rows, `alerts.TAGS`, `conformance.bats`'s `TIMING_VALUES` and `TIMING_STEPS`, and `install_units.sh`), so a core Source cannot pass CI without editing five core files. New features go in extensions.

**The brief's room.** The Source runs inside the brief, which has two limits:
- **The brief prompt's word cap** (`system/tests/prep.bats`: `.claude/commands/brief.md` plus every extension's `brief/section.md`, at most 2,500 words; none are left since F5, so a Source with a brief section raises the cap in its own pull request). The scaffold writes no `brief/section.md`, so it stays under the cap. The first feature's section prompt does not fit: the owner raises the cap or `brief.md` is trimmed first.
- **The timing rule** (`conformance.bats`). No brief Source at the default 300 s fits: the brief's waits are within 35 s of its limit (6,565 of 6,600 s on 2026-10-31; the test prints `# brief: <sum> s of <limit> s`). A Source that runs inside the brief fails it in CI and needs its own unit or a raised brief limit, built in the feature's own pull request.

**Template or vault.** `system/config.md` exists only in a vault. There `--issue` is optional and no change file is written; in the template repository `--issue` is required.

## Steps

1. **Gather the inputs.**
   - The name: a short noun for what the Source reads, such as `drive_recent`. It becomes the alert tag, the smoke row and every file name.
   - The tool's full name: `mcp__<server>__<tool>`.
   - The server's name as `claude mcp list` prints it (`--server`).
   - The server's tool table: the name of a `lib_fetch.sh` table that holds the tool's bare name (`--tools <NAME>_TOOLS`; `grep -n '_TOOLS=(' system/scripts/lib_fetch.sh` lists the tables); for any other server, every tool of that server from this session's own tool list (`--server-tool <tool> …`, the tool included).
   - A one-line description (`--description`), written as a plain phrase: it is the change line and the manifest's first line.
   - What credential to renew and how (`--credential`, `--renew`).
   - The issue number (`--issue`, required in the template repository; a vault skips the change file).
2. **Run the script** from the repository root:
   `python3 .claude/skills/new-source/new_source.py <name> --tool <mcp__server__tool> --server "<server>" (--tools <table> | --server-tool <tool>…) --description "<one line>" --credential "<what>" --renew "<how>" [--issue <n>]`
   It writes `extensions/<name>/` (manifest, fetch, checker, brief prep, bats tests) and, in the template, one `- Added: <description>. (#<issue>)` line in its change file, `changes/<today>-source-<name>.md`. A trailing "." on the description is dropped.
3. **Run the suites**, one `system/scripts/test.sh` call each (it takes one target): `system/tests/conformance.bats`, `system/tests/python/test_source_rule.py`, `extensions/<name>/tests/<name>.bats`, and the brief prompt word check alone (the whole prep.bats takes minutes): `system/scripts/test.sh system/tests/prep.bats --filter "brief prompt is at most"`. All must be green before any feature code. When the task is the scaffold alone, stop here.
4. **Write the feature.**
   - Probe the tool once in a throwaway directory under `.scratch/` and record what came back (FOUNDRY.md "Probe first").
   - Write the feature's tests red first. **REQUIRED SUB-SKILL:** `superpowers:test-driven-development`.
   - Fill `ARGS` and `lines()` in `scripts/<name>_check.py`, and the `TODO(feature)` task sentence in the prompt in `scripts/<name>_fetch.sh` (and the manifest body's).
   - Write `brief/section.md`: where the section goes, print the lines verbatim, omit it when empty. `extensions/intraday/brief/section.md` is a short one. Check the word cap above first.
   - When a result can be too large for the model, pass `persisted` to `check_stream` as the handoffs extension does, with its own test. Without it, a too-large result exits 6.
   - When you change the fetch's `<NAME>_TIMEOUT` default, change the manifest's `budget` value to match.
5. **Review:** run `/foundry-review` before the pull request.

## Exit 2 (nothing written)

One `new_source: <reason>` line on stderr. The reasons, in the order checked:
- not run from the repository root (no `system/scripts/lib_fetch.sh`); a missing or unknown argument (argparse usage, `--tools` names no `lib_fetch.sh` table, or both `--tools` and `--server-tool`)
- the name is not `[a-z][a-z_]*` (no digits or dashes: the runner and the alert router read tags as `[a-z_]+`)
- `--tool` is not `mcp__<server>__<tool>`
- `--server`, `--description`, `--credential` or `--renew` is empty, or holds a quote, apostrophe, backslash, `$`, backtick or newline
- `extensions/<name>` exists; the name is a core alert tag or another extension's alert tag; a `<name>_fetch.sh` exists in `system/scripts/` or an extension's `scripts/` (it would share that fetch's log and reasons); the name is a core smoke row
- the tool's bare name is not in the `--tools` table; a `--server-tool` entry is not a tool name, or the bare name is not among them
- `--issue` is missing in the template repository
