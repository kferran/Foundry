# Setup Consent and Briefing-Archive Minors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/setup` phase 6b asks before installing units (#59); the briefing archive keeps yesterday one more day (#57), says how to resolve an existing archived copy (#55) and has a tested failure path and midnight-safe tests (#56); the README warns before the first archive (#54).

**Architecture:** Text changes in `setup.md`, `CLAUDE.md` and `README.md`; in `brief_prep.sh` the archive compares each file's date with yesterday instead of today and extends one message. Bats tests pin each change.

**Tech Stack:** bash, bats 1.8.2, GNU `date`.

**Spec:** `docs/superpowers/specs/2026-10-08-setup-and-archive-minors-design.md`

## Global Constraints

- Work on branch `fix/setup-and-archive-minors` of `kferran/Foundry`. Commit there; do not push or open a pull request.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. Read verdicts from exit codes.
- New prose follows the Writing rules in `CLAUDE.md`. Nothing names a specific vault, organization or person.
- Run the suites as `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch bats system/tests/prep.bats system/tests/commands.bats` from the repository root (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: bats (`prep.bats`, `commands.bats`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- Yesterday's briefing and debrief stay in `briefings/`; a file from two days ago moves: the archive test.
- A read-only archive folder leaves the file in place and records one line, exit 0: the `#56` test (skipped as root).
- A test that straddles local midnight skips instead of failing: each archive test re-reads the date after the run.
- `/setup` phase 6b never installs units without a dry run and a yes: the `#59` test.

---

### Task 1: Setup consent and the archive minors

**Files:**
- Modify: `.claude/commands/setup.md`, `system/scripts/brief_prep.sh`, `CLAUDE.md`, `README.md`
- Test: `system/tests/prep.bats`, `system/tests/commands.bats`

- [ ] **Step 1: Write the failing tests**

Edit 1 in `system/tests/prep.bats`. Find:

````text
@test "brief_prep: briefings and debriefs before today move to briefings/archive/<YYYY-MM>/; a rerun changes nothing" {
  today="$(TZ=America/Denver date +%F)"
  mkdir -p briefings
  for f in 2026-09-29.md 2026-09-29.debrief.md 2026-10-01.md "$today.md" "$today.debrief.md" notes.md; do
````

Replace with:

````text
@test "brief_prep: briefings and debriefs before yesterday move to briefings/archive/<YYYY-MM>/; a rerun changes nothing" {
  today="$(TZ=America/Denver date +%F)"
  yesterday="$(date -d "$today -1 day" +%F)"
  mkdir -p briefings
  for f in 2026-09-29.md 2026-09-29.debrief.md 2026-10-01.md "$yesterday.md" "$yesterday.debrief.md" "$today.md" \
      "$today.debrief.md" notes.md; do
````

Edit 2 in `system/tests/prep.bats`. Find:

````text
  done
  run "$BP"
````

Replace with:

````text
  done
  run "$BP"
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
````

Edit 3 in `system/tests/prep.bats`. Find:

````text
  [ ! -e briefings/2026-09-29.md ]
````

Replace with:

````text
  [ ! -e briefings/2026-09-29.md ]
  [ -f "briefings/$yesterday.md" ]
  [ -f "briefings/$yesterday.debrief.md" ]
````

Edit 4 in `system/tests/prep.bats`. Find:

````text
@test "brief_prep: a busy run.lock skips archiving and is recorded" {
````

Replace with:

````text
@test "brief_prep: a busy run.lock skips archiving and is recorded" {
  today="$(TZ=America/Denver date +%F)"
````

Edit 5 in `system/tests/prep.bats`. Find:

````text
  wait
````

Replace with:

````text
  wait
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
````

Edit 6 in `system/tests/prep.bats`. Find:

````text
@test "brief_prep: a briefing whose archive copy exists stays put and is recorded" {
````

Replace with:

````text
@test "brief_prep: a briefing whose archive copy exists stays put and is recorded with what to do (#55)" {
  today="$(TZ=America/Denver date +%F)"
````

Edit 7 in `system/tests/prep.bats`. Find:

````text
  printf 'new\n' > briefings/2026-09-29.md
  run "$BP"
````

Replace with:

````text
  printf 'new\n' > briefings/2026-09-29.md
  run "$BP"
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
````

Edit 8 in `system/tests/prep.bats`. Find:

````text
  grep -qxF -- '- brief_prep: briefings: 2026-09-29.md not archived (briefings/archive/2026-09/2026-09-29.md exists)' \
    "system/logs/inputs/$(TZ=America/Denver date +%F)/unavailable.md"
````

Replace with:

````text
  grep -qxF -- '- brief_prep: briefings: 2026-09-29.md not archived (briefings/archive/2026-09/2026-09-29.md exists; merge the two copies, then delete briefings/2026-09-29.md)' \
    "system/logs/inputs/$today/unavailable.md"
}

@test "brief_prep: a briefing that cannot be moved stays put and is recorded (#56)" {
  [ "$(id -u)" -ne 0 ] || skip "root can write to a read-only folder"
  today="$(TZ=America/Denver date +%F)"
  mkdir -p briefings/archive/2026-09
  printf 'x\n' > briefings/2026-09-29.md
  chmod a-w briefings/archive/2026-09
  run "$BP"
  chmod u+w briefings/archive/2026-09
  [ "$(TZ=America/Denver date +%F)" = "$today" ] || skip "the date changed during the run"
  [ "$status" -eq 0 ]
  [ -f briefings/2026-09-29.md ]
  [ ! -e briefings/archive/2026-09/2026-09-29.md ]
  grep -qF -- '- brief_prep: briefings: 2026-09-29.md could not be archived (see ' "system/logs/inputs/$today/unavailable.md"
````


Edit 1 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'only when the summary and details leave a fact unclear' "$f"
}

````

Replace with:

````text
  grep -qF 'only when the summary and details leave a fact unclear' "$f"
}

@test "setup phase 6b dry-runs the unit installer and installs only on an explicit yes (#59)" {
  sec="$(setup_section '6b. Meetings')"
  [[ "$sec" == *'system/scripts/install_units.sh --dry-run'* ]]
  [[ "$sec" == *'install on an explicit yes'* ]]
  run grep -cF 'run `system/scripts/install_units.sh` again' .claude/commands/setup.md
  [ "$output" = "0" ]
}

@test "the archive keeps yesterday: CLAUDE.md and the README say days before yesterday (#57); the README warns before the first archive (#54)" {
  grep -qF 'Each brief moves days before yesterday to `briefings/archive/<YYYY-MM>/`.' CLAUDE.md
  grep -qF "Briefings and debriefs from before yesterday move to \`briefings/archive/<YYYY-MM>/\`" README.md
  grep -qF 'run `system/scripts/lint_vault.sh` before updating' README.md
}

````


- [ ] **Step 2: Run them to verify they fail**

Run: the suite command from Global Constraints.
Expected: FAIL, 4 `not ok`: `brief_prep: briefings and debriefs before yesterday move …` (yesterday's file was moved), `brief_prep: a briefing whose archive copy exists … (#55)` (no hint in the line), `setup phase 6b dry-runs the unit installer … (#59)` and `the archive keeps yesterday: … (#57) …`. The `#56` test and the busy-lock test pass already: they cover paths that work today.

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/brief_prep.sh`. Find:

````text
  if flock -w "${ARCHIVE_LOCK_WAIT:-60}" 9; then
````

Replace with:

````text
  if flock -w "${ARCHIVE_LOCK_WAIT:-60}" 9; then
    # Yesterday stays one more day: a client may still have it open in Obsidian (#57).
    yesterday="$(date -d "$today -1 day" +%F)"
````

Edit 2 in `system/scripts/brief_prep.sh`. Find:

````text
      [[ "${BASH_REMATCH[1]}" < "$today" ]] || continue
      dest="briefings/archive/${BASH_REMATCH[2]}/$name"
      if [[ -e "$dest" ]]; then
        prep_unavailable "briefings: $name not archived ($dest exists)"
````

Replace with:

````text
      [[ "${BASH_REMATCH[1]}" < "$yesterday" ]] || continue
      dest="briefings/archive/${BASH_REMATCH[2]}/$name"
      if [[ -e "$dest" ]]; then
        prep_unavailable "briefings: $name not archived ($dest exists; merge the two copies, then delete briefings/$name)"
````


Edit 1 in `.claude/commands/setup.md`. Find:

````text
Write `meetings_enabled` and `meetings_partition` with `system/scripts/vault_index.py set system/config.md <key> <value>` and `owner_names` by editing the file (a list of quoted names), then run `system/scripts/vault_index.py validate system/config.md`. If phase 5 installed the units, run `system/scripts/install_units.sh` again so the meetings timer follows `meetings_enabled`, and report its lines.
````

Replace with:

````text
Write `meetings_enabled` and `meetings_partition` with `system/scripts/vault_index.py set system/config.md <key> <value>` and `owner_names` by editing the file (a list of quoted names), then run `system/scripts/vault_index.py validate system/config.md`. If phase 5 installed the units, run `system/scripts/install_units.sh --dry-run` so the meetings timer follows `meetings_enabled`, show the units that would change, and install on an explicit yes (as in phase 5), then report its lines.
````


Edit 1 in `CLAUDE.md`. Find:

````text
- `briefings/`: `<date>.md` (morning briefing) and `<date>.debrief.md` (evening debrief, embedded in the briefing). Write your own notes in the briefing's 📝 Notes section. Each brief moves earlier days to `briefings/archive/<YYYY-MM>/`.
````

Replace with:

````text
- `briefings/`: `<date>.md` (morning briefing) and `<date>.debrief.md` (evening debrief, embedded in the briefing). Write your own notes in the briefing's 📝 Notes section. Each brief moves days before yesterday to `briefings/archive/<YYYY-MM>/`.
````


Edit 1 in `README.md`. Find:

````text
| `/brief [date]` | The Foreman writes `briefings/<date>.md`: calendar commitments, 3–5 objectives tied to your superpowers and handed to a capability, 🎯 Active Projects, a DTCC changes block when the watcher is set up, and a friction matrix. A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Earlier days' briefings and debriefs move to `briefings/archive/<YYYY-MM>/` |
````

Replace with:

````text
| `/brief [date]` | The Foreman writes `briefings/<date>.md`: calendar commitments, 3–5 objectives tied to your superpowers and handed to a capability, 🎯 Active Projects, a DTCC changes block when the watcher is set up, and a friction matrix. A 📝 Notes section holds your own notes for the day; `/brief` never edits it. Briefings and debriefs from before yesterday move to `briefings/archive/<YYYY-MM>/` |
````

Edit 2 in `README.md`. Find:

````text
briefings/                    today's brief and debrief; earlier days in archive/<YYYY-MM>/
````

Replace with:

````text
briefings/                    today's and yesterday's briefs and debriefs; earlier days in archive/<YYYY-MM>/
````

Edit 3 in `README.md`. Find:

````text
- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders only the units this vault installed. A unit the update adds is listed as `new unit available: <unit>` and left out; read `system/scripts/install_units.sh --dry-run`, then run `system/scripts/install_units.sh` to add it. It never runs automatically.
````

Replace with:

````text
- **Pull template updates:** `system/scripts/update_template.sh`. It refuses to run on a dirty tree, fetches the `template` remote, merges with `--no-ff`, and stops on conflicts without resolving them. Afterwards it rebuilds the index and re-renders only the units this vault installed. A unit the update adds is listed as `new unit available: <unit>` and left out; read `system/scripts/install_units.sh --dry-run`, then run `system/scripts/install_units.sh` to add it. It never runs automatically.
- **The first update with the briefing archive:** the first brief after it moves every briefing older than yesterday into `briefings/archive/`, and the next sync lints them all, so run `system/scripts/lint_vault.sh` before updating and fix what it reports.
````


- [ ] **Step 4: Run the tests to verify they pass**

Run: the suite command from Global Constraints.
Expected: PASS, no `not ok`.

- [ ] **Step 5: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 6: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(setup, brief): setup consent and briefing-archive minors

/setup phase 6b dry-runs the unit installer and installs only on an
explicit yes (#59). The briefing archive keeps yesterday one more day
(#57), says how to resolve an existing archived copy (#55), has a test
for a failed move and midnight-safe tests (#56). The README warns to
lint before the update that adds the archive (#54).

Claude-Session: https://claude.ai/code/session_01647fUGoWRjf3w7UNpdzKpF
```

Run: `git add .claude/commands/setup.md system/scripts/brief_prep.sh CLAUDE.md README.md system/tests/prep.bats system/tests/commands.bats`

Run: `git commit -q -F .scratch/msg-1.txt`
