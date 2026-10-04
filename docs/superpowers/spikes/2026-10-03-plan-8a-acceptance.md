# Plan 8a acceptance

**Date:** 2026-10-03 · **Branch:** `feat/plan-8a` · **Commits:** a07b695 (Tasks 1–5), re-run at 5660b38 (final-review fixes) · **Debian host:** Debian 12.15 (bookworm), jq 1.6, Bats 1.8.2, SQLite 3.40.1, Python 3.11. The host name is kept out of this record (template rule, spec §9).

## Gate

| Where | Commit | Exit | Suites | Notes |
|---|---|---|---|---|
| Arch (local) | a07b695 | 0 | 14/14 PASS | |
| Debian host (`verify_on_host.sh`) | 184bcad (Task 1 red step) | 1 | 12/14 | `hooks_install.bats` (empty install record on jq 1.6) and pytest (`test_guard.py` FTS `MATCH` and `pragma_table_info` on SQLite 3.40), as planned |
| Debian host | 54ab28e (Task 1 fixes) | 0 | 14/14 PASS | |
| Debian host | a07b695 | 0 | 14/14 PASS | copy and log removed; nothing left under `/tmp` |
| Arch (local) | 5660b38 | 0 | 14/14 PASS | after the final-review fixes |
| Debian host | 5660b38 | 0 | 14/14 PASS | |

## Role outputs

On the Debian host (from a `git archive` of the scripts in a `mktemp -d` directory, removed afterwards), at a07b695:

- `--role client`: `claude` (missing; see below), `git`, `jq`, `python3`, `pyyaml`, `fts5`, plus the optional `herdr` and `tmux`. Nothing else.
- `--role server`: the full list without `hyprctl`. `gcalcli` missing with its `pipx` hint. At 5660b38 `gcalcli` is optional for every role (user decision: the calendar moves to the connector in Plan 8d).

Locally (Arch), the same two roles printed the same item sets; `gcalcli` missing on `server` at a07b695.

**`claude` shows as missing over a non-login ssh command** on the host, because `~/.local/bin` is only on the login shell's `PATH`. Units are unaffected (they carry the absolute `CLAUDE_BIN` found at install time) and `/setup` runs inside `claude`. Not a defect.

`apt` hints were not exercised live: every apt-packaged item is installed on the host. `setup.bats` covers them with `PATH` stubs.

## Verdict

**PASS.** The suite passes on the oldest supported Debian release with its tool floor, the two Debian defects found while planning are fixed, and each role reports exactly its own requirements.
