# Plan 4b outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-02 (plan: `2026-10-02-plan-4b-memory-integration.md`, commits 6b1bbae..f663384). Executed subagent-driven: a fresh implementer and task review per task (Task 2 needed one fix round), then one final whole-branch review and one fix wave. Live check of `/setup` phase 5a: `docs/superpowers/spikes/2026-10-02-plan-4b-acceptance.md`.

Final verification at f663384: `hooks_install.bats` 33/33, `verify_setup.sh` exit 0.

**Next on the roadmap:** Plan 6 (Communication). Plans 9 (rename to Cerebra) and 10 (migrate Cerebro and Wong) are the last steps, by the user's decision.

## Rulings
- Ruling: Task 8 also adds two final roadmap rows the user requested (2026-10-02): "Rename to Cerebra (product, unit prefix, env vars, agent_owner values, team theme)" and "Migrate Cerebro and Wong into Cerebra" — both last, after everything else — user decision recorded in conversation — cost if wrong: two roadmap rows to edit.
- Ruling: Task 7 (live /setup 5a check) is run by the user as a manual checklist — the plan already makes it manual — cost if wrong: Task 8 waits on the user.
- Task 2: Ruling: Important (plan-mandated) "an empty or multi-document install record makes --argjson fail, so install and --uninstall exit 1 blaming settings.json" — fix: treat any record value that is not exactly one JSON value as no record (fallback path), with empty-file and {} {} tests — §7.3a: uninstall is the escape hatch and must not depend on a file this task added — cost if wrong: none.
- Final: Ruling: re-graded Minor 1 (uninstall exits 1 and leaves digest.md when the record can't be written) to Important, together with the T2 install variant — §7.3a: the escape hatch must not depend on the record — fix in one wave: digest step before the record update, record update best-effort (warn, continue) in uninstall, and install pre-flights the record dir (or writes the record first) so it never leaves a half install — cost if wrong: none.
- Final: Ruling: Important 1 (outcomes doc misstates the ledger) and Minor 4 (acceptance record says the record is written before settings; cites 30 tests, there are 31) are controller bookkeeping docs — fixed by the controller from the ledger and the code — cost if wrong: none.

## Fix rounds and final-review fixes
- Task 2: fix round 1/5 (1 addressed, 0 open — malformed record falls back; commits f22eb64..69b0476)
- fixed uninstall/install depending on a writable install record — hooks_install.bats tests 32 (uninstall with unwritable record dir: exit 0, warning, settings restored, digest removed) and 33 (install refuses before writing: exit 1, settings sha unchanged, no digest.md) RED→GREEN; suite 33/33; gate exit 0 (commit f663384); scoped re-review: addressed, no new breakage.
- fixed acceptance-record slips (record written after settings; 31 tests) — docs (300f998).

## Deferred minors
- Task 1: refusal tests compare "$(cat)" (strips trailing newlines) instead of sha256sum/cmp (plan-mandated).
- Task 1: shape test checks only the message prefix, not the offending path, nor that no .bak/digest.md was created.
- Task 1: no test that --uninstall refuses {} {} / garbage and leaves the file untouched.
- Task 1: backup -e then cp -p is not atomic across concurrent runs.
- Task 2: no-record fallback still deletes user-created empty hooks containers; a reinstall after losing the record makes that permanent (plan-accepted for pre-record installs; also triggers after `git clean -X`).
- Task 2: record key not normalized (CLAUDE_CONFIG_DIR with a trailing slash stores …//settings.json; a plain --uninstall misses it) — realpath -m the config dir.
- Task 2: unwritable record dir leaves settings written but no digest.md (rc 1); write the record first or pre-flight the dir.
- Task 2: the junk-record test rewrites the record by reinstalling before --uninstall, so uninstall-with-junk is exercised only through the shared read path.
- Task 3: default-no prompt "(yes/no, default no)" not pinned by a test (plan-mandated test list).
- Task 3: decline/yes-branch wording only partly pinned (backup:, the install prompt); ordering check is a prose proxy.
- Task 4: remote_mode test doesn't pin --detect-first or the origin URL default (prose only).
- Task 4: first-run default shows the example's "none" without saying it's the template's initial value.
- Task 5: README names table header still says "Concrete artifacts (planned)" though the Soundwave artifacts now exist.
- Task 5: README states ~/.claude/settings.json without the CLAUDE_CONFIG_DIR override; /digest "in any session in scope" is loose (plan-mandated text).
- Final: /setup 5a re-asks on every re-run when the user has their own digest.md (dry run prints "left alone", not "unchanged"); accept "left alone" as installed.
- Final: plan D3 says a hand-edited record can never delete a user container; a hand-written record listing user containers does delete them.
- Final: README.md:163 says uninstall removes only entries owned by this vault; STRIP and digest_owned match any Jarvis vault (Plan 3 D7).
- Final: permission tests can't exercise the guard as root.
- Final: install's record write after a passing preflight can still fail mid-way (race/disk); not observed.
