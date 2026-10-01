---
type: schema
schema_for: schema
folders: ["system/schemas/"]
fields:
  type: {kind: const, value: schema, required: true}
  schema_for: {kind: string, required: true}
  folders: {kind: list, of: string, required: true}
  fields: {kind: fieldspecs, required: true}
---
# Schema
Defines a note type. `folders` lists vault-relative folders (ending in `/`, matching all subfolders) or exact file paths where the type may live. `fields` maps each frontmatter key to a field spec with `kind` and optional `required`, `default`, `values`, `value`, `of`, `fields`, `must_exist`, `unique_true`, `matches_folder`. Adding a note type means adding a schema note. Spec §6.15.
