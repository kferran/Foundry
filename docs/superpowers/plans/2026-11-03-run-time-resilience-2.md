# Run-time resilience 2 (#436 S2, S5-S8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Now.md conflict the line rules settle no longer blocks the sync, the unattended update merges only a green template commit, a notice hold lifts after 24 h, old logs go after 30 days, and a brief whose calendar rows disagree with the connector says so.

**Architecture:** S5 adds `merge()` to `vaultlib/now.py` and a `merge-driver` verb to `now.py`, wired for the one merge in `vault_sync.sh` through a temporary attributes file. S2 reads the template head's public check runs with `curl` before the unattended merge. S6 moves a day-old hold aside in `notify.sh`. S7 adds a once-a-day prune to the intake tick. S8 compares `calendar_tsv.py`'s rows with the raw `list_events` results and marks the brief through an unavailable line.

**Tech Stack:** bash, git, jq, curl, Python 3 stdlib, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-run-time-resilience-2-design.md`

## Global Constraints

- Exit codes, alert texts and log fields stay unless the spec names them. Alerts use existing tags (`scripts.bats` test 28).
- Bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions.
- Tests stub claude and curl; no test calls the real claude or the network. Tasks 5 and 9 are run by the controller (sandbox off).
- No new unit or config key. No unit file changes.
- Anti-goals: the Now merge never guesses; a line it cannot place exits 1 and blocks the sync as today, and no tick or note is lost. An unknown CI state never merges. The prune never deletes a poisoned input, a quarantined meeting, or a run folder that a recovery or commit still needs.
- Core cap: one raise for the spec, 230 lines on the cap S5's PR finds (15,850 → 16,080), with one comment line in `system/tests/vault_integrity.bats` naming all five findings. Going past it is the owner's call.
- One PR per finding, in the order S5, S2, S6, S7, S8, failing test first; the owner merges each (safety surfaces: sync, update, notify's hold, the connector checker).
- Each PR's first commit marks its finding in progress on the roadmap's #436 entries (S5's first commit adds S2 and S5-S8 and the spec's merge, #475), and its last commit marks it done.
- Release notes, one `- Changed: … (#N)` line each: `changes/2026-11-03-now-merge.md`, `-update-ci-gate.md`, `-notify-hold-lift.md`, `-log-prune.md`, `-calendar-check.md` (each PR's own date).
- §9 decisions (owner, as recommended): Q-A no config key, a hand-run update stays ungated and is the way out; Q-B a hold written within 7 days of a lift stays until deleted by hand; Q-C the driver settles the server's merge only, and a client conflict is merged in Obsidian.

## Review Focus

1. Now.md added on both sides with no common version (git passes an empty `%O`): two pages from the same template merge their lines (Task 1 `test_merge_empty_base`).
2. A one-sided layout change, such as `_insert` adding a missing `## Waiting` heading on the server while the client ticks: the changed side's layout wins and the tick is kept (Task 1 `test_merge_layout_from_one_side`).
3. A line typed with trailing spaces in Obsidian still pairs with its base line by key (Task 1 `test_merge_tick_against_close`, its last case).
4. A check-runs answer whose `total_count` is larger than the list (over 100 runs, or a paged answer) reads `no runs` and never merges (Task 4, the `paged` stub case).
5. A prune pass that raises part way writes no `.pruned` date, so the next tick tries again (Task 8 `test_prune_once_a_day_and_lock_busy`, its last case).

---

## PR 1: S5, the Now.md merge driver (branch `feat/now-merge`)

### Task 1: `merge()` settles a Now page line by line

**Files:**
- Modify: `system/scripts/vaultlib/now.py` (after `_block_end`)
- Modify: `docs/superpowers/roadmap.md` (the Now list's **#436's other findings** bullet; the **Run-time resilience** row's status cell)
- Test: `system/tests/python/test_now.py`

**Interfaces:**
- Produces: `now.merge(base: str, ours: str, theirs: str) -> str`, the merged page; `ValueError(<one-line reason>)` when it cannot place something. It reads no file and takes no lock.

The rules are spec §3's, with these builder's choices (each one a ledger `Ruling:`):
- A version is a list of layout lines and blocks (a `- [` line and its notes, `_block_end`). A block's section is the last `## ` line above it.
- Layout three-way, as a whole sequence. The side whose layout wins is the skeleton: its lines and its block order are the result's. The other side's added blocks go after their predecessor on that side, or first in their section; a section the skeleton lacks exits 1.
- A paired block whose section differs between ours and theirs exits 1 (the spec is silent on moves).
- The suffix comes from a side whose mark is the merged mark, ours first; when neither has one, none (the next `stamp()` adds `ticked <date>`). This is spec §3's "closing side's suffix, or ours" read for the case where the two marks differ.
- A merged block that equals one version's block keeps that version's raw line (trailing space included).
- Deletion: "only closed" means text and notes unchanged and the mark closed (`[xX-]`), and the deleting side added no line in that section (an archive adds none). A reopen against a deletion exits 1.
- Rewrite pairing (final review): only an open base line pairs with a candidate, the candidate matches kind, since, who, evidence and section, a candidate two base lines claim pairs with neither, and a line with no evidence rewritten on one side and ticked or noted on the other exits 1.
- The sync's merge sets `merge.now.recursive=binary`, so the inner merge of a criss-cross never runs the driver and a refusal there cannot leave a silent virtual base.

- [ ] **Step 1: Write the failing tests**

```python
HEAD = '---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-01"\npartition: work\n---\n# Now\n\n## Needs you\n'
A = "- [ ] owed: Review the export PR [due:: 2026-10-12] (Blake, since 2026-10-09, https://github.com/acme/shop/pull/7)"
A2 = A.replace("the export PR", "the export PR and its docs")
B = "- [ ] owed: Send the invoice [due:: 2026-11-08] (since 2026-10-09)"


def pg(*needs, waiting=()):
    return HEAD + "".join(f"{x}\n" for x in needs) + "\n## Waiting\n" + "".join(f"{x}\n" for x in waiting)


def tick(line, mark="x", how=""):
    return f"- [{mark}]{line[5:]}" + (f" _(closed: {how})_" if how else "")


def test_merge_tick_against_close():
    base, server, client = pg(A, B), pg(tick(A, how="PR merged 2026-10-10"), B), pg(tick(A), B)
    assert now.merge(base, server, client) == server
    assert now.merge(base, client, server) == server
    assert now.merge(base, pg(tick(A, "-", "expired 2026-10-16"), B), client) == client   # [x] beats [-]
    assert now.merge(base, server, pg(tick(A) + "  ", B)) == server   # trailing space pairs by key


def test_merge_rewrite_and_tick():
    base, server = pg(A, B), pg(A2, B)
    client = pg(tick(A), "  - 2026-10-10: asked about the docs", B)
    want = pg(tick(A2), "  - 2026-10-10: asked about the docs", B)
    assert now.merge(base, server, client) == want
    assert now.merge(base, client, server) == want


C = "- [ ] draft: Reply to the vendor [due:: 2026-10-12] (vendor, since 2026-10-09)"
W = "- [ ] waiting: Access to the logs [due:: 2026-10-12] (Sam, since 2026-10-09, EX-12)"


def test_merge_adds_on_both_sides():
    assert now.merge(pg(A), pg(A, B), pg(A, C, waiting=(W,))) == pg(A, C, B, waiting=(W,))
    assert now.merge(pg(A), pg(A, B), pg(A, B)) == pg(A, B)


def test_merge_archived_against_ticked():
    base, server, client = pg(A, B), pg(B), pg(tick(A), B)
    assert now.merge(base, server, client) == server
    assert now.merge(base, client, server) == server
    assert now.merge(pg(tick(A, how="ticked 2026-10-10"), B), server, pg(tick(A, how="ticked 2026-10-10"), B)) == server


def test_merge_empty_base():
    assert now.merge("", pg(A), pg(B)) == pg(B, A)   # theirs' new line goes first in its section


def test_merge_layout_from_one_side():
    no_waiting = HEAD + f"{A}\n"   # the server's add writes the missing heading
    assert now.merge(no_waiting, pg(A, waiting=(W,)), HEAD + f"{tick(A)}\n") == pg(tick(A), waiting=(W,))


TWO = ("- [ ] owed: Review the first part (Blake, since 2026-10-09)", "- [ ] owed: Review the second part (Blake, since 2026-10-09)")


@pytest.mark.parametrize("base, ours, theirs, reason", [
    (pg(A), pg(A2), pg(A.replace("PR", "pull request")), "both sides"),                         # two rewrites
    (pg(A), pg(B), pg(A, "  - 2026-10-10: a note"), "gone on one side"),                          # gone vs a note
    (pg(A), pg(B), pg(A.replace("PR", "pull request")), "gone on one side"),                       # gone vs a rewrite
    (pg(A), pg(*TWO), pg(tick(A)), "gone on one side"),                                            # two candidates
    (pg(tick(A, how="ticked 2026-10-10")), pg(), pg(A), "gone on one side"),                       # gone vs reopened
    (pg(A), pg(A, B), pg(B, waiting=(A,)), "section"),                                             # a moved line
    (pg(A), pg(A, A), pg(A, B), "twice"),                                                          # a key twice
    (pg(A), pg(A, "  - 2026-10-10: n", "  - 2026-10-10: n"), pg(A, B), "twice"),                   # a note twice
    ("<<<<<<< ours\n" + pg(A), pg(A, B), pg(A), "conflict marker"),                                # criss-cross base
    (pg(A), pg(A).replace("# Now", "# Now page"), pg(A).replace("# Now", "# Open loops"), "layout"),
    (pg(A), pg(A).replace("\n## Waiting\n", "\n"), pg(A, waiting=(W,)), "section"),             # no section for it
])
def test_merge_blocks(base, ours, theirs, reason):
    with pytest.raises(ValueError, match=reason):
        now.merge(base, ours, theirs)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest system/tests/python/test_now.py -k merge -q`
Expected: every test FAILS with `AttributeError: module 'vaultlib.now' has no attribute 'merge'`.

- [ ] **Step 3: Implement `merge(base: str, ours: str, theirs: str) -> str`** with the rules above. Refusal reasons start with the fact: `the line "<statement, 60 characters>" was changed on both sides`, `… is gone on one side and changed on the other`, `… is in a different section on each side`, `the line "…" is twice in one version`, `a note is twice under "…"`, `a conflict marker in one version`, `the page layout changed on both sides`, `no "<heading>" section to place "…"`. The roadmap edits go in this commit: the **#436's other findings** bullet adds "Spec merged (#475); S5 in progress (#479)"; the **Run-time resilience** status cell adds "S1 review minors fixed (#473). The S2, S5-S8 spec merged (#475)".

- [ ] **Step 4: Run them to verify they pass.** Run: `python3 -m pytest system/tests/python/test_now.py -q`. Expected: all pass.

- [ ] **Step 5: Commit:** `feat(now): merge() settles a Now page line by line (#436 S5)`

### Task 2: The sync merges Now.md through the driver

**Files:**
- Modify: `system/scripts/now.py` (a `merge-driver` verb before `intake = Intake(VAULT)`; the docstring and its exit list)
- Modify: `system/scripts/vault_sync.sh:137-146`
- Modify: `FOUNDRY.md:279` (the stale Now.md paragraph under Sync conflicts)
- Modify: `system/tests/vault_integrity.bats` (`CORE_CAP` 15850 → 16080 and one measured comment line)
- Create: `changes/2026-11-03-now-merge.md`
- Test: `system/tests/sync.bats`, `system/tests/python/test_now.py`

**Interfaces:**
- Consumes: `now.merge` (Task 1).
- Produces: `now.py merge-driver <base> <ours> <theirs>`: reads the three files as UTF-8, writes the result to `<ours>` and exits 0; on any failure prints one line `now merge: <reason>` to stderr, leaves `<ours>` as it was and exits 1. No lock, no Intake.
- `vault_sync.sh`: `attrs="$(mktemp)"`, removed by an EXIT trap, holds `wiki/*/Now.md merge=now`; the merge runs as `git -c core.attributesFile="$attrs" -c merge.now.driver="'<VAULT_ROOT>/system/scripts/now.py' merge-driver %O %A %B" merge …` (the path single-quoted for `sh`). On a block, the marker's detail adds the `now merge: …` line from `$err`.

- [ ] **Step 1: Write the failing tests**

sync.bats, with a helper `now_page <repo> <line…>` that writes `wiki/work/Now.md` from `system/templates/now.md` (the template's frontmatter with a fixed date) and the lines under `## Needs you`, and `now_base <line…>` that commits it on the server, pushes and pulls it into the client:

```bash
@test "a settled Now.md conflict does not block (#436 S5)" {
  now_base "$NA" "$NB"
  now_page "$C" "${NA/- \[ \]/- [x]}" "$NB"
  git -C "$C" commit -q -am tick
  git -C "$C" push -q
  now_page "$V" "${NA/- \[ \]/- [x]} _(closed: PR merged 2026-10-10)_" "$NB"
  run "$VS"
  [ "$status" -eq 0 ]
  [ ! -e system/logs/sync-blocked ]
  [ "$(grep -c '^- \[x\] owed: Review the export PR .* _(closed: PR merged 2026-10-10)_$' wiki/work/Now.md)" -eq 1 ]
  [ "$(git -C "$O" rev-parse "$B")" = "$(git rev-parse HEAD)" ]
}

@test "a refused Now.md merge blocks with its reason (#436 S5)" {
  now_base "$NA"
  now_page "$C" "${NA/export PR/export pull request}"
  git -C "$C" commit -q -am client
  git -C "$C" push -q
  now_page "$V" "${NA/export PR/export PR and its docs}"
  run "$VS"
  [ "$status" -eq 3 ]
  grep -qx 'wiki/work/Now.md' system/logs/sync-blocked
  grep -q '^now merge: the line .* was changed on both sides' system/logs/sync-blocked
}

@test "another file's conflict still blocks when Now.md settles (#436 S5)" {
  now_base "$NA"
  now_page "$C" "${NA/- \[ \]/- [x]}"
  git -C "$C" commit -q -am tick
  diverge_on_kafka   # commits and pushes the client's Kafka line
  now_page "$V" "${NA/- \[ \]/- [x]} _(closed: PR merged 2026-10-10)_"
  run "$VS"
  [ "$status" -eq 3 ]
  grep -qx 'wiki/work/concepts/Kafka.md' system/logs/sync-blocked
  run grep -c 'Now.md' system/logs/sync-blocked
  [ "$output" = 0 ]
  [ ! -e .git/MERGE_HEAD ]
}

@test "a hand merge has no driver, and the sync leaves no attributes file (#436 S5)" {
  export TMPDIR="$BATS_TEST_TMPDIR/tmp"
  mkdir -p "$TMPDIR"
  run "$VS"
  [ "$status" -eq 0 ]
  [ -z "$(ls -A "$TMPDIR")" ]
  run git config --get merge.now.driver
  [ "$status" -eq 1 ]
  now_base "$NA"
  now_page "$C" "${NA/- \[ \]/- [x]}"
  git -C "$C" commit -q -am tick
  git -C "$C" push -q
  now_page "$V" "${NA/- \[ \]/- [x]} _(closed: PR merged 2026-10-10)_"
  git commit -q --no-verify -am close
  git fetch -q origin
  run git merge --no-edit "origin/$B"
  [ "$status" -eq 1 ]
  grep -q '^<<<<<<< ' wiki/work/Now.md
}
```

test_now.py:

```python
def test_merge_driver_writes_ours_or_exits_1(vault, tmp_path):
    base, ours, theirs = (tmp_path / n for n in ("o", "a", "b"))
    base.write_text(pg(A, B)), ours.write_text(pg(tick(A, how="PR merged 2026-10-10"), B)), theirs.write_text(pg(tick(A), B))
    r = cli(vault, "merge-driver", str(base), str(ours), str(theirs))
    assert (r.returncode, ours.read_text()) == (0, pg(tick(A, how="PR merged 2026-10-10"), B))
    theirs.write_bytes(b"\xff\xfe")
    r = cli(vault, "merge-driver", str(base), str(ours), str(theirs))
    assert r.returncode == 1 and r.stderr.startswith("now merge: ") and len(r.stderr.splitlines()) == 1
    assert ours.read_text() == pg(tick(A, how="PR merged 2026-10-10"), B)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `bats -f "#436 S5" system/tests/sync.bats` and `python3 -m pytest system/tests/python/test_now.py -k merge_driver -q`
Expected: the settled test exits 3 (textual conflict); the refused test finds no `now merge:` line; the driver test exits 2 (`invalid choice: 'merge-driver'`). The other two may pass already (they pin today's behaviour).

- [ ] **Step 3: Implement** the driver and the wiring. FOUNDRY.md:279 becomes the line rules: the server's sync merges `wiki/<partition>/Now.md` line by line (a tick on either side wins, lines added on either side are kept, a line rewritten on one side and ticked on the other keeps the new text with the tick, a closed line the other side archived goes); a line it cannot place (rewritten on both sides, changed on one side and gone on the other) blocks the sync as above, and the marker says why; a conflict met by the client's Obsidian Git merge is merged by hand in Obsidian. Change line: `- Changed: the server's sync merges a Now page changed on both machines line by line, so a tick on the laptop next to a line the server closed, rewrote or archived no longer blocks intake, the brief and the debrief; a line it cannot place still blocks, with the reason in the marker. (#479)`. Measure core with `bats -f "core stays" system/tests/vault_integrity.bats` after `git add`; the comment line: `# 15,850 -> 16,080 (#436 S2, S5-S8, owner to approve at merge): the Now.md merge driver (S5), the update's CI gate (S2), the notice hold's lift (S6), the 30-day prune (S7) and the calendar check (S8); S5 took core from <before> to <after>.`

- [ ] **Step 4: Run the suites.** Run: `bats system/tests/sync.bats system/tests/vault_integrity.bats` and `python3 -m pytest system/tests/python/test_now.py -q`. Expected: all pass; `git status --porcelain` shows only this task's edits.

- [ ] **Step 5: Commit:** `feat(sync): merge Now.md line by line through now.py's driver (#436 S5)`. The PR's last commit (after review) marks S5 done on the roadmap.

---

## PR 2: S2, the update merges only a green template commit (branch `feat/update-ci-gate`)

### Task 3: `git_github_slug` in lib_git.sh

**Files:**
- Modify: `system/scripts/lib_git.sh` (new function), `system/scripts/lib_prep.sh:62` (uses it), `docs/superpowers/roadmap.md` (S2 in progress)
- Test: `system/tests/lib.bats`

**Interfaces:**
- Produces: `git_github_slug <url>` prints `<owner>/<repo>` (no `.git`) for `https://github.com/o/r(.git)`, `git@github.com:o/r(.git)` and `ssh://git@github.com/o/r`, and nothing (status 0) for any other host.

- [ ] **Step 1: Write the failing test** `@test "git_github_slug reads https and ssh forms (#436 S2)"`: the three forms print `o/r`; `https://gitlab.com/o/r.git` and a local path print "".
- [ ] **Step 2: Run** `bats -f git_github_slug system/tests/lib.bats`. Expected: FAIL, status 127.
- [ ] **Step 3: Implement** with the sed from `lib_prep.sh:62`; `github_repos` calls it.
- [ ] **Step 4: Run** `bats system/tests/lib.bats system/tests/prep.bats`. Expected: pass (compare prep.bats calendar failures with master).
- [ ] **Step 5: Commit:** `refactor(git): git_github_slug for the prep and the update (#436 S2)`

### Task 4: The unattended update checks the template head's CI

**Files:**
- Modify: `system/scripts/update_template.sh` (after :92-95, before :99; the `template updated:` alert at :186; a hand run prints the state)
- Modify: `system/scripts/check_deps.sh:26` (`curl` for standalone and server), `system/tests/conformance.bats` (`update.checks system/scripts/update_template.sh \{UPDATE_CHECKS_TIMEOUT:-([0-9]+)\}` and the step `update 1 - update.checks`)
- Modify: `FOUNDRY.md` Updating (the gate, a non-GitHub template merges as today, the hand run is ungated and the way out for a template that never goes green, `git revert -m 1 <sha>` and that reverted commits stay out of later updates until the revert is reverted)
- Create: `changes/<date>-update-ci-gate.md`
- Test: `system/tests/remote.bats`, `system/tests/deps.bats` if it lists the required tools

**Interfaces:**
- Produces: `ci_state <owner/repo> <sha>` in `update_template.sh`, printing one of `green`, `pending`, `failing: <check names, comma-separated>`, `no runs`, `unreachable`. It runs `curl -fsS --connect-timeout 10 --max-time ${UPDATE_CHECKS_TIMEOUT:-20} "https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs?per_page=100"` and decides with one `jq` over `.total_count` and `.check_runs[] | {name, status, conclusion}` by spec §4's rules.
- The slug comes from `git config --get remote.template.url` through `git_github_slug` (Task 3); an empty slug skips the check.

- [ ] **Step 1: Write the failing tests** (remote.bats; a PATH `curl` stub that logs its argv to `$BATS_TEST_TMPDIR/curl.args` and prints the JSON named by `CURL_CASE` or exits 22 for `down`; the template remote's URL is `https://github.com/acme/tpl.git`, served from the local template through `url.<local>.insteadOf`):
  - "a green head merges and names its revert (#436 S2)": `CURL_CASE=green` (one `success`, one `skipped`); exit 0; the alert matches `template updated: .*; merge [0-9a-f]{12} \(undo: git revert -m 1 [0-9a-f]{12}\)`; the curl argv holds `repos/acme/tpl/commits/<template head sha>/check-runs?per_page=100`.
  - "each other state skips with one alert, exit 0 (#436 S2)": for `pending`, `failing` (a `failure` named `test`), `none` (no runs), `skipped-only`, `paged` (`total_count` 101 with one run listed), `garbage` (not JSON) and `down`: exit 0, HEAD unchanged, and exactly one new alert line `template update skipped: CI for acme/tpl@<sha12> is <state>; the vault is unchanged; the next run tries again`, with `<state>` = `pending`, `failing: test`, `no runs`, `no runs`, `no runs`, `unreachable`, `unreachable`.
  - "no curl call off GitHub or with nothing new (#436 S2)": a template URL off github.com merges with no `curl.args`; a second run with nothing new writes no `curl.args`.
  - "a hand run merges whatever the state and prints it (#436 S2)": `CURL_CASE=failing`, no `--unattended`: exit 0, merged, stdout holds `CI for acme/tpl@`.
- [ ] **Step 2: Run** `bats -f "#436 S2" system/tests/remote.bats`. Expected: FAIL (no curl call, no skip alert).
- [ ] **Step 3: Implement** `ci_state` and the gate; `curl` joins `REQUIRED` for standalone and server with its pacman and apt hint.
- [ ] **Step 4: Run** `bats system/tests/remote.bats system/tests/conformance.bats system/tests/deps.bats`. Expected: pass.
- [ ] **Step 5: Commit:** `feat(update): merge only a template commit whose check runs passed (#436 S2)`

### Task 5: Live check against api.github.com (run by the controller, sandbox off)

- [ ] **Step 1:** In a `.scratch/` vault with the real public template as `template`, run `system/scripts/update_template.sh --unattended`: the green head merges and the alert names its revert.
- [ ] **Step 2:** Point `insteadOf` at a local clone whose head is a real template commit with a failed run and one with no runs: each skips with the alert. Record the three outcomes in the PR body.

---

## PR 3: S6, a notice hold lifts after 24 h (branch `feat/notify-hold-lift`)

### Task 6: The hold lifts after 24 h, once within 7 days

**Files:**
- Modify: `system/scripts/notify.sh:9` (header) and `:39-40`; `FOUNDRY.md` Slack notices ("until you … delete the hold file"); `docs/superpowers/roadmap.md`
- Create: `changes/<date>-notify-hold-lift.md`
- Test: `system/tests/notify.bats`

**Interfaces:**
- Before `:40`: when `find "$hold" -mmin +1440` prints it and `hold.lifted` is absent or older than 7 days (`find … -mtime +6`, by mtime), `mv -f "$hold" "$hold.lifted"`, `touch "$hold.lifted"`, `alert_once "Notices hold lifted after 24 h:" "<the hold's first line>; a session that breaks its rules holds them again"` (tag `notify`), then go on. A hold younger than 24 h, or one written within 7 days of a lift, exits 5; the second's reason adds `; it lifted once this week, so delete it by hand`.

- [ ] **Step 1: Write the failing tests:** "a hold older than 24 h lifts with one alert and the tick posts (#436 S6)" (`touch -d '25 hours ago'` on the hold; exit 0; the post ran; `hold.lifted` exists; one `[notify] Notices hold lifted after 24 h:` line); "a younger hold still exits 5 (#436 S6)" (`touch -d '23 hours ago'`); "a rule break after a lift holds again, and that hold stays (#436 S6)" (after the lift a breaking session writes a new hold; with the hold at 25 hours old and `hold.lifted` at 2 days old, the tick exits 5 and names the hand delete).
- [ ] **Step 2: Run** `bats -f "#436 S6" system/tests/notify.bats`. Expected: the lift tests exit 5.
- [ ] **Step 3: Implement** (about 6 lines). Change line: `- Changed: a Slack notice hold lifts itself after 24 h with an alert in the brief; a second hold within 7 days stays until you delete it. (#N)`
- [ ] **Step 4: Run** `bats system/tests/notify.bats`. Expected: pass.
- [ ] **Step 5: Commit:** `fix(notify): a notice hold lifts after 24 h, once a week (#436 S6)`

---

## PR 4: S7, one prune a day (branch `feat/log-prune`)

### Task 7: `prune()` removes what has aged 30 days and is settled

**Files:**
- Create: `system/scripts/vaultlib/prune.py`
- Modify: `docs/superpowers/roadmap.md`
- Test: `system/tests/python/test_intake.py`

**Interfaces:**
- Produces: `prune.prune(vault: Path, cutoff: date) -> dict` with `runs`, `inputs`, `quarantine`, `entries` (counts removed), `unsettled` (count) and `oldest` (the oldest unsettled run id, or ""). The caller holds run.lock. It removes:
  - `system/logs/runs/<run_id>/` dated before the cutoff (the id's date; a name that is no run id stays) when the publish journal (`publish.py:484`) is absent or `_committed` and one of: a `committed` marker, a `publish.json` whose `published` is empty, no `publish.json`, or an id before `commit_runs.since`;
  - `system/logs/inputs/<YYYY-MM-DD>/` before the cutoff;
  - the paths of `quarantine.items(vault, today)` rows of kind `run` or `telemetry_state` with `days >= 30`;
  - `extracted_blocks.jsonl` entries whose `briefings/<date>.md` is dated before the cutoff, is absent, and has `briefings/archive/<YYYY-MM>/<date>.md`; rewritten through a temp file and `os.replace`.

- [ ] **Step 1: Write the failing tests:** `test_prune_runs_settled_only` (an old committed run goes; an old run with a pending journal, one with `publish.json` naming a file and no marker after `commit_runs.since`, a young run and a folder named `notes` stay; `unsettled == 2`, `oldest` the older id), `test_prune_inputs_and_safe_quarantine_only` (an old inputs folder goes, a young one stays; a 31-day `run` staging folder and a `telemetry_state-*` file go; a 40-day poisoned input and a quarantined meeting stay), `test_prune_entries_of_archived_briefings_only` (entries for an archived old briefing go; entries for an old briefing still in `briefings/`, for a young archived one and for a briefing in neither place stay), `test_restored_briefing_drops_a_duplicate` (prune an archived briefing's entries, copy the briefing back to `briefings/`, run extraction: its blocks are archived as duplicates through `manifest_has` and no digest or session starts).
- [ ] **Step 2: Run** `python3 -m pytest system/tests/python/test_intake.py -k prune -q`. Expected: FAIL, no module `vaultlib.prune`.
- [ ] **Step 3: Implement** `prune.py`.
- [ ] **Step 4: Run** the same. Expected: pass.
- [ ] **Step 5: Commit:** `feat(intake): prune runs, inputs, safe quarantine and archived extraction records after 30 days (#436 S7)`

### Task 8: The intake tick prunes once a day

**Files:**
- Modify: `system/scripts/vaultlib/intake.py:861-866` (`Intake.prune()`, called after `extract_briefing` in its own `try`); `FOUNDRY.md` Repository layout (one sentence)
- Create: `changes/<date>-log-prune.md`
- Test: `system/tests/python/test_intake.py`

**Interfaces:**
- Consumes: `prune.prune` (Task 7).
- Produces: `Intake.prune(self) -> None`: returns when `system/logs/.pruned` holds `self.today()`; takes `self.lock("run.lock", timeout=0)` (busy: returns); calls `prune.prune(self.vault, <today - 30 days>)`; writes today to `.pruned` after the pass; with `unsettled`, alerts once a day `<n> run folder(s) older than 30 days are not settled (oldest <id>); they stay` (key `run folder(s) older than 30 days`). `run()` catches its exception: `prune failed (<Type>: <msg>); will retry`.

- [ ] **Step 1: Write the failing test** `test_prune_once_a_day_and_lock_busy`: two `run()`s prune once (a folder aged after the first stays); with run.lock held the tick writes no `.pruned`; a `prune.prune` monkeypatched to raise alerts `prune failed (` once and writes no `.pruned`.
- [ ] **Step 2: Run** `python3 -m pytest system/tests/python/test_intake.py -k once_a_day -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Change line: `- Changed: the intake tick deletes run folders, prep inputs, safe quarantine and archived briefings' extraction records once they are 30 days old; poisoned inputs and quarantined meetings stay. (#N)`
- [ ] **Step 4: Run** `python3 -m pytest system/tests/python/test_intake.py system/tests/python/test_intake_digests.py -q`. Expected: pass.
- [ ] **Step 5: Commit:** `feat(intake): the tick prunes once a day under run.lock (#436 S7)`

---

## PR 5: S8, the calendar rows checked against the raw results (branch `feat/calendar-check`)

### Task 9: Capture a real list_events page (run by the controller, sandbox off, owner's approval)

**Files:**
- Create: `docs/superpowers/spikes/<date>-list-events-page.md`, `system/tests/fixtures/calendar/list_events_page.jsonl` (scrubbed)

- [ ] **Step 1:** In a `.scratch/` vault, run `calendar_fetch.sh` with real claude and keep the stream. Record whether the page reads through `structured` or `text_json`, the event list's key and each event's start (timed and all-day) and title fields.
- [ ] **Step 2:** Scrub titles, ids, attendees and links; keep the shape. Commit: `docs(spike): the shape of a list_events page (#436 S8)`

### Task 10: `verify()` compares the rows with the raw events

**Files:**
- Modify: `system/scripts/calendar_tsv.py` (after `rows` at :123; the summary gains `unverified`), `docs/superpowers/roadmap.md`
- Test: `system/tests/python/test_calendar_tsv.py`

**Interfaces:**
- Consumes: Task 9's field names; `connector.structured` / `connector.text_json`.
- Produces: `verify(results: list, table: list, tz: str) -> str`: "" when the sorted (start date, start time, title) triples of the raw events equal the table's; else `the connector listed N events, the rows hold M`, `row K (<date> <time>) differs from the connector's results`, or `the connector's results could not be read`. A timed start converts to `tz`; an all-day start keeps its date with time ""; a title gets `rows()`' cleaning. `main` sets `summary["unverified"]` and prints `calendar_tsv: unverified: <reason>` on stderr; the exit stays 0.

- [ ] **Step 1: Write the failing tests:** `test_matching_rows_verified`, `test_count_mismatch`, `test_changed_row_named_without_text` (the reason holds no title text), `test_all_day_and_offset_times` (a `Z` start and a `-04:00` start convert to the run's TZ), `test_unreadable_pages_unverified`.
- [ ] **Step 2: Run** `python3 -m pytest system/tests/python/test_calendar_tsv.py -q`. Expected: FAIL, no `verify`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same. Expected: pass.
- [ ] **Step 5: Commit:** `feat(calendar): compare the rows with the raw list_events results (#436 S8)`

### Task 11: The fetch alerts once a day and the brief marks the calendar

**Files:**
- Modify: `system/scripts/calendar_fetch.sh` (`finish` logs `unverified`; `FETCH_TAG=calendar`; `alert_once "calendar rows unverified:" "<reason>"`; stderr `calendar_fetch: unverified: <reason>`), `system/scripts/brief_prep.sh:27` (on exit 0, the line from `prep_errors.log` adds `prep_unavailable "calendar: rows unverified: <reason> (check today's events in Google Calendar)"`)
- Create: `changes/<date>-calendar-check.md`
- Test: `system/tests/calendar.bats`, `system/tests/prep.bats`

- [ ] **Step 1: Write the failing tests:** `stream_ok` gains a matching `list_events` result built from Task 9's fixture, so the existing cases stay verified; "an unverified fetch prints the rows, exits 0 and alerts once (#436 S8)" (two runs, one `[calendar] calendar rows unverified:` line, the log line's `unverified` set); "--check passes when unverified (#436 S8)"; prep.bats "an unverified calendar adds one unavailable line; a verified one adds none (#436 S8)".
- [ ] **Step 2: Run** `bats -f "#436 S8" system/tests/calendar.bats system/tests/prep.bats`. Expected: FAIL.
- [ ] **Step 3: Implement.** Change line: `- Changed: the brief says when its calendar rows disagree with what the Google Calendar connector listed, and one alert a day names the first difference. (#N)`
- [ ] **Step 4: Run** `bats system/tests/calendar.bats system/tests/prep.bats system/tests/intraday*.bats` (compare the known sandbox failures with master). Expected: pass.
- [ ] **Step 5: Commit:** `feat(calendar): alert once a day and mark an unverified calendar in the brief (#436 S8)`

---

## After the last merge

- Live acceptance per spec §11 (S5 in a `.scratch/` origin with server and client clones, sandboxed; S2 and S8 with the sandbox off).
- Tick S2 and S5-S8 on #436 and close it. Remove the worktrees and branches.
