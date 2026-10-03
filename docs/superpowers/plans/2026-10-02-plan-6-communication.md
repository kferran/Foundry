# Plan 6: Communication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vault sessions reply in three sized tiers and follow condensed humanizer wording rules. The humanizer skill ships in the vault as `/humanizer`, and the headless `ingest`, `brief` and `debrief` runs edit their own prose against it before they finish.

**Architecture:** Prompt and documentation work only; no script changes.
- The humanizer skill (v3.0.0, MIT) is copied unchanged into `.claude/skills/humanizer/`. A checksum test keeps it unchanged.
- `CLAUDE.md` gains a Writing section: reply tiers plus 10 condensed wording rules. `run_headless.sh` already appends `CLAUDE.md` to every headless prompt, so headless runs get the rules with no runner change.
- The three headless commands gain a last self-edit step that Reads the vendored skill. Read inside the vault is already allowed under `--restricted`, so no permission changes.
- Changing those commands reopens the Plan 4a acceptance gate, so Task 4 re-runs it live.

**Tech Stack:** Markdown prompts, bats 1.14, the real `claude` binary for acceptance.

**Spec:** `docs/superpowers/specs/2026-10-02-communication-design.md` §3–§4 (Plan 6). §5 is Plan 7 and is out of scope. The runner contract is `docs/superpowers/specs/2026-09-30-vault-template-design.md` §6.3.

## Global Constraints

