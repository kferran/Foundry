# Probe: research Work Order cannot write out/ (#314)

**Date:** 2026-10-21
**Binaries:** Claude Code 2.1.305 for every run; the `cd` run also on 2.1.304 and 2.1.303.
**Managed settings:** none present (`/etc/claude-code/` absent), so `--restricted` loaded only `--settings`.

## Setup

The runner's own builders made each run: `nightshift_session.profile(vault, "research", …)` wrote `<S>`, and
`nightshift_session.command("research", …)` built the command line (`-p`, `--restricted`, `--strict-mcp-config`,
`--settings <S>`, `--permission-mode dontAsk`, `--permission-prompts none`, the research `--tools` list, the
superpowers `--plugin-dir`, `--output-format stream-json --verbose`). The session ran with cwd `<W>` (which held
`out/` and an empty `code/`), `<S>` sat in a sibling folder `<L>` (as the runner puts it in the item's log folder), and
the environment was the `session_env()` allowlist only (`env -i`).

Deviations to keep runs tiny: `--model haiku`, `--max-turns 3`, `--max-budget-usd 0.25`,
`--no-session-persistence`. The five rule-form runs used `--tools Write,Read` and the research profile file with
only `Read` plus the form under test. `<W>` sat in a git-ignored folder of a git repository; `--restricted` ignores
that repository's project settings.

Each run's result: does `<W>/out/a.md` exist, and does the stream's `result.permission_denials` list it. Every
denial carried "Permission to use Write has been denied because Claude Code is running in don't ask mode".

## Results

| Rule in `<S>` (Write and Edit) | Bash `cd` before the Write | Result |
|---|---|---|
| `./out/**` | no | allowed |
| `out/**` | no | allowed |
| `/out/**` | no | denied: `/` anchors at `<L>`, the folder of `<S>`, not `<W>` |
| `//<W>/out/**` | no | allowed |
| no rule (negative control) | no | denied |
| `./out/**`, runner-built profile, full research tools and plugin | no | allowed |
| same, plus `Read(//<W>/**)` denied | no | allowed: a Read deny does not block Write |
| `./out/**` | `cd code` | **denied** on 2.1.305, 2.1.304 and 2.1.303 |
| `//<W>/out/**` | `cd code` | allowed |

The same mechanism applied to a deny rule (`<S>` also denies `Read(wiki/*/private/**)`, `<W>/wiki/a/private/x.txt`
holds a marker string):

| Run | Result |
|---|---|
| Read the file, no `cd` (control) | denied |
| `cd wiki`, then Read the file by absolute path | **allowed**: the marker came back in the tool result |
| Deny rewritten as `Read(//**/wiki/*/private/**)`; `cd wiki`, then Read | denied; the marker never came back |

Rules passed on the command line (`--allowedTools`, the form `run_headless.sh` uses for the staging folder):

| CLI rule | Bash `cd` first | Result |
|---|---|---|
| `Write(/out/**)` | no | denied (cause not established; the fix emits both Write and Edit forms) |
| `Edit(/out/**)` | no | allowed: `/` anchors at the launch directory |
| `Edit(/out/**)` | `cd code` | allowed |

## Finding

A bare or `./` path rule resolves against the session's current directory at check time, and a Bash `cd` moves
that directory for the rest of the session. After `cd code`, `./out/**` means `<W>/code/out/**`, so the findings
note at `<W>/out/<Name>.md` falls outside it and dontAsk denies the Write. The same shift turns a relative deny rule
off. No version change between 2.1.303 and 2.1.305 explains #314: all three deny after a `cd`. Absolute `//` rules
held in every run.

Not checked: the failing live order's stream for a Bash `cd` before its denied Write (the probe shows the
mechanism, not that this order used it), and a `/`-anchored rule inside a settings file after a `cd`.
