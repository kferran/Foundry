---
name: items
contract: 1
description: "A fixture extension whose source is checked once per item its list prints"
requires: []
smoke:
  - {source: items, timeout: 30, connector: false, each: "scripts/items_list.sh", run: "scripts/items_check.sh {}"}
---
The fixture for per-item sources: the smoke check and the Sources line read one line per listed item.
