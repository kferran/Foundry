---
type: schema
schema_for: market_page
folders: ["briefings/market/"]
fields:
  type: {kind: const, value: market_page, required: true}
  date: {kind: date, required: true}
  partition: {kind: enum, values: [work, personal], required: true}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
  sources: {kind: list, of: string}
  counts: {kind: map, required: true, fields: {threat: {kind: int, min: "0", required: true}, opening: {kind: int, min: "0", required: true}, watch: {kind: int, min: "0", required: true}, news: {kind: int, min: "0", required: true}}}
---
# Market page
The daily market page `briefings/market/<date>.md`, written by the market extension's rating run (market watch spec §3.4). Its body has `## Threats`, `## Openings`, `## Watch`, `## News` and `## Proposed changes`, each present even when empty. Each item is `- **<Entry>**: <what changed>. <Why it matters>. [<source title>](<link>)`; a proposed change is `- [[<project note>]]: <the change> (<link>)` and is never applied by the run.
