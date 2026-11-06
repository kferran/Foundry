---
type: schema
schema_for: config
fields:
  market_watch: {kind: list, of: {kind: map, fields: {name: {kind: string, required: true}, group: {kind: string, required: true}, newsroom: {kind: string}, feed: {kind: string}, match: {kind: string}, exclude: {kind: string}}}}
  market_press: {kind: list, of: {kind: map, fields: {name: {kind: string, required: true}, feed: {kind: string, required: true}}}}
  market_runs_per_day: {kind: int, min: "1", max: "4", default: "1"}
  market_model: {kind: string, default: "sonnet"}
  market_timeout_minutes: {kind: int, min: "1", default: "20"}
  market_alert_groups: {kind: list, of: string}
  market_keep_groups: {kind: list, of: string}
  market_partition: {kind: enum, values: [work, personal], default: work}
---
The market extension's keys (market watch spec §3.1). `market_watch` lists the companies and bodies you watch, each `{name, group}` with an HTTPS `newsroom` page, an RSS or Atom `feed`, both, or neither (a name-only entry is never fetched and is matched only through the press feeds). `match` is a path prefix for a newsroom's release links (default: the page's own path; `/` for releases at the site root). `exclude` is a regex on item titles; a matching item is dropped (for example `-rc\d*\b` for release candidates). `market_press` lists the trade-press feeds, `{name, feed}`; a press item counts only when it names a `market_watch` entry as a whole word. `market_runs_per_day` (1 to 4) is how many runs a day the unit makes. `market_model` and `market_timeout_minutes` are the rating run's model and time limit (at most the harness's own). `market_alert_groups` names the groups whose threats post to Slack (empty: all groups). `market_keep_groups` names the groups whose low-impact items stay on the page under News. `market_partition` is the partition whose notes the rating reads.
