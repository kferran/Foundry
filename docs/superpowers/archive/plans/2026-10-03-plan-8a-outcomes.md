# Plan 8a outcomes: rulings, fixes and deferred minors

Recorded from the execution ledger on 2026-10-03 (plan: `2026-10-03-plan-8a-roles-debian.md`, commits df368ac..5660b38 plus this status commit). Executed natively: every task applied the plan's tested patches with red-then-green tests, then one final whole-branch review on the most capable model and one fix wave. Acceptance: `docs/superpowers/spikes/2026-10-03-plan-8a-acceptance.md`.

Final verification at 5660b38: `verify_setup.sh` exit 0 (14/14) on Arch and on the Debian host (Debian 12.15, jq 1.6, Bats 1.8.2, SQLite 3.40.1); lint 0 errors.

**Next on the roadmap:** Plan 8d (calendar from the installed calendar connector, replacing `gcalcli`; user decision 2026-10-03), then 8b (commit history) and 8c (sync).

## Rulings

- Ruling: branched from `feat/plan-8` at df368ac (the approved spec plus the plan doc) instead of 7efe52d — the plan file must be on the branch — cost if wrong: none.
- Ruling: the final whole-branch review ran before the acceptance record and status docs — the outcomes doc must include its fixes — cost if wrong: none.
- Ruling (user decision): the calendar comes from the installed connector through a separate narrow fetch step, in its own Plan 8d after 8a; in 8a `gcalcli` became optional for every role — cost if wrong: a standalone machine is no longer told `gcalcli` is missing until 8d replaces it.
- Final: Ruling: re-graded reviewer Minor 2 (`verify_on_host.sh -V` exits 0 without running the gate) to Important — a measurement that reports green without measuring — fixed — cost if wrong: none.
- Final: Ruling: re-graded reviewer Minor 8a (guard tests did not pin how narrow the `sqlite_master` allowance is) to Important — it is the security pin for the relaxed authorizer — fixed — cost if wrong: none.
- Final: Ruling: `/setup` phase 6 still checks `gcalcli` until Plan 8d replaces it with the connector fetch — one rewrite instead of two — cost if wrong: a `/setup` run before 8d shows a `gcalcli` step the user does not want.

## Acceptance notes

- `claude` reads as missing over a non-login ssh command on the Debian host (`~/.local/bin` is only on the login `PATH`). Units use the absolute `CLAUDE_BIN`; `/setup` runs inside `claude`. Not a defect.
- `apt` hints were not exercised live (every apt-packaged item is installed on the host); `setup.bats` covers them with stubs.

## Final-review fixes

- fixed `/setup` on a client never removing units and hooks left from an earlier role: phases 5 and 5a now run on a client only to remove them (units without asking; hooks only on an explicit yes). `commands.bats` client test RED→GREEN.
- fixed `verify_on_host.sh` accepting a host that ssh reads as an option (`-V` exited 0 without running the gate): leading `-` refused. `setup.bats` RED→GREEN; the failing-gate test now also asserts the summary prints.
- fixed the guard's narrowness being unpinned: `test_update_allowance_covers_only_the_schema_table` failed with the guard widened to every `UPDATE` and passes on the real guard; `UPDATE notes` is rejected.
- fixed `gcalcli` being required (user decision): optional for every role, with a hint naming it as an optional calendar source. `setup.bats` RED→GREEN; README updated.

## Deferred minors

- `verify_on_host.sh`'s remote command assumes a POSIX login shell (a fish login shell would break it).
- An invalid `machine_role` in config makes `check_deps.sh` print its usage line, which blames the arguments rather than the config.
- `check_deps.sh`'s `hint()` has no default arm; an item added without one aborts under `set -u`.
- `/setup` phase 5's dry run does not list units a role change would remove; the "`jarvis-focus` (standalone only), the focus tracker" wording reads awkwardly.
- README Requirements still shows only a `pacman` command for PyYAML and pytest.
