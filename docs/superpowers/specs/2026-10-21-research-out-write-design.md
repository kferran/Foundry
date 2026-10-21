# Absolute path rules for session profiles (#314)

**Date:** 2026-10-21
**Status:** draft for the owner
**Grill:** not an owner idea: live vault bug report #314
**Builder check:** 2026-10-21, three questions: the live order's `cd` (confirmed, §Cause), sandbox paths (in scope, §Design 4, with a Bash-side probe first), and the failure reason's precedence (builder's call, §Design 3).
**Blueprint:** Work Order
**Lane:** feature (a safety surface: the Work Order session profile); the owner merges

## Why

A research Work Order drafted its findings note, but its Write to `<workspace>/nightshift-<id>/out/<Name>.md` was
denied under `dontAsk`. The session ended with subtype success, `out/` stayed empty, and the runner failed the item
with reason `no result`, which told the owner nothing. The owner recovered the note from the stream by hand.

## Cause (probe: `docs/superpowers/spikes/2026-10-21-research-out-write-probe.md`)

Claude Code resolves a bare or `./` path rule against the session's current directory when it checks the call, and
a Bash `cd` moves that directory for the rest of the session. A research session that runs `cd code` to read the
code copy turns `Write(./out/**)` into `<workspace>/code/out/**`; the findings path no longer matches, and dontAsk
denies it. Claude Code 2.1.303, 2.1.304 and 2.1.305 all behave this way, so no version change explains the report.
Without a `cd`, `./out/**` works in the runner's exact setup. `//<abs>/out/**` held with and without a `cd`.

Confirmed in the live order (the live vault's session read its `stream.jsonl`, 2026-10-21): all 22 Bash calls
started with `cd <absolute path>`, and the last one before the denied Write went into `context/entities`, so
`./out/**` resolved to `context/entities/out/**`.

## Goals

- A research session can write `out/` wherever its Bash shell has moved.
- No session profile carries a path rule that a `cd` can move, allow or deny.
- A denied write to `out/` reports as its own failure reason.

Non-goals: stopping sessions from running `cd`; changing what any profile allows or denies.

## Other relative rules (grep of every settings file and settings builder)

| Where | Rule | Affected |
|---|---|---|
| `system/nightshift/research.settings.json` | `Write(./out/**)`, `Edit(./out/**)` | yes: this report |
| `system/nightshift/plan.settings.json` | bare `Write`, `Edit` (no path) | no |
| `nightshift_session.profile()` | `Read(//<abs>…)` denies | no: absolute |
| `system/headless.settings.json` | denies `Read(wiki/*/private/**)`, `Edit(wiki/*/private/**)` | **yes, fails open**: the probe read a file under `wiki/*/private/` after `cd wiki` |
| `run_headless.sh` | `--allowedTools "Edit(/wiki/.staging/<run>/**)"` | no: a CLI `/` rule anchors at the launch directory; the probe wrote through it after a `cd` |
| `.claude/settings.json` | `/wiki/**`, `/wiki/*/private/**` and others | no: `/` anchors at the project folder (interactive sessions; not probed after a `cd`) |
| `lib_confine.sh` (connector and intraday fetches) | tool names only, no paths | no |

## Design

1. **Research profile.** `profile()` takes the session's working directory (new argument `cwd`) and rewrites every
   `Tool(./<p>)` rule in `allow` and `deny` to `Tool(//<cwd without its leading />/<p>)`. `research.settings.json`
   keeps `./out/**` as the readable source form. Both callers already hold the directory: `_run_session` (its
   `cwd`) and the self-test (its temporary directory). Builder's call: use `Path(cwd).resolve()`, and emit the
   unresolved form as well when the two differ (a symlinked `order_workspace`).
2. **Headless profile.** The two private-folder denies become `Read(//**/wiki/*/private/**)` and
   `Edit(//**/wiki/*/private/**)`, the absolute-glob form the same file already uses for `.env` (the probe showed
   the `Read` form still denies after `cd wiki`). *Builder's call:* this half is headless confinement, a second safety
   surface, and ships in this PR: two strings and one test, the same defect class, and the owner merges the PR either way. It also matches a
   `wiki/*/private/` folder outside the vault, which only denies more. FOUNDRY.md's Private folder paragraph and the
   comment in `vault_integrity.bats` change to match.
   *Superseded 2026-10-21, was "The two private-folder denies become `Read(//**/wiki/*/private/**)` and
   `Edit(//**/wiki/*/private/**)`":* the Bash-side probe showed only the relative rule reaches the sandbox, so both
   forms ship, and the `vault_integrity.bats` test checks that each bare or `./` deny has its `//**/` twin. The `.env`
   sandbox glob masks nothing with or without a `cd` and is tracked separately (probe, Bash side).
3. **Failure reason.** `_run_session` returns the file paths from the result event's `permission_denials` for the
   Write and Edit tools. When `_deliver_research` finds no `result.json` or no findings note and a denied path lies
   under `out/`, it fails the item with reason `out write denied`, and its `needs` line names the denied path and
   points at `stream.jsonl`. Every other case keeps `no result`. *Builder's call:* `budget` and `cancelled` keep
   their precedence (they return before delivery), and denials are read from the result event only.
4. **Sandbox paths (builder check).** Goal 2 covers `sandbox.filesystem.*` too: all three profiles list the
   relative glob `**/.env*` under `denyRead`, and Read deny paths are merged into the sandbox's `denyRead`
   (FOUNDRY.md, Private folder). Before the plan settles, the build's first task re-runs the probe's `cd wiki` case
   with Bash `cat <absolute path>` in place of the Read tool, for the private folder and a `.env` file. Each
   relative sandbox entry the probe shows can move is rewritten to its absolute form in `profile()` and
   `headless.settings.json`, and both new tests extend to `sandbox.filesystem.*`. If the absolute glob misbehaves
   inside the sandbox, the fallback is a launch-anchored CLI rule from `run_headless.sh`
   (`--disallowedTools "Read(/wiki/*/private/**)"`), which the probe showed holds after a `cd`.

## Tests (each fails first)

- `test_nightshift_session.py`: for both kinds, `profile(…, cwd=<tmp>)` has no file-tool rule outside the `//` and
  `~/` forms (`^(Read|Write|Edit|Glob|Grep|NotebookEdit)\((?!//|~/)`: a bare, `./`, `../` or `/`-anchored path;
  `WebFetch(domain:…)` is not a path rule), and the research profile allows
  `Write(//<tmp>/out/**)` and `Edit(//<tmp>/out/**)`.
- `vault_integrity.bats`: `headless.settings.json` has no deny rule with a bare or `./` path (extends the existing
  "no /-anchored rules" test), and the private-folder test checks the `//**/` forms.
- `test_nightshift_run.py`: a fake session whose stream denies a Write under `out/` and writes nothing fails with
  reason `out write denied`; a fake session that writes nothing without a denial still fails with `no result`.

Live acceptance: one research Work Order in a throwaway vault under `.scratch/` whose brief makes the session run
`cd code` before writing; it must publish its findings note.

## Out of scope

- The interactive `.claude/settings.json` `/`-anchored rules: anchored at the project folder, and no report.
- Checking that the live order ran a `cd`: the owner's stream, not template code.
- A prompt line telling sessions not to `cd`: the absolute rules make the shell directory irrelevant.

## Risks

- Claude Code changes how `//` rules resolve: the self-test runs the plan profile only, so it would not notice. The
  live acceptance run and the new failure reason make such a change visible on the first failed order.
- A `cwd` with characters the rule syntax treats as special (`(`, `)`, `*`) would break the rule. `order_workspace`
  is an owner path; the builder escapes or refuses such a path (builder's call).

## Size

One PR: about 30 lines of code across `nightshift_session.py`, `nightshift_run.py` and `headless.settings.json`, plus
tests and the FOUNDRY.md sentence.
