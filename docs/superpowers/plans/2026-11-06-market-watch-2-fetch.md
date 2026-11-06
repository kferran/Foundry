# Market watch, PR 2 (the fetch) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `market` extension whose unit reads the watch list's newsrooms and feeds and the press feeds each morning, without a model, and writes the day's new items to `raw/market/<date>/candidates.jsonl`.

**Architecture:** `extensions/market/` holds the manifest, a config schema fragment, an example config, and three modules under `scripts/marketlib/`: `http.py` (one capped HTTPS GET with a fixed user agent and same-host redirects), `parse.py` (feeds and newsroom pages to items) and `run.py` (sources from config, per-source state, matching, caps, candidates, failure alerts, `--check`). `scripts/market_fetch.py` is the unit's entry point under `api.guard`. The smoke row's `--check` reports the last fetch for the brief's Sources line.

**Tech Stack:** Python 3 standard library (`urllib.request`, `xml.etree.ElementTree`, `html.parser`, `concurrent.futures`), pytest, systemd unit templates.

**Spec:** `docs/superpowers/specs/2026-10-31-market-watch-design.md` §3.1, §3.2, §4 and §7 item 2, as amended on 2026-11-06 (M1–M13, owner's decisions on #236)

## Global Constraints

- Extension scripts import vaultlib only through `vaultlib.api` (`test_extension_api.py:72`): `config`, `load`, `save`, `alert`, `guard`, `redact_credentials`.
- No company, body, site or industry names in any committed file; examples use `example.com`/`example.org` hosts and names like `Vendor A`.
- HTTPS only; one user agent, `Mozilla/5.0 (compatible; foundry-market/1.0)`; a 30-second timeout per request; a 4 MB body cap; redirects only to the same host; no credentials; no retry under another user agent.
- Summaries are cut to 500 characters and passed through `redact_credentials`.
- At most 25 candidates per group per run, newest first; the rest are marked seen and counted in `raw/market/<date>/held.json`.
- Failure alerts: tag `market_source`, severity `now`, one alert when a source's streak of failed runs reaches 3; classes `auth`, `network`, `timeout`, `other`.
- No core change in this PR (`system/scripts`, `system/hooks`, `.claude/commands` untouched), so the core cap stays.
- Smoke budget: the `foundry-smoke` limit has about 150 s left (3,150 of 3,300 s); the market row's timeout is 30.
- Run only the changed files' suites locally (`system/scripts/test.sh <paths>`); the extension's tests run in CI's `gate-all-extensions`.
- Test file basenames are unique across all test folders (`test_market_*.py`).

## Rulings against the spec

- **Ruling 1, a source's first fetch is a baseline.** §3.2 calls "a link not seen before" new, which on the first run makes every listed item a candidate. A source with no state records its items as seen and yields none. Cost if wrong: the first day's page is empty; the live acceptance in PR 3 uses fixture candidates.
- **Ruling 2, the smoke row carries the Sources line.** §3.2 has `brief/prep.sh` read the fetch log and call `prep_source`. `sources.report` already takes a listed source's reading from its smoke row (`vaultlib/sources.py:114-121`), so the manifest lists `sources: [{name: market, …}]` and the row runs `market_fetch.py --check`, which reads the state the morning fetch left. `brief/prep.sh` arrives in PR 3 for the Market line. Cost if wrong: none; a later `prep_source` call overrides the smoke reading.
- **Ruling 3, sources are fetched 8 at a time.** About 62 sources at 30 s each could take 31 minutes in sequence. `run.py` uses a thread pool of `WORKERS = 8`, so the worst case is about 4 minutes, inside `TimeoutStartSec=10min`. Cost if wrong: a busy host sees 8 parallel requests at most, one per source.
- **Ruling 4, a press item names one entry.** When a press item names several entries, its candidate takes the first in `market_watch` order. Cost if wrong: the rating sees one entry name where two apply; the item text still names both.

## Review Focus

1. A newsroom page or feed that is huge, binary, not UTF-8, or malformed XML/HTML: one `bad` failure for that source; the others still run. (Task 3 and Task 4 tests.)
2. A redirect to another host, to `http://`, or a redirect loop: refused as `bad` (off-host) or `network`, never followed. (Task 2 test.)
3. A config entry with an `http://` URL, an invalid `exclude` regex, or a `match` that is not a path: that source fails with class `other` and a reason naming the entry; the run goes on. (Task 4 test.)
4. Two runs on the same day: the second adds only new items, appends to `candidates.jsonl`, and sums `held.json`. (Task 4 test.)
5. `system/logs/market_state.json` missing, empty or corrupt: the run treats it as no state (every source takes a baseline) and rewrites it; it never crashes. (Task 4 test.)

---

### Task 1: The extension's manifest, config schema and docs

**Files:**
- Create: `extensions/market/extension.md`, `extensions/market/schemas/config.md`, `extensions/market/templates/config.example.md`, `extensions/market/tests/python/conftest.py`, `extensions/market/tests/python/test_market_config.py`
- Modify: `FOUNDRY.md` ("What the Foundry offers" row, "What each extension needs" row, a Market watch paragraph after the Intraday one, line 119's area)
- Create: `changes/2026-11-06-market-fetch.md`

**Interfaces:**
- Produces: config keys `market_watch` (list of maps `{name (required), group (required), newsroom, feed, match, exclude}`), `market_press` (list of maps `{name (required), feed (required)}`), `market_runs_per_day` (int, min 1, max 4, default `"1"`), `market_model` (string, default `"sonnet"`), `market_timeout_minutes` (int, min 1, default `"20"`), `market_alert_groups` (list of string), `market_keep_groups` (list of string), `market_partition` (enum `work`, `personal`, default `work`).
- Produces: `conftest.py` fixture `vault` (the core fixture vault plus `extensions/market`, with `extensions: [market]` in `system/config.md`), following `extensions/telemetry/tests/python/conftest.py`.

- [ ] **Step 1: Write the failing tests** in `test_market_config.py`:
  - `test_the_manifest_loads_with_no_reasons`: `extensions.check(vault) == []` (import through the core test path as telemetry's tests do) and `market` is in `extensions.enabled(vault)`.
  - `test_the_example_config_validates`: copy the frontmatter keys of `templates/config.example.md` into the vault's `system/config.md`, then `system/scripts/vault_index.py validate system/config.md` exits 0.
  - `test_a_watch_entry_needs_a_name_and_group`: an entry `{newsroom: "https://example.com/news"}` fails validation naming `name`.
- [ ] **Step 2: Run** `system/scripts/test.sh extensions/market/tests/python` → FAIL (no extension).
- [ ] **Step 3: Write the files.**
  - Manifest: `name: market`, `contract: 1`, `description: "A daily page of what changed among the companies and bodies you watch, from their newsrooms and feeds"`, `requires: []`, `sources: [{name: market, credential: "", renew: ""}]`, `smoke: [{source: market, timeout: 30, connector: false, run: "scripts/market_fetch.py --check"}]`, `units: [{name: foundry-market, roles: [standalone, server]}]`, `alert_tags: [{tag: market_source, severity: now}]`, `allow: ["Bash(extensions/market/scripts/market_fetch.py --check)"]`, `deps: []`, `index_ignore: ["raw/market"]`, `budget: {values: {TIMEOUT: 30, WORKERS: 8}, out: "the HTTP poller: no session; 8 sources at a time, each with its own 30 s limit"}`. The body: one paragraph on what it does and its data handling (what it fetches, from where, what it stores, that nothing is sent), then a **Setup** list: ask for the groups, then entries per group (name; newsroom and/or feed, or neither for name-only; `match` and `exclude` when needed), then the press feeds; write them into `system/config.md`; run `vault_index.py validate system/config.md` and `extensions/market/scripts/market_fetch.py --check`.
  - Config schema: the keys above in `intraday/schemas/config.md`'s form, with a body explaining each key (including M1's name-only entries, M2's `match`, M12's `exclude`, M9 and M10).
  - Example config: frontmatter with two groups, one entry of each shape (newsroom only, feed only, both with `match`, name-only, one with `exclude: "-rc\\d*\\b"`) on `example.com`/`example.org`, and one press feed.
  - FOUNDRY.md: the offers row `| [market](#daily-use) (extension) | A daily page of what changed among the companies and bodies you watch | \`extensions: [market]\` | \`foundry-market\` | \`market\` | \`raw/market/<date>/\` candidates; \`[market_source]\` alerts |` (match the columns of the telemetry row); the needs row `| \`market\` | the watch list and press feeds in \`system/config.md\` | none | \`market_watch\`, \`market_press\`, \`market_runs_per_day\`, \`market_model\`, \`market_timeout_minutes\`, \`market_alert_groups\`, \`market_keep_groups\`, \`market_partition\` | none yet |`; and a **Market watch.** paragraph: what the unit fetches at `{{PRE_BRIEF_TIME}}`, the rules (HTTPS, one user agent, 4 MB, same-host redirects, 25 per group), where candidates go, and that the rating and the brief line arrive with the next PR.
  - Change file: `- Added: the \`market\` extension's fetch: each morning it reads your watch list's newsrooms and feeds and your press feeds into \`raw/market/<date>/\` (#<PR number>)` with `  - Action: list your groups, entries and press feeds in \`system/config.md\` (see \`extensions/market/templates/config.example.md\`), then add \`market\` to \`extensions\`.`
- [ ] **Step 4: Run** the market tests and `system/scripts/test.sh system/tests/vault_integrity.bats system/tests/python/test_source_rule.py system/tests/python/test_extensions.py` → PASS.
- [ ] **Step 5: Commit** `feat(market): the extension's manifest, config keys and docs (#236)`.

### Task 2: `marketlib/http.py`, one capped HTTPS GET

**Files:**
- Create: `extensions/market/scripts/marketlib/__init__.py` (empty), `extensions/market/scripts/marketlib/http.py`
- Test: `extensions/market/tests/python/test_market_http.py`

**Interfaces:**
- Produces: `UA = "Mozilla/5.0 (compatible; foundry-market/1.0)"`, `TIMEOUT = 30`, `MAX_BYTES = 4 * 1024 * 1024`; `class MarketError(Exception)` with `.kind` in `{"auth", "network", "timeout", "bad"}` and `.reason: str`; `get(url: str) -> bytes`.
- Stub seam: when `FOUNDRY_MARKET_STUB` names a folder, `get` reads `<folder>/routes.json` (`{url: {"status": int, "file": str, "location": str}}`), returns the file's bytes for 200, follows `location` for 301/302/303/307/308 through the same redirect rule, and appends each URL to `<folder>/requests.log`.

- [ ] **Step 1: Write the failing tests** (all through the stub seam, `monkeypatch.setenv`):
  - `test_a_200_returns_the_body`; `test_401_and_403_are_auth`; `test_429_and_5xx_are_network`; `test_404_is_bad`.
  - `test_a_body_over_4_mb_is_bad`: a 4 MB + 1 byte file → `MarketError` kind `bad`, reason containing `4 MB`.
  - `test_a_same_host_redirect_is_followed_and_another_host_is_refused`: `https://example.com/a` → `/b` on the same host returns `/b`'s body; a `location` of `https://example.org/x` or `http://example.com/b` → kind `bad`, reason naming the target host.
  - `test_a_redirect_loop_stops`: two routes pointing at each other → `MarketError` (kind `bad`) after at most 5 hops.
  - `test_a_non_https_url_is_refused_without_a_request`: `http://example.com/feed` → kind `bad`; `requests.log` is absent.
  - `test_the_request_sends_the_fixed_user_agent`: patch `urllib.request.urlopen` (no stub env) to capture the `Request`; its `User-Agent` header equals `UA`.
- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `get` with `urllib.request.build_opener` and a `HTTPRedirectHandler` subclass whose `redirect_request` raises `MarketError("bad", f"redirect to {host}")` unless the new URL is `https` on the original host (max 5 hops, as `max_redirections`). Read `resp.read(MAX_BYTES + 1)` and refuse a longer body. Map `HTTPError` codes as in the tests, `socket.timeout`/`TimeoutError` to `timeout`, other `URLError`/`OSError` to `network` with the host in the reason. The stub path applies the same scheme, host and size rules.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(market): one capped HTTPS GET with same-host redirects (#236)`.

### Task 3: `marketlib/parse.py`, feeds and newsroom pages to items

**Files:**
- Create: `extensions/market/scripts/marketlib/parse.py`, fixtures under `extensions/market/tests/fixtures/` (`rss.xml`, `atom.xml`, `rss-quirks.xml`, `newsroom.html`, `newsroom-root.html`)
- Test: `extensions/market/tests/python/test_market_parse.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Item: key: str; title: str; link: str; published: str; summary: str` (`published` is ISO `YYYY-MM-DD` or `""`); `feed_items(body: bytes) -> list[Item]`; `newsroom_items(body: bytes, page_url: str, match: str = "") -> list[Item]`. Both raise `http.MarketError("bad", …)` on input they cannot parse.

- [ ] **Step 1: Write the failing tests:**
  - `test_rss_items_carry_guid_title_link_date_summary`: `rss.xml` with two items → keys are the `guid` values; `published` is ISO.
  - `test_atom_entries_key_by_id`: `atom.xml` → keys are the entry `id`s, links from `link[@href]`.
  - `test_an_item_without_guid_keys_by_link`.
  - `test_quirks_parse`: `rss-quirks.xml` has `<pubDate>Thu, 05 Nov 26 10:00:00 GMT</pubDate>` → `published == "2026-11-05"`, and `<title>Release <a href="x">4.2</a> ships</title>` → `title == "Release 4.2 ships"`; an unparseable date gives `""`.
  - `test_malformed_xml_is_bad`: `b"<rss><channel><item>"` → `MarketError` kind `bad`; `b"\xff\xfe junk"` too.
  - `test_newsroom_links_under_the_page_path`: `newsroom.html` at `https://example.com/news/` → same-host links under `/news/` only; off-host links, `#` anchors, the page itself and `mailto:` are left out; the key is the absolute link and the title is the link text, whitespace collapsed.
  - `test_a_match_prefix_finds_root_and_dated_links`: `newsroom-root.html` at `https://example.com/about/newsroom.html` with `match="/"` → links like `/2026/08/slug` and `/slug` are found; with `match="/press-releases/"` only those.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with `xml.etree.ElementTree.fromstring` (namespaces for Atom: `{http://www.w3.org/2005/Atom}`), `email.utils.parsedate_to_datetime` for RSS dates (a two-digit year is read by it as 20YY, which the test pins; fall back to `datetime.fromisoformat` for Atom), and an `html.parser.HTMLParser` subclass collecting `<a href>` and its text. Title tags are stripped with the same parser's text collection, not a regex.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(market): parse feeds and newsroom pages into items (#236)`.

### Task 4: `marketlib/run.py` and `market_fetch.py`, the run and `--check`

**Files:**
- Create: `extensions/market/scripts/marketlib/run.py`, `extensions/market/scripts/market_fetch.py` (executable, telemetry_fetch.py's shape, `guard(…, VAULT, "foundry-market", "market_source", alerting=not sys.argv[1:])`)
- Test: `extensions/market/tests/python/test_market_run.py`

**Interfaces:**
- Consumes: `http.get`, `http.MarketError`, `parse.feed_items`, `parse.newsroom_items`, `parse.Item`.
- Produces: `main(argv: list[str], vault: Path, today: date | None = None) -> int` (0 all sources ok, 1 any failed, 2 usage); `--check` prints `market_fetch: ok: <n> sources` (exit 0) or `market_fetch: <class>: <n> of <m> sources failed; first <source>: <reason>` (exit 1), or `market_fetch: other: no fetch today` (exit 1), from state alone, with no network.
- State, `system/logs/market_state.json` through `api.load`/`api.save`: `{"sources": {<source id>: {"seen": {<key>: "YYYY-MM-DD"}, "streak": int, "class": str, "reason": str, "last_ok": "YYYY-MM-DD"}}, "last_run": "YYYY-MM-DD"}`. A source id is `<entry name>:newsroom`, `<entry name>:feed` or `press:<name>`. Each key holds the day it was last seen on its source; a key not seen for 30 days is dropped.
- Candidates: one JSON line per item in `raw/market/<date>/candidates.jsonl`, `{source, entry, group, title, link, published, summary}`; `raw/market/<date>/held.json` `{<group>: <count>}` summed over the day's runs.

- [ ] **Step 1: Write the failing tests** (stub seam from Task 2, fixtures from Task 3, `today=date(2026, 11, 6)`):
  - `test_a_first_fetch_is_a_baseline_and_the_next_yields_new_items`: run once → no candidates, state has the keys; add an item to the fixture, run again → one candidate line with the entry's name and group.
  - `test_a_name_only_entry_is_never_fetched_but_matches_press_items`: `requests.log` has no URL for it; a press item whose title says `Vendor B` (whole word, any case) becomes a candidate with `entry: "Vendor B"` and its group; `Vendor Bx` does not.
  - `test_a_press_item_naming_no_entry_is_dropped`.
  - `test_exclude_drops_matching_titles`: `exclude: "-rc\\d*\\b"` drops `Runtime 9.0.0-rc2` and keeps `Runtime 9.0.0`.
  - `test_a_feed_out_of_date_order_gives_each_item_once`: the same items reordered on the second run → no candidates.
  - `test_a_group_over_25_passes_the_newest_25_and_holds_the_rest`: 30 new items in one group → 25 lines, newest first by `published` (undated last), `held.json == {"<group>": 5}`; the 5 are in state as seen; a second same-day run with 3 more held sums to 8.
  - `test_summaries_are_cut_and_redacted`: a 900-character summary holding `token=abc123def456ghi789` → 500 characters at most and the token masked (`redact_credentials`' mask).
  - `test_one_failed_source_does_not_stop_the_others_and_three_failed_runs_alert_once`: one route 503 → exit 1, the other source's candidate is written; runs 1–2 write no `[market_source]` line, run 3 writes one (`alerts_<date>.md`), run 4 no second one; a success resets the streak to 0.
  - `test_a_bad_entry_fails_that_source_only`: an `http://` newsroom, an `exclude` of `"("` and a `match` of `"news"` (no leading `/`) each fail their source with class `other` naming the entry.
  - `test_a_missing_or_corrupt_state_file_starts_over`: state file `""` or `"{"` → the run takes baselines and writes valid JSON.
  - `test_check_reports_from_state_alone`: after an all-ok run → exit 0 and `market_fetch: ok: 3 sources`; after a run with one `auth` failure → exit 1 and the line starts `market_fetch: auth: 1 of 3 sources failed; first `; no run today → `market_fetch: other: no fetch today`. `requests.log` gains nothing from `--check`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `main`. Read `market_watch` and `market_press` with `api.config(vault)` (`or []`). Build the source list (skip name-only entries; validate scheme, `match` and `exclude` per source before fetching). Fetch with `concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS)`. For each result: baseline or new items by key; press items through the whole-word match (`re.compile(rf"\b{re.escape(name)}\b", re.I)`, entries in config order); `exclude`; group caps; write candidates and `held.json`; update streaks and alert with `api.alert(vault, day, clock, "market_source", f"{source}: {class}: {reason} (3 failed runs)", key=source)` when a streak reaches exactly 3; save state once at the end. Log one line per source to stderr (the unit's journal). `market_fetch.py` takes `--check` or no arguments; anything else is usage (exit 2).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(market): the fetch run, its state and --check (#236)`.

### Task 5: The unit and the timing rule

**Files:**
- Create: `extensions/market/units/foundry-market.service.in`, `extensions/market/units/foundry-market.timer.in`
- Test: `system/tests/conformance.bats`, `system/tests/python/test_source_rule.py`, `system/tests/scripts.bats` (existing; run, not changed)

- [ ] **Step 1: Write the units.** The service is telemetry's shape: `Type=oneshot`, `WorkingDirectory={{VAULT_ROOT}}`, `Environment="TZ={{TZ}}"`, `Environment="PATH={{UNIT_PATH}}"`, `TimeoutStartSec=10min`, `SuccessExitStatus=1`, `ExecStart="{{VAULT_ROOT}}/extensions/market/scripts/market_fetch.py"`. The timer: `OnCalendar=*-*-* {{PRE_BRIEF_TIME}}:00 {{TZ}}`, `Persistent=false`, `WantedBy=timers.target`.
- [ ] **Step 2: Run** `system/scripts/test.sh system/tests/conformance.bats system/tests/scripts.bats system/tests/python/test_source_rule.py system/tests/python/test_smoke.py` → PASS. A failure here is a manifest value (budget `values` must match `TIMEOUT = 30` and `WORKERS = 8` in `http.py`/`run.py`; the smoke row's timeout must fit the smoke limit).
- [ ] **Step 3: Commit** `feat(market): the foundry-market unit at the pre-brief time (#236)`.
