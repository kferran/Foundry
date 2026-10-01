# Vault Template Design

**Date:** 2026-09-30
**Status:** Approved in brainstorming (incl. schema + index addendum), pending spec review
**Branch:** `feat/vault-template`

## 1. Context

`scaffold.sh` (866 lines) generates an Obsidian + Claude Code "second brain" vault: directories, `CLAUDE.md`, slash commands, templates, agent personas, automation scripts, systemd user units, a BATS suite and a git pre-commit hook. A review found five blocking defects (headless runs can't write, a mock telemetry generator on a live timer, an ingest-marker bug that deletes briefing content, a pre-commit gate that never fails, and re-runs that clobber state) plus a set of medium and low issues (traced in §13).

Agents also discover context by grepping and reading whole folders of notes, which grows token cost with the vault, and frontmatter rules are duplicated (and already inconsistent) across templates, the linter and prompts.

## 2. Goals

1. The repo **is** the vault template. Generated files are committed as real files; `scaffold.sh` is removed.
2. A new user clones the repo, launches `claude`, runs `/setup`, and ends with a working vault configured for their machine and codebases.
3. Nothing machine- or user-specific is committed. Per-user state is produced by `/setup` and gitignored.
4. Anything that must be exact (config parsing, unit rendering, linting, schema validation, indexing, git remote changes, metric checks, focus stats, codebase inspection) is a deterministic script (bash, or Python where parsing is involved). The LLM handles conversation and synthesis and calls those scripts.
5. Headless (systemd) Claude runs have the minimum permissions needed; failures are visible, never silent.
6. The template is stack-agnostic. Codebases are discovered and inspected at `/setup` time.
7. **One schema per note type** is the single source of truth for frontmatter, used by validation, templates, the index and Obsidian (Dataview).
8. **Agents query a SQLite index before reading notes**, so context cost scales with the answer, not the vault.
9. Every finding from the review is resolved (§13).

## 3. Decisions

| Topic | Decision |
|---|---|
| Scope | All review findings: high, medium and low |
| Headless permissions | Narrow allowlist in committed `.claude/settings.json`; prep scripts gather inputs so headless Claude needs almost no Bash |
| Telemetry | Enricher stays a mock; its timer ships disabled and is only enabled when `telemetry_enabled: true` |
| Pre-commit | Deterministic linter; no LLM in the hook |
| Re-runs | `/setup` and every script it calls are idempotent; existing config is shown and edited, never overwritten blindly |
| Repo model | `/setup` renames the clone's `origin` to `template` and adds the user's private remote as `origin` (or none, or keep for maintainers) |
| Multiple codebases | One file per codebase in `system/codebases/`, produced by discovery + inspection + user confirmation |
| Audience | Generic template; no hardcoded Ultron/Vue/.NET/Kusto |
| `herdr` | Optional, documented in README, not dependency-checked |
| Source of truth | Markdown notes. SQLite is a derived, gitignored, rebuildable index |
| Schemas | One Obsidian note per note type in `system/schemas/`, field definitions in frontmatter |
| Obsidian querying | Dataview plugin over frontmatter; SQLite serves agents and scripts only |
| Indexer language | Python 3 + PyYAML (stdlib `sqlite3`); Python becomes the only frontmatter parser |
| Machine data (metrics, focus, alerts) | Stays as files; not moved into SQLite (§14) |

## 4. Migration sequence

1. **Baseline:** run the current `scaffold.sh` (default `BRAIN_TZ`) at the repo root. Immediately delete the generated `.git/hooks/pre-commit` (it calls `claude -p /lint` and would run on every commit that follows). Commit the output as `chore: generate vault structure from scaffold.sh`. This commit contains rendered units with this machine's absolute path; the next commits convert them to templates.
2. **Remove generator:** `git rm scaffold.sh` in its own commit.
3. **Apply fixes** as a sequence of focused commits against real files, each with tests written first (TDD) and each leaving the gating suites (§12) green. Commit order is defined in the implementation plan.

## 5. Final repo layout

```
README.md                         ★ new-user and maintainer guide
CLAUDE.md                           generic rules; imports @system/config.md
.gitignore                          see §10
.claude/settings.json             ★ committed permission allowlist (§7)
.claude/commands/
  setup.md brief.md debrief.md ingest.md query.md lint.md backup.md impact.md
.githooks/pre-commit              ★ runs lint_vault.sh --staged
raw/.gitkeep
raw/archive/.gitkeep
raw/telemetry/.gitkeep            ★ production-error intake (not ingested)
wiki/Index.md                     ★ root index node; Dataview dashboards
briefings/.gitkeep
system/config.example.md          ★ committed example of the global config
system/codebases/example.md       ★ committed example of a codebase file
system/schemas/                   ★ one schema note per note type (§6.16)
  schema.md concept.md index.md briefing.md plan_gate.md
  production_error.md config.md codebase.md
system/templates/
  wiki-concept.md daily-briefing.md intent-shaper.md compilation-metric.json
system/agents/
  ChiefOfStaff.md CodingAgent.md SystemMaintenance.md
system/scripts/
  vault_index.py                  ★ CLI entry point for schema + index (§6.17)
  vaultlib/                       ★ Python package
    frontmatter.py schema.py links.py index.py cli.py
  lib_config.sh                   ★ shell helpers; delegate parsing to vault_index.py
  check_deps.sh                   ★ single dependency list
  run_headless.sh                 ★ wrapper for all headless claude -p calls
  intake_daemon.sh                  rewritten (§6.4)
  brief_prep.sh                   ★ calendar + focus stats into inputs/
  debrief_prep.sh                 ★ git digest + transcript digest + focus stats into inputs/
  focus_stats.sh                  ★ focus log → top notes + fragmentation windows
  track_obsidian.sh                 fixed
  telemetry_enricher.sh             mock; config-aware; writes to raw/telemetry/
  check_metrics.sh                ★ quarantine decision from metric files
  lint_vault.sh                   ★ wrapper over vault_index.py issues
  install_units.sh                ★ render + install + enable systemd units
  setup_remote.sh                 ★ template/origin remote handling + hooksPath
  discover_codebases.sh           ★ find git repos under a directory
  inspect_codebase.sh             ★ gather stack evidence as JSON
  verify_setup.sh                   runs gating suites; --health adds health suite
system/systemd/
  brain-intake.service.in  brain-intake.timer.in
  brain-brief.service.in   brain-brief.timer.in
  brain-debrief.service.in brain-debrief.timer.in
  brain-focus-tracker.service.in
  brain-telemetry.service.in brain-telemetry.timer.in   (renamed from ultron-telemetry.*)
system/tests/
  vault_integrity.bats              structure only; runs anywhere
  scripts.bats                    ★ shell script tests, using fixtures + stubs
  system_health.bats              ★ live service state; advisory
  python/                         ★ pytest suite for vaultlib
  fixtures/                       ★ stubs (claude/systemctl/gcalcli), sample repos, transcripts, fixture vault
system/logs/.gitkeep
system/quarantine/.gitkeep
system/index.db                     generated, gitignored
docs/superpowers/specs/             this spec
```

★ = new or moved relative to the scaffold output.

## 6. Components

**Shell scripts:** `#!/bin/bash`, `set -euo pipefail`, locate the vault as `VAULT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`, and respect a `VAULT_ROOT` env override for tests. External tools (`claude`, `systemctl`, `gcalcli`, `git`) are called by name so tests can put stubs first on `PATH`; `install_units.sh` additionally honours `SYSTEMCTL` and `SYSTEMD_USER_DIR`.

**Python:** `#!/usr/bin/env python3`, stdlib plus PyYAML only, no network. Same `VAULT_ROOT` resolution and override. Never crashes on bad input notes: parse failures become `issues` rows.

### 6.1 `lib_config.sh` (sourced)

Shell-facing helpers. All parsing is delegated to `vault_index.py`.

- `config_get <key> [default]` → `vault_index.py field system/config.md <key>`; expands leading `~`; prints default if missing.
- `config_set <key> <value>` → `vault_index.py set system/config.md <key> <value>`.
- `codebases_list` — names of `system/codebases/*.md`, excluding `example.md`.
- `codebase_get <name> <key> [default]` → `vault_index.py field`; nested keys as `layers.ui`; lists printed comma-joined.
- `codebase_default` — the codebase with `default: true`, or the only codebase if there is exactly one.
- `config_validate` → `vault_index.py validate system/config.md system/codebases/*.md`; exit 1 on error.

Validation rules live in the `config` and `codebase` schemas (§6.16), not in shell:
- required: `timezone`, `brief_time`, `debrief_time`, `telemetry_enabled`, `remote_mode`
- `timezone` kind checks `/usr/share/zoneinfo`; `time` kind checks `HH:MM`
- `remote_mode` enum `private|none|keep` (the example ships `none`, so a config validated before `setup_remote.sh` runs never pushes to the template)
- codebase `path` must exist and be a git repo (warning severity)
- codebase `default` is `unique_true` across codebase files

### 6.2 `check_deps.sh`

The single dependency list: `claude git jq bats gcalcli systemctl hyprctl python3`, plus checks that `python3 -c 'import yaml'` succeeds, that `python3 -m pytest` is available, and that `sqlite3` has FTS5 (`python3 -c` creating an FTS5 table in memory). Prints `ok|missing <item> <install hint>` per item (`sudo pacman -S python-yaml python-pytest`, etc.). Exit 0 always; `--strict` exits 1 if anything is missing. Used by `/setup` preflight and `system_health.bats`.

### 6.3 `run_headless.sh <slash-command> [args…]`

Runs `claude -p "<slash-command> <args>"` from `VAULT_ROOT`. Appends a timestamped header plus all output to `system/logs/headless/<command>_<YYYY-MM-DD>.log`. Passes through claude's exit code. All units and the intake daemon call Claude only through this wrapper.

### 6.4 `intake_daemon.sh`

Per run:
1. **Briefing extraction:** if today's briefing exists and contains both `#wiki-ingest-start` and a later `#wiki-ingest-end`, extract the text between each pair to `raw/daily_note_drop_<epoch>.md` and remove the blocks (awk to a temp file, then `mv`). An unterminated start marker leaves the briefing untouched and logs an alert.
2. **For each regular file in `raw/`** (not subdirectories):
   - skip if modified less than 60 s ago (half-written or syncing; the drop file from step 1 is picked up on the next run)
   - if `vault_index.py field <file> type` is `production_error` → move to `raw/telemetry/`, log, continue
   - if `raw/archive/<name>` already exists, rename the raw file to `<stem>-<epoch>.<ext>` **before** ingesting, so the wiki's source link stays valid
   - touch a marker file, run `run_headless.sh /ingest <file>`
   - success = exit 0 **and** at least one `wiki/**/*.md` newer than the marker → move to `raw/archive/`
   - otherwise → move to `system/quarantine/` and append an alert with the reason (`claude exit <n>` or `no wiki output`)
3. **Alerts** go to `system/logs/alerts_<YYYY-MM-DD>.md`. The daemon never creates or appends to files in `briefings/`.

Known limitation: an unrelated wiki edit during an ingest run can mask a no-output ingest. Accepted.

### 6.5 `brief_prep.sh [date]` and `debrief_prep.sh [date]`

Both write to `system/logs/inputs/<date>/`, always exit 0, and record any unavailable source in `inputs/<date>/unavailable.md` (one line per source).

- `brief_prep.sh`: `gcalcli agenda "<date>T00:00" "<date>T23:59" --tsv > calendar.tsv`; `focus_stats.sh <yesterday> > focus_yesterday.md`.
- `debrief_prep.sh`:
  - `git.md` — for the vault and every codebase: `git log --since=<date>T00:00 --until=<date>T23:59 --format=…` under a `## <name>` heading
  - `transcript.md` — from `~/.claude/projects/<slug>/*.jsonl` modified on `<date>`, where `<slug>` is `VAULT_ROOT` with `/` and `.` replaced by `-`; `jq` keeps only user and assistant text content. Headless sessions (intake, brief, debrief runs) are excluded. Detection method is verified during implementation: preferred is a transcript field identifying non-interactive entrypoints; fallback is excluding sessions whose first user message is a slash command issued by `run_headless.sh`.
  - `focus.md` — `focus_stats.sh <date>`

Under systemd these run as `ExecStartPre=-…` (failures never block the brief). Run by hand, `/brief` and `/debrief` call them when today's inputs directory is missing.

### 6.6 `focus_stats.sh <date>`

Reads `system/logs/obsidian_focus_<date>.log` (`[HH:MM:SS] Note`). Outputs markdown: top 10 notes by sample count (×30 s ≈ minutes), and every 15-minute window with more than 4 note switches, flagged as **Focus Fragmentation Warning**. Missing log → "no focus data".

### 6.7 `track_obsidian.sh`

Unchanged behaviour; fixes: `LOG_DIR` derived from `VAULT_ROOT` and created with `mkdir -p` before use; `hyprctl` failures don't kill the loop.

### 6.8 `telemetry_enricher.sh`

- Remains a mock generator. Frontmatter gains `mock: true`; `/brief` labels mock items as such. Output validates against the `production_error` schema.
- Writes to `TELEMETRY_DIR` (default `$VAULT_ROOT/raw/telemetry`).
- Repo selection: the codebase whose `namespace_prefix` prefixes the stack frame; otherwise search every codebase with `git ls-files -- "*<Class>.cs"`. The note records `codebase:` and takes `service:` from that codebase's `name`.
- Distinguishes "no class parsed", "no codebases configured" and "class not found" in the attribution text.

### 6.9 `check_metrics.sh`

Reads `system/logs/metrics/<agent>-<epoch>.json`. For each agent, if its three most recent files all have `verification_gates.test_suite_passed == false` or `system_telemetry.warnings_generated > 5`, prints the agent name. Exit 1 if any agent is printed, 0 otherwise, 0 if no metrics exist. The metric template gains an `"agent"` field; the CodingAgent persona specifies the filename convention.

### 6.10 `lint_vault.sh [--staged]`

Thin wrapper: `vault_index.py issues [--staged]`; exit 1 if any `error` issue, else 0. Prints issues as `path:line: severity: message` and a summary line.

- Scope: every note whose folder has a schema (`wiki/`, `briefings/`, `raw/telemetry/`, `system/schemas/`, `system/config*.md`, `system/codebases/`). `raw/` and `raw/archive/` are unstructured and not validated.
- **Errors:** missing or malformed frontmatter; schema violations (§6.16); dead links in `wiki/` and `briefings/`.
- **Warnings:** unknown fields; orphan notes in `wiki/`; codebase path missing.
- `--staged` limits issues to staged files (`git diff --cached --name-only --diff-filter=ACMR`) while still resolving links against the whole vault.

### 6.11 `.githooks/pre-commit`

If no files in linted folders are staged, exit 0. Otherwise run `system/scripts/lint_vault.sh --staged`; non-zero blocks the commit. If the script is missing or not executable, print an error and exit 1. `--no-verify` remains the escape hatch.

### 6.12 `install_units.sh [--dry-run | --uninstall]`

- Renders `system/systemd/*.in` replacing `{{VAULT_ROOT}}`, `{{TZ}}`, `{{BRIEF_TIME}}`, `{{DEBRIEF_TIME}}` (sed with `|` delimiter, values escaped for `& | \`). Fails if any `{{` remains.
- Prepends `# Managed by vault: <VAULT_ROOT>` to each rendered unit.
- Writes to `SYSTEMD_USER_DIR` (default `~/.config/systemd/user`) only when content differs; reports `new|changed|unchanged` per unit.
- `daemon-reload`; `enable --now` brain-intake.timer, brain-brief.timer, brain-debrief.timer, brain-focus-tracker.service; brain-telemetry.timer enabled iff `telemetry_enabled: true`, otherwise disabled.
- If set, `systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE`.
- `--dry-run` prints rendered units, touches nothing. `--uninstall` disables and removes only units whose header names this `VAULT_ROOT`.
- Re-running after moving the vault re-points all units.

### 6.13 `setup_remote.sh <url> | --none | --keep`

- `<url>`: if a `template` remote doesn't exist, rename `origin` → `template`. Add or set `origin` to `<url>` (refuse if equal to the template URL). `git ls-remote` reachability check warns only. Sets `remote_mode: private` and `template_remote` via `config_set`.
- `--none`: same rename; no `origin`. Sets `remote_mode: none`.
- `--keep`: maintainer mode; remotes untouched. Sets `remote_mode: keep`.
- Already-configured state (template exists, origin differs) is a no-op.
- Always `git config core.hooksPath .githooks`.

### 6.14 `discover_codebases.sh <dir>` and `inspect_codebase.sh <path>`

- `discover_codebases.sh`: if `<dir>` is a repo, print it; else list repos under it (`find -maxdepth 3 -name .git`, files or dirs). Collapse worktrees of the same repo (same `git rev-parse --git-common-dir`) into one entry listing all worktree paths. Output: one JSON object per line `{path, worktrees[], remote}`.
- `inspect_codebase.sh`: evidence only, printed as one JSON object:
  - `manifests[]`: `{file, dir, kind, details}` for `package.json` (notable deps: vue/react/next/angular/svelte), `*.csproj`/`*.sln` (`TargetFramework`, `RootNamespace`), `go.mod` (module), `pyproject.toml` (project name), `Cargo.toml`, `pom.xml`, `Gemfile`
  - `layer_candidates[]`: top-level dirs containing their own manifest
  - `namespace_prefix_candidates[]`: RootNamespace, top `namespace X.` prefixes in `.cs`, Go module path, Python package
  - `extensions{}`: tracked-file counts by extension (`git ls-files`)
  - `logging_hints{}`: counts of `EventId`, `LoggerMessage`, `ILogger`, `logger.`, `log.` etc., with up to 10 example paths
  - `git{}`: default branch, remote URL

### 6.15 `verify_setup.sh [--health]`

Runs the gating suites: `vault_integrity.bats`, `scripts.bats`, `python3 -m pytest system/tests/python -q`. `--health` also runs `system_health.bats`. Exit code reflects the gated suites only; health failures are reported but do not change the exit code.

### 6.16 Schemas (`system/schemas/<type>.md`)

Each schema is an Obsidian note: frontmatter defines the type, the body documents it for humans and agents.

```yaml
---
type: schema
schema_for: concept
folders: [wiki/]
fields:
  type:        {kind: const, value: concept, required: true}
  tags:        {kind: list, of: string, required: true}
  compiled_at: {kind: date, required: true}
  agent_owner: {kind: enum, values: [CodingAgent, SystemMaintenance, ChiefOfStaff]}
  is_friction: {kind: bool, default: false}
  source:      {kind: link}
---
# Concept
Evergreen, atomic knowledge node compiled from raw/.
```

- **Field kinds:** `const(value)`, `string`, `text`, `int`, `bool`, `date` (YYYY-MM-DD), `datetime` (ISO 8601), `time` (HH:MM), `timezone` (exists in zoneinfo), `enum(values)`, `list(of: <kind>)`, `map(fields: {...})` (one level, for `layers`), `link` (wikilink, must resolve), `path` (filesystem path, `~` expanded; `must_exist: warn|error`).
- **Field options:** `required`, `default` (used by views and Dataview docs; never written into notes), `unique_true` (bool: at most one note of this type may be `true`).
- **Routing:** a note's `type:` field selects its schema. A note in a folder listed by some schema must have a `type:` of a schema that lists that folder; otherwise it is an error (e.g. a `briefing` inside `wiki/`). Notes in unlisted folders are ignored. A folder may be listed by several schemas (`wiki/` holds `concept` and `index`).
- **Unknown fields:** warning, never error, so users can add fields freely in Obsidian.
- **Shipped schemas:** `schema` (validates the schema notes themselves), `concept`, `index` (for `wiki/Index.md` and dashboard notes), `briefing`, `plan_gate`, `production_error`, `config`, `codebase`. Field sets are taken from the existing templates and §8.
- **Drift guard:** every template in `system/templates/` declares the `type:` it produces; a test renders it with sample placeholder values and validates it against its schema (§12).
- **Adding a note type** = adding a schema note. `CLAUDE.md` states this rule.

### 6.17 Index (`system/index.db`) and `vault_index.py`

**Package layout (`system/scripts/vaultlib/`):** `frontmatter.py` (split + parse, error positions), `schema.py` (load schemas, validate), `links.py` (extract + resolve wikilinks, tags), `index.py` (SQLite schema, incremental refresh, views), `cli.py` (subcommands). `vault_index.py` is a three-line entry point.

**Tables:**

| Table | Columns |
|---|---|
| `notes` | `path PK, type, title, folder, mtime, size, sha256, valid` |
| `fields` | `path, key, value, kind` (value JSON-encoded for lists and maps) |
| `links` | `src, target_raw, target_path` (NULL if dead), `line, kind` (`link`/`embed`) |
| `tags` | `path, tag` (frontmatter tags + inline `#tags` outside code) |
| `notes_fts` | FTS5 over `title, body` |
| `issues` | `path, line, severity, code, message` |
| `meta` | `schema_hash, built_at, version` |
| `v_<type>` | generated view per schema: `path, title` + one column per field, typed via `CAST`, defaults applied with `COALESCE` |

**Link resolution** (moved from the old linter, unchanged): `[[T]]`, `[[T|alias]]`, `[[T#heading]]`, `![[T]]`. `T` containing `/` resolves as a vault-relative path; otherwise by basename anywhere in the vault excluding `.git/` and `.obsidian/`; `.md` is assumed when `T` has no extension. Links inside fenced code blocks and inline code are ignored.

**Freshness:** no watcher daemon. Every subcommand that reads the index (`query`, `related`, `backlinks`, `orphans`, `friction`, `issues`, `validate`) first runs an incremental refresh. `field` and `set` read or edit a single file directly and never touch the index, so the intake loop stays cheap. The refresh: walk `*.md` (excluding `.git/`, `.obsidian/`), compare `mtime`+`size` (then `sha256` on mismatch) with `notes`, re-parse only changed files, delete rows for removed files, then re-resolve links whose `target_raw` could be affected by added or removed basenames. If `meta.schema_hash` differs from the current schema notes, do a full rebuild. Writes happen in one transaction with WAL mode; a lock file serializes concurrent refreshes (intake daemon vs interactive session). A missing or corrupt `index.db` is rebuilt automatically.

**CLI** (`--json` on every read command; default output is compact markdown):

| Subcommand | Purpose | Allowlisted headless |
|---|---|---|
| `query "<SQL>"` | Read-only SQL (§7 guard) | yes |
| `related <path \| "text"> [--limit N]` | Candidate notes ranked by FTS5 score + shared tags + shared links | yes |
| `backlinks <note>` | Notes linking to a note | yes |
| `orphans` | `wiki/` notes with no inbound links | yes |
| `friction` | Notes with `is_friction = true`, newest first | yes |
| `issues [--staged]` | Schema + link issues | yes |
| `validate <file>…` | Validate specific files (used for config/codebases) | yes |
| `field <file> <key>` | Print one frontmatter value (dotted keys for maps) | yes |
| `rebuild` | Drop and rebuild the index | yes |
| `set <file> <key> <value>` | Line-based replace or insert of a **top-level scalar** in frontmatter (preserves comments and order), then validate | **no** |

**Read-only guard for `query`:** opens the db with `file:…?mode=ro` and installs a `sqlite3` authorizer that permits only `SELECT`, `READ` and `FUNCTION` actions (rejects `ATTACH`, `PRAGMA` writes, DML, DDL). Result rows are capped (default 200, `--limit`).

**Performance target (non-gating benchmark):** incremental refresh of a 2,000-note vault with no changes completes in under 1 s; `related` returns in under 200 ms.

## 7. Permissions

Committed `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Read", "Glob", "Grep",
      "Edit(/wiki/**)", "Edit(/briefings/**)",
      "Bash(system/scripts/brief_prep.sh:*)",
      "Bash(system/scripts/debrief_prep.sh:*)",
      "Bash(system/scripts/lint_vault.sh:*)",
      "Bash(system/scripts/vault_index.py query:*)",
      "Bash(system/scripts/vault_index.py related:*)",
      "Bash(system/scripts/vault_index.py backlinks:*)",
      "Bash(system/scripts/vault_index.py orphans:*)",
      "Bash(system/scripts/vault_index.py friction:*)",
      "Bash(system/scripts/vault_index.py issues:*)",
      "Bash(system/scripts/vault_index.py validate:*)",
      "Bash(system/scripts/vault_index.py field:*)",
      "Bash(system/scripts/vault_index.py rebuild:*)"
    ]
  }
}
```

- Applies to interactive and headless sessions. Anything not listed prompts interactively and is denied headlessly. `vault_index.py set` is deliberately not listed, so untrusted content cannot change config.
- Untrusted content in `raw/` can therefore, at worst, edit wiki and briefing notes and run read-only index queries.
- `/setup` writes the user's codebase paths into the gitignored `.claude/settings.local.json` as `permissions.additionalDirectories`, so interactive `/impact` can read them without prompts.
- **Must verify during implementation** (against current Claude Code docs, with a headless smoke test using a stub vault): leading-`/` path rules resolve relative to the settings file; `Edit(...)` rules cover file creation by Write; `Bash(<cmd> <subcommand>:*)` prefix rules match as intended and reject chained commands; `@system/config.md` import is harmless when the file is missing; how headless sessions are identifiable in transcripts (§6.5).

## 8. Config and codebase files

Both are validated by their schemas (§6.16). Examples:

`system/config.md` (gitignored; `system/config.example.md` committed):

```yaml
---
type: config
timezone: America/Denver
brief_time: "06:00"
debrief_time: "17:00"
telemetry_enabled: false
remote_mode: none           # private | none | keep; set by setup_remote.sh
template_remote:            # set by setup_remote.sh
superpowers:
  - <strategic anchor>
---
```

`system/codebases/<name>.md` (gitignored except `example.md`, which ships `default: false` so it never collides with a user's `unique_true` default):

```yaml
---
type: codebase
name: ultron
path: ~/code/worktrees/main
default: true
stack: [vue3, dotnet]
search_globs: [ "*.vue", "*.ts", "*.js", "*.cs", "*.csproj" ]
layers:
  ui: ultron-ui/
  api: Ultron.Api/
namespace_prefix: Ultron.
---
Free-form notes for agents: conventions, gotchas, owners.
```

With a real YAML parser, `stack` and `search_globs` are proper lists.

## 9. Commands, prompts and personas

Editing rule: change only text that is false, unimplementable, or contrary to this design. Persona and communication rules are preserved.

**`CLAUDE.md`**
- Replace "Anti-Refusal Stance" with: "When an action is blocked (permission, missing tool, missing input), state in one line what was blocked and what is needed."
- Remove "Intent Gate Audit" (unimplemented; the vault can't observe code changes).
- Reword "Fail-Fast Loop Breaker" to the real mechanism: `check_metrics.sh` + quarantine in `/backup`.
- "Kusto Intake Hook" → "Production Telemetry Routing": files in `raw/telemetry/` are critical and route to SystemMaintenance.
- **Index-first rule:** "Before reading notes to find context, query the index (`vault_index.py related|query|backlinks|friction`). Read only the notes it returns. Never grep or read all of `wiki/`."
- **Schema rule:** "Every note's frontmatter must match `system/schemas/<type>.md`. A new note type requires a new schema note."
- Directory map and script list updated to §5. Codebase Map becomes: "Codebases are defined in `system/codebases/`. Read the relevant file before touching code." Add `@system/config.md`.
- No Ultron/Vue/.NET/Kusto names.

**Commands**

| Command | Behaviour |
|---|---|
| `/setup` | §11 flow |
| `/brief` | Load config; run `brief_prep.sh` if today's inputs are missing; read `inputs/<date>/`, `alerts_<date>.md`, `raw/telemetry/` (label `mock: true` items), and `vault_index.py friction`; create `briefings/<date>.md` from the template only if missing; fill Morning Alignment and Friction Matrix; tie objectives to superpowers. Gmail/Slack steps run only if such a source is available in the session; otherwise one line says they were skipped. |
| `/debrief` | Run `debrief_prep.sh` if missing; read `git.md`, `transcript.md`, `focus.md`, alerts, metrics; fill Evening Debriefing; extract explicit user preferences/goals from the transcript digest into wiki notes (checking `related` first to update rather than duplicate); never copy secrets. |
| `/ingest` | Step 2 context discovery = `vault_index.py related <file>`, then read only those notes. Use `system/templates/wiki-concept.md`; `compiled_at` = today's date (YYYY-MM-DD); source link uses the raw file's basename (`[[<stem>]]`, or `[[<name.ext>]]` for non-markdown); link `[[Index]]`; friction regex narrowed to `\b(not sure|waiting on|stuck|blocked|tbd|double-check)\b` (case-insensitive) → `is_friction: true`; finish with `vault_index.py validate` on written files; no git commands. |
| `/query` | `vault_index.py related "<question>"` (and `query` for structured questions), read only the returned notes, answer with "Sources Compiled". |
| `/lint` | Run `lint_vault.sh` and `vault_index.py orphans`, present results, then add LLM-only analysis (link suggestions for orphans, likely duplicates via `related`); ask before fixing. |
| `/backup` | `check_metrics.sh` → quarantine flagged agents (move persona to `system/quarantine/<Agent>.stalled`, alert); `verify_setup.sh` (blocks on failure); `system_health.bats` (report only); `git status`; stage; commit (hook lints); push per `remote_mode`: `private` → `origin`, refusing if `origin` URL equals `template`; `none` → skip push; `keep` → push `origin`. |
| `/impact <component> [--repo name]` | Search each (or the named) codebase with its `search_globs`; use `layers` to match API routes to UI consumers, across repos; cross-reference wiki via `related "<component>"`; group results by repo; read-only. |

**Personas:** CodingAgent gets the metrics filename convention `system/logs/metrics/CodingAgent-<epoch>.json` and the `agent` field. All personas lose Ultron-specific wording.

**Templates:** each declares its `type:`. `wiki-concept.md` links `[[Index]]` and `[[{{source_stem}}]]`; `compilation-metric.json` gains `"agent"`. `daily-briefing.md` replaces the hardcoded `(08:00)`/`(17:00)` with `{{brief_time}}`/`{{debrief_time}}`, filled from config by `/brief`.

**`wiki/Index.md`** (`type: index`) ships Dataview blocks: friction nodes, recently compiled concepts, notes by `agent_owner`. They render as plain code blocks if Dataview isn't installed.

## 10. Git and Obsidian configuration

`.gitignore`:

```
.obsidian/workspace*.json
.obsidian/graph.json
.claude/settings.local.json
system/config.md
system/codebases/*.md
!system/codebases/example.md
system/logs/*
!system/logs/.gitkeep
system/index.db
system/index.db-wal
system/index.db-shm
system/index.lock
__pycache__/
```

- `system/quarantine/` is tracked (it holds the user's own raw notes). The hook lives in `.githooks/` and is activated by `setup_remote.sh` via `core.hooksPath`.
- Dataview is not committed (no plugin binaries in git). The README tells users to install it from Obsidian's community plugins; `/setup` reminds them in its final report.

## 11. `/setup` flow

Every phase is idempotent and safe to re-run.

0. **Preflight:** `check_deps.sh`; list missing items with install hints; continue with affected features marked off (no PyYAML blocks setup, since validation needs it).
1. **Existing config:** if `system/config.md` exists, show values and ask which to change; otherwise start from `config.example.md`.
2. **Global interview** (one question at a time, defaults shown): timezone, brief time, debrief time, superpowers, telemetry enabled (default no). Write config; run `config_validate`; fix and retry on error.
3. **Codebases:** ask for a directory → `discover_codebases.sh` → user picks repos. For each: `inspect_codebase.sh` → draft `system/codebases/<name>.md` → confirm each field → `config_validate`. Loop "add another directory?". Existing codebase files are shown and edited, not replaced. Write `additionalDirectories` to `.claude/settings.local.json`.
4. **Remote:** ask private URL / none / keep → `setup_remote.sh`.
5. **Units:** `install_units.sh`.
6. **Calendar auth:** non-interactive `gcalcli list`; on failure, tell the user to run `! gcalcli init`.
7. **Index:** `vault_index.py rebuild`, then `issues`; report any problems.
8. **Verify:** `verify_setup.sh --health`; `systemctl --user list-timers`.
9. **Hand-off:** for each codebase without one, create `wiki/<Name>OnboardingAssignment.md` (schema-valid, `agent_owner: CodingAgent`) directing a map of layers, logging/telemetry definitions (seeded from `logging_hints`) into `wiki/<Name>LogEventMap.md`, linked to the superpowers.
10. **Report:** status table of every provisioned item, plus the Dataview reminder.

Scripts called during `/setup` that are not allowlisted prompt the user; that is intentional.

## 12. Testing

Gating suites (must pass on every commit in the implementation and in `/backup`): `vault_integrity.bats`, `scripts.bats`, `pytest system/tests/python`.

- **`vault_integrity.bats`** (runs anywhere): required dirs and files exist (each agent persona must exist in `system/agents/` **or** as `system/quarantine/<Agent>.stalled`, so a quarantine never blocks later backups); scripts executable; `.githooks/pre-commit` executable; `.claude/settings.json` is valid JSON; every `*.in` unit contains at least one `{{` placeholder; no `/home/` path committed under `system/systemd/`; a schema note exists for every template's `type:`; `system/index.db` is not tracked; `lint_vault.sh` reports no errors on the committed template vault.
- **`pytest system/tests/python`** (fixture vault under `fixtures/vault/`, copied to a temp dir per test):
  - frontmatter: none, empty, malformed YAML → issue (no crash); `---` inside body ignored; error line numbers
  - schema: each field kind valid/invalid; `required`; `default` not written; `enum`; `list(of)`; `map`; `unique_true` across files; `path must_exist`; unknown field → warning; type/folder mismatch → error; schema notes validate against `schema`
  - links: alias/heading/embed/path forms; code fence and inline code ignored; basename vs path resolution; non-`.md` targets; dead link → error
  - index: first build populates all tables; unchanged refresh re-parses nothing; edit → only that note re-parsed; delete → rows removed and inbound links become dead; new file resolves previously dead links; schema change → full rebuild; corrupt db → rebuilt; concurrent refresh serialized by lock
  - views: one `v_<type>` per schema; defaults applied; typed columns
  - query guard: `SELECT` works; `INSERT`, `ATTACH`, `PRAGMA journal_mode=…`, `CREATE` rejected; row cap
  - related: fixture where the expected note ranks first by FTS + shared tags
  - `set`: replaces scalar, inserts missing key, preserves comments and order, refuses non-scalar keys, re-validates
  - templates: every `system/templates/*.md` renders with sample values and validates against its schema
  - benchmark (marked, non-gating): 2,000 generated notes, refresh < 1 s, related < 200 ms
- **`scripts.bats`** (temp vault via `VAULT_ROOT`, stubs from `fixtures/` first on `PATH`):
  - intake: unterminated marker leaves briefing intact; terminated block extracted and removed; no wiki output → quarantine + alert; claude exit 1 → quarantine; production_error → `raw/telemetry/`; archive collision renamed before ingest; fresh file skipped; briefing never created
  - lint wrapper: exit 1 on error issue, 0 on warnings only; `--staged` limits scope; pre-commit hook blocks on error and passes with nothing staged
  - check_metrics: three failing → flagged; two failing + one pass → not flagged; warnings > 5 → flagged; no metrics → exit 0
  - install_units: placeholders replaced; TZ substituted; second run `unchanged`; telemetry not enabled when false; `--uninstall` ignores foreign units; `--dry-run` writes nothing
  - setup_remote: rename + add; refuses origin == template; `--none`; `--keep`; idempotent re-run; hooksPath set; config keys written
  - lib_config: get/default/`~` expansion; set; codebase listing excludes example; `layers.ui`; list values comma-joined; validate exit codes
  - brief_prep/debrief_prep: outputs written; missing gcalcli recorded in `unavailable.md` and exit 0; transcript digest keeps only user/assistant text from a fixture jsonl; headless sessions excluded; slug derivation
  - focus_stats: top notes; fragmentation window flagged at 5 switches, not at 4
  - telemetry_enricher: writes only to `TELEMETRY_DIR`; namespace match selects repo; fallback search; `mock: true` present; output validates against schema
  - discover/inspect: fixture repos (Vue + .NET pair, Go module, Python package, repo with two worktrees) produce expected JSON
  - run_headless: log file written; exit code passed through
- **`system_health.bats`** (advisory): config present and valid; timers active (telemetry only if enabled); focus tracker active; `core.hooksPath` = `.githooks`; push target consistent with `remote_mode`; `check_deps.sh --strict`; index builds with no errors.
- **Headless smoke test** (manual, once, recorded in the plan): real `claude -p` against a temp vault confirms the §7 assumptions, including that `vault_index.py set` is denied.

## 13. Finding traceability

| Review finding | Resolution |
|---|---|
| H1 headless runs can't write; archive on false success | §7 allowlist; §6.5 prep scripts; §6.4 output-based success |
| H2 mock telemetry on a live timer | §6.12 timer gated by `telemetry_enabled`; §6.8 `mock: true`, writes to `raw/telemetry/` |
| H3 unterminated marker deletes briefing | §6.4 step 1 |
| H4 pre-commit never fails | §6.10, §6.11, §6.16 |
| H5 re-runs clobber state | §4 generator removed; §11 idempotent setup; §6.12/§6.13 idempotent scripts |
| M1 daemon creates template-less briefing | §6.4 step 3 alerts file |
| M2 production errors archived before `/brief` sees them | §6.4 routing; §9 `/brief` reads `raw/telemetry/` |
| M3 debrief reads its own transcript | §6.5 prep runs before the session; headless sessions excluded |
| M4 backups blocked by service state | §6.15, §12 health suite advisory |
| M5 BATS deletes real telemetry | §6.8 `TELEMETRY_DIR`; §12 temp vault |
| M6 enricher ignores configured codebase | §6.8 codebase selection via §6.1 |
| M7 logs committed; no-op negations; settings.local not ignored | §10 |
| M8 untrusted content + anti-refusal hides failures | §7 (incl. `set` not allowlisted, query guard); §9 `CLAUDE.md` |
| L1 dependency lists disagree; herdr | §6.2; README documents herdr as optional |
| L2 BRAIN_TZ vs setup mismatch | §6.12 rendering from config |
| L3 noisy friction regex; `$CURRENT_DATE` | §9 `/ingest` |
| L4 metrics naming inconsistent | §6.9 |
| L5 archive collisions overwrite | §6.4 rename before ingest |
| L6 worktree `.git` check; duplicate check | Moot: generator removed; scripts use `git rev-parse` |
| L7 `@{u}` fails without upstream | §6.5 `--since` per repo |
| New: template links missing `[[IndexNote]]` | §5 `wiki/Index.md`; §9 template |
| New: `[[raw/…]]` source links die on archive | §9 basename links; §6.4 rename before ingest |
| New: baseline generation installs LLM hook | §4 step 1 |
| New: multiple codebases | §6.1, §6.14, §8, §11 step 3 |
| New: agent context cost grows with vault | §6.17 index; §9 index-first rule and command changes |
| New: frontmatter rules duplicated across templates/lint/prompts | §6.16 schemas + drift guard; §12 template tests |

## 14. Out of scope

- Storing machine data (metrics, focus samples, alerts, telemetry) in SQLite; it stays as files for now and can be indexed later.
- An Obsidian plugin that reads `index.db`; Obsidian-side querying is Dataview over frontmatter.
- A filesystem watcher for the index; refresh-on-command is sufficient.
- Embedding/vector search; FTS5 + tags + links ranking first.
- Live Gmail/Slack intake via read-only claude.ai connector tools and a `sources:` config key.
- A real Kusto query replacing the mock enricher.
- CI running the test suites.
- `herdr` integration beyond a README mention.
