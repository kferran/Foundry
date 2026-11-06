---
name: market
contract: 1
description: "A daily page of what changed among the companies and bodies you watch, from their newsrooms and feeds"
requires: []
sources:
  - {name: market, credential: "", renew: ""}
smoke:
  - {source: market, timeout: 30, connector: false, run: "scripts/market_fetch.py --check"}
brief: true
commands:
  - {name: market, targets: ["briefings/market/<date>.md"], model_key: market_model, timeout_key: market_timeout_minutes}
units:
  - {name: foundry-market, roles: [standalone, server]}
alert_tags:
  - {tag: market_source, severity: now}
  - {tag: market, severity: now}
allow: ["Bash(extensions/market/scripts/market_fetch.py --check)"]
deps: []
index_ignore: ["raw/market"]
budget:
  values: {TIMEOUT: 30, WORKERS: 8, FETCH_LIMIT: 300, NOTIFY_LIMIT: 120}
  steps:  # market_unit.py: the fetch, then run_headless.sh market (run.lock, then the session), then after-publish
    - "market 1 - FETCH_LIMIT"
    - "market 1 - headless.lock"
    - "market 1 grace.headless headless"
    - "market 1 - NOTIFY_LIMIT"
---
**Market watch.** Each morning, 30 minutes before the brief, `foundry-market` reads the newsrooms and feeds of the companies and bodies you list in `market_watch`, and the trade-press feeds in `market_press`, and writes the items it has not seen before to `raw/market/<date>/candidates.jsonl`. A press item counts only when it names one of your entries. When there are new candidates, the unit then runs `run_headless.sh market`, a rating session that writes the day's page `briefings/market/<date>.md`. After the page publishes, the unit posts each alert-group threat to Slack, adds an `owed` Now line per proposed change, and drops a copy in `raw/inbox/` for ingest. The brief carries one Market line.

**Data handling.** It fetches only the HTTPS addresses you list, with no credentials and one fixed user agent, follows redirects only on the same host, and stops any response at 4 MB. It keeps the keys of the items it has seen for 30 days in `system/logs/market_state.json`. Summaries are cut to 500 characters and redacted. The fetch runs no model and sends nothing anywhere; a source that fails three runs in a row raises one `[market_source]` alert. The rating session has the headless profile with no network: it reads only the candidates, recent market pages and the notes of `market_partition`, and writes only its staged page, which the publish gate checks. Only `market_unit.py` posts (`[market]` threat lines, once per link for 14 days) or adds Now lines.

**Setup.** Skipped on a client.
1. Ask for the groups you watch (your own labels, for example vendors, partners, distribution, standards bodies).
2. For each group, ask for its entries. For each entry: its name; its newsroom page and its RSS or Atom feed (either, both, or neither: an entry with neither is matched only through the press feeds); a `match` path prefix when the newsroom's release links do not sit under the page's own path (`/` for releases at the site root); an `exclude` regex for titles to drop (for example release candidates).
3. Ask for the trade-press feeds to sweep (`{name, feed}`).
4. Write them into `system/config.md` as `market_watch` and `market_press` (`extensions/market/templates/config.example.md` shows the form), run `system/scripts/vault_index.py validate system/config.md`, then `extensions/market/scripts/market_fetch.py --check` after the first morning run.
