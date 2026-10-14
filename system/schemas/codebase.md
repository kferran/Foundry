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
  order_hosts: {kind: list, of: string}
  order_plugins: {kind: list, of: string}
  order_pr: {kind: string}
  order_toolchain: {kind: list, of: string}
  order_install: {kind: string}
  nightshift_hosts: {kind: list, of: string}
  nightshift_plugins: {kind: list, of: string}
  nightshift_pr: {kind: string}
---
# Codebase
One registered codebase, produced by `/setup` discovery and inspection. The body holds free-form notes for agents.

`nightshift_hosts`, `nightshift_plugins` and `nightshift_pr` are the old names of `order_hosts`, `order_plugins` and `order_pr`. They are still read when the new key is absent; the new key wins when both are set.

`order_toolchain` lists the directories (`~` allowed) that hold the codebase's toolchain executables; a Work Order's sealed verify binds them read-only and puts them first on its PATH, and the plan session's PATH starts with them too. `order_install` is one shell command that installs the project's dependencies; it runs once, before the verify commands, in the same private checkout, with the network open. Neither has an old name.
