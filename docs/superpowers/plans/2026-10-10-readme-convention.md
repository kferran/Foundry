# README Convention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every vault owns its `README.md`, and template updates never conflict on it (#90).

**Architecture:**
- The template manual moves to `FOUNDRY.md` (`git mv`, then small edits), and `README.md` becomes a short landing page with a `<!-- foundry:landing -->` marker.
- `.gitattributes` marks `README.md` `merge=ours`. `update_template.sh` defines the driver for its own merge only (`git -c merge.ours.driver=true merge`), so sync merges between machines stay normal.
- `/setup` gains step 9a, which writes the vault's README while the landing marker is there.
- Every pointer to a README section moves to `FOUNDRY.md`.

**Tech Stack:** bash, git attributes, bats 1.8.2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-10-readme-convention-design.md`

## Global Constraints

- Work on branch `feat/readme-convention`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Template rule: no machine, employer or people names.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once), outside a sandbox. The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: bats (`commands.bats`, `vault_integrity.bats`, `remote.bats`), pytest (`test_telemetry_core.py`, which reads the manual) and the gate.
- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Departures from the spec (applied here)

- **The setup prompt stays in `FOUNDRY.md`** (Getting started), and the landing page links to it. A client clones the private vault, whose README is the vault's own, so the prompt must live in a file every vault keeps. The spec's Q5 answer put it on the landing page.
- **The sync check is a plain git merge in `remote.bats`.** It confirms that without the driver, a README changed on both sides conflicts, which is what `vault_sync.sh` sees. The spec named `sync.bats`.

## Review Focus

- **A vault README changed while the template's also changed:** the vault's version survives `update_template.sh`. Test: `update_template keeps a README the vault changed…`.
- **No driver in the vault's config:** the driver exists only for the template merge, so sync merges keep both machines' edits. Tests: the same test's `git config` check, and `without the driver, a README changed on both sides still conflicts…`.
- **An unedited README takes the template's.** Test: `update_template gives an unedited README the template's new one`.
- **Every README text check moved to `FOUNDRY.md`,** and the link check covers both files. Test: `vault_integrity.bats` and the moved `commands.bats` checks.
- **`/setup` never overwrites an owned README:** step 9a runs only behind the marker. Test: the README convention test in `commands.bats`.

---

### Task 1: The vault owns its README

**Files:**
- Rename: `README.md` → `FOUNDRY.md`
- Create: `README.md`, `.gitattributes`
- Modify: `FOUNDRY.md`, `system/scripts/update_template.sh`, `.claude/commands/setup.md`, `.claude/commands/backup.md`, `system/scripts/vault_sync.sh`, `system/scripts/check_deps.sh`
- Test: `system/tests/commands.bats`, `system/tests/vault_integrity.bats`, `system/tests/remote.bats`, `system/tests/python/test_telemetry_core.py`

