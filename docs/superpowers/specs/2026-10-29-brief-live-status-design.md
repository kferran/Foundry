# The brief checks a PR, issue or Work Order before calling it open

**Date:** 2026-10-29
**Status:** draft, for the owner's review
**Grill:** not an owner idea: issue https://github.com/kferran/Foundry/issues/353, filed from the live vault (in-flight plan `docs/superpowers/2026-10-28-in-flight-plan.md` phase 4)
**Builder check:** 2026-10-29, three questions and three wrong claims, all settled as my calls: a bare `#N` resolves when exactly one GitHub repository is known (§3.1); the prep writes the current state inline into every input, so the sections the brief copies verbatim carry it (§3.1, §3.2); at most 20 references a brief, each under its own timeout (§3.1); the brief's timeout key, the word-cap test and the Sources line are as the code has them (§3.1, §3.3, §4)
**Blueprint:** none: a prep step and a brief rule; no new feature shape.
**Lane:** feature, one pull request with a short plan. It edits `brief.md` (a headless command), so it re-runs the live acceptance steps.

## 1. Why

The 2026-10-22 brief, generated at 06:05, said in Where yesterday landed: "PR #296 … is open and needs three live Slack checks after merge." PR #296 had merged at 08:16 the day before, and its Now line was ticked at 09:50 by the Now check. The sentence came from the 2026-10-20 debrief, which the brief copies through `yesterday.md`, and nothing checked it again.

The Now page itself was right: `now.check` closes a line whose evidence is a pull request, an issue or a Work Order on every intake tick. The stale claim came from text the brief copies: the last debrief, and digests summarised there.

## 2. Goals, non-goals, anti-goals

- **Goal:** the brief never calls a GitHub pull request, a GitHub issue or a Work Order open, waiting or in progress when it has merged, closed or finished; it shows the current state.
- **Non-goals (smallest version):** Jira keys, Slack or Gmail threads and calendar claims (#353 lists them). They need connector sessions in the prep, and the observed failure was a pull request. Each joins when a brief shows a stale claim of its kind; #353 keeps them as later lines.
- **Anti-goals:** a model deciding status from memory or doing date arithmetic; a network call from the headless brief session; ticking a Now line the brief only read (the Now check already closes lines on evidence).

## 3. Design

### 3.1 The prep annotates references

A new step at the end of `brief_prep.sh`, after `yesterday.md` and `away.md` are written, reads the prep inputs the brief copies status from (`yesterday.md`, `away.md`, `now.md`, `overdue.md`, `people.md`, `actions.md`, `projects.md`) and finds:

- a GitHub pull request or issue URL, or `owner/repo#N`;
- a bare `#N` (as in "PR #296"), resolved only when exactly one GitHub repository is known (the template's remote and the registered codebases' `github:` repositories); with none or several, it reads `unverified (ambiguous)`;
- a Work Order id (`YYYY-MM-DD-slug`).

For each, at most 20 a brief in file order, one call: `gh api repos/<o>/<r>/issues/<N>` (an issue or a pull request alike; a pull request's merge comes from its `pull_request.merged_at`) under its own `STATUS_TIMEOUT` (10 s), or the order's `state` from `nightshift.py list --json`. Times are converted to the vault's `timezone` in the prep, so the brief does no date arithmetic. The step writes the state inline after the reference, in place, in each input file: `PR #296 (merged 2026-10-21 08:16)`, `(closed 2026-10-20)`, `(open)`, `(done)`, `(unverified: <reason class>)`. A reference past the 20th is left as written. `STATUS_MAX` and `STATUS_TIMEOUT` are new rows in `conformance.bats`'s timing values, and the brief's step table gains `STATUS_MAX` × `STATUS_TIMEOUT`.

### 3.2 The brief's rule

Sections the brief copies verbatim (Overdue, Before today's meetings, Waiting on, While you were away) now carry the state as written. `brief.md` gains one rule for the text it writes itself (Where yesterday landed, Blockers): "a reference marked (merged …), (closed …) or (done) is reported in that state, never as open; one marked (unverified …) keeps the mark." The prompt is at 2,499 of its 2,500 words (`prep.bats`), so the rule replaces wording elsewhere, avoiding the strings `commands.bats` checks.

### 3.3 The Sources line

The step appends `status: N checked, M closed, K unverified` to `sources.md` after the source rows. The brief's "all ok" summary covers the source rows only; the status line is printed as it is.

## 4. Tests

- `prep.bats`: references in `yesterday.md`, `now.md` and `projects.md` resolve through a stubbed `gh api` and a stubbed `nightshift.py list --json` to inline `(merged …)`, `(closed …)`, `(open)` and `(done)` marks with local times; a `gh` failure gives `(unverified: …)`; a bare `#N` resolves with one known repository and reads `(unverified: ambiguous)` with two; the 21st reference is left as written; the status line lands in `sources.md`; the prompt is still at most 2,500 words.
- `commands.bats`: `brief.md` names the rule.
- `conformance.bats`: the brief's sum holds the status step under its limit.
- The live acceptance re-run, since `brief.md` changes.

## 5. Done when

A brief generated after a pull request merges states it as merged wherever it mentions it, including in text copied from the last debrief, and the Sources line shows the status counts.

## 6. Left to the builder

The reference-matching regex, the in-place rewrite of each input file, and the exact brief wording within the cap.