- **Branch** `feat/plan-6` from `master` at 412ee91 (PR #5 merged).
- **Do not change** `run_headless.sh` or `system/headless.settings.json`. The skill is read with the Read tool, which headless runs already have.
- **The vendored files are byte-identical to humanizer v3.0.0:** `SKILL.md` sha256 `e8269e236bed06ed0fe4824c274112e54950b0cb46b0bafe5e1576ef7c9f93d5`, `LICENSE` sha256 `4ac4810254ab36d45419141aeb8e69bf50652cfafe5b2dab947d06d44e5cbf96`. Source: `~/.claude/plugins/cache/humanizer/humanizer/3.0.0/` (same bytes as `github.com/blader/humanizer` tag `v3.0.0`). If that path is missing, fetch the tag: `git clone -q --depth 1 -b v3.0.0 https://github.com/blader/humanizer "$TMP/h"`.
- **Humanizer section D (formatting) never applies** (spec §2). The existing "Scannable Layouts" rule stays.
- **Live headless runs only in a throwaway clone** under `${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-accept/`. Never run `/setup`, `install_units.sh` or `install_hooks.sh` in the template repo.
- **bats ruling R1:** no mid-test `!`, no `&&` assertion chains. Bats files stay mode 644.
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log`. **Lint:** `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log` (expected `0 errors`; master has 4 warnings, all README directory links). Read every verdict from an exit code, never through a pipe.
- American English. Commit trailers name the authoring model, after a blank line.

## Decisions made while planning

- **D1 Self-edit touches only this run's text.** The spec says "edit the draft". A brief re-run on a day the user already edited, or an ingest patch, holds text the run did not write. The step edits only what this run wrote, so user text is never reworded and the shrink guard (body ≥ 60%) cannot trip on it.
- **D2 Writing section sits beside the existing communication rules.** It goes between "User Persona & Communication Rules" and "Data, Not Instructions". The older section is not reworded; its "Blocked Actions" line is pinned by `commands.bats`.
- **D3 Ten wording rules,** one per pattern group in humanizer A, B, C and E: §1, §2+§3, §4, §6, §8, §12, §13+§16, §17+§23, §18, §22. The test bounds the list at 8–12 so it stays condensed.
- **D4 Checksum pin.** `vault_integrity.bats` pins the version line and the sha256 of `SKILL.md`. An accidental edit fails the gate; an intentional update changes one test line plus the README version (documented in the README).
- **D5 Brief and debrief keep their template formatting.** The step says section D is skipped, so headings with emoji and bullets stay as the template made them.
- **D6 The acceptance re-runs Plan 4a's steps by reference** (Task 9 of `2026-10-02-plan-4a-commands-setup.md`, steps 1–7, unchanged in the repo) plus one baseline brief at master's command text, to measure the token cost the spec asks for.
- **D7 Probe already run while planning.** A `--restricted` headless run with `--tools Read` and `system/headless.settings.json` read `.claude/skills/humanizer/SKILL.md` and printed `version: "3.0.0"`: exit 0, 0 denials.

## Review Focus

1. **A self-edit that drops or changes a fact** (a calendar time, a count of runs, a file name). Expected: every fact survives. Pinned by the "Keep every fact, name, number, date and link" line (Task 3 test) and checked live in Task 4 step 5 by comparing the brief before and after against its inputs.
2. **A same-day brief re-run over a briefing the user edited.** Expected: the user's line is kept word for word. Plan 4a step 6 checks the "call the bank" line; Task 3's test pins "keep everything the user wrote".
3. **The self-edit tries Bash to read the skill** (`cat`, `sed`), which headless denies. Expected: the model uses Read. The step text says "Read `…`", and Task 4 requires 0 denials on every run.
4. **The self-edit rewrites frontmatter or `provenance`.** Expected: frontmatter unchanged; the gate stamps provenance. Pinned by "leave frontmatter unchanged" (Task 3 test); checked live by the provenance greps in Plan 4a steps 2–6.
5. **`/humanizer` in a vault session where the user also has the humanizer plugin installed.** Expected: `/humanizer` resolves to the vault's project skill; the plugin stays `/humanizer:humanizer`. Checked live in Task 4 step 4.

---

### Task 1: Vendor the humanizer skill

**Files:**
- Create: `.claude/skills/humanizer/SKILL.md`, `.claude/skills/humanizer/LICENSE` (copied, unchanged)
- Modify: `README.md` (layout, Updating, Acknowledgements)
- Test: `system/tests/vault_integrity.bats`, `system/tests/commands.bats`

**Interfaces:**
- Produces: the path `.claude/skills/humanizer/SKILL.md`, which Tasks 2 and 3 name verbatim.

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/vault_integrity.bats`:

```bash

@test "the vendored humanizer is v3.0.0, unchanged, with its MIT license" {
  d=.claude/skills/humanizer
  grep -qx '  version: "3.0.0"' "$d/SKILL.md"
  grep -qx 'name: humanizer' "$d/SKILL.md"
  [ "$(sha256sum < "$d/SKILL.md")" = 'e8269e236bed06ed0fe4824c274112e54950b0cb46b0bafe5e1576ef7c9f93d5  -' ]
  [ "$(head -n 1 "$d/LICENSE")" = 'MIT License' ]
  grep -qx 'Copyright (c) 2025 Siqi Chen' "$d/LICENSE"
  grep -qF 'humanizer v3.0.0' README.md
}
```

Append to `system/tests/commands.bats`:

```bash

@test "the humanizer skill and its license ship with the template" {
  [ "$(git ls-files .claude/skills/humanizer | tr '\n' ' ')" = '.claude/skills/humanizer/LICENSE .claude/skills/humanizer/SKILL.md ' ]
}
```

- [ ] **Step 2: Run them and watch them fail.**

```bash
bats system/tests/vault_integrity.bats > system/logs/t1.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t1.log
bats system/tests/commands.bats > system/logs/t1c.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t1c.log
```
Expected: both `exit=1`; the only failures are the two new tests (no such file / empty `ls-files`).

- [ ] **Step 3: Copy the files and verify the bytes.**

```bash
H=~/.claude/plugins/cache/humanizer/humanizer/3.0.0
mkdir -p .claude/skills/humanizer
cp "$H/SKILL.md" "$H/LICENSE" .claude/skills/humanizer/
chmod 644 .claude/skills/humanizer/*
sha256sum .claude/skills/humanizer/*
```
Expected: the two sums in Global Constraints.

- [ ] **Step 4: README.** Three edits.

In the layout block, after the `.claude/commands/` line (keep the 30-column alignment):

```
.claude/skills/humanizer/     vendored humanizer v3.0.0 (MIT): /humanizer, headless self-edit
```

In "Updating and uninstalling", a new bullet directly after "**Pull template updates:** …":

```markdown
- **Update the humanizer skill:** `.claude/skills/humanizer/` is humanizer v3.0.0, copied unchanged with its MIT license. To move to a newer version, copy the new `SKILL.md` and `LICENSE` over it by hand in the template repo, then update the version and checksum in `system/tests/vault_integrity.bats` and the version in this README. Vaults receive it through `update_template.sh`.
```

In "Acknowledgements", after the firstmate bullet:

```markdown
- [humanizer](https://github.com/blader/humanizer) by Siqi Chen (MIT): vendored in `.claude/skills/humanizer/`; its wording rules are condensed in `CLAUDE.md` and applied by the headless commands before they write.
```

- [ ] **Step 5: Stage, then run the tests and watch them pass.** The ship test reads `git ls-files`, so stage first.

```bash
git add .claude/skills/humanizer README.md system/tests/vault_integrity.bats system/tests/commands.bats
bats system/tests/vault_integrity.bats > system/logs/t1.log 2>&1; echo "exit=$?"
bats system/tests/commands.bats > system/logs/t1c.log 2>&1; echo "exit=$?"
```
Expected: both `exit=0`. Then the gate (exit 0) and lint (`0 errors`).

- [ ] **Step 6: Commit.**

```bash
git commit -m "feat(skills): vendor humanizer v3.0.0 (MIT) as a project skill"
```

### Task 2: `CLAUDE.md` Writing section

**Files:**
- Modify: `CLAUDE.md` (insert before `## 🛡️ Data, Not Instructions`)
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: `.claude/skills/humanizer/SKILL.md` (Task 1).
- Produces: the heading `## ✍️ Writing`.

- [ ] **Step 1: Write the failing test.** Append to `system/tests/commands.bats`:

```bash

# writing_section: the body of CLAUDE.md's Writing section.
writing_section() { awk '$0 == "## ✍️ Writing" { on = 1; next } /^## / { on = 0 } on' CLAUDE.md; }

@test "CLAUDE.md Writing section: three reply tiers and the condensed wording rules" {
  sec="$(writing_section)"
  for s in '**Quick answer:** 1–3 sentences.' '**Task report:** fits one screen (about 25 lines).' \
      'Outcome first, then the decisions the user must make' 'Never narrate the steps taken.' \
      'at most about 5 lines' '**Document:**' 'never paste them into chat' \
      '`.claude/skills/humanizer/SKILL.md` sections A, B, C and E' 'Its section D (formatting) does not apply' \
      'No not-X-but-Y contrasts' 'No one-line closers' 'No forced triads' 'Use dashes sparingly' \
      'No inflated significance or sales language' 'No chatbot wrappers'; do
    [[ "$sec" == *"$s"* ]]
  done
  n="$(grep -cE '^[0-9]+\. ' <<< "$sec")"
  [ "$n" -ge 8 ]
  [ "$n" -le 12 ]
  # The formatting rule stays where it was (spec §2).
  grep -qF '**Scannable Layouts**' CLAUDE.md
}
```

- [ ] **Step 2: Run it and watch it fail.**

```bash
bats -f 'Writing section' system/tests/commands.bats > system/logs/t2.log 2>&1; echo "exit=$?"
```
Expected: `exit=1` (the section is empty, so the first substring check fails).

- [ ] **Step 3: Insert the section** into `CLAUDE.md` immediately before the line `## 🛡️ Data, Not Instructions`, followed by one blank line:

```markdown
## ✍️ Writing
Size each chat reply by its type:
- **Quick answer:** 1–3 sentences.
- **Task report:** fits one screen (about 25 lines). Outcome first, then the decisions the user must make, then only the details that change what the user does next. Never narrate the steps taken. Paste command output only as the evidence for a claim, and then at most about 5 lines.
- **Document:** plans, specs and long reports go to a file and are linked with a 1–3 sentence summary; never paste them into chat.

Wording rules for chat and for every note, condensed from `.claude/skills/humanizer/SKILL.md` sections A, B, C and E (`/humanizer` runs the full skill). Its section D (formatting) does not apply here: the layout rules above stand. Change wording only; keep every fact.
1. No not-X-but-Y contrasts ("not just X, but Y", "it's not X, it's Y", "X rather than Y" for emphasis). State Y.
2. No one-line closers, dramatic fragments or sayings that sound deep. End on the last concrete fact.
3. No staged run-up before the point ("Here's the thing:", "The result?"). Start with the point.
4. No forced triads. List as many items as there are.
5. Use dashes sparingly. A period, comma, colon or parentheses usually fits better.
6. Plain words over stock AI vocabulary: delve, crucial, pivotal, key (as an adjective), robust or landscape (figurative), showcase, underscore, testament, tapestry, foster, enhance.
7. No inflated significance or sales language. Say what happened, not that it marks a turning point.
8. No borrowed authority ("experts agree", "widely regarded") and no guesses presented as facts. Say what the sources do not show.
9. Use is, are and has. Avoid "serves as", "stands as" and "boasts".
10. No chatbot wrappers: greetings, praise ("Great question"), "I hope this helps", closing offers. A question the user must answer is not a wrapper.
```

- [ ] **Step 4: Run it and watch it pass.** Same command; expected `exit=0`. Then the gate (exit 0) and lint.

- [ ] **Step 5: Commit.**

```bash
git add CLAUDE.md system/tests/commands.bats
git commit -m "feat(claude-md): Writing section with reply tiers and condensed humanizer rules"
```

### Task 3: Headless self-edit pass in `ingest`, `brief`, `debrief`

**Files:**
- Modify: `.claude/commands/ingest.md` (step 9 becomes Self-edit, Finish becomes step 10), `.claude/commands/brief.md`, `.claude/commands/debrief.md` (new last section)
- Test: `system/tests/commands.bats`

**Interfaces:**
- Consumes: `.claude/skills/humanizer/SKILL.md` (Task 1).
- Produces: changed headless command text. **This reopens the Plan 4a acceptance gate; Task 4 must pass before the branch merges.**

- [ ] **Step 1: Write the failing tests.** Append to `system/tests/commands.bats`:

```bash

# self_edit_contract <command file>: the headless self-edit pass (communication spec §4).
self_edit_contract() {
  grep -qF 'Read `.claude/skills/humanizer/SKILL.md`' "$1"
  grep -qF 'against its sections A, B, C and E (wording)' "$1"
  grep -qF 'Skip section D (formatting)' "$1"
  grep -qF 'Keep every fact, name, number, date and link' "$1"
  grep -qF 'only the text this run wrote' "$1"
}

@test "ingest self-edits its notes with humanizer before the summary" {
  f=.claude/commands/ingest.md
  self_edit_contract "$f"
  grep -qF '`_decisions.jsonl`' <(grep -F '**Self-edit.**' "$f")
  edit="$(grep -nF '**Self-edit.**' "$f" | cut -d: -f1)"
  fin="$(grep -nF '**Finish**' "$f" | cut -d: -f1)"
  last_write="$(grep -nF '**Write the notes.**' "$f" | cut -d: -f1)"
  [ -n "$edit" ]
  [ "$last_write" -lt "$edit" ]
  [ "$edit" -lt "$fin" ]
}

@test "brief and debrief end with the humanizer self-edit pass" {
  for f in .claude/commands/brief.md .claude/commands/debrief.md; do
    self_edit_contract "$f"
    [ "$(grep -E '^## ' "$f" | tail -n 1)" = '## Self-edit' ]
    grep -qF 'keep everything the user wrote' <(awk '$0 == "## Self-edit" { on = 1 } on' "$f")
  done
}
```

- [ ] **Step 2: Run them and watch them fail.**

```bash
bats -f 'self-edit' system/tests/commands.bats > system/logs/t3.log 2>&1; echo "exit=$?"; grep -c '^not ok' system/logs/t3.log
```
Expected: `exit=1`, `2` failures (the skill path is not named yet).

- [ ] **Step 3: `ingest.md`.** Replace the line beginning `9. **Finish** with a short summary` with these two lines (step 10 keeps its existing text):

```markdown
9. **Self-edit.** Read `.claude/skills/humanizer/SKILL.md` once, then edit the prose of every note you created or changed against its sections A, B, C and E (wording). Skip section D (formatting). Keep every fact, name, number, date and link, and leave frontmatter, code, paths and `_decisions.jsonl` unchanged. On a patched note, edit only the text this run wrote. Headless, edit only the staged copies under `wiki/.staging/<run_id>/`.
10. **Finish** with a short summary: one line per decision (decision, target).
```

- [ ] **Step 4: `brief.md`.** Append at the end of the file (after the Frontmatter bullet), preceded by one blank line:

```markdown
## Self-edit

Read `.claude/skills/humanizer/SKILL.md` once, then edit the briefing against its sections A, B, C and E (wording). Skip section D (formatting): keep the template's headings, emoji and bullets. Keep every fact, name, number, date and link, and leave frontmatter unchanged. Edit only the text this run wrote and keep everything the user wrote. Headless, edit only `wiki/.staging/<run_id>/briefings/<date>.md`.
```

- [ ] **Step 5: `debrief.md`.** Append at the end of the file, preceded by one blank line:

```markdown
## Self-edit

Read `.claude/skills/humanizer/SKILL.md` once, then edit the debrief against its sections A, B, C and E (wording). Skip section D (formatting): keep the template's headings, emoji and bullets. Keep every fact, name, number, date and link, and leave frontmatter unchanged. Edit only the text this run wrote and keep everything the user wrote. Headless, edit only `wiki/.staging/<run_id>/briefings/<date>.debrief.md`.
```

- [ ] **Step 6: Run them and watch them pass.** Same command; expected `exit=0`, `0`. Then the gate (exit 0, 14 PASS lines) and lint (`0 errors`). The existing `headless_contract` and `headless_allowlist` tests must still pass: the new text names no new `vault_index.py` subcommand and no `@`-import.

- [ ] **Step 7: Commit.**

```bash
git add .claude/commands/ingest.md .claude/commands/brief.md .claude/commands/debrief.md system/tests/commands.bats
git commit -m "feat(commands): headless ingest, brief and debrief self-edit with the vendored humanizer"
```

### Task 4: Live acceptance re-run (real `claude`, throwaway clone)

**Files:**
- Create: `docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md`
- Modify only if a run fails: the command file that failed

**Interfaces:**
- Consumes: Tasks 1–3 committed; the real `claude` binary on PATH.
- Produces: a PASS/FAIL row per run and the measured cost. Task 5 marks Plan 6 complete only on PASS.

About 9 headless runs plus one short interactive-mode run. Every command runs inside a throwaway clone, never the template repo.

- [ ] **Step 1: Baseline brief at master's command text** (for the cost comparison).

```bash
A="${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-accept"; R="$(git rev-parse --show-toplevel)"
rm -rf "$A" && mkdir -p "$A" && git clone -q -b master "$R" "$A/base" && cd "$A/base"
cp system/config.example.md system/config.md
system/scripts/brief_prep.sh; echo "prep exit=$?"
system/scripts/run_headless.sh brief > "$A/base-brief.out" 2>&1; echo "exit=$?"
id="$(tail -n 1 system/logs/runs-*.jsonl | jq -r .run_id)"
jq -c '{u: .usage, cost: .total_cost_usd, d: (.permission_denials|length)}' "system/logs/runs/$id/claude.json" | tee "$A/base-cost.json"
cd "$R"
```
Expected: `exit=0`, 0 denials. Record input tokens as `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.

- [ ] **Step 2: Plan 4a acceptance, steps 1–7.** Run Task 9 steps 1–7 of `docs/superpowers/plans/2026-10-02-plan-4a-commands-setup.md` exactly as written there, from the template repo on `feat/plan-6` (step 1 clones the current branch into `$A/vault`). Every Expected there must hold, and every run must show 0 denials:

```bash
for f in "$A"/vault/system/logs/runs/*/claude.json; do jq -r --arg f "$f" '"\($f): denials=\((.permission_denials // []) | length)"' "$f"; done
```

- [ ] **Step 3: Cost and self-edit evidence.** From `$A/vault`, for the step 2 brief run (the first `brief` line in the ledger):

```bash
id="$(jq -r 'select(.command=="brief") | .run_id' system/logs/runs-*.jsonl | head -n 1)"
jq -c '{u: .usage, cost: .total_cost_usd}' "system/logs/runs/$id/claude.json"
```
Expected: total input tokens above the baseline by roughly 4–8k (the skill is ~5k tokens). A delta under 3k means the skill was not read: FAIL, fix the step wording. Record both numbers and the delta.

- [ ] **Step 4: `/humanizer` resolves to the project skill.** From `$A/vault` (not restricted, so project skills load):

```bash
claude -p '/humanizer Great question! This robust update is not just a fix, but a pivotal step forward — truly a testament to the team. I hope this helps!' --no-session-persistence > "$A/humanizer.out" 2>&1; echo "exit=$?"; cat "$A/humanizer.out"
```
Expected: `exit=0`; the rewrite drops "Great question", "I hope this helps", the not-X-but-Y contrast and the dash. If the reply says `/humanizer` is unknown or ambiguous, FAIL.

- [ ] **Step 5: Facts survive the self-edit.** In `$A/vault`, open `briefings/<today>.md` and `briefings/<today>.debrief.md` and check against `system/logs/inputs/<today>/`: every Unavailable Source named in `unavailable.md` appears, the alerts count matches, and the step 6 (Plan 4a) "call the bank" line is unchanged. Count the remaining tells for the record (informational; thresholds are Plan 7):

```bash
for f in briefings/*.md wiki/*/concepts/*.md; do printf '%s dashes=%s contrasts=%s\n' "$f" "$(grep -o '[—–]' "$f" | wc -l)" "$(grep -ciE "not (just|only|merely) .*but|it's not .*, it's" "$f")"; done
```

- [ ] **Step 6: Write the record** `docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md` in the Plan 4a record's format: header (date, `claude --version`, branch, commit, clone path), a Runs table (step, command, commit, exit, published, denials, notes), a Cost section (baseline vs Plan 6 brief tokens and USD, delta), the `/humanizer` result, the tell counts, and a Verdict. If a run fails, fix the command, commit, and re-run that step and every later step; record each attempt as a row, as Plan 4a did. Stop after two fix attempts on the same step and report to the user.

- [ ] **Step 7: Commit.**

```bash
git add docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md
git commit -m "docs: Plan 6 live acceptance record"
```

### Task 5: Status

**Files:**
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (Plan 6 row status), `README.md` (Status table)
- Create: `docs/superpowers/plans/2026-10-02-plan-6-outcomes.md` (generated from the execution ledger)

- [ ] **Step 1: Roadmap.** In the Plan 6 row, replace `After Plan 3` with:

```markdown
Complete (2026-10-02): `2026-10-02-plan-6-communication.md`; acceptance `docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md`
```

And in the "Gate lifted" paragraph, append: `Plan 6 re-ran it after adding the self-edit step (docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md).`

- [ ] **Step 2: README Status table.** After the `| 4b. Memory integration, renames |` row:

```markdown
| 6. Communication | `CLAUDE.md` Writing section, vendored humanizer skill, headless self-edit pass | Complete: [plan](docs/superpowers/plans/2026-10-02-plan-6-communication.md), [acceptance](docs/superpowers/spikes/2026-10-02-plan-6-acceptance.md) |
```

- [ ] **Step 3: Outcomes doc** in the format of `2026-10-02-plan-4b-outcomes.md`: rulings, fix rounds and final-review fixes, deferred minors, final verification (gate exit code and commit), and "Next on the roadmap: Plan 8 (two machines)".

- [ ] **Step 4: Verify and commit.** Gate (exit 0), lint (`0 errors`, 4 warnings: the plan link resolves now).

```bash
git add README.md docs/superpowers/plans/2026-09-30-jarvis-roadmap.md docs/superpowers/plans/2026-10-02-plan-6-outcomes.md
git commit -m "docs: record Plan 6 rulings, acceptance and status"
```