**Interfaces:**
- `README.md` line 1 is `<!-- foundry:landing -->` in the template, and in no vault README written by `/setup`.
- `update_template.sh` merges with `-c merge.ours.driver=true`, and sets no git config.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/commands.bats`. Find:

````text
  run git grep -nE '[C]hiefOfStaff' -- CLAUDE.md README.md .claude system
````

Replace with:

````text
  run git grep -nE '[C]hiefOfStaff' -- CLAUDE.md README.md FOUNDRY.md .claude system
````

Edit 2 in `system/tests/commands.bats`. Find:

````text
  [ "$(git grep -l gcalcli -- CLAUDE.md README.md .claude system/scripts system/systemd system/agents system/templates system/headless.settings.json | tr '\n' ' ')" = '.claude/settings.json system/headless.settings.json ' ]
````

Replace with:

````text
  [ "$(git grep -l gcalcli -- CLAUDE.md README.md FOUNDRY.md .claude system/scripts system/systemd system/agents system/templates system/headless.settings.json | tr '\n' ' ')" = '.claude/settings.json system/headless.settings.json ' ]
````

Edit 3 in `system/tests/commands.bats`. Find:

````text
  grep -qx '### Sync conflicts' README.md
  grep -qF 'git merge origin/foundry/server-pending' README.md
  grep -qF 'On the machine that pushed the pending branch, its side is already checked out: run `git merge origin/<branch>` there instead' README.md
  grep -qF -- '--no-verify' README.md
  run grep -F 'Syncing them automatically is Plan 8c' README.md
````

Replace with:

````text
  grep -qx '### Sync conflicts' FOUNDRY.md
  grep -qF 'git merge origin/foundry/server-pending' FOUNDRY.md
  grep -qF 'On the machine that pushed the pending branch, its side is already checked out: run `git merge origin/<branch>` there instead' FOUNDRY.md
  grep -qF -- '--no-verify' FOUNDRY.md
  run grep -F 'Syncing them automatically is Plan 8c' FOUNDRY.md
````

Edit 4 in `system/tests/commands.bats`. Find:

````text
  grep -qF "Briefings and debriefs from before yesterday move to \`briefings/archive/<YYYY-MM>/\`" README.md
  grep -qF 'run `system/scripts/lint_vault.sh` before updating' README.md
````

Replace with:

````text
  grep -qF "Briefings and debriefs from before yesterday move to \`briefings/archive/<YYYY-MM>/\`" FOUNDRY.md
  grep -qF 'run `system/scripts/lint_vault.sh` before updating' FOUNDRY.md
````

Edit 5 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'meetings/drop/' README.md
````

Replace with:

````text
  grep -qF 'meetings/drop/' FOUNDRY.md
````

Edit 6 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'An empty filter value (`adx_filter: {deployment.instance: ""}`) selects the rows that lack that attribute' README.md
````

Replace with:

````text
  grep -qF 'An empty filter value (`adx_filter: {deployment.instance: ""}`) selects the rows that lack that attribute' FOUNDRY.md
````

Edit 7 in `system/tests/commands.bats`. Find:

````text
  grep -qF '**The Now page.**' README.md
  grep -qF 'Never stage or edit `wiki/<p>/Now.md` either' .claude/commands/ingest.md
  grep -qF '`wiki/<partition>/Now.md` is the one note both machines write' README.md
````

Replace with:

````text
  grep -qF '**The Now page.**' FOUNDRY.md
  grep -qF 'Never stage or edit `wiki/<p>/Now.md` either' .claude/commands/ingest.md
  grep -qF '`wiki/<partition>/Now.md` is the one note both machines write' FOUNDRY.md
````

Edit 8 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'A unit the update adds is listed as `new unit available: <unit>` and left out' README.md
````

Replace with:

````text
  grep -qF 'A unit the update adds is listed as `new unit available: <unit>` and left out' FOUNDRY.md
````

Edit 9 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'replace every `<…>` first' README.md
````

Replace with:

````text
  grep -qF 'replace every `<…>` first' FOUNDRY.md
````

Edit 10 in `system/tests/commands.bats`. Find:

````text
  run grep -nE '(^|[`( ])/nightshift' "$f" CLAUDE.md README.md
  [ "$status" -eq 1 ]
  grep -qF '| `/order add\|ask\|list\|cancel\|status` |' README.md
  grep -qF '.claude/skills/order/' README.md
  for k in run_window order_workspace nightshift_window nightshift_workspace; do grep -qF "\`$k\`" README.md; done
````

Replace with:

````text
  run grep -nE '(^|[`( ])/nightshift' "$f" CLAUDE.md README.md FOUNDRY.md
  [ "$status" -eq 1 ]
  grep -qF '| `/order add\|ask\|list\|cancel\|status` |' FOUNDRY.md
  grep -qF '.claude/skills/order/' FOUNDRY.md
  for k in run_window order_workspace nightshift_window nightshift_workspace; do grep -qF "\`$k\`" FOUNDRY.md; done
````

Edit 11 in `system/tests/commands.bats`. Find:

````text
  grep -qF '`order_max_five_hour`' README.md
  grep -qF 'By default `run_window` is empty and the window is always open' README.md
````

Replace with:

````text
  grep -qF '`order_max_five_hour`' FOUNDRY.md
  grep -qF 'By default `run_window` is empty and the window is always open' FOUNDRY.md
````

Edit 12 in `system/tests/commands.bats`. Find:

````text
  grep -qF 'Run the Foreman session and your design sessions in the same permission mode' README.md
````

Replace with:

````text
  grep -qF 'Run the Foreman session and your design sessions in the same permission mode' FOUNDRY.md
````

Edit 13 in `system/tests/commands.bats`. Find:

````text
  grep -qF '**Handoffs and delivered work.**' README.md
  grep -qF 'the connector returns no change history' README.md
````

Replace with:

````text
  grep -qF '**Handoffs and delivered work.**' FOUNDRY.md
  grep -qF 'the connector returns no change history' FOUNDRY.md
````

Edit 14 in `system/tests/commands.bats`. Find:

