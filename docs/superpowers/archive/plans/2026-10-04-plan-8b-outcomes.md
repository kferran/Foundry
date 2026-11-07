# Plan 8b outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-04 (plan: `2026-10-04-plan-8b-commit-history.md`, commits 48aed16..0d0c890 plus this status commit). Executed natively on the Debian host: every task applied the plan's tested patches with red-then-green tests, then one final whole-branch review and one fix wave. Acceptance: `docs/superpowers/spikes/2026-10-04-plan-8b-acceptance.md`.

Final verification at 0d0c890: `verify_setup.sh` exit 0 (15/15) on the Debian host (Debian 12.15, jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11.2); lint 0 errors.

**Next on the roadmap:** Plan 8c (sync), then the real vault set up with this server as `server` and the laptop as `client`.

## Rulings

- Ruling: the plan names base 41c243b; the branch was at 48aed16, which adds only the plan doc — cost if wrong: none.
- Ruling: the user chose Native execution after weighing subagent-driven (2026-10-04) — cost if wrong: no per-task review before the final one.
- Final: Ruling: when two pending runs published the same note (spec silent; plan D4 did not cover it), the note is committed with the later run, whose body lists `carries <path> from <run>`; an earlier run left with no paths gets `{"sha": null, "reason": "superseded by <run>"}`. The earlier run's own version of the note no longer exists on disk, so no commit could hold it honestly — cost if wrong: `git log --grep 'Jarvis-Run: <earlier>'` finds no commit for a fully superseded run (its id is in the later commit's body).
- Final: Ruling: the reviewer's pathspec-magic minor was re-graded up to Important, then back: its test passed before any fix, because git matches an existing path literally first — cost if wrong: a deleted tracked note with `[` or `*` in its name could pull a matching file into a run commit.
- Final: Ruling: the reviewer's declined-to-judge items stand: run_id overlap in the DST fall-back hour (the cutover and `run_headless.sh` use the same clock), partially staged hunks committed whole (plan D4), signed-commit prompts (user environment), a non-list `published` (written only by `publish.py`), and Plan 8c behavior — cost if wrong: small.

## Final-review fixes

- fixed the already-committed check depending on the user's git config: `git status` with `status.showUntrackedFiles=no` hid new notes, so a run was marked already committed and its note fell into the next bulk commit. The paths are now staged and the index compared with `HEAD`. `test_a_users_status_config_cannot_hide_a_new_note` RED→GREEN. This also fixes a staged-then-undone path making `commit --only` fail as if the hook had.
- fixed a note two pending runs published being committed with the earlier run's message and the later run's content (see the ruling). `test_a_note_two_pending_runs_published_is_committed_with_the_later_run` and `test_a_run_whose_notes_a_later_run_published_again_is_recorded_as_superseded` RED→GREEN.

## Deferred minors

- Pathspec magic: set `GIT_LITERAL_PATHSPECS=1` in `commit_runs.py`'s `git()`.
- `git reset` after a failed commit drops the user's earlier staged version of a run path (the file content survives; spec §7 says unstage).
- An empty or malformed `commit_runs.since` replays every old run; write it atomically and validate its format.
- `/backup` reads every exit 1 as a hook failure; a merge in progress, a missing identity or an uncaught exception also exit 1, and an exception prints no `commit_runs:` line.
- Subjects may be exactly 72 characters; spec §4 says "under 72".
- `update_template.sh` writes the cutover only after a clean merge; after a conflicted merge, the first `/backup` writes it.
- The staged-then-undone case is fixed by the index-based check but has no dedicated test.
