---
type: schema
schema_for: codebase
folders: ["system/codebases/"]
fields:
  type: {kind: const, value: codebase, required: true}
  name: {kind: string, required: true}
  path: {kind: path, required: true, must_exist: warn}
  partition: {kind: enum, values: [work, personal, shared], required: true}
  default: {kind: bool, default: "false", unique_true: true}
  stack: {kind: list, of: string}
  search_globs: {kind: list, of: string, required: true}
  layers: {kind: map, of: string}
  nightshift_hosts: {kind: list, of: string}
  nightshift_plugins: {kind: list, of: string}
  nightshift_pr: {kind: string}
---
# Codebase
One registered codebase, produced by `/setup` discovery and inspection. The body holds free-form notes for agents.