````text
  grep -qF '`foundry-update.timer` runs it every morning at 05:30 (`update_template.sh --unattended`, #87)' README.md
  grep -qF 'aborts a conflicted merge (`git merge --abort`), leaving the vault unchanged' README.md
  grep -qF 'later updates keep it disabled' README.md
}
````

Replace with:

````text
  grep -qF '`foundry-update.timer` runs it every morning at 05:30 (`update_template.sh --unattended`, #87)' FOUNDRY.md
  grep -qF 'aborts a conflicted merge (`git merge --abort`), leaving the vault unchanged' FOUNDRY.md
  grep -qF 'later updates keep it disabled' FOUNDRY.md
}

@test "the vault owns its README: a landing page, the manual in FOUNDRY.md, merge=ours and the /setup stub (#90)" {
  [ "$(head -n 1 README.md)" = '<!-- foundry:landing -->' ]
  grep -qF '[FOUNDRY.md](FOUNDRY.md)' README.md
  grep -qF '[the manual'"'"'s Getting started](FOUNDRY.md#getting-started)' README.md
  [ "$(wc -l < README.md)" -le 40 ]
  grep -qx 'README.md merge=ours' .gitattributes
  grep -qF 'g -c merge.ours.driver=true merge --no-ff --no-edit "$ref"' system/scripts/update_template.sh
  grep -qF 'This file is its manual.' FOUNDRY.md
  grep -qF '**Your README survives updates:**' FOUNDRY.md
  grep -qF 'Your vault'"'"'s `README.md` (the template ships only its landing page)' FOUNDRY.md
  sec="$(setup_section "9a. The vault's README")"
  [[ "$sec" == *'Only when the first line of `README.md` is `<!-- foundry:landing -->`'* ]]
  [[ "$sec" == *'Write no marker line'* ]]
  grep -qF 'the setup prompt in `FOUNDRY.md`, Getting started' .claude/commands/setup.md
  grep -qF '(FOUNDRY.md: Sync conflicts)' system/scripts/vault_sync.sh .claude/commands/backup.md
  run grep -rn 'README: Sync conflicts' system/scripts .claude
  [ "$status" -eq 1 ]
}
````


Edit 1 in `system/tests/vault_integrity.bats`. Find:

````text
  grep -qF 'humanizer v3.0.0' README.md
````

Replace with:

````text
  grep -qF 'humanizer v3.0.0' FOUNDRY.md
````

Edit 2 in `system/tests/vault_integrity.bats`. Find:

````text
@test "every relative link in README.md names a tracked file or folder" {
  bad=""
  for t in $(grep -oE '\]\([^) ]+\)' README.md | sed -E 's/^\]\(//; s/\)$//; s/#.*//'); do
````

Replace with:

````text
@test "every relative link in README.md and FOUNDRY.md names a tracked file or folder" {
  bad=""
  for t in $(grep -ohE '\]\([^) ]+\)' README.md FOUNDRY.md | sed -E 's/^\]\(//; s/\)$//; s/#.*//'); do
````

Edit 3 in `system/tests/vault_integrity.bats`. Find:

````text
OWN=(CLAUDE.md README.md .gitignore .claude .githooks system wiki/Index.md ':!system/codebases')
````

Replace with:

````text
OWN=(CLAUDE.md README.md FOUNDRY.md .gitattributes .gitignore .claude .githooks system wiki/Index.md ':!system/codebases')
````


Edit 1 in `system/tests/remote.bats`. Find:

````text
  alerts | grep -qF 'new unit available: foundry-nightshift.service, foundry-nightshift.timer (install with system/scripts/install_units.sh)'
}
````

Replace with:

````text
  alerts | grep -qF 'new unit available: foundry-nightshift.service, foundry-nightshift.timer (install with system/scripts/install_units.sh)'
}

# A vault with the template's .gitattributes and README.md in its base commit (#90).
readme_setup() {
  cp "$REPO/.gitattributes" .gitattributes
  printf 'landing\n' > README.md
  template_setup
}

@test "update_template keeps a README the vault changed and leaves no merge driver in its config (#90)" {
  readme_setup
  upstream_commit README.md "new landing"
  printf 'my vault\n' > README.md
  git commit -qam "my README"
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat README.md)" = "my vault" ]
  [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
  run git config --get merge.ours.driver
  [ "$status" -eq 1 ]
}

@test "update_template gives an unedited README the template's new one (#90)" {
  readme_setup
  upstream_commit README.md "new landing"
  run "$UT"
  [ "$status" -eq 0 ]
  [ "$(cat README.md)" = "new landing" ]
}

