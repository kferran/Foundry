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

## Can a sandboxed session reach outside through the excluded command? (review of PR B, same day)

Project settings: `excludedCommands: ["system/scripts/ns.sh *"]`, allow `Bash(system/scripts/ns.sh add:*)`, `cd`, `sed` and `touch`, `autoAllowBashIfSandboxed`, `denyWrite` on the queue folder; auto mode.

| Steps | Result |
|---|---|
| sandboxed `sed -i` on `system/scripts/ns.sh`, then `system/scripts/ns.sh add edited` | the edited script **ran outside the sandbox** and wrote into the denied folder, no prompt |
| `system/scripts/ns.sh add compound; touch <denied>/x.md` | the whole line stayed sandboxed; both writes refused |
| `cd .scratch/copy`, then `system/scripts/ns.sh add viacd` | the copy's script **ran outside the sandbox** and wrote into the denied folder, no prompt |

- An excluded command is matched by the text typed, so any code a sandboxed session can write and then call by that name runs outside the sandbox: the script itself, what it imports or sources, or a copy under a writable folder reached with `cd`. The same holds for any excluded `git` command, whose `.git/config` (`core.sshCommand`, hooks) is writable from the sandbox.
- So `excludedCommands` cannot carry the CLI past the write deny safely. Spec §3.1a needs another mechanism (owner decision).
