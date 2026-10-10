---
description: Interactive onboarding — config interview, codebases, remotes, systemd units, calendar, meetings, index and verification. Safe to re-run.
---

You are running setup for this Foundry vault. Every phase is idempotent: show what exists and edit it, never overwrite blindly. When the user gave answers up front (the README's setup prompt), use them and ask only for what is missing; an answer still written as `<…>` is missing. Ask one question at a time, show the default, and wait for the answer. Scripts that are not allowlisted will ask the user for permission; that is intended. Run every script as `system/scripts/<name> …` from the vault root.

## 0. Role and preflight
Read the current role with `system/scripts/vault_index.py field system/config.md machine_role` (no config, or an empty value, means `standalone`). Ask which role this machine has, showing the current role as the default:
- `standalone`: this machine does everything (automation, coding sessions, Obsidian).
- `server`: an always-on machine that runs the automation and the coding sessions. Other machines sync with it through the private `origin`.
- `client`: a machine for reading and editing the vault in Obsidian. It runs no automation and syncs through git.

Then run `system/scripts/check_deps.sh --role <role>`. List every `missing` line with its install hint, and every `optional` line as optional. If `pyyaml` is missing, stop: setup cannot continue without it. Otherwise continue, noting which features are off (no `hyprctl` on a standalone machine: no focus tracking).

On a client, skip phases 3, 6, 6a and 9, and report each as "not used on a client". Phases 5 and 5a run on a client only to remove automation and memory hooks left from an earlier role.

## 1. Existing config
If `system/config.md` exists, show its values and ask which to change. Otherwise create it from the example's frontmatter, without the example's body text, by running exactly this: `[ -f system/config.md ] || { awk '{ print } NR > 1 && /^---$/ { exit }' system/config.example.md; printf '# Config\n\nWritten by /setup. Re-run /setup to change it.\n'; } > system/config.md`. Use its values as the defaults below. Then record the role from phase 0 with `system/scripts/vault_index.py set system/config.md machine_role <role>`.

## 2. Interview
Ask, in order: timezone (default from config; must exist under `/usr/share/zoneinfo`), brief time (`HH:MM`), debrief time (`HH:MM`), superpowers (strategic anchors, one per line), default partition for vault sessions and inbox files (`personal`, `work` or `shared`; default `personal`), digest thresholds (default 5 work events and 20 minutes), recall budget (default 9000 characters, at most 9500). On a client, ask only for the timezone and the default partition.

Write each scalar with `system/scripts/vault_index.py set system/config.md <key> <value>` and the superpowers list by editing the file. Then run `system/scripts/vault_index.py validate system/config.md`; on an error, show it, ask again for that value, and re-validate.

## 3. Codebases
1. Show every existing `system/codebases/*.md` (except `example.md`) and ask whether to edit any. Never replace one.
2. Ask for a directory to scan. Run `system/scripts/discover_codebases.sh <dir>` and show the repos it prints (path, worktrees, remote). If the directory you scanned is one of a repo's `worktrees` but not its `path`, say that `path` is the repo's main checkout and ask which of the two to register. Ask which to register.
3. For each chosen repo, run `system/scripts/inspect_codebase.sh <path>` and draft `system/codebases/<name>.md` (name: letters, digits, `.`, `_`, `-`) from the evidence:
   - `type: codebase`, `name`, `path` (written with `~/` when under your home directory), `partition` (default `work`), `default` (`"true"` for at most one codebase), `stack` (from `manifest_counts` and `notable`; `manifests` shows at most 5 of each kind, and `inspect_codebase.sh --all-manifests <path>` lists every one), `search_globs` (from the most common extensions), `layers` (from `layer_candidates`, e.g. `ui: "web/"`, `api: "Api/"`).
   - In the body: conventions and owners you learn from the user.
   Confirm each field with the user, write the file, and run `system/scripts/vault_index.py validate system/codebases/<name>.md`.
4. Ask "add another directory?" and repeat until no.
5. Add every registered codebase path (expanded, absolute) to `permissions.additionalDirectories` in `.claude/settings.local.json`, keeping everything else in that file and the existing order. Run exactly this, with the paths in place of `<paths…>`: `[ -f .claude/settings.local.json ] || echo '{}' > .claude/settings.local.json; jq '.permissions.additionalDirectories = ((.permissions.additionalDirectories // []) + ($ARGS.positional - (.permissions.additionalDirectories // [])))' .claude/settings.local.json --args <paths…> > .claude/settings.local.json.tmp && jq -e 'type == "object"' .claude/settings.local.json.tmp > /dev/null && mv .claude/settings.local.json.tmp .claude/settings.local.json`

## 4. Remote
Run `system/scripts/setup_remote.sh --detect` and report what it found. Read the current mode with `system/scripts/vault_index.py field system/config.md remote_mode`. Then ask, showing the current mode as the default: a private URL for your vault (`private`), no remote (`none`), or keep the remotes as they are (`keep`, for template maintainers; choose this when `origin` is the template and you maintain it). If the current mode is `private`, show the current `origin` URL (`git remote get-url origin`) as the default URL. Run `system/scripts/setup_remote.sh <url>`, `--none` or `--keep` and report its output.

On a server or a client, only `private` is allowed: the machines share the vault through the private `origin`. Run these checks whenever the mode is `private`, on every role including standalone (`vault_sync.sh` needs the upstream `origin/<branch>`). Check in order, and stop this phase at the first failure with what the user must do:
1. `git config user.name` and `git config user.email` both print a value. If not, ask the user to set them (`! git config user.name "…"`).
2. `GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote origin > /dev/null` succeeds. If not, and `setup_remote.sh` printed a `hint:` line with an SSH URL, offer that URL first: on yes, run `system/scripts/setup_remote.sh <that URL>` and re-check. Otherwise explain that automation needs credentials that work without a prompt (an SSH key without a passphrase prompt, or a credential helper), and re-check once the user has set them up.
3. The branch is published and tracks `origin`: if `git ls-remote --heads origin "$(git branch --show-current)"` prints nothing, run `git push -u origin HEAD`. Otherwise run `git fetch origin` and `git merge-base HEAD "origin/<branch>"`. If that prints nothing, `origin` holds a history of its own (often the README commit a hosting site offers to create), and the first sync would fail: stop and show `git log --oneline "origin/<branch>"`. When it is one commit, offer to replace it with `git push --force-with-lease="<branch>:<that commit>" -u origin HEAD`; otherwise offer `git merge --allow-unrelated-histories "origin/<branch>"`. Run either only on an explicit yes. Then, if `git rev-parse --abbrev-ref '@{u}'` is not `origin/<branch>` (`setup_remote.sh` moves the upstream to `template` when it renames a plain clone's `origin`), run `git branch -u "origin/$(git branch --show-current)"`. Report the result.

## 5. Units
Run `system/scripts/install_units.sh --dry-run` and summarize the units it prints: `foundry-intake` (every 5 minutes), `foundry-brief` and `foundry-debrief` (at the configured times), `foundry-focus` (standalone only), the focus tracker; `foundry-sync` (server only), which syncs with `origin` every `sync_interval_minutes` and, through a drop-in on each run service, before and after every run; `foundry-meetings` (when `meetings_enabled` is `true`), which fetches Gemini notes from Google Drive every hour from 08:00 to 18:00 on workdays; `foundry-update` (standalone and server), which merges template updates every morning at 05:30 and reports them through the alerts the brief reads (turn it off with `systemctl --user disable --now foundry-update.timer`). Ask before installing; on yes run `system/scripts/install_units.sh` and report each `new|changed|unchanged|removed` line.

On a client, run `system/scripts/install_units.sh` without asking: it installs nothing and removes any units this vault installed under an earlier role. Report each `removed` line, or "no units" when it prints none, and skip the linger check.

Then run `loginctl show-user "$USER" -p Linger --value`. If it prints `no`, explain that timers only run while you are logged in, and offer `loginctl enable-linger "$USER"` (the user runs it). On a server, linger is required: give the command, wait until the user says it is done, and re-check; do not continue past this phase until it prints `yes`.

## 5a. Memory hooks
Memory is optional and stays off until its hooks are installed in your user-level Claude Code settings. Ask nothing until you have shown the dry run.

On a client, never install the hooks. Run `system/scripts/install_hooks.sh --dry-run`; if it prints both `unchanged` lines (the hooks are installed from an earlier role), explain that a client runs no coding sessions for the vault, offer `system/scripts/install_hooks.sh --uninstall`, and run it only on an explicit yes. Otherwise report "not used on a client". Then go on to phase 6.

1. Run `system/scripts/install_hooks.sh --dry-run`. If it exits non-zero, show its message, say memory stays off, and go on to phase 6. Otherwise show its output unchanged: the diff to your user settings (`~/.claude/settings.json`, or `$CLAUDE_CONFIG_DIR/settings.json` when that is set) and its `settings:` and `digest command:` lines.
2. If it prints both `settings: unchanged (dry run, nothing written)` and `digest command: unchanged (dry run, nothing written)`, the hooks are already installed: say so, mention that `system/scripts/install_hooks.sh --uninstall` removes them, and go on to phase 6.
3. Explain each entry in the diff, in these words or close to them:
   - `memory_recall.sh` (SessionStart): when a session starts in the vault or in a registered codebase, it adds recent session digests for that codebase or partition, up to `recall_budget_chars` characters, marked as vault data, not instructions.
   - `memory_capture.sh` (Stop): after at least `digest_min_events` tool events and `digest_min_minutes` minutes since the last digest, it asks Claude for a short digest of the session, then redacts it and writes it to `raw/<partition>/notes/` for intake to compile. It asks at most once in a row, and not when Claude's last reply ended with a question to you.
   - `memory_activity.sh` (PostToolUse on edits and Bash): counts work events for that threshold. It only updates a counter.
   - Three `permissions.allow` rules for `vault_index.py related`, `show` and `backlinks`: the only way a codebase session reads the vault, and it sees only that codebase's partition plus `shared`.
   - `digest.md` in your user commands directory: the `/digest` command, which writes a digest on demand. If the dry run says `left alone`, a `digest.md` that is not managed by a vault already exists; it is kept, and `/digest` stays yours.
4. Say that the hooks run in every Claude Code session on this machine but act only inside the vault and the registered codebases. Everywhere else, and in headless runs, subagents and `claude -p` scripts, they exit at once and do nothing.
5. Explain the label: when the Stop hook asks for a digest, Claude Code shows the request as `Stop hook error: Foundry memory (not an error): please reply with a short session digest. …`. It is not an error. Claude Code labels every request from a Stop hook that way; Claude replies with the digest and the session carries on.
6. Ask: "Install the memory hooks? (yes/no, default no)". Only an explicit yes installs. On yes, run `system/scripts/install_hooks.sh` and report its `backup:`, `settings:` and `digest command:` lines. On anything else, change nothing and say that memory capture stays off and that re-running `/setup` (or `system/scripts/install_hooks.sh` after reading its `--dry-run`) turns it on later.

## 6. Calendar
The brief reads today's calendar from the Google Calendar connector of the Claude account this machine's `claude` is logged in with. Run `system/scripts/calendar_fetch.sh` with a Bash timeout of at least 300000 ms (a fetch takes up to about three minutes and costs about $0.20). On exit 0, report how many events it printed for today. Otherwise report its `calendar_fetch:` line and what to do: exit 3, connect Google Calendar in the account's connector settings at claude.ai (same account as this machine), or log `claude` in with a claude.ai account; exit 6, reconnect it; exit 4, try again later; any other exit, show the line from `system/logs/calendar_fetch-<YYYY-MM>.jsonl`. A calendar failure never blocks setup: the brief then lists the calendar under Unavailable Sources.

## 6a. Telemetry
Optional error monitoring from Sentry and Azure Data Explorer. Skipped on a client.
1. Show existing `system/telemetry/*.md` (except `example.md`) and ask whether to edit any. Never replace one.
2. For each registered codebase, ask whether it reports errors to Sentry, ADX, both or neither. For Sentry: the API base URL (for example `https://us.sentry.io`), the organization slug, and the project slugs per environment. For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database). A filter value of `""` selects the rows that lack the attribute: offer that as a separate source when shared services log without it. Ask for a `rank` per environment (lower is listed first in the brief). Ask whether an ADX source `covers` its Sentry source only after the user confirms the codebase's Sentry SDK continues the OpenTelemetry traces (shares trace IDs with ADX); otherwise leave `covers` unset.
3. Sentry needs a read-only token (`event:read`, `project:read`, `org:read`). Ask the user to write it themselves: `! mkdir -p ~/.config/foundry && (umask 077; cat > ~/.config/foundry/sentry.token)`, paste, Ctrl-D. Never ask for the token in chat. Check it is mode 0600.
4. ADX uses the Azure CLI login: if `az account show` fails, ask the user to run `! az login`.
5. Write each source as `system/telemetry/<name>.md` (`<codebase>-<environment>-<kind>` by default), run `system/scripts/vault_index.py validate system/telemetry/<name>.md`, then `system/scripts/telemetry_fetch.py --check <name>`. On a failed check, set `enabled: "false"` and report its line.
6. If any source is enabled, re-run `system/scripts/install_units.sh --dry-run`, show the telemetry units, and install on an explicit yes (as in phase 5).

## 6b. Meetings
On a client, skip this phase and report "not used on a client": the server imports meetings. On a server or a standalone vault, ask, showing the current values as defaults:
1. Fetch Gemini meeting notes from Google Drive (`meetings_enabled`, default `false`)? The fetch reads only Google Docs titled `… - Notes by Gemini`. Transcripts dropped into `meetings/drop/<partition>/` are imported either way.
2. Which partition fetched meetings go to (`meetings_partition`: `work` or `personal`). The default is `default_partition`, or `personal` when that is `shared`; write the answer even when it is the default.
3. Your names as they appear in meeting action items (`owner_names`, one per line), so the brief lists your actions first.

Write `meetings_enabled` and `meetings_partition` with `system/scripts/vault_index.py set system/config.md <key> <value>` and `owner_names` by editing the file (a list of quoted names), then run `system/scripts/vault_index.py validate system/config.md`. If phase 5 installed the units, run `system/scripts/install_units.sh --dry-run` so the meetings timer follows `meetings_enabled`, show the units that would change, and install on an explicit yes (as in phase 5), then report its lines.

If `meetings_enabled` is `true`, check the Drive connector: run `system/scripts/meetings_fetch.sh --check` with a Bash timeout of at least 300000 ms (one search session, no reads; the fetch window is left as it is). On exit 0, report its `the search listed N Docs` line; the hourly fetch reads them. Otherwise report the reason it printed and what to do: exit 3, connect Google Drive in the account's connector settings at claude.ai (same account as this machine); exit 6, reconnect it; exit 4, try again later; exit 7, show the meetings alert in `system/logs/alerts_<date>.md`. A Drive failure never blocks setup: the brief then lists meetings under Unavailable Sources.

## 6c. Handoffs
On a client, skip this phase and report "not used on a client". On a server or a standalone vault, ask whether the brief should list Jira tickets you reported that someone else holds and that have not changed status category for 7 days. Only keys, summaries and links are read, and nothing is written to Jira. On yes, ask for your Jira site's host name, as it appears in a ticket's address without `https://` (`handoffs_site`), and the project keys to read (`handoffs_projects`, one per line). Write `handoffs_site` with `system/scripts/vault_index.py set system/config.md handoffs_site <value>` and `handoffs_projects` by editing the file (a list of quoted keys), then run `system/scripts/vault_index.py validate system/config.md`. An empty `handoffs_projects` turns handoffs off.

When `handoffs_projects` is set, check the Atlassian connector: run `system/scripts/jira_fetch.sh --check` with a Bash timeout of at least 400000 ms (one search session). On exit 0, report its `the search listed N stalled handoffs` line. Otherwise report the reason it printed and what to do: exit 1 with an allow rule named, replace a rule that allows every Atlassian tool with single tools (the fetch will not run while the whole server is allowed); exit 2, fix the setting it names; exit 3, connect Atlassian in the account's connector settings at claude.ai (same account as this machine); exit 6, reconnect it; exit 4, try again later; exit 7, show the handoffs alert in `system/logs/alerts_<date>.md`. A Jira failure never blocks setup: the brief then lists handoffs under Unavailable Sources.

## 7. Index
Run `system/scripts/vault_index.py rebuild`, then `system/scripts/vault_index.py issues`, and report any error. Then run `system/scripts/commit_runs.py --init-cutover`: it records the time from which `/backup` commits each headless run on its own; runs from before it are committed with the rest of the vault.

## 8. Verify
Run `system/scripts/verify_setup.sh --health` and `systemctl --user list-timers 'foundry-*'`. Report each suite's PASS/FAIL line and the next run time of each timer. Health failures are advisory. On a client, run `system/scripts/lint_vault.sh` instead (a client has no test tools or timers) and report its last line.

## 9. Hand-off
For each registered codebase without one, create `wiki/<partition>/concepts/<Name>OnboardingAssignment.md`, where `<partition>` is the codebase's partition and `<Name>` its name in PascalCase. Frontmatter: `type: concept`, `tags: ["onboarding"]`, `compiled_at` today, `partition`, `codebase`, `capability: code`, `status: draft`. Body: ask the Workcell with `code` to map the codebase's layers and its logging and telemetry definitions (start from the `logging_hints` the inspection found) into `wiki/<partition>/entities/<Name>LogEventMap.md`; link `[[Index]]` and name each superpower the work serves. Then add the line `Onboarding: [[<Name>OnboardingAssignment]]` to the body of `system/codebases/<name>.md`, so the note is not an orphan (`wiki/Index.md` belongs to the template; never edit it here). Run `system/scripts/lint_vault.sh` afterwards.

## 10. Report
On a standalone machine or a client (any machine where you open the vault in Obsidian), install the community plugins first:

1. **Quit Obsidian** if it is running: it rewrites `.obsidian/` when it exits and would undo these edits.
2. **Install from the official repositories only.** Dataview on every role that uses Obsidian; Obsidian Git on a client only. For each plugin, run `gh release download --repo blacksmithgu/obsidian-dataview --pattern main.js --pattern manifest.json --pattern styles.css -D .obsidian/plugins/dataview --clobber` and `gh release download --repo Vinzent03/obsidian-git --pattern main.js --pattern manifest.json --pattern styles.css -D .obsidian/plugins/obsidian-git --clobber`. Check that each `manifest.json` has the `"id"` of its folder (`dataview`, `obsidian-git`); report the release tag, since a release's `manifest.json` version can lag its tag.
3. **Enable them:** add each id to `.obsidian/community-plugins.json`, keeping existing entries, with exactly this: `[ -f .obsidian/community-plugins.json ] || echo '[]' > .obsidian/community-plugins.json; jq '. + ($ARGS.positional - .)' .obsidian/community-plugins.json --args <ids…> > .obsidian/community-plugins.json.tmp && mv .obsidian/community-plugins.json.tmp .obsidian/community-plugins.json`.
4. **Settle what `.obsidian/` commits before anything syncs on its own.** Obsidian Git's commit-and-sync stages every change, so its first automatic run commits whatever is in `.obsidian/` at that moment. Run `git status --short --untracked-files=all .obsidian/`, show the list, and ask whether to commit the plugin files and `community-plugins.json` (other machines then get the plugins on their next sync) or to keep `.obsidian/` local (add it to `.git/info/exclude`). Do what the user chooses before the next step.

On a client, then write the Obsidian Git settings into `.obsidian/plugins/obsidian-git/data.json` (merge the keys into any existing file with `jq`; create it as `{}` if missing) and show them with their `data.json` keys. Write them last: they turn on automatic commit-and-sync.

| Setting | Key | Value |
|---|---|---|
| Auto commit-and-sync interval (minutes) | `autoSaveInterval` | `5` |
| Auto commit-and-sync after stopping file edits | `autoBackupAfterFileChange` | on |
| Pull on startup | `autoPullOnBoot` | on |
| Push on commit-and-sync | `disablePush` | `false` |
| Pull on commit-and-sync | `pullBeforePush` | on |
| Merge strategy | `syncMethod` | `merge` |
| Commit message on auto commit-and-sync | `autoCommitMessage` | `sync(client): {{numFiles}} files`, a blank line, `{{files}}`, a blank line, then `Foundry-Command: sync` and `Foundry-Role: client` on two lines |

Then ask the user to open the vault in Obsidian and check that the `wiki/Index.md` dashboards render as tables. If a plugin does not load, tell them to turn off Restricted Mode under Settings → Community plugins.

If `git ls-files --error-unmatch .obsidian/plugins/obsidian-git/data.json` succeeds, run `git rm --cached .obsidian/plugins/obsidian-git/data.json` (the file is machine-specific and gitignored). The plugin runs the pre-commit hook inside Obsidian, whose `PATH` can differ from a terminal's: ask the user to make one test edit and confirm the plugin's commit succeeds; the hook's error names any missing tool. Then give the client notes: files dropped into `raw/inbox/` on a client are not synced (write notes in today's briefing between the `#wiki-ingest-start` and `#wiki-ingest-end` markers in 📝 Notes, which go to the wiki once, just after midnight); disable any plugin that creates `briefings/<date>.md` (daily notes, templates), because the server creates it; `/backup` on a client runs lint and then `vault_sync.sh`; to hand a meeting transcript to the server, drop transcripts (`.vtt`, `.srt`, `.txt` or `.md`) into `meetings/drop/<partition>/`: the plugin commits them, and the pre-commit hook refuses any other file type and any file that holds a secret. Write or paste a transcript elsewhere and move the finished file in: the server imports a drop a minute after it arrives and quarantines an empty one. Obsidian mobile runs no hooks, so a drop from a phone is checked only by the server's redaction.

Show a table of every item set up (role, config, each codebase, remote mode, each unit, linger, memory hooks, calendar, telemetry sources, meetings, handoffs, index, verification) with its status; on a client, the skipped items say "not used on a client". Include the installed plugins and their release tags, and remind the user that `system/scripts/update_template.sh` pulls template updates.
