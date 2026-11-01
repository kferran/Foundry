# Market watch: a daily page of what changed among the companies and bodies you track

**Date:** 2026-10-31
**Status:** draft, for the owner's review
**Grill:** 2026-10-16, decisions recorded on https://github.com/kferran/Foundry/issues/236 (phase 1; phase 2 waits for its own grills)
**Builder check:** 2026-10-31, four questions and six wrong claims. Settled as my calls: the page's partition and what the rating reads (§3.3, §3.4); the rating's tools (§3.3); the timing (§3.6); tracker proposals as a page section (§3.4, §3.5); and the corrected facts (web access, the link form, the Sources reading, the redaction export, alert keys, and what the harness needs). Where the rating runs is the owner's (question 3).
**Blueprint:** Poller (the fetch), plus a Compile run (the rating); see the Blueprint checklist.
**Lane:** feature, an extension (`extensions/market/`) and one new headless command; about three pull requests (§7).

## 1. Why

You want to know each morning what changed among the companies and bodies that shape your position (vendors, partners, distribution, standards and industry bodies), so a threat or an opening reaches you before a meeting does. Today it is manual one-off research, and nothing watches for news.

## 2. Goals, non-goals, anti-goals

- **Goals:** one daily page, `briefings/market/<date>.md`, written before the brief. Each item says what changed, why it matters to you, and links its source. The brief carries one line linking the page. A threat item posts one Slack line. Facts reach the entity notes through ingest.
- **Non-goals (phase 2 on #236, each grilled first):** customer input, findings by bucket with claim states, dedupe with counts, page snapshots and diffs of pricing or changelog pages, the weekly review, decision packs.
- **Anti-goals:**
  - No names of companies, bodies, sites or the industry in the template: the vault supplies them.
  - No model session with network access (#416), and no new web tool in any profile.
  - Nothing outside the vault but the notify channel ever hears from the run.

(Fact, for question 1: since #416 a `run_headless.sh` session has no network. Research Work Orders keep WebFetch to the hosts the owner listed, and WebSearch is denied in every profile.)

## 3. Design

### 3.1 The watch list and the press list (vault configuration)

`extensions/market/schemas/config.md` adds two keys to `system/config.md`. Both are lists of maps, like `watch_channels`:
- `market_watch`: `{name, group, newsroom, feed}`, one per entry. `group` is the vault's own label, for example one of four groups. `newsroom` is an HTTPS page URL and `feed` an RSS or Atom URL; at least one is set.
- `market_press`: `{name, feed}`, the trade-press feeds to sweep.

The extension also adds `market_runs_per_day` (int, default 1), `market_model` (default `sonnet`) and `market_timeout_minutes` (default 20). The template ships an example block in `extensions/market/templates/config.example.md` with placeholder entries only.

### 3.2 Fetch (Poller, no model)

`extensions/market/scripts/market_fetch.py` runs from the extension's unit at `{{PRE_BRIEF_TIME}}` and again for each extra run of the day (§3.6). Per source (each watch entry's newsroom and feed, each press feed):
- It reads the source over HTTPS with the standard library, with a 30-second timeout and a size cap. It follows the shape of telemetry's `http.py`: the same error classes (auth, transient, bad) and the same stub seam for tests.
- **A feed** is parsed with `xml.etree` (RSS 2.0 items and Atom entries): title, link, date, summary.
- **A newsroom page** is parsed with `html.parser`: the set of article links on it (same host, a path deeper than the page's own). A link not seen before is a new item; the title is the link text.
- It keeps per-source state in `system/logs/market_state.json`: the item links seen in the last 30 days, the last success and the failure streak. It writes atomically, like telemetry's store.
- **A press feed's item** is a candidate only when its title or summary names a watch entry (`name`, matched as a whole word, case-insensitive).
- New candidates go to `raw/market/<date>/candidates.jsonl`: one object per item with `{source, entry, group, title, link, published, summary}`. Summaries are cut to 500 characters and passed through `redact_credentials`, the extension API's redaction.
- One failed source never stops the others. A failure is logged and, after 3 failed runs in a row, alerted once with its class (`[market_source]`, severity `now`, like `telemetry_source`; the class maps to the Sources classes: auth, network, timeout, other).
- The brief's Sources line shows the fetch's state: `brief/prep.sh` reads the fetch log and calls `prep_source market ok|failed <class>`, as intraday does. A smoke row runs the fetch's `--check`.
- Only the hosts named in `market_watch` and `market_press` are fetched. The script runs no model and sends nothing.

### 3.3 Rate (Compile run)

The rating is its own headless run (owner, question 3), with no network and ingest's tools (Read, Glob, Grep, the `vault_index.py` reads, and the staging write).

**A generic headless command for extensions.** It is built first, as its own PR, since it touches the harness and the gate.
- **The manifest field:** an extension's manifest may declare `commands: [{name, targets, model_key, timeout_key}]`.
  - `name` is a lowercase word that is not a core command.
  - `targets` are path patterns under `briefings/<name>/` or `wiki/<partition>/`, with `<date>` and `<partition>` filled in at run time.
  - `model_key` and `timeout_key` name the extension's config keys.
- **`run_headless.sh <name>`** runs it when the extension is enabled:
  - it reads the prompt from `extensions/<ext>/commands/<name>.md`, not `.claude/commands/`, so no slash command appears;
  - it takes its targets from the manifest;
  - it passes `--model`;
  - its timeout is the key's value, at most `HEADLESS_TIMEOUT`.
  It refuses a name that no enabled extension declares.
- **The gate's run-id pattern** accepts a declared command's name, read from the enabled manifests; nothing is hard-coded per extension.
- **The market rating** is `commands: [{name: market, targets: ["briefings/market/<date>.md"], model_key: market_model, timeout_key: market_timeout_minutes}]`.
- **It reads** today's candidates, the last 14 days of market pages (to drop repeats) and, through the index, the entity and project notes of the page's partition for the entries named. It never reads another partition.
- **For each candidate** it gives:
  - a kind: `threat`, `opening` or `watch`;
  - an impact: `high`, `medium` or `low`;
  - one sentence on why it matters to you, grounded in those notes;
  - the source link.

  It drops `watch` items rated `low`.
- **It writes** `briefings/market/<date>.md` to staging, the run's only target. The gate checks it against the `market_page` schema. A later run the same day stages the existing page and rewrites it with all of the day's items: it keeps every heading and every earlier item, so the gate's shrink guard holds.
- **It is capped** at `market_timeout_minutes` (default 15, at most `HEADLESS_TIMEOUT`) and runs on `market_model`. A run past its cap is stopped, and the brief says `Market: unavailable (timeout)`.

### 3.4 The page (`market_page`, an extension schema)

- **Frontmatter:** `type: market_page`, `date`, `partition` (`market_partition`, default `work`; `shared` is refused, like intraday's fallback, since the rating grounds its sentences in one partition's notes), `provenance: [headless]`, `sources` (the item links) and `counts` (`{threat, opening, watch}`).
- **Body:** `## Threats`, `## Openings`, `## Watch` and `## Proposed changes`, each present even when empty, the first three ranked by impact. Each item is `**<Entry>**: <what changed>. <Why it matters>. [<source title>](<link>)`. A proposed change is `- [[<project note>]]: <the change> (<link>)`, naming a project note from the index; it is never applied.
- **Folders:** `briefings/market/`. The brief's archive step moves only top-level briefings, so market pages stay where they are.

### 3.5 What the page feeds

- **The brief:** `extensions/market/brief/prep.sh` reads today's page and writes `sections/market.md`, one line:
  - `Market: <N> changes, top: <headline> (<kind>) [[briefings/market/<date>|market]]` (the full path: a bare `[[<date>]]` resolves to the brief itself);
  - or `No market changes`;
  - or `Market: unavailable (<reason>)` when the run failed, timed out or wrote no page.

  `brief/section.md` tells the brief to copy the line as is.
- **Slack:** after the page publishes, `market_notify.py` writes one `[market]` alert line per `threat` item (`Market threat: <entry>: <what changed> <link>`). The `market` tag has severity `now`. Notify redacts what it sends, so a link holding an id may arrive partly masked.
- **Once per threat:** `market_notify.py` keeps the links it has posted in `system/logs/market_state.json` for 14 days. The alert file's own once-a-day key matches only a line's start, within one day.
- **The entity notes:** after the page publishes, a copy of it is dropped in `raw/inbox/` as `market-<date>.md`. Intake routes it to ingest like any other drop, which adds each fact to its entity note with the page as source. (Owner question 2 decides whether it waits for a tick first.)
- **A proposed change:** each `## Proposed changes` line becomes one `owed` Now line, `Review a proposed change to <project>: <the change>`, with `--rec` and no evidence. It is added by `market_notify.py` through `now.py add`, never by the session.
- **No importer:** the extension declares no `importer` for `market_page`, so intake ingests the inbox copy instead of routing it to `raw/market/`.

### 3.6 Runs per day

- **How many:** `market_runs_per_day` (1 to 4) sets how many runs the unit's timer makes. The first is at `{{PRE_BRIEF_TIME}}`, 30 minutes before the brief; each further run is spaced evenly until 18:00.
- **The extra times:** they need one generic `install_units.sh` placeholder (`{{EXTRA_TIMES:<key>}}`, reading a config key), since the template renders only fixed placeholders today.
- **On a slow morning:** the first run fetches, then rates, inside 30 minutes. If `run.lock` keeps it waiting (the template update holds it from 45 minutes before), the brief says `Market: unavailable (still running)` and is never delayed.

## 4. Safety

- **Pages, feeds and search results are data.** The fetch script parses them without a model. The rating session gets them only as candidate text, with no tool beyond the staging write, and the gate checks its one page.
- **Fetching:** only listed hosts, over HTTPS, with no credentials, and redirects only to the same host.
- **Size caps:** each fetch is size-capped, and candidates are cut and redacted.
- **No new network for any session:** the rating run has the headless profile as it is today.

## 5. Tests

- **The fetch:**
  - A stubbed feed and newsroom give new items once.
  - A press item counts only when it names an entry.
  - A failed source does not stop the others; three failures alert once.
  - An off-list redirect is refused.
- **The rating:** a stub run writes a page that the gate accepts; a page outside `briefings/market/` or with a missing count is refused.
- **The brief line:** a page gives one line; no page, a failed run or a timeout give the `unavailable` line.
- **Notify:** a threat item gives one `[market]` line, and the same link the next run gives none.
- **Runs per day:** 2 renders a second timer time with no code change.
- **The cap:** a run past `market_timeout_minutes` exits with the timeout and leaves no page.
- **Live acceptance:** in a throwaway clone, one real rating run over fixture candidates, then the brief line.

## 6. Docs

FOUNDRY.md gets a Market watch paragraph and the setup step: add the extension, then the two lists. The extension's manifest describes its data handling. A change file goes with each PR.

## 7. Delivery

1. **PR 1, extension commands:** the generic `commands` manifest field, `run_headless.sh` and the gate's run id (the owner merges: harness and gate), and the `{{EXTRA_TIMES:<key>}}` unit placeholder.
2. **PR 2, the fetch:** the extension, `market_fetch.py`, the config fragment, the state store, the smoke row and the unit.
3. **PR 3, the rating and what it feeds:**
   - the `market` command prompt and the `market_page` schema;
   - the brief line;
   - `market_notify.py` and the inbox drop;
   - runs per day;
   - the live acceptance.

The core cap and the brief's word cap rise by their measured counts, with the reason beside each.

## Blueprint checklist

**Poller** (the fetch):
- a source's cursor: uses (`market_state.json`, links seen in 30 days)
- alerts: uses (`market_source` after 3 failed runs; `market` for threats)
- unit: uses (`foundry-market.{service,timer}.in` at `{{PRE_BRIEF_TIME}}`)
- no `claude` session: uses

**Compile run** (the rating):
- `run_headless.sh` with restricted settings, a timeout, the daily cap and `run.lock`: uses, after the change question 3 picks. Today the harness hard-codes its commands, targets, timeout and model, and the gate's run-id pattern names its commands.
- staging and `publish.py`: uses (one target, `briefings/market/<date>.md`)

**Defect classes it can reopen:**
- C1 too large: holds by the fetch size cap, the 500-character summaries and the 14-day window.
- C3 timeout: holds by the unit's timing budget in the manifest (`conformance.bats`) and `market_timeout_minutes`.
- C4 confinement: holds by fetch hosts limited to the lists and the unchanged headless profile.
- C5 alerts: holds by alert keys (once per link) and the 3-run failure threshold.
- C7 redaction: holds by summaries through `redact`.
- C8 names: holds by no names in the template (`leak_hits`, the vendor scan).
- C11 input bounds: holds by feed and HTML parsing that tolerates bad input (tests with broken XML and HTML).
- C14 gate escape: holds by the rating's only write, staging, checked by the gate.

## Grill

The decisions are on #236 (owner, 2026-10-16). On 2026-10-31 the owner answered the three questions below, each with the recommended option: (1) the script reads the press feeds, (2) facts reach entity notes through ingest on their own, (3) the rating is its own run, through a generic `commands` manifest field.
1. **Gathering:** the 10-16 decision has a headless agent sweep the trade press "by web search". Since #416, no headless session has network access, and WebSearch is denied in every profile. This spec fetches the trade press's feeds by script instead, so the rating session reads only text the script gathered.
2. **Write-back:** the page reaches entity notes through ingest, as decided. Since then, #301 S9 (PR C, #442) holds research stale claims until you tick them. Market facts are new dated facts with a link; they do not change older claims.
3. **Where the rating runs** (builder check): today the headless harness and the gate know only ingest, brief and debrief. The rating needs either a generic extension field that the harness and the gate read (a change to both safety surfaces, useful to any later extension) or a market section rendered by the brief itself (no new run; the brief grows).
