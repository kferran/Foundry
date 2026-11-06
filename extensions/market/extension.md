---
name: market
contract: 1
description: "A daily page of what changed among the companies and bodies you watch, from their newsrooms and feeds"
requires: []
sources:
  - {name: market, credential: "", renew: ""}
smoke:
  - {source: market, timeout: 30, connector: false, run: "scripts/market_fetch.py --check"}
units:
  - {name: foundry-market, roles: [standalone, server]}
alert_tags:
  - {tag: market_source, severity: now}
allow: ["Bash(extensions/market/scripts/market_fetch.py --check)"]
deps: []
index_ignore: ["raw/market"]
budget:
  values: {TIMEOUT: 30, WORKERS: 8}
  out: "the HTTP poller: no session; 8 sources at a time, each with its own 30 s limit"
---
**Market watch.** Each morning, 30 minutes before the brief, `foundry-market` reads the newsrooms and feeds of the companies and bodies you list in `market_watch`, and the trade-press feeds in `market_press`, and writes the items it has not seen before to `raw/market/<date>/candidates.jsonl`. A press item counts only when it names one of your entries.

**Data handling.** It fetches only the HTTPS addresses you list, with no credentials and one fixed user agent, follows redirects only on the same host, and stops any response at 4 MB. It keeps the keys of the items it has seen for 30 days in `system/logs/market_state.json`. Summaries are cut to 500 characters and redacted. It runs no model and sends nothing anywhere; a source that fails three runs in a row raises one `[market_source]` alert.

**Setup.** Skipped on a client.
1. Ask for the groups you watch (your own labels, for example vendors, partners, distribution, standards bodies).
2. For each group, ask for its entries. For each entry: its name; its newsroom page and its RSS or Atom feed (either, both, or neither: an entry with neither is matched only through the press feeds); a `match` path prefix when the newsroom's release links do not sit under the page's own path (`/` for releases at the site root); an `exclude` regex for titles to drop (for example release candidates).
3. Ask for the trade-press feeds to sweep (`{name, feed}`).
4. Write them into `system/config.md` as `market_watch` and `market_press` (`extensions/market/templates/config.example.md` shows the form), run `system/scripts/vault_index.py validate system/config.md`, then `extensions/market/scripts/market_fetch.py --check` after the first morning run.
