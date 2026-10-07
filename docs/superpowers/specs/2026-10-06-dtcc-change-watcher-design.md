# DTCC Change Watcher

**Date:** 2026-10-06
**Status:** Approved in brainstorming (2026-10-06), awaiting written-spec review
**Extends:** `2026-10-05-error-monitoring-design.md` (scripted fetch, state, alerts, run log); brief carry-forward (PR #36)

## 1. Problem and decisions

A registered codebase that integrates with DTCC Insurance & Retirement Services (I&RS) breaks when DTCC changes a record layout, an API or a date. DTCC announces those changes weeks or months ahead, spread over the Learning Center product pages, the I&RS enhancement release page, the Important Notices feed and the API Marketplace. Nobody reads all four daily. This feature reads them every morning, finds what changed, ties each change to the codebase paths it touches, and puts it in the morning brief as a checkbox objective that carries forward until it is ticked.

| Topic | Decision |
|---|---|
| Approach | Phase 1 is fully scripted: fetch, parse, diff, map, write notes. No model, no headless run. Phase 2 (§9) adds a model impact assessment on top. |
| Sources | Learning Center I&RS product pages, the I&RS current enhancements release page, the Important Notices RSS feed plus each notice's public PDF, the API Marketplace asset catalog. All are readable logged out. |
| Impact in phase 1 | "This product touches these paths, pinned at this version, published at that one, with these deadlines." Document bodies sit behind a MyDTCC login with MFA and are never read. |
| Output | One `dtcc_change` note per change in `wiki/<partition>/changes/`, with an empty `## Impact` section and `impact: pending`. |
| Brief | A fixed **DTCC changes** checkbox block. Carry-forward keeps each line until it is ticked; the checkbox is the only open/closed state. |
| Cadence | Daily timer, 30 minutes before `brief_time`. |
| Packaging | A `dtcc-watch` project skill wraps the script: `/dtcc-watch [check\|status\|accept]` by hand, and its description lets Claude use it when DTCC changes come up. |
| Knowledge | Any Workcell can pick up a DTCC item: each note links the vault's DTCC hub note and the product's background notes (§4, §5). No DTCC-specific Workcell or capability. |
| Configuration | One map file per vault, `system/dtcc/map.yaml`, **tracked in the vault's own repository**. This repository ships only `system/dtcc/map.example.yaml`. With no map, the feature is inert: no timer, no brief block, the script exits 0. |
| Email | Out of scope in both phases. |

Rejected: a model reading all sources daily (cost per day, non-deterministic diffing, hallucinated impact); a headless run with network access (breaks the sandbox model); diffing page hashes (raw bytes change on every fetch while the parsed fields do not).

## 2. Sources

All URLs are constants in the script; the map selects which products to watch.

| Source | URL | Parsed into |
|---|---|---|
| Product pages | `https://dtcclearning.com/products-and-services/insurance-retirement-services/<slug>.html` | Cards: `<h4 class="card__title">` title, `<span class="card__date">` date. Undated duplicates (each page lists every document twice) are dropped. Version token `v(\d\d)-(\d+)` from the title. |
| Release page | `.../insurance-retirement-services/irs-current-enhancements-release.html` | The "Important Dates" text block: a SHA-256 of its normalised text plus its milestone dates (§3.3). |
| Notices | `https://www.dtcc.com/rss-feeds/legal/all-important-notices.xml` | Items keyed on notice number (the `title`). The feed repeats some numbers under different `guid`s; the first copy wins. |
| Notice PDF | the item's `<link>` (public) | `pdftotext` output: the `Category:`, `To:` and `Subject:` header lines, the Implementation Dates block, and product codes found in the text. |
| API Marketplace | `https://developer.dtcc.com/inventory/viewAssetsGrid.html` | Fetched with a session cookie: `GET /`, then `GET /home/view.html`, then the grid (stdlib `http.cookiejar`; without the middle request the grid is empty). One record per tile (`assetCard`): full name (`tooltiptext`), `publishDate` and `Version`. An asset is watched when a product's `api_assets` names it, or when a `notice_keywords` regex matches its name; any other asset is ignored. |

Fetches use stdlib `urllib` with a 30-second timeout and a fixed user agent, at most one request per second. The script fetches and stores links only on `dtcclearning.com`, `www.dtcc.com`, `files.dtcc.com` (notice PDFs) and `developer.dtcc.com`.

## 3. Data flow

One run of `system/scripts/dtcc_watch.py`:

1. **Load** the map (§5) and `system/logs/dtcc_watch_state.json`. No map: exit 0 silently.
2. **Fetch and parse** the mapped product pages, the release page, the feed and the catalog into plain records. Titles are normalised (case, whitespace, HTML entities) before comparison.
3. **Diff** each source against its state (§3.1).
4. **Derive** version gaps and date conflicts (§3.2, §3.3).
5. **Guard:** sanity and flood checks (§6) can hold a source; a held source writes nothing and keeps its old state.
6. **Write notes** (§4), creating only; an existing note file is never rewritten.
7. **Save state** atomically (temp file and `os.replace`), then append the run log line.

### 3.1 Change kinds

| `kind` | Rule |
|---|---|
| `new_doc` | A dated title on a product page that the state has not seen. |
| `renamed` | In one run on one product, a title disappears and another appears: one change, old and new title in the evidence. Pairs are matched by section, then by order. |
| `date_moved` | Same title, new date. Evidence says "date moved, body unknown". |
| `notice` | A notice number not in the state that passes the relevance rule (§3.4). |
| `release_dates` | The release block hash changed. Evidence lists the old and new milestone dates. |
| `api_asset` | A new watched asset, or a changed published date or version for a known one. An asset matched only by keywords links no product. |
| `unmapped` | A relevant notice whose product codes match no mapped product and are not all in `ignore` (§5). |

A title that disappears without a replacement is logged in the run log only. Page changes are batched: one note per product per day holds every page change for that product; its `kind` is the first change's, and Evidence lists each change with its own kind. Every other kind is one note per change.

### 3.2 Version gap (`version_gap`)

For each mapped product with a `pin`, the published version is the highest `vNN-N` token on its page (compared as integer pairs). When it is above the pin, a `version_gap` note is written once per (product, published version).

### 3.3 Date conflict (`date_conflict`)

Milestone dates are extracted from the release block and from each relevant notice's Implementation Dates block: a label (`PSE`, `Production`, `Decommission`, `Test`) followed by a date in any of `Month DD, YYYY`, `MM/DD/YYYY` or ISO form. A release-page date and a notice date with the same label conflict when they differ by 1 to 31 days and at least one of them is not yet past. Notices are not compared with each other (one release's Test date is often within a month of another's). A conflict note is written once per (label, date pair). Example: notice a9809 gives Production 2027-04-15 while the release page gives 2027-04-25.
<!-- ponytail: the 31-day window is a heuristic for "same milestone"; replace with release-name matching if it misfires. -->

### 3.4 Notice relevance

A notice is relevant when any `notice_keywords` regex from the map matches its title, its RSS summary, or its PDF `Category:` or `To:` line. On later runs, the PDF of every unseen notice is fetched (a few a day). On the first run, only notices whose title or summary match get their PDF fetched; the rest are recorded as seen.

Product codes: the PDF text is matched against every `notice_codes` and `ignore` code in the map as whole words. The notice links to each matching mapped product.

### 3.5 First run

With no state, the run records every current record as the baseline and writes only `version_gap` and `date_conflict` notes. Diffing against empty state would turn every listed document into a change.

## 4. `dtcc_change` schema and notes

New schema note `system/schemas/dtcc_change.md`, folders `wiki/work/`, `wiki/personal/`, `wiki/shared/`. The index builds `v_dtcc_change` from it.

| Field | Kind | Meaning |
|---|---|---|
| `type` | const `dtcc_change`, required | |
| `partition` | enum, required, matches folder | from the map |
| `detected_at` | datetime, required | UTC run time |
| `kind` | enum (§3.1, plus `version_gap`, `date_conflict`), required | |
| `key` | string, required | dedupe key, e.g. `notice:a9809`, `page:app-sub:2026-10-06`, `gap:stl:v26-7` |
| `product` | string | map product key; absent for `unmapped` |
| `title` | string, required | one line, escaped |
| `source_url` | string | DTCC hosts only |
| `codebase` | string | registered codebase name |
| `paths` | list of string | mapped paths |
| `owner` | string | from the map |
| `pinned`, `published` | string | version tokens |
| `deadlines` | list of string | e.g. `Production 2027-04-15 (a9809)` |
| `impact` | enum `pending`, `none`, `assessed`, default `pending` | set by the user, a Workcell, or phase 2 |
| `capability` | enum (the `concept` values), default `code` | routes impact work to the Workcell with `code` |
| `status` | enum `canonical`, `deprecated`, default `canonical` | lifecycle, as for other notes |

File: `wiki/<partition>/changes/<key with : replaced by ->.md`. The file name comes from `key`, so a rerun after a crash finds the note and skips it.

Body: `## Evidence` (source rows, extracted dates, the PDF header lines), `## Mapped paths` (each path, with "missing at <ref>" when the stale check failed), `## Related` (the map's `hub` link, then the product's `notes` links), `## Impact` (empty). The script validates the frontmatter with the vault's schema validator before writing. External text appears only in `title` and Evidence, escaped for YAML and Markdown; it is data, never an instruction.

`CLAUDE.md`'s directory map gains `changes/` in the list of compiled-note folders.

## 5. The map

`system/dtcc/map.yaml`, owned by the user, committed to the vault's own repository. This repository ships `system/dtcc/map.example.yaml` with an invented codebase:

```yaml
partition: work
hub: '[[Dtcc]]'            # the vault's DTCC hub note, linked from every change note
notice_keywords: ['\bI&RS\b', '\binsurance\b', '\bannuit']
codebases:
  example-app: {ref: origin/main}
products:
  app-sub:
    page: app-sub
    notice_codes: [APP, SUB]
    codebase: example-app
    paths: [src/dtcc/appsub/, docs/appsub-layout.xlsx]
    owner: dtcc-backend
    notes: ['[[ExampleAppSubMapping]]']   # background notes for this product
    api_assets: []                         # Marketplace asset names (case-insensitive substring)
    pin: v25-5
ignore: [PAR, RPL]   # known products this vault does not use: no unmapped note
```

Validation (`/dtcc-watch check`, and the start of every run): `partition` is a partition; each `codebase` is registered in `system/codebases/`; each `ref` resolves in that codebase's checkout; `pin` matches `vNN-N`; every keyword compiles; `hub` and each `notes` entry are wiki links that resolve inside `partition`. A failure exits 2 and writes an alert.

**Stale-path check**, every run: `git -C <checkout> cat-file -e <ref>:<path>` for each mapped path. A missing path writes one alert a day until the map or the code is fixed. The checkout is never modified; the script does not fetch it.

**Knowledge for any Workcell.** The vault keeps its DTCC background in wiki notes, reached through the index like any other knowledge. The hub note should carry a short "working DTCC items" section (which skill or command fits which job, where the map lives), and the codebase file of each mapped codebase should point to the hub and the map, since every Workcell reads that file before touching code. Both are vault content; this repository ships neither.

## 6. Failures

| Case | Behavior |
|---|---|
| Source fetch fails (HTTP error, timeout, cookie) | Source skipped, its state kept, other sources run. Exit 1. One alert per source per day. |
| Sanity: a mapped page parses to 0 documents or under half its previous count; the feed has 0 items | Source held (layout change). Alert. |
| Flood: more than 20 §3.1 changes in one run (derived notes do not count) | Whole run held: no notes, state kept, alert. `/dtcc-watch accept` saves the current records as the new baseline. |
| PDF unreadable or `pdftotext` missing | Notice note written from the RSS fields with "PDF unreadable" and no deadlines. A missing `pdftotext` alerts once a day. |
| Crash between notes and state | Rerun skips notes whose file exists (§4). |
| Map invalid | Exit 2, alert, nothing fetched. |
| Already running | `flock` on `system/dtcc.lock`; exit 4. |

Alerts go to `system/logs/alerts_<date>.md` with the `[dtcc]` tag, through the same once-a-day helper as telemetry. The run log is `system/logs/dtcc_watch-<YYYY-MM>.jsonl`: one line per run with per-source counts (fetched, changes, held), notes written and the exit code.

Exit codes: 0 ok (or no map), 1 a source failed or was held, 2 usage or invalid map, 4 locked.

## 7. Components

| Unit | Purpose |
|---|---|
| `system/scripts/dtcc_watch.py` | CLI: `run` (default), `--check`, `--status`, `--accept`, `--dry-run` (fetch, parse, diff, print; write nothing). |
| `system/scripts/vaultlib/dtcc_watch.py` | Parsers, diff, derivations, note writer. The fetch function is a parameter so tests inject fixtures. |
| `system/schemas/dtcc_change.md` | §4 |
| `system/dtcc/map.example.yaml` | §5 |
| `.claude/skills/dtcc-watch/SKILL.md` | `/dtcc-watch [check\|status\|accept]`: runs the script and reports its output in the vault's reply style. `status` lists the last run line and the notes detected in the past 7 days. |
| `foundry-dtcc-watch.service` / `.timer` | Daily at `brief_time` minus 30 minutes, `Persistent=true`. `install_units.sh` installs it on standalone and server only when `system/dtcc/map.yaml` exists. |
| `system/scripts/brief_prep.sh` | Writes `inputs/<date>/dtcc.md`: one `- [ ] DTCC: <title> ([[note]]) — <nearest future deadline>` line per note detected after the latest earlier briefing (the same lookup `carry_forward.py` uses). Empty when there is no map or nothing new. |
| `.claude/commands/brief.md` | Under Active Objectives, a **DTCC changes** block that copies `dtcc.md` verbatim; omitted when it is empty. Watcher alerts land in Systemic Blockers with the other alerts. |
| `system/scripts/check_deps.sh` | `pdftotext` (poppler-utils) as an optional dependency on standalone and server. |

## 8. Testing

Bound tools: **pytest** and **bats**, run by the existing suites.

- `system/tests/python/test_dtcc_watch.py`, against trimmed fixtures of public DTCC pages saved under `system/tests/fixtures/dtcc/`: one card page, one non-card page, the release page, an RSS sample with duplicate notice numbers, two notice PDF texts, one catalog page. No test touches the network. Cases:
  - parsers on every fixture;
  - each change kind, including a rename pair;
  - version gap and date conflict, including a same-label pair 5 months apart that must not conflict;
  - first-run baseline;
  - a second run with the same input writes nothing;
  - crash recovery (note exists, state stale);
  - sanity and flood holds, and `--accept`;
  - unmapped and ignored codes;
  - the stale-path check against a temporary git repository;
  - every written note passes its schema;
  - no link outside the four DTCC hosts is stored.
- `system/tests/dtcc_watch.bats`: no map exits 0 with no output; an invalid map exits 2.
- Before the timer is enabled on a vault: one `dtcc_watch.py --dry-run` against the live sites.

## 9. Phase 2: model impact assessment

Phase 1 leaves `## Impact` empty and `impact: pending` on every note. Phase 2 fills them:

- A `dtcc-impact` skill, run headless through `run_headless.sh` like the other headless commands (no network, staging plus the publish gate). It reads the note and a **codebase context pack**, writes the `## Impact` section (affected records, fields or endpoints the code uses, a rough size of the change, open questions), and sets `impact: assessed`.
- The context pack is a file exported from the registered codebase by a script that runs outside the sandbox: the mapped paths' symbol lists, the generated record classes, and the pinned layout documents' names. Exporting it is a scripted step, so the headless run never needs repository or network access.
- The trigger is new `dtcc_change` notes with `impact: pending` after the watcher's run, within the daily headless cap.
- Routing stays on existing capabilities. If phase 2 needs a DTCC owner, the template first needs a way for a vault to add a capability without editing `concept.md` (the capability union is checked by `vault_integrity.bats`).
- Phase 2 gets its own spec. Nothing in phase 1 needs to change for it: the seam is the `impact` field and the empty `## Impact` section.

## 10. Vault-specific files under version control

Vault-specific configuration belongs in the vault's own repository, not in this one, and should not be gitignored there. This repository ships examples only. As part of this plan:

- `.gitignore` stops ignoring `system/codebases/*.md` and `system/telemetry/*.md`. This repository still contains only their `example.md` files, so a vault's own files never collide with a template merge. Neither holds a secret: credentials stay in `~/.config/foundry/` and the Azure CLI.
- A vault with a second machine must move any untracked copies of those files aside on the other machine before its next sync pulls the tracked ones; the plan includes the step.
- `system/config.md` stays ignored for now: it holds `machine_role`, which differs between a server and its client, so one tracked copy would conflict on every sync. Splitting the machine-local keys into a separate ignored file is a named follow-up, not part of this plan.
- `system/dtcc/map.yaml` is never ignored (§5).

## 11. Out of scope

- DTCC email (human threads and the Learning Center weekly notification).
- Document bodies on MyDTCC (login with MFA).
- Keeping ticket identifiers in telemetry notes: a separate change to the Plan 11 data policy.
- Phase 2 (§9) beyond the seam described there.