@test "without the driver, a README changed on both sides still conflicts, as in a sync merge (#90)" {
  readme_setup
  upstream_commit README.md "theirs"
  printf 'ours\n' > README.md
  git commit -qam ours
  git fetch -q template
  run git merge --no-edit "template/$(git -C "$W" rev-parse --abbrev-ref HEAD)"
  [ "$status" -ne 0 ]
  grep -qx '<<<<<<< HEAD' README.md
  git merge --abort
}
````


Edit 1 in `system/tests/python/test_telemetry_core.py`. Find:

````text
    readme = (REPO / "README.md").read_text()
````

Replace with:

````text
    readme = (REPO / "FOUNDRY.md").read_text()
````


- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_telemetry_core.py`
Expected: FAIL, 1 failed (`FOUNDRY.md` does not exist yet).

Run: `bats system/tests/commands.bats system/tests/vault_integrity.bats system/tests/remote.bats`
Expected: FAIL, 17 `not ok` (the 12 manual checks that now read `FOUNDRY.md`, the humanizer version check, the README convention test, and the 3 `remote.bats` README tests, which need `.gitattributes`).

- [ ] **Step 3: Implement**

Run: `git mv README.md FOUNDRY.md`

Edit 1 in `FOUNDRY.md`. Find:

````text
An Obsidian + Claude Code "second brain" vault template.
````

Replace with:

````text
An Obsidian + Claude Code "second brain" vault template. This file is its manual. A vault's own `README.md` describes that vault (its machines, codebases and what runs where), and template updates never change it (see [Updating and uninstalling](#updating-and-uninstalling)).
````

Edit 2 in `FOUNDRY.md`. Find:

````text
The layout, abbreviated from spec §5. `/digest` is not in the repo: it is a user-level command that `install_hooks.sh` writes to `~/.claude/commands/digest.md`, so it works in codebase sessions too.

```
````

Replace with:

````text
The layout, abbreviated from spec §5. `/digest` is not in the repo: it is a user-level command that `install_hooks.sh` writes to `~/.claude/commands/digest.md`, so it works in codebase sessions too.

```
README.md                     your vault's own README (the template ships a landing page)
FOUNDRY.md                    this manual
.gitattributes                README.md merge=ours (template updates keep your README)
````

Edit 3 in `FOUNDRY.md`. Find:

````text
- **Tracked in your vault, never in the template.** `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Work Order queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).
````

Replace with:

````text
- **Tracked in your vault, never in the template.** Your vault's `README.md` (the template ships only its landing page), `system/codebases/*.md`, `system/telemetry/*.md`, `system/dtcc/map.yaml` and `raw/<partition>/nightshift/*.md` (Work Order queue notes): your vault's own configuration and queue, committed to your private repository so a client's changes reach the server. The template ships only the `example` files. Credentials stay outside the vault (`~/.config/foundry/`, the Azure CLI).
````

Edit 4 in `FOUNDRY.md`. Find:

````text
- **The first update with the briefing archive:** the first brief after it moves every briefing older than yesterday into `briefings/archive/`, and the next sync lints them all, so run `system/scripts/lint_vault.sh` before updating and fix what it reports.
- **Update the humanizer skill:** `.claude/skills/humanizer/` is humanizer v3.0.0, copied unchanged with its MIT license. To move to a newer version, copy the new `SKILL.md` and `LICENSE` over it by hand in the template repo, then update the version and checksum in `system/tests/vault_integrity.bats` and the version in this README. Vaults receive it through `update_template.sh`.
````

Replace with:

````text
- **Your README survives updates:** `.gitattributes` marks `README.md` `merge=ours`, and `update_template.sh` defines that driver for its own merge only (`git -c merge.ours.driver=true merge`). A README your vault has changed keeps your version; one you never edited takes the template's landing page. Sync merges between your machines define no driver, so a README edited on two machines conflicts as usual and nothing is lost. `/setup` writes a starting README while yours is still the landing page.
- **The first update with the briefing archive:** the first brief after it moves every briefing older than yesterday into `briefings/archive/`, and the next sync lints them all, so run `system/scripts/lint_vault.sh` before updating and fix what it reports.
- **Update the humanizer skill:** `.claude/skills/humanizer/` is humanizer v3.0.0, copied unchanged with its MIT license. To move to a newer version, copy the new `SKILL.md` and `LICENSE` over it by hand in the template repo, then update the version and checksum in `system/tests/vault_integrity.bats` and the version in this manual. Vaults receive it through `update_template.sh`.
````


