---
type: index
tags: []
---
# Index

Start here. Compiled knowledge lives in `wiki/work/`, `wiki/personal/` and `wiki/shared/`. Query it with `system/scripts/vault_index.py related "<topic>"`; in Obsidian the dashboards below need the Dataview plugin.

## Friction
```dataview
TABLE partition, compiled_at
FROM "wiki"
WHERE (is_friction = true OR is_friction = "true") AND status != "deprecated"
SORT compiled_at DESC
```

## Recently compiled
```dataview
TABLE partition, codebase
FROM "wiki"
WHERE type = "concept" AND status != "deprecated"
SORT compiled_at DESC
LIMIT 20
```

## By capability
```dataview
TABLE rows.file.link AS notes
FROM "wiki"
WHERE capability
GROUP BY capability
```

## Written by headless runs
```dataview
LIST
FROM "wiki"
WHERE contains(provenance, "headless")
```
