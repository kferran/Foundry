---
description: Interactive onboarding — config interview, codebases, remotes, systemd units, calendar, index and verification. Safe to re-run.
---

You are running Jarvis setup. Every phase is idempotent: show what exists and edit it, never overwrite blindly. Ask one question at a time, show the default, and wait for the answer. Scripts that are not allowlisted will ask the user for permission; that is intended. Run every script as `system/scripts/<name> …` from the vault root.

## 0. Preflight
Run `system/scripts/check_deps.sh`. List every `missing` line with its install hint, and every `optional` line as optional. If `pyyaml` is missing, stop: setup cannot continue without it. Otherwise continue, noting which features are off (no `gcalcli`: no calendar in the brief; no `hyprctl`: no focus tracking).

## 1. Existing config
If `system/config.md` exists, show its values and ask which to change. Otherwise copy `system/config.example.md` to `system/config.md` and use its values as the defaults below.

## 2. Interview
Ask, in order: timezone (default from config; must exist under `/usr/share/zoneinfo`), brief time (`HH:MM`), debrief time (`HH:MM`), superpowers (strategic anchors, one per line), default partition for vault sessions and inbox files (`personal`, `work` or `shared`; default `personal`), digest thresholds (default 5 work events and 20 minutes), recall budget (default 9000 characters, at most 9500).

Write each scalar with `system/scripts/vault_index.py set system/config.md <key> <value>` and the superpowers list by editing the file. Then run `system/scripts/vault_index.py validate system/config.md`; on an error, show it, ask again for that value, and re-validate.

## 3. Codebases
1. Show every existing `system/codebases/*.md` (except `example.md`) and ask whether to edit any. Never replace one.
2. Ask for a directory to scan. Run `system/scripts/discover_codebases.sh <dir>` and show the repos it prints (path, worktrees, remote). Ask which to register.
3. For each chosen repo, run `system/scripts/inspect_codebase.sh <path>` and draft `system/codebases/<name>.md` (name: letters, digits, `.`, `_`, `-`) from the evidence:
   - `type: codebase`, `name`, `path` (written with `~/` when under your home directory), `partition` (default `work`), `default` (`"true"` for at most one codebase), `stack` (from manifest kinds and notable dependencies), `search_globs` (from the most common extensions), `layers` (from `layer_candidates`, e.g. `ui: "web/"`, `api: "Api/"`).
   - In the body: conventions and owners you learn from the user.
   Confirm each field with the user, write the file, and run `system/scripts/vault_index.py validate system/codebases/<name>.md`.
4. Ask "add another directory?" and repeat until no.
5. Add every registered codebase path (expanded, absolute) to `permissions.additionalDirectories` in `.claude/settings.local.json`, keeping everything else in that file: `jq '.permissions.additionalDirectories = (((.permissions.additionalDirectories // []) + $ARGS.positional) | unique)' --args <paths…>` on the existing file (or on `{}` if there is none), written back only if the result parses.

## 4. Remote
Run `system/scripts/setup_remote.sh --detect` and report what it found. Then ask: a private URL for your vault (`private`), no remote (`none`), or keep the remotes as they are (`keep`, for template maintainers; choose this when `origin` is the template and you maintain it). Run `system/scripts/setup_remote.sh <url>`, `--none` or `--keep` and report its output.

## 5. Units
Run `system/scripts/install_units.sh --dry-run` and summarize the units: `jarvis-intake` (every 5 minutes), `jarvis-brief` and `jarvis-debrief` (at the configured times), `jarvis-focus` (the focus tracker). Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged` line.

Then run `loginctl show-user "$USER" -p Linger --value`. If it prints `no`, explain that timers only run while you are logged in, and offer `loginctl enable-linger "$USER"` (the user runs it).

Memory capture (session digests and recall) is not part of this version of setup; it arrives in a later release and will be added here.

## 6. Calendar
Run `timeout 20 gcalcli list < /dev/null`. If it fails, tell the user to run `! gcalcli init` and re-run this phase afterwards.

## 7. Index
Run `system/scripts/vault_index.py rebuild`, then `system/scripts/vault_index.py issues`, and report any error.

## 8. Verify
Run `system/scripts/verify_setup.sh --health` and `systemctl --user list-timers 'jarvis-*'`. Report each suite's PASS/FAIL line and the next run time of each timer. Health failures are advisory.

## 9. Hand-off
For each registered codebase without one, create `wiki/<partition>/concepts/<Name>OnboardingAssignment.md`, where `<partition>` is the codebase's partition and `<Name>` its name in PascalCase. Frontmatter: `type: concept`, `tags: ["onboarding"]`, `compiled_at` today, `partition`, `codebase`, `agent_owner: CodingAgent`, `status: draft`. Body: direct **CodingAgent** to map the codebase's layers and its logging and telemetry definitions (start from the `logging_hints` the inspection found) into `wiki/<partition>/entities/<Name>LogEventMap.md`; link `[[Index]]` and name each superpower the work serves. Run `system/scripts/lint_vault.sh` afterwards.

## 10. Report
Show a table of every item set up (config, each codebase, remote mode, each unit, linger, calendar, index, verification) with its status. Remind the user to install the Obsidian **Dataview** plugin for the `wiki/Index.md` dashboards, and that `system/scripts/update_template.sh` pulls template updates.
