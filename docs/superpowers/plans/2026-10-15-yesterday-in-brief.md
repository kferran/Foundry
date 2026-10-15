# Where Yesterday Landed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The morning brief opens with a link to the last debrief and three to five lines drawn from it (#179).

**Architecture:** `brief_prep.sh` writes `yesterday.md` (the newest debrief in the 7 days before the brief's date, frontmatter dropped, or a `none:` line). The template gains a `### Where yesterday landed` heading; `brief.md` says how to fill it.

**Tech Stack:** bash, bats.

**Spec:** `docs/superpowers/specs/2026-10-15-yesterday-in-brief-design.md`

## Global Constraints

- bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Brief command change: live acceptance run (real headless brief) before merge.
- Template rule: no names, hosts or user paths.

## Review Focus

1. A debrief dated the brief's own day (a re-run after the evening) is ignored (Task 1 test).
2. Two debriefs in the window, one archived: the newest wins (Task 1 test).
3. A debrief with no frontmatter: copied whole, no crash (Task 1 test, covered by the `awk` that drops only a leading `---` block).
4. An existing briefing made from the old template: the brief adds the section before Active Objectives (Task 2 text).
5. A Monday brief after a weekend: Friday's debrief is within 7 days (Task 1 test uses a 3-day gap).

---

### Task 1: `yesterday.md` in `brief_prep.sh`

**Files:** Modify `system/scripts/brief_prep.sh` (before the archive step). Test: `system/tests/prep.bats` (beside the nightshift.md test).

- [ ] **Step 1: Failing tests**

```bash
@test "brief_prep: yesterday.md copies the newest debrief of the 7 days before, frontmatter dropped (#179)" {
  mkdir -p briefings/archive/2026-09
  printf -- '---\ntype: debrief\ndate: "2026-09-26"\n---\n# Old\n' > briefings/archive/2026-09/2026-09-26.debrief.md
  printf -- '---\ntype: debrief\ndate: "2026-09-28"\n---\n# Evening Debrief: 2026-09-28\nClosed X.\n' \
    > briefings/archive/2026-09/2026-09-28.debrief.md
  printf -- '---\ntype: debrief\ndate: "2026-10-01"\n---\n# Today\n' > briefings/2026-10-01.debrief.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/yesterday.md")" = "$(printf 'debrief: [[2026-09-28.debrief]]\n\n# Evening Debrief: 2026-09-28\nClosed X.')" ]
}

@test "brief_prep: no debrief in the 7 days before writes the none line (#179)" {
  mkdir -p briefings/archive/2026-09
  printf -- '---\ntype: debrief\n---\n# Old\n' > briefings/archive/2026-09/2026-09-23.debrief.md
  run "$BP" 2026-10-01
  [ "$status" -eq 0 ]
  [ "$(cat "$IN/yesterday.md")" = 'none: no debrief found from 2026-09-24 to 2026-09-30' ]
}
```

- [ ] **Step 2: Run red** — `system/scripts/test.sh system/tests/prep.bats -f yesterday` → both FAIL (no file).

- [ ] **Step 3: Implement**, before the archive comment:

```bash
# Where yesterday landed (#179): the newest debrief of the 7 days before, archived or not, for the brief to draw from.
since="$(date -d "$PREP_DATE -7 days" +%F)" last="" last_date=""
for f in briefings/*.debrief.md briefings/archive/*/*.debrief.md; do
  d="$(basename "$f" .debrief.md)"
  [[ "$d" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ && "$d" < "$PREP_DATE" && ! "$d" < "$since" && "$d" > "$last_date" ]] || continue
  last="$f" last_date="$d"
done
if [[ -n "$last" ]]; then
  { printf 'debrief: [[%s.debrief]]\n\n' "$last_date"
    awk 'NR == 1 && /^---$/ { fm = 1; next } fm && /^---$/ { fm = 0; next } !fm' "$last"; } > "$PREP_DIR/yesterday.md"
else
  printf 'none: no debrief found from %s to %s\n' "$since" "$(date -d "$PREP_DATE -1 day" +%F)" > "$PREP_DIR/yesterday.md"
fi
```

- [ ] **Step 4: Run green** — same command, then the whole `prep.bats`.
- [ ] **Step 5: Commit** — `feat(brief): prep copies the last debrief into yesterday.md (#179)`

### Task 2: The briefing section

**Files:** `system/templates/daily-briefing.md`, `.claude/commands/brief.md`, `FOUNDRY.md`. Test: `system/tests/commands.bats` (beside the one-screen brief test).

- [ ] **Step 1: Failing test**

```bash
@test "the brief opens with where yesterday landed: the last debrief's link and lines drawn from it (#179)" {
  f=.claude/commands/brief.md
  grep -qF '`system/logs/inputs/<date>/yesterday.md`' "$f"
  grep -qF '**🌅 Morning Alignment → Where yesterday landed:**' "$f"
  grep -qF 'three to five `- ` lines drawn from the debrief' "$f"
  grep -qF '`No debrief found from <a> to <b>.`' "$f"
  run grep -n -e '^### Where yesterday landed$' -e '^### 1. Active Objectives' system/templates/daily-briefing.md
  [ "${lines[0]}" = "11:### Where yesterday landed" ]
  grep -qF 'opens with **Where yesterday landed**' FOUNDRY.md
}
```

(Adjust the line number to where the heading lands; the assertion is that it comes first.)

- [ ] **Step 2: Run red.**
- [ ] **Step 3: Write** the template heading, the `brief.md` input line and section rule (spec §2 wording), and the `FOUNDRY.md` sentence in Daily use.
- [ ] **Step 4: Run green** — `commands.bats`.
- [ ] **Step 5: Commit** — `feat(brief): the brief opens with where yesterday landed (#179)`

### Task 3: Gate, review, acceptance, PR

- [ ] `verify_setup.sh` green; fresh Opus review; live headless brief in a throwaway clone with a debrief for the day before (and one with none); PR "Closes #179".
