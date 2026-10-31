# Probe: an excluded command's permission rules, and the denyWrite path forms

**Date:** 2026-10-31. **Binary:** Claude Code 2.1.311 on Linux (bwrap sandbox). **For:** the Work Order confinement spec §3.1a (`docs/superpowers/specs/2026-10-30-work-order-confinement-design.md`), PR B.

**Setup:** a throwaway folder `<P>` under `.scratch/` with a stub `system/scripts/ns.sh` that writes `raw/work/nightshift/<arg1>-<arg2>.md`. `claude -p … --strict-mcp-config --settings <file> --tools Bash --model haiku`, launched from `<P>`. The settings allowed `Bash(system/scripts/ns.sh add:*)` and `Bash(bash:*)`, asked for `Bash(system/scripts/ns.sh research:*)`, enabled the sandbox with no network and set `filesystem.denyWrite` to `<P>/raw/work/nightshift`.

## Which `excludedCommands` entry takes a command out of the sandbox (`--permission-mode auto`)

| `excludedCommands` | `allowUnsandboxedCommands` | `ns.sh add one` | `ns.sh research two` | `bash ns.sh add three` |
|---|---|---|---|---|
| `<P>/system/scripts/ns.sh` | false | sandboxed, write refused | refused (ask) | sandboxed, write refused |
| `<P>/system/scripts/ns.sh` | unset | sandboxed, write refused | refused (ask) | sandboxed, write refused |
| `system/scripts/ns.sh` | unset | sandboxed, write refused | refused (ask) | sandboxed, write refused |
| `system/scripts/ns.sh *` | unset | **ran outside, wrote its note** | refused (ask) | sandboxed, write refused |
| `system/scripts/ns.sh *` | false | **ran outside, wrote its note** | refused (ask) | sandboxed, write refused |
| `ns.sh` | unset | sandboxed, write refused | refused (ask) | sandboxed, write refused |

The same refusals held in `--permission-mode default`.

## Which `denyWrite` form refuses a sandboxed `touch <P>/raw/work/nightshift/t.md` (`dontAsk`)

| `denyWrite` entry | Result |
|---|---|
| `<P>/raw/work/nightshift` | `Read-only file system` |
| `<P>/raw/work/nightshift/**` | `Read-only file system` |
| `<P>/raw/*/nightshift` | written |
| `<P>/raw/*/nightshift/**` | written |
| `raw/*/nightshift/**` | written |

## Findings

- An `excludedCommands` entry takes a command out of the sandbox only in the prefix form `<command as typed> *`, and it works with `allowUnsandboxedCommands: false`. The command still meets the permission rules: the allowed subcommand runs, and the ask rule refuses `research` in a `-p` session in auto mode (it would prompt in an interactive one).
- A `bash <script> …` form is not the excluded command: it stays sandboxed, so its writes are refused.
- `denyWrite` honours a literal directory, with or without a trailing `/**`; no glob form refuses anything. So the denied folders are listed one by one: `raw/work/nightshift`, `raw/personal/nightshift`, `raw/shared/nightshift`, `system/codebases`, `system/nightshift`.
## In a project's `.claude/settings.json` (`--setting-sources project`, `dontAsk`)

| Entry | Result |
|---|---|
| `denyWrite: ["raw/work/nightshift"]` | `Read-only file system` |
| `denyWrite: ["./raw/work/nightshift"]` | `Read-only file system` |
| `denyWrite: ["/raw/work/nightshift"]` | written (read as the filesystem root) |
| `excludedCommands: ["system/scripts/sync.sh"]`, run with no arguments | ran outside, wrote |
| `excludedCommands: ["system/scripts/sync.sh *"]`, run with no arguments | ran outside, wrote |

- In a project's settings, a `denyWrite` path relative to the project (bare or `./`) holds; a leading `/` does not.
- `<command>` matches only that command with no arguments; `<command> *` matches it with or without arguments.
- **Not checked:** an interactive session's prompt for the ask rule.
