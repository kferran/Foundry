# Health Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `health` extension that scores about 12 factory and platform metrics from existing logs and GitHub, puts a weekly 🩺 Health scorecard in Monday's brief and a breach line on any other day, and keeps a month of history for trends.

**Architecture:** One deterministic script, `extensions/health/scripts/health.py`, with one function per metric reading the files spec §3.2 names. `score <date>` appends each metric's value, threshold and state to `system/logs/health/<YYYY-MM>.jsonl`; the brief prep writes the section file from it. No model, no connector session, no core change.

**Tech Stack:** Python (stdlib), Bash, bats, pytest, `gh`.

**Spec:** `docs/superpowers/specs/2026-10-23-health-scorecard-design.md`

## Global Constraints

- Starts after the factory's F1 is merged (grill item 5); read each source's log keys as F1 left them.
- A missing or unreadable log makes its metric `unavailable`, never zero or ok.
- Every number the brief shows comes from the prep's file; the section prompt says to print it verbatim.
- The brief prompt stays within 2,500 words (spec §6 item 1).
- Template stays generic: no vault, employer or people names; `defect:` classes as FOUNDRY.md lists them.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock assertions.
- CHANGELOG line under the merge date ending `(#PR)`.
- Gate: `system/scripts/verify_setup.sh --require-suites`, with every extension off and with every extension on.

## Review Focus

1. **Numbers are reproducible:** each metric names its files, and a fixture test pins its value.
2. **Unavailable is never ok:** a missing log never reads as a healthy zero.
3. **The brief prompt stays within its cap.**

---

### Task 1: Make room in the brief prompt

**Files:** `.claude/commands/brief.md`, `system/tests/prep.bats`.

- [ ] Cut at least 20 words of repetition from `brief.md`, keeping every rule and every sentence a test pins. If no cut keeps every rule, stop and ask the owner to raise the cap (spec §6 item 1).
- [ ] Run `prep.bats` and `commands.bats`. Commit.

### Task 2: The extension skeleton and config

**Files:** `extensions/health/extension.md`, `schemas/config.md`, `brief/section.md`, `tests/health.bats`.

- [ ] Failing tests: the manifest loads (`extensions.py check`), the config keys validate (`health_thresholds` as a map, `health_defect_gates` as class to date), the brief section prompt is at most 20 words.
- [ ] Write the manifest (brief true, alert tag `{tag: health, severity: brief}`), the schema with the spec §3.3 defaults, and the section prompt: put the data file's lines verbatim under `## 🩺 Health` before 📝 Notes on a Monday, else under Pipeline.
- [ ] Run. Commit.

### Task 3: Platform metrics

**Files:** `extensions/health/scripts/health.py`, `tests/python/test_platform.py`, fixture logs.

- [ ] Failing pytest, one per metric of spec §3.2's platform table: a passing week, a breaching week, a missing file as `unavailable`.
- [ ] Implement each metric as one function returning `(value, detail)`.
- [ ] Run. Commit.

### Task 4: Factory metrics

**Files:** `health.py`, `tests/python/test_factory.py`, a stub `gh`.

- [ ] Failing pytest: fix PRs per class and a recurrence after a gate date; first-push CI green from stubbed check runs, cached per PR in the history; review-fix commits per PR; budget and ratchet headroom from the repository's own test files; the whole half omitted without `gh` or a GitHub `template_remote`.
- [ ] Implement. Run. Commit.

### Task 5: Scoring, history and the brief prep

**Files:** `health.py` (`score`), `brief/prep.sh`, `tests/health.bats`, `tests/python/test_score.py`.

- [ ] Failing tests: `score` appends one line per metric with its state; a trend metric shows `trend` under 4 weeks of history and breaches at 1.5× the median after; the prep writes the whole scorecard on a Monday and only breach lines on a Tuesday; an all-pass Tuesday writes an empty section file.
- [ ] Implement. Run the gate with every extension off and on. Commit.

### Task 6: Documents

**Files:** `extension.md` body (what it measures, setup: turn on, tune thresholds, fill gate dates), `FOUNDRY.md` (a Health paragraph), `docs/superpowers/roadmap.md`, `CHANGELOG.md`.

- [ ] Write them. Run `commands.bats`. Commit.

### Task 7: Live acceptance (owner)

- [ ] Turn `health` on in the vault and fill `health_defect_gates` with the gates that exist.
- [ ] The first Monday brief carries the scorecard; check three metrics against a hand count by the 2026-10-21 survey's method; a breached metric shows on the next weekday's brief.