Create `README.md`:

````text
<!-- foundry:landing -->
# The Foundry

An Obsidian + Claude Code "second brain" vault template. It runs on Linux (Arch or Debian), on one machine or as a server that syncs with laptop clients.

- **The vault compiles itself.** Files you drop in, short digests of your Claude Code sessions and your meetings become a wiki of concepts, entities and summaries, split into `work`, `personal` and `shared` partitions.
- **It runs your day.** A morning brief from your calendar, open loops, alerts and production errors; an evening debrief of what you delivered.
- **Automation stays checked.** Timed headless `claude -p` runs write to a staging area, and a deterministic gate validates and publishes their output.

## Quick start

1. Install what [the manual's Requirements](FOUNDRY.md#requirements) lists and sign in to Claude Code.
2. Create your vault from this template and start Claude Code in it:

   ```sh
   git clone <template-url> my-vault    # or "Use this template" on the hosting site
   cd my-vault
   claude
   ```

3. Paste the setup prompt from [the manual's Getting started](FOUNDRY.md#getting-started) with your answers, or type `/setup` and answer its questions.

`/setup` replaces this page with your vault's own README, which describes your machines, codebases and what runs where. Template updates keep it.

## The manual

Everything else (how it works, daily use, memory, machine roles, security and updating) is in [FOUNDRY.md](FOUNDRY.md).
````

Create `.gitattributes`:

````text
# A vault owns its README.md: update_template.sh merges with this driver defined (merge.ours.driver=true), so a
# README the vault changed keeps its version. Sync merges define no driver and merge it normally (#90).
README.md merge=ours
````

Edit 1 in `system/scripts/update_template.sh`. Find:

````text
if ! g merge --no-ff --no-edit "$ref"; then
````

Replace with:

````text
# merge.ours.driver for this merge only: .gitattributes keeps the vault's README.md (#90); sync merges stay normal.
if ! g -c merge.ours.driver=true merge --no-ff --no-edit "$ref"; then
````


Edit 1 in `.claude/commands/setup.md`. Find:

````text
You are running setup for this Foundry vault. Every phase is idempotent: show what exists and edit it, never overwrite blindly. When the user gave answers up front (the README's setup prompt), use them and ask only for what is missing; an answer still written as `<…>` is missing. Ask one question at a time, show the default, and wait for the answer. Scripts that are not allowlisted will ask the user for permission; that is intended. Run every script as `system/scripts/<name> …` from the vault root.
````

Replace with:

````text
You are running setup for this Foundry vault. Every phase is idempotent: show what exists and edit it, never overwrite blindly. When the user gave answers up front (the setup prompt in `FOUNDRY.md`, Getting started), use them and ask only for what is missing; an answer still written as `<…>` is missing. Ask one question at a time, show the default, and wait for the answer. Scripts that are not allowlisted will ask the user for permission; that is intended. Run every script as `system/scripts/<name> …` from the vault root.
````

Edit 2 in `.claude/commands/setup.md`. Find:

````text
For each registered codebase without one, create `wiki/<partition>/concepts/<Name>OnboardingAssignment.md`, where `<partition>` is the codebase's partition and `<Name>` its name in PascalCase. Frontmatter: `type: concept`, `tags: ["onboarding"]`, `compiled_at` today, `partition`, `codebase`, `capability: code`, `status: draft`. Body: ask the Workcell with `code` to map the codebase's layers and its logging and telemetry definitions (start from the `logging_hints` the inspection found) into `wiki/<partition>/entities/<Name>LogEventMap.md`; link `[[Index]]` and name each superpower the work serves. Then add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`, so the note is not an orphan (`wiki/Index.md` belongs to the template; never edit it here). Run `system/scripts/lint_vault.sh` afterwards.

````

Replace with:

````text
For each registered codebase without one, create `wiki/<partition>/concepts/<Name>OnboardingAssignment.md`, where `<partition>` is the codebase's partition and `<Name>` its name in PascalCase. Frontmatter: `type: concept`, `tags: ["onboarding"]`, `compiled_at` today, `partition`, `codebase`, `capability: code`, `status: draft`. Body: ask the Workcell with `code` to map the codebase's layers and its logging and telemetry definitions (start from the `logging_hints` the inspection found) into `wiki/<partition>/entities/<Name>LogEventMap.md`; link `[[Index]]` and name each superpower the work serves. Then add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`, so the note is not an orphan (`wiki/Index.md` belongs to the template; never edit it here). Run `system/scripts/lint_vault.sh` afterwards.

## 9a. The vault's README
Only when the first line of `README.md` is `<!-- foundry:landing -->` (the template's landing page; any other `README.md` is the user's, so leave it alone): replace it with the vault's own README and show it to the user. Write a `# ` title with the vault folder's name, then short sections from what this setup knows: the machine role and, for a server or client, that the vault syncs through a private `origin`; the timezone and brief and debrief times; the partitions and the default one; each registered codebase with its partition; the timers `systemctl --user list-timers 'foundry-*'` lists (none on a client). End with `The Foundry manual: [FOUNDRY.md](FOUNDRY.md).` Write no marker line: the README is the user's from now on, and template updates keep it.

````


Edit 1 in `.claude/commands/backup.md`. Find:

````text
3. **Run commits.** In every role and every `remote_mode`, each headless run that published files is committed first, one commit per run with a message built from the run's records. In `private`, run `system/scripts/vault_sync.sh` instead of steps 3 to 6: it runs `commit_runs.py` itself, commits the remaining changes with a scripted `sync` message, merges `origin` and pushes. Report its exit in words: 0 synced; 1 the `vault_sync:` line it printed (also in today's alerts); 3 blocked, with the reason and pending branch from `system/logs/sync-blocked`; 4 a run is in progress; try again shortly. Then list any `origin/foundry/*-pending` branch (`git branch -r --list 'origin/foundry/*-pending'`): each is a conflict waiting to be resolved (README: Sync conflicts). Go to step 7. Otherwise run `system/scripts/commit_runs.py`, which prints one line per run. If it exits 1, stop: report its `commit_runs:` line (a run's files failed the pre-commit hook; fix them, then run `/backup` again) and do not commit.
````

Replace with:

````text
3. **Run commits.** In every role and every `remote_mode`, each headless run that published files is committed first, one commit per run with a message built from the run's records. In `private`, run `system/scripts/vault_sync.sh` instead of steps 3 to 6: it runs `commit_runs.py` itself, commits the remaining changes with a scripted `sync` message, merges `origin` and pushes. Report its exit in words: 0 synced; 1 the `vault_sync:` line it printed (also in today's alerts); 3 blocked, with the reason and pending branch from `system/logs/sync-blocked`; 4 a run is in progress; try again shortly. Then list any `origin/foundry/*-pending` branch (`git branch -r --list 'origin/foundry/*-pending'`): each is a conflict waiting to be resolved (FOUNDRY.md: Sync conflicts). Go to step 7. Otherwise run `system/scripts/commit_runs.py`, which prints one line per run. If it exits 1, stop: report its `commit_runs:` line (a run's files failed the pre-commit hook; fix them, then run `/backup` again) and do not commit.
````


Edit 1 in `system/scripts/vault_sync.sh`. Find:

````text
        block "merge conflict with origin/$branch; resolve it by merging origin/$pending (README: Sync conflicts)" \
````

Replace with:

````text
        block "merge conflict with origin/$branch; resolve it by merging origin/$pending (FOUNDRY.md: Sync conflicts)" \
````


Edit 1 in `system/scripts/check_deps.sh`. Find:

````text
    herdr) echo "optional session backend for sub-project 2; see README"; return ;;
````

Replace with:

````text
    herdr) echo "optional session backend for sub-project 2; see FOUNDRY.md"; return ;;
````


- [ ] **Step 4: Run the tests and the gate**

Run: the commands from Step 2.
Expected: PASS, no failures and no `not ok`.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
feat(readme): every vault owns its README (#90)

The template manual moves to FOUNDRY.md, and README.md becomes a short
landing page with a <!-- foundry:landing --> marker. .gitattributes marks
README.md merge=ours; update_template.sh defines that driver for its own
merge only, so a vault keeps its README through template updates while
sync merges between machines stay normal. /setup step 9a writes the
vault's README while the landing marker is there. Every pointer to a
README section moves to FOUNDRY.md.
```

Run: `git add FOUNDRY.md README.md .gitattributes system/scripts/update_template.sh .claude/commands/setup.md .claude/commands/backup.md system/scripts/vault_sync.sh system/scripts/check_deps.sh system/tests/commands.bats system/tests/vault_integrity.bats system/tests/remote.bats system/tests/python/test_telemetry_core.py`

Run: `git commit -q -F .scratch/msg-1.txt`
