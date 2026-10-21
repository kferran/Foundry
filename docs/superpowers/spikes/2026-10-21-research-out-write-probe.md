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

## Bash side (spec Design 4, build task 1)

**Date:** 2026-10-21. **Binary:** Claude Code 2.1.305. Same setup as above (runner-built research profile, `command()`,
`<S>` in `<L>`, `session_env()` only, haiku), with the research `--tools` list and no plugin. `<W>` held
`wiki/a/private/x.txt`, `.env` and `wiki/a/public.txt`, each with its own marker. Each run's prompt named the commands
in order; `cat` of the public file is the positive control (its marker came back in every run). `tac` is a reader the
permission layer does not parse, so it isolates the sandbox; `cat` and `tac` gave the same result in every run. The
probe used the research profile, not `run_headless.sh` with `headless.settings.json`; the live ingest acceptance run
shows the headless file still loads with the extra rules.

| Run | Bash `cat`/`tac` of `wiki/a/private/x.txt` | Read tool, same file | Bash `cat`/`tac` of `.env` |
|---|---|---|---|
| deny `Read(wiki/*/private/**)`, no `cd` | masked ("No such file or directory") | | readable |
| same, `cd wiki` first | masked | (allowed, first probe above) | readable |
| deny `Read(//**/wiki/*/private/**)` only, `denyRead` `/**/.env*`, `cd wiki` | **readable** | (denied, first probe above) | readable |
| no rule; `denyRead` adds bare `wiki/*/private`, `cd wiki` | **readable** | | readable |
| no rule; `denyRead` adds the literal absolute path of `<W>/.env` | | | denied ("Permission denied") |
| both deny forms (relative and `//**/`), `cd wiki` | masked | denied | readable |
| no settings rule; `--disallowedTools "Read(/wiki/*/private/**)"`, `cd wiki` | **readable** | denied | |

Findings:
- Only a relative `Read(...)` deny reaches the sandbox: Claude Code resolves it against the launch directory and
  masks the folder, and a later `cd` does not move it. The `//**/` form and the CLI rule fence the Read tool after a
  `cd` but not Bash. The headless profile therefore keeps the relative pair and adds the `//**/` pair; neither form
  alone covers both layers. The spec's fallback (a launch-anchored CLI rule) does not fence Bash either.
- The `**/.env*` and `/**/.env*` `denyRead` globs mask nothing, with or without a `cd`; only a literal path did. That
  gap predates #314 and a `cd` does not change it, so this PR leaves the entry as it is and #326 tracks it.
  The `Read(//**/.env*)` permission rule did not stop `cat` either.

Not checked: whether the relative rule's mask covers a private folder created after launch (the folder existed at
launch in every run).
