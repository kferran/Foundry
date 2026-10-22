---
type: schema
schema_for: memo
folders: ["wiki/work/memos/"]
reserved_tag: "true"
fields:
  type: {kind: const, value: memo, required: true}
  tags: {kind: list, of: string}
---
A note type the demo extension's script writes, tagged `memo`; the tag is reserved to it.
