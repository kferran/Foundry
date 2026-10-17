---
type: schema
schema_for: index
folders: ["wiki/Index.md"]
fields:
  type: {kind: const, value: index, required: true, readers: [system/scripts/vaultlib/schema.py]}
  tags: {kind: list, of: string, readers: [system/scripts/vaultlib/index.py]}
---
# Index
The cross-partition entry point and dashboards, `wiki/Index.md` only. It is the one note exempt from partition link walls.
