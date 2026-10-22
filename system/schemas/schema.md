---
type: schema
schema_for: schema
folders: ["system/schemas/"]
fields:
  type: {kind: const, value: schema, required: true, readers: [system/scripts/vaultlib/schema.py]}
  schema_for: {kind: string, required: true, readers: [system/scripts/vaultlib/schema.py]}
  folders: {kind: list, of: string, required: true, readers: [system/scripts/vaultlib/schema.py]}
  fields: {kind: fieldspecs, required: true, readers: [system/scripts/vaultlib/schema.py]}
  reserved_tag: {kind: bool, default: "false", readers: [system/scripts/vaultlib/schema.py]}
---
# Schema
Defines a note type. `folders` lists vault-relative folders (ending in `/`, matching all subfolders) or exact file paths where the type may live. `fields` maps each frontmatter key to a field spec with `kind` and optional `required`, `default`, `values`, `value`, `of`, `fields`, `must_exist`, `unique_true`, `matches_folder`, and the `readers` every field carries: the vault paths of the scripts, hooks or command files that read the field by name (validation and the index's generic field table do not count). `readers: []` marks a field nothing reads; `test_schema_readers.py` checks each path exists and names the field, and warns on an empty list. `reserved_tag: true` makes the type's name a system tag, written only on its own notes (lint warns elsewhere). Adding a note type means adding a schema note. Spec §6.15.
